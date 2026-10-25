#!/usr/bin/env python3
"""Create a task worktree in the agreed place: <repo>-worktrees/<task> beside the primary checkout.

Usage: python3 new_worktree.py <task> [--branch <name>] [--base <ref>] [--no-fetch]

Run it from the primary checkout of a repository. It fetches origin (unless --no-fetch), then
creates `../<repo>-worktrees/<task>` on a new branch (default `agent/<task>`) from <base>
(default: origin's default branch as fetched, else local main or master). It refuses a task that
is not a plain name, an existing path or branch, a linked worktree as the starting point, and a
checkout inside a cloud-synced folder (iCloud Drive, OneDrive, Dropbox, Google Drive), where sync clients
corrupt git's files.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

SYNCED = ('/Library/Mobile Documents/', '/Library/CloudStorage/', '/OneDrive', '/Dropbox/',
          '/Google Drive/', '\\OneDrive', '\\Dropbox\\', '\\Google Drive\\')


def git(*args, cwd=None):
    return subprocess.run(['git', *args], capture_output=True, text=True, cwd=cwd)


def default_base(primary):
    """origin's default branch as last fetched, else local main or master."""
    head = git('symbolic-ref', '-q', 'refs/remotes/origin/HEAD', cwd=primary).stdout.strip()
    candidates = [head, 'refs/remotes/origin/main', 'refs/remotes/origin/master',
                  'refs/heads/main', 'refs/heads/master']
    for ref in candidates:
        if ref and git('rev-parse', '-q', '--verify', ref, cwd=primary).returncode == 0:
            return ref
    return None


def main(argv: list[str]) -> int:
    branch, base, fetch, rest = None, None, True, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--branch', '--base'):
            if i + 1 >= len(argv):
                print(__doc__, file=sys.stderr)
                return 2
            if a == '--branch':
                branch = argv[i + 1]
            else:
                base = argv[i + 1]
            i += 2
            continue
        if a == '--no-fetch':
            fetch = False
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            rest.append(a)
        i += 1
    if len(rest) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    task = rest[0]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,80}', task):
        print(f"new_worktree: task '{task}' must be a plain name (letters, digits, . _ -)",
              file=sys.stderr)
        return 1
    branch = branch or f'agent/{task}'

    top = git('rev-parse', '--show-toplevel')
    if top.returncode != 0:
        print('new_worktree: not inside a git checkout', file=sys.stderr)
        return 1
    primary = os.path.normpath(top.stdout.strip())
    common = git('rev-parse', '--git-common-dir').stdout.strip()  # relative to the cwd
    common = os.path.realpath(common if os.path.isabs(common) else os.path.join(os.getcwd(), common))
    if os.path.normcase(os.path.dirname(common)) != os.path.normcase(os.path.realpath(primary)):
        print('new_worktree: run it from the primary checkout, not from a linked worktree',
              file=sys.stderr)
        return 1
    real = os.path.realpath(primary) + os.sep
    if any(s in real for s in SYNCED):
        print(f'new_worktree: {real} is in a cloud-synced folder; keep checkouts out of it',
              file=sys.stderr)
        return 1
    dest = os.path.join(os.path.dirname(primary), os.path.basename(primary) + '-worktrees', task)
    if os.path.lexists(dest):
        print(f'new_worktree: {dest} exists already', file=sys.stderr)
        return 1
    if git('rev-parse', '-q', '--verify', f'refs/heads/{branch}', cwd=primary).returncode == 0:
        print(f'new_worktree: branch {branch} exists already; pick another --branch',
              file=sys.stderr)
        return 1
    if fetch and 'origin' in git('remote', cwd=primary).stdout.split():
        fetched = git('fetch', '--quiet', 'origin', cwd=primary)
        if fetched.returncode != 0:
            print('new_worktree: git fetch origin failed: ' + fetched.stderr.strip(),
                  file=sys.stderr)
            return 1
    base = base or default_base(primary)
    if not base:
        print('new_worktree: no base found (origin/HEAD, origin/main, main or master); '
              'pass --base', file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    added = git('worktree', 'add', '-q', '--no-track', '-b', branch, dest, base, cwd=primary)
    if added.returncode != 0:
        print('new_worktree: ' + added.stderr.strip(), file=sys.stderr)
        return 1
    print(f'new_worktree: {dest} on {branch} from {base}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
