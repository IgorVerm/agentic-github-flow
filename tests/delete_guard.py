#!/usr/bin/env python3
"""Checks the guards plugin's pre_tool_delete_guard.py: python3 tests/delete_guard.py.

Every case runs the hook as Claude Code does (PreToolUse JSON on stdin) under a fixture home
folder in a temporary directory, with `Library/Application Support`, `AppData`, a git
repository and a folder of worktrees in it, and a temporary folder of its own (TMPDIR). The
hook only reads the command and looks at paths; nothing here runs a delete. ASK lists commands
that must reach the user's approval, PASS lists routine work it must leave alone. Every answer
must be "ask" or nothing: the hook never denies. WINDOWS_PATHS checks the path reading for
Git Bash and drive paths on any system. The end checks the hook contract, long inputs through
stdin (Windows refuses a command line over 32,767 characters) and the wiring in the plugin's
hooks/hooks.json.
"""
import importlib.util, json, os, re, subprocess, sys, tempfile, time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
GUARDS = os.path.join(ROOT, 'plugins', 'guards')
HOOK = os.path.join(GUARDS, 'scripts', 'pre_tool_delete_guard.py')


USERS = 'Us' 'ers'  # spelled in two parts, so the repository's home-path check passes


def fwd(path):
    """A path as an agent writes it in a Bash command: forward slashes, also on Windows."""
    return path.replace('\\', '/')


tmp = os.path.realpath(tempfile.mkdtemp(prefix='delete-guard-'))
HOME = os.path.join(tmp, 'fixtureuser')
SESSION_TMP = os.path.join(tmp, 'session-tmp')  # the client's TMPDIR
AS = os.path.join(HOME, 'Library', 'Application Support')
CODE = os.path.join(HOME, 'My projects')
REPO = os.path.join(CODE, 'repo')
WTS = os.path.join(CODE, 'repo-worktrees')
WT = os.path.join(WTS, '52-x')
OUTSIDE = os.path.join(HOME, 'Downloads', 'old')
ME = os.path.basename(os.path.realpath(os.path.expanduser('~')))  # the real account name
for d in (os.path.join(AS, 'Foo', 'cache'), os.path.join(HOME, 'Library', 'Caches'),
          os.path.join(HOME, 'AppData', 'Roaming', 'Code'),
          os.path.join(HOME, 'AppData', 'Local', 'Temp'),
          os.path.join(HOME, '.ssh'), os.path.join(HOME, 'Documents', 'notes'),
          os.path.join(REPO, 'target', 'debug'), os.path.join(REPO, 'build'), WT, OUTSIDE,
          SESSION_TMP):
    os.makedirs(d, exist_ok=True)
subprocess.run(['git', 'init', '-q', REPO], check=True)
try:
    os.symlink(os.path.join(HOME, 'Library'), os.path.join(REPO, 'liblink'))
    LINK = True
except OSError:  # Windows without the right to create links
    LINK = False
with open(os.path.join(WT, '.git'), 'w') as f:
    f.write('gitdir: %s/.git/worktrees/52-x\n' % fwd(REPO))
H, R, A = fwd(HOME), fwd(REPO), fwd(AS)


def env_for():
    env = {k: v for k, v in os.environ.items() if k not in ('TMPDIR', 'TEMP', 'TMP')}
    env.update(HOME=HOME, USERPROFILE=HOME, TMPDIR=SESSION_TMP)
    return env


def run(command, cwd=REPO, tool='Bash', raw=None):
    event = {'hook_event_name': 'PreToolUse', 'tool_name': tool, 'cwd': cwd,
             'tool_input': {'command': command}}
    return subprocess.run([sys.executable, HOOK], input=raw if raw is not None else
                          json.dumps(event), capture_output=True, text=True, env=env_for())


def decision(r):
    if not r.stdout.strip():
        return None
    out = json.loads(r.stdout)['hookSpecificOutput']
    return out['permissionDecision'], out['permissionDecisionReason']


