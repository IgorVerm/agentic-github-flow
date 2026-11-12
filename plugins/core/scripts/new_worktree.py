#!/usr/bin/env python3
"""Create a task worktree in the agreed place: <repo>-worktrees/<task> beside the primary checkout.

Usage: python3 new_worktree.py <task> [--branch <name>] [--base <ref>] [--no-fetch]
                               [--no-clones | --clones]

Run it from the primary checkout of a repository. It fetches origin (unless --no-fetch), then
creates `../<repo>-worktrees/<task>` on a new branch (default `agent/<task>`) from <base>
(default: the landing branch, the row `landing branch` of HANDOFF.md's `## Landing settings`
(landing.py), else origin's default branch as fetched, else local main or master; in local-main
mode the local landing branch while it holds landings not pushed yet). It refuses a task that
is not a plain name, an existing path or branch, a linked worktree as the starting point, and a
checkout inside a cloud-synced folder (iCloud Drive, OneDrive, Dropbox, Google Drive), where
sync clients corrupt git's files. When the repository's post-checkout hook fails, git still
makes the worktree and its branch and exits with the hook's status; so does this script, and it
says that the worktree stands.

Clones (on by default on macOS; Igor's ruling on #19, DESIGN_DECISIONS.md): the tracked files
are APFS clones of the primary checkout's (copy-on-write: they share disk blocks until one side
changes), so a worktree of a repository with large tracked files costs almost no disk.
--no-clones or AGENTIC_GITHUB_FLOW_CLONES=0 turns it off; on other systems nothing changes
unless --clones or AGENTIC_GITHUB_FLOW_CLONES=1 asks for it. It runs `git worktree add
--no-checkout`, fills the index from <base> and clones every tracked file whose blob a clean
primary file holds (clone_dedupe_worktree.py owns which files may serve). Git checks out the
rest: files that differ from the primary or are missing there, symlinks, submodules, and paths
with a checkout conversion (`filter`, `text`, `eol`, `crlf`, `ident`, `working-tree-encoding`,
so LFS too); such a file of 100 KB or more whose bytes equal the primary's then becomes a clone
after a sha256 check. A clone keeps none of the primary file's flags (hidden, locked) or
extended attributes (quarantine, tags) beyond `com.apple.provenance`, which a file git writes
gets too; a compressed or system-flagged source is left to git. Git re-hashes every clone
(`update-index --refresh`) and checks out again any that does not match. Should the clone
checkout fail at all (paths that differ only in case on a case-insensitive volume, for one),
git checks out every file, as without clones. The result is what `git worktree add` gives: the same files, modes and
index, `git status` clean, the post-checkout hook run with the same arguments. Where cloning
cannot work it says why in one line and makes a plain worktree: off macOS (only when asked
for) exactly as without clones; on macOS on another volume or a file system without clones;
on macOS under a sparse checkout, `core.autocrlf` true or input, or a git without
`check-attr --source` (2.40), followed by `clone_dedupe_worktree.py --apply`.
"""
from __future__ import annotations

import errno
import os
import re
import stat
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clone_dedupe_worktree as dedupe  # noqa: E402  (owner of what may be cloned)
from landing import SettingError, landing_setting, unpushed_landings  # noqa: E402

SYNCED = ('/Library/Mobile Documents/', '/Library/CloudStorage/', '/OneDrive', '/Dropbox/',
          '/Google Drive/', '\\OneDrive', '\\Dropbox\\', '\\Google Drive\\')
CLONES_ENV = 'AGENTIC_GITHUB_FLOW_CLONES'
CONVERSION_ATTRS = ('filter', 'text', 'eol', 'crlf', 'ident', 'working-tree-encoding')


def git(*args, cwd=None):
    return subprocess.run(['git', *args], capture_output=True, text=True, cwd=cwd)


def gitb(cwd: str, *args: str, data: bytes | None = None) -> bytes:
    """Bytes out, raising CalledProcessError on a failure (the clone path)."""
    return subprocess.run(['git', '-C', cwd, *args], input=data, check=True,
                          capture_output=True).stdout


def nul(paths: list[str]) -> bytes:
    return b''.join(os.fsencode(p) + b'\0' for p in paths)


def default_base(primary):
    """The landing branch when HANDOFF.md sets one (landing.py), as fetched, else local;
    otherwise origin's default branch as last fetched, else local main or master."""
    setting = landing_setting(primary)
    if setting:
        candidates = ['refs/remotes/origin/' + setting, 'refs/heads/' + setting]
    else:
        head = git('symbolic-ref', '-q', 'refs/remotes/origin/HEAD', cwd=primary).stdout.strip()
        candidates = [head, 'refs/remotes/origin/main', 'refs/remotes/origin/master',
                      'refs/heads/main', 'refs/heads/master']
    for ref in candidates:
        if ref and git('rev-parse', '-q', '--verify', ref, cwd=primary).returncode == 0:
            return unpushed_landings(primary, ref)
    return None


