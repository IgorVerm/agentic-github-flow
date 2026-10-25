#!/usr/bin/env python3
"""PreToolUse hook (Claude Code, Codex): the user confirms before personal data leaves the machine.

Enforces the core rule "Personal data leaves the machine only on the user's explicit
confirmation". When a tool call that can send data off the machine carries one of the user's
identifiers, or anyone's e-mail address, the hook stops it and names what matched (never the
value):
- Claude Code: `permissionDecision: "ask"`, so Claude Code shows a permission prompt and the call
  runs only when the user approves it there.
- Codex (`--codex`): `permissionDecision: "deny"`. Codex rejects "ask" from a PreToolUse hook and
  does not show the hook whether a call will go to the user's approval prompt (measured with
  codex-cli 0.164), so no call can pass on an approval there. The reason tells the model to ask
  the user in the conversation which data goes to which recipient and, when the user confirms,
  to give them the exact command to run themselves. Nothing the model can set (an environment
  variable, a flag, a file, sandbox escalation) lets the call through.
Anything else passes silently and the normal permission flow applies.

Outbound calls (everything else is local and passes):
- Bash: a command that runs a network program, also behind a wrapper, `sh -c`, `eval`, `$(…)`:
  curl, wget, gh, ssh/scp/rsync, git push/fetch/clone/…, mail programs, `open <url>`, package
  publishing, or `python -c`/`node -e` code that uses a network library. Each such command is
  scanned with its arguments, the here-document it reads, the files it hands over
  (`--body-file`, `-F`, `--input`, `@file`, `-T`, `< file`) and the whole line when a pipe
  feeds what it sends (`echo … | curl -d @-`, `… | ssh`); URL-encoding is decoded first. A `git`
  push, fetch, pull, clone or ls-remote to a remote configured in the repository, a local path or
  GitHub is checked only for other people's addresses: the user's identity on commits and pushes
  is outside the rule. To any other host it is judged in full.
- WebFetch (the URL; the prompt stays with the model), WebSearch (the query).
- Artifact publish (the page and its files), ArtifactData, ArtifactComments.
- Every MCP tool except the desktop app's own local controls (LOCAL_MCP); `run_in_terminal` is
  judged as a Bash command. Browser tools are scanned in full: a typed text, a form value, a URL
  or page script.
- Codex: its shell tool arrives as Bash and its MCP tools as `mcp__<server>__<tool>`, so the rules
  above apply; its web tool `webrun` or `web.run` is scanned in full. Text written into a running
  command (`write_stdin`) reaches no hook.
Not seen: data sent by a script file or program the command starts (`python3 tools/x.py`), file
contents sent by scp/rsync, a handed-over file named through a shell variable
(`--body-file "$D/x.md"`), the conversation itself (it goes to the model provider anyway).
Not distinguished: the user's own machines (an ssh to one counts as leaving), and phone numbers
or addresses of other people (too many false matches among ids, dates and numbers).

The user's identifiers are read at run time, never from a committed file: `git config --global`
user.name and user.email, the gh login (`gh config get user -h github.com`), the local account
name, and one identifier per line in
`${XDG_CONFIG_HOME:-~/.config}/agentic-github-flow/personal-data` (outside every repository, so it
cannot be committed; lines may start with `email:`, `phone:` or `name:`). The first name alone is
not matched: "<first name>'s ruling" in an issue comment is routine. Paths under the home folder
are routine too. The gh login is not matched when the call only reaches GitHub (the configured
identity on pushes and issue posts is outside the rule). Any other e-mail address in an outbound
call is someone's personal data and is asked too, except placeholder, no-reply and git-host
addresses (NOT_PERSONAL).

An input it cannot read passes, as with the git guard: a fault must not stop all work.

Usage as a hook: reads the PreToolUse JSON on stdin, prints the decision ("ask"; with `--codex`
"deny") on stdout or nothing, and exits 0. Test: `python3 tests/personal_data_guard.py`.
"""
import importlib.util, json, os, re, shlex, subprocess, sys
from urllib.parse import unquote, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('pre_tool_git_guard',
                                               os.path.join(HERE, 'pre_tool_git_guard.py'))
gg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gg)  # the shell parsing helpers have one owner: the git guard