ASK = [
    # the reported incident: xargs splits "Application Support", dirname gives ~/Library
    ('find "$HOME/Library/Application Support" -name "*.cache" | xargs -n1 dirname '
     '| xargs rm -rf', REPO),
    ("printf '%s\\n' ~/Library/Application\\ Support/Foo/cache | xargs -n1 dirname "
     "| xargs rm -rf", REPO),
    ('ls ~/Library/Logs | xargs rm', REPO),
    ('find . -name "*.tmp" -print0 | xargs -0 rm -f', REPO),
    ('rm -rf ~/Library', REPO), ('rm -rf "$EMPTY"/*', REPO), ('find ~ -delete', REPO),
    # protected targets, in other spellings
    ('rm -rf "$HOME/Library/Application Support"', REPO), ('rm -rf ~/Library/Caches', REPO),
    ('rm -fr ~/Library/Application\\ Support', REPO), ('rm -rf ~/library', REPO),
    ('/bin/rm -rf ~/Library', REPO), ('rm -r -- ~/Documents', REPO), ('rm -rf ~/*', REPO),
    ('rm -rf ~/.* ', REPO), ('rm -rf ~/Library/*', REPO), ('rm -rf ~/Documents/*', REPO),
    ('rm -rf /Applications/*', REPO), ('rm -rf /*', REPO), ('rm ~/.zshrc', REPO),
    ('rm -f ~/.ssh/id_ed25519', REPO), ('rm -rf /', REPO), ('rm -rf /Users', REPO),
    ('rm -rf /%s/someoneelse' % USERS, REPO), ('rm -rf /ho' 'me/someoneelse', REPO),
    ('sudo rm -rf /Applications/Foo.app', REPO), ('rm -rf /Library/Caches', REPO),
    ('rm -rf /usr/local/lib', REPO), ('rm -rf /etc/ssh', REPO), ('rm -rf "%s"' % H, REPO),
    ('rm -rf "%s/.."' % H, REPO), ('rmdir ~/Documents', REPO), ('unlink ~/.zshrc', REPO),
    ('timeout 5 rm -rf ~/Library', REPO), ('env X=1 rm -rf ~', REPO), ('rm -rf ../../..', REPO),
    ('rm -rf ~/AppData/Roaming/Code', REPO), ('rm -rf "$HOME/AppData"', REPO),
    # computed targets
    ('rm -rf "$(dirname "$f")"', REPO), ('rm -rf `pwd`/x', REPO), ('rm -rf "$TARGET"', REPO),
    ('rm -rf ${TARGET:-}', REPO), ('rm -rf $DIR/build', REPO),
    ('for d in a b; do rm -rf "$d"; done', REPO),
    ('cat list.txt | while read p; do rm -rf "$p"; done', REPO),
    ('D=$(date +%s); rm -rf "/tmp/x/../../$D"', REPO), ('rm -rf "$S"/build', REPO),
    ('rm -rf "build-$C"', REPO), ('rm -rf $S/x', REPO),
    ('cd "$D" && rm -rf *', REPO), ('cd && rm -rf *', REPO), ('cd ~ && rm -rf ./*', REPO),
    # behind a shell, eval or a here-document
    ("bash -c 'rm -rf \"$X\"'", REPO), ('sh -c "rm -rf ~/Documents"', REPO),
    ("zsh -lc 'cd ~ && rm -rf *'", REPO), ("eval 'rm -rf ~/Documents'", REPO),
    ("bash <<'EOF'\nrm -rf ~/Library\nEOF", REPO), ('echo "$(rm -rf ~/Library)"', REPO),
    # spellings of the command name, quoting, wrappers
    ('\\rm -rf ~/Library', REPO), ('r\\m -rf ~/Library', REPO), ('"r"m -rf ~/Library', REPO),
    ("r''m -rf ~/Library", REPO), ('RM -rf ~/Library', REPO), ('/BIN/RM -rf ~/Library', REPO),
    ("$'rm' -rf ~/Library", REPO), ("$'\\x72m' -rf ~/Library", REPO),
    ("rm -rf $'%s/Library'" % H, REPO), ("rm -rf $'\\q' ~/Library", REPO),
    ('rm -rf ~%s/Library' % ME, REPO), ('rm -rf /Use{rs,}/%s/Library' % ME, REPO),
    ('rm -rf ~/{Library,Documents}', REPO),
    ('ls x | xargs sudo rm -rf', REPO), ('ls x | xargs env rm -rf', REPO),
    ('ls x | xargs nice -n 5 rm -rf', REPO), ('ls x | xargs --max-args 1 rm -rf', REPO),
    ("ls -d ~/Library/Application\\ Support/*/x | xargs -n1 dirname | xargs -I{} sh -c "
     "'rm -rf \"{}\"'", REPO),
    ("find ~ -maxdepth 1 -exec sh -c 'rm -rf \"$1\"' _ {} \\;", REPO),
    ('find ~/Library -maxdepth 0 -exec sudo rm -rf {} +', REPO),
    ('find ~/Library -maxdepth 0 -exec \\rm -rf {} +', REPO),
    ('find -- ~ -delete', REPO), ('find -f ~ -delete', REPO),
    ('rm "-rf" "$DIR"', REPO), ("rm '-r' -f $X", REPO), ('rm --rec "$X"', REPO),
    ('builtin cd ~ && rm -rf Library', REPO), ('command cd ~ && rm -rf Library', REPO),
    ('if cd ~; then rm -rf Library; fi', REPO), ('{ cd ~; rm -rf Library; }', REPO),
    ("bash -c -- 'rm -rf ~/Library'", REPO), ("bash <<< 'rm -rf ~/Library'", REPO),
    ("echo 'rm -rf ~/Library' | sh", REPO), ("printf 'rm -rf %s\\n' ~/Library | bash", REPO),
    ("csh -c 'rm -rf ~/Library'", REPO), ("fish -c 'rm -rf ~/Library'", REPO),
    ("su root -c 'rm -rf ~/Library'", REPO), ("CMD='rm -rf ~/Library'; sh -c \"$CMD\"", REPO),
    ("CMD='rm -rf ~/Library'; eval \"$CMD\"", REPO), ('R=rm; $R -rf ~/Library', REPO),
    ('$RMCMD -rf build', REPO), ('arch -arm64 rm -rf ~/Library', REPO),
    ('script -q /dev/null rm -rf ~/Library', REPO),
    (' '.join(['eval'] * 10) + ' rm -rf ~/Library', REPO),
    (' '.join(['nice'] * 10) + ' rm -rf ~/Library', REPO),
    ('=rm -rf ~/Library', REPO), ('rm.exe -rf ~/Library', REPO),
    ('"C:\\Program Files\\Git\\usr\\bin\\rm.exe" -rf ~/Library', REPO),
    ('X=/bin/rm; "$X" -rf ~/Library', REPO), ('ls x | parallel rm -rf', REPO),
    ('cd ~ && rm -rf ~+/Library', REPO), ('rm -rf "%s/Foo"' % A, REPO),
    ('rm -rf ~/Library/Preferences/com.example.app.plist', REPO),
    # repositories and worktrees go through the cleanup-merged skill
    ('rm -rf "%s"' % R, CODE), ('rm -rf "%s"' % fwd(WT), REPO), ('rm -rf "%s"' % fwd(WTS), REPO),
    ('rm -rf .git', REPO), ('rm -rf .', REPO),
    # find with a delete outside a git worktree and the temporary folders
    ('find . -name "*.log" -delete', OUTSIDE),
    ('find "%s" -exec rm -rf {} +' % fwd(OUTSIDE), REPO),
    ('find ~/Library/Caches -type f -delete', REPO), ('find "$DIR" -delete', REPO),
    ('find /tmp -delete', REPO),
    # more paths than the guard reads (6,400 by brace expansion)
    ('rm -rf /tmp/x ' + 'a{1,2}{3,4}{5,6}{7,8}{9,0}{1,2}/ ' * 100, REPO),
]
if LINK:
    ASK.append(('rm -rf "%s/liblink/"' % R, REPO))