def clones_wanted(flag: bool | None) -> bool:
    """The flag, else the environment variable, else on for macOS only."""
    if flag is not None:
        return flag
    value = os.environ.get(CLONES_ENV, '').strip().lower()
    if value in ('1', 'true', 'yes', 'on'):
        return True
    if value in ('0', 'false', 'no', 'off'):
        return False
    return sys.platform == 'darwin'


def clone_plan(primary: str, base: str, probe_dir: str):
    """(by_blob, None, False) when the worktree can be made from clones, else
    ({}, reason, whether the deduplication pass after a plain checkout can still clone)."""
    if sys.platform != 'darwin':
        return {}, 'APFS clones are macOS only', False
    sparse = git('config', '--type=bool', 'core.sparseCheckout', cwd=primary).stdout.strip()
    if sparse == 'true':
        return {}, 'sparse checkout is on', True
    autocrlf = git('config', 'core.autocrlf', cwd=primary).stdout.strip().lower()
    if autocrlf in ('true', 'yes', 'on', '1', 'input'):
        return {}, f'core.autocrlf is {autocrlf}', True
    if git('check-attr', '--source', base, 'text', '--', 'probe', cwd=primary).returncode:
        return {}, 'this git has no check-attr --source (2.40 or later)', True
    try:
        by_blob = dedupe.sources(primary)
    except (subprocess.CalledProcessError, UnicodeDecodeError, ValueError) as e:
        return {}, f"cannot list the primary's clean files ({e})", False
    if not by_blob:
        return {}, 'no clean tracked file in the primary checkout', False
    probe = os.path.join(probe_dir, f'.clone-probe-{os.getpid()}')
    try:
        dedupe.clonefile(os.path.join(primary, next(iter(by_blob.values()))), probe)
    except OSError as e:
        return {}, f'cannot clone into {probe_dir} ({e.strerror})', False
    finally:
        dedupe.discard(probe)
    return by_blob, None, False


def checkout_from_clones(primary: str, dest: str, by_blob: dict[str, str]) -> tuple[int, int, int]:
    """Fill the index of the empty worktree <dest> from HEAD and write its files.

    Returns (files cloned, bytes cloned, files git checked out). Raises on a git failure."""
    gitb(dest, 'read-tree', 'HEAD')
    entries = []
    for rec in gitb(dest, 'ls-files', '-s', '-z').split(b'\0'):
        if rec:
            meta, path = rec.split(b'\t', 1)
            mode, blob, _stage = meta.decode().split()
            entries.append((mode, blob, os.fsdecode(path)))
    regular = [p for mode, _b, p in entries if mode in ('100644', '100755')]
    converted = set()
    if regular:
        out = gitb(dest, 'check-attr', '--source', 'HEAD', '-z', '--stdin', *CONVERSION_ATTRS,
                   data=nul(regular)).split(b'\0')
        for i in range(0, len(out) - 2, 3):
            if out[i + 2] not in (b'unspecified', b'unset'):
                converted.add(os.fsdecode(out[i]))

    umask = os.umask(0)
    os.umask(umask)
    cloned, nbytes = set(), 0
    for mode, blob, path in entries:
        if mode not in ('100644', '100755') or path in converted or blob not in by_blob:
            continue
        src, dst = os.path.join(primary, by_blob[blob]), os.path.join(dest, path)
        try:
            st = os.lstat(src)
            if not stat.S_ISREG(st.st_mode):
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            dedupe.clone_plain(src, dst)
        except OSError:
            continue  # git checks it out below
        try:
            os.chmod(dst, (0o777 if mode == '100755' else 0o666) & ~umask)
            os.utime(dst)  # written now, as a fresh checkout's file is
        except OSError:
            dedupe.discard(dst)
            continue
        cloned.add(path)
        nbytes += st.st_size

    rest = [p for _m, _b, p in entries if p not in cloned]
    if rest:
        gitb(dest, 'checkout-index', '-u', '-z', '--stdin', data=nul(rest))
    # A file git wrote through a conversion (LFS, text) still becomes a clone where its bytes
    # equal the primary's, as clone_dedupe_worktree.py --apply makes it after a full checkout.
    later, later_bytes, _ = dedupe.replace_with_clones(
        primary, dest, by_blob, {p: b for _m, b, p in entries if p in converted}, 100, True)
    # The index holds no stat data for the clones, so git hashes each one and records it; a
    # clone whose bytes are not its blob shows up in diff-files and is written by git instead.
    subprocess.run(['git', '-C', dest, 'update-index', '-q', '--refresh'], capture_output=True)
    bad = [os.fsdecode(p) for p in gitb(dest, 'diff-files', '--name-only', '-z').split(b'\0') if p]
    if bad:
        gitb(dest, 'checkout-index', '-f', '-u', '-z', '--stdin', data=nul(bad))
        cloned.difference_update(bad)
    if subprocess.run(['git', '-C', dest, 'diff-files', '--quiet']).returncode or \
            subprocess.run(['git', '-C', dest, 'diff-index', '--cached', '--quiet',
                            'HEAD']).returncode:
        raise RuntimeError('the worktree does not match HEAD after the checkout')
    return len(cloned) + later, nbytes + later_bytes, len(entries) - len(cloned) - later


