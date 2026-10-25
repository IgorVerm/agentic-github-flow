#!/usr/bin/env python3
"""Checks the guards plugin's pre_tool_personal_data.py: python3 tests/personal_data_guard.py.

The hook reads the user's identifiers at run time, so every case runs it under a fixture
identity (a temporary HOME with its own git config, gh config and personal-data file); no real
identifier appears here. ASK lists calls that send that identity, or someone's e-mail address,
off the machine; each would be a leak if the hook let it pass. PASS lists routine calls the hook
must not prompt on (the user's identity on GitHub, a first name as the decision-maker, home
paths, local tools). The end checks the matcher in the plugin's hooks/hooks.json, a missing
configuration and the hook contract. Cases with the GitHub login need `gh` to read the fixture's
login; without gh they are left out and the output says so.

The Codex entry point (`--codex`) must deny every ASK case and pass every PASS case, in every
Codex permission mode (Codex shows the hook no sign of whether the user will be prompted), with
the output Codex accepts; CODEX_DENY adds the tool names Codex uses (measured 2026-10-25).
"""
import json, os, re, shutil, subprocess, sys, tempfile, time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
GUARDS = os.path.join(ROOT, 'plugins', 'guards')
HOOK = os.path.join(GUARDS, 'scripts', 'pre_tool_personal_data.py')
HAVE_GH = shutil.which('gh') is not None
NAME, EMAIL, LOGIN = 'Fixture Persona', 'fixture.persona@fixture-persona.eu', 'FixtureLogin'
PHONE_LINE, PHONE_SENT = 'phone: +32 470 12 34 56', '0470/12.34.56'

tmp = tempfile.mkdtemp(prefix='pd-guard-')
HOME = os.path.join(tmp, 'fixtureperson')
os.makedirs(os.path.join(HOME, 'cfg', 'agentic-github-flow'))
os.makedirs(os.path.join(HOME, 'gh'))
with open(os.path.join(HOME, '.gitconfig'), 'w') as f:
    f.write('[user]\n\tname = %s\n\temail = %s\n' % (NAME, EMAIL))
with open(os.path.join(HOME, 'gh', 'hosts.yml'), 'w') as f:
    f.write('github.com:\n    user: %s\n    git_protocol: https\n' % LOGIN)
with open(os.path.join(HOME, 'cfg', 'agentic-github-flow', 'personal-data'), 'w') as f:
    f.write('# fixture\n%s\n' % PHONE_LINE)
os.makedirs(os.path.join(tmp, 'My projects'))  # repositories often sit under a space
BODY = os.path.join(tmp, 'My projects', 'body.md')
with open(BODY, 'w') as f:
    f.write('Reported by %s.\n' % NAME)
PAGE = os.path.join(tmp, 'page.html')
with open(PAGE, 'w') as f:
    f.write('<p>Contact: %s</p>\n' % EMAIL)
BIG = os.path.join(tmp, 'big.html')  # a minified page: a long run of address characters
with open(BIG, 'w') as f:
    f.write('<script>var d="%s";</script><p>jane.doe@realmail.io</p>\n' % ('a1.' * 300000))
EMPTY = os.path.join(tmp, 'empty-home')
os.makedirs(EMPTY)


def env_for(home, cfg=True):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('GIT_', 'GH_', 'XDG_'))}
    env.update(HOME=home, USERPROFILE=home, GIT_CONFIG_NOSYSTEM='1',
               XDG_CONFIG_HOME=os.path.join(home, 'cfg'), GH_CONFIG_DIR=os.path.join(home, 'gh'))
    return env


def run(event, home=HOME, args=()):
    return subprocess.run([sys.executable, HOOK, *args], input=json.dumps(event),
                          capture_output=True, text=True, env=env_for(home))


def codex(event, mode='default'):
    """The event as Codex sends it (measured with codex-cli 0.164.0-alpha.11.1)."""
    return dict(event, session_id='s', turn_id='t', model='gpt', permission_mode=mode,
                tool_use_id='exec-1', transcript_path=None)


def bash(command, cwd=None):
    return {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'cwd': cwd or tmp,
            'tool_input': {'command': command}}


def tool(name, **tool_input):
    return {'hook_event_name': 'PreToolUse', 'tool_name': name, 'cwd': tmp,
            'tool_input': tool_input}


