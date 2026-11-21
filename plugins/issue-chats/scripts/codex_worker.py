#!/usr/bin/env python3
"""Run Codex as the worker of a Claude issue chat, in a disposable clone of the chat's branch.

Usage: python3 codex_worker.py <worktree> --model <model> --prompt-file <file>
                               [--resume <thread id>] [--time-limit <minutes>] [--fresh]
       python3 codex_worker.py <worktree> --export

The route of method.md *Codex as the worker* (issues #103, #107): the Claude issue chat stays
the owner of the issue and the person's interface, and hands the implementation to Codex. One
tool, so that a single narrow allow rule and one `sandbox.excludedCommands` entry cover it,
instead of rules on `codex exec *`, which would also admit
`--dangerously-bypass-approvals-and-sandbox`, `--sandbox danger-full-access` or
`--approve-for-me`. Codex needs the network and writes its sessions under `~/.codex`, so it
cannot run inside Claude Code's sandbox (measured 2026-11-20). Because the allow rule lets this
script run outside that sandbox without a prompt, it takes no program to run: `codex` is the one
on PATH (changing PATH needs an environment assignment in front, which the rule does not match).

**Codex never writes the chat's repository.** It works in a clone of its own,
`<git folder>/codex/clone` (the worktree's git folder), made from the chat's HEAD with
`git clone --shared --no-checkout`, without a remote. On macOS its tracked files are APFS clones
of the worktree's (copy-on-write; measured on pax_deorum: 16,878 files, 13 GiB, no measurable
disk, a 59 s re-hash once per clone), elsewhere git checks them out. Codex's objects go into the
clone; the chat's object store is only its alternate, which it reads.

It refuses (exit 3) before Codex starts unless:
- the system has process groups (not Windows): the kill after the turn needs them;
- <worktree> is the top of a linked git worktree, never a primary checkout, on a branch with a
  commit, and clean (no change, no untracked file), so that the clone holds all of its work;
- the model and the thread id are plain values, the time limit is 1 to 1440 minutes, a resume
  finds the clone, and the clone was made from this branch;
- the prompt file is a plain file of this user (no link, no second hard link, opened without
  following a link and checked on the open file) in this process's temporary folder or Claude
  Code's per-user one (`/tmp/claude-<uid>`, where a sandboxed chat writes), never `/tmp` itself
  and outside Claude Code's private folders (`bash-edit-diff`, `plugin-tool-staging`,
  `cc-daemon-<uid>`): its text goes to OpenAI, so it never reads a key, an `.env` or a file in
  the home folder.

**A turn** is one `codex exec` (or `codex exec resume <thread id>`) in the clone, the prompt on
stdin, in a process session of its own, with a time limit (`--time-limit`, default 60 minutes):

  codex exec [resume <thread id>] --json -o <last message> -m <model>
             -c approval_policy="never" -c sandbox_mode="workspace-write"
             -c sandbox_workspace_write.network_access=false
             -c sandbox_workspace_write.exclude_slash_tmp=true
             -c sandbox_workspace_write.exclude_tmpdir_env_var=true
             -c sandbox_workspace_write.writable_roots=[<clone>, <clone>/.git, <codex tmp>]
             -c shell_environment_policy.set.CODEX_WORKER_TURN="<marker>" -

Codex's own sandbox is the boundary. Codex reads the whole disk (`workspace-write` reads
everything) and writes only the clone and its own temporary folder `<git folder>/codex/tmp`
(its `TMPDIR`, emptied before each turn; `/tmp` and the caller's temporary folder are closed to
it). It has no network, so it cannot push. It is never asked for an approval and cannot ask one:
a question belongs in its final message. Nothing here passes a `--dangerously-*` option or
another sandbox mode. When `codex` ends, or the time limit kills it, the worker kills what is
left of the turn: the process group, then every process of this user whose environment holds the
turn's marker (which catches a `setsid` double-fork). A process that leaves the group and drops
its environment survives, but it stays inside Codex's sandbox. The kill is hygiene; the boundary
is that no git outside a sandbox reads a file Codex wrote as configuration. So a turn runs no git
on the clone. Its report: `status`, `thread_id` (for `--resume` and `codex resume`), `model`,
`branch`, `clone`, `time_limit_minutes`, `timed_out`, `group_left` (processes of the group
outlived `codex`), `marked_killed` (marked processes killed), `last_message` (Codex's final
message: all the Claude chat reads of a turn), `events` (the JSONL event log, kept with the last
message in `${XDG_CACHE_HOME:-~/.cache}/agentic-github-flow/codex-worker/`, outside every folder
Codex writes, and removed after 30 days). Exit: 0 the turn completed; 1 Codex failed, timed out
or the turn did not complete; 2 usage; 3 refused before Codex started.

**The export** (`--export`, once, when Codex's work is done) cuts a git bundle of Codex's commits
on top of the chat's HEAD, at `<git folder>/codex/codex.bundle`, for `codex_import.py`, which
the Claude chat runs inside its own sandbox. It reads the clone's branch ref as a file, without
following a link, and runs git only in a fresh bare repository of its own, whose objects come
from the clone's as an alternate and whose configuration is the worker's (no fsmonitor, no
commit-graph, no multi-pack index, no submodules). So git never reads a configuration, hook or
index that Codex wrote. Its report: `status` (`exported`, `nothing` when Codex made no commit,
`failed`), `branch`, `base` (the chat's HEAD), `head`, `commits` (`sha`, `subject`, oldest first),
`bundle`. Exit: 0 exported or nothing; 1 failed (the clone's branch is missing, unreadable or not
on top of the chat's HEAD); 3 refused.

`--fresh` removes the clone first, for a new start from the chat's HEAD. The worktree's removal
(`cleanup-merged`) removes the clone with the git folder. One worker at a time per worktree:
a lock in `<git folder>/codex/lock`.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

try:
    import fcntl
except ImportError:  # Windows: refused in main
    fcntl = None

MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
THREAD_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}([0-9a-f]{24})?$')
PROMPT_MAX = 1024 * 1024
LOG_DAYS = 30
MARKER = 'CODEX_WORKER_TURN'
# Every git call of this script runs outside every sandbox, and only on repositories Codex never
# wrote: the chat's worktree, the fresh clone before Codex starts, and the export repository.
GIT_SAFE = ['-c', 'core.fsmonitor=false', '-c', 'submodule.recurse=false']
EXPORT_SAFE = GIT_SAFE + ['-c', 'core.commitGraph=false', '-c', 'core.multiPackIndex=false',
                          '-c', 'core.hooksPath=' + os.devnull]


def refuse(message):
    print('codex_worker: refused: %s' % message, file=sys.stderr)
    sys.exit(3)


def git(cwd, *args, env=None):
    result = subprocess.run(['git', '-C', cwd] + GIT_SAFE + list(args), capture_output=True,
                            text=True, env=env)
    if result.returncode != 0:
        return None
    return result.stdout.rstrip('\n')


def toml_string(value):
    # A TOML basic string: JSON's escapes for backslash, quote and control characters are TOML's.
    return json.dumps(value, ensure_ascii=False)


def temp_roots():
    # This process's temporary folder, and Claude Code's per-user one, where a sandboxed chat
    # writes ($TMPDIR inside the sandbox differs from the one an excluded call sees). Never all
    # of /tmp, which holds other users' and Claude Code's private folders.
    uid = os.getuid() if hasattr(os, 'getuid') else None
    roots = {tempfile.gettempdir()}
    if uid is not None:
        roots |= {'/tmp/claude-%d' % uid, '/private/tmp/claude-%d' % uid}
    roots = {os.path.realpath(r) for r in roots if os.path.isdir(r)}
    return sorted(r for r in roots if r not in ('/tmp', '/private/tmp', '/var/tmp', '/'))


def prompt_denied():
    uid = os.getuid() if hasattr(os, 'getuid') else 0
    return ('bash-edit-diff', 'plugin-tool-staging', 'cc-daemon-%d' % uid)


def check_prompt(path):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        refuse('cannot open the prompt file without following a link: %s' % error)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            refuse('the prompt file is not a plain file (a link, a hard link or a folder)')
        if hasattr(os, 'getuid') and info.st_uid != os.getuid():
            refuse('the prompt file belongs to another user')
        parent = os.path.realpath(os.path.dirname(os.path.abspath(path)))
        roots = temp_roots()
        if not any(parent == r or parent.startswith(r + os.sep) for r in roots) or \
                any(part in prompt_denied() for part in parent.split(os.sep)):
            refuse('the prompt file is not in your temporary folder (%s); its text goes to '
                   'OpenAI' % ', '.join(roots))
        if info.st_size > PROMPT_MAX:
            refuse('the prompt file is larger than %d bytes' % PROMPT_MAX)
        data = b''
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            data += block
            if len(data) > PROMPT_MAX:
                refuse('the prompt file is larger than %d bytes' % PROMPT_MAX)
    finally:
        os.close(fd)
    prompt = data.decode('utf-8', errors='replace')
    if not prompt.strip():
        refuse('the prompt file is empty')
    return prompt


def check_worktree(path):
    """Return (worktree, git dir, branch, head) or refuse."""
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
    git_dir = os.path.realpath(git_dir)
    if git_dir == os.path.realpath(common):
        refuse('%s is a primary checkout; Codex works only for a linked worktree' % path)
    branch = git(worktree, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    if not branch:
        refuse('HEAD of %s is not on a branch' % path)
    head = git(worktree, 'rev-parse', '--verify', '--quiet', 'HEAD')
    if not head:
        refuse('branch %s has no commit yet' % branch)
    status = git(worktree, 'status', '--porcelain', '--untracked-files=all')
    if status is None:
        refuse('git status failed in %s' % path)
    if status:
        refuse('%s has uncommitted changes; commit them first, so that the clone holds all of '
               'the work' % path)
    return worktree, git_dir, branch, head


# --- the clone -------------------------------------------------------------------------------

def paths(git_dir):
    folder = os.path.join(git_dir, 'codex')
    return {'folder': folder, 'clone': os.path.join(folder, 'clone'),
            'tmp': os.path.join(folder, 'tmp'), 'state': os.path.join(folder, 'state.json'),
            'export': os.path.join(folder, 'export.git'),
            'bundle': os.path.join(folder, 'codex.bundle'), 'lock': os.path.join(folder, 'lock')}


def lock(where):
    os.makedirs(where['folder'], mode=0o700, exist_ok=True)
    handle = open(where['lock'], 'a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        refuse('another codex_worker run holds %s' % where['lock'])
    return handle


def remove(path):
    # Only folders this script made under <git folder>/codex; rmtree does not follow links.
    if os.path.lexists(path):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


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


def clonefile_function():
    """macOS clonefile(2), or None."""
    if sys.platform != 'darwin':
        return None
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.clonefile
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
        return function
    except (OSError, AttributeError):
        return None


def fill_with_clones(worktree, clone):
    """APFS clones of the worktree's tracked regular files; git checks out the rest."""
    clonefile = clonefile_function()
    if clonefile is None:
        return 0
    listing = subprocess.run(['git', '-C', worktree] + GIT_SAFE + ['ls-files', '-z', '--stage'],
                             capture_output=True).stdout
    count = 0
    for entry in listing.split(b'\0'):
        meta, _, name = entry.partition(b'\t')
        if not name or meta.split(b' ')[0] not in (b'100644', b'100755'):
            continue
        source = os.path.join(os.fsencode(worktree), name)
        target = os.path.join(os.fsencode(clone), name)
        try:
            if not stat.S_ISREG(os.lstat(source).st_mode):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
        except OSError:
            continue
        if clonefile(source, target, 0) == 0:
            count += 1
    return count


