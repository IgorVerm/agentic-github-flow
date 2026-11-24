#!/usr/bin/env python3
"""Run Codex as the worker of a Claude issue chat, in a job folder of its own.

Usage: python3 -I codex_worker.py <worktree> --model <model> --prompt-file <file>
                                  [--effort <effort>] [--resume <thread id>]
                                  [--time-limit <minutes>] [--fresh]
       python3 -I codex_worker.py <worktree> --export
       python3 -I codex_worker.py --sweep

The route of the `codex-worker` skill (issues #103, #107): the Claude issue chat stays
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
- **Codex's process** ignores the person's configuration and rules, and runs no hook, no shell
  snapshot and no MCP tool: apps (the ChatGPT account's connectors, on whenever Codex is logged
  in with ChatGPT, whatever the configuration), plugins and a skill's MCP install are off, since
  their tools run in Codex's process, outside its sandbox (`codex features list`, 2026-11-21).
  `codex sandbox` has no `--ignore-user-config` (0.171.0-alpha.13): the setup and the export
  load the person's configuration, which the chat cannot write, and override the profile.

**The profile** (`permissions.agf_codex_worker`), the same for the setup, a turn and the export:
write only the job's four folders (not `/tmp`, not `$TMPDIR`); no network; read the disk except
the read deny list. Its floor is all of `~/.claude` (Claude Code's sandbox denies the chat its
`file-history`, `daemon`, `ide`, `remote/run`, `bridge-spawn` and `seed-admin` folders; Codex
needs none of it), `~/.ssh`, `~/.aws`, `~/.netrc`, `~/.gnupg`, `~/.config/gh`,
`/private/tmp/cc-daemon-<uid>`, `/private/tmp/claude-<uid>/bash-edit-diff`, and any `.env`,
`.env.*`, `*.pem`, `*.key` or `*.p12`. On top of it comes, read at each run, what the settings
deny: the `Read(...)` deny rules and `sandbox.filesystem.denyRead` of `~/.claude/settings.json`
and the managed settings (files the chat's sandbox cannot write), and of the project's
`.claude/settings.json` and `settings.local.json` in the worktree the worker runs on, which are
the chat's files and so are read inside Codex's sandbox; the job keeps those it was made under,
for every later turn and the export. That is the merge condition the maintainer set on
2026-11-21 (#107): the floor and the person's settings hold in every case; a project's read
limits bind the worktree the worker is given, not a chat that names another worktree. What the profile cannot express refuses the run: a rule of
another form than `**/name`, `~/path` and `//path` (a denyRead entry also `/path`, in the
person's own settings), an optional trailing `/**` aside; `sandbox.credentials`;
`permissions.blockReadsOutsideWorkingDirectories`; and a settings source this script does not
read: an MDM profile (`/Library/Managed Preferences/…/com.anthropic.claudecode.plist`),
server-managed settings (`~/.claude/remote-settings.json`), or `CLAUDE_CONFIG_DIR`,
`CLAUDE_CODE_MANAGED_SETTINGS_PATH` or `CLAUDE_CODE_REMOTE_SETTINGS_PATH` set. A session started
with `--settings <file>` can add read limits no file tells this script about. Measured on macOS with `codex sandbox`
(2026-11-21): each entry refused, `/private/tmp` ones also through `/tmp`, a pattern also inside
a writable folder, a folder named by `**/name` with its contents, a denied file also through a
symlink and for a new hard link; this script's folder, Python and `~/.codex` stay readable. The
prompt file is read under it too, so the chat cannot have a denied file sent to OpenAI.

It refuses (exit 3) before Codex starts unless: the system is macOS (the only one the profile
is measured on) with process groups; the settings' deny rules are readable and expressible;
this script's folder and Python lie outside the deny list; the model and the thread id are plain
values and the time limit is more than 0 and at most 1440 minutes; a resume finds its job; and
the setup accepts the worktree (the top of a linked worktree, on a branch with a commit, clean)
and the prompt file (a plain file of at most 1 MiB, not empty).

**A turn** is one `codex exec` (or `codex exec resume <thread id>`) in `<job>/work`, the prompt
on stdin after a fixed note on the git setup, in a process session of its own, with a time limit
(`--time-limit`, default 60 minutes). `--effort` sets Codex's reasoning effort for the turn, one
of `minimal`, `low`, `medium`, `high`, `xhigh` and `max` (any other value exits 2): since the
person's configuration is ignored, without it a turn runs at the model's own default (issue
#112; `low` for gpt-6.2-astra in Codex's model catalog, which lists `low` to `max` and `ultra`
for it, not `minimal`). `ultra` ("automatic task delegation") is left out until its sub-agents
are measured under the profile. The effort is passed on every turn it is given, a resume too: a
resume does not keep the effort of the turn before it (measured 2026-11-22 with
0.171.0-alpha.13 and gpt-6.2-astra: `turn_context.effort` in Codex's session file under
`~/.codex/sessions` read `xhigh`, then null on a resume without it, then `xhigh`, then `max` on
resumes with it; `--json` events do not carry it):

  codex exec [resume <thread id>] --json -o <last message> -m <model>
             --skip-git-repo-check --ignore-user-config --ignore-rules
             [-c model_reasoning_effort="<effort>"]
             -c approval_policy="never" -c tool_output_token_limit=2000
             -c default_permissions="agf_codex_worker"
             -c permissions.agf_codex_worker.filesystem={…}
             -c permissions.agf_codex_worker.network.enabled=false
             -c shell_environment_policy.set.GIT_DIR=… (GIT_WORK_TREE, TMPDIR, the marker)
             -c features.hooks=false -c features.shell_snapshot=false -c features.apps=false
             -c features.plugins=false -c features.skill_mcp_dependency_install=false -

**What a turn keeps in its context** (issue #149). Every request of a turn re-sends its whole
context, so the usage follows what stays in it. `tool_output_token_limit` caps each tool output
Codex keeps at `OUTPUT_TOKENS` (2,000 tokens, about 8,000 characters): measured on the model job
of pax_deorum#1019, 99% of the 14.6M characters of text output came from Codex's own commands
and 0.6% from the project's tools, so the cap belongs here, where it covers every command, not in
each project's tools; `codex_tools.py` adds a file with the full log of a tool's call. The note
tells Codex to send long output to a file and read the part it needs.

**A round** is one task the chat hands Codex in a prompt of its own (a part of the issue, a
round of a model); the chat decides where one ends, since it writes the prompts and reads the
last messages. Within a round `--resume` carries on the same thread: an answer to Codex's
question, a review finding, a turn the time limit cut. The next task in the same job is a turn
without `--resume`: a fresh thread, so the earlier rounds' context is not re-sent with every
request (about 11% of that job's input, estimated). The worker writes its hand-over: the note
names the job's commits since the base and adds the last turn's final message (its first
`HANDOVER_MAX` characters, kept in `state.json`), which the note asks Codex to write so that a
fresh thread can carry on from it. The report's `round` says which it was: `first` (a new job),
`next` (a fresh thread with the hand-over) or `resume`.

**The project's tools** (issue #116; `codex_tools.py`'s header owns them): when the worktree
holds `.agents/codex-tools.json`, it and the project's `Bash(...)` rules are read inside Codex's
sandbox (`codex_job.py tools`), and each tool is anchored in the Claude Code settings: its command
in a `Bash(...)` allow rule (no deny or ask rule) of the person's, the managed or the project's
settings, its network hosts and unix sockets in `sandbox.network` of the person's or the managed
settings, read here, outside. For the turn the worker starts one server per anchored tool with
`sandbox-exec`, in a profile of its own making (the job writable, the deny list, the tool's
grants), with fixed arguments, and for a network grant a forwarder (`/usr/bin/nc`) to that one
`host:port`; it opens none of the tools' files. Codex gets `AGF_CODEX_TOOLS_DIR` and
`AGF_CODEX_TOOLS` and a line per tool in the note. The servers stop when `codex` ends, before
the kill by the marker, which every tool carries too. A list that cannot be read refuses the turn.
Claude Code's hooks see the tools' runs no more than Codex's commands. For the chat: the list is
changed as the repository is, not for one issue; a tool the report's `tools` shows `refused` that
the issue needs is a question for the user, not a command to run for Codex.

Codex is never asked for an approval and cannot ask one: a question belongs in its final
message. When `codex` ends, or the time limit kills it, the worker kills what is left of the
turn: the process group, then every process of this user whose environment holds the turn's
marker (which catches a `setsid` double-fork). A process that leaves the group and drops its
environment survives inside Codex's sandbox; the kill is hygiene, not the boundary. Its report:
`status`, `thread_id` (for `--resume` and `codex resume`), `model`, `effort` (null without
`--effort`), `round`, `branch`, `job`,
`time_limit_minutes`, `timed_out`, `group_left`, `marked_killed`, `last_message` (Codex's final
message: all the Claude chat reads of a turn), `tools` (`served`: names; `refused`: name and
reason; `ended_early`: a server that ended before the turn, with its exit), `events` (the JSONL event log, kept with the last
message and Codex's stderr in `jobs/<key>/logs/`, beside the jobs and outside every folder Codex
writes, removed after 30 days or with the worktree's jobs, whichever comes first);
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
worktree: a lock in the worker's folder.

**The sweep** (`--sweep`, issue #111; also at the start of every turn and export) removes the
folder `jobs/<key>/` of each worktree that is gone, once `cleanup-merged` removed it: its jobs,
its `state.json`, its lock and its logs. The logs go with it, decided in #111 on the maintainer's
ask of 2026-11-22 ("kijk dat alles van codex opgeruimd wordt"): they matter while the issue is
open, and the issue's comments and the Codex thread keep what is worth keeping after it. A key folder that a run holds (its lock)
stays, and so does one whose worktree still exists. Loose log files that older versions left in
the worker's folder go after 30 days. `--sweep` takes nothing else, starts no `codex`, reads no
settings and runs no git. Its report: `status` (`swept`, `failed` with `failure`), `removed`
(each with its `worktree`, None when no run recorded one, and its number of log files, `logs`:
three per turn, and one `tool-<name>.txt` per listed tool), `kept`, `busy` (a gone worktree's folder that a run holds), `old_logs`. Every
run records its worktree in `state.json` when it takes the lock, so a live worktree's folder is
never taken for a gone one. A worktree whose path is missing for a while (an unmounted volume)
loses its jobs and logs at a sweep in that time. Exit: 0 swept; 1 failed; 2 usage; 3 refused.

Why the sweep keeps the rule above, outside every sandbox: it opens no file the chat or Codex
wrote. It reads only `jobs/<key>/state.json`, which only this script writes: Codex's profile
writes only a job's four folders below it, and Claude Code's sandbox cannot write
`~/.cache/agentic-github-flow` (the person's condition in `docs/install.md`). Of the worktree it
asks only whether its path exists (`lstat`), opening nothing there; a chat that makes a path
vanish only costs that worktree its job, as `--fresh` would. It looks into no job's `work`, `git`,
`tmp` or `out`. It acts only on names this script makes (`<key>`, `gone-…`), takes the lock first,
then renames the key folder to `jobs/gone-<random>`, out of every path a job's profile names, so
that a process a turn left behind cannot write into it while it goes, and removes it with
`shutil.rmtree`, which unlinks names and follows no link (the worker refuses a Python where it
would: `avoids_symlink_attacks`).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time

try:
    import fcntl
except ImportError:  # Windows: refused in main
    fcntl = None

HERE = os.path.dirname(os.path.abspath(__file__))
JOB_TOOL = os.path.join(HERE, 'codex_job.py')
TOOLS_TOOL = os.path.join(HERE, 'codex_tools.py')


def _load(path):
    # By its path: under `python3 -I` this script's folder is not on sys.path.
    spec = importlib.util.spec_from_file_location('codex_tools', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


codex_tools = _load(TOOLS_TOOL)
EFFORTS = ('minimal', 'low', 'medium', 'high', 'xhigh', 'max')  # Codex's efforts (#112)
MODEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
THREAD_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
SHA_RE = re.compile(r'^[0-9a-f]{40}([0-9a-f]{24})?$')
JOB_RE = re.compile(r'^job-[0-9a-f]{32}$')
KEY_RE = re.compile(r'^[0-9a-f]{16}$')
GONE_RE = re.compile(r'^gone-[0-9a-f]{32}$')
MEASURED = ('darwin',)  # the systems the permission profile is measured on
PROFILE = 'agf_codex_worker'
PARTS = ('work', 'git', 'tmp', 'out')
# The floor of the read deny list. All of ~/.claude: Claude Code's sandbox denies the chat its
# file-history, daemon, ide, remote/run, bridge-spawn and seed-admin folders, and Codex needs
# none of it (its own home is ~/.codex). The person's Read(...) deny rules are added at run time.
DENY_HOME = ('.claude', '.ssh', '.aws', '.netrc', '.gnupg', os.path.join('.config', 'gh'))
DENY_GLOBS = ('/**/.env', '/**/.env.*', '/**/*.pem', '/**/*.key', '/**/*.p12')
DENY_TMP = ('/private/tmp/cc-daemon-%d', '/private/tmp/claude-%d/bash-edit-diff')
# Where the person's deny rules live: files the chat's sandbox cannot write.
USER_SETTINGS = os.path.join('.claude', 'settings.json')
MANAGED_SETTINGS = '/Library/Application Support/ClaudeCode'
SETTINGS_MAX = 1024 * 1024
# Sources of Claude Code settings this script does not read (Claude Code 2.1.322): MDM profiles,
# server-managed settings, and a moved configuration folder. Any read limit there would be
# missing from Codex's deny list, so a run refuses when one may be in play (the maintainer, #107).
UNREAD_VARIABLES = ('CLAUDE_CONFIG_DIR', 'CLAUDE_CODE_MANAGED_SETTINGS_PATH',
                    'CLAUDE_CODE_REMOTE_SETTINGS_PATH')
MANAGED_PREFERENCES = ('/Library/Managed Preferences/%(user)s/com.anthropic.claudecode.plist',
                       '/Library/Managed Preferences/com.anthropic.claudecode.plist')
REMOTE_SETTINGS = os.path.join('.claude', 'remote-settings.json')
FEATURES_OFF = ('hooks', 'shell_snapshot', 'apps', 'plugins', 'skill_mcp_dependency_install')
# The cap on each tool output Codex keeps in its context (`tool_output_token_limit`, issue #149):
# about 8,000 characters. Measured on the job of pax_deorum#1019: 99% of the text output came
# from Codex's own commands, and an 8,000-character cap cuts 30% of it.
OUTPUT_TOKENS = 2000
HANDOVER_MAX = 6000  # characters of a turn's last message kept for the next round's hand-over
REPORT_MAX = 8 * 1024 * 1024  # a 1 MiB prompt, JSON-escaped
LOG_DAYS = 30
MARKER = 'CODEX_WORKER_TURN'
SECONDS = {'setup': 3600, 'prompt': 30, 'settings': 30, 'tools': 30, 'export': 600}
NOTE = '''[Note from the worker that started you]
You work in %(work)s on branch %(branch)s. It is a git repository, but it has no .git folder:
git reaches it through the GIT_DIR and GIT_WORK_TREE variables that every command of yours
already has, so `git status`, `git add` and `git commit` work as usual. Do not create a .git
folder, do not unset or change those variables, and never push (you have no network). Commit
your work on this branch. You cannot ask a question while you work: put a question or a blocker
in your final message. A command's output beyond about %(tokens)d tokens is cut in the middle:
send long output to a file under $TMPDIR and read the part you need. Write your final message so
that a fresh thread can carry on from it alone: what you did and committed, what is left, where
your outputs are, and any question.

'''
HANDOVER = '''[Hand-over from the earlier rounds of this job]
This job did earlier work in other threads, which are closed. Their commits are on your branch
since %(base)s (`git log --oneline %(base)s..HEAD`). The final message of the last turn follows;
build on it, and read the files rather than assume more.

%(message)s

'''


def refuse(message):
    print('codex_worker: refused: %s' % message, file=sys.stderr)
    sys.exit(3)


def toml_string(value):
    # A TOML basic string: JSON's escapes for backslash, quote and control characters are TOML's.
    return json.dumps(value, ensure_ascii=False)


# --- the worker's own folder -------------------------------------------------------------------

def cache_folder(create=True):
    # From the home folder ($HOME), not XDG_CACHE_HOME, which the chat could point where it
    # writes. A `HOME=…` prefix keeps the call inside Claude Code's sandbox (measured 2026-11-21:
    # an env-var prefix does not match `sandbox.excludedCommands`), where Codex cannot start.
    folder = os.path.join(os.path.realpath(os.path.expanduser('~')), '.cache',
                          'agentic-github-flow', 'codex-worker')
    if create:
        os.makedirs(folder, mode=0o700, exist_ok=True)
    return folder


def paths(worktree):
    key = hashlib.sha256(os.fsencode(worktree)).hexdigest()[:16]
    folder = os.path.join(cache_folder(), 'jobs', key)
    return {'folder': folder, 'state': os.path.join(folder, 'state.json'),
            'lock': os.path.join(folder, 'lock'), 'logs': os.path.join(folder, 'logs'),
            'worktree': worktree}


def take_lock(path):
    handle = open(path, 'a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def lock(where):
    """Take the worktree's lock and record the worktree in its state, so that a sweep never
    takes a live worktree's folder for a gone one. A sweep that removes the folder between its
    making and the lock (its worktree looked gone) is met by making it again."""
    for _ in range(3):
        os.makedirs(where['folder'], mode=0o700, exist_ok=True)
        try:
            handle = take_lock(where['lock'])
        except FileNotFoundError:
            continue
        if handle is None:
            refuse('another codex_worker run holds %s' % where['lock'])
        if os.path.exists(where['lock']):
            break
        handle.close()
    else:
        refuse('a sweep kept removing %s' % where['folder'])
    state = read_state(where)
    if state.get('worktree') != where['worktree']:
        state['worktree'] = where['worktree']
        write_state(where, state)
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


def remove(path):
    """Remove a name: a folder (not a link to one) with all below it, unlinking names and
    following no link (main refuses a Python whose rmtree would), else the name itself."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(info.st_mode):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def retire(folder, name):
    """Remove a job, or a worktree's key folder. It is renamed first, out of the paths a job's
    sandbox may write, so a process a turn left behind cannot refill it while it goes."""
    path = os.path.join(folder, name)
    if not os.path.lexists(path):
        return
    gone = os.path.join(folder, 'gone-' + secrets.token_hex(16))
    os.rename(path, gone)
    remove(gone)


