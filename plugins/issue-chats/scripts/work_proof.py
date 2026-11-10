#!/usr/bin/env python3
"""Proofs that a worktree's work survives it: the shared part of remove_merged_worktree.py
(cleanup-merged) and of the issue-chats plugin's chat_archivable.py.

  stranded_commits      commits only a worktree's own history holds (its HEAD reflog,
                        ORIG_HEAD, the reflog of a branch that goes with it), which removing it
                        would make unreachable
  merged_pull_request   a pull request of origin merged into a branch whose head is exactly a
                        given commit (a squash or rebase merge leaves no ancestry to read)
  worktrees             `git worktree list --porcelain`, primary first

The core plugin owns this file. An installed plugin stands alone, so the issue-chats plugin
carries an identical copy in its scripts/ folder; tests/chat_archivable.py keeps the two
identical. AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command (tests use it). It
reads only.
"""
import json
import os
import shutil
import subprocess


def git(cwd, *args):
    return subprocess.run(['git', '-C', cwd, *args], text=True, capture_output=True)


def git_path(cwd, name):
    """The absolute path of `git rev-parse --git-path <name>` in cwd. Without
    `--path-format=absolute`, which git before 2.31 echoes instead of applying."""
    found = git(cwd, 'rev-parse', '--git-path', name).stdout.strip()
    return os.path.normpath(found if os.path.isabs(found) else os.path.join(cwd, found))


def ref_format(cwd):
    """'files' or 'reftable'; None when git answers something else. Git before 2.45 echoes the
    unknown option `--show-ref-format` and exits 0; those versions know only `files`."""
    answer = git(cwd, 'rev-parse', '--show-ref-format').stdout.strip()
    if answer == '--show-ref-format':
        return 'files'
    return answer if answer in ('files', 'reftable') else None


def gh_command():
    """The gh command as a list, or None when gh is not installed."""
    raw = os.environ.get('AGENTIC_GITHUB_FLOW_GH')
    if raw:
        try:
            command = json.loads(raw)
        except ValueError:
            return None
        return command if isinstance(command, list) and command else None
    found = shutil.which('gh')
    return [found] if found else None