NET_PROGRAMS = {'curl', 'wget', 'gh', 'ssh', 'scp', 'sftp', 'rsync', 'nc', 'ncat', 'netcat',
                'telnet', 'ftp', 'http', 'https', 'xh', 'aria2c', 'lynx', 'w3m', 'mail', 'mailx',
                'sendmail', 'msmtp', 'mutt', 'osascript', 'websocat', 'grpcurl'}
GIT_NET = {'push', 'fetch', 'pull', 'clone', 'ls-remote', 'send-email', 'request-pull',
           'submodule', 'archive'}
PUBLISHERS = {'npm', 'pnpm', 'yarn', 'cargo', 'docker', 'podman', 'twine', 'poetry', 'uv'}
PUBLISH_WORDS = {'publish', 'login', 'push', 'upload', 'adduser', 'owner'}
NET_CODE = re.compile(r'requests\.(get|post|put|patch|request|Session)|urlopen|urllib\.request|'
                      r'http\.client|httpx|aiohttp|smtplib|socket\.|\bfetch\(|XMLHttpRequest|'
                      r'Net::HTTP|LWP::|webbrowser')
URL_ARG = re.compile(r'^(https?|ftp|mailto|sms|tel):', re.I)
FILE_FLAGS = {'--body-file', '-F', '--input', '-T', '--upload-file', '--attach'}
STDIN_PROGRAMS = {'ssh', 'nc', 'ncat', 'netcat', 'telnet', 'mail', 'mailx', 'sendmail', 'msmtp',
                  'mutt', 'websocat'}  # they send what a pipe hands them without a flag
GITHUB_HOSTS = ('github.com', 'githubusercontent.com', 'githubassets.com', 'github.io')
GITHUB_PROGRAMS = {'git', 'gh'}
HTTP_CLIENTS = {'curl', 'wget', 'http', 'https', 'xh'}
LOCAL_MCP = ('mcp__ccd_', 'mcp__visualize__', 'mcp__Claude_Code_iOS_Simulator__',
             'mcp__terminal__', 'mcp__scheduled-tasks__list', 'mcp__mcp-registry__')
CLOUD_CCD = ('mcp__ccd_session__move_to_cloud',)
WEB_TOOLS = {'WebFetch': ('url',), 'WebSearch': ('query',)}
# Codex's web search and page opening: `webrun` measured 2026-10-25; the bundled binary names
# the tool `web.run`, so that spelling is judged too
CODEX_WEB = {'webrun', 'web.run'}
ARTIFACT_TOOLS = {'ArtifactData', 'ArtifactComments'}
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}')
LOCAL_CHARS = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._%+-')
AT_DOMAIN = re.compile(r'@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,10}\.[A-Za-z]{2,63}')
URL = re.compile(r'(?:https?|wss?|ftp)://[^\s"\'<>)\]}]+', re.I)
NOT_PERSONAL = re.compile(
    r'^(?:no-?reply|do-?not-?reply|git|noreply\+.*)$|'      # local parts
    r'(?:^|\.)(?:example\.(?:com|org|net)|[a-z0-9-]+\.(?:example|test|invalid|localhost|local|'
    r'lan|internal|home))$|users\.noreply\.github\.com$', re.I)
FILE_TLDS = {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'js', 'mjs', 'ts', 'css', 'json',
             'md', 'py', 'rs', 'txt', 'gz', 'zip', 'tar', 'toml', 'yaml', 'yml', 'html', 'glb',
             'gltf', 'blend', 'wasm', 'lock', 'sh', 'log', 'ktx2', 'ron', 'wgsl', 'jsonl',
             # systemd units: `user@1000.service`, `user-1000.slice/…`
             'service', 'socket', 'target', 'timer', 'slice', 'scope', 'mount'}
MAX_FILE = 2_000_000


def emails(text):
    """The e-mail addresses in text. EMAIL.finditer is quadratic on a long run of address
    characters (a 300 kB minified page took 40 s), so the scan starts from each `@`."""
    at = text.find('@')
    while at != -1:
        m = AT_DOMAIN.match(text, at)
        start = at
        while m and start > max(0, at - 64) and text[start - 1] in LOCAL_CHARS:
            start -= 1
        if m and start < at:
            yield text[start:m.end()]
        at = text.find('@', at + 1)


def _boundary(core):
    return r'(?<![A-Za-z0-9])' + core + r'(?![A-Za-z0-9])'