def make_clone(worktree, branch, head, where):
    clone = where['clone']
    remove(clone)
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', 'clone', '-q', '--shared',
                             '--no-checkout', '--branch', branch, '--', worktree, clone],
                            capture_output=True, text=True)
    if result.returncode != 0:
        refuse('git clone failed: %s' % result.stderr.strip()[-500:])
    git(clone, 'remote', 'remove', 'origin')
    if git(clone, 'rev-parse', '--verify', '--quiet', 'HEAD') != head:
        refuse('the clone does not start at the worktree\'s HEAD')
    cloned = fill_with_clones(worktree, clone)
    # The index from HEAD (re-hashing the cloned files), then git writes what is missing or
    # differs. Codex has not run yet, so this is git on a repository of this script's own.
    if git(clone, 'reset', '-q') is None or git(clone, 'checkout', '-q', '--', '.') is None:
        refuse('git could not check out the clone')
    if git(clone, 'status', '--porcelain', '--untracked-files=all') != '':
        refuse('the new clone is not clean')
    return cloned


# --- the turn --------------------------------------------------------------------------------

def log_folder():
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    folder = os.path.join(base, 'agentic-github-flow', 'codex-worker')
    os.makedirs(folder, mode=0o700, exist_ok=True)
    cutoff = time.time() - LOG_DAYS * 86400
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        try:
            if os.lstat(path).st_mtime < cutoff and os.path.isfile(path):
                os.remove(path)
        except OSError:
            pass
    return folder