def post_checkout(dest: str) -> int:
    """Run the post-checkout hook as `git worktree add` does: in <dest>, with the arguments
    null, HEAD, 1 and with GIT_DIR and GIT_WORK_TREE unset (`git hook run` would set GIT_DIR).

    A hook git cannot exec directly (no shebang: ENOEXEC) runs as `/bin/sh <hook> <args>`, as in
    git's run-command.c, start_command(). Returns the hook's exit status, which `git worktree
    add` makes its own; a hook that cannot be started at all counts as status 1 (hook.c,
    notify_start_failure()). Either way the finished worktree and its branch stay, as in git's
    builtin/worktree.c: "Hook failure does not warrant worktree deletion"."""
    hook = gitb(dest, 'rev-parse', '--path-format=absolute', '--git-path',
                'hooks/post-checkout').decode().strip()
    if not os.access(hook, os.X_OK) or os.path.isdir(hook):
        return 0
    fmt = gitb(dest, 'rev-parse', '--show-object-format').decode().strip()
    null = '0' * (64 if fmt == 'sha256' else 40)
    head = gitb(dest, 'rev-parse', 'HEAD').decode().strip()
    env = {k: v for k, v in os.environ.items() if k not in ('GIT_DIR', 'GIT_WORK_TREE')}
    args = [hook, null, head, '1']
    io = {'cwd': dest, 'env': env, 'stdin': subprocess.DEVNULL, 'stdout': sys.stderr}
    try:  # git runs hooks with stdin from /dev/null and stdout sent to stderr
        try:
            rc = subprocess.run(args, **io).returncode
        except OSError as e:
            if e.errno != errno.ENOEXEC:
                raise
            rc = subprocess.run(['/bin/sh', *args], **io).returncode
    except OSError as e:
        print(f'new_worktree: cannot run the post-checkout hook {hook}: {e}', file=sys.stderr)
        rc = 1
    if rc:
        rc = rc if rc > 0 else 128 - rc  # killed by a signal: the shell's 128 + signal
        print(f'new_worktree: the post-checkout hook exited {rc}; the worktree and its branch '
              'stand complete, as `git worktree add` leaves them', file=sys.stderr)
    return rc


def add_with_clones(primary, dest, branch, base, by_blob) -> int:
    added = git('worktree', 'add', '-q', '--no-checkout', '--no-track', '-b', branch, dest, base,
                cwd=primary)
    if added.returncode != 0:
        print('new_worktree: ' + added.stderr.strip(), file=sys.stderr)
        return 1
    print(f'new_worktree: {dest} on {branch} from {base}')
    try:
        n, nbytes, normal = checkout_from_clones(primary, dest, by_blob)
    except (subprocess.CalledProcessError, RuntimeError, OSError) as e:
        err = (getattr(e, 'stderr', None) or b'').decode(errors='replace').strip()
        print(f'new_worktree: no clones ({err or e}); git checks out every file')
        # What `git worktree add` itself does after --no-checkout: the index from HEAD and
        # every file written by git, over any clone made so far.
        done = git('read-tree', 'HEAD', cwd=dest)
        if done.returncode == 0:
            done = git('checkout-index', '-a', '-f', '-u', cwd=dest)
        if done.returncode != 0:
            print('new_worktree: the checkout did not complete: ' + done.stderr.strip()
                  + f'; the worktree stands unfinished, see `git -C {dest} status`',
                  file=sys.stderr)
            return 1
        return post_checkout(dest)
    print(f'new_worktree: cloned {n} files ({nbytes / 2**30:.2f} GiB) from {primary}; '
          f'git checked out {normal}')
    return post_checkout(dest)


