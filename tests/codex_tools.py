#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/codex_tools.py: python3 tests/codex_tools.py.

Offline, everywhere: the project's tool list is validated (a name, a command, a grant, a network
entry, a unix socket, a variable, a time limit that is not a plain value is refused, and so is a
name the job or the route owns, PATH among them); each tool is served only when a Bash allow rule
covers its command and no deny or ask rule does, and its network hosts and unix sockets only when
the person's or the managed settings allow them (a socket compared after `~` is expanded on both
sides, a wildcard domain never counting); Claude Code's rule forms match as they do there (`x *`
also the bare command, the legacy `x:*` as `x *`, `*` anywhere); the tool's seatbelt profile
writes only the job, has the GPU only with the grant, a unix socket only when named, and ends in
the deny list; a call to a tool the turn does not serve, or whose server never starts, is refused
(126). A server run without a sandbox serves only its own turn's folder (a request of another
turn is never run), survives a request whose folder holds a NUL byte, and a call removes its
files; a call whose server is gone stops waiting (125).

Live, on macOS wherever `sandbox-exec` can run (not inside Claude Code's own sandbox, which
refuses a nested one; under `CI` it must run): a broker serves four tools from their sandboxes,
and a call outside them runs an allowed command line and gets its output and exit; a command line
the rules do not allow, a deny rule's match and a tool not served are refused; a tool cannot
write outside the job nor read `~/.ssh` or `.env`; it has no TCP of its own but reaches its one
`host:port` through the worker's forwarder, the way ssh's ProxyCommand does; a tool past its time
limit is killed; and stopping the broker ends the servers.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SCRIPT = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'codex_tools.py')
spec = importlib.util.spec_from_file_location('codex_tools', SCRIPT)
ct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ct)

failures = []


def check(name, condition, detail=''):
    if not condition:
        failures.append('%s %s' % (name, detail))
        print('FAIL', name, detail)


BLENDER = '/Applications/Blender.app/Contents/MacOS/Blender'
HOME = '/h/someone'
SOCKET = HOME + '/.local/state/gpu-box-ssh/agent.sock'


def tool(**fields):
    base = {'name': 'blender', 'command': [BLENDER, '--background']}
    base.update(fields)
    return base


def anchored(tools, allow=(BLENDER + ' --background --python *',), deny=(), domains=(),
             sockets=()):
    return ct.check_tools({'tools': tools}, {'allow': list(allow), 'deny': list(deny)},
                          {'domains': list(domains), 'sockets': list(sockets)}, HOME)


