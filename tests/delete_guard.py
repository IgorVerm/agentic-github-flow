#!/usr/bin/env python3
"""Checks the guards plugin's pre_tool_delete_guard.py: python3 tests/delete_guard.py.

Every case of tests/delete_guard_cases.py runs the hook as Claude Code does (PreToolUse JSON on
stdin) under that module's fixture home folder. The hook only reads the command and looks at
paths; nothing here runs a delete. Every ASK case must ask and every PASS case pass, and every
answer must be "ask" or nothing: the hook never denies. WINDOWS_PATHS checks the path reading
for Git Bash and drive paths on any system. The end checks the hook contract, long inputs
through stdin (Windows refuses a command line over 32,767 characters) and the wiring in the
plugin's hooks/hooks.json. tests/delete_guard_differential.py checks the same cases, and more,
against the guard as it was on main.
"""
import importlib.util, json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from delete_guard_cases import *  # noqa: E402,F403 (the fixture, ASK and PASS)

failures = []
for command, cwd in ASK:
    got = decision(run(command, cwd))
    if not got or got[0] != 'ask':
        failures.append('NOT ASKED: %r (cwd %s)' % (command[:200], os.path.relpath(cwd, tmp)))
for command, cwd in PASS:
    got = decision(run(command, cwd))
    if got:
        failures.append('WRONGLY ASKED: %r: %s' % (command[:200], got[1][:220]))

# Windows path reading, on any system: Git Bash and drive spellings of the same folders
spec = importlib.util.spec_from_file_location('delete_guard_module', HOOK)
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)
dg.WINDOWS = True
WIN_HOMES = frozenset({'c:/%s/fixture' % USERS.lower()})
WINDOWS_PATHS = [(written.replace('%s', USERS), cwd and cwd.replace('%s', USERS), want)
                 for written, cwd, want in [
    # (path as written, cwd, protected?); %s is the folder of the homes
    ('/c/%s/fixture/AppData/Roaming/App', None, True),
    ('C:\\%s\\fixture\\Documents', None, True), ('/cygdrive/c/%s/fixture', None, True),
    ('C:/%s/other', None, True), ('C:/', None, True), ('/c', None, True),
    ('D:/data', None, True), ('C:\\Windows\\System32', None, True),
    ('/c/Program Files/Git', None, True), ('C:/%s/fixture/../..', None, True),
    ('..\\..', 'C:/%s/fixture/code', True),
    ('/c/%s/fixture/code/repo/target', None, False),
    ('build', 'C:\\%s\\fixture\\code\\repo', False),
    ('C:/%s/fixture/AppData/Local/Temp/x', None, False),
]]
for written, cwd, want in WINDOWS_PATHS:
    path = dg.norm(written, dg.norm(cwd, None) if cwd else None)
    got = bool(dg.protected(path, WIN_HOMES))
    if got != want:
        failures.append('WINDOWS PATH: %r (cwd %r) read as %r, protected %s, expected %s'
                        % (written, cwd, path, got, want))
dg.WINDOWS = os.name == 'nt'
dg.variants.cache_clear()
dg.git_root.cache_clear()
dg.holds_repository.cache_clear()

# a call that blocks (a hung mount): the judging thread is abandoned after HARD_DEADLINE
saved = dg.decide, dg.HARD_DEADLINE
dg.decide, dg.HARD_DEADLINE = (lambda command, cwd: time.sleep(30)), 0.3
started = time.time()
reason, finished = dg.decide_bounded('rm -rf build', REPO)
if finished or 'within' not in (reason or '') or time.time() - started > 2:
    failures.append('hard deadline: a blocked judgement must ask after HARD_DEADLINE')
if dg.decide_bounded('ls -la', REPO) != (None, False):
    failures.append('hard deadline: a blocked command without a delete must pass')
dg.decide, dg.HARD_DEADLINE = saved
if dg.HARD_DEADLINE >= 10:
    failures.append('HARD_DEADLINE must stay under the 10 s timeout in hooks.json')

# the deadline: past it, a command that names a delete asks, and any other passes
saved, dg.DEADLINE = dg.DEADLINE, -1.0
if 'longer than' not in (dg.decide('rm -rf build', REPO) or ''):
    failures.append('deadline: a delete judged past the deadline must ask')
if dg.decide('ls -la', REPO) is not None:
    failures.append('deadline: a command without a delete must pass past the deadline')
dg.DEADLINE = saved

# the review's slow shape: many recursive targets over a folder of 2,100 folders, judged
# through the hook process well under the deadline (each folder is scanned once)
WIDE = os.path.join(SESSION_TMP, 'wide')
for k in range(2100):
    os.makedirs(os.path.join(WIDE, 'd%04d' % k))