def _run(args):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=4,
                           stdin=subprocess.DEVNULL)
        return r.stdout if r.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def identifiers():
    """[(label, pattern, is_login)] for the user's identifiers, read now; empty when none are set."""
    found = []
    config = _run(['git', 'config', '--global', '--get-regexp', r'^user\.(name|email)$'])
    for line in config.splitlines():
        key, _, value = line.partition(' ')
        value = value.strip()
        if key == 'user.email' and '@' in value:
            found += _email_patterns(value, "the user's e-mail address (git user.email)")
        elif key == 'user.name' and value:
            found += _name_patterns(value, "the user's name (git user.name)")
    login = _run(['gh', 'config', 'get', 'user', '-h', 'github.com']).strip()
    if len(login) >= 3:
        found.append(("the user's GitHub login (gh)", re.compile(_boundary(re.escape(login)), re.I),
                      True))
    account = os.path.basename(os.path.expanduser('~'))
    if len(account) >= 6:
        found.append(("the user's account name", re.compile(_boundary(re.escape(account)), re.I),
                      False))
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    try:
        lines = open(os.path.join(base, 'agentic-github-flow', 'personal-data'), encoding='utf-8')
        lines = lines.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        kind, sep, value = line.partition(':')
        kind, value = (kind.strip().lower(), value.strip()) if sep and kind.strip().lower() in (
            'email', 'phone', 'name', 'text') else ('text', line)
        label = "the user's %s (local personal-data file)" % {
            'email': 'e-mail address', 'phone': 'phone number', 'name': 'name'}.get(kind, 'data')
        if kind == 'email' or (kind == 'text' and EMAIL.fullmatch(value)):
            found += _email_patterns(value, label)
        elif kind == 'phone':
            digits = re.sub(r'\D', '', value)
            if len(digits) >= 7:
                # the last eight digits, so +32 470 … and 0470/… both match; whatever precedes
                tail = digits[-8:]
                found.append((label, re.compile(r'[\s./()-]*'.join(tail) + r'(?!\d)'), False))
        elif kind == 'name':
            found += _name_patterns(value, label)
        elif len(value) >= 3:
            found.append((label, re.compile(_boundary(re.escape(value)), re.I), False))
    return found


def _email_patterns(address, label):
    local, _, domain = address.partition('@')
    pats = [(label, re.compile(re.escape(local) + '@' + re.escape(domain), re.I), False)]
    if len(local) >= 6 and not NOT_PERSONAL.search(local):
        pats.append((label.replace('e-mail address', 'e-mail name', 1),
                     re.compile(_boundary(re.escape(local)), re.I), False))
    return pats


def _name_patterns(name, label):
    parts = [p for p in re.split(r'\s+', name.strip()) if p]
    pats = []
    if len(parts) >= 2:
        sep = r'[\s+._-]+'
        pats.append((label, re.compile(_boundary(sep.join(map(re.escape, parts))), re.I), False))
    if len(parts) >= 2 and len(parts[-1]) >= 4:
        # the surname alone identifies the user; the first name alone is routine ("X's ruling")
        pats.append((label.replace('name', 'surname', 1),
                     re.compile(_boundary(re.escape(parts[-1])), re.I), False))
    return pats


# --- which Bash commands reach the network -------------------------------------------------

def segments(text, depth=0):
    """[(programs, text)] for every part of a shell command that reaches the network: a simple
    command with its arguments, or a here-document body with the programs that read it."""
    if depth > 8:
        return []
    text, bodies = gg.strip_heredocs(text.replace('\\\n', ' '))
    found = []
    for line, body in bodies:
        readers = {gg.base(w) for w in re.findall(r'[\w./-]+', line)}
        if readers & gg.SHELLS:
            found += segments(body, depth + 1)
        elif readers & gg.INTERPRETERS and NET_CODE.search(body):
            found.append(({'interpreter'}, body))
        else:
            programs = set().union(*[p for p, _ in segments(line, depth + 1)])
            if programs:
                found.append((programs, body))
    for inner in gg.substitutions(text):
        found += segments(inner, depth + 1)
    try:
        commands = list(piped_commands(text))
    except ValueError:
        words = set(re.findall(r'[\w.-]+', text))
        programs = (words & NET_PROGRAMS) | ({'git'} if 'git' in words and words & GIT_NET
                                             else set())
        return found + ([(programs, text)] if programs else [])
    for tokens, piped in commands:
        programs = command_programs(tokens, depth)
        if programs:
            found.append((programs, shlex.join(tokens)))
            if piped and (programs & STDIN_PROGRAMS or any(
                    t in ('-', '@-') or t.endswith(('=-', '=@-')) for t in tokens)):
                found.append((programs, text))  # `echo … | curl -d @-`: the pipe is sent
        if gg.base(tokens[0]) in gg.SHELLS and all(t.startswith('-') for t in tokens[1:]):
            # a shell reading its commands from a pipe: `echo curl … | bash`
            programs = set(re.findall(r'[\w.-]+', text)) & NET_PROGRAMS
            if programs:
                found.append((programs, text))
    return found


