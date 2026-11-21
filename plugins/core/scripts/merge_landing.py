#!/usr/bin/env python3
"""Merge the landing branch into a task branch inside the Claude Code sandbox (#50, option D).

Usage: python3 merge_landing.py [-C <worktree>] [--no-ff] <ref>
       python3 merge_landing.py [-C <worktree>] --abort

The sandbox keeps a session from writing its own working directory's `.claude/` and
`.mcp.json`, so a plain `git merge` of a landing branch that changed them dies with
"Operation not permitted" and leaves no merge commit. This tool merges <ref> into the worktree's
HEAD so that the commit is the ordinary merge, while those files on disk stay as the chat
started with them ("frozen .claude"):

  1. `git merge-tree --write-tree HEAD <ref>` computes the result without touching a file.
  2. When the merge changes nothing under .claude/ or .mcp.json compared with HEAD: a plain
     `git merge --no-edit <ref>`.
  3. When it does: the changed protected paths get the skip-worktree bit and are excluded in
     the worktree's own info/sparse-checkout; their on-disk state goes into a manifest in the
     worktree's git dir (work_proof.FROZEN_MANIFEST); then the merge runs with
     `-c core.sparseCheckout=true -c sparse.expectFilesOutsideOfPatterns=true`, so git updates
     the index and leaves those files alone. A file the landing branch deleted stays on disk,
     untracked. The settings go in with -c on each merge, never into git config.
  4. It refuses, changing nothing: a conflict in a protected path (the ship-change skill, step
     2, has the route), a protected path whose file on disk differs from HEAD or from what was
     frozen earlier, any index entry that hides local changes from git status and that it did
     not freeze itself (skip-worktree or assume-unchanged: the merge would not see those
     changes and could lose them), an operation in progress, a sparse checkout of the user's
     own, a primary checkout (land from a worktree), and an untracked file (as git lists it:
     not ignored) where the merge adds a path, whose content differs from the merge's version,
     or that stands where the merge needs a folder or holds untracked files where it puts a
     file (the sparse settings would overwrite it without a word).
  5. The leftovers of a bare `git merge` that died in the sandbox (#108) are taken in on both
     paths when they equal the merge's version: untracked files where the merge adds a path,
     and, after a fast-forward, tracked files it already rewrote or deleted (unstaged). Outside
     .claude/ and .mcp.json they are put back to HEAD's state right before the merge (removed,
     or HEAD's version), so the merge writes the same bytes, and written back byte for byte if
     the merge fails before it begins; on a protected path an untracked one is kept and frozen,
     being the merged version already. A change staged as the merge's version is left to git;
     any other change to a path the merge changes is refused.

A conflict elsewhere, or a hook that refuses, stops the merge as `git merge` does: resolve,
stage by path, commit; or `merge_landing.py --abort`, which runs `git merge --abort` with the
same sparse settings (a plain `git merge --abort` fails on the frozen paths). The frozen paths
stay frozen for the worktree's life, so later merges of the landing branch go
through this tool too; remove_merged_worktree.py and chat_archivable.py accept the frozen paths
while the files on disk match the manifest. What a chat gives up by this: the ship-change
skill, step 2.

Exit 0 merged (or nothing to merge), 1 refused or a conflict, 2 usage or git failure.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from work_proof import (FROZEN_MANIFEST, disk_state, frozen_manifest, git_path,  # noqa: E402
                        protected)

SPARSE = ['-c', 'core.sparseCheckout=true', '-c', 'core.sparseCheckoutCone=false',
          '-c', 'sparse.expectFilesOutsideOfPatterns=true', '-c', 'index.sparse=false']
OPERATIONS = ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply')


def git(tree, *args):
    # paths are file names, never patterns: a `*` in a name must not match other files
    return subprocess.run(['git', '--literal-pathspecs', '-C', tree, *args], capture_output=True,
                          text=True, stdin=subprocess.DEVNULL)


def zlist(text):
    return [item for item in text.split('\0') if item]


def pattern(path):
    """A sparse-checkout line that excludes exactly `path` (gitignore syntax, escaped)."""
    escaped = ''.join('\\' + c if c in '\\*?[' else c for c in path)
    return '!/' + (escaped[:-1] + '\\ ' if escaped.endswith(' ') else escaped)


def merge_result(tree, ref):
    """(result tree, conflicted paths, changed paths) of merging ref into HEAD, or a problem."""
    run = git(tree, 'merge-tree', '--write-tree', '-z', '--name-only', 'HEAD', ref)
    if run.returncode not in (0, 1) or not run.stdout:
        return None, None, None, ('git merge-tree failed (git 2.38 or newer is needed): '
                                  + (run.stderr.strip().splitlines() or ['?'])[0])
    head, _, rest = run.stdout.partition('\0')
    conflicts = zlist(rest.partition('\0\0')[0]) if run.returncode else []
    diff = git(tree, 'diff', '--name-only', '-z', '--no-renames', 'HEAD', head)
    if diff.returncode:
        return None, None, None, 'git diff failed: ' + diff.stderr.strip()[:200]
    return head, conflicts, zlist(diff.stdout), None


def refuse(message):
    print('refused: ' + message, file=sys.stderr)
    return 1


class GitFailed(Exception):
    pass


def chunked(tree, args, paths):
    """zlist of `git <args> -- <paths>`, 500 paths per call; GitFailed when git fails, so a
    failure never reads as "nothing found"."""
    out = []
    for start in range(0, len(paths), 500):
        run = git(tree, *args, '--', *paths[start:start + 500])
        if run.returncode:
            raise GitFailed(f'git {args[0]} failed: ' + run.stderr.strip()[:200])
        out += zlist(run.stdout)
    return out


def untracked(tree, paths):
    """The `paths` (files, or folders: the untracked files under them) git lists as untracked
    and not ignored, with git's own spelling. On a file system that ignores case, a tracked
    `Foo.md` on disk is not an untracked `foo.md`, which os.path.lexists cannot tell."""
    return chunked(tree, ('ls-files', '--others', '--exclude-standard', '-z'), paths)


def identical(tree, result, paths):
    """{path: (mode, blob)} for each of `paths` whose content on disk equals its version in the
    tree `result` (as `git add` would store it: hash-object applies the clean filters)."""
    full = lambda p: os.path.join(tree, *p.split('/'))  # noqa: E731
    wanted = {}
    for record in chunked(tree, ('ls-tree', '-z', result), paths):
        info, _, path = record.partition('\t')
        mode, _, blob = info.split()
        wanted[path] = (mode, blob)
    plain = [p for p in paths if wanted.get(p, ('',))[0] not in ('', '120000') and '\n' not in p
             and os.path.isfile(full(p)) and not os.path.islink(full(p))]
    hashed = subprocess.run(['git', '-C', tree, 'hash-object', '--stdin-paths'],
                            input=''.join(p + '\n' for p in plain), capture_output=True,
                            text=True) if plain else None
    ids = dict(zip(plain, hashed.stdout.split())) if hashed and not hashed.returncode else {}
    same = {}
    for path in paths:
        mode, blob = wanted.get(path, ('', ''))
        if mode == '120000' and os.path.islink(full(path)):
            data = subprocess.run(['git', '-C', tree, 'cat-file', 'blob', blob],
                                  capture_output=True).stdout
            equal = os.fsencode(os.readlink(full(path))) == data
        else:
            equal = bool(blob) and ids.get(path) == blob
        if equal:
            same[path] = (mode, blob)
    return same


def tree_entries(tree, treeish, paths):
    """{path: (mode, blob)} of `paths` in `treeish`."""
    entries = {}
    for record in chunked(tree, ('ls-tree', '-z', treeish), paths):
        info, _, path = record.partition('\t')
        mode, _, blob = info.split()
        entries[path] = (mode, blob)
    return entries


def in_the_way(tree, result, changed):
    """Leftovers in the merge's way outside the protected paths (freeze() judges those):
    ({path: the state to put on disk right before the merge}, a problem or None). A state is
    (mode, blob), or None for no file.

    A bare `git merge` that died in the sandbox (#108) leaves two kinds, both equal to the
    merge's version and both taken in: untracked files where the merge adds a path (state None:
    removed, the merge writes them), and, when it was a fast-forward, tracked files it already
    rewrote (` M`) or deleted (` D`) (state: HEAD's version, which the merge then replaces).
    Any other untracked file in the way is someone's work, which the frozen path's sparse
    settings would overwrite without a word, and any other change to a path the merge changes
    is one git would refuse: both are refused. Ignored files, and changes to paths the merge
    leaves alone, are git's to handle, as in a plain `git merge`."""
    added = zlist(git(tree, 'diff', '--name-only', '-z', '--no-renames', '--diff-filter=A',
                      'HEAD', result).stdout)
    full = lambda p: os.path.join(tree, *p.split('/'))  # noqa: E731
    files, parents, folders = [], set(), []
    for path in added:
        if protected(path):
            continue
        parts = path.split('/')
        for depth in range(1, len(parts)):  # a file where the merge needs a folder
            parent = '/'.join(parts[:depth])
            if os.path.lexists(full(parent)) and not os.path.isdir(full(parent)):
                parents.add(parent)
        if os.path.isdir(full(path)) and not os.path.islink(full(path)):
            folders.append(path)  # a folder where the merge puts a file
        elif os.path.lexists(full(path)):
            files.append(path)
    clear_to, differ = {}, []
    if files or parents or folders:
        loose = set(untracked(tree, files + sorted(parents)))
        present = [p for p in files if p in loose]
        differ = sorted(p for p in parents if p in loose) + untracked(tree, folders)
        same = identical(tree, result, present)
        differ += [p for p in present if p not in same]
        clear_to = {p: None for p in same}
    # tracked paths the merge changes that differ from HEAD: a dead fast-forward's rewrites
    mine = [p for p in changed if not protected(p) and p not in added]
    touched = chunked(tree, ('diff', '--name-only', '-z', '--no-renames', 'HEAD'),
                      mine) if mine else []
    if touched:
        staged = set(chunked(tree, ('diff', '--cached', '--name-only', '-z', '--no-renames',
                                    'HEAD'), touched))
        head, merged = tree_entries(tree, 'HEAD', touched), tree_entries(tree, result, touched)
        index = {}
        for record in chunked(tree, ('ls-files', '-s', '-z'), sorted(staged)) if staged else []:
            info, _, path = record.partition('\t')
            index[path] = info.split()[1]
        on_disk = [p for p in touched if os.path.lexists(full(p))]
        same = identical(tree, result, on_disk)
        for path in touched:
            gone = not os.path.lexists(full(path)) and path not in merged
            if not (path in same or gone):
                differ.append(path)
            elif path in staged:
                # staged as the merge's version: git's to take, as in a plain `git merge`
                if index.get(path) != merged.get(path, ('', None))[1]:
                    differ.append(path)
            elif path in head:
                clear_to[path] = head[path]
            else:
                differ.append(path)
    if differ:
        shown = ', '.join(differ[:10]) + (f' and {len(differ) - 10} more' if len(differ) > 10
                                          else '')
        return None, (f'{len(differ)} path(s) where the merge writes differ from HEAD and from '
                      f'the merge\'s version: {shown}; commit them, or move them out of the '
                      'worktree first (files equal to the merge\'s version are taken in)')
    return clear_to, None


def snapshot(full):
    """What is on disk at `full`: ('link', target), ('file', bytes, executable) or None."""
    if os.path.islink(full):
        return ('link', os.readlink(full))
    if os.path.isfile(full):
        with open(full, 'rb') as handle:
            return ('file', handle.read(), bool(os.stat(full).st_mode & 0o111))
    return None


def put(full, kind, data, executable=False):
    """Replace what is at `full` with a link to `data`, a file holding `data`, or nothing."""
    if os.path.lexists(full):
        os.remove(full)
    if kind is None:
        return
    os.makedirs(os.path.dirname(full), exist_ok=True)
    if kind == 'link':
        os.symlink(data, full)
        return
    with open(full, 'wb') as handle:
        handle.write(data)
    if executable:
        os.chmod(full, os.stat(full).st_mode | 0o111)


def holds(tree, path, state):
    """True when the disk at `path` is `state` ((mode, blob) or None)."""
    full = os.path.join(tree, *path.split('/'))
    if state is None:
        return not os.path.lexists(full)
    if not os.path.lexists(full):
        return False
    mode, blob = state
    if mode == '120000' or os.path.islink(full):
        data = os.fsencode(os.readlink(full)) if os.path.islink(full) else None
        return mode == '120000' and data is not None and data == subprocess.run(
            ['git', '-C', tree, 'cat-file', 'blob', blob], capture_output=True).stdout
    run = git(tree, 'hash-object', '--', path)
    return not run.returncode and run.stdout.strip() == blob


def clear(tree, clear_to):
    """Put each leftover path in the state the merge starts from (removed, or HEAD's version),
    right before the merge, which writes the merge's version there; returns undo(), which
    writes back the leftovers byte for byte where the disk still holds that state."""
    full = lambda p: os.path.join(tree, *p.split('/'))  # noqa: E731
    saved = {path: snapshot(full(path)) for path in clear_to}

    def undo():
        for path, before in saved.items():
            if before is not None and holds(tree, path, clear_to[path]):
                put(full(path), *before)

    try:
        for path, state in clear_to.items():
            if state is None:
                put(full(path), None, None)
                continue
            mode, blob = state
            data = subprocess.run(['git', '-C', tree, 'cat-file', 'blob', blob],
                                  capture_output=True, check=True).stdout
            if mode == '120000':
                put(full(path), 'link', os.fsdecode(data))
            else:
                put(full(path), 'file', data, mode == '100755')
    except (OSError, subprocess.CalledProcessError) as error:
        undo()
        raise OSError(str(error)) from error
    return undo


def freeze(tree, paths, result):
    """Mark `paths` frozen; (undo, problem). undo() restores the state before. An untracked
    file on one of them is accepted only when it equals its version in `result` (#108)."""
    frozen = frozen_manifest(tree)
    if frozen is None:
        return None, f'the manifest {FROZEN_MANIFEST} cannot be read'
    # an entry git status does not look at hides local changes the merge could lose (#54)
    for entry in zlist(git(tree, 'ls-files', '-v', '-z').stdout):
        tag, path = entry[0], entry[2:]
        if tag.islower() or (tag == 'S' and path not in frozen):
            mark = 'assume-unchanged' if tag.islower() else 'skip-worktree'
            return None, (f'{path} is marked {mark}, so git status cannot show its local changes '
                          'and the merge could lose them; commit them and clear the mark first')
    in_head = set(zlist(git(tree, 'ls-files', '-z', '--', *paths).stdout))
    fresh = [p for p in paths if p not in frozen]
    dirty = zlist(git(tree, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--',
                      *fresh).stdout) if fresh else []
    loose = [p for p in paths if p not in frozen and p not in in_head
             and disk_state(tree, p) is not None]
    leftovers = identical(tree, result, loose) if loose else {}
    for path in paths:
        state = disk_state(tree, path)
        if path in frozen:
            if state != frozen[path]:
                return None, f'{path} changed on disk since it was frozen'
        elif path in in_head and any(r[3:] == path for r in dirty):
            return None, f'{path} differs from HEAD; commit or restore it first'
        elif path not in in_head and state is not None and path not in leftovers:
            return None, (f'{path} is on disk, not tracked and differs from the merge\'s version; '
                          'the merge would hide it')
    old_marks = set(p[2:] for p in zlist(git(tree, 'ls-files', '-v', '-z', '--', *paths).stdout)
                    if p[0] == 'S')
    manifest, sparse = git_path(tree, FROZEN_MANIFEST), git_path(tree, 'info/sparse-checkout')
    saved = {}
    for name in (manifest, sparse):
        try:
            with open(name, 'rb') as handle:
                saved[name] = handle.read()
        except FileNotFoundError:
            saved[name] = None
    new = dict(frozen)
    for path in paths:
        new.setdefault(path, disk_state(tree, path))

    def write(name, data):
        os.makedirs(os.path.dirname(name), exist_ok=True)
        with open(name, 'wb') as handle:
            handle.write(data)

    def undo():
        marked = sorted(in_head - old_marks)
        if marked:
            git(tree, 'update-index', '--no-skip-worktree', '--', *marked)
        for name, data in saved.items():
            if data is None:
                if os.path.exists(name):
                    os.remove(name)
            else:
                write(name, data)

    write(manifest, json.dumps({'frozen': new}, indent=1, sort_keys=True).encode() + b'\n')
    write(sparse, ('/*\n' + ''.join(pattern(p) + '\n' for p in sorted(new))).encode())
    marks = sorted(in_head - old_marks)
    if marks:
        run = git(tree, 'update-index', '--skip-worktree', '--', *marks)
        if run.returncode:
            undo()
            return None, 'git update-index failed: ' + run.stderr.strip()[:200]
    return undo, None


def settle(tree):
    """After a finished merge: drop from the manifest a frozen path that left the index and the
    disk (the merge deleted it where the disk was writable): nothing of it is left to keep."""
    frozen = frozen_manifest(tree) or {}
    index = set(zlist(git(tree, 'ls-files', '-z', '--', *frozen).stdout)) if frozen else set()
    gone = [p for p in frozen if p not in index and disk_state(tree, p) is None]
    if not gone:
        return
    for path in gone:
        del frozen[path]
    with open(git_path(tree, FROZEN_MANIFEST), 'w', encoding='utf-8') as handle:
        handle.write(json.dumps({'frozen': frozen}, indent=1, sort_keys=True) + '\n')


def restore_missing(tree):
    """After `--abort`: a frozen file the stopped merge deleted (where the disk was writable)
    is back in the index, but git leaves a skip-worktree file off the disk. Write it back from
    the index, which is HEAD's version, and record that in the manifest: for a path frozen by an
    earlier merge HEAD's version is newer than what was frozen, and both are in the history.
    Nothing on disk is overwritten. Returns the paths it could not write back."""
    frozen = frozen_manifest(tree) or {}
    missing = [p for p in frozen if frozen[p] is not None and disk_state(tree, p) is None]
    if not missing:
        return []
    failed = []
    for record in zlist(git(tree, 'ls-files', '-s', '-z', '--', *missing).stdout):
        info, _, path = record.partition('\t')
        mode, blob = info.split()[:2]
        data = subprocess.run(['git', '-C', tree, 'cat-file', 'blob', blob],
                              capture_output=True).stdout
        full = os.path.join(tree, *path.split('/'))
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if mode == '120000':  # Windows without the symlink privilege refuses this
                os.symlink(data.decode('utf-8', 'surrogateescape'), full)
            else:
                with open(full, 'wb') as handle:
                    handle.write(data)
                if mode == '100755':
                    os.chmod(full, os.stat(full).st_mode | 0o111)
        except OSError as error:
            failed.append(f'{path} ({error})')
            continue
        frozen[path] = disk_state(tree, path)
    with open(git_path(tree, FROZEN_MANIFEST), 'w', encoding='utf-8') as handle:
        handle.write(json.dumps({'frozen': frozen}, indent=1, sort_keys=True) + '\n')
    return failed


def main(argv):
    args, tree, flags = list(argv), '.', []
    if args[:1] == ['-C'] and len(args) > 1:
        tree, args = args[1], args[2:]
    if '--no-ff' in args:
        args.remove('--no-ff')
        flags.append('--no-ff')
    if len(args) != 1 or (args[0].startswith('-') and args[0] != '--abort') or (
            flags and args[0] == '--abort'):
        print('usage: merge_landing.py [-C <worktree>] [--no-ff] <ref>\n'
              '       merge_landing.py [-C <worktree>] --abort', file=sys.stderr)
        return 2
    ref = args[0]
    top = git(tree, 'rev-parse', '--show-toplevel')
    if top.returncode:
        print(f'not a git worktree: {tree}', file=sys.stderr)
        return 2
    tree = top.stdout.strip()
    if ref == '--abort':
        if not os.path.lexists(git_path(tree, 'MERGE_HEAD')):
            return refuse('no merge in progress')
        run = subprocess.run(['git', '-C', tree, *SPARSE, 'merge', '--abort'],
                             stdin=subprocess.DEVNULL)
        if run.returncode:
            return 1
        failed = restore_missing(tree)
        if failed:
            print('merge aborted, but these frozen files could not be written back from HEAD: '
                  + ', '.join(failed) + '; the cleanup keeps this worktree until they are',
                  file=sys.stderr)
            return 1
        return 0
    if git(tree, 'rev-parse', '-q', '--verify', ref + '^{commit}').returncode:
        print(f'not a commit: {ref}', file=sys.stderr)
        return 2
    for marker in OPERATIONS:
        if os.path.lexists(git_path(tree, marker)):
            return refuse(f'a git operation is in progress ({marker})')
    if not git(tree, 'merge-base', '--is-ancestor', ref, 'HEAD').returncode:
        print(f'nothing to merge: {ref} is in HEAD already')
        return 0
    result, conflicts, changed, problem = merge_result(tree, ref)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    try:
        same, problem = in_the_way(tree, result, changed)
    except GitFailed as error:
        print(error, file=sys.stderr)
        return 2
    if problem:
        return refuse(problem)
    paths = sorted(p for p in set(changed) | set(conflicts) if protected(p))
    if not paths:
        try:
            undo_clear = clear(tree, same)
        except OSError as error:
            return refuse(f'a leftover could not be moved out of the merge\'s way ({error})')
        run = subprocess.run(['git', '-C', tree, 'merge', '--no-edit', *flags, ref],
                             stdin=subprocess.DEVNULL)
        if run.returncode and not os.path.lexists(git_path(tree, 'MERGE_HEAD')):
            undo_clear()
        return 0 if run.returncode == 0 else 1
    if [p for p in conflicts if protected(p)]:
        return refuse('the merge conflicts in ' + ', '.join(p for p in conflicts if protected(p))
                      + "; resolve it in a worktree that is not this session's working "
                      'directory, as the ship-change skill says in step 2')
    common = git(tree, 'rev-parse', '--git-common-dir').stdout.strip()
    if os.path.realpath(os.path.join(tree, common)) == os.path.realpath(
            git(tree, 'rev-parse', '--absolute-git-dir').stdout.strip()):
        return refuse('this is the primary checkout, whose .claude/ would stay behind for good; '
                      'merge in a task worktree (new_worktree.py)')
    if git(tree, 'config', '--bool', 'core.sparseCheckout').stdout.strip() == 'true':
        return refuse('the worktree is a sparse checkout of its own; this tool would overwrite '
                      'its patterns')
    settle(tree)  # a merge finished by hand after a conflict left its deletions recorded
    try:
        undo, problem = freeze(tree, paths, result)
    except GitFailed as error:
        print(error, file=sys.stderr)
        return 2
    if problem:
        return refuse(problem)
    try:
        undo_clear = clear(tree, same)
    except OSError as error:
        undo()
        return refuse(f'a leftover could not be moved out of the merge\'s way ({error}); '
                      'nothing was frozen')
    run = subprocess.run(['git', '-C', tree, *SPARSE, 'merge', '--no-edit', *flags, ref],
                         stdin=subprocess.DEVNULL)
    if run.returncode and not os.path.lexists(git_path(tree, 'MERGE_HEAD')):
        undo()
        undo_clear()
        print('the merge failed before it began; nothing was frozen', file=sys.stderr)
        return 1
    if run.returncode:
        print('the merge stopped (a conflict outside .claude/, or a hook): resolve, stage each '
              'path by name, then commit; or undo it with `merge_landing.py --abort`, never a '
              'plain `git merge --abort`; the frozen paths are recorded', file=sys.stderr)
        return 1
    settle(tree)
    if git(tree, 'rev-parse', 'HEAD^{tree}').stdout.strip() != result:
        print(f'warning: the merge commit\'s tree differs from merge-tree\'s {result[:12]}',
              file=sys.stderr)
    print('frozen (kept on disk as the chat started with them; the commit has the merged '
          'versions): ' + ', '.join(paths))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