def count_logs(folder):
    try:
        return len(os.listdir(folder)) if not os.path.islink(folder) else 0
    except OSError:
        return 0


def prune_logs(folder):
    """Remove the files in folder older than LOG_DAYS; return how many went."""
    cutoff = time.time() - LOG_DAYS * 86400
    removed = 0
    try:
        names = os.listdir(folder)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(folder, name)
        try:
            info = os.lstat(path)
            if info.st_mtime < cutoff and not stat.S_ISDIR(info.st_mode):
                os.remove(path)
                removed += 1
        except OSError:
            pass
    return removed


def sweep_jobs(skip=None):
    """Remove the key folder of each worktree that is gone (cleanup-merged ran): its jobs, its
    state, its lock and its logs, unless a run holds its lock; and what an interrupted sweep
    left. Reads only the state.json this script wrote; of the worktree only lstat. Loose log
    files of older versions in the worker's folder go after LOG_DAYS. Returns the report."""
    report = {'removed': [], 'kept': 0, 'busy': [], 'old_logs': 0}
    top = cache_folder(create=False)
    if not os.path.isdir(top) or os.path.islink(top):
        return report
    report['old_logs'] = prune_logs(top)
    jobs = os.path.join(top, 'jobs')
    try:
        names = sorted(os.listdir(jobs)) if not os.path.islink(jobs) else []
    except FileNotFoundError:
        names = []
    for name in names:
        folder = os.path.join(jobs, name)
        if GONE_RE.match(name):
            remove(folder)
            continue
        if folder == skip or not KEY_RE.match(name) or os.path.islink(folder) \
                or not os.path.isdir(folder):
            continue
        worktree = read_state({'state': os.path.join(folder, 'state.json')}).get('worktree')
        if not isinstance(worktree, str) or not os.path.isabs(worktree):
            worktree = None
        if worktree is not None and os.path.lexists(worktree):
            report['kept'] += 1
            continue
        held = take_lock(os.path.join(folder, 'lock'))
        if held is None:
            report['busy'].append(worktree)
            continue
        try:
            logs = count_logs(os.path.join(folder, 'logs'))
            retire(jobs, name)
        finally:
            held.close()
        report['removed'].append({'worktree': worktree, 'logs': logs})
    return report


