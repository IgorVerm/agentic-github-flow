#!/usr/bin/env python3
"""Run one Codex turn as the worker of a Claude issue chat, in that chat's worktree.

Usage: python3 codex_worker.py <worktree> --model <model> --prompt-file <file>
                               [--resume <thread id>]

The route of method.md *Codex as the worker* (issue #103): the Claude issue chat stays the
owner of the issue and the person's interface, and hands the implementation to Codex. One tool,
so that a single narrow allow rule and one `sandbox.excludedCommands` entry cover it, instead of
rules on `codex exec *`, which would also admit `--dangerously-bypass-approvals-and-sandbox`,
`--sandbox danger-full-access` or `--approve-for-me`. Codex needs the network and writes its
sessions under `~/.codex`, so it cannot run inside Claude Code's sandbox (measured 2026-11-20).
Because the allow rule lets this script run outside that sandbox without a prompt, it takes no
program to run: `codex` is the one on PATH (changing PATH needs an environment assignment in
front, which the rule does not match).

It refuses (exit 3) before Codex starts unless:
- <worktree> is the top of a linked git worktree, never a primary checkout;
- HEAD is a branch with at least one commit whose name has a `/` (`agent/<issue>-<topic>`).
  Codex may write that branch's ref folder, so a branch directly under `refs/heads/` would open
  every branch, `main` included;
- the worktree is clean (no change, no untracked file), so whatever Codex leaves is its own;
- the model and the thread id are plain values, and the prompt file is a regular file (not a
  link) under the system's temporary folders (`/tmp`, `/private/tmp`, `/var/folders`, the
  temporary folder of this process): its text goes to OpenAI, so it never reads a key, an
  `.env` or a file in the home folder.

Then it runs, with <worktree> as the working folder and the prompt on stdin:

  codex exec [resume <thread id>] --json -o <last message> -m <model>
             -c approval_policy="never" -c sandbox_mode="workspace-write"
             -c sandbox_workspace_write.network_access=false
             -c sandbox_workspace_write.writable_roots=[<git folders>] -

Codex's own sandbox is the boundary. Codex reads the whole disk (`workspace-write` reads
everything) and writes in the worktree, in `/tmp` and the temporary folder (Codex's defaults,
which tests and builds need), and, so that it can commit, in these git folders: the worktree's
own git folder, the shared `objects`, and the ref and reflog folders of the branch's first name
part (for `agent/103-x`: `refs/heads/agent`, `logs/refs/heads/agent`, which hold every `agent/*`
branch). It has no network, so it cannot push. It is never asked for an approval and cannot ask
one: a question belongs in its final message, which the Claude chat reads. Nothing here passes a
`--dangerously-*` option or another sandbox mode.

After the turn, before it runs git again (its git runs outside every sandbox), it compares what
Codex could have used to run code here or in the Claude chat with how it was before the turn:
the worktree's git folder files git reads as configuration or pointers (`commondir`, `gitdir`,
`config.worktree`, `config`, `HEAD`, `info/`), the worktree's `.git` file, and Claude Code's
`.claude/` folder and `.mcp.json`, ignored files included. Any difference: no further git, the
turn counts as failed, and `protected_changed` names the paths. Then it checks that the other
branches under the same ref folder did not move (`other_refs_moved`) and that the new HEAD
descends from the old one (`history_rewritten`).

It prints one JSON object on stdout: `status`, `thread_id` (the Codex session id, for `--resume`
and `codex resume`), `model`, `branch`, `branch_moved`, `head_before`, `head_after`, `commits`
(Codex's commits, oldest first: `sha` and `subject`), `uncommitted` (`git status --porcelain`
lines after the run), `protected_changed`, `other_refs_moved`, `history_rewritten`,
`last_message`, `events` (the JSONL event log). The event log and the last message are kept in
`${XDG_CACHE_HOME:-~/.cache}/agentic-github-flow/codex-worker/`, outside every folder Codex can
write, so Codex cannot forge them.
Exit: 0 the turn completed and every check after it passed; 1 Codex failed, the turn did not
complete, or a check after it failed; 2 usage; 3 refused before Codex started.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
THREAD_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
PROMPT_MAX = 1024 * 1024
GIT_DIR_PROTECTED = ('commondir', 'gitdir', 'config.worktree', 'config', 'HEAD', 'info')
WORKTREE_PROTECTED = ('.git', '.claude', '.mcp.json')


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


def temp_roots():
    roots = {'/tmp', '/private/tmp', '/var/folders', '/private/var/folders',
             tempfile.gettempdir()}
    return [os.path.realpath(r) for r in roots if os.path.isdir(r)]


def check_prompt(path):
    try:
        info = os.lstat(path)
    except OSError as error:
        refuse('cannot read the prompt file: %s' % error)
    if not stat.S_ISREG(info.st_mode):
        refuse('the prompt file is not a regular file (a link or a folder)')
    real = os.path.realpath(path)
    if not any(real == r or real.startswith(r + os.sep) for r in temp_roots()):
        refuse('the prompt file is not under a temporary folder (%s); its text goes to OpenAI'
               % ', '.join(temp_roots()))
    if info.st_size > PROMPT_MAX:
        refuse('the prompt file is larger than %d bytes' % PROMPT_MAX)
    with open(real, encoding='utf-8') as handle:
        prompt = handle.read()
    if not prompt.strip():
        refuse('the prompt file is empty')
    return prompt


def check_worktree(path):
    """Return (worktree, git dir, common dir, branch, head) or refuse."""
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
    head = git(worktree, 'rev-parse', '--verify', '--quiet', 'HEAD')
    if not head:
        refuse('branch %s has no commit yet' % branch)
    status = git(worktree, 'status', '--porcelain', '--untracked-files=all')
    if status is None:
        refuse('git status failed in %s' % path)
    if status:
        refuse('%s has uncommitted changes; commit them first, so that what Codex leaves is '
               'its own' % path)
    return worktree, git_dir, common, branch, head


def fingerprint(path):
    """A map of every file, link and folder under path to what it holds; {} when missing."""
    found = {}

    def one(p):
        try:
            info = os.lstat(p)
        except OSError:
            return
        if stat.S_ISLNK(info.st_mode):
            found[p] = 'link:' + os.readlink(p)
        elif stat.S_ISDIR(info.st_mode):
            found[p] = 'dir'
            try:
                names = sorted(os.listdir(p))
            except OSError:
                found[p] = 'dir:unreadable'
                return
            for name in names:
                one(os.path.join(p, name))
        else:
            digest = hashlib.sha256()
            try:
                with open(p, 'rb') as handle:
                    for block in iter(lambda: handle.read(65536), b''):
                        digest.update(block)
            except OSError:
                found[p] = 'file:unreadable'
                return
            found[p] = 'file:%o:%s' % (info.st_mode & 0o7777, digest.hexdigest())

    one(path)
    return found


def protected_state(worktree, git_dir):
    state = {}
    for name in GIT_DIR_PROTECTED:
        state.update(fingerprint(os.path.join(git_dir, name)))
    for name in WORKTREE_PROTECTED:
        state.update(fingerprint(os.path.join(worktree, name)))
    return state


def changed_paths(before, after):
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def sibling_refs(worktree, branch):
    first = branch.split('/', 1)[0]
    listing = git(worktree, 'for-each-ref', '--format=%(refname) %(objectname)',
                  'refs/heads/%s/' % first) or ''
    own = 'refs/heads/' + branch
    return dict(line.split(' ', 1) for line in listing.splitlines()
                if line and not line.startswith(own + ' '))


def writable_roots(git_dir, common, branch):
    first = branch.split('/', 1)[0]
    roots = [git_dir, os.path.join(common, 'objects'),
             os.path.join(common, 'refs', 'heads', first),
             os.path.join(common, 'logs', 'refs', 'heads', first)]
    for root in roots[2:]:
        os.makedirs(root, exist_ok=True)
    return roots


def log_folder():
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    folder = os.path.join(base, 'agentic-github-flow', 'codex-worker')
    os.makedirs(folder, mode=0o700, exist_ok=True)
    return folder


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
    """(thread id, turn completed, failure). An `error` event alone (a retried connection)
    counts only when no `turn.completed` follows it."""
    thread_id, completed, failed, error = None, False, None, None
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
            detail = event.get('error') or event.get('message') or kind
            text = detail.get('message', kind) if isinstance(detail, dict) else str(detail)
            if kind == 'thread.started' and isinstance(event.get('thread_id'), str):
                thread_id = event['thread_id']
            elif kind == 'turn.completed':
                completed, error = True, None
            elif kind == 'turn.failed':
                failed = text
            elif kind == 'error':
                error = text
    return thread_id, completed, failed or (None if completed else error)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run one Codex turn in an issue worktree.')
    parser.add_argument('worktree')
    parser.add_argument('--model', required=True)
    parser.add_argument('--prompt-file', required=True)
    parser.add_argument('--resume', metavar='THREAD_ID')
    args = parser.parse_args(argv)

    if not MODEL_RE.match(args.model):
        refuse('model %r is not a plain model id' % args.model)
    if args.resume is not None and not THREAD_RE.match(args.resume):
        refuse('thread id %r is not a Codex session id' % args.resume)
    prompt = check_prompt(args.prompt_file)
    codex = shutil.which('codex')
    if not codex:
        refuse('no codex command on PATH')

    worktree, git_dir, common, branch, head_before = check_worktree(args.worktree)
    roots = writable_roots(git_dir, common, branch)
    protected_before = protected_state(worktree, git_dir)
    siblings_before = sibling_refs(worktree, branch)

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = log_folder()
    events = os.path.join(folder, stamp + '.jsonl')
    last_message = os.path.join(folder, stamp + '.last.txt')

    command = codex_command(codex, args.model, args.resume, roots, last_message)
    with open(events, 'w', encoding='utf-8') as out:
        result = subprocess.run(command, cwd=worktree, input=prompt, text=True, stdout=out,
                                stderr=subprocess.PIPE)

    thread_id, completed, failure = read_events(events)
    try:
        with open(last_message, encoding='utf-8', errors='replace') as handle:
            last = handle.read()
    except OSError:
        last = ''
    report = {'status': 'failed', 'thread_id': thread_id or args.resume, 'model': args.model,
              'branch': branch, 'branch_moved': None, 'head_before': head_before,
              'head_after': None, 'commits': [], 'uncommitted': [],
              'protected_changed': changed_paths(protected_before,
                                                 protected_state(worktree, git_dir)),
              'other_refs_moved': [], 'history_rewritten': None, 'last_message': last,
              'events': events}
    problems = []
    if report['protected_changed']:
        # Git reads these as configuration: run no git at all after such a change.
        problems.append('Codex changed protected paths; no git was run after the turn')
    else:
        head_after = git(worktree, 'rev-parse', 'HEAD')
        now_branch = git(worktree, 'symbolic-ref', '--quiet', '--short', 'HEAD')
        report['head_after'] = head_after
        report['branch_moved'] = now_branch != branch
        report['history_rewritten'] = bool(head_after) and head_after != head_before and \
            subprocess.run(['git', '-C', worktree, 'merge-base', '--is-ancestor', head_before,
                            head_after], capture_output=True).returncode != 0
        siblings_after = sibling_refs(worktree, branch)
        report['other_refs_moved'] = sorted(r for r in set(siblings_before) | set(siblings_after)
                                            if siblings_before.get(r) != siblings_after.get(r))
        if head_after and head_after != head_before and not report['history_rewritten']:
            listing = git(worktree, 'log', '--reverse', '--format=%H%x09%s',
                          '%s..%s' % (head_before, head_after)) or ''
            for line in listing.splitlines():
                sha, _, subject = line.partition('\t')
                report['commits'].append({'sha': sha, 'subject': subject})
        report['uncommitted'] = (git(worktree, 'status', '--porcelain',
                                     '--untracked-files=all') or '').splitlines()
        for key, text in (('branch_moved', 'HEAD left the branch'),
                          ('history_rewritten', 'the new HEAD does not descend from the old'),
                          ('other_refs_moved', 'other branches under the same ref folder moved')):
            if report[key]:
                problems.append(text)

    if result.returncode != 0:
        problems.append('codex exited %d' % result.returncode)
    if failure:
        problems.append(failure)
    elif not completed:
        problems.append('the turn did not complete')
    ok = not problems
    report['status'] = 'completed' if ok else 'failed'
    if not ok:
        stderr = '\n'.join(line for line in (result.stderr or '').splitlines()
                           if 'PATH alias' not in line)
        report['failure'] = '; '.join(problems)
        report['stderr_tail'] = stderr[-2000:]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
