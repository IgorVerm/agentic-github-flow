#!/usr/bin/env python3
"""The project's tools for a Codex job: each served from a sandbox of its own (issue #116).

Usage (inside Codex's sandbox, by Codex):  python3 -I codex_tools.py call <tool> [argument ...]
       (by codex_worker.py only)           codex_tools.py serve <job> <turn> <tool spec>
       (by ssh, as its ProxyCommand)       codex_tools.py connect <host> <port>

Codex's own sandbox cannot run what a model maker needs: Blender dies on its first Metal call
there (Codex's seatbelt policy is fixed and grants no GPU; a permission profile sets only files,
network and unix sockets), and it has no network for the Spark. An execpolicy `allow` rule would
lift the command out of every sandbox, with the arguments unchecked. So a project declares a fixed
list of tools, and while a turn runs the worker serves each listed tool from a sandbox it makes
itself with `sandbox-exec`: deny by default; the job's four folders the only writable ones; the
worker's whole read deny list; no network. On top of that only the tool's own grants:

- `gpu`: the Metal device (`AGXDeviceUserClient`, `IOSurfaceRootUserClient`), Metal's compiler
  service, LaunchServices' lookup (Metal asks it for the program's identity), and the issue of a
  read-write sandbox extension for Metal's shader cache folders under the user's Darwin cache
  folder (`<cache>/<bundle id>/com.apple.metal`, `…metalfe`, `…gpuarchiver`), which the compiler
  service writes. Measured 2026-11-22 with Blender 5.1.2: GLB export, EEVEE and Cycles renders.
  Opening an app (`lsopen`) and Apple Events stay denied (measured: `open` and `osascript` to
  Finder fail).
- `network`: `host:port` entries. The sandbox has no network; the tool reaches only a unix socket
  of the worker's, behind which the worker connects to that one host and port (`/usr/bin/nc`,
  outside every sandbox, handing bytes through without reading them). An ssh tool gets it the way
  Claude Code's sandbox hands it over: `SANDBOX_RUNTIME=1` and `SRT_SSH_PROXY_COMMAND`, a shell
  snippet that takes the host and port as `$1` and `$2` and here runs `codex_tools.py connect`.
- `unix_sockets`: paths the tool may connect to, such as a dedicated ssh agent.

**The list** is the project's file `.agents/codex-tools.json` in the worktree the worker is given
(the chat's), read inside Codex's sandbox. Codex cannot change it: its sandbox protects `.agents`
in its folder, and the import refuses a bundle that touches it. The chat can, so the list grants
nothing on its own; each tool is served only with two anchors in Claude Code's own settings, so a
tool never reaches further than a Claude chat's route for the same command:

- its command line (`shlex.join` of the command and the call's arguments) matches a `Bash(...)`
  allow rule of the person's, the managed or the project's Claude Code settings, and no deny or
  ask rule; checked when the turn starts (the command's start) and again for every call;
- each `network` host and `unix_sockets` path is in `sandbox.network.allowedDomains` (the host,
  or the host and port, no wildcard) and `sandbox.network.allowUnixSockets` of the person's or the
  managed settings: files the chat's sandbox cannot write. A project's network settings are not
  read (Igor, 2026-11-22, on #116: a project never widens them). Where the managed settings set
  `allowManagedPermissionRulesOnly` or `allowManagedDomainsOnly`, only their rules or domains
  count, as in Claude Code.

What the anchors bind: the command rule binds an honest chat; a hostile chat can name a worktree
whose project settings it wrote, so against it the bound is the tool's sandbox, the person's deny
and ask rules, and the network grants, which only the person's settings give. The `gpu` grant
has no anchor: Claude Code's sandbox gives no GPU, so a listed `gpu` tool reaches the Metal
device, its compiler service and LaunchServices' lookup, which a sandboxed Claude chat cannot.

    {"tools": [{"name": "blender",
                "command": ["/Applications/Blender.app/Contents/MacOS/Blender", "--background"],
                "grants": ["gpu"], "time_limit_minutes": 30,
                "description": "Blender headless: --python <builder> [-- args]"},
               {"name": "remote-shot", "command": ["tools/qa/remote_shot.sh"],
                "network": ["gpu-box.local:22"],
                "unix_sockets": ["~/.local/state/gpu-box-ssh/agent.sock"],
                "env": {"PAX_DATA_DIR": "{tmp}/pax-data"}}]}

`name` is lowercase letters, digits and `-`; `command` the fixed start of the command line,
whose program is absolute, on PATH, or a path in Codex's folder (`<job>/work`, so a project script
runs as Codex has it: the sandbox, not the script, is the boundary); `env` values may name
`{work}`, `{tmp}` and `{out}` of the job (a game's data folder goes there: the sandbox refuses the
person's real one anyway; `PATH`, `GIT_*`, `TMPDIR`, `DYLD_*`, `PYTHON*` and the route's names
are refused); `time_limit_minutes` (default 30, at most 240) limits one call. Every tool also gets
what Codex's commands get: `GIT_DIR`, `GIT_WORK_TREE` and `TMPDIR` of the job, and the turn's
marker; of the person's environment only `ENV_KEEP` and `LC_*` (no token, key or
`SSH_AUTH_SOCK`). The job's four folders enter the profile by the job's path and the fixed names,
never resolved below the job, and the worker refuses a job where one is not a folder. A rule is matched against the shell-quoted command line, so a program whose path holds a
space needs a rule that quotes it (`Bash('/a b/tool' *)`).

**What runs Codex's code.** A tool runs what Codex wrote whenever its arguments name it (Blender
runs a builder; a project script runs as Codex left it). The bound is the tool's sandbox: it
writes only the job, reads the disk except the deny list, and reaches nothing else but its grants.

**The route of a call.** `call` (in Codex's sandbox) writes a request into
`<job>/out/tools/<turn>/<tool>/` (a folder per turn, so nothing of an earlier turn is read or
run) and waits; `serve` (one per tool, in the tool's sandbox, started by the worker for the turn)
reads it, checks the command line against the anchors again, runs the tool in `<job>/work` (or
the caller's folder below it) with output to `<id>.log`, and writes `<id>.done`; the call prints
the log and removes its files. Calls to one tool run one after another. A call waits up to 30 s
for its server to start, stops waiting (exit 125) when the server's `ready` file has not been
touched for 20 s (it touches it every 2 s while it lives), and stops waiting (exit 124) when no
result comes within the tool's limit and 2 minutes.
The worker outside every sandbox opens none of these files (method.md *Codex as the worker*, issue
#107): it starts the servers with fixed arguments and kills them, by the turn's marker, when the
turn ends. A tool not in the list has no server, so its call is refused; a call whose command line
the anchors do not allow is refused by the server (exit 126). Codex's own sandbox stays as it was.
A tool's process that leaves its group and drops its environment outlives the turn inside its
sandbox, with its grants (the GPU, its unix sockets; its forwarder ends with the turn): the kill
is hygiene, as for Codex's own leftovers.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

SANDBOX_EXEC = '/usr/bin/sandbox-exec'
NC = '/usr/bin/nc'
LIST_PATH = os.path.join('.agents', 'codex-tools.json')
LIST_MAX = 64 * 1024
REQUEST_MAX = 256 * 1024
NAME_RE = re.compile(r'^[a-z][a-z0-9-]{0,31}$')
ID_RE = re.compile(r'^[0-9a-f]{32}$')
HOST_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.-]{0,252}:[0-9]{1,5}$')
ENV_RE = re.compile(r'^[A-Z_][A-Z0-9_]{0,63}$')
# Names a list may not set: the job's, the route's and the loader's.
ENV_RESERVED = re.compile(r'^(GIT_.*|TMPDIR|TMP|TEMP|PATH|DYLD_.*|SANDBOX_RUNTIME|SRT_.*|AGF_.*|'
                          r'CODEX_WORKER_TURN|PYTHON.*)$')
GRANTS = ('gpu',)
PARTS = ('work', 'git', 'tmp', 'out')
FORWARDS_MAX = 16  # live connections of a turn, over all its network grants
# What a tool keeps of the person's environment: no tokens or keys (Codex's own commands drop
# *KEY* and *TOKEN* too), no SSH_AUTH_SOCK; the job's variables and the list's `env` come on top.
ENV_KEEP = ('HOME', 'USER', 'LOGNAME', 'SHELL', 'TERM', 'PATH', 'LANG', '__CF_USER_TEXT_ENCODING')
LIMIT_DEFAULT, LIMIT_MAX = 30, 240
TOOLS_MAX, ARGS_MAX, ARG_MAX = 32, 256, 4096
POLL = 0.2
REFUSED = 126
TIMED_OUT = 124
READY_SECONDS = 30   # how long a call waits for its tool's server to start
GRACE_SECONDS = 120  # past the tool's limit, a call stops waiting for its result
BEAT_SECONDS = 2     # a server touches its ready file this often
STALE_SECONDS = 20   # a ready file untouched this long: the server is gone
GONE = 125

# The base of every tool's sandbox: deny by default, then what a process needs to start and run
# Python, a shell, git, ssh and rsync and read files; modelled on Codex's own seatbelt policy
# (itself after Chrome's) and measured with sandbox-exec on macOS (2026-11-22).
BASE = r'''(version 1)
(deny default)
(allow process-exec process-fork)
(allow signal (target same-sandbox))
(allow process-info* (target same-sandbox))
(allow sysctl-read)
(allow sysctl-write (sysctl-name "kern.grade_cputype"))
(allow iokit-open (iokit-registry-entry-class "RootDomainUserClient"))
(allow ipc-posix-sem)
(allow ipc-posix-shm-read-data ipc-posix-shm-write-create ipc-posix-shm-write-unlink
  (ipc-posix-name-regex #"^/__KMP_REGISTERED_LIB_[0-9]+$"))
(allow ipc-posix-shm-read* (ipc-posix-name-prefix "apple.cfprefs."))
(allow ipc-posix-shm-read* (ipc-posix-name "apple.shm.notification_center"))
(allow mach-lookup
  (global-name "com.apple.analyticsd")
  (global-name "com.apple.analyticsd.messagetracer")
  (global-name "com.apple.bsd.dirhelper")
  (global-name "com.apple.cfprefsd.agent")
  (global-name "com.apple.cfprefsd.daemon")
  (global-name "com.apple.diagnosticd")
  (global-name "com.apple.logd")
  (global-name "com.apple.logd.events")
  (global-name "com.apple.PowerManagement.control")
  (global-name "com.apple.system.DirectoryService.libinfo_v1")
  (global-name "com.apple.system.logger")
  (global-name "com.apple.system.notification_center")
  (global-name "com.apple.system.opendirectoryd.libinfo")
  (global-name "com.apple.system.opendirectoryd.membership")
  (global-name "com.apple.trustd")
  (global-name "com.apple.trustd.agent")
  (local-name "com.apple.cfprefsd.agent"))
(allow user-preference-read)
(allow pseudo-tty)
(allow file-read* file-write* file-ioctl (literal "/dev/ptmx"))
(allow file-read* file-write* file-ioctl
  (require-all (regex #"^/dev/ttys[0-9]+$") (extension "com.apple.sandbox.pty")))
(allow file-read* file-write-data file-ioctl
  (literal "/dev/null") (literal "/dev/zero") (literal "/dev/tty") (literal "/dev/dtracehelper"))
(allow file-read* file-write-data (subpath "/dev/fd"))
(allow system-mac-syscall (mac-policy-name "vnguard"))
(allow system-mac-syscall (require-all (mac-policy-name "Sandbox") (mac-syscall-number 67)))
(allow system-fsctl (fsctl-command FSIOC_CAS_BSDFLAGS))
(allow file-read*)
'''

# The `gpu` grant (measured with Blender 5.1.2, 2026-11-22; the header says what each part is).
GPU = r'''(allow iokit-open-user-client
  (iokit-user-client-class "AGXDeviceUserClient")
  (iokit-user-client-class "IOSurfaceRootUserClient"))
(allow mach-lookup (xpc-service-name "com.apple.MTLCompilerService")
  (global-name "com.apple.coreservices.launchservicesd"))
(allow file-issue-extension (require-all
  (extension-class "com.apple.app-sandbox.read-write")
  (regex #"^%s/[^/]+/com\.apple\.(metal|metalfe|gpuarchiver)(/.*)?$")))
'''


# --- the tool's sandbox ------------------------------------------------------------------------

def cache_dir():
    """The user's Darwin cache folder (confstr _CS_DARWIN_USER_CACHE_DIR, 65538), real path;
    None when there is none (as on every system but macOS). Python's os.confstr does not know
    the name."""
    if sys.platform != 'darwin':
        return None
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        buffer = ctypes.create_string_buffer(1024)
        if not 0 < libc.confstr(65538, buffer, 1024) <= 1024:
            return None
        path = os.path.realpath(buffer.value.decode())
    except (OSError, AttributeError, UnicodeDecodeError):
        return None
    return path if os.path.isabs(path) and path != '/' else None


def sb_string(value):
    return '"%s"' % value.replace('\\', '\\\\').replace('"', '\\"')


def sb_regex(pattern):
    return '#"%s"' % pattern.replace('"', '\\"')


def glob_regex(name):
    return ''.join('[^/]*' if char == '*' else re.escape(char) for char in name)


def both_forms(path):
    """The path and its real path (`/tmp/x` is `/private/tmp/x`)."""
    return sorted({path, os.path.realpath(path)})


def deny_reads(denied):
    """The worker's read deny list: `/**/<name>` anywhere (the name may hold `*`), else a path
    with all below it; denied for reads and writes, after every allow, so it wins."""
    lines = []
    for entry in denied:
        if entry.startswith('/**/'):
            pattern = '^(.*/)?%s(/.*)?$' % glob_regex(entry[4:])
            lines.append('(deny file-read* file-write* (regex %s))' % sb_regex(pattern))
        else:
            lines += ['(deny file-read* file-write* (subpath %s))' % sb_string(path)
                      for path in both_forms(entry)]
    return '\n'.join(lines) + '\n'


def job_forms(job):
    """The job's four folders, by the job's path and its real path joined with the fixed names.
    Never a real path below the job: Codex and every tool write those folders, so a link put in
    place of one would otherwise make its target writable for the next turn's tools."""
    return [os.path.join(top, part) for top in both_forms(job) for part in PARTS]


