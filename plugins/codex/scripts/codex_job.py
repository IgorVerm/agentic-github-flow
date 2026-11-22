#!/usr/bin/env python3
"""The part of the Codex worker that runs inside Codex's sandbox. Never run it yourself.

Usage (by codex_worker.py only, as `codex sandbox … -- python3 -I codex_job.py …`):
       codex_job.py setup <worktree> <job>
       codex_job.py prompt <file>
       codex_job.py settings <worktree>
       codex_job.py tools <worktree>
       codex_job.py export <job> <base>

`codex_worker.py` runs outside every sandbox, so it runs no git and opens no file that the
Claude chat or Codex wrote (the `codex-worker` skill, issue #107). Everything that has to
read such data runs here instead, under the same permission profile as Codex's own commands: it
writes only the job's folders, has no network and reads the disk minus the worker's deny list.
So a filter, hook or fsmonitor that the chat's repository or Codex's git folder names runs with
no more rights than Codex has, and a path the chat passes is read under that deny list.

A job is a folder of the worker's with `work` (the files Codex edits; it never holds a `.git`),
`git` (Codex's git folder, reached through GIT_DIR and GIT_WORK_TREE), `tmp` and `out`.

`setup` refuses (exit 3) unless <worktree> is the top of a linked git worktree, on a branch with
a commit, and clean. It then makes `<job>/git` with the chat's object store as an alternate
(Codex reads it and cannot write it), the branch at the chat's HEAD, and fills `<job>/work`: on
macOS each tracked regular file is an APFS clone of the worktree's file (copy-on-write, no disk),
and git checks out what is left. A tracked file that cannot exist in `work` (under a name
Codex's sandbox protects, `.codex` or `.agents` at the top, or one the deny list covers, such as
`.env`) is marked skip-worktree: Codex neither sees it as deleted nor commits its removal.

`prompt` prints a plain file of at most 1 MiB, for the worker to hand to Codex.

`settings` prints what the project's `.claude/settings.json` and `.claude/settings.local.json`
in <worktree> say about reads (`permissions.deny` Read rules,
`permissions.blockReadsOutsideWorkingDirectories`, `sandbox.filesystem.denyRead`,
`sandbox.credentials`), for the worker to add to the deny list. A file that is missing counts as
empty; one that is not a plain file of at most 1 MiB of JSON is refused.

`tools` prints the project's tool list `.agents/codex-tools.json` in <worktree> (`list`, None
without one; codex_tools.py's header owns it) and the `Bash(...)` allow, ask and deny rules of
the project's two settings files, for the worker to anchor each tool.

`export` cuts `<job>/out/codex.bundle`: Codex's commits on its branch on top of <base>, with
`log.showSignature` and `core.fsmonitor` off, since Codex wrote the git folder's config (a
signature check runs `gpg.program`). It runs under the job's full deny list, the project's
denials included.

Each prints one JSON object; exit 0, 1 failed, 3 refused.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time

PROMPT_MAX = 1024 * 1024
BUNDLE = 'codex.bundle'


class Refused(Exception):
    pass


class Failed(Exception):
    pass


def run(args, env=None, data=None):
    return subprocess.run(['git'] + list(args), capture_output=True, env=env, input=data)


def git(*args, env=None, error=Failed):
    result = run(args, env=env)
    if result.returncode != 0:
        raise error('git %s failed: %s' % (' '.join(args[:3]),
                                           result.stderr.decode('utf-8', 'replace').strip()[-400:]))
    return result.stdout.decode('utf-8', 'replace').rstrip('\n')


def clonefile_function():
    """macOS clonefile(2), or None."""
    if sys.platform != 'darwin':
        return None
    try:
        import ctypes
        function = ctypes.CDLL(None, use_errno=True).clonefile
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
        return function
    except (OSError, AttributeError):
        return None


def job_env(job):
    env = {name: value for name, value in os.environ.items() if not name.startswith('GIT_')}
    env.update(GIT_DIR=os.path.join(job, 'git'), GIT_WORK_TREE=os.path.join(job, 'work'))
    return env


def setup(worktree, job):
    started = time.time()
    plain = {name: value for name, value in os.environ.items() if not name.startswith('GIT_')}

    def chat(*args):
        return git('-C', worktree, *args, env=plain, error=Refused)

    if not os.path.isdir(worktree):
        raise Refused('%s is not a folder' % worktree)
    top = chat('rev-parse', '--show-toplevel')
    if os.path.realpath(top) != os.path.realpath(worktree):
        raise Refused('%s is not the top of a git worktree' % worktree)
    git_dir = os.path.realpath(chat('rev-parse', '--absolute-git-dir'))
    common = os.path.realpath(chat('rev-parse', '--path-format=absolute', '--git-common-dir'))
    if git_dir == common:
        raise Refused('%s is a primary checkout; Codex works only for a linked worktree'
                      % worktree)
    branch = run(['-C', worktree, 'symbolic-ref', '--quiet', '--short', 'HEAD'], env=plain)
    branch = branch.stdout.decode('utf-8', 'replace').strip()
    if not branch:
        raise Refused('HEAD of %s is not on a branch' % worktree)
    head = run(['-C', worktree, 'rev-parse', '--verify', '--quiet', 'HEAD'], env=plain)
    head = head.stdout.decode('ascii', 'replace').strip()
    if not head:
        raise Refused('branch %s has no commit yet' % branch)
    if chat('status', '--porcelain', '--untracked-files=all'):
        raise Refused('%s has uncommitted changes; commit them first, so that Codex starts from '
                      'all of the work' % worktree)
    object_format = chat('rev-parse', '--show-object-format')

    env = job_env(job)
    work = env['GIT_WORK_TREE']
    git('init', '-q', '--object-format=' + object_format, env=env)
    with open(os.path.join(env['GIT_DIR'], 'objects', 'info', 'alternates'), 'w') as handle:
        handle.write(os.path.join(common, 'objects') + '\n')
    git('update-ref', 'refs/heads/' + branch, head, env=env)
    git('symbolic-ref', 'HEAD', 'refs/heads/' + branch, env=env)
    git('read-tree', head, env=env)
    listing = run(['ls-files', '-z', '--stage'], env=env).stdout
    names = []
    cloned = 0
    clonefile = clonefile_function()
    made = set()
    for entry in listing.split(b'\0'):
        meta, _, name = entry.partition(b'\t')
        if not name:
            continue
        names.append(name)
        if clonefile is None or meta.split(b' ')[0] not in (b'100644', b'100755'):
            continue
        target = os.path.join(os.fsencode(work), name)
        folder = os.path.dirname(target)
        if folder not in made:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError:
                continue
            made.add(folder)
        # 1: CLONE_NOFOLLOW. A file that fails (a link, a denied name, another volume) is left
        # to git below.
        if clonefile(os.path.join(os.fsencode(worktree), name), target, 1) == 0:
            cloned += 1
    run(['update-index', '-q', '--refresh'], env=env)
    run(['checkout-index', '-a', '-q'], env=env)
    # What still is not there cannot exist in Codex's folder: a protected or denied name.
    withheld = [name for name in names
                if not os.path.lexists(os.path.join(os.fsencode(work), name))]
    if withheld:
        marked = run(['update-index', '--skip-worktree', '-z', '--stdin'], env=env,
                     data=b'\0'.join(withheld))
        if marked.returncode != 0:
            raise Failed('git could not mark the withheld files')
    status = git('status', '--porcelain', '--untracked-files=all', env=env)
    if status:
        raise Failed('the new job is not clean: %s' % status[:300])
    return {'status': 'ready', 'branch': branch, 'base': head, 'apfs_clones': cloned,
            'files': len(names),
            'withheld': [name.decode('utf-8', 'replace') for name in withheld[:50]],
            'withheld_count': len(withheld), 'seconds': round(time.time() - started, 2)}


def prompt(path):
    data = read_plain(path, PROMPT_MAX, 'the prompt file')
    if data is None:
        raise Refused('cannot read the prompt file: it does not exist')
    text = data.decode('utf-8', errors='replace')
    if not text.strip():
        raise Refused('the prompt file is empty')
    return {'status': 'read', 'prompt': text}


def read_plain(path, limit, what):
    """The bytes of a plain file of at most limit bytes; None when it does not exist."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
    except FileNotFoundError:
        return None
    except OSError as error:
        raise Refused('cannot read %s: %s' % (what, error.strerror))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Refused('%s is not a plain file' % what)
        data = b''
        while len(data) <= limit:
            block = os.read(fd, 65536)
            if not block:
                break
            data += block
    finally:
        os.close(fd)
    if len(data) > limit:
        raise Refused('%s is larger than %d bytes' % (what, limit))
    return data