def merged_pull_request(primary, branch, tip, base=None, timeout=60):
    """(number, problem): a pull request of origin merged into `base` whose head commit is
    exactly `tip`. A pull request merged into another branch (a stacked one) proves nothing
    about `base`."""
    gh = gh_command()
    if not gh:
        return None, 'gh is not installed, so a squash or rebase merge cannot be proven'
    # the repository named outright: gh alone would prefer a remote `upstream`
    origin = git(primary, 'remote', 'get-url', 'origin')
    if origin.returncode:
        return None, 'no remote origin, so no pull request can be read'
    try:
        result = subprocess.run(gh + ['pr', 'list', '-R', origin.stdout.strip(), '--head', branch,
                                      '--state', 'merged',
                                      '--json', 'number,headRefOid,baseRefName',
                                      '--limit', '50'],
                                cwd=primary, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f'gh failed: {error}'
    if result.returncode:
        return None, 'gh pr list failed: ' + (result.stderr.strip().splitlines() or ['?'])[0]
    try:
        pulls = json.loads(result.stdout or '[]')
    except ValueError:
        return None, 'gh pr list gave no JSON'
    for pull in pulls:
        if isinstance(pull, dict) and pull.get('headRefOid') == tip and (
                base is None or pull.get('baseRefName') == base):
            return pull.get('number'), None
    return None, None


def recorded_ids(log, ids, amended):
    """Add every old and new id of the reflog file `log` to `ids`, and to `amended` the commits
    `commit --amend` replaced and no later entry restored as a tip. No file adds nothing."""
    try:
        with open(log, encoding='utf-8', errors='replace') as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        return
    for line in lines:  # oldest first
        head, _, message = line.partition('\t')
        old, new = (head.split(' ') + ['', ''])[:2]
        ids.update((old, new))
        amended.discard(new)  # restored as a tip: no longer superseded
        if message.startswith('commit (amend)'):
            amended.add(old)


def existing_commits(primary, ids):
    """([those of `ids` that are commits here], whether git could tell): an id already gone has
    nothing to lose."""
    known = subprocess.run(['git', '-C', primary, 'cat-file', '--batch-check'], text=True,
                           input=''.join(f'{i}\n' for i in sorted(ids) if i.strip('0')),
                           capture_output=True)
    return ([line.split()[0] for line in known.stdout.splitlines()
             if line.split()[1:2] == ['commit']], not known.returncode)


def stranded_commits(primary, tree, branch_goes, merged_head=None):
    """(reason to keep or None): commits only this worktree's own history still holds.

    `git worktree remove` deletes the worktree's HEAD reflog, ORIG_HEAD and per-worktree refs,
    and `git branch -d` deletes the branch's reflog. A commit that only those record (made on a
    detached HEAD, or dropped by a reset or a branch recreation) would become unreachable. Every
    old and new id in those reflogs must be reachable from a ref that survives, or from the head
    of the merged pull request (GitHub keeps it); the commit a `commit --amend` replaced is
    superseded, not lost.
    """
    path, branch = tree['path'], tree['branch']
    if ref_format(path) != 'files':
        return 'cannot read reflogs (ref format is not `files`)'
    refs = git(path, 'for-each-ref', '--format=%(refname)', 'refs/worktree', 'refs/bisect',
               'refs/rewritten').stdout.split()
    if refs:
        return 'has per-worktree refs: ' + ', '.join(refs[:5])
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'REBASE_HEAD', 'BISECT_LOG',
                   'rebase-merge', 'rebase-apply'):
        if os.path.lexists(git_path(path, marker)):
            return f'a git operation is in progress ({marker})'
    logs = [(path, 'logs/HEAD')] + ([(primary, f'logs/refs/heads/{branch}')]
                                    if branch and branch_goes else [])
    ids, amended = set(), set()
    for cwd, name in logs:
        try:
            recorded_ids(git_path(cwd, name), ids, amended)
        except OSError as error:
            return f'cannot read {name}: {error}'
    ids -= amended
    for name in ('HEAD', 'ORIG_HEAD'):  # current tips are never exempt
        tip = git(path, 'rev-parse', '-q', '--verify', f'{name}^{{commit}}')
        if not tip.returncode:
            ids.add(tip.stdout.strip())
    commits, read = existing_commits(primary, ids)
    if not commits:
        return None
    # for --branches the pattern is relative to refs/heads/ (measured)
    exclude = [f'--exclude={branch}'] if branch and branch_goes else []
    merged = [merged_head] if merged_head else []
    left = git(primary, 'rev-list', *commits, '--not', *merged, *exclude,
               '--branches', '--tags', '--remotes')
    if not read or left.returncode:
        return 'cannot establish which commits stay reachable: ' + left.stderr.strip()[:200]
    lost = set(left.stdout.split())
    stranded = [commit[:12] for commit in commits if commit in lost]
    if stranded:
        return ('commits only this worktree\'s history holds would become unreachable: '
                + ', '.join(stranded[:5]) + (' …' if len(stranded) > 5 else ''))
    return None


def worktrees(primary):
    """[{path, branch, locked, prunable}] from `git worktree list --porcelain`, primary first."""
    out, current = [], None
    for line in git(primary, 'worktree', 'list', '--porcelain').stdout.splitlines():
        if line.startswith('worktree '):
            current = {'path': os.path.realpath(line[9:]), 'branch': None,
                       'locked': None, 'prunable': False}
            out.append(current)
        elif line.startswith('branch refs/heads/'):
            current['branch'] = line[len('branch refs/heads/'):]
        elif line == 'locked' or line.startswith('locked '):
            current['locked'] = line[7:] or 'locked'
        elif line.startswith('prunable'):
            current['prunable'] = True
    return out
