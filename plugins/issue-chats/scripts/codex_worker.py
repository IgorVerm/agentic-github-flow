#!/usr/bin/env python3
"""Run one Codex turn as the worker of a Claude issue chat, in that chat's worktree.

Usage: python3 codex_worker.py <worktree> --model <model> --prompt-file <file>
                               [--resume <thread id>] [--codex-bin <path>]

The route of method.md *Codex as the worker* (issue #103): the Claude issue chat stays the
owner of the issue and the person's interface, and hands the implementation to Codex. One tool,
so that a single narrow allow rule and one `sandbox.excludedCommands` entry cover it, instead of
rules on `codex exec *`, which would also admit `--dangerously-bypass-approvals-and-sandbox`,
`--sandbox danger-full-access` or `--approve-for-me`. Codex needs the network and writes its
sessions under `~/.codex`, so it cannot run inside Claude Code's sandbox (measured 2026-11-20).

It refuses (exit 3) before Codex starts unless:
- <worktree> is the top of a linked git worktree, never a primary checkout;
- HEAD is a branch whose name has a `/` (`agent/<issue>-<topic>`). Codex may write that branch's
  ref folder, so a branch directly under `refs/heads/` would open every branch, `main` included;
- the worktree is clean (no change, no untracked file), so whatever Codex leaves is its own;
- the model and the thread id are plain values, and the prompt file is not empty.

Then it runs, with <worktree> as the working folder and the prompt on stdin:

  codex exec [resume <thread id>] --json -o <last message> -m <model>
             -c approval_policy="never" -c sandbox_mode="workspace-write"
             -c sandbox_workspace_write.network_access=false
             -c sandbox_workspace_write.writable_roots=[<git folders>] -

Codex's own sandbox is the boundary. Codex writes in the worktree and, so that it can commit,
in exactly these git folders: the worktree's own git folder, the shared `objects`, and the ref
and reflog folders of the branch's first name part (for `agent/103-x`: `refs/heads/agent`,
`logs/refs/heads/agent`). It has no network, so it cannot push. It is never asked for an
approval and cannot ask one: a question belongs in its final message, which the Claude chat
reads. Nothing here passes a `--dangerously-*` option or another sandbox mode.

It prints one JSON object on stdout: `thread_id` (the Codex session id, for `--resume` and
`codex resume`), `model`, `branch`, `head_before`, `head_after`, `commits` (Codex's commits,
oldest first: `sha` and `subject`), `uncommitted` (`git status --porcelain` lines after the run),
`branch_moved` (true when HEAD is no longer on the branch), `last_message`, `events` (the JSONL
event log, kept in the worktree's git folder under `codex-worker/`) and `status`.
Exit: 0 the turn completed; 1 Codex failed or the turn did not complete; 2 usage; 3 refused
before Codex started.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
THREAD_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')


def refuse(message):
    print('codex_worker: refused: %s' % message, file=sys.stderr)
    sys.exit(3)


def git(worktree, *args):
    result = subprocess.run(['git', '-C', worktree] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.rstrip('\n')


def toml_string(value):
    # A TOML basic string: JSON's escapes for backslash, quote and control characters are TOML's.
    return json.dumps(value, ensure_ascii=False)


def check_worktree(path):
    """Return (worktree, git dir, common dir, branch) or refuse."""
    if not os.path.isdir(path):
        refuse('%s is not a folder' % path)
    worktree = os.path.realpath(path)
    top = git(worktree, 'rev-parse', '--show-toplevel')
    if top is None or os.path.realpath(top) != worktree:
        refuse('%s is not the top of a git worktree' % path)
    git_dir = git(worktree, 'rev-parse', '--absolute-git-dir')
    common = git(worktree, 'rev-parse', '--git-common-dir')
    if git_dir is None or common is None:
        refuse('git could not name the git folders of %s' % path)
    if not os.path.isabs(common):
        common = os.path.join(worktree, common)
    git_dir, common = os.path.realpath(git_dir), os.path.realpath(common)
    if git_dir == common:
        refuse('%s is a primary checkout; Codex works only in a linked worktree' % path)
    branch = git(worktree, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    if not branch:
        refuse('HEAD of %s is not on a branch' % path)
    if '/' not in branch:
        refuse('branch %s has no folder part (agent/<issue>-<topic>); Codex would get every '
               'branch ref' % branch)
    status = git(worktree, 'status', '--porcelain', '--untracked-files=all')
    if status is None:
        refuse('git status failed in %s' % path)
    if status:
        refuse('%s has uncommitted changes; commit them first, so that what Codex leaves is '
               'its own' % path)
    return worktree, git_dir, common, branch


def writable_roots(git_dir, common, branch):
    first = branch.split('/', 1)[0]
    roots = [git_dir, os.path.join(common, 'objects'),
             os.path.join(common, 'refs', 'heads', first),
             os.path.join(common, 'logs', 'refs', 'heads', first)]
    for root in roots[2:]:
        os.makedirs(root, exist_ok=True)
    return roots


def codex_command(codex, model, resume, roots, last_message):
    command = [codex, 'exec']
    if resume:
        command += ['resume', resume]
    command += ['--json', '-o', last_message, '-m', model,
                '-c', 'approval_policy="never"',
                '-c', 'sandbox_mode="workspace-write"',
                '-c', 'sandbox_workspace_write.network_access=false',
                '-c', 'sandbox_workspace_write.writable_roots=[%s]'
                % ', '.join(toml_string(r) for r in roots),
                '-']
    return command


def read_events(path):
    thread_id, completed, failure = None, False, None
    try:
        handle = open(path, encoding='utf-8', errors='replace')
    except OSError:
        return thread_id, completed, 'no event log'
    with handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get('type')
            if kind == 'thread.started' and isinstance(event.get('thread_id'), str):
                thread_id = event['thread_id']
            elif kind == 'turn.completed':
                completed = True
            elif kind in ('turn.failed', 'error'):
                detail = event.get('error') or event.get('message') or kind
                failure = detail.get('message', kind) if isinstance(detail, dict) else str(detail)
    return thread_id, completed, failure


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run one Codex turn in an issue worktree.')
    parser.add_argument('worktree')
    parser.add_argument('--model', required=True)
    parser.add_argument('--prompt-file', required=True)
    parser.add_argument('--resume', metavar='THREAD_ID')
    parser.add_argument('--codex-bin', default='codex')
    args = parser.parse_args(argv)

    if not MODEL_RE.match(args.model):
        refuse('model %r is not a plain model id' % args.model)
    if args.resume is not None and not THREAD_RE.match(args.resume):
        refuse('thread id %r is not a Codex session id' % args.resume)
    try:
        with open(args.prompt_file, encoding='utf-8') as handle:
            prompt = handle.read()
    except OSError as error:
        refuse('cannot read the prompt file: %s' % error)
    if not prompt.strip():
        refuse('the prompt file is empty')
    codex = shutil.which(args.codex_bin)
    if not codex:
        refuse('no codex command (%s) found' % args.codex_bin)

    worktree, git_dir, common, branch = check_worktree(args.worktree)
    head_before = git(worktree, 'rev-parse', 'HEAD')
    roots = writable_roots(git_dir, common, branch)

    log_dir = os.path.join(git_dir, 'codex-worker')
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    events = os.path.join(log_dir, stamp + '.jsonl')
    last_message = os.path.join(log_dir, stamp + '.last.txt')

    command = codex_command(codex, args.model, args.resume, roots, last_message)
    with open(events, 'w', encoding='utf-8') as out:
        result = subprocess.run(command, cwd=worktree, input=prompt, text=True, stdout=out,
                                stderr=subprocess.PIPE)

    thread_id, completed, failure = read_events(events)
    head_after = git(worktree, 'rev-parse', 'HEAD')
    now_branch = git(worktree, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    commits = []
    if head_before and head_after and head_before != head_after:
        listing = git(worktree, 'log', '--reverse', '--format=%H%x09%s',
                      '%s..%s' % (head_before, head_after)) or ''
        for line in listing.splitlines():
            sha, _, subject = line.partition('\t')
            commits.append({'sha': sha, 'subject': subject})
    uncommitted = (git(worktree, 'status', '--porcelain', '--untracked-files=all') or '')
    try:
        with open(last_message, encoding='utf-8', errors='replace') as handle:
            last = handle.read()
    except OSError:
        last = ''

    ok = result.returncode == 0 and completed and not failure
    report = {
        'status': 'completed' if ok else 'failed',
        'thread_id': thread_id or args.resume,
        'model': args.model,
        'branch': branch,
        'branch_moved': now_branch != branch,
        'head_before': head_before,
        'head_after': head_after,
        'commits': commits,
        'uncommitted': uncommitted.splitlines(),
        'last_message': last,
        'events': events,
    }
    if not ok:
        stderr = '\n'.join(line for line in (result.stderr or '').splitlines()
                           if 'PATH alias' not in line)
        report['failure'] = failure or ('codex exited %d' % result.returncode
                                        if result.returncode else 'the turn did not complete')
        report['stderr_tail'] = stderr[-2000:]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