def offline():
    # Claude Code's rule forms.
    for pattern, line, expected in (
            ('/bin/echo hi *', '/bin/echo hi', True),
            ('/bin/echo hi *', '/bin/echo hi there', True),
            ('/bin/echo hi *', '/bin/echo hither', False),
            ('/bin/echo hi *', '/bin/echo bye', False),
            ('git status:*', 'git status --short', True),
            ('git status:*', 'git push', False),
            ('git status:*', 'git status', True),
            ('tools/qa/run:*', 'tools/qa/run_all.sh', False),
            ('*', 'anything at all', True),
            ('a * c', 'a b c', True),
            ('a * c', 'a b d', False)):
        check('pattern %r on %r' % (pattern, line), ct.matches(pattern, line) is expected)
    check('bash_patterns', ct.bash_patterns(['Bash', 'Bash(x *)', 'Read(y)', 3, 'Bashful']) ==
          ['*', 'x *'], str(ct.bash_patterns(['Bash', 'Bash(x *)', 'Read(y)', 3])))

    # The list itself.
    served, refused = anchored([tool(grants=['gpu'], time_limit_minutes=20, description='d')])
    check('a covered tool is served', [s['name'] for s in served] == ['blender'] and not refused,
          str(refused))
    if served:
        check('the served spec keeps only what covers it',
              served[0]['allow'] == [BLENDER + ' --background --python *'] and
              served[0]['grants'] == ['gpu'] and served[0]['time_limit_minutes'] == 20,
              str(served[0]))
    for name, listed in (('no tools key', {}), ('tools not a list', {'tools': 'x'}),
                         ('too many tools', {'tools': [tool(name='t%d' % i) for i in range(33)]}),
                         ('not an object', [])):
        got = ct.check_tools(listed, {'allow': ['*'], 'deny': []}, {}, HOME)
        check('list refused: %s' % name, got[0] == [] and got[1] and got[1][0]['name'] is None,
              str(got))
    bad = {
        'a name with capitals': tool(name='Blender'),
        'a name with a slash': tool(name='a/b'),
        'an unknown key': tool(shell=True),
        'an empty command': tool(command=[]),
        'a command with a control character': tool(command=[BLENDER, 'a\nb']),
        'a program with ..': tool(command=['../x']),
        'a program that is an option': tool(command=['-x']),
        'an unknown grant': tool(grants=['root']),
        'a network entry without a port': tool(network=['gpu-box.local']),
        'a network port 0': tool(network=['h:0']),
        'a network port past 65535': tool(network=['h:70000']),
        'a network entry with a scheme': tool(network=['ssh://h:22']),
        'a relative unix socket': tool(unix_sockets=['agent.sock']),
        'a unix socket with ..': tool(unix_sockets=['~/../x.sock']),
        'PATH set by the list': tool(env={'PATH': '/x'}),
        'GIT_DIR set by the list': tool(env={'GIT_DIR': '/x'}),
        'DYLD_ set by the list': tool(env={'DYLD_INSERT_LIBRARIES': '/x'}),
        'SRT_ set by the list': tool(env={'SRT_SSH_PROXY_COMMAND': 'x'}),
        'the marker set by the list': tool(env={'CODEX_WORKER_TURN': 'x'}),
        'PYTHONPATH set by the list': tool(env={'PYTHONPATH': '/x'}),
        'a lowercase variable': tool(env={'path': '/x'}),
        'a time limit of 0': tool(time_limit_minutes=0),
        'a time limit past 240': tool(time_limit_minutes=241),
        'a time limit that is a bool': tool(time_limit_minutes=True),
        'a description too long': tool(description='x' * 301),
    }
    for name, entry in bad.items():
        served, refused = anchored([entry], allow=['*'])
        check('tool refused: %s' % name, not served and len(refused) == 1, str(served))
    served, refused = anchored([tool(), tool()])
    check('a name twice: the second refused', len(served) == 1 and len(refused) == 1, str(refused))

    # The anchors.
    served, refused = anchored([tool()], allow=['/usr/bin/other *'])
    check('no allow rule: refused', not served and 'allow rule' in refused[0]['reason'],
          str(refused))
    served, refused = anchored([tool()], deny=[BLENDER + ' *'])
    check('a deny or ask rule over the command: refused', not served and refused, str(served))
    served, refused = anchored([tool()], deny=[BLENDER + ' --background --python * --python-expr*'])
    check('a deny rule on later arguments is kept for the calls',
          served and served[0]['deny'] and not ct.matches(served[0]['deny'][0],
                                                         BLENDER + ' --background --python b.py')
          and ct.matches(served[0]['deny'][0],
                         BLENDER + ' --background --python b.py --python-expr x'), str(served))
    spark = tool(name='spark', command=['tools/qa/spark_shot.sh'],
                 network=['gpu-box.local:22'], unix_sockets=['~/.local/state/gpu-box-ssh/agent.sock'])
    rule = ['tools/qa/spark_shot.sh *']
    served, refused = anchored([spark], allow=rule, domains=['gpu-box.local'], sockets=[SOCKET])
    check('network and socket anchored: served',
          served and served[0]['unix_sockets'] == [os.path.realpath(SOCKET)],
          str(refused))
    served, refused = anchored([spark], allow=rule, domains=['gpu-box.local:22'],
                               sockets=['~/.local/state/gpu-box-ssh/agent.sock'])
    check('host:port domain and a ~ socket in the settings: served', served, str(refused))
    served, refused = anchored([spark], allow=rule, domains=['*.local'], sockets=[SOCKET])
    check('a wildcard domain does not count', not served and 'allowedDomains' in
          refused[0]['reason'], str(served))
    served, refused = anchored([spark], allow=rule, domains=['gpu-box.local:2222'],
                               sockets=[SOCKET])
    check('another port does not count', not served, str(served))
    served, refused = anchored([spark], allow=rule, domains=['gpu-box.local'], sockets=[])
    check('a socket the settings do not allow: refused', not served and 'allowUnixSockets' in
          refused[0]['reason'], str(served))

    # A link in place of a job folder is never resolved into the profile.
    top = tempfile.mkdtemp(prefix='codex-tools-forms-')
    try:
        job_dir = os.path.join(top, 'job')
        os.makedirs(os.path.join(job_dir, 'work'))
        os.symlink(os.path.expanduser('~'), os.path.join(job_dir, 'out'))
        forms = ct.job_forms(job_dir)
        check('job folders: by the job\'s path and the fixed names only',
              all(os.path.basename(f) in ct.PARTS and os.path.dirname(f) in
                  (job_dir, os.path.realpath(job_dir)) for f in forms) and
              not any(os.path.realpath(os.path.expanduser('~')) == f for f in forms), str(forms))
    finally:
        shutil.rmtree(top, ignore_errors=True)
    # A socket of the list is compared as text, the person's entry resolved.
    served, refused = anchored([tool(name='s', command=[BLENDER, '--background'],
                                     unix_sockets=['~/./.local/state/gpu-box-ssh/agent.sock'])],
                               sockets=['~/.local/state/gpu-box-ssh/agent.sock'])
    check('a socket written another way but the same text after normpath: served', served,
          str(refused))

    # The profile.
    job = HOME + '/.cache/x/job-1'
    folders = [job + '/' + part for part in ('work', 'git', 'tmp', 'out')]
    denied = [HOME + '/.ssh', '/**/.env']
    text = ct.profile(folders, denied)
    check('profile: a tty only with the pty extension',
          '(extension "com.apple.sandbox.pty")' in text and
          '(regex #"^/dev/ttys[0-9]+$"))' not in text.split('require-all')[0])
    lines = text.splitlines()
    allows = [i for i, line in enumerate(lines) if line.startswith('(allow')]
    denies = [i for i, line in enumerate(lines) if line.startswith('(deny file')]
    check('profile: deny by default', '(deny default)' in lines)
    check('profile: the deny list comes after every allow', denies and max(allows) < min(denies))
    check('profile: writes only the job',
          [line for line in lines if 'file-write*' in line and line.startswith('(allow')] ==
          ['(allow file-read* file-write* file-ioctl (literal "/dev/ptmx"))',
           '(allow file-read* file-write* file-ioctl'] +
          ['(allow file-write* (subpath "%s"))' % f for f in folders],
          '\n'.join(line for line in lines if 'file-write*' in line))
    check('profile: no network, no GPU without grants',
          'network-outbound' not in text and 'AGXDeviceUserClient' not in text)
    check('profile: an .env anywhere denied', any('\\.env' in line or '.env' in line
                                                  for line in lines[min(denies):]))
    gpu = ct.profile(folders, denied, ['gpu'])
    check('profile: the gpu grant adds the Metal device', 'AGXDeviceUserClient' in gpu and
          'com.apple.MTLCompilerService' in gpu)
    with_socket = ct.profile(folders, denied, [], ['/private/tmp/agf-cw-x/n0'])
    check('profile: a named socket only', '(path-literal "/private/tmp/agf-cw-x/n0")' in
          with_socket and with_socket.count('network-outbound') ==
          len(ct.both_forms('/private/tmp/agf-cw-x/n0')), with_socket[-600:])

    # The note and the environment a tool gets.
    check('no tools: no note', ct.note([], '/usr/bin/python3') == '')
    served, _ = anchored([tool(description='Blender headless')])
    text = ct.note(served, '/usr/bin/python3')
    check('the note names the tool and the call', 'blender' in text and ' call <tool>' in text,
          text)
    broker = ct.Broker('/j', [], [], {'SANDBOX_RUNTIME': '1', 'SRT_SSH_PROXY_COMMAND': 'x',
                                      'HOME': '/h', 'LC_ALL': 'C', 'GH_TOKEN': 't',
                                      'SSH_AUTH_SOCK': '/s', 'OPENAI_API_KEY': 'k'},
                       {'GIT_DIR': '/j/git'})
    env = broker.tool_env({'env': {'PAX_DATA_DIR': '{tmp}/pax-data'}}, {})
    check('a tool keeps only a short list of the person\'s variables, plus the job\'s',
          sorted(env) == ['GIT_DIR', 'HOME', 'LC_ALL', 'PAX_DATA_DIR'] and
          env['PAX_DATA_DIR'] == os.path.join('/j', 'tmp') + '/pax-data', str(env))
    env = broker.tool_env({'env': {}}, {'h:22': '/s'})
    check('a tool with network: the proxy route', env['SANDBOX_RUNTIME'] == '1' and
          ' connect "$1" "$2"' in env['SRT_SSH_PROXY_COMMAND'] and
          json.loads(env['AGF_TOOL_NET']) == {'h:22': '/s'}, str(env))

    # A call the turn does not serve, or whose server never starts.
    folder = tempfile.mkdtemp(prefix='codex-tools-test-')
    quiet = contextlib.redirect_stderr(io.StringIO())
    quiet.__enter__()
    try:
        saved = dict(os.environ)
        os.environ.update(AGF_CODEX_TOOLS_DIR=folder, AGF_CODEX_TOOLS='blender')
        check('a tool the turn does not serve: 126', ct.call('other', []) == ct.REFUSED)
        os.makedirs(os.path.join(folder, 'other'))
        open(os.path.join(folder, 'other', 'ready'), 'w').close()
        check('a ready folder does not make a tool served', ct.call('other', []) == ct.REFUSED)
        ct.READY_SECONDS = 0.5
        check('a server that never starts: 126', ct.call('blender', []) == ct.REFUSED)
        os.environ.clear()
        os.environ.update(saved)
        os.environ.pop('AGF_CODEX_TOOLS_DIR', None)
        check('outside a turn: 126', ct.call('blender', []) == ct.REFUSED)
    finally:
        quiet.__exit__(None, None, None)
        os.environ.clear()
        os.environ.update(saved)
        shutil.rmtree(folder, ignore_errors=True)