def profile(job_folders, denied, grants=(), sockets=()):
    """The seatbelt profile of one tool: BASE, the job's folders writable (as given, unresolved),
    the grants, the unix sockets it may connect to, then the deny list."""
    text = BASE
    text += ''.join('(allow file-write* (subpath %s))\n' % sb_string(folder)
                    for folder in job_folders)
    if 'gpu' in grants:
        text += GPU % re.escape(cache_dir() or '/nonexistent')
    if sockets:
        text += '(allow system-socket (socket-domain AF_UNIX))\n'
        text += ''.join('(allow network-outbound (remote unix-socket (path-literal %s)))\n'
                        % sb_string(path) for socket_path in sockets
                        for path in both_forms(socket_path))
    text += deny_reads(denied)
    return text


# --- the anchors: Claude Code's own rules -------------------------------------------------------

def bash_patterns(rules):
    """The bodies of `Bash(...)` rules; a bare `Bash` is everything (`*`)."""
    found = []
    for rule in rules if isinstance(rules, list) else []:
        if rule == 'Bash':
            found.append('*')
        elif isinstance(rule, str) and rule.startswith('Bash(') and rule.endswith(')'):
            found.append(rule[5:-1])
    return found


def normal(pattern):
    """The legacy `prefix:*` is Claude Code's `prefix *`: the prefix as a whole word."""
    return pattern[:-2] + ' *' if pattern.endswith(':*') else pattern