def sweep(where):
    """At the start of a run: sweep_jobs for the other worktrees, and what an interrupted run
    left in this one."""
    sweep_jobs(skip=where['folder'])
    current = read_state(where).get('job')
    for name in os.listdir(where['folder']):
        if name.startswith(('job-', 'gone-')) and name != current:
            retire(where['folder'], name)


def job_folders(job):
    return [os.path.join(job, part) for part in PARTS]


# --- Codex's sandbox ---------------------------------------------------------------------------

def read_settings(path):
    """The JSON of a settings file, None when there is none; refuses one it cannot read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as error:
        refuse('cannot read %s: %s' % (path, error.strerror))
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > SETTINGS_MAX:
            refuse('%s is not a plain settings file' % path)
        data = handle.read(SETTINGS_MAX + 1)
    try:
        settings = json.loads(data.decode('utf-8'))
    except ValueError:
        refuse('%s is not valid JSON, so its Read deny rules are unknown' % path)
    return settings if isinstance(settings, dict) else {}


def rule_path(rule, home):
    """The profile path of a Read(...) deny rule, None for a rule the profile cannot express.
    Claude Code's forms: `**/name` anywhere, `~/path` under the home folder, `//path` absolute;
    a trailing `/**` denies the folder. Other forms (relative to a project or the current folder)
    and wildcards before the last name are not measured with Codex's profile."""
    body = rule[len('Read('):-1]
    if body.endswith('/**'):
        body = body[:-3]
    if body.startswith('**/'):
        path, rest = '/' + body, body[3:]
    elif body.startswith('~/'):
        path = rest = os.path.join(home, body[2:])
    elif body.startswith('//'):
        path = rest = body[1:]
    else:
        return None
    parent, name = os.path.split(rest)
    if not name or any(char in rest for char in '?[]{}') or '*' in parent or '**' in name \
            or '..' in rest.split('/'):
        return None
    return path