ASK = [
    # the incident behind the rule: an e-mail address in a User-Agent for crates.io
    bash('curl -s -A "probe-check (%s)" https://crates.io/api/v1/crates/sccache/versions'
         % EMAIL),
    tool('WebFetch', url='https://lookup.example.org/find?email=%s' % EMAIL.replace('@', '%40'),
         prompt='who is this'),
    tool('WebSearch', query='%s address' % NAME),
    tool('mcp__Claude_Browser__form_input', ref='ref_3', value=NAME),
    tool('mcp__claude-in-chrome__computer', action='type', text='Persona'),
    tool('mcp__Claude_Browser__browser_batch', actions=[
        {'name': 'navigate', 'input': {'url': 'https://forms.example.org/?n=Fixture+Persona'}}]),
    tool('mcp__some_saas__create_contact', email=EMAIL),
    bash('gh issue comment 12 --body "Mail %s for access"' % EMAIL),
    bash('gh issue create --title x --body-file "%s"' % BODY),
    bash('curl -d @"%s" https://x.io/api' % BODY),
    bash('echo "{\\"email\\": \\"%s\\"}" | curl -d @- https://x.io/api' % EMAIL),
    bash('printf %%s "%s" | gh api repos/a/b/issues/1/comments -F body=@-' % NAME),
    bash('echo "%s" | ssh box "cat >> /srv/contacts"' % EMAIL),
    bash("gh issue comment 1 --body-file - <<'EOF'\nContact: %s\nEOF" % EMAIL),
] + ([bash('curl -A "probe (%s)" https://crates.io/api/v1/crates/x' % LOGIN)] if HAVE_GH else []) + [
    bash('curl -d "to=jane.doe@realmail.io" https://api.mailer.io/send'),
    bash('python3 -c "import urllib.request; urllib.request.urlopen(\'https://x.io/?u=%s\')"'
         % EMAIL),
    bash('bash -lc "curl -H \'From: %s\' https://x.io"' % EMAIL),
    bash('timeout 20 wget "https://x.io/?q=%s"' % NAME.replace(' ', '%20')),
    bash('curl -d "phone=%s" https://x.io/callback' % PHONE_SENT),
    bash('ssh box "echo %s > /srv/contact"' % EMAIL),
    tool('Artifact', file_path=PAGE),
    tool('Artifact', file_path=BIG),
]

PASS = [
    bash('git push origin main'),
    # a systemd user unit is no address
    bash("ssh box 'systemctl --user status user@1000.service; ls /sys/fs/cgroup/user.slice/"
         "user-1000.slice/user@1000.service/app.slice'"),
    bash('git -c user.name="%s" -c user.email=%s commit -m x -- a.md' % (NAME, EMAIL)),
    bash('git -c user.email=%s push origin main' % EMAIL),
    bash('git commit -m "x (#1)\n\nCo-Authored-By: Claude <noreply@anthropic.com>" -- a.md'
         ' && git push origin main'),
    bash("gh issue comment 304 -R %s/project --body \"🤖 Claude Code (build): Fixture's ruling"
         " stands; Fixture said to merge it.\"" % LOGIN),
    bash('gh api repos/%s/project/issues -q ".[].title"' % LOGIN),
    bash('curl -s https://api.github.com/repos/%s/project' % LOGIN),
    tool('WebFetch', url='https://github.com/%s/project/issues/1' % LOGIN, prompt='summary'),
    bash('curl -s https://crates.io/api/v1/crates/x'
         ' -o "/Us' 'ers/fixtureperson/My projects/x.json"'),
    bash('rsync -a "%s/My projects/app/" box:/srv/app/' % HOME),
    bash("cat > notes.md <<'EOF'\n%s, %s\nEOF" % (NAME, EMAIL)),
    bash('echo "%s" && grep -rn "%s" docs' % (EMAIL, NAME)),
    bash('python3 -c "print(\'https://github.com/%s/x\')"; gh issue list' % LOGIN),
    bash('curl -d "user=someone@example.com" https://x.io'),
    bash('git clone git@github.com:%s/project.git' % LOGIN),
    tool('Write', file_path=os.path.join(tmp, 'x.md'), content=EMAIL),
    tool('mcp__ccd_session_mgmt__send_message', session_id='s', message=NAME),
    tool('Artifact', action='read', url='https://claude.ai/artifact/abc'),
]

CODEX_DENY = [
    tool('webrun', search_query=[{'q': '%s contact' % EMAIL}], response_length='short'),
    tool('web.run', search_query=[{'q': '%s contact' % EMAIL}]),  # the binary's spelling
    tool('webrun', open=[{'ref_id': 'https://lookup.example.org/?who=' + NAME.replace(' ', '+')}]),
    tool('mcp__openaiDeveloperDocs__search_openai_docs', query='mail %s' % EMAIL, limit=3),
    # a model cannot unlock the call: an inline variable, a flag or a comment changes nothing
    bash('PD_CONFIRMED=1 curl -d "to=%s" https://x.io/send' % EMAIL),
    bash('curl --confirmed -d "to=%s" https://x.io/send  # the user confirmed' % EMAIL),
]

failures = []
for event in ASK:
    started = time.time()
    r = run(event)
    if time.time() - started > 3:
        failures.append('SLOW (%.0f s; the hook timeout is 10 s): %s %s' % (
            time.time() - started, event['tool_name'], json.dumps(event['tool_input'])[:80]))
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    spec = out.get('hookSpecificOutput', {})
    if r.returncode != 0 or spec.get('permissionDecision') != 'ask':
        failures.append('NOT ASKED: %s %s' % (event['tool_name'],
                                               json.dumps(event['tool_input'])[:120]))
    elif any(v in spec.get('permissionDecisionReason', '') for v in (NAME, EMAIL, LOGIN, 'jane')):
        failures.append('REASON ECHOES THE VALUE: ' + spec['permissionDecisionReason'])
