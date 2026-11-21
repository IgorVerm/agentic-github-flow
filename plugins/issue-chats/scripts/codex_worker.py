#!/usr/bin/env python3
"""Run Codex as the worker of a Claude issue chat, in a job folder of its own.

Usage: python3 -I codex_worker.py <worktree> --model <model> --prompt-file <file>
                                  [--resume <thread id>] [--time-limit <minutes>] [--fresh]
       python3 -I codex_worker.py <worktree> --export

The route of method.md *Codex as the worker* (issues #103, #107): the Claude issue chat stays
the owner of the issue and the person's interface, and hands the implementation to Codex. One
tool, so that a single narrow allow rule and one `sandbox.excludedCommands` entry cover it,
instead of rules on `codex exec *`, which would also admit
`--dangerously-bypass-approvals-and-sandbox`. Codex needs the network and writes its sessions
under `~/.codex`, so it cannot run inside Claude Code's sandbox (measured 2026-11-20). The allow
rule lets this script run outside that sandbox without a prompt, so it takes no program to run:
`codex` is the one on PATH.

**The rule this script keeps (issue #107).** Bytes that the chat or Codex wrote are handled only
inside a sandbox no wider than their writer's. Outside a sandbox this script runs no git and
opens no file of theirs: it reads its arguments as text, keeps its own folder, and starts
`codex`. Five reviews each found git run outside the sandbox on a repository the chat or Codex
could write; Codex's own process does the same on every turn (`git status` in its working
folder, hooks and fsmonitor off but filters on; read in its source at 0.171.0-alpha.13), and the
person's Codex configuration can lift a command out of Codex's sandbox (an execpolicy `allow`
rule, an MCP server, `notify`, the shell snapshot). So:

- **A job** is `~/.cache/agentic-github-flow/codex-worker/jobs/<key>/job-<random>/` (`<key>`
  from the worktree's path) with `work`, `git`, `tmp` and `out`. Every new job has a new random
  name, so a process an old job left behind, which stays in its own sandbox, cannot write it.
- **Everything that reads the chat's or Codex's data runs in Codex's sandbox**, through
  `codex sandbox … -- python3 -I codex_job.py …` under the profile below: the setup of a job
  (the clean check, Codex's git folder with the chat's object store as an alternate, each tracked
  file an APFS clone of the worktree's on macOS: measured on pax_deorum, 16,891 files, 13 GiB,
  64 s, 15.7 MiB of disk), the reading of the prompt file, and the export of Codex's commits as
  a git bundle. `codex_job.py`'s header owns what they do and refuse.
- **Codex's working folder holds no git folder.** Its commands reach `<job>/git` through
  `GIT_DIR` and `GIT_WORK_TREE` (`shell_environment_policy.set`); Codex's own process has
  neither and finds no repository in `<job>/work`, and Codex's sandbox refuses to create
  `work/.git` or `work/.codex` (measured). Only commands inside the sandbox ever use the git
  folder Codex writes.
- **Codex's process** ignores the person's configuration and rules, and runs no hook and no
  shell snapshot.

**The profile** (`permissions.agf_codex_worker`), the same for the setup, a turn and the export:
write only the job's four folders (not `/tmp`, not `$TMPDIR`); no network; read the disk except
`~/.ssh`, `~/.aws`, `~/.netrc`, `~/.gnupg`, `~/.config/gh`, and any `.env`, `.env.*`, `*.pem`,
`*.key` or `*.p12` (what Claude Code's sandbox denies the chat; measured on macOS with
`codex sandbox`, also inside a writable folder, through a symlink, and for a new hard link). The
prompt file is read under it too, so the chat cannot have a denied file sent to OpenAI.

It refuses (exit 3) before Codex starts unless: the system is macOS (the only one the profile
is measured on) with process groups; the model and the thread id are plain values and the time
limit is 1 to 1440 minutes; a resume finds its job; and the setup accepts the worktree (the top
of a linked worktree, on a branch with a commit, clean) and the prompt file (a plain file of at
most 1 MiB, not empty).

**A turn** is one `codex exec` (or `codex exec resume <thread id>`) in `<job>/work`, the prompt
on stdin after a fixed note on the git setup, in a process session of its own, with a time limit
(`--time-limit`, default 60 minutes):

  codex exec [resume <thread id>] --json -o <last message> -m <model>
             --skip-git-repo-check --ignore-user-config --ignore-rules
             -c approval_policy="never" -c default_permissions="agf_codex_worker"
             -c permissions.agf_codex_worker.filesystem={…}
             -c permissions.agf_codex_worker.network.enabled=false
             -c shell_environment_policy.set.GIT_DIR=… (GIT_WORK_TREE, TMPDIR, the marker)
             -c features.hooks=false -c features.shell_snapshot=false -

Codex is never asked for an approval and cannot ask one: a question belongs in its final
message. When `codex` ends, or the time limit kills it, the worker kills what is left of the
turn: the process group, then every process of this user whose environment holds the turn's
marker (which catches a `setsid` double-fork). A process that leaves the group and drops its
environment survives inside Codex's sandbox; the kill is hygiene, not the boundary. Its report:
`status`, `thread_id` (for `--resume` and `codex resume`), `model`, `branch`, `job`,
`time_limit_minutes`, `timed_out`, `group_left`, `marked_killed`, `last_message` (Codex's final
message: all the Claude chat reads of a turn), `events` (the JSONL event log, kept with the last
message in the worker's folder, outside every folder Codex writes, and removed after 30 days);
on a new job also `setup` (`apfs_clones`, `files`, `withheld`: tracked files that cannot exist in
Codex's folder). Exit: 0 the turn completed; 1 Codex failed, timed out or the turn did not
complete; 2 usage; 3 refused before Codex started.

**The export** (`--export`, once, when Codex's work is done) cuts `<job>/out/codex.bundle`
inside Codex's sandbox: Codex's commits on top of the commit the job started from. The chat
imports it inside its own sandbox with `codex_import.py <worktree> <bundle>`, which treats it as
data. Its report: `status` (`exported`, `nothing`, `failed`), `branch`, `base`, `head`,
`commits` (`sha`, `subject`, oldest first), `bundle`. Exit: 0 exported or nothing; 1 failed;
3 refused.

`--fresh` retires the job first, for a new start from the chat's HEAD. One worker at a time per
worktree: a lock in the worker's folder. A job whose worktree is gone is removed at the next run.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:  # Windows: refused in main
    fcntl = None

HERE = os.path.dirname(os.path.abspath(__file__))
JOB_TOOL = os.path.join(HERE, 'codex_job.py')
MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
THREAD_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}([0-9a-f]{24})?$')
JOB_RE = re.compile(r'^job-[0-9a-f]{32}$')
MEASURED = ('darwin',)  # the systems the permission profile is measured on
PROFILE = 'agf_codex_worker'
PARTS = ('work', 'git', 'tmp', 'out')
DENY_HOME = ('.ssh', '.aws', '.netrc', '.gnupg', os.path.join('.config', 'gh'))
DENY_GLOBS = ('/**/.env', '/**/.env.*', '/**/*.pem', '/**/*.key', '/**/*.p12')
REPORT_MAX = 2 * 1024 * 1024
LOG_DAYS = 30
MARKER = 'CODEX_WORKER_TURN'
SECONDS = {'setup': 3600, 'prompt': 30, 'export': 600}
NOTE = '''[Note from the worker that started you]
You work in %(work)s on branch %(branch)s. It is a git repository, but it has no .git folder:
git reaches it through the GIT_DIR and GIT_WORK_TREE variables that every command of yours
already has, so `git status`, `git add` and `git commit` work as usual. Do not create a .git
folder, do not unset or change those variables, and never push (you have no network). Commit
your work on this branch. You cannot ask a question while you work: put a question or a blocker
in your final message.

'''


def refuse(message):
    print('codex_worker: refused: %s' % message, file=sys.stderr)
    sys.exit(3)


def toml_string(value):
    # A TOML basic string: JSON's escapes for backslash, quote and control characters are TOML's.
    return json.dumps(value, ensure_ascii=False)


# --- the worker's own folder -------------------------------------------------------------------

def cache_folder():
    # From the home folder alone: an environment variable could move it to where the chat writes.
    folder = os.path.join(os.path.realpath(os.path.expanduser('~')), '.cache',
                          'agentic-github-flow', 'codex-worker')
    os.makedirs(folder, mode=0o700, exist_ok=True)
    return folder


def paths(worktree):
    key = hashlib.sha256(os.fsencode(worktree)).hexdigest()[:16]
    folder = os.path.join(cache_folder(), 'jobs', key)
    return {'folder': folder, 'state': os.path.join(folder, 'state.json'),
            'lock': os.path.join(folder, 'lock'), 'worktree': worktree}


def take_lock(path):
    handle = open(path, 'a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def lock(where):
    os.makedirs(where['folder'], mode=0o700, exist_ok=True)
    handle = take_lock(where['lock'])
    if handle is None:
        refuse('another codex_worker run holds %s' % where['lock'])
    return handle


def read_state(where):
    try:
        with open(where['state'], encoding='utf-8') as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(where, state):
    with open(where['state'], 'w', encoding='utf-8') as handle:
        json.dump(state, handle, indent=2)


def retire(folder, name):
    """Remove a job. It is renamed first, out of the paths its sandbox may write, so a process
    it left behind cannot refill it; the removal unlinks names and follows no link."""
    path = os.path.join(folder, name)
    if not os.path.lexists(path):
        return
    gone = os.path.join(folder, 'gone-' + secrets.token_hex(16))
    os.rename(path, gone)
    if os.path.isdir(gone) and not os.path.islink(gone):
        shutil.rmtree(gone, ignore_errors=True)
    else:
        os.remove(gone)


def sweep(where):
    """Remove the job folders whose worktree is gone (cleanup-merged ran), and what an
    interrupted run left in this one."""
    jobs = os.path.dirname(where['folder'])
    for name in os.listdir(jobs):
        folder = os.path.join(jobs, name)
        if folder == where['folder'] or os.path.islink(folder) or not os.path.isdir(folder):
            continue
        worktree = read_state({'state': os.path.join(folder, 'state.json')}).get('worktree')
        if isinstance(worktree, str) and os.path.lexists(worktree):
            continue
        held = take_lock(os.path.join(folder, 'lock'))
        if held is not None:
            try:
                shutil.rmtree(folder, ignore_errors=True)
            finally:
                held.close()
    current = read_state(where).get('job')
    for name in os.listdir(where['folder']):
        if name.startswith(('job-', 'gone-')) and name != current:
            retire(where['folder'], name)


def job_folders(job):
    return [os.path.join(job, part) for part in PARTS]


# --- Codex's sandbox ---------------------------------------------------------------------------

def profile_config(job):
    """The `-c` values of the permission profile: the job writable, the deny list unreadable."""
    home = os.path.realpath(os.path.expanduser('~'))
    entries = [(':root', 'read')] + [(folder, 'write') for folder in job_folders(job)]
    entries += [(os.path.join(home, name), 'deny') for name in DENY_HOME]
    entries += [(pattern, 'deny') for pattern in DENY_GLOBS]
    table = ', '.join('%s = %s' % (toml_string(path), toml_string(access))
                      for path, access in entries)
    return ['default_permissions=%s' % toml_string(PROFILE),
            'permissions.%s.filesystem={%s}' % (PROFILE, table),
            'permissions.%s.network.enabled=false' % PROFILE]


def config_args(values):
    return [item for value in values for item in ('-c', value)]


def clean_environment(job):
    """The environment of every `codex` this script starts: no GIT_* variable, so that Codex's
    own git never follows one into a repository, and the job's temporary folder."""
    env = {name: value for name, value in os.environ.items() if not name.startswith('GIT_')}
    tmp = os.path.join(job, 'tmp')
    env.update(TMPDIR=tmp, TMP=tmp, TEMP=tmp)
    return env