def sandbox_path(path, home, project):
    """The profile path of a `sandbox.filesystem.denyRead` entry (`~/path`, `//path`, and in the
    person's own settings `/path`, measured absolute there: this session's sandbox shows
    `/private/tmp/…` from `allowWrite` as written; an optional trailing `/**`), None for any
    other form or a wildcard."""
    body = path[:-3] if path.endswith('/**') else path
    if body.startswith('~/'):
        body = os.path.join(home, body[2:])
    elif body.startswith('//'):
        body = body[1:]
    elif project or not body.startswith('/'):
        return None
    if any(char in body for char in '*?[]{}') or '..' in body.split('/') or body == '/':
        return None
    return body


def settings_denials(settings, source, home, project=False):
    """The deny entries one settings file adds: its Read(...) deny rules and its
    `sandbox.filesystem.denyRead`. Refuses what the profile cannot hold: a rule of another
    form, `sandbox.credentials`, `permissions.blockReadsOutsideWorkingDirectories`."""
    if not isinstance(settings, dict):
        return []
    permissions, sandbox = settings.get('permissions') or {}, settings.get('sandbox') or {}
    if not isinstance(permissions, dict) or not isinstance(sandbox, dict):
        refuse('%s: permissions or sandbox is not an object' % source)
    if permissions.get('blockReadsOutsideWorkingDirectories'):
        refuse('%s: blockReadsOutsideWorkingDirectories cannot be carried into Codex\'s profile'
               % source)
    if sandbox.get('credentials'):
        refuse('%s: sandbox.credentials is not measured with Codex\'s profile' % source)
    filesystem = sandbox.get('filesystem') or {}
    rules = permissions.get('deny') or []
    reads = filesystem.get('denyRead') or [] if isinstance(filesystem, dict) else None
    if not isinstance(rules, list) or not isinstance(reads, list):
        refuse('%s: permissions.deny or sandbox.filesystem.denyRead is not a list' % source)
    found = []
    for rule in rules:
        if not isinstance(rule, str) or not (rule == 'Read' or rule.startswith('Read(')):
            continue
        entry = rule_path(rule, home) if rule.endswith(')') else None
        if entry is None:
            refuse('%s: the deny rule %r has a form Codex\'s profile is not measured with; '
                   'write it as **/name, ~/path or //path' % (source, rule))
        found.append(entry)
    for path in reads:
        entry = sandbox_path(path, home, project) if isinstance(path, str) else None
        if entry is None:
            refuse('%s: denyRead entry %r has a form Codex\'s profile is not measured with; '
                   'write it as ~/path or //path' % (source, path))
        found.append(entry)
    return found