def pattern_regex(pattern):
    """Claude Code's Bash rule as a regex over the command line: `*` any text, a trailing ` *`
    (or the legacy `:*`) also the bare command."""
    pattern = normal(pattern)
    body = ''.join('.*' if char == '*' else re.escape(char) for char in pattern)
    if pattern.endswith(' *'):
        body = ''.join('.*' if char == '*' else re.escape(char) for char in pattern[:-2])
        body += '( .*)?'
    return re.compile(body, re.S)


def matches(pattern, line):
    return pattern_regex(pattern).fullmatch(line) is not None


def literal_start(pattern):
    head = normal(pattern).split('*', 1)[0]
    return head.rstrip()


def may_match(pattern, start):
    """Could a command line that begins with `start` match the pattern? For the check at the
    start of the turn; every call is matched in full."""
    head = literal_start(pattern)
    return head.startswith(start) or start.startswith(head) or matches(pattern, start)


def expand(path, home):
    return os.path.join(home, path[2:]) if path.startswith('~/') else path


def check_tools(listed, rules, network, home):
    """Validate the project's list and anchor each tool. listed: the parsed codex-tools.json;
    rules: {'allow': [...], 'deny': [...]} Bash patterns of every settings source (ask counts as
    deny: no one can be asked); network: {'domains': [...], 'sockets': [...]} of the person's and
    the managed settings. Returns (served specs, refused [{name, reason}])."""
    served, refused = [], []
    tools = listed.get('tools') if isinstance(listed, dict) else None
    if not isinstance(tools, list) or len(tools) > TOOLS_MAX:
        return [], [{'name': None, 'reason': '%s holds no list "tools" of at most %d tools'
                     % (LIST_PATH, TOOLS_MAX)}]
    domains = {str(entry).lower() for entry in network.get('domains', []) if isinstance(entry, str)}
    # The person's entries, by their text with ~ expanded, to their real path. The list's entries
    # are the chat's: compared as text, never resolved here (no link of the chat's is followed).
    sockets = {os.path.normpath(expand(entry, home)): os.path.realpath(expand(entry, home))
               for entry in network.get('sockets', [])
               if isinstance(entry, str) and (entry.startswith('/') or entry.startswith('~/'))}
    seen = set()
    for tool in tools:
        name = tool.get('name') if isinstance(tool, dict) else None
        reason = tool_problem(tool, seen)
        if reason is None:
            start = shlex.join(tool['command'])
            allow = [p for p in rules.get('allow', []) if may_match(p, start)]
            deny = [p for p in rules.get('deny', []) if may_match(p, start)]
            if not allow:
                reason = 'no Bash allow rule of the Claude Code settings covers %r' % start
            elif any(matches(p, start) for p in deny):
                reason = 'a Bash deny or ask rule covers %r' % start
        if reason is None:
            for entry in tool.get('network', []):
                host = entry.rsplit(':', 1)[0].lower()
                if entry.lower() not in domains and host not in domains:
                    reason = ('network %s is not in sandbox.network.allowedDomains of the '
                              'person\'s or the managed settings' % entry)
        if reason is None:
            for entry in tool.get('unix_sockets', []):
                if os.path.normpath(expand(entry, home)) not in sockets:
                    reason = ('unix socket %s is not in sandbox.network.allowUnixSockets of the '
                              'person\'s or the managed settings' % entry)
        if reason is not None:
            refused.append({'name': name if isinstance(name, str) else None, 'reason': reason})
            if isinstance(name, str):
                seen.add(name)  # a second tool of that name is refused too
            continue
        seen.add(name)
        served.append({
            'name': name, 'command': list(tool['command']), 'allow': allow, 'deny': deny,
            'grants': sorted(set(tool.get('grants', []))),
            'network': list(tool.get('network', [])),
            'unix_sockets': [sockets[os.path.normpath(expand(e, home))]
                             for e in tool.get('unix_sockets', [])],
            'env': dict(tool.get('env', {})),
            'time_limit_minutes': tool.get('time_limit_minutes', LIMIT_DEFAULT),
            'description': tool.get('description', '')})
    return served, refused