started = time.time()
r = run('rm -rf ' + ' '.join(['wide', './wide', 'wide/', 'wide/../wide'] * 1000), SESSION_TMP)
took = time.time() - started
if took > dg.DEADLINE * 0.75 or decision(r):
    failures.append('wide folder: 4,000 targets must pass in under %.1f s (took %.1f s; %s)'
                    % (dg.DEADLINE * 0.75, took, decision(r)))

# the contract: "ask" with a reason or nothing, never "deny", exit 0, for any input
outputs = [run(c, w) for c, w in ASK + PASS]
outputs += [run('rm -rf ~/Library', REPO, tool='Write'), run('', REPO, raw='not json'),
            run('', REPO, raw='[]'), run('rm -rf "an unclosed quote ~/Library', REPO)]
for raw in ('{"tool_name": 5}',
            '{"tool_name": "Bash", "cwd": 5, "tool_input": {"command": "rm -rf ~"}}',
            '{"tool_name": "Bash", "tool_input": {"command": 7}}', 'null', '"x"'):
    r = run('', REPO, raw=raw)
    if r.returncode != 0 or 'deny' in r.stdout.lower():
        failures.append('contract: %s gave exit %d' % (raw, r.returncode))
for r in outputs:
    if r.returncode != 0 or 'deny' in r.stdout.lower():
        failures.append('contract: exit %d, output %s' % (r.returncode, r.stdout[:120]))
if decision(outputs[-4]) or decision(outputs[-3]) or decision(outputs[-2]):
    failures.append('contract: another tool and unreadable input must pass')
if not decision(outputs[-1]):
    failures.append('contract: an unparsable command that names rm must ask')
event = {'tool_name': 'Bash', 'cwd': REPO, 'tool_input': {'command': ['rm', '-rf', H]}}
if not decision(run('', REPO, raw=json.dumps(event))):
    failures.append('contract: a command given as a list must be judged')
got = decision(run('rm -rf ~/Library', REPO))
if not got or not all(text in got[1] for text in (
        "Outside a repository, delete with the system's trash, not `rm -rf`",
        'Approve only if the user', '`gio trash` on Linux', 'the Recycle Bin on Windows')):
    failures.append('contract: the reason must quote the rule, say who approves and give the '
                    'safe form')
if decision(run('rm -rf ~/Library', REPO, tool='mcp__terminal__run_in_terminal')) is None:
    failures.append('contract: run_in_terminal is judged as Bash')

# long inputs come through stdin, as the client sends them; the cap asks, and stays fast
if not decision(run('rm -rf build ' + 'x' * 40000, REPO)):
    failures.append('a command over MAX_INPUT that names a delete must ask')
if decision(run('echo ' + 'x' * 40000, REPO)):
    failures.append('a long command without a delete must pass')
for command in ('rm -rf build ' + "$'\\x' " * 4000, 'cat <<A\n' * 3000 + 'rm -rf ~/Library',
                'echo "$(' * 1000 + 'rm -rf ~/Library' + ')"' * 1000):
    started = time.time()
    r = run(command[:30000], REPO)
    if time.time() - started > 3 or r.returncode != 0:
        failures.append('a 30 KB input must be judged within 3 s (took %.1f s): %r'
                        % (time.time() - started, command[:40]))

# the plugin's hooks.json runs the hook for Bash and run_in_terminal, and for nothing else
with open(os.path.join(GUARDS, 'hooks', 'hooks.json'), encoding='utf-8') as f:
    entries = json.load(f)['hooks']['PreToolUse']
wiring = [e for e in entries if e['hooks'][0]['command'].endswith('pre_tool_delete_guard.py"')]
if len(wiring) != 1:
    failures.append('hooks.json: expected one entry that runs pre_tool_delete_guard.py')
else:
    matcher = wiring[0]['matcher']
    for tool in ('Bash', 'mcp__terminal__run_in_terminal'):
        if not re.search(matcher, tool):
            failures.append('hooks.json: the matcher does not reach %s' % tool)
    for tool in ('Write', 'Edit', 'mcp__terminal__read_terminal', 'WebFetch'):
        if re.search(matcher, tool):
            failures.append('hooks.json: the matcher reaches %s, which the hook does not judge'
                            % tool)

if failures:
    print('\n'.join(failures))
    sys.exit(1)
print('OK: %d asked, %d passed, %d Windows paths, never denied, hook contract and wiring hold'
      % (len(ASK), len(PASS), len(WINDOWS_PATHS)))