def add_denied(entries):
    for entry in entries:
        if entry not in DENIED:
            DENIED.append(entry)


def unread_sources():
    """The settings sources in play that this script does not read: refused in main."""
    found = ['$%s' % name for name in UNREAD_VARIABLES if os.environ.get(name)]
    try:
        import pwd
        user = pwd.getpwuid(os.getuid()).pw_name
    except (ImportError, KeyError, AttributeError):
        user = ''
    home = os.path.realpath(os.path.expanduser('~'))
    paths = [pattern % {'user': user} for pattern in MANAGED_PREFERENCES]
    paths.append(os.path.join(home, REMOTE_SETTINGS))
    found += [path for path in paths if os.path.lexists(path)]
    return found


def settings_files(home):
    """The person's and the managed Claude Code settings: files the chat's sandbox cannot write."""
    files = [os.path.join(home, USER_SETTINGS), os.path.join(MANAGED_SETTINGS,
                                                             'managed-settings.json')]
    drop_in = os.path.join(MANAGED_SETTINGS, 'managed-settings.d')
    if os.path.isdir(drop_in):
        files += sorted(os.path.join(drop_in, name) for name in os.listdir(drop_in)
                        if name.endswith('.json'))
    return files


def strings(value):
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def tool_anchors(home):
    """The anchors of the project's tools (codex_tools.py's header) in the person's and the
    managed settings: their Bash allow rules, their Bash ask and deny rules (an ask counts as a
    deny: no one can be asked), and their sandbox's allowed domains and unix sockets."""
    rules, network = {'allow': [], 'deny': []}, {'domains': [], 'sockets': []}
    managed = {'allow': [], 'domains': []}
    only = {'rules': False, 'domains': False}
    person = os.path.join(home, USER_SETTINGS)
    for path in settings_files(home):
        settings = read_settings(path)
        if not isinstance(settings, dict):
            continue
        permissions, sandbox = settings.get('permissions') or {}, settings.get('sandbox') or {}
        net = sandbox.get('network') or {} if isinstance(sandbox, dict) else {}
        if not isinstance(permissions, dict) or not isinstance(net, dict):
            refuse('%s: permissions or sandbox.network is not an object' % path)
        allow = codex_tools.bash_patterns(strings(permissions.get('allow')))
        rules['allow'] += allow
        rules['deny'] += codex_tools.bash_patterns(strings(permissions.get('ask')) +
                                                   strings(permissions.get('deny')))
        network['domains'] += strings(net.get('allowedDomains'))
        network['sockets'] += strings(net.get('allowUnixSockets'))
        if path != person:
            # Managed settings may let only their own rules or domains count (Claude Code's
            # allowManagedPermissionRulesOnly and allowManagedDomainsOnly): then so here.
            managed['allow'] += allow
            managed['domains'] += strings(net.get('allowedDomains'))
            only['rules'] |= bool(settings.get('allowManagedPermissionRulesOnly') or
                                  permissions.get('allowManagedPermissionRulesOnly'))
            only['domains'] |= bool(net.get('allowManagedDomainsOnly') or
                                    settings.get('allowManagedDomainsOnly'))
    if only['domains']:
        network['domains'] = managed['domains']
    if only['rules']:
        rules['allow'] = managed['allow']
    rules['managed_only'] = only['rules']
    return rules, network