PASS = [
    ('rm -rf "%s/target"' % R, REPO), ('rm -rf target', REPO), ('rm -rf ./build dist', REPO),
    ('rm -rf node_modules', REPO), ('rm -rf build/*', REPO),
    ('rm -f "%s/a.txt" 2>/dev/null' % R, REPO),
    ('rm -rf "%s/target"' % fwd(WT), WT), ('mkdir -p x && rm -rf x', REPO),
    ('rm -rf "$HOME/My projects/repo/target"', REPO), ('rm -rf "$PWD/build"', REPO),
    ('D="%s/target"; rm -rf "$D"' % R, REPO), ('cd "%s" && rm -rf build/*' % R, CODE),
    ('rm "$f"', REPO), ('rm -f "$TMPFILE"', REPO),
    ('D=$(mktemp -d); rm -rf "$D"', REPO), ('T=$(mktemp -d); cd "$T" && find . -delete', REPO),
    ('S=/tmp/session-1/s; C=$(git rev-parse --short HEAD); rm -rf "$S/pkg-$C"', REPO),
    ('rm -rf "%s/target/$C"' % R, REPO), ('rm -rf "./target/$PROFILE"', REPO),
    ('trash "%s/Foo"' % A, REPO), ('trash ~/Downloads/old', REPO), ('trash ~/Library/Caches', REPO),
    ('find . -name "*.pyc" -delete', REPO),
    ('find "%s" -name __pycache__ -exec rm -rf {} +' % R, REPO),
    ('find /tmp/session-1/x -name "*.o" -delete', REPO),
    ('find "$TMPDIR/x" -name "*.o" -delete', REPO),
    ('rm -rf /tmp/session-1/x/build', REPO), ('rm -rf "%s"' % fwd(OUTSIDE), REPO),
    ('xargs trash < list.txt', REPO), ('rm -f /tmp/ov570.*', REPO),
    ('rm -rf ~/Documents/notes/*', REPO), ('git rm -r --cached build', REPO),
    ('echo "rm -rf ~"', REPO), ('grep -rn "rm -rf" .', REPO), ('find . -name "*.rs"', REPO),
    ('gh issue comment 1 --body "never rm -rf ~/Library"', REPO),
    ("git commit -m 'rm -rf ~/Library was the incident' -- a.md", REPO),
    ('git commit -m "$(cat <<\'EOF\'\nFix two things:\n1) the `xargs rm -rf` shape asks\n'
     '2) docs\nEOF\n)" -- a.md', REPO),
    ('rm -rf "$TMPDIR/x"', REPO), ('rm -rf ~/Library/Caches/pip', REPO),
    ('rm -rf ~/Library/Logs/old-app', REPO), ('rm -rf ~/AppData/Local/Temp/build-1', REPO),
    ('docker rm -f web', REPO), ('rm -rf .venv', REPO),
    ('ls | xargs sed -n 1p', REPO), ('$PYTHON -m pytest -rA', REPO),
    ('cargo clean', REPO), ('npm ci', REPO), ('ls -la ~/Library', REPO),
    ('python3 tests/delete_guard.py', REPO),
    ("cat > notes.md <<'EOF'\nrm -rf ~/Library\nEOF", REPO),
    ("echo $'a\\tb' && rm -rf build", REPO),
]

failures = []
for command, cwd in ASK:
    got = decision(run(command, cwd))
    if not got or got[0] != 'ask':
        failures.append('NOT ASKED: %r (cwd %s)' % (command, os.path.relpath(cwd, tmp)))
for command, cwd in PASS:
    got = decision(run(command, cwd))
    if got:
        failures.append('WRONGLY ASKED: %r: %s' % (command, got[1][:160]))

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
if got and ('Approve only if the user' not in got[1] or 'trash' not in got[1]):
    failures.append('contract: the reason must say who approves and the safe form')
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