def in_sandbox(codex, job, action, *args):
    """Run codex_job.py inside Codex's sandbox; return (exit code, its report or {})."""
    command = [codex, 'sandbox'] + config_args(profile_config(job)) + \
        ['--', sys.executable, '-I', JOB_TOOL, action] + list(args)
    out_path = os.path.join(os.path.dirname(job), 'report-' + secrets.token_hex(8))
    try:
        with open(out_path, 'wb') as out:
            process = subprocess.Popen(command, cwd=job, stdin=subprocess.DEVNULL, stdout=out,
                                       stderr=subprocess.DEVNULL, env=clean_environment(job),
                                       start_new_session=True)
            try:
                code = process.wait(timeout=SECONDS[action])
            except subprocess.TimeoutExpired:
                code = 124
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait()
        with open(out_path, 'rb') as handle:
            data = handle.read(REPORT_MAX + 1)
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)
    report = {}
    if len(data) <= REPORT_MAX:
        # The last line: what ran in the sandbox may have printed before the report.
        lines = data.decode('utf-8', errors='replace').strip().splitlines()
        try:
            report = json.loads(lines[-1]) if lines else {}
        except ValueError:
            report = {}
    if not isinstance(report, dict):
        report = {}
    if code == 124:
        report = {'status': 'failed', 'failure': 'the %s ran past %d s' % (action, SECONDS[action])}
    return code, report