def turn_tools(codex, job, worktree):
    """The project's tools for this turn: (served specs, refused [{name, reason}]). The list and
    the project's Bash rules are the chat's files, read inside Codex's sandbox; the network
    anchors only from the person's and the managed settings, which a project never widens."""
    code, read = in_sandbox(codex, job, 'tools', worktree)
    if code != 0 or read.get('status') != 'read':
        return None, text_of(read, 'failure') or 'the project\'s tool list could not be read ' \
            '(exit %d)' % code
    if read.get('list') is None:
        return ([], []), None
    home = os.path.realpath(os.path.expanduser('~'))
    rules, network = tool_anchors(home)
    project = read.get('rules') if isinstance(read.get('rules'), dict) else {}
    allow = rules['allow'] + ([] if rules['managed_only'] else
                              codex_tools.bash_patterns(strings(project.get('allow'))))
    deny = rules['deny'] + codex_tools.bash_patterns(strings(project.get('ask')) +
                                                     strings(project.get('deny')))
    return codex_tools.check_tools(read['list'], {'allow': allow, 'deny': deny}, network,
                                   home), None


def deny_list():
    """The read deny list: the floor above, and what the person's settings and the managed
    settings deny, read now so that no copy drifts. The project's settings in the worktree are
    the chat's files, so they are read inside Codex's sandbox (`project_denials`). Refuses what
    the profile cannot express: running with less than Claude Code's sandbox denies is the
    defect of issue #107."""
    home = os.path.realpath(os.path.expanduser('~'))
    denied = [os.path.join(home, name) for name in DENY_HOME] + list(DENY_GLOBS)
    if hasattr(os, 'getuid'):
        denied += [pattern % os.getuid() for pattern in DENY_TMP]
    for path in settings_files(home):
        for entry in settings_denials(read_settings(path), path, home):
            if entry not in denied:
                denied.append(entry)
    return denied


DENIED = []  # filled by main before any profile is made


def outside_denied(path):
    """True when path lies under no denied folder of the list."""
    real = os.path.realpath(path)
    return not any(real == entry or real.startswith(entry.rstrip('/') + '/')
                   for entry in DENIED if not entry.startswith('/**/'))