def codex_command(codex, model, resume, roots, last_message, marker):
    command = [codex, 'exec']
    if resume:
        command += ['resume', resume]
    command += ['--json', '-o', last_message, '-m', model,
                '-c', 'approval_policy="never"',
                '-c', 'sandbox_mode="workspace-write"',
                '-c', 'sandbox_workspace_write.network_access=false',
                '-c', 'sandbox_workspace_write.exclude_slash_tmp=true',
                '-c', 'sandbox_workspace_write.exclude_tmpdir_env_var=true',
                '-c', 'sandbox_workspace_write.writable_roots=[%s]'
                % ', '.join(toml_string(r) for r in roots),
                '-c', 'shell_environment_policy.set.%s=%s' % (MARKER, toml_string(marker)),
                '-']
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


def run_turn(args, prompt, codex, worktree, branch, head, where):
    state = read_state(where)
    if args.fresh:
        remove(where['clone'])
        state = {}
    if os.path.isdir(where['clone']):
        if state.get('branch') != branch:
            refuse('the clone in %s was made for another branch; start with --fresh'
                   % where['clone'])
    elif args.resume:
        refuse('no clone to resume in (%s); start a new thread' % where['clone'])
    else:
        cloned = make_clone(worktree, branch, head, where)
        state = {'branch': branch, 'base': head, 'apfs_clones': cloned,
                 'created': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    remove(where['tmp'])
    os.makedirs(where['tmp'], mode=0o700)
    marker = secrets.token_hex(16)
    state['marker'] = marker
    write_state(where, state)

    clone = where['clone']
    roots = [clone, os.path.join(clone, '.git'), where['tmp']]
    tmp = where['tmp']
    codex_env = dict(os.environ, TMPDIR=tmp, TMP=tmp, TEMP=tmp, **{MARKER: marker})
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = log_folder()
    events = os.path.join(folder, stamp + '.jsonl')
    last_message = os.path.join(folder, stamp + '.last.txt')
    stderr_path = os.path.join(folder, stamp + '.stderr.txt')
    prompt_path = os.path.join(folder, stamp + '.prompt.txt')
    with open(prompt_path, 'w', encoding='utf-8') as handle:
        handle.write(prompt)

    command = codex_command(codex, args.model, args.resume, roots, last_message, marker)
    limit = args.time_limit * 60
    timed_out = False
    # Files, not pipes, for stdin, stdout and stderr: a process that outlives codex and keeps a
    # pipe open would make this script wait for it.
    with open(prompt_path, 'rb') as stdin, open(events, 'wb') as out, \
            open(stderr_path, 'wb') as err:
        os.remove(prompt_path)
        process = subprocess.Popen(command, cwd=clone, stdin=stdin, stdout=out, stderr=err,
                                   env=codex_env, start_new_session=True)
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
              'branch': branch, 'clone': clone, 'time_limit_minutes': args.time_limit,
              'timed_out': timed_out, 'group_left': group_left,
              'marked_killed': marked_killed, 'last_message': last, 'events': events}
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