def text_of(report, key, limit=2000):
    value = report.get(key)
    return value[:limit] if isinstance(value, str) else ''


# --- the turn ----------------------------------------------------------------------------------

def log_folder():
    folder = cache_folder()
    cutoff = time.time() - LOG_DAYS * 86400
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.lstat(path).st_mtime < cutoff and os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
    return folder


def codex_command(codex, model, resume, job, last_message, marker):
    command = [codex, 'exec']
    if resume:
        command += ['resume', resume]
    work, tmp = os.path.join(job, 'work'), os.path.join(job, 'tmp')
    variables = {'GIT_DIR': os.path.join(job, 'git'), 'GIT_WORK_TREE': work, 'TMPDIR': tmp,
                 'TMP': tmp, 'TEMP': tmp, MARKER: marker}
    values = ['approval_policy="never"'] + profile_config(job)
    values += ['shell_environment_policy.set.%s=%s' % (name, toml_string(value))
               for name, value in variables.items()]
    values += ['features.hooks=false', 'features.shell_snapshot=false']
    command += ['--json', '-o', last_message, '-m', model, '--skip-git-repo-check',
                '--ignore-user-config', '--ignore-rules'] + config_args(values) + ['-']
    return command


def marked_pids(needle):
    """Pids of this user's processes whose environment holds needle; None when unknown."""
    own = os.getpid()
    found = []
    if sys.platform.startswith('linux'):
        try:
            names = os.listdir('/proc')
        except OSError:
            return None
        for name in names:
            if not name.isdigit() or int(name) == own:
                continue
            try:
                with open('/proc/%s/environ' % name, 'rb') as handle:
                    if needle in handle.read():
                        found.append(int(name))
            except OSError:
                continue
        return found
    if sys.platform != 'darwin':
        return None
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        count = libc.proc_listallpids(None, 0)
        if count <= 0:
            return None
        pids = (ctypes.c_int * (count + 256))()
        count = libc.proc_listallpids(pids, ctypes.sizeof(pids))
        argmax = ctypes.c_int(0)
        size = ctypes.c_size_t(ctypes.sizeof(argmax))
        if libc.sysctl((ctypes.c_int * 2)(1, 8), 2, ctypes.byref(argmax), ctypes.byref(size),
                       None, 0) != 0:
            return None
        buffer = ctypes.create_string_buffer(argmax.value)
        for pid in pids[:max(count, 0)]:
            if pid <= 0 or pid == own:
                continue
            size = ctypes.c_size_t(argmax.value)
            # KERN_PROCARGS2: the arguments and the environment the process started with.
            if libc.sysctl((ctypes.c_int * 3)(1, 49, pid), 3, buffer, ctypes.byref(size),
                           None, 0) == 0 and needle in buffer.raw[:size.value]:
                found.append(pid)
    except (OSError, AttributeError):
        return None
    return found