def settings(worktree):
    found = {}
    for name in ('settings.json', 'settings.local.json'):
        path = os.path.join(worktree, '.claude', name)
        data = read_plain(path, PROMPT_MAX, path)
        if data is None:
            continue
        try:
            whole = json.loads(data.decode('utf-8'))
        except ValueError:
            raise Refused('%s is not valid JSON, so its read rules are unknown' % path)
        if not isinstance(whole, dict):
            continue
        permissions, sandbox = whole.get('permissions'), whole.get('sandbox')
        kept = {}
        if isinstance(permissions, dict):
            deny = permissions.get('deny')
            kept['permissions'] = {
                'deny': [rule for rule in deny if isinstance(rule, str) and
                         (rule == 'Read' or rule.startswith('Read('))]
                if isinstance(deny, list) else deny,
                'blockReadsOutsideWorkingDirectories':
                    permissions.get('blockReadsOutsideWorkingDirectories')}
        elif permissions is not None:
            kept['permissions'] = permissions
        if isinstance(sandbox, dict):
            filesystem = sandbox.get('filesystem')
            kept['sandbox'] = {'credentials': sandbox.get('credentials'), 'filesystem': {
                'denyRead': filesystem.get('denyRead')} if isinstance(filesystem, dict)
                else filesystem}
        elif sandbox is not None:
            kept['sandbox'] = sandbox
        found[name] = kept
    return {'status': 'read', 'settings': found}


