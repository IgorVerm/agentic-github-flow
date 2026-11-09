#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/start_issue_chat.py against a stand-in `claude` and `gh`:
python3 tests/start_issue_chat.py.

No real session starts: a stand-in `claude` first on PATH answers `auth status`, `agents --json`,
`--bg`, `stop` and `--desktop --resume` from a state file and logs each call, writes the new
session's transcript (its reply to the ready prompt: a real one on a chosen model, the
`<synthetic>` placeholder, or none until a later poll) under a stand-in CLAUDE_CONFIG_DIR, and a
stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) answers `issue view` for the title's issue. Each case exposes one way
the hand-over could go wrong: a next chat started in a primary checkout, a dirty or busy
worktree, a second chat with the same title, a second chat on an issue another chat has claimed
(assigned, also when --handover claims it is the caller's own) or one that is closed or
unreadable, a title without its GitHub issue or the repository prefix, a refused value reaching
`claude --bg`, a session left running after a failure, or a chat opened in the app before its
background run stopped, or a chat opened although it never answered the ready prompt or answered
on another model than --model. On Windows, where the tool knows no form of `script`, it checks only
that the tool refuses before starting anything. Offline.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'start_issue_chat.py')
SID = '0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0'
WINDOWS = os.name == 'nt'

STUB = r'''import json, os, re, sys
st = os.environ['STUB_STATE']
s = json.load(open(st))
a = sys.argv[1:]
s['log'].append(a)
def save(): json.dump(s, open(st, 'w'))
def write_reply(cwd, kind, model):
    # The session's transcript as Claude Code keeps it: the ready prompt, then its reply.
    folder = re.sub(r'[^A-Za-z0-9]', '-', cwd) if s.get('reply_dir') != 'other' else 'renamed'
    d = os.path.join(os.environ['CLAUDE_CONFIG_DIR'], 'projects', folder)
    os.makedirs(d, exist_ok=True)
    recs = [{'type': 'user', 'message': {'role': 'user', 'content': 'Reply ...'}}]
    if kind == 'synthetic':
        recs.append({'type': 'assistant', 'isApiErrorMessage': False,
                     'message': {'model': '<synthetic>', 'content': [
                         {'type': 'text', 'text': 'No response requested.'}]}})
    elif kind == 'real':
        recs.append({'type': 'assistant', 'message': {'model': model, 'content': [
            {'type': 'text', 'text': 'ready'}]}})
    with open(os.path.join(d, s['sid'] + '.jsonl'), 'w') as f:
        f.write('not json\n' + ''.join(json.dumps(r) + '\n' for r in recs))
def reply_model(m):
    m = re.sub(r'\[.*\]$', '', m)
    return s.get('reply_model') or {'opus': 'claude-opus-5-5'}.get(m, m)
if a[:2] == ['auth', 'status']:
    print(json.dumps({'loggedIn': s['logged_in']}))
elif a[:2] == ['agents', '--json']:
    if s.get('agents_fail_after_bg') and any(c[:1] == ['--bg'] for c in s['log']):
        print('error: agents unavailable', file=sys.stderr); save(); sys.exit(1)
    rows = s['others'] + [r for r in s['bg'] if not r.get('stopped')]
    if '--cwd' in a:
        cwd = os.path.realpath(a[a.index('--cwd') + 1])
        rows = [r for r in s['bg'] if os.path.realpath(r['cwd']) == cwd and not r.get('stopped')]
        s['polls'] = s.get('polls', 0) + 1
        late = s.get('reply_after_polls')
        if rows and late and s['polls'] == late:
            write_reply(rows[0]['cwd'], 'real', s['bg_model'])
    print(json.dumps(rows, indent=2))
elif a[:1] == ['--bg']:
    name = a[a.index('--name') + 1]
    s['bg'].append({'cwd': os.getcwd(), 'kind': 'background', 'sessionId': s['sid'],
                    'name': name, 'status': s['bg_status']})
    if s.get('bg_fail'):
        print('error: something went wrong', file=sys.stderr); save(); sys.exit(1)
    s['bg_model'] = reply_model(a[a.index('--model') + 1])
    kind = s.get('reply', 'real')
    write_reply(os.getcwd(), 'none' if s.get('reply_after_polls') else kind, s['bg_model'])
    print('backgrounded · 0f1e2d3c · ' + name)
elif a[:1] == ['stop']:
    for r in s['bg']:
        r['stopped'] = True
elif a[:2] == ['--desktop', '--resume']:
    if s['desktop_ok']:
        print('Opening session %s in Claude Desktop' % a[2])
    else:
        print('error: no desktop'); save(); sys.exit(1)
save()
'''