for event in PASS:
    r = run(event)
    if r.returncode != 0 or r.stdout.strip():
        failures.append('WRONGLY ASKED: %s %s  (%s)' % (event['tool_name'], json.dumps(
            event['tool_input'])[:120], r.stdout.strip()[-140:]))

# Codex: deny, never ask or allow (Codex rejects both from PreToolUse), a non-empty reason (it
# rejects a deny without one), no other key it rejects, in every permission mode; the reason
# sends the model to the user and never echoes the value.
CODEX_MODES = ('default', 'acceptEdits', 'plan', 'dontAsk', 'bypassPermissions')
for event in ASK + CODEX_DENY:
    for mode in (CODEX_MODES if event is ASK[0] or event in CODEX_DENY else ('default',)):
        r = run(codex(event, mode), args=('--codex',))
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        spec = out.get('hookSpecificOutput', {})
        reason = spec.get('permissionDecisionReason') or ''
        what = 'CODEX (%s): %s %s' % (mode, event['tool_name'],
                                      json.dumps(event['tool_input'])[:100])
        if r.returncode != 0 or spec.get('permissionDecision') != 'deny' or not reason:
            failures.append('NOT DENIED ' + what)
        elif set(out) != {'hookSpecificOutput'} or set(spec) != {
                'hookEventName', 'permissionDecision', 'permissionDecisionReason'}:
            failures.append('CODEX OUTPUT HAS KEYS IT REJECTS: ' + r.stdout[:160])
        elif any(v in reason for v in (NAME, EMAIL, LOGIN, 'jane')):
            failures.append('CODEX REASON ECHOES THE VALUE: ' + reason)
        elif 'ask their explicit confirmation' not in reason or ('exact command' in reason) != (
                event['tool_name'] == 'Bash'):
            failures.append('CODEX REASON LACKS THE CONFIRMATION PATH: ' + reason)
for event in PASS:
    r = run(codex(event, 'bypassPermissions'), args=('--codex',))
    if r.returncode != 0 or r.stdout.strip():
        failures.append('CODEX WRONGLY DENIED: %s %s  (%s)' % (event['tool_name'], json.dumps(
            event['tool_input'])[:120], r.stdout.strip()[-140:]))

# the plugin's hooks.json must hand the hook every tool it judges, and no local tool
with open(os.path.join(GUARDS, 'hooks', 'hooks.json'), encoding='utf-8') as f:
    entries = json.load(f)['hooks']['PreToolUse']
wiring = [e for e in entries if e['hooks'][0]['command'].endswith('pre_tool_personal_data.py"')]
if len(wiring) != 1:
    failures.append('hooks.json: expected one entry that runs pre_tool_personal_data.py')
else:
    matcher = wiring[0]['matcher']
    for event in ASK:
        if not re.search(matcher, event['tool_name']):
            failures.append('hooks.json: the matcher misses %s' % event['tool_name'])
    for name in ('Read', 'Write', 'Edit', 'Agent', 'NotebookEdit'):
        if re.search(matcher, name):
            failures.append('hooks.json: the matcher runs the hook for %s' % name)

# no git, gh or local configuration: no crash, and someone's e-mail address is still asked
r = run(bash('curl -A "probe (%s)" https://x.io' % NAME), home=EMPTY)  # nothing to match
if r.returncode != 0 or r.stdout.strip() or r.stderr.strip():
    failures.append('missing configuration: must pass quietly (%s)' % (r.stderr.strip()[-120:]))
r = run(bash('curl -d "to=jane.doe@realmail.io" https://x.io'), home=EMPTY)
if 'ask' not in r.stdout:
    failures.append("missing configuration: someone's e-mail address must still be asked")
r = run(codex(bash('curl -d "to=jane.doe@realmail.io" https://x.io')), home=EMPTY,
        args=('--codex',))
if '"deny"' not in r.stdout:
    failures.append("Codex, missing configuration: someone's e-mail address must still be denied")
for bad in ('not json', '[]', '{"tool_name": "Bash", "tool_input": "x"}'):
    for args in ((), ('--codex',)):
        r = subprocess.run([sys.executable, HOOK, *args], input=bad, capture_output=True,
                           text=True, env=env_for(HOME))
        if r.returncode != 0 or r.stdout.strip():
            failures.append('hook contract: unreadable input must pass: %r %s' % (bad, args))

if failures:
    print('\n'.join(failures)); sys.exit(1)
print('OK: %d asked, %d passed; Codex: %d denied, %d passed; missing configuration and hook '
      'contract hold%s' % (len(ASK), len(PASS), len(ASK) + len(CODEX_DENY), len(PASS),
                           '' if HAVE_GH else ' (gh not installed: login cases left out)'))