# --- the export ------------------------------------------------------------------------------

def read_file_nofollow(base, parts, limit):
    """The bytes of base/parts..., opened component by component without following a link."""
    flags_dir = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fds = []
    try:
        fd = os.open(base, flags_dir)
        fds.append(fd)
        for part in parts[:-1]:
            fd = os.open(part, flags_dir, dir_fd=fd)
            fds.append(fd)
        fd = os.open(parts[-1], os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0), dir_fd=fd)
        fds.append(fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = os.read(fd, limit + 1)
        return data if len(data) <= limit else None
    except OSError:
        return None
    finally:
        for fd in fds:
            os.close(fd)


def clone_tip(clone, branch):
    """The clone's commit for refs/heads/<branch>, read as a file; None when unreadable."""
    name = 'refs/heads/' + branch
    loose = read_file_nofollow(clone, ['.git'] + name.split('/'), 200)
    if loose is not None:
        value = loose.decode('ascii', errors='replace').strip()
        return value if SHA_RE.match(value) else None
    packed = read_file_nofollow(clone, ['.git', 'packed-refs'], 64 * 1024 * 1024)
    for line in (packed or b'').decode('utf-8', errors='replace').splitlines():
        sha, _, ref = line.partition(' ')
        if ref == name:
            return sha if SHA_RE.match(sha) else None
    return None


def export(worktree, branch, head, where):
    state = read_state(where)
    report = {'status': 'failed', 'branch': branch, 'base': head, 'head': None, 'commits': [],
              'bundle': None}
    if not os.path.isdir(where['clone']) or state.get('branch') != branch:
        refuse('no clone of branch %s in %s' % (branch, where['folder']))
    if state.get('marker'):
        # A process a turn left behind must not change the clone while the bundle is cut.
        report['marked_killed'] = kill_leftovers(None, state['marker'])[1]
    tip = clone_tip(where['clone'], branch)
    exp = where['export']
    remove(exp)
    remove(where['bundle'])
    object_format = git(worktree, 'rev-parse', '--show-object-format') or 'sha1'
    if subprocess.run(['git', 'init', '-q', '--bare', '--object-format=' + object_format, exp],
                      capture_output=True).returncode != 0:
        refuse('git could not make the export repository')
    with open(os.path.join(exp, 'objects', 'info', 'alternates'), 'w') as handle:
        handle.write(os.path.join(where['clone'], '.git', 'objects') + '\n')
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_NO_REPLACE_OBJECTS='1')
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
                 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_CONFIG', 'GIT_CONFIG_PARAMETERS',
                 'GIT_CONFIG_COUNT'):
        env.pop(name, None)

    def gx(*args, text=True):
        return subprocess.run(['git', '--git-dir=' + exp] + EXPORT_SAFE + list(args),
                              capture_output=True, text=text, env=env)

    problems = []
    if tip is None:
        problems.append('the clone has no readable ref refs/heads/%s (a plain file or '
                        'packed-refs)' % branch)
    elif gx('update-ref', 'refs/heads/codex', tip).returncode != 0:
        problems.append('the clone\'s commit %s is not in its objects' % tip)
    else:
        report['head'] = tip
        if tip == head:
            report['status'] = 'nothing'
        elif gx('merge-base', '--is-ancestor', head, tip).returncode != 0:
            problems.append('the clone\'s branch is not on top of the worktree\'s HEAD %s (Codex '
                            'rewrote history, or the chat committed since the clone); start '
                            'with --fresh' % head)
        else:
            listing = gx('log', '--reverse', '--format=%H%x09%s', '%s..%s' % (head, tip))
            for line in listing.stdout.splitlines():
                sha, _, subject = line.partition('\t')
                report['commits'].append({'sha': sha, 'subject': subject})
            made = gx('bundle', 'create', '-q', where['bundle'], 'refs/heads/codex', '^' + head)
            if made.returncode != 0:
                problems.append('git bundle create failed: %s' % made.stderr.strip()[-500:])
            else:
                report['status'] = 'exported'
                report['bundle'] = where['bundle']
    if problems:
        report['failure'] = '; '.join(problems)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if problems else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run Codex in a clone of an issue worktree.')
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
        parser.error('--resume needs the clone that --fresh removes')

    if not args.export:
        if not MODEL_RE.match(args.model):
            refuse('model %r is not a plain model id' % args.model)
        if args.resume is not None and not THREAD_RE.match(args.resume):
            refuse('thread id %r is not a Codex session id' % args.resume)
        if not 0 < args.time_limit <= 1440:
            refuse('the time limit is not between 0 and 1440 minutes')
        prompt = check_prompt(args.prompt_file)
        codex = shutil.which('codex')
        if not codex:
            refuse('no codex command on PATH')
    worktree, git_dir, branch, head = check_worktree(args.worktree)
    if fcntl is None or not hasattr(os, 'killpg'):
        refuse('this system has no process groups; the kill after the turn needs them')
    where = paths(git_dir)
    held = lock(where)
    try:
        if args.export:
            return export(worktree, branch, head, where)
        return run_turn(args, prompt, codex, worktree, branch, head, where)
    finally:
        held.close()


if __name__ == '__main__':
    sys.exit(main())
