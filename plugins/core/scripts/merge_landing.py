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
     own, and a primary checkout (land from a worktree).

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


def freeze(tree, paths):
    """Mark `paths` frozen; (undo, problem). undo() restores the state before."""
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
    for path in paths:
        state = disk_state(tree, path)
        if path in frozen:
            if state != frozen[path]:
                return None, f'{path} changed on disk since it was frozen'
        elif path in in_head and any(r[3:] == path for r in dirty):
            return None, f'{path} differs from HEAD; commit or restore it first'
        elif path not in in_head and state is not None:
            return None, f'{path} is on disk but not tracked; the merge would hide it'
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
    paths = sorted(p for p in set(changed) | set(conflicts) if protected(p))
    if not paths:
        run = subprocess.run(['git', '-C', tree, 'merge', '--no-edit', *flags, ref],
                             stdin=subprocess.DEVNULL)
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
    undo, problem = freeze(tree, paths)
    if problem:
        return refuse(problem)
    run = subprocess.run(['git', '-C', tree, *SPARSE, 'merge', '--no-edit', *flags, ref],
                         stdin=subprocess.DEVNULL)
    if run.returncode and not os.path.lexists(git_path(tree, 'MERGE_HEAD')):
        undo()
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
