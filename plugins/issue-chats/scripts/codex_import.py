#!/usr/bin/env python3
"""Import Codex's commits into a Claude issue chat's worktree, from the bundle of codex_worker.py.

Usage: python3 codex_import.py <worktree> <bundle>

The last step of method.md *Codex as the worker* (issue #107). `codex_worker.py --export` had
the bundle cut inside Codex's sandbox and reports its path, in the worker's job folder: Codex's
commits on top of the commit it started from. This script runs inside Claude Code's sandbox,
like any git command of the chat, and needs no allow rule. It refuses (exit 3) unless <worktree>
is the top of a git worktree, on a branch, with no uncommitted change, and <bundle> opens as a
plain file without following a link. It copies the bundle to `<git folder>/codex/codex.bundle`
first, because Codex can still write the original, and reads only the copy.

It verifies the bundle (`git bundle verify`), stores its objects (`git bundle unbundle`, which
moves no ref), and then checks the range HEAD..<bundle head> before anything reaches the
worktree:
- the head descends from HEAD, so the import is a fast-forward;
- no commit in the range is a merge, so every change shows in a commit's own diff;
- no commit adds, changes or removes a submodule (a gitlink, mode 160000) or `.gitmodules`
  (a submodule's own configuration runs commands in a plain `git status`), anything under a
  `.claude`, `.codex` or `.agents` folder, a `.mcp.json`, a `CLAUDE.md`, `CLAUDE.local.md`,
  `AGENTS.md` or `AGENTS.override.md` (Claude Code and Codex read them as settings, skills,
  hooks, servers or instructions: a nested
  `CLAUDE.md` while the chat reviews the files beside it, an `AGENTS.md` through the
  `CLAUDE.md` that imports it, a `.codex/config.toml` in every later Codex session of a trusted
  repository), or anything on the hooks path when `core.hooksPath` lies in the worktree: the
  path as the configuration writes it, at each link on the way and as it resolves, anything
  under one of them, each folder above one and the folder that holds one (husky's stub in
  `.husky/_` runs the scripts in `.husky`), so a link added or changed there cannot move the
  hooks to files the same commits add; nor a hook manager's files (`.husky`,
  `.pre-commit-config.yaml`, `lefthook.yml`), which the chat's next commit would run. Names
  compare case-insensitively, as on macOS and Windows file systems.
Only when every check passes does it fast-forward the branch (`git merge --ff-only`), with the
hooks path set to nothing, so that no hook runs before the chat has reviewed the commits. The chat
then reviews `base..head` once before the push; this script reviews nothing.

It prints one JSON object: `status` (`imported`, `nothing`: the bundle's head is already in the
branch, `refused`), `branch`, `base`, `head`, `commits` (`sha`, `subject`, oldest first),
`refused` (each refused change: `commit`, `path`, `reason`), `bundle`. Exit: 0 imported or
nothing; 1 refused or failed, the worktree unchanged; 2 usage; 3 refused before the import.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

GIT_SAFE = ['-c', 'core.fsmonitor=false', '-c', 'submodule.recurse=false']
NAMES = {'claude.md': 'Claude Code instructions', 'claude.local.md': 'Claude Code instructions',
         'agents.md': 'agent instructions (AGENTS.md)',
         'agents.override.md': 'agent instructions (AGENTS.override.md)',
         '.mcp.json': 'MCP server configuration', '.gitmodules': 'submodule configuration',
         '.pre-commit-config.yaml': 'git hook configuration (pre-commit)',
         'lefthook.yml': 'git hook configuration (lefthook)',
         '.lefthook.yml': 'git hook configuration (lefthook)',
         'lefthook-local.yml': 'git hook configuration (lefthook)',
         '.lefthook-local.yml': 'git hook configuration (lefthook)'}
FOLDERS = {'.claude': 'Claude Code configuration (.claude)',
           '.codex': 'Codex configuration (.codex)',
           '.agents': 'Codex skills and plugins (.agents)',
           '.husky': 'git hooks (husky)'}


def refuse(message):
    print('codex_import: refused: %s' % message, file=sys.stderr)
    sys.exit(3)


def run(worktree, *args, text=True):
    return subprocess.run(['git', '-C', worktree] + GIT_SAFE + list(args), capture_output=True,
                          text=text)


def git(worktree, *args):
    result = run(worktree, *args)
    return result.stdout.rstrip('\n') if result.returncode == 0 else None


def reason_for(path, old_mode, new_mode, hooks):
    if '160000' in (old_mode, new_mode):
        return 'a submodule (gitlink)'
    lower = path.lower()
    parts = lower.split('/')
    for part in parts:
        if part in FOLDERS:
            return FOLDERS[part]
    if parts[-1] in NAMES:
        return NAMES[parts[-1]]
    for hook in hooks:
        # The hooks path, anything under it, each folder above it, and the folder that holds
        # it: a hook manager's stub there (husky's `.husky/_`) runs the scripts beside it.
        holder = hook.rsplit('/', 1)[0] if '/' in hook else hook
        if hook == '.' or lower == hook or lower.startswith(hook + '/') or \
                hook.startswith(lower + '/') or lower.startswith(holder + '/'):
            return 'the git hooks path (core.hooksPath %s)' % hook
    return None


def link_steps(path):
    """Each path the links on the way to `path` point at, one link at a time."""
    steps, parts, current = [], path.split(os.sep), os.sep
    for index, part in enumerate(parts[1:], 1):
        current = os.path.join(current, part)
        for _ in range(40):
            if not os.path.islink(current):
                break
            current = os.path.normpath(os.path.join(os.path.dirname(current),
                                                    os.readlink(current)))
            steps.append(os.path.normpath(os.path.join(current, *parts[index + 1:])))
    return steps


def hooks_paths(worktree):
    """core.hooksPath inside the worktree, as written and as resolved (lower case), or []."""
    value = git(worktree, 'config', '--get', 'core.hooksPath')
    if not value:
        return []
    written = os.path.normpath(os.path.join(worktree, os.path.expanduser(value)))
    found = []
    for path in [written] + link_steps(written) + [os.path.realpath(written)]:
        if path == worktree or path.startswith(worktree + os.sep):
            relative = os.path.relpath(path, worktree).replace(os.sep, '/').lower()
            if relative not in found:
                found.append(relative)
    return found


def copy_bundle(source, git_dir):
    """Copy the bundle Codex's sandbox wrote into the chat's git folder; return the copy."""
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        fd = os.open(source, flags)
    except OSError:
        refuse('no bundle at %s (a plain file, no link); run codex_worker.py --export first'
               % source)
    folder = os.path.join(git_dir, 'codex')
    target = os.path.join(folder, 'codex.bundle')
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            refuse('%s is not a plain file' % source)
        os.makedirs(folder, exist_ok=True)
        if os.path.lexists(target):
            os.remove(target)
        out = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(out, 'wb') as handle:
            while True:
                block = os.read(fd, 1024 * 1024)
                if not block:
                    break
                handle.write(block)
    except OSError as error:
        refuse('cannot copy the bundle to %s: %s' % (target, error))
    finally:
        os.close(fd)
    return target


def changes(worktree, commit):
    """(old mode, new mode, path) of each change of a commit against its parent."""
    output = run(worktree, 'diff-tree', '-r', '-z', '--no-renames', '--no-commit-id', '--root',
                 commit, text=False).stdout
    fields = output.split(b'\0')
    found, i = [], 0
    while i < len(fields) - 1:
        meta = fields[i].decode('ascii', errors='replace')
        if not meta.startswith(':'):
            i += 1
            continue
        modes = meta[1:].split(' ')
        found.append((modes[0], modes[1], fields[i + 1].decode('utf-8', errors='replace')))
        i += 2
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0].startswith('-') or argv[1].startswith('-'):
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    path = argv[0]
    if not os.path.isdir(path):
        refuse('%s is not a folder' % path)
    worktree = os.path.realpath(path)
    top = git(worktree, 'rev-parse', '--show-toplevel')
    if top is None or os.path.realpath(top) != worktree:
        refuse('%s is not the top of a git worktree' % path)
    git_dir = os.path.realpath(git(worktree, 'rev-parse', '--absolute-git-dir'))
    branch = git(worktree, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    if not branch:
        refuse('HEAD of %s is not on a branch' % path)
    base = git(worktree, 'rev-parse', '--verify', '--quiet', 'HEAD')
    if not base:
        refuse('the branch of %s has no commit' % path)
    if git(worktree, 'status', '--porcelain', '--untracked-files=all') != '':
        refuse('%s has uncommitted changes' % path)
    bundle = copy_bundle(argv[1], git_dir)

    report = {'status': 'refused', 'branch': branch, 'base': base, 'head': None, 'commits': [],
              'refused': [], 'bundle': bundle}
    problems = []
    heads = (git(worktree, 'bundle', 'list-heads', bundle) or '').splitlines()
    if len(heads) != 1 or not heads[0].split(' ', 1)[-1].startswith('refs/heads/'):
        problems.append('the bundle does not hold exactly one branch')
    elif run(worktree, 'bundle', 'verify', '-q', bundle).returncode != 0:
        problems.append('git bundle verify failed: the bundle is damaged or needs commits this '
                        'repository lacks')
    elif run(worktree, 'bundle', 'unbundle', bundle).returncode != 0:
        problems.append('git bundle unbundle failed')
    else:
        tip = heads[0].split(' ', 1)[0]
        report['head'] = tip
        if run(worktree, 'merge-base', '--is-ancestor', tip, base).returncode == 0:
            report['status'] = 'nothing'
        elif run(worktree, 'merge-base', '--is-ancestor', base, tip).returncode != 0:
            problems.append('the bundle\'s head does not descend from HEAD %s; the branch moved '
                            'since the export' % base)
        elif git(worktree, 'rev-list', '--min-parents=2', '%s..%s' % (base, tip)):
            problems.append('the range holds a merge commit')
        else:
            hooks = hooks_paths(worktree)
            listing = git(worktree, 'log', '--reverse', '--format=%H%x09%s',
                          '%s..%s' % (base, tip)) or ''
            for line in listing.splitlines():
                sha, _, subject = line.partition('\t')
                report['commits'].append({'sha': sha, 'subject': subject})
                for old_mode, new_mode, name in changes(worktree, sha):
                    why = reason_for(name, old_mode, new_mode, hooks)
                    if why:
                        report['refused'].append({'commit': sha, 'path': name, 'reason': why})
            if report['refused']:
                problems.append('Codex\'s commits change paths only the Claude chat may change')
            else:
                # No hook runs: a post-merge or post-checkout hook in the worktree could be one
                # these commits wrote, and it would run before the chat has reviewed them.
                merged = run(worktree, '-c', 'core.hooksPath=' + os.devnull, 'merge',
                             '--ff-only', '-q', tip)
                if merged.returncode != 0:
                    problems.append('git merge --ff-only failed: %s'
                                    % merged.stderr.strip()[-500:])
                else:
                    report['status'] = 'imported'
    if problems:
        report['failure'] = '; '.join(problems)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