def plain_text(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and \
        not any(ord(char) < 32 or ord(char) == 127 for char in value)


def tool_problem(tool, seen):
    if not isinstance(tool, dict):
        return 'a tool is not an object'
    unknown = set(tool) - {'name', 'command', 'grants', 'network', 'unix_sockets', 'env',
                           'time_limit_minutes', 'description'}
    if unknown:
        return 'unknown keys %s' % ', '.join(sorted(unknown))
    name = tool.get('name')
    if not isinstance(name, str) or not NAME_RE.match(name):
        return 'the name is not lowercase letters, digits and "-" (at most 32)'
    if name in seen:
        return 'the name %s comes twice' % name
    command = tool.get('command')
    if not isinstance(command, list) or not 1 <= len(command) <= 32 or \
            not all(plain_text(part, ARG_MAX) for part in command):
        return 'command is not a list of 1 to 32 plain strings'
    program = command[0]
    if '..' in program.split('/') or (not program.startswith('/') and program.startswith('-')):
        return 'the program %r is not a plain path or name' % program
    grants = tool.get('grants', [])
    if not isinstance(grants, list) or any(grant not in GRANTS for grant in grants):
        return 'grants may hold only %s' % ', '.join(GRANTS)
    network = tool.get('network', [])
    if not isinstance(network, list) or len(network) > 8 or \
            not all(isinstance(e, str) and HOST_RE.match(e) and 0 < int(e.rsplit(':', 1)[1]) < 65536
                    for e in network):
        return 'network is not a list of at most 8 host:port entries'
    sockets = tool.get('unix_sockets', [])
    if not isinstance(sockets, list) or len(sockets) > 8 or not all(
            plain_text(e, 200) and (e.startswith('/') or e.startswith('~/'))
            and '..' not in e.split('/') for e in sockets):
        return 'unix_sockets is not a list of at most 8 absolute or ~/ paths'
    env = tool.get('env', {})
    if not isinstance(env, dict) or len(env) > 32 or not all(
            isinstance(k, str) and ENV_RE.match(k) and not ENV_RESERVED.match(k)
            and isinstance(v, str) and len(v) <= ARG_MAX and '\0' not in v
            for k, v in env.items()):
        return 'env holds a name that is reserved or not A-Z, 0-9 and _, or a value that is not text'
    limit = tool.get('time_limit_minutes', LIMIT_DEFAULT)
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or not 0 < limit <= LIMIT_MAX:
        return 'time_limit_minutes is not more than 0 and at most %d' % LIMIT_MAX
    description = tool.get('description', '')
    if not isinstance(description, str) or len(description) > 300 or '\0' in description:
        return 'description is not text of at most 300 characters'
    return None


# --- the worker's side: start the servers and forwarders, stop them -------------------------------

class Broker:
    """The tools of one turn, run by codex_worker.py outside every sandbox. It starts one server
    per tool with fixed arguments and opens no file of the job's."""

    def __init__(self, job, denied, specs, environ, fixed, python=None):
        """environ: the person's environment, of which a tool keeps only ENV_KEEP and LC_*;
        fixed: the job's variables and the turn's marker, which every tool gets.
        tools_dir: the folder of this turn's calls, for Codex's AGF_CODEX_TOOLS_DIR."""
        self.job, self.denied, self.specs = job, list(denied), specs
        self.turn = secrets.token_hex(16)
        self.tools_dir = os.path.join(job, 'out', 'tools', self.turn)
        self.base_env = {name: value for name, value in environ.items()
                         if name in ENV_KEEP or name.startswith('LC_')}
        self.base_env.update(fixed)
        self.python = python or sys.executable
        self.servers, self.listeners, self.pipes = [], [], []
        self.ended = {}  # name: exit code of a server that ended before the turn did
        self.folder = None
        self.stopping = threading.Event()
        self.lock = threading.Lock()

    def folders(self):
        return job_forms(self.job)

    def tool_env(self, spec, net):
        values = {'work': os.path.join(self.job, 'work'), 'tmp': os.path.join(self.job, 'tmp'),
                  'out': os.path.join(self.job, 'out')}
        env = dict(self.base_env)
        for name, value in spec['env'].items():
            for key, path in values.items():
                value = value.replace('{%s}' % key, path)
            env[name] = value
        if net:
            env['AGF_TOOL_NET'] = json.dumps(net)
            env['SANDBOX_RUNTIME'] = '1'
            env['SRT_SSH_PROXY_COMMAND'] = 'exec %s -I %s connect "$1" "$2"' % (
                shlex.quote(self.python), shlex.quote(os.path.abspath(__file__)))
        else:
            for name in ('SANDBOX_RUNTIME', 'SRT_SSH_PROXY_COMMAND', 'AGF_TOOL_NET'):
                env.pop(name, None)
        return env

    def forward(self, host, port):
        """A unix socket of the worker's; each connection to it goes to host:port through nc,
        with the accepted socket as its input and output. Returns the socket's path."""
        if self.folder is None:
            self.folder = tempfile.mkdtemp(prefix='agf-cw-', dir='/private/tmp')
        path = os.path.join(self.folder, 'n%d' % len(self.listeners))
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        os.chmod(path, 0o600)
        listener.listen(8)
        listener.settimeout(0.5)
        self.listeners.append(listener)

        def accept():
            while not self.stopping.is_set():
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                try:
                    with self.lock:
                        # Checked under the lock that stop() takes: no nc starts after it.
                        if self.stopping.is_set():
                            return
                        self.pipes = [p for p in self.pipes if p.poll() is None]
                        if len(self.pipes) < FORWARDS_MAX:
                            self.pipes.append(subprocess.Popen(
                                [NC, host, str(port)], stdin=connection.fileno(),
                                stdout=connection.fileno(), stderr=subprocess.DEVNULL,
                                start_new_session=True, env=self.base_env))
                except OSError:
                    pass
                finally:
                    connection.close()
        threading.Thread(target=accept, daemon=True).start()
        return path

    def start(self, log_folder):
        for spec in self.specs:
            net = {}
            for entry in spec['network']:
                host, port = entry.rsplit(':', 1)
                net[entry.lower()] = self.forward(host, int(port))
            text = profile(self.folders(), self.denied, spec['grants'],
                           list(net.values()) + spec['unix_sockets'])
            log = open(os.path.join(log_folder, 'tool-%s.txt' % spec['name']), 'ab')
            try:
                self.servers.append((spec['name'], subprocess.Popen(
                    [SANDBOX_EXEC, '-p', text, self.python, '-I', os.path.abspath(__file__),
                     'serve', self.job, self.turn, json.dumps(spec)],
                    cwd=os.path.join(self.job, 'work'), env=self.tool_env(spec, net),
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)))
            except OSError as error:
                self.ended[spec['name']] = 'not started: %s' % error.strerror
            finally:
                log.close()

    def stop(self):
        """Kill the servers, their tools' groups and the forwarders. A tool's own group is left to
        the worker's kill by the turn's marker, which every tool carries in its environment."""
        with self.lock:
            self.stopping.set()
            pipes = list(self.pipes)
        for listener in self.listeners:
            listener.close()
        for name, process in self.servers:
            if process.poll() is not None:
                self.ended[name] = process.returncode
        for process in [p for _, p in self.servers] + pipes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)