GH = r'''import json, os, sys
s = json.load(open(os.environ['STUB_STATE']))
a = sys.argv[1:]
s['log'].append(['gh'] + a)
json.dump(s, open(os.environ['STUB_STATE'], 'w'))
if a[:2] != ['issue', 'view'] or s['gh'] is None:
    print('could not resolve to an Issue', file=sys.stderr); sys.exit(1)
print(json.dumps(s['gh']))
'''

tmp = os.path.realpath(tempfile.mkdtemp(prefix='start-issue-chat-'))
bindir = os.path.join(tmp, 'bin')
os.makedirs(bindir)
for name, body in (('fake_claude.py', STUB), ('fake_gh.py', GH)):
    with open(os.path.join(bindir, name), 'w', encoding='utf-8') as f:
        f.write(body)
if not WINDOWS:
    with open(os.path.join(bindir, 'claude'), 'w') as f:
        f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable,
                                                       os.path.join(bindir, 'fake_claude.py')))
    os.chmod(os.path.join(bindir, 'claude'), 0o755)
GH_CMD = json.dumps([sys.executable, os.path.join(bindir, 'fake_gh.py')])
OPEN = {'state': 'OPEN', 'assignees': []}
GENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
            GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t.invalid',
            GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t.invalid')

primary = os.path.join(tmp, 'repo')


def sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, env=GENV)


sh('git', 'init', '-q', '-b', 'main', primary)
sh('git', 'commit', '-q', '--allow-empty', '-m', 'init', cwd=primary)
wt = os.path.join(tmp, 'repo-worktrees', 'next')
sh('git', 'worktree', 'add', '-q', '-b', 'agent/next', wt, cwd=primary)

failures = []
CASES = SKIPPED = 0