def piped_commands(text):
    """(tokens, piped) per simple command, as gg.split_commands, with whether a pipe feeds it."""
    lex = shlex.shlex(text, posix=True, punctuation_chars=';&|(){}\n')
    lex.whitespace = ' \t\r'
    lex.whitespace_split = True
    lex.commenters = ''
    current, piped, sep = [], False, ''
    for tok in lex:
        if tok and set(tok) <= gg.SEPARATORS:
            if current:
                yield current, piped
            current, sep = [], tok
        else:
            if not current:
                piped = sep in ('|', '|&')
            current.append(tok)
    if current:
        yield current, piped


def net_programs(text, depth=0):
    """The network programs a shell command runs, as a set of names."""
    return set().union(*[p for p, _ in segments(text, depth)])


def command_programs(tokens, depth):
    while tokens and (gg.ASSIGN.fullmatch(tokens[0]) or gg.base(tokens[0]) in gg.KEYWORDS):
        tokens = tokens[1:]
    if not tokens:
        return set()
    name, args = gg.base(tokens[0]), tokens[1:]
    if name in NET_PROGRAMS:
        return {name}
    if name == 'git':
        i = 0
        while i < len(args) and args[i].startswith('-'):
            i += 2 if args[i] in gg.GIT_VALUE_OPTS else 1
        return {'git'} if i < len(args) and args[i] in GIT_NET else set()
    if name in PUBLISHERS:
        return {name} if PUBLISH_WORDS & set(args) else set()
    if name in ('open', 'xdg-open'):
        return {name} if any(URL_ARG.match(a) for a in args) else set()
    if name in gg.SHELLS:
        for j, tok in enumerate(args):
            if re.fullmatch(r'-[a-z]*c[a-z]*', tok) and j + 1 < len(args):
                return net_programs(args[j + 1], depth + 1)
            if tok.startswith('<<<'):
                return net_programs(tok[3:] or ' '.join(args[j + 1:j + 2]), depth + 1)
        return set()
    if name in gg.INTERPRETERS:
        for j, tok in enumerate(args):
            if tok in ('-c', '-e') and j + 1 < len(args) and NET_CODE.search(args[j + 1]):
                return {name}
        return set()
    if name == 'eval':
        return net_programs(' '.join(args), depth + 1)
    if name in gg.WRAPPERS:
        runs = NET_PROGRAMS | PUBLISHERS | gg.SHELLS | gg.INTERPRETERS | gg.WRAPPERS | {
            'git', 'eval', 'open'}
        for j, tok in enumerate(args):
            if gg.base(tok) in runs:
                return command_programs(args[j:], depth + 1)
    return set()


def handed_files(command, cwd):
    """Contents of the files an outbound command hands over (`--body-file x`, `@x`, `-T x`)."""
    try:
        tokens = [t for c in gg.split_commands(gg.strip_heredocs(command)[0]) for t in c]
    except ValueError:
        return []
    paths = []
    for i, tok in enumerate(tokens):
        if tok in FILE_FLAGS and i + 1 < len(tokens) and not (tok == '-F' and '=' in tokens[i + 1]):
            paths.append(tokens[i + 1])  # `gh api -F key=value` is a field, not a file
        if tok == '<' and i + 1 < len(tokens):
            paths.append(tokens[i + 1])
        elif tok.startswith('<') and not tok.startswith('<<'):
            paths.append(tok[1:])
        if tok.startswith('@'):
            paths.append(tok[1:])
        elif '=@' in tok:
            paths.append(tok.split('=@', 1)[1].split(';', 1)[0])
        elif tok.startswith('--body-file=') or tok.startswith('--input='):
            paths.append(tok.split('=', 1)[1])
    texts = []
    for p in paths:
        if not p or p == '-':
            continue
        p = os.path.join(cwd or '.', os.path.expanduser(p))
        try:
            if os.path.isfile(p) and os.path.getsize(p) <= MAX_FILE:
                texts.append(open(p, encoding='utf-8', errors='replace').read())
        except OSError:
            pass
    return texts