def project_denials(codex, job, worktree):
    """What the project's `.claude/settings.json` and `settings.local.json` in <worktree> deny;
    None when they cannot be read. They are the chat's files, so they are read inside Codex's
    sandbox (codex_job.py `settings`). The maintainer's ruling of 2026-11-21 (#107) binds the
    project settings of the worktree the worker runs on: a chat that names another worktree is not
    held to its own project's read limits; the floor and the person's settings hold in every
    case."""
    code, read = in_sandbox(codex, job, 'settings', worktree)
    files = read.get('settings')
    if code != 0 or read.get('status') != 'read' or not isinstance(files, dict):
        return None
    home = os.path.realpath(os.path.expanduser('~'))
    found = []
    for name in sorted(files):
        found += settings_denials(files[name], os.path.join(worktree, '.claude', str(name)),
                                  home, project=True)
    return found


def job_denials(codex, job, where, state, name=None):
    """Add the project denials the job was made under (kept in its state) and what the project
    denies now, for every later call on the job, the export included; return them all. A refusal
    removes a job this run made."""
    stored = state.get('project_denied')
    kept = [entry for entry in stored if isinstance(entry, str) and entry.startswith('/')] \
        if isinstance(stored, list) else []
    add_denied(kept)
    try:
        fresh = project_denials(codex, job, where['worktree'])
        if fresh is None:
            refuse('the project\'s Claude Code settings could not be read inside Codex\'s '
                   'sandbox')
    except SystemExit:
        if name:
            retire(where['folder'], name)
        raise
    add_denied(fresh)
    return kept + [entry for entry in fresh if entry not in kept]


def profile_config(job):
    """The `-c` values of the permission profile: the job writable, the deny list unreadable."""
    entries = [(':root', 'read')] + [(folder, 'write') for folder in job_folders(job)]
    entries += [(entry, 'deny') for entry in DENIED]
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

def log_folder(where):
    """The worktree's log folder, beside its jobs, so that the sweep removes them together."""
    folder = where['logs']
    os.makedirs(folder, mode=0o700, exist_ok=True)
    prune_logs(folder)
    return folder


def codex_command(codex, model, effort, resume, job, last_message, marker, extra=None):
    command = [codex, 'exec']
    if resume:
        command += ['resume', resume]
    work, tmp = os.path.join(job, 'work'), os.path.join(job, 'tmp')
    variables = {'GIT_DIR': os.path.join(job, 'git'), 'GIT_WORK_TREE': work, 'TMPDIR': tmp,
                 'TMP': tmp, 'TEMP': tmp, MARKER: marker}
    variables.update(extra or {})
    values = ['model_reasoning_effort=%s' % toml_string(effort)] if effort else []
    values += ['approval_policy="never"', 'tool_output_token_limit=%d' % OUTPUT_TOKENS]
    values += profile_config(job)
    values += ['shell_environment_policy.set.%s=%s' % (name, toml_string(value))
               for name, value in variables.items()]
    # Off: hooks and the shell snapshot run outside Codex's sandbox; apps (the ChatGPT account's
    # connectors, on whenever Codex is logged in with ChatGPT, whatever the configuration) and
    # plugins and a skill's MCP install bring MCP tools that run outside it.
    values += ['features.%s=false' % name for name in FEATURES_OFF]
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
            for folder in job_folders(job):
                # Codex and the tools write these four folders: a link put in place of one (or
                # anything but a folder) refuses the job, since a profile would name its target.
                # lstat only: nothing in them is opened.
                try:
                    info = os.lstat(folder)
                except OSError:
                    info = None
                if info is None or not stat.S_ISDIR(info.st_mode):
                    refuse('%s is no longer a folder of the job (a link or a file put in its '
                           'place); start again with --fresh' % folder)
            return job
    return None