def add_plain(primary, dest, branch, base) -> int:
    """`git worktree add`; returns 0, the failing post-checkout hook's status (the worktree
    stands), or 1 when there is no worktree."""
    added = git('worktree', 'add', '-q', '--no-track', '-b', branch, dest, base, cwd=primary)
    if added.returncode != 0 and os.path.exists(os.path.join(dest, '.git')):
        # git made the worktree and the branch, then its post-checkout hook failed
        print(f'new_worktree: {dest} on {branch} from {base}')
        print(f'new_worktree: the post-checkout hook exited {added.returncode}; the worktree '
              'and its branch stand complete, as `git worktree add` leaves them: '
              + added.stderr.strip(), file=sys.stderr)
        return added.returncode
    if added.returncode != 0:
        print('new_worktree: ' + added.stderr.strip(), file=sys.stderr)
        return 1
    print(f'new_worktree: {dest} on {branch} from {base}')
    return 0


def main(argv: list[str]) -> int:
    branch, base, fetch, clones, rest = None, None, True, None, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--branch', '--base'):
            if i + 1 >= len(argv):
                print(__doc__, file=sys.stderr)
                return 2
            if a == '--branch':
                branch = argv[i + 1]
            else:
                base = argv[i + 1]
            i += 2
            continue
        if a == '--no-fetch':
            fetch = False
        elif a in ('--clones', '--no-clones'):
            clones = a == '--clones'
        elif a in ('-h', '--help'):
            print(__doc__)
            return 0
        else:
            rest.append(a)
        i += 1
    if len(rest) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    task = rest[0]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,80}', task):
        print(f"new_worktree: task '{task}' must be a plain name (letters, digits, . _ -)",
              file=sys.stderr)
        return 1
    branch = branch or f'agent/{task}'

    top = git('rev-parse', '--show-toplevel')
    if top.returncode != 0:
        print('new_worktree: not inside a git checkout', file=sys.stderr)
        return 1
    primary = os.path.normpath(top.stdout.strip())
    common = git('rev-parse', '--git-common-dir').stdout.strip()  # relative to the cwd
    common = os.path.realpath(common if os.path.isabs(common) else os.path.join(os.getcwd(), common))
    if os.path.normcase(os.path.dirname(common)) != os.path.normcase(os.path.realpath(primary)):
        print('new_worktree: run it from the primary checkout, not from a linked worktree',
              file=sys.stderr)
        return 1
    real = os.path.realpath(primary) + os.sep
    if any(s in real for s in SYNCED):
        print(f'new_worktree: {real} is in a cloud-synced folder; keep checkouts out of it',
              file=sys.stderr)
        return 1
    dest = os.path.join(os.path.dirname(primary), os.path.basename(primary) + '-worktrees', task)
    if os.path.lexists(dest):
        print(f'new_worktree: {dest} exists already', file=sys.stderr)
        return 1
    if git('rev-parse', '-q', '--verify', f'refs/heads/{branch}', cwd=primary).returncode == 0:
        print(f'new_worktree: branch {branch} exists already; pick another --branch',
              file=sys.stderr)
        return 1
    if fetch and 'origin' in git('remote', cwd=primary).stdout.split():
        fetched = git('fetch', '--quiet', 'origin', cwd=primary)
        if fetched.returncode != 0:
            print('new_worktree: git fetch origin failed: ' + fetched.stderr.strip(),
                  file=sys.stderr)
            return 1
    try:
        base = base or default_base(primary)
    except SettingError as e:
        print(f'new_worktree: {e}', file=sys.stderr)
        return 2
    if not base:
        print('new_worktree: no base found (the landing branch HANDOFF.md names, else '
              'origin/HEAD, origin/main, main or master); pass --base', file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    dedupe_after = False
    if clones_wanted(clones):
        by_blob, reason, dedupe_after = clone_plan(primary, base, os.path.dirname(dest))
        if reason is None:
            return add_with_clones(primary, dest, branch, base, by_blob)
        print(f'new_worktree: no clones ({reason}); a plain checkout'
              + (', then deduplication' if dedupe_after else ''))
    rc = add_plain(primary, dest, branch, base)
    if dedupe_after and os.path.exists(os.path.join(dest, '.git')):
        d = subprocess.run([sys.executable, os.path.join(HERE, 'clone_dedupe_worktree.py'),
                            '--apply', primary, dest], capture_output=True, text=True)
        out = (d.stdout + d.stderr).strip().splitlines()
        print('new_worktree: dedupe: ' + (out[-1] if out else f'exit {d.returncode}'))
        if d.returncode != 0:
            print('new_worktree: deduplication did not complete; the worktree stands, run '
                  'clone_dedupe_worktree.py --apply again by hand', file=sys.stderr)
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