def route():
    """serve and call without a sandbox: the folder per turn, a bad request, the cleanup and a
    server that is gone."""
    base = tempfile.mkdtemp(prefix='codex-tools-route-')
    server = None
    saved = dict(os.environ)
    try:
        job = os.path.join(base, 'job')
        for part in ('work', 'git', 'tmp', 'out'):
            os.makedirs(os.path.join(job, part))
        turn, other = 'a' * 32, 'b' * 32
        orphans = []
        for folder in (os.path.join(job, 'out', 'tools', other, 'echo'),
                       os.path.join(job, 'out', 'tools', 'echo')):
            os.makedirs(folder)
            orphan = os.path.join(folder, 'c' * 32 + '.req')
            with open(orphan, 'w') as handle:
                json.dump({'args': ['hi', 'orphan'], 'cwd': None}, handle)
            orphans.append(orphan)
        spec_text = json.dumps({'name': 'echo', 'command': ['/bin/echo'],
                                'allow': ['/bin/echo hi *'], 'deny': [],
                                'time_limit_minutes': 1})
        server = subprocess.Popen([sys.executable, '-I', SCRIPT, 'serve', job, turn, spec_text],
                                  cwd=os.path.join(job, 'work'), stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        tools_dir = os.path.join(job, 'out', 'tools', turn)
        env = dict(os.environ, AGF_CODEX_TOOLS_DIR=tools_dir, AGF_CODEX_TOOLS='echo')
        result = subprocess.run([sys.executable, '-I', SCRIPT, 'call', 'echo', 'hi', 'there'],
                                env=env, cwd=os.path.join(job, 'work'), capture_output=True,
                                text=True, timeout=60)
        folder = os.path.join(tools_dir, 'echo')
        check('route: a call runs and removes its files', result.returncode == 0 and
              result.stdout == 'hi there\n' and os.listdir(folder) == ['ready'],
              repr(result) + str(os.listdir(folder)))
        check('route: a request of another turn is never run',
              all(os.path.exists(o) and not os.path.exists(o[:-4] + '.done') for o in orphans),
              str([os.listdir(os.path.dirname(o)) for o in orphans]))
        ident = 'd' * 32
        with open(os.path.join(folder, ident + '.tmp'), 'w') as handle:
            json.dump({'args': ['hi', 'nul'], 'cwd': '/a\0b'}, handle)
        os.replace(os.path.join(folder, ident + '.tmp'), os.path.join(folder, ident + '.req'))
        deadline = time.time() + 30
        while not os.path.exists(os.path.join(folder, ident + '.done')) and time.time() < deadline:
            time.sleep(0.1)
        deep = 'e' * 32  # nesting past Python's recursion limit, under REQUEST_MAX
        with open(os.path.join(folder, deep + '.tmp'), 'w') as handle:
            handle.write('{"args": ' + '[' * 120000 + ']' * 120000 + '}')
        os.replace(os.path.join(folder, deep + '.tmp'), os.path.join(folder, deep + '.req'))
        deadline = time.time() + 30
        while not os.path.exists(os.path.join(folder, deep + '.done')) and time.time() < deadline:
            time.sleep(0.1)
        result = subprocess.run([sys.executable, '-I', SCRIPT, 'call', 'echo', 'hi', 'again'],
                                env=env, cwd=os.path.join(job, 'work'), capture_output=True,
                                text=True, timeout=60)
        check('route: a folder with a NUL byte or a deeply nested request does not stop it',
              server.poll() is None and result.returncode == 0 and
              result.stdout == 'hi again\n', repr(result))
        server.kill()
        server.wait()
        os.environ.update(AGF_CODEX_TOOLS_DIR=tools_dir, AGF_CODEX_TOOLS='echo')
        stale = ct.STALE_SECONDS
        ct.STALE_SECONDS = 1
        started = time.time()
        try:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = ct.call('echo', ['hi'])
        finally:
            ct.STALE_SECONDS = stale
        check('route: a call whose server is gone stops waiting (125)',
              code == ct.GONE and time.time() - started < 5 and 'gone' in err.getvalue(),
              '%r %s' % (code, err.getvalue()))
    finally:
        os.environ.clear()
        os.environ.update(saved)
        if server is not None and server.poll() is None:
            server.kill()
            server.wait()
        shutil.rmtree(base, ignore_errors=True)


def sandbox_exec_runs():
    if sys.platform != 'darwin' or not os.path.exists(ct.SANDBOX_EXEC):
        return False
    probe = subprocess.run([ct.SANDBOX_EXEC, '-p', '(version 1)(allow default)', '/usr/bin/true'],
                           capture_output=True)
    return probe.returncode == 0


WRITER = r'''import os
for label, path in (('home', os.path.expanduser('~/agf-tools-test-%d' % os.getpid())),
                    ('tmp', '/private/tmp/agf-tools-test-%d' % os.getpid()),
                    ('job', os.path.join(os.environ['GIT_WORK_TREE'], 'made.txt'))):
    try:
        open(path, 'w').write('x')
        print('write', label, 'OK')
    except OSError:
        print('write', label, 'refused')
for label, path in (('ssh', os.path.expanduser('~/.ssh')),
                    ('env', os.path.join(os.environ['GIT_WORK_TREE'], '.env'))):
    try:
        os.listdir(path) if os.path.isdir(path) else open(path).read(1)
        print('read', label, 'OPEN')
    except OSError:
        print('read', label, 'refused')
'''

NET = r'''import os, socket, subprocess, sys
port = int(sys.argv[1])
try:
    socket.create_connection(('127.0.0.1', port), 2)
    print('direct OPEN')
except OSError:
    print('direct refused')
route = subprocess.run(['/bin/sh', '-c', os.environ['SRT_SSH_PROXY_COMMAND'], 'p', '127.0.0.1',
                        str(port)], input=b'hello', capture_output=True)
print('proxy', route.stdout.decode(), route.returncode)
'''


def live():
    base = os.path.realpath(tempfile.mkdtemp(prefix='codex-tools-live-',
                                             dir=os.path.expanduser('~')))
    server = socket.socket()
    server.bind(('127.0.0.1', 0))
    server.listen(2)
    port = server.getsockname()[1]

    def answer():
        connection, _ = server.accept()
        connection.sendall(b'echo:' + connection.recv(100))
        connection.close()
    threading.Thread(target=answer, daemon=True).start()
    broker = None
    try:
        job = os.path.join(base, 'job')
        for part in ('work', 'git', 'tmp', 'out'):
            os.makedirs(os.path.join(job, part))
        open(os.path.join(job, 'work', '.env'), 'w').write('SECRET=1\n')
        logs = os.path.join(base, 'logs')
        os.makedirs(logs)
        python = sys.executable
        writer = os.path.join(base, 'writer.py')
        net = os.path.join(base, 'net.py')
        for path, text in ((writer, WRITER), (net, NET)):
            with open(path, 'w') as handle:
                handle.write(text)

        def spec(name, command, allow, deny=(), network=(), limit=1):
            return {'name': name, 'command': command, 'allow': list(allow), 'deny': list(deny),
                    'grants': [], 'network': list(network), 'unix_sockets': [], 'env': {},
                    'time_limit_minutes': limit, 'description': ''}
        specs = [spec('echo', ['/bin/echo'], ['/bin/echo hi *'], ['/bin/echo hi bad*']),
                 spec('writer', [python, '-I', writer], ['*']),
                 spec('net', [python, '-I', net], ['*'], network=['127.0.0.1:%d' % port]),
                 spec('slow', ['/bin/sleep'], ['/bin/sleep *'], limit=0.03)]
        home = os.path.realpath(os.path.expanduser('~'))
        env = dict(os.environ, GIT_DIR=os.path.join(job, 'git'),
                   GIT_WORK_TREE=os.path.join(job, 'work'), TMPDIR=os.path.join(job, 'tmp'))
        broker = ct.Broker(job, [os.path.join(home, '.ssh'), '/**/.env'], specs, os.environ,
                           {'GIT_DIR': os.path.join(job, 'git'),
                            'GIT_WORK_TREE': os.path.join(job, 'work'),
                            'TMPDIR': os.path.join(job, 'tmp')})
        broker.start(logs)
        call_env = dict(env, AGF_CODEX_TOOLS_DIR=broker.tools_dir,
                        AGF_CODEX_TOOLS='echo,writer,net,slow')

        def call(*args):
            return subprocess.run([python, '-I', SCRIPT, 'call'] + list(args), env=call_env,
                                  cwd=os.path.join(job, 'work'), capture_output=True, text=True,
                                  timeout=180)
        result = call('echo', 'hi', 'there')
        check('live: an allowed call runs', result.returncode == 0 and
              result.stdout == 'hi there\n', repr(result))
        result = call('echo', 'bye')
        check('live: a command line the rules do not allow: 126', result.returncode == 126 and
              'refused' in result.stdout, repr(result))
        result = call('echo', 'hi', 'bad')
        check('live: a deny rule\'s match: 126', result.returncode == 126, repr(result))
        result = call('nope')
        check('live: a tool not served: 126', result.returncode == 126, repr(result))
        result = call('writer')
        check('live: the tool writes only the job and cannot read ~/.ssh or .env',
              result.stdout == 'write home refused\nwrite tmp refused\nwrite job OK\n'
              'read ssh refused\nread env refused\n', repr(result.stdout))
        result = call('net', str(port))
        check('live: no TCP of its own, its one host:port through the forwarder',
              result.stdout == 'direct refused\nproxy echo:hello 0\n', repr(result.stdout))
        started = time.time()
        result = call('slow', '60')
        check('live: past its time limit the tool is killed', result.returncode == 137 and
              time.time() - started < 30 and 'time limit' in result.stderr, repr(result))
        broker.stop()
        check('live: no server ended early', broker.ended == {}, str(broker.ended))
        check('live: stopping the broker ends the servers',
              all(process.poll() is not None for _, process in broker.servers))
        broker = None
    finally:
        if broker is not None:
            broker.stop()
        server.close()
        shutil.rmtree(base, ignore_errors=True)


def main():
    offline()
    if os.name == 'posix':
        route()
    if sandbox_exec_runs():
        live()
        where = 'offline and live'
    elif sys.platform == 'darwin' and os.environ.get('CI'):
        check('sandbox-exec runs under CI on macOS', False)
        where = 'offline'
    else:
        where = 'offline only (sandbox-exec cannot run here, e.g. inside Claude Code\'s sandbox)'
    if failures:
        print('codex_tools: %d failure(s)' % len(failures))
        return 1
    print('codex_tools: ok (%s)' % where)
    return 0


if __name__ == '__main__':
    sys.exit(main())