TOOLS_LIST = os.path.join('.agents', 'codex-tools.json')
TOOLS_MAX = 64 * 1024


def tools(worktree):
    """The project's tool list (codex_tools.py's header) and the Bash rules of its Claude Code
    settings in <worktree>: the chat's files, so read here. No list: `list` is None."""
    data = read_plain(os.path.join(worktree, TOOLS_LIST), TOOLS_MAX, TOOLS_LIST)
    listed = None
    if data is not None:
        try:
            listed = json.loads(data.decode('utf-8'))
        except ValueError:
            raise Refused('%s is not valid JSON' % TOOLS_LIST)
    rules = {'allow': [], 'ask': [], 'deny': []}
    for name in ('settings.json', 'settings.local.json'):
        path = os.path.join(worktree, '.claude', name)
        raw = read_plain(path, PROMPT_MAX, path)
        if raw is None:
            continue
        try:
            whole = json.loads(raw.decode('utf-8'))
        except ValueError:
            raise Refused('%s is not valid JSON, so its Bash rules are unknown' % path)
        permissions = whole.get('permissions') if isinstance(whole, dict) else None
        for kind in rules:
            found = permissions.get(kind) if isinstance(permissions, dict) else None
            rules[kind] += [rule for rule in found if isinstance(rule, str) and
                            (rule == 'Bash' or rule.startswith('Bash('))] \
                if isinstance(found, list) else []
    return {'status': 'read', 'list': listed, 'rules': rules}


def export(job, base):
    env = job_env(job)
    env.pop('GIT_WORK_TREE')
    # Codex wrote this git folder's config: no signature check, which would run gpg.program.
    env.update(GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='log.showSignature',
               GIT_CONFIG_VALUE_0='false', GIT_CONFIG_KEY_1='core.fsmonitor',
               GIT_CONFIG_VALUE_1='false')
    out = os.path.join(job, 'out', BUNDLE)
    if os.path.lexists(out):
        os.remove(out)
    branch = git('symbolic-ref', '--short', 'HEAD', env=env)
    tip = git('rev-parse', '--verify', 'HEAD', env=env)
    report = {'status': 'nothing', 'branch': branch, 'base': base, 'head': tip, 'commits': [],
              'bundle': None}
    if tip == base:
        return report
    if run(['merge-base', '--is-ancestor', base, tip], env=env).returncode != 0:
        raise Failed('Codex\'s branch is not on top of the commit it started from, %s (Codex '
                     'rewrote history); start with --fresh' % base)
    for line in git('log', '--reverse', '--format=%H%x09%s', '%s..%s' % (base, tip),
                    env=env).splitlines():
        sha, _, subject = line.partition('\t')
        report['commits'].append({'sha': sha, 'subject': subject})
    git('bundle', 'create', '-q', out, 'refs/heads/' + branch, '^' + base, env=env)
    report.update(status='exported', bundle=out)
    return report


def main(argv):
    actions = {'setup': (setup, 2), 'prompt': (prompt, 1), 'settings': (settings, 1),
               'tools': (tools, 1), 'export': (export, 2)}
    if not argv or argv[0] not in actions or len(argv) - 1 != actions[argv[0]][1]:
        print(__doc__.split('\n\n')[1], file=sys.stderr)
        return 2
    try:
        report, code = actions[argv[0]][0](*argv[1:]), 0
    except Refused as error:
        report, code = {'status': 'refused', 'failure': str(error)}, 3
    except (Failed, OSError) as error:
        report, code = {'status': 'failed', 'failure': str(error)}, 1
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