def pty_works():
    """Whether `script` can open a terminal here (a sandbox may forbid it); CI can."""
    if WINDOWS:
        return False
    form = ['script', '-q', '/dev/null', 'true'] if sys.platform == 'darwin' else \
        ['script', '-q', '-c', 'true', '/dev/null']
    try:
        return subprocess.run(form, capture_output=True, stdin=subprocess.DEVNULL,
                              timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


PTY = pty_works()


def case(name, expect_code, *, args=None, logged_in=True, others=(), bg_status='idle',
         desktop_ok=True, env_extra=None, check=None, gh=OPEN, cwd=None, needs_pty=None,
         stub=None):
    global CASES, SKIPPED
    if (expect_code != 1 if needs_pty is None else needs_pty) and not PTY:
        SKIPPED += 1
        return []
    CASES += 1
    state = os.path.join(tmp, 'state.json')
    with open(state, 'w') as f:
        json.dump({'log': [], 'logged_in': logged_in, 'others': list(others), 'bg': [],
                   'sid': SID, 'bg_status': bg_status, 'desktop_ok': desktop_ok, 'gh': gh,
                   **(stub or {})}, f)
    config = os.path.join(tmp, 'config')
    shutil.rmtree(config, ignore_errors=True)
    env = dict(GENV, PATH=bindir + os.pathsep + os.environ['PATH'], STUB_STATE=state,
               AGENTIC_GITHUB_FLOW_GH=GH_CMD, CLAUDE_CODE_SESSION_ID='me', CLAUDE_EFFORT='high',
               CLAUDE_CONFIG_DIR=config, AGENTIC_GITHUB_FLOW_START_WAIT_S='8')
    env.pop('CLAUDE_CODE_HOST_SESSION_ID', None)
    env.update(env_extra or {})
    argv = args if args is not None else [wt, '#12 · next', '--model', 'claude-opus-5-5']
    p = subprocess.run([sys.executable, TOOL, *argv], env=env, capture_output=True, text=True,
                       encoding='utf-8', timeout=200, cwd=cwd)
    with open(state) as f:
        s = json.load(f)
    log = s['log']
    started = any(c[:1] == ['--bg'] for c in log)
    msg = []
    if p.returncode != expect_code:
        msg.append('exit %d, want %d: %s %s' % (p.returncode, expect_code, p.stdout, p.stderr))
    if expect_code == 0 and not started:
        msg.append('no claude --bg')
    if expect_code == 1 and started and not all(r.get('stopped') for r in s['bg']):
        msg.append('a background session was left running')
    if check:
        m = check(log, p.stdout)
        if m:
            msg.append(m)
    if msg:
        failures.append('%s: %s' % (name, '; '.join(msg)))
    return log


def order_ok(log, out):
    kinds = [c[0] for c in log]
    if not {'gh', '--bg', 'stop', '--desktop'} <= set(kinds):
        return 'calls %s, last line %r' % (kinds, out)
    if kinds.index('gh') > kinds.index('--bg'):
        return 'the claim was checked after the start: %s' % kinds
    bg, stop, desk = kinds.index('--bg'), kinds.index('stop'), kinds.index('--desktop')
    if not bg < stop < desk:
        return 'order %s' % kinds
    bgcall = next(c for c in log if c[:1] == ['--bg'])
    if bgcall[bgcall.index('--effort') + 1] != 'high':
        return 'effort not taken from CLAUDE_EFFORT: %s' % bgcall
    if out.strip() != 'ok local_' + SID:
        return 'last line %r' % out
    return None


def nothing_started(log, out):
    if any(c[:1] == ['--bg'] for c in log):
        return 'claude --bg ran'
    if not out.strip().startswith('fail:'):
        return 'last line %r' % out
    return None


if WINDOWS:
    case('Windows refuses before anything', 1, check=nothing_started)
else:
    case('route', 0, check=order_ok)
    case('own title is no other chat', 0,
         others=[{'cwd': primary, 'sessionId': 'me', 'name': '#12 · next', 'status': 'busy'}])
    case('primary checkout refused', 1, args=[primary, '#12 · next', '--model', 'opus'],
         check=nothing_started)
    case('not logged in', 1, logged_in=False, check=nothing_started)
    case('session already in the worktree', 1,
         others=[{'cwd': wt, 'sessionId': 'old', 'name': '#11 · old', 'status': 'idle'}],
         check=nothing_started)
    case('title already running elsewhere', 1,
         others=[{'cwd': primary, 'sessionId': 'other', 'name': '#12 · next', 'status': 'busy'}],
         check=nothing_started)
    case('flag as model refused', 1,
         args=[wt, '#12 · next', '--model', '--dangerously-skip-permissions'],
         check=nothing_started)
    case('model with a flag inside refused', 1,
         args=[wt, '#12 · next', '--model', 'opus --settings x'], check=nothing_started)
    case('bad effort refused', 1,
         args=[wt, '#12 · next', '--model', 'opus', '--effort', 'huge'], check=nothing_started)
    case('title as a flag refused', 1,
         args=[wt, '--dangerously-skip-permissions', '--model', 'opus'], check=nothing_started)
    def stopped_first(log, out):
        kinds = [c[0] for c in log]
        if 'local_' + SID in out and 'stop' in kinds and '--desktop' in kinds and \
                kinds.index('stop') < kinds.index('--desktop'):
            return None
        return 'out %r log %s' % (out, log)

    case('desktop refused: unsure, stopped first', 2, desktop_ok=False, check=stopped_first)
    case('a title of another form refused', 1, args=[wt, 'Lane 2: next', '--model', 'opus'],
         check=nothing_started)
    case('title without an issue refused', 1,
         args=[wt, 'Web · next', '--model', 'opus', '--prefix', 'Web · '], check=nothing_started)
    case('repository prefix', 0,
         args=[wt, 'Web · #12 · next', '--model', 'opus', '--prefix', 'Web · '])
    case('repository prefix missing from the title refused', 1,
         args=[wt, '#12 · next', '--model', 'opus', '--prefix', 'Web · '], check=nothing_started)
    case('a prefix with an issue sign refused', 1,
         args=[wt, '#1 · #12 · next', '--model', 'opus', '--prefix', '#1 · '],
         check=nothing_started)
    case('requirements title', 0, args=[wt, 'Requirements · #30 · trade', '--model', 'opus'])
    case('requirements title before its parent exists: no issue to read', 0,
         args=[wt, 'Requirements · new · trade', '--model', 'opus'], gh=None,
         check=lambda log, out: 'gh ran' if any(c[0] == 'gh' for c in log) else None)
    case('issue already assigned refused', 1,
         gh={'state': 'OPEN', 'assignees': [{'login': 'someone'}]}, check=nothing_started)
    ROBOT = '\N{ROBOT FACE}'

    def claimed(*bodies):
        return {'state': 'OPEN', 'assignees': [{'login': 'someone'}],
                'comments': [{'body': ROBOT + ' Claude Code (issue chat): ' + b} for b in bodies]}

    MINE = 'claimed for chat "#12 · next" (local_aaaabbbb-1111), branch agent/12-x, worktree /w/12-x'
    THEIRS = 'claimed for chat "#12 · other" (local_ccccdddd-2222), branch agent/12-y, worktree /w/12-y'
    HANDOVER = [wt, '#12 · next', '--model', 'opus', '--handover']
    case('own claim handed over before it is ready', 0, args=HANDOVER, gh=claimed(MINE),
         env_extra={'CLAUDE_CODE_HOST_SESSION_ID': 'local_aaaabbbb-1111'})
    case('own claim recognized by the worktree it names', 0, args=HANDOVER,
         gh=claimed('claimed for chat "#12 · next", branch agent/12, worktree %s' % primary),
         cwd=primary)
    case('--handover on another chat\'s claim refused', 1, args=HANDOVER, gh=claimed(THEIRS),
         env_extra={'CLAUDE_CODE_HOST_SESSION_ID': 'local_aaaabbbb-1111'}, check=nothing_started)
    case('--handover after another chat claimed it since refused', 1, args=HANDOVER,
         gh=claimed(MINE, THEIRS), env_extra={'CLAUDE_CODE_HOST_SESSION_ID': 'local_aaaabbbb-1111'},
         check=nothing_started)
    case('--handover on an assigned issue without a claim comment refused', 1, args=HANDOVER,
         gh=claimed(), env_extra={'CLAUDE_CODE_HOST_SESSION_ID': 'local_aaaabbbb-1111'},
         check=nothing_started)
    case('own claim, then a signed remark about the claim: still own', 0, args=HANDOVER,
         gh=claimed(MINE, 'a note on the claim of local_ccccdddd-2222 above'),
         env_extra={'CLAUDE_CODE_HOST_SESSION_ID': 'local_aaaabbbb-1111'})
    case('another chat\'s claim, then a signed remark naming this chat: refused', 1,
         args=HANDOVER, gh=claimed(THEIRS, 'is the claim of local_aaaabbbb-1111 gone?'),
         env_extra={'CLAUDE_CODE_HOST_SESSION_ID': 'local_aaaabbbb-1111'}, check=nothing_started)
    case('a claim naming only the worktree folder name refused', 1, args=HANDOVER,
         gh=claimed('claimed for chat "#12 · next", branch agent/12, worktree %s'
                    % os.path.basename(primary)), cwd=primary, check=nothing_started)
    case('a claim naming a longer path refused', 1, args=HANDOVER,
         gh=claimed('claimed for chat "#12 · next", branch agent/12, worktree %s-old/x'
                    % primary), cwd=primary, check=nothing_started)

    def unsure_with_id(log, out):
        if not out.strip().startswith('unsure:') or 'nothing started' in out:
            return 'last line %r' % out
        return None

    case('claude --bg fails and the sessions cannot be listed: unsure, not nothing started', 2,
         stub={'bg_fail': True, 'agents_fail_after_bg': True}, needs_pty=False,
         check=unsure_with_id)
    case('the sessions cannot be listed after the start: unsure with the short id', 2,
         stub={'agents_fail_after_bg': True}, needs_pty=False,
         check=lambda log, out: unsure_with_id(log, out) or (
             None if '0f1e2d3c' in out else 'no short id in %r' % out))
    def not_opened(log, out):
        kinds = [c[0] for c in log]
        if '--desktop' in kinds:
            return 'opened in the app: %s' % kinds
        if 'stop' not in kinds or not out.strip().startswith('fail:'):
            return 'calls %s, last line %r' % (kinds, out)
        return None

    case('a synthetic ready reply at idle never gives ok', 1, stub={'reply': 'synthetic'},
         check=lambda log, out: not_opened(log, out) or (
             None if 'ready prompt' in out else 'reason missing in %r' % out))
    case('no reply at all at idle never gives ok', 1, stub={'reply': 'none'}, check=not_opened)
    case('a reply on another model: stopped, not opened', 1,
         stub={'reply_model': 'claude-fable-5-1'},
         check=lambda log, out: not_opened(log, out) or (
             None if 'claude-fable-5-1' in out else 'model missing in %r' % out))
    case('a reply on another model of the alias\'s family name refused', 1,
         args=[wt, '#12 · next', '--model', 'opus'], stub={'reply_model': 'claude-sonnet-5-5'},
         check=not_opened)
    case('an alias answered by a model of its family', 0,
         args=[wt, '#12 · next', '--model', 'opus'], stub={'reply_model': 'claude-opus-5-5'})
    case('an id answered by its dated form', 0,
         args=[wt, '#12 · next', '--model', 'claude-sonnet-4-5'],
         stub={'reply_model': 'claude-sonnet-4-5-20250929'})
    case('another alias refused, never a false ok', 1,
         args=[wt, '#12 · next', '--model', 'default'], stub={'reply_model': 'claude-opus-5-5'},
         check=not_opened)
    case('idle before the reply: waits for it, then ok', 0, stub={'reply_after_polls': 3},
         env_extra={'AGENTIC_GITHUB_FLOW_START_WAIT_S': '20'},
         check=lambda log, out: order_ok(log, out) or (
             None if sum(c[:2] == ['agents', '--json'] and '--cwd' in c for c in log) >= 3
             else 'stopped before the reply: %s' % log))
    case('a context suffix on the model id', 0,
         args=[wt, '#12 · next', '--model', 'claude-opus-5-5[1m]'])
    case('the transcript in a project folder of another name', 0, stub={'reply_dir': 'other'})
    case('closed issue refused', 1, gh={'state': 'CLOSED', 'assignees': []},
         check=nothing_started)
    case('unreadable issue refused', 1, gh=None, check=nothing_started)
    case('no gh refused', 1, env_extra={'AGENTIC_GITHUB_FLOW_GH': 'not json'},
         check=nothing_started)
    with open(os.path.join(wt, 'dirty.txt'), 'w') as f:
        f.write('x')
    case('dirty worktree refused', 1, check=nothing_started)
    os.remove(os.path.join(wt, 'dirty.txt'))

shutil.rmtree(tmp, ignore_errors=True)
if failures:
    print('\n'.join(failures))
    print('FAIL: %d case(s)' % len(failures))
    sys.exit(1)
if SKIPPED:
    print('SKIP: `script` cannot open a terminal here, so %d case(s) that open the chat did not '
          'run; %d refusal case(s) ok' % (SKIPPED, CASES))
    sys.exit(77)
print('OK: start_issue_chat, %d cases%s' % (CASES, ' (Windows: the refusal only)' if WINDOWS else ''))