def note(specs, python):
    """The lines that tell Codex its tools."""
    if not specs:
        return ''
    lines = ['Tools: this project lets you run these commands, each in a sandbox of its own that '
             'writes only this job\'s folders. Run one with',
             '  %s -I %s call <tool> [arguments ...]' % (shlex.quote(python),
                                                         shlex.quote(os.path.abspath(__file__))),
             'in place of the command itself, passing only the arguments that follow the '
             'command shown for the tool (it already holds them); the call prints the tool\'s '
             'output and exits with its code. It waits for the tool, so give the call a timeout at least as long as '
             'the tool\'s limit. A command line the project does not allow is refused (exit '
             '126). The tools run while this turn runs.']
    for spec in specs:
        lines.append('- %s: %s ... (at most %g minutes)%s' % (
            spec['name'], shlex.join(spec['command']), spec['time_limit_minutes'],
            ': ' + spec['description'] if spec['description'] else ''))
    return '\n'.join(lines) + '\n\n'


# --- inside the tool's sandbox: the server ------------------------------------------------------

def read_request(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('not a plain file')
        data = handle.read(REQUEST_MAX + 1)
    if len(data) > REQUEST_MAX:
        raise ValueError('the request is larger than %d bytes' % REQUEST_MAX)
    request = json.loads(data.decode('utf-8'))
    args = request.get('args') if isinstance(request, dict) else None
    if not isinstance(args, list) or len(args) > ARGS_MAX or not all(
            isinstance(arg, str) and len(arg) <= ARG_MAX and '\0' not in arg for arg in args):
        raise ValueError('args is not a list of at most %d strings' % ARGS_MAX)
    cwd = request.get('cwd')
    if not (isinstance(cwd, str) and cwd.startswith('/') and len(cwd) <= 4096 and '\0' not in cwd):
        cwd = None  # then the tool runs in <job>/work
    return args, cwd


def write_done(folder, ident, result):
    temporary = os.path.join(folder, '%s.done-%s' % (ident, secrets.token_hex(4)))
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump(result, handle)
    os.replace(temporary, os.path.join(folder, ident + '.done'))


def program_path(program, work, env):
    if program.startswith('/'):
        return program
    if '/' in program:
        return os.path.join(work, program)
    return shutil.which(program, path=env.get('PATH')) or program


def run_call(spec, job, folder, ident):
    work = os.path.join(job, 'work')
    claimed = os.path.join(folder, ident + '.run')
    os.replace(os.path.join(folder, ident + '.req'), claimed)
    log_path = os.path.join(folder, ident + '.log')
    log = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    started = time.time()
    try:
        try:
            args, cwd = read_request(claimed)
        except (OSError, ValueError, RecursionError) as error:
            os.write(log, ('codex_tools: refused: %s\n' % error).encode())
            return {'exit': REFUSED, 'refused': str(error)}
        line = shlex.join(spec['command'] + args)
        if not any(matches(p, line) for p in spec['allow']) or \
                any(matches(p, line) for p in spec['deny']):
            reason = 'the Claude Code rules do not allow %s' % line
            os.write(log, ('codex_tools: refused: %s\n' % reason).encode())
            return {'exit': REFUSED, 'refused': reason}
        real_work = os.path.realpath(work)
        where = os.path.realpath(cwd) if cwd else real_work
        if where != real_work and not where.startswith(real_work + '/'):
            where = real_work
        argv = [program_path(spec['command'][0], work, os.environ)] + spec['command'][1:] + args
        limit = spec['time_limit_minutes'] * 60
        try:
            process = subprocess.Popen(argv, cwd=where, stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=log, start_new_session=True)
        except OSError as error:
            os.write(log, ('codex_tools: cannot start %s: %s\n' % (argv[0], error)).encode())
            return {'exit': 127, 'failure': str(error)}
        timed_out = False
        try:
            code = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            code = process.wait()
        try:
            os.killpg(process.pid, signal.SIGKILL)  # what the tool left in its group
        except OSError:
            pass
        return {'exit': code if code >= 0 else 128 - code, 'timed_out': timed_out,
                'seconds': round(time.time() - started, 1)}
    finally:
        os.close(log)


def serve(job, turn, spec_text):
    spec = json.loads(spec_text)
    if not ID_RE.match(turn):
        print('codex_tools: the turn %r is not an id' % turn, file=sys.stderr)
        return 1
    top = os.path.join(job, 'out', 'tools')
    folder = os.path.join(top, turn, spec['name'])
    os.makedirs(folder, exist_ok=True)
    for path in (top, os.path.dirname(folder), folder):
        if os.path.islink(path) or not os.path.isdir(path):
            print('codex_tools: %s is not a folder' % path, file=sys.stderr)
            return 1
    ready = os.path.join(folder, 'ready')
    write_done(folder, 'ready', {'pid': os.getpid(), 'command': spec['command'],
                                 'time_limit_minutes': spec['time_limit_minutes']})
    os.replace(os.path.join(folder, 'ready.done'), ready)

    def beat():  # while this server lives, a call can tell it from one that is gone
        while True:
            time.sleep(BEAT_SECONDS)
            try:
                os.utime(ready)
            except OSError:
                pass
    threading.Thread(target=beat, daemon=True).start()
    while True:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return 1
        for name in names:
            ident = name[:-4]
            if name.endswith('.req') and ID_RE.match(ident):
                try:
                    result = run_call(spec, job, folder, ident)
                except Exception as error:  # noqa: BLE001 - one request never ends the server
                    result = {'exit': REFUSED, 'refused': '%s: %s' % (type(error).__name__, error)}
                try:
                    write_done(folder, ident, result)
                except OSError:
                    pass
        time.sleep(POLL)


# --- inside Codex's sandbox: the call -----------------------------------------------------------

def call(name, args):
    """Ask the tool's server for one run and wait for it; print its output, return its exit."""
    top = os.environ.get('AGF_CODEX_TOOLS_DIR')
    served = [n for n in os.environ.get('AGF_CODEX_TOOLS', '').split(',') if NAME_RE.match(n)]
    if not top or name not in served:
        print('codex_tools: refused: %r is not a tool of this turn (tools: %s)'
              % (name, ', '.join(served) or 'none'), file=sys.stderr)
        return REFUSED
    folder = os.path.join(top, name)
    ready = os.path.join(folder, 'ready')
    deadline = time.time() + READY_SECONDS
    while not os.path.isfile(ready):
        if time.time() > deadline:
            print('codex_tools: the server of %s did not start in %g s; the worker\'s log '
                  'tool-%s.txt beside the turn\'s events says why' % (name, READY_SECONDS, name),
                  file=sys.stderr)
            return REFUSED
        time.sleep(POLL)
    try:
        with open(ready, encoding='utf-8') as handle:
            limit = float(json.load(handle).get('time_limit_minutes', LIMIT_MAX))
    except (OSError, ValueError, TypeError, AttributeError):
        limit = LIMIT_MAX
    ident = secrets.token_hex(16)
    temporary = os.path.join(folder, ident + '.tmp')
    with open(temporary, 'w', encoding='utf-8') as handle:
        json.dump({'args': args, 'cwd': os.getcwd()}, handle)
    os.replace(temporary, os.path.join(folder, ident + '.req'))
    log_path, done_path = (os.path.join(folder, ident + suffix) for suffix in ('.log', '.done'))
    # Calls to one tool run one after another, so the wait counts from when this one starts.
    deadline = None
    offset = 0
    out = sys.stdout.buffer
    # The heartbeat counted on this call's own monotonic clock: it stops while the Mac sleeps,
    # as the server's does, so a wake is no gap.
    beat, beat_seen = None, time.monotonic()
    while True:
        finished = os.path.exists(done_path)
        try:
            mtime = os.stat(ready).st_mtime
            if mtime != beat:
                beat, beat_seen = mtime, time.monotonic()
            gone = time.monotonic() - beat_seen > STALE_SECONDS
        except OSError:
            gone = True
        try:
            with open(log_path, 'rb') as handle:
                handle.seek(offset)
                chunk = handle.read()
            offset += len(chunk)
            out.write(chunk)
            out.flush()
            if deadline is None:
                deadline = time.time() + limit * 60 + GRACE_SECONDS
        except FileNotFoundError:
            pass
        if finished:
            break
        if gone:
            print('codex_tools: the server of %s is gone; the worker\'s log tool-%s.txt beside '
                  'the turn\'s events says why' % (name, name), file=sys.stderr)
            return GONE
        if deadline is not None and time.time() > deadline:
            print('codex_tools: no result from %s within its limit; stopped waiting' % name,
                  file=sys.stderr)
            return TIMED_OUT
        time.sleep(POLL)
    try:
        with open(done_path, encoding='utf-8') as handle:
            result = json.load(handle)
    except (OSError, ValueError):
        result = {}
    if not isinstance(result, dict):
        result = {}
    for suffix in ('.run', '.log', '.done'):  # the folder keeps only calls still waiting
        try:
            os.remove(os.path.join(folder, ident + suffix))
        except OSError:
            pass
    if result.get('timed_out'):
        print('codex_tools: %s ran past its time limit and was killed' % name, file=sys.stderr)
    return result['exit'] if isinstance(result.get('exit'), int) else 1


# --- inside the tool's sandbox: ssh's way out ---------------------------------------------------

def connect(host, port):
    """ssh's ProxyCommand: hand stdin and stdout to the worker's socket for host:port."""
    try:
        net = json.loads(os.environ.get('AGF_TOOL_NET', '{}'))
    except ValueError:
        net = {}
    path = net.get(('%s:%s' % (host, port)).lower()) if isinstance(net, dict) else None
    if not isinstance(path, str):
        print('codex_tools: refused: %s:%s is not a network grant of this tool' % (host, port),
              file=sys.stderr)
        return 1
    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    peer.connect(path)

    def upstream():
        while True:
            data = os.read(0, 65536)
            if not data:
                break
            peer.sendall(data)
        try:
            peer.shutdown(socket.SHUT_WR)
        except OSError:
            pass
    threading.Thread(target=upstream, daemon=True).start()
    while True:
        data = peer.recv(65536)
        if not data:
            return 0
        os.write(1, data)


def main(argv):
    if len(argv) >= 2 and argv[0] == 'call':
        return call(argv[1], argv[2:])
    if len(argv) == 4 and argv[0] == 'serve':
        return serve(argv[1], argv[2], argv[3])
    if len(argv) == 3 and argv[0] == 'connect':
        return connect(argv[1], argv[2])
    print(__doc__.split('\n\n')[1], file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
