#!/usr/bin/env python3
"""Delete a merged task branch from the remote, only while its tip is still the merged commit.

Usage: python3 delete_merged_branch.py <branch> [--remote origin] [--dry-run]

The cleanup-merged skill runs this after the user said yes to the push. It reads the branch's
tip on the remote (`git ls-remote`) and deletes the branch only when that tip is exactly the head
commit of a pull request merged into the default branch (`gh pr list --head <branch> --state
merged`, its `baseRefName` the default branch), or is already in the default branch as just
fetched. The push carries a lease on that tip (`--force-with-lease=refs/heads/<branch>:<tip>`),
so a commit a teammate pushed after the merge makes the push fail instead of vanishing. It
refuses the default branch. AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command
(tests use it). Exit 0: deleted, or already gone; 1: kept, with the reason; 2: usage error.
"""
import json
import os
import shutil
import subprocess
import sys


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True)


def gh_command():
    raw = os.environ.get('AGENTIC_GITHUB_FLOW_GH')
    if raw:
        try:
            command = json.loads(raw)
        except ValueError:
            return None
        return command if isinstance(command, list) and command else None
    found = shutil.which('gh')
    return [found] if found else None


def default_branch(remote):
    head = git('symbolic-ref', '-q', 'refs/remotes/%s/HEAD' % remote).stdout.strip()
    for ref in (head, 'refs/remotes/%s/main' % remote, 'refs/remotes/%s/master' % remote):
        if ref and git('rev-parse', '-q', '--verify', ref).returncode == 0:
            return ref
    return None


def merged_heads(branch, base):
    """(set of head commits of pull requests from branch merged into base, problem)."""
    gh = gh_command()
    if not gh:
        return set(), 'gh is not installed'
    try:
        result = subprocess.run(gh + ['pr', 'list', '--head', branch, '--state', 'merged',
                                      '--json', 'number,headRefOid,baseRefName', '--limit', '50'],
                                capture_output=True, text=True, timeout=60)
        pulls = json.loads(result.stdout or '[]') if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        return set(), 'gh failed: %s' % error
    if pulls is None:
        return set(), 'gh pr list failed: ' + (result.stderr.strip().splitlines() or ['?'])[0]
    return {p.get('headRefOid') for p in pulls if isinstance(p, dict)
            and p.get('baseRefName') == base}, None


def main(argv):
    args, remote, dry = [], 'origin', False
    i = 0
    while i < len(argv):
        if argv[i] == '--remote' and i + 1 < len(argv):
            remote = argv[i + 1]
            i += 2
            continue
        if argv[i] == '--dry-run':
            dry = True
        elif argv[i] in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            args.append(argv[i])
        i += 1
    if len(args) != 1 or args[0].startswith('-'):
        print(__doc__, file=sys.stderr)
        return 2
    branch = args[0][len('refs/heads/'):] if args[0].startswith('refs/heads/') else args[0]
    fetched = git('fetch', '--quiet', remote)
    if fetched.returncode:
        print('KEPT %s: git fetch %s failed: %s' % (branch, remote, fetched.stderr.strip()))
        return 1
    default = default_branch(remote)
    if not default:
        print('KEPT %s: no default branch for %s' % (branch, remote))
        return 1
    base = default.rsplit('/', 1)[-1]
    if branch in (base, 'main', 'master'):
        print('KEPT %s: the default branch is never deleted' % branch)
        return 1
    listed = git('ls-remote', '--heads', remote, 'refs/heads/' + branch)
    if listed.returncode:
        print('KEPT %s: git ls-remote failed: %s' % (branch, listed.stderr.strip()))
        return 1
    tip = listed.stdout.split()[0] if listed.stdout.split() else ''
    if not tip:
        print('GONE %s: no such branch on %s (GitHub may have deleted it at the merge)'
              % (branch, remote))
        return 0
    heads, problem = merged_heads(branch, base)
    if tip in heads:
        why = 'the head of a pull request merged into %s' % base
    elif git('merge-base', '--is-ancestor', tip, default).returncode == 0:
        why = 'in %s' % default
    else:
        print('KEPT %s: its tip %s on %s is neither the head of a merged pull request nor in %s%s'
              % (branch, tip[:12], remote, default, ' (%s)' % problem if problem else ''))
        return 1
    if dry:
        print('WOULD DELETE %s on %s: its tip %s is %s' % (branch, remote, tip[:12], why))
        return 0
    pushed = git('push', '--force-with-lease=refs/heads/%s:%s' % (branch, tip), remote,
                 '--delete', 'refs/heads/' + branch)
    if pushed.returncode:
        print('KEPT %s: the push was refused (did someone push to it?): %s'
              % (branch, pushed.stderr.strip()))
        return 1
    print('DELETED %s on %s: its tip %s was %s' % (branch, remote, tip[:12], why))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