# --- the decision --------------------------------------------------------------------------

def strings(value, skip=('mcp_server',)):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in skip:
                yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def outbound(tool, tool_input, cwd):
    """(what leaves, [(programs, text)]) or None when the call stays on the machine. programs
    is the set of network programs that send the text; empty for a non-shell tool."""
    if not isinstance(tool_input, dict):
        return None
    if tool == 'Bash' or tool.endswith('__run_in_terminal'):
        command = tool_input.get('command')
        if isinstance(command, list):
            command = ' '.join(shlex.quote(str(c)) for c in command)
        if not isinstance(command, str):
            return None
        segs = segments(command)
        if not segs:
            return None
        segs += [(p, f) for p, t in segs for f in handed_files(t, cwd)]
        return 'this %s command' % '/'.join(sorted(set().union(*[p for p, _ in segs]))), segs
    if tool in WEB_TOOLS:
        return 'this %s' % tool, [(set(), str(tool_input.get(k) or '')) for k in WEB_TOOLS[tool]]
    if tool == 'Artifact':
        if (tool_input.get('action') or 'publish') != 'publish':
            return None
        texts = [str(tool_input.get(k) or '') for k in ('title', 'description', 'label')]
        sources = [tool_input.get('file_path')] + list(tool_input.get('file_paths') or [])
        files = tool_input.get('files')
        if isinstance(files, dict):
            sources += [v if isinstance(v, str) else (v or {}).get('from')
                        for v in files.values()]
        elif isinstance(files, list):
            sources += [(f or {}).get('path') for f in files]
        for src in sources:
            if isinstance(src, str):
                p = os.path.join(cwd or '.', os.path.expanduser(src))
                try:
                    if os.path.getsize(p) <= MAX_FILE:
                        texts.append(open(p, encoding='utf-8', errors='replace').read())
                except OSError:
                    pass
        return 'this Artifact publish', [(set(), t) for t in texts]
    if tool in ARTIFACT_TOOLS or tool in CODEX_WEB or (tool.startswith('mcp__') and (
            tool.startswith(CLOUD_CCD) or not tool.startswith(LOCAL_MCP))):
        return 'this %s call' % tool, [(set(), t) for t in strings(tool_input)]
    return None


def home_routine(text):
    """Remove the forms in which the account name is only part of a path."""
    home = os.path.expanduser('~')
    account = os.path.basename(home)
    if len(account) < 3:
        return text
    text = text.replace(home, '~')
    return re.sub(r'(/Users/|/home/|-Users-|~)' + re.escape(account) + r'(?![A-Za-z0-9])', r'\1~',
                  text, flags=re.I)


def is_github(host):
    return any(host == g or host.endswith('.' + g) for g in GITHUB_HOSTS)


def only_github(programs, text):
    """True when this text reaches GitHub alone: through git or gh, or by URLs all GitHub's."""
    if programs:
        if programs <= GITHUB_PROGRAMS:
            return True
        if programs - HTTP_CLIENTS:
            return False
    hosts = [(urlsplit(u).hostname or '').lower() for u in URL.findall(text)]
    return bool(hosts) and all(is_github(h) for h in hosts)


GIT_EXEMPT = {'push', 'fetch', 'pull', 'clone', 'ls-remote'}
SCP_LIKE = re.compile(r'^(?:[^@/\s]+@)?([^:/\s]+):(?!//)')