def run_turn(args, codex, where):
    state = read_state(where)
    if args.fresh and state.get('job'):
        retire(where['folder'], state['job'])
        state = {'worktree': where['worktree']}
        write_state(where, state)
    job = current_job(where, state)
    setup = name = None
    if job is None:
        if args.resume:
            refuse('no job to resume in (%s); start a new thread' % where['folder'])
        name, job = new_job(where)
    project = job_denials(codex, job, where, state, name)
    code, read = in_sandbox(codex, job, 'prompt', os.path.abspath(args.prompt_file))
    prompt = read.get('prompt')
    if code != 0 or not isinstance(prompt, str) or not prompt.strip():
        if name:
            retire(where['folder'], name)
        refuse(text_of(read, 'failure') or 'the prompt file could not be read (exit %d); is '
               'Codex installed?' % code)
    try:
        found, problem = turn_tools(codex, job, where['worktree'])
        if found is None:
            refuse(problem)
    except SystemExit:
        if name:
            retire(where['folder'], name)
        raise
    served, refused_tools = found
    if name:
        code, setup = in_sandbox(codex, job, 'setup', where['worktree'], job)
        branch, base = setup.get('branch'), setup.get('base')
        if code != 0 or setup.get('status') != 'ready' or not isinstance(branch, str) \
                or not isinstance(base, str) or not SHA_RE.match(base):
            retire(where['folder'], name)
            refuse(text_of(setup, 'failure') or 'the setup of the job failed (exit %d)' % code)
        state = {'job': name, 'branch': branch, 'base': base, 'worktree': where['worktree'],
                 'created': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    state['project_denied'] = project
    write_state(where, state)
    branch = state.get('branch') if isinstance(state.get('branch'), str) else ''
    # A round (the header): a turn without --resume in a job that has one starts a fresh thread,
    # with the last turn's final message as its hand-over.
    kind = 'first' if name else 'resume' if args.resume else 'next'
    handover = ''
    if kind == 'next':
        message = state.get('handover') if isinstance(state.get('handover'), str) else ''
        handover = HANDOVER % {'base': state.get('base'),
                               'message': message.strip() or '(the last turn left none)'}
    prompt = NOTE % {'work': os.path.join(job, 'work'), 'branch': branch,
                     'tokens': OUTPUT_TOKENS} + \
        codex_tools.note(served, sys.executable) + handover + prompt

    marker = secrets.token_hex(16)
    state['marker'] = marker
    write_state(where, state)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = log_folder(where)
    events = os.path.join(folder, stamp + '.jsonl')
    last_message = os.path.join(folder, stamp + '.last.txt')
    stderr_path = os.path.join(folder, stamp + '.stderr.txt')
    prompt_path = os.path.join(folder, stamp + '.prompt.txt')
    with open(prompt_path, 'w', encoding='utf-8') as handle:
        handle.write(prompt)

    # The tools' servers: each in a sandbox of its own, with the job's variables and the marker,
    # so that the kill below also finds what a tool left behind.
    tmp = os.path.join(job, 'tmp')
    broker = codex_tools.Broker(job, DENIED, served, os.environ, {
        'GIT_DIR': os.path.join(job, 'git'), 'GIT_WORK_TREE': os.path.join(job, 'work'),
        'TMPDIR': tmp, 'TMP': tmp, 'TEMP': tmp, MARKER: marker})
    extra = {}
    if served:
        extra = {'AGF_CODEX_TOOLS_DIR': broker.tools_dir,
                 'AGF_CODEX_TOOLS': ','.join(spec['name'] for spec in served)}
    command = codex_command(codex, args.model, args.effort, args.resume, job, last_message,
                            marker, extra)
    limit = args.time_limit * 60
    timed_out = False
    # Files, not pipes, for stdin, stdout and stderr: a process that outlives codex and keeps a
    # pipe open would make this script wait for it.
    try:
        broker.start(folder)
    except OSError as error:
        broker.stop()
        refuse('the project\'s tools could not be started: %s' % error)
    try:
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
    finally:
        broker.stop()
    group_left, marked_killed = kill_leftovers(process.pid, marker)

    thread_id, completed, failure = read_events(events)
    try:
        with open(last_message, encoding='utf-8', errors='replace') as handle:
            last = handle.read()
    except OSError:
        last = ''
    if last.strip():
        # Codex's own text, kept as text for the next round's prompt; only this script reads it.
        state['handover'] = last[:HANDOVER_MAX]
        write_state(where, state)
    report = {'status': 'failed', 'thread_id': thread_id or args.resume, 'model': args.model,
              'effort': args.effort, 'round': kind, 'branch': branch, 'job': job,
              'time_limit_minutes': args.time_limit, 'timed_out': timed_out,
              'group_left': group_left,
              'marked_killed': marked_killed, 'last_message': last, 'events': events,
              'tools': {'served': [spec['name'] for spec in served], 'refused': refused_tools,
                        'ended_early': broker.ended}}
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
    job_denials(codex, job, where, state)
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
    parser.add_argument('worktree', nargs='?')
    parser.add_argument('--model')
    parser.add_argument('--prompt-file')
    parser.add_argument('--effort', choices=EFFORTS)
    parser.add_argument('--resume', metavar='THREAD_ID')
    parser.add_argument('--time-limit', type=float, metavar='MINUTES')
    parser.add_argument('--fresh', action='store_true')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--sweep', action='store_true')
    args = parser.parse_args(argv)
    if args.sweep:
        if args.fresh or args.export or any(value is not None for value in (
                args.worktree, args.model, args.prompt_file, args.effort, args.resume,
                args.time_limit)):
            parser.error('--sweep takes nothing else')
        # No codex, no settings, no git: only the worker's own folder (the header's sweep).
        if fcntl is None:
            refuse('this system has no file locks, so a running job cannot be told apart')
        if not getattr(shutil.rmtree, 'avoids_symlink_attacks', False):
            refuse('this Python cannot remove a folder without following links')
        try:
            report = dict(status='swept', **sweep_jobs())
        except OSError as error:
            report = {'status': 'failed', 'failure': '%s: %s' % (error.strerror, error.filename)}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report['status'] == 'swept' else 1
    if args.worktree is None:
        parser.error('the worktree is required, except with --sweep')
    if args.time_limit is None:
        args.time_limit = 60.0
    if args.export and (args.model or args.prompt_file or args.effort or args.resume
                        or args.fresh):
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
    unread = unread_sources()
    if unread:
        refuse('Claude Code settings this worker does not read may limit reads here (%s); '
               'Codex\'s deny list could miss them' % ', '.join(unread))
    DENIED[:] = deny_list()
    for program in (JOB_TOOL, TOOLS_TOOL, sys.executable):
        if not outside_denied(program):
            refuse('%s lies in a folder Codex may not read; install the plugin outside ~/.claude'
                   % program)
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
