#!/usr/bin/env python3
"""Import Codex's commits into a Claude issue chat's worktree, from the bundle of codex_worker.py.

Usage: python3 codex_import.py <worktree>

The last step of method.md *Codex as the worker* (issue #107). `codex_worker.py --export` cut
`<git folder>/codex/codex.bundle`: Codex's commits on top of the chat's HEAD. This script runs
inside Claude Code's sandbox, like any git command of the chat, and needs no allow rule. It
refuses (exit 3) unless <worktree> is the top of a git worktree, on a branch, clean, with that
bundle beside it.

It verifies the bundle (`git bundle verify`), stores its objects (`git bundle unbundle`, which
moves no ref), and then checks the range HEAD..<bundle head> before anything reaches the
worktree:
- the head descends from HEAD, so the import is a fast-forward;
- no commit in the range is a merge, so every change shows in a commit's own diff;
- no commit adds, changes or removes a submodule (a gitlink, mode 160000) or `.gitmodules`
  (a submodule's own configuration runs commands in a plain `git status`), anything under a
  `.claude` folder, a `.mcp.json`, a `CLAUDE.md` or `CLAUDE.local.md` (Claude Code reads them
  as settings, hooks, servers or instructions, a nested `CLAUDE.md` while the chat reviews the
  files beside it), or a file under `core.hooksPath` when that lies in the worktree. Names
  compare case-insensitively, as on macOS and Windows file systems.
Only when every check passes does it fast-forward the branch (`git merge --ff-only`). The chat
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
         '.mcp.json': 'MCP server configuration', '.gitmodules': 'submodule configuration'}


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
    if '.claude' in parts[:-1] or parts[-1] == '.claude':
        return 'Claude Code configuration (.claude)'
    if parts[-1] in NAMES:
        return NAMES[parts[-1]]
    if hooks and (lower == hooks or lower.startswith(hooks + '/')):
        return 'a git hook (core.hooksPath)'
    return None


def hooks_prefix(worktree):
    value = git(worktree, 'config', '--get', 'core.hooksPath')
    if not value:
        return None
    path = os.path.realpath(os.path.join(worktree, os.path.expanduser(value)))
    if path != worktree and not path.startswith(worktree + os.sep):
        return None
    return os.path.relpath(path, worktree).replace(os.sep, '/').lower()


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
    if len(argv) != 1 or argv[0].startswith('-'):
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
    if git(worktree, 'status', '--porcelain', '--untracked-files=all') != '':
        refuse('%s has uncommitted changes' % path)
    bundle = os.path.join(git_dir, 'codex', 'codex.bundle')
    try:
        if not stat.S_ISREG(os.lstat(bundle).st_mode):
            refuse('%s is not a plain file' % bundle)
    except OSError:
        refuse('no bundle at %s; run codex_worker.py --export first' % bundle)

    report = {'status': 'refused', 'branch': branch, 'base': base, 'head': None, 'commits': [],
              'refused': [], 'bundle': bundle}
    problems = []
    heads = (git(worktree, 'bundle', 'list-heads', bundle) or '').splitlines()
    if len(heads) != 1 or not heads[0].endswith(' refs/heads/codex'):
        problems.append('the bundle does not hold exactly the ref refs/heads/codex')
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
            hooks = hooks_prefix(worktree)
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
                merged = run(worktree, 'merge', '--ff-only', '-q', tip)
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
