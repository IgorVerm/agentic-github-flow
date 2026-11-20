#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/codex_worker.py against a stand-in `codex`:
python3 tests/codex_worker.py.

No real Codex runs. A temporary repository with a linked worktree on `agent/1-x` stands in for
an issue chat's worktree, with a second branch `agent/2-y` beside it. A stand-in `codex`, first
on PATH, logs its arguments, working folder and stdin, prints the JSONL events of
`codex exec --json`, writes the last message and does what the case asks in its working folder.
Each case exposes one way the route could go wrong: Codex started in a primary checkout, on a
detached HEAD, on a branch without a commit or whose ref folder is `refs/heads` itself (which
would open `main` to it), in a dirty worktree, with a model, a thread id or a prompt that is not
a plain value, with a prompt file outside the temporary folders or behind a link (its text goes
to OpenAI); a dangerous option, another sandbox mode, the network or a wider writable folder
reaching `codex exec`; and after the turn: a commit, the thread id or a failed turn not
reported, a changed git pointer or `.claude/` file not caught (git reads them as configuration,
the Claude chat as hooks), another branch moved or the history rewritten unnoticed, the event
log kept where Codex can write. On Windows, where the stand-in cannot be run as a command, only
the refusals run. Offline.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'codex_worker.py')
THREAD = '01a1f914-a724-7ab3-8ad0-ce1133d3c4f7'
WINDOWS = os.name == 'nt'
ENV = dict(os.environ, GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.com',
           GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.com',
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')

STUB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
a = sys.argv[1:]
mode = os.environ.get('STUB_MODE', 'commit')
prompt = sys.stdin.read()
with open(os.environ['STUB_LOG'], 'w') as f:
    json.dump({'argv': a, 'cwd': os.getcwd(), 'stdin': prompt}, f)
last = a[a.index('-o') + 1]
tid = a[a.index('resume') + 1] if 'resume' in a else '01a1f999-0000-7000-8000-000000000001'
print(json.dumps({'type': 'thread.started', 'thread_id': tid}))
print(json.dumps({'type': 'turn.started'}))
def git(*args):
    subprocess.run(['git'] + list(args), check=True, capture_output=True)
def commit():
    with open('work.txt', 'a') as f:
        f.write('codex\n')
    git('add', 'work.txt')
    git('commit', '-q', '-m', 'codex work (#1)')
if mode == 'fail':
    print(json.dumps({'type': 'turn.failed', 'error': {'message': 'model refused'}}))
    sys.exit(1)
if mode == 'retry':
    print(json.dumps({'type': 'error', 'message': 'reconnecting'}))
if mode in ('commit', 'retry'):
    commit()
if mode == 'leave':
    with open('work.txt', 'a') as f:
        f.write('codex\n')
if mode == 'claude':
    os.makedirs('.claude', exist_ok=True)
    with open(os.path.join('.claude', 'settings.local.json'), 'w') as f:
        f.write('{"hooks": {}}')
if mode == 'gitdir':
    gd = subprocess.run(['git', 'rev-parse', '--absolute-git-dir'], capture_output=True,
                        text=True).stdout.strip()
    with open(os.path.join(gd, 'config.worktree'), 'w') as f:
        f.write('[core]\n\tfsmonitor = touch pwned\n')
if mode == 'sibling':
    git('update-ref', 'refs/heads/agent/2-y', 'HEAD')
if mode == 'rewrite':
    git('reset', '-q', '--hard', 'HEAD~1')
    commit()
with open(last, 'w') as f:
    f.write('done; question: none')
print(json.dumps({'type': 'turn.completed', 'usage': {}}))
'''

failures = []


def check(name, condition, detail=''):
    if not condition:
        failures.append('%s %s' % (name, detail))
        print('FAIL', name, detail)


def git(cwd, *args):
    return subprocess.run(['git', '-C', cwd] + list(args), capture_output=True, text=True,
                          env=ENV, check=True).stdout.strip()


def main():
    base = os.path.realpath(tempfile.mkdtemp(prefix='codex-worker-test-'))
    try:
        bindir = os.path.join(base, 'bin')
        os.makedirs(bindir)
        stub = os.path.join(bindir, 'codex')
        with open(stub, 'w') as f:
            f.write(STUB)
        os.chmod(stub, 0o755)
        log = os.path.join(base, 'stub.json')
        cache = os.path.join(base, 'cache')
        env = dict(ENV, PATH=bindir + os.pathsep + ENV.get('PATH', ''), STUB_LOG=log,
                   XDG_CACHE_HOME=cache)

        def run(args, **extra):
            return subprocess.run([sys.executable, TOOL] + args, capture_output=True,
                                  text=True, env=dict(env, **extra))

        primary = os.path.join(base, 'repo')
        os.makedirs(primary)
        git(primary, 'init', '-q', '-b', 'main')
        with open(os.path.join(primary, 'work.txt'), 'w') as f:
            f.write('start\n')
        git(primary, 'add', 'work.txt')
        git(primary, 'commit', '-q', '-m', 'start')
        git(primary, 'commit', '-q', '--allow-empty', '-m', 'second')
        git(primary, 'branch', 'agent/2-y', 'HEAD~1')
        wt = os.path.join(base, 'wt')
        git(primary, 'worktree', 'add', '-q', '-b', 'agent/1-x', wt)
        flat = os.path.join(base, 'flat')
        git(primary, 'worktree', 'add', '-q', '-b', 'flat', flat)
        detached = os.path.join(base, 'detached')
        git(primary, 'worktree', 'add', '-q', '--detach', detached)
        prompt = os.path.join(base, 'prompt.txt')
        with open(prompt, 'w') as f:
            f.write('Do the task of issue #1.\n')
        empty = os.path.join(base, 'empty.txt')
        open(empty, 'w').close()
        link = os.path.join(base, 'link.txt')
        if not WINDOWS:
            os.symlink(prompt, link)

        def refused(name, args, **extra):
            if os.path.exists(log):
                os.remove(log)
            result = run(args, **extra)
            check(name, result.returncode == 3, 'exit %d: %s' % (result.returncode, result.stderr))
            check(name + ' (codex not started)', not os.path.exists(log))

        good = ['--model', 'gpt-6.2-astra', '--prompt-file', prompt]
        refused('primary checkout', [primary] + good)
        refused('detached HEAD', [detached] + good)
        refused('branch without folder part', [flat] + good)
        refused('not a worktree top', [os.path.join(wt, 'nope')] + good)
        refused('model with an option', [wt, '--model=--dangerously-bypass-approvals-and-sandbox',
                                          '--prompt-file', prompt])
        refused('model with a space', [wt, '--model', 'gpt x', '--prompt-file', prompt])
        refused('thread id not an id', [wt] + good + ['--resume', 'last'])
        refused('empty prompt', [wt, '--model', 'm', '--prompt-file', empty])
        refused('prompt outside the temporary folders',
                [wt, '--model', 'm', '--prompt-file', os.path.join(ROOT, 'README.md')])
        if not WINDOWS:
            refused('prompt behind a link', [wt, '--model', 'm', '--prompt-file', link])
        refused('no codex on PATH', [wt] + good, PATH=os.path.join(base, 'nothing'))
        check('no --codex-bin option', run([wt] + good + ['--codex-bin', stub]).returncode == 2)
        with open(os.path.join(wt, 'stray.txt'), 'w') as f:
            f.write('x')
        refused('dirty worktree', [wt] + good)
        os.remove(os.path.join(wt, 'stray.txt'))

        if WINDOWS:
            print('codex_worker: Windows: only the refusals ran (the stand-in is no command here)')
            return

        before = git(wt, 'rev-parse', 'HEAD')
        result = run([wt] + good)
        check('commit run exits 0', result.returncode == 0, result.stderr + result.stdout)
        report = json.loads(result.stdout or '{}')
        call = json.load(open(log))
        argv = call['argv']
        check('codex exec', argv[:1] == ['exec'] and 'resume' not in argv, str(argv))
        check('prompt on stdin', call['stdin'] == 'Do the task of issue #1.\n' and argv[-1] == '-')
        check('runs in the worktree', os.path.realpath(call['cwd']) == os.path.realpath(wt))
        check('model', argv[argv.index('-m') + 1] == 'gpt-6.2-astra')
        configs = [argv[i + 1] for i, v in enumerate(argv) if v == '-c']
        check('approval never', 'approval_policy="never"' in configs, str(configs))
        check('workspace-write', 'sandbox_mode="workspace-write"' in configs, str(configs))
        check('no network', 'sandbox_workspace_write.network_access=false' in configs)
        roots_entry = [c for c in configs if c.startswith('sandbox_workspace_write.writable_roots=')]
        roots = json.loads(roots_entry[0].split('=', 1)[1]) if roots_entry else []
        common = os.path.realpath(os.path.join(primary, '.git'))
        gitdir = os.path.realpath(git(wt, 'rev-parse', '--absolute-git-dir'))
        expected = [gitdir, os.path.join(common, 'objects'),
                    os.path.join(common, 'refs', 'heads', 'agent'),
                    os.path.join(common, 'logs', 'refs', 'heads', 'agent')]
        check('writable roots are the four git folders', roots == expected, str(roots))
        joined = ' '.join(argv)
        for bad in ('dangerously', 'danger-full-access', 'approve-for-me', '--add-dir',
                    '--sandbox', '-s ', 'network_access=true', '--full-auto'):
            check('no %s' % bad, bad not in joined, joined)
        check('report thread id', report.get('thread_id') == '01a1f999-0000-7000-8000-000000000001')
        check('report status', report.get('status') == 'completed', str(report))
        check('report commit', [c['subject'] for c in report.get('commits', [])] ==
              ['codex work (#1)'], str(report.get('commits')))
        check('report heads', report.get('head_before') == before and
              report.get('head_after') == git(wt, 'rev-parse', 'HEAD'))
        check('report last message', report.get('last_message') == 'done; question: none')
        check('report clean', report.get('uncommitted') == [] and not report.get('branch_moved')
              and report.get('protected_changed') == [] and report.get('other_refs_moved') == []
              and report.get('history_rewritten') is False, str(report))
        events = report.get('events', '')
        check('event log outside what Codex writes',
              os.path.dirname(events) == os.path.join(cache, 'agentic-github-flow', 'codex-worker')
              and not any(events.startswith(r) for r in expected + [wt]), events)

        result = run([wt] + good + ['--resume', THREAD])
        argv = json.load(open(log))['argv']
        check('resume exits 0', result.returncode == 0, result.stderr)
        check('resume passes the thread', argv[:3] == ['exec', 'resume', THREAD], str(argv))
        check('resume keeps the sandbox', 'sandbox_mode="workspace-write"' in argv)
        check('resume reports the thread', json.loads(result.stdout).get('thread_id') == THREAD)

        result = run([wt] + good, STUB_MODE='retry')
        check('an error event before turn.completed is no failure', result.returncode == 0,
              result.stdout)

        def failed(name, mode, key, value_check):
            result = run([wt] + good, STUB_MODE=mode)
            report = json.loads(result.stdout or '{}')
            check(name + ' exits 1', result.returncode == 1, result.stdout)
            check(name + ' reported', report.get('status') == 'failed' and
                  value_check(report.get(key)), str(report))
            return report

        report = failed('failed turn', 'fail', 'failure', lambda v: v and 'model refused' in v)
        report = failed('.claude written', 'claude', 'protected_changed',
                        lambda v: v and any(p.endswith('settings.local.json') for p in v))
        check('.claude written: no git after', report.get('head_after') is None)
        shutil.rmtree(os.path.join(wt, '.claude'))
        report = failed('git pointer written', 'gitdir', 'protected_changed',
                        lambda v: v == [os.path.join(gitdir, 'config.worktree')])
        check('git pointer written: no git after', report.get('head_after') is None and
              not os.path.exists(os.path.join(wt, 'pwned')))
        os.remove(os.path.join(gitdir, 'config.worktree'))
        failed('other branch moved', 'sibling', 'other_refs_moved',
               lambda v: v == ['refs/heads/agent/2-y'])
        git(primary, 'update-ref', 'refs/heads/agent/2-y', 'main~1')
        report = failed('history rewritten', 'rewrite', 'history_rewritten', lambda v: v is True)
        check('history rewritten: no commits listed', report.get('commits') == [])
        result = run([wt] + good, STUB_MODE='leave')
        report = json.loads(result.stdout or '{}')
        check('left changes reported', report.get('uncommitted') == [' M work.txt'] and
              report.get('commits') == [], str(report))
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == '__main__':
    main()
    if failures:
        print('codex_worker: %d failure(s)' % len(failures))
        sys.exit(1)
    print('codex_worker: ok')