def remotes(where):
    try:
        r = subprocess.run(['git', '-C', where or '.', 'remote'], capture_output=True, text=True,
                           timeout=4, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(r.stdout.split()) if r.returncode == 0 else set()


def git_to_known_remote(text, cwd):
    """True when this git command talks only to a remote configured in the repository, a local
    path or GitHub: then the user's configured identity on it is outside the rule. Any other
    host, and git commands that mail or publish (send-email, request-pull, archive --remote),
    are judged like every other outbound command."""
    try:
        tokens = shlex.split(text)
    except ValueError:
        return False
    at = next((i for i, t in enumerate(tokens) if gg.base(t) == 'git'), None)
    if at is None:
        return False
    args, where, i = tokens[at + 1:], cwd, 0
    while i < len(args) and args[i].startswith('-'):
        if args[i] == '-C' and i + 1 < len(args):
            where = os.path.join(where or '.', os.path.expanduser(args[i + 1]))
        i += 2 if args[i] in gg.GIT_VALUE_OPTS else 1
    if i >= len(args) or args[i] not in GIT_EXEMPT:
        return False
    sub = args[i]
    words = [a for a in args[i + 1:] if not a.startswith('-')]
    if not words:
        return sub != 'clone'  # the configured default remote
    target = words[0]
    if '://' in target:
        return is_github((urlsplit(target).hostname or '').lower()) or target.startswith('file://')
    scp = SCP_LIKE.match(target)
    if scp and not os.path.exists(os.path.join(where or '.', target)):
        return is_github(scp.group(1).lower())
    if target.startswith(('/', '.', '~')) or os.path.isdir(os.path.join(where or '.', target)):
        return True  # a local path: nothing leaves the machine
    return sub != 'clone' and target in remotes(where)


def mask(address):
    local, _, domain = address.partition('@')
    return '%s…@….%s' % (local[:1], domain.rsplit('.', 1)[-1])


def judge(event):
    """(what leaves, what it carries) when the user must confirm the call, or None."""
    cwd = event.get('cwd') or ''
    tool = event.get('tool_name') or ''
    found = outbound(tool, event.get('tool_input'), cwd)
    if not found:
        return None
    what, segs = found
    hits = []
    texts = []
    exempt = []
    ids = identifiers()
    for programs, text in segs:
        if not text:
            continue
        text = home_routine(text)
        decoded = unquote(text) if '%' in text else text  # a URL sends `%40` for `@`
        texts.append(decoded)
        if programs and programs <= {'git'} and git_to_known_remote(text, cwd):
            exempt.append(decoded)
            continue  # the configured identity on commits and pushes is outside the rule
        github = only_github(programs, text)
        for label, pattern, is_login in ids:
            if not (is_login and github) and label not in hits and pattern.search(decoded):
                hits.append(label)
    own = [pattern for label, pattern, _ in ids if 'e-mail address' in label]
    others = []
    if not hits:
        for t in texts:
            for address in emails(t):
                if t in exempt and any(p.fullmatch(address) for p in own):
                    continue  # the user's own address in a git command: the configured identity
                local, _, domain = address.partition('@')
                if NOT_PERSONAL.search(local) or NOT_PERSONAL.search(domain) or \
                        domain.rsplit('.', 1)[-1].lower() in FILE_TLDS:
                    continue
                if mask(address) not in others:
                    others.append(mask(address))
    hits = [h for h in hits if h.replace('e-mail name', 'e-mail address', 1) not in hits
            or 'e-mail name' not in h]
    if not hits and not others:
        return None
    parts = hits + ['an e-mail address (%s): someone\'s personal data' % ', '.join(others[:3])
                    if others else '']
    return what, '; '.join(p for p in parts if p)


def claude_reason(what, carried):
    return ('Personal-data check (agentic-github-flow rules, §Git): %s would send %s off the '
            'machine. Approve only if you confirm sending it.' % (what, carried))


def codex_reason(what, carried, shell):
    then = ('give them the exact command to run in their own terminal' if shell else
            'tell them exactly what to send where, so that they can do it themselves')
    return ('Blocked by the personal-data check (agentic-github-flow rules, §Git): %s would send '
            '%s off the machine. Do not retry it in another form or split it up. Tell the user in '
            'the conversation which data would go to which recipient and ask their explicit '
            'confirmation; if they confirm, %s. Codex cannot let this call through on an '
            'approval: no flag, variable, file or escalation unlocks it.' % (what, carried, then))


def main(argv):
    codex = argv == ['--codex']
    if argv and not codex:
        sys.stderr.write('usage: pre_tool_personal_data.py [--codex] < PreToolUse JSON\n')
        return 0  # a wiring mistake must not stop all work either
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return 0
    except ValueError:
        return 0
    try:
        found = judge(event)
    except Exception:
        # Deliberate, as in the git guard: a guard that fails on an input it cannot read must
        # not stop all work. The written rule still binds.
        return 0
    if not found:
        return 0
    if codex:
        tool = event.get('tool_name') or ''
        shell = tool == 'Bash' or tool.endswith('__run_in_terminal')
        decision, reason = 'deny', codex_reason(*found, shell)
    else:
        decision, reason = 'ask', claude_reason(*found)
    json.dump({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                      'permissionDecision': decision,
                                      'permissionDecisionReason': reason}}, sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