def kill_leftovers(pgid, marker):
    """Kill what is left of a turn: (the group outlived codex, marked pids killed or None)."""
    group_left = False
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
            group_left = True
        except OSError:
            pass
    needle = ('%s=%s' % (MARKER, marker)).encode()
    killed = set()
    for _ in range(10):
        pids = marked_pids(needle)
        if pids is None:
            return group_left, None if not killed else len(killed)
        pids = [p for p in pids if p not in killed or _alive(p)]
        if not pids:
            break
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                killed.add(pid)
            except OSError:
                pass
        time.sleep(0.2)
    return group_left, len(killed)


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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


def new_job(where):
    name = 'job-' + secrets.token_hex(16)
    job = os.path.join(where['folder'], name)
    os.mkdir(job, 0o700)
    for folder in job_folders(job):
        os.mkdir(folder, 0o700)
    return name, job


def current_job(where, state):
    name = state.get('job')
    if isinstance(name, str) and JOB_RE.match(name):
        job = os.path.join(where['folder'], name)
        if os.path.isdir(job) and not os.path.islink(job):
            return job
    return None


def run_turn(args, codex, where):
    state = read_state(where)
    if args.fresh and state.get('job'):
        retire(where['folder'], state['job'])
        state = {}
        write_state(where, state)
    job = current_job(where, state)
    setup = name = None
    if job is None:
        if args.resume:
            refuse('no job to resume in (%s); start a new thread' % where['folder'])
        name, job = new_job(where)
    code, read = in_sandbox(codex, job, 'prompt', os.path.abspath(args.prompt_file))
    prompt = read.get('prompt')
    if code != 0 or not isinstance(prompt, str) or not prompt.strip():
        if name:
            retire(where['folder'], name)
        refuse(text_of(read, 'failure') or 'the prompt file could not be read (exit %d); is '
               'Codex installed?' % code)
    if name:
        code, setup = in_sandbox(codex, job, 'setup', where['worktree'], job)
        branch, base = setup.get('branch'), setup.get('base')
        if code != 0 or setup.get('status') != 'ready' or not isinstance(branch, str) \
                or not isinstance(base, str) or not SHA_RE.match(base):
            retire(where['folder'], name)
            refuse(text_of(setup, 'failure') or 'the setup of the job failed (exit %d)' % code)
        state = {'job': name, 'branch': branch, 'base': base, 'worktree': where['worktree'],
                 'created': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        write_state(where, state)
    branch = state.get('branch') if isinstance(state.get('branch'), str) else ''
    prompt = NOTE % {'work': os.path.join(job, 'work'), 'branch': branch} + prompt

    marker = secrets.token_hex(16)
    state['marker'] = marker
    write_state(where, state)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = log_folder()
    events = os.path.join(folder, stamp + '.jsonl')
    last_message = os.path.join(folder, stamp + '.last.txt')
    stderr_path = os.path.join(folder, stamp + '.stderr.txt')
    prompt_path = os.path.join(folder, stamp + '.prompt.txt')
    with open(prompt_path, 'w', encoding='utf-8') as handle:
        handle.write(prompt)

    command = codex_command(codex, args.model, args.resume, job, last_message, marker)
    limit = args.time_limit * 60
    timed_out = False
    # Files, not pipes, for stdin, stdout and stderr: a process that outlives codex and keeps a
    # pipe open would make this script wait for it.
    with open(prompt_path, 'rb') as stdin, open(events, 'wb') as out, \
            open(stderr_path, 'wb') as err:
        os.remove(prompt_path)
        process = subprocess.Popen(command, cwd=os.path.join(job, 'work'), stdin=stdin,
                                   stdout=out, stderr=err, start_new_session=True,
                                   env=dict(clean_environment(job), **{MARKER: marker}))
        try:
            returncode = process.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                returncode = process.wait()
    group_left, marked_killed = kill_leftovers(process.pid, marker)

    thread_id, completed, failure = read_events(events)
    try:
        with open(last_message, encoding='utf-8', errors='replace') as handle:
            last = handle.read()
    except OSError:
        last = ''
    report = {'status': 'failed', 'thread_id': thread_id or args.resume, 'model': args.model,
              'branch': branch, 'job': job, 'time_limit_minutes': args.time_limit,
              'timed_out': timed_out, 'group_left': group_left,
              'marked_killed': marked_killed, 'last_message': last, 'events': events}
    if setup is not None:
        report['setup'] = {key: setup.get(key) for key in
                           ('apfs_clones', 'files', 'withheld', 'withheld_count', 'seconds')}
    problems = []
    if timed_out:
        problems.append('the turn ran out of time (%g minutes) and was killed' % args.time_limit)
    elif returncode != 0:
        problems.append('codex exited %d' % returncode)
    if failure:
        problems.append(failure)
    elif not completed and not timed_out:
        problems.append('the turn did not complete')
    ok = not problems
    report['status'] = 'completed' if ok else 'failed'
    if not ok:
        try:
            with open(stderr_path, encoding='utf-8', errors='replace') as handle:
                stderr = handle.read()
        except OSError:
            stderr = ''
        report['failure'] = '; '.join(problems)
        report['stderr_tail'] = '\n'.join(line for line in stderr.splitlines()
                                          if 'PATH alias' not in line)[-2000:]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 1


# --- the export --------------------------------------------------------------------------------

def export(codex, where):
    state = read_state(where)
    job = current_job(where, state)
    base = state.get('base')
    if job is None or not isinstance(base, str) or not SHA_RE.match(base):
        refuse('no job for %s in %s' % (where['worktree'], where['folder']))
    killed = None
    if isinstance(state.get('marker'), str):
        # Hygiene: a process a turn left behind should not change the job while the bundle is cut.
        killed = kill_leftovers(None, state['marker'])[1]
    code, made = in_sandbox(codex, job, 'export', job, base)
    status = made.get('status')
    report = {'status': status if status in ('exported', 'nothing') and code == 0 else 'failed',
              'branch': text_of(made, 'branch', 300), 'base': base, 'head': None, 'commits': [],
              'bundle': None, 'marked_killed': killed}
    head = made.get('head')
    if isinstance(head, str) and SHA_RE.match(head):
        report['head'] = head
    for commit in made.get('commits') if isinstance(made.get('commits'), list) else []:
        if isinstance(commit, dict) and isinstance(commit.get('sha'), str) \
                and SHA_RE.match(commit['sha']):
            report['commits'].append({'sha': commit['sha'],
                                      'subject': text_of(commit, 'subject', 300)})
    if report['status'] == 'exported':
        report['bundle'] = os.path.join(job, 'out', 'codex.bundle')
    elif report['status'] == 'failed':
        report['failure'] = text_of(made, 'failure') or 'the export failed (exit %d)' % code
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report['status'] != 'failed' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run Codex in a job of an issue worktree.')
    parser.add_argument('worktree')
    parser.add_argument('--model')
    parser.add_argument('--prompt-file')
    parser.add_argument('--resume', metavar='THREAD_ID')
    parser.add_argument('--time-limit', type=float, default=60.0, metavar='MINUTES')
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args(argv)
    if args.export and (args.model or args.prompt_file or args.resume or args.fresh):
        parser.error('--export takes only the worktree')
    if not args.export and not (args.model and args.prompt_file):
        parser.error('a turn needs --model and --prompt-file')
    if args.fresh and args.resume:
        parser.error('--resume needs the job that --fresh removes')

    if not args.export:
        if not MODEL_RE.match(args.model):
            refuse('model %r is not a plain model id' % args.model)
        if args.resume is not None and not THREAD_RE.match(args.resume):
            refuse('thread id %r is not a Codex session id' % args.resume)
        if not 0 < args.time_limit <= 1440:
            refuse('the time limit is not between 0 and 1440 minutes')
    if sys.platform not in MEASURED or fcntl is None or not hasattr(os, 'killpg'):
        refuse('Codex\'s read deny list is measured on macOS only; this system (%s) is refused'
               % sys.platform)
    if not getattr(shutil.rmtree, 'avoids_symlink_attacks', False):
        refuse('this Python cannot remove a folder without following links')
    codex = shutil.which('codex')
    if not codex:
        refuse('no codex command on PATH')
    # The path as text: this script resolves no link in it and opens nothing below it.
    worktree = os.path.abspath(args.worktree)
    if any(ord(char) < 32 for char in worktree):
        refuse('the worktree path holds a control character')
    where = paths(worktree)
    held = lock(where)
    try:
        sweep(where)
        if args.export:
            return export(codex, where)
        return run_turn(args, codex, where)
    finally:
        held.close()


if __name__ == '__main__':
    sys.exit(main())
