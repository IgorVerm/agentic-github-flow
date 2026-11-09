#!/usr/bin/env python3
"""Create a task worktree in the agreed place: <repo>-worktrees/<task> beside the primary checkout.

Usage: python3 new_worktree.py <task> [--branch <name>] [--base <ref>] [--no-fetch]

Run it from the primary checkout of a repository. It fetches origin (unless --no-fetch), then
creates `../<repo>-worktrees/<task>` on a new branch (default `agent/<task>`) from <base>
(default: origin's default branch as fetched, else local main or master). It refuses a task that
is not a plain name, an existing path or branch, a linked worktree as the starting point, and a
checkout inside a cloud-synced folder (iCloud Drive, OneDrive, Dropbox, Google Drive), where
sync clients corrupt git's files.

On macOS, where the file system can clone files (APFS, `cp -c`), the worktree's tracked files
start as clones of the primary checkout's, so a large repository does not write a second copy
of every file. It runs `git worktree add --no-checkout`, fills the index from <base>, and makes
every regular tracked file whose blob a clean primary file holds (`git status` reports it
unmodified) a clone of that file (`clonefile`, as `cp -c`). Everything else git checks out
itself: files that differ from the primary or are missing there, symlinks, submodules, and paths
with a checkout conversion (`filter`, `text`, `eol`, `crlf`, `ident`, `working-tree-encoding`
attributes, so LFS too); a converted file of at least 100 KB whose bytes equal the primary's
then becomes a clone. Git then re-hashes every clone against its blob (`update-index
--refresh`), and a clone that does not match is checked out again by git. The result is what
`git worktree add` gives: the same files and modes, the index matching, `git status` clean, and
the post-checkout hook run with the same arguments and environment (a hook without a shebang
through /bin/sh, as git runs it), the script exiting with the hook's status. A plain `git
worktree add` is used, with a note, where cloning cannot work: another file system, sparse
checkout, `core.autocrlf` true or input, or no clean tracked file in the primary. On Linux and
Windows it is always the plain `git worktree add`, without a note.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import re
import stat
import subprocess
import sys

SYNCED = ('/Library/Mobile Documents/', '/Library/CloudStorage/', '/OneDrive', '/Dropbox/',
          '/Google Drive/', '\\OneDrive', '\\Dropbox\\', '\\Google Drive\\')
CONVERSION_ATTRS = ('filter', 'text', 'eol', 'crlf', 'ident', 'working-tree-encoding')
CONVERTED_MIN = 100 * 1024  # a converted file is cloned again only from this size


def git(*args, cwd=None):
    return subprocess.run(['git', *args], capture_output=True, text=True, cwd=cwd)


def gitb(cwd, *args, data=None):
    """git's stdout as bytes; raises CalledProcessError on failure."""
    return subprocess.run(['git', '-C', cwd, *args], input=data, check=True,
                          capture_output=True).stdout


def nul(paths):
    return b''.join(os.fsencode(p) + b'\0' for p in paths)


def clonefile(src, dst):
    """APFS clone of the regular file src at the new path dst; raises OSError where impossible."""
    fn = getattr(ctypes.CDLL(None, use_errno=True), 'clonefile', None)
    if fn is None:
        raise OSError(errno.ENOTSUP, 'clonefile() is not available on this system')
    fn.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32)
    if fn(os.fsencode(src), os.fsencode(dst), 1) != 0:  # 1 = CLONE_NOFOLLOW
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def clean_sources(primary):
    """blob -> a path in <primary> whose file may serve as the clone source for that blob: a
    regular tracked file that `git status` reports unmodified. An edit git does not report
    (assume-unchanged) is caught later, when git re-hashes the clone."""
    dirty = {os.fsdecode(rec[3:]) for rec in gitb(primary, 'status', '--porcelain', '-z',
                                                   '--untracked-files=no').split(b'\0') if rec}
    by_blob = {}
    for rec in gitb(primary, 'ls-files', '-s', '-z').split(b'\0'):
        if rec:
            meta, path = rec.split(b'\t', 1)
            mode, blob, _stage = meta.decode().split()
            path = os.fsdecode(path)
            if mode in ('100644', '100755') and path not in dirty:
                by_blob.setdefault(blob, path)
    return by_blob


def no_clone_reason(primary, probe_dir, by_blob):
    """Why this checkout cannot be made from clones, or None when it can."""
    sparse = git('config', '--type=bool', 'core.sparseCheckout', cwd=primary).stdout.strip()
    if sparse == 'true':
        return 'sparse checkout is on'
    autocrlf = git('config', 'core.autocrlf', cwd=primary).stdout.strip().lower()
    if autocrlf in ('true', 'yes', 'on', '1', 'input'):
        return 'core.autocrlf is ' + autocrlf
    if not by_blob:
        return 'no clean tracked file in the primary checkout'
    probe = os.path.join(probe_dir, '.clone-probe-%d' % os.getpid())
    try:
        clonefile(os.path.join(primary, next(iter(by_blob.values()))), probe)
    except OSError as e:
        return 'cannot clone into %s (%s)' % (probe_dir, e.strerror)
    os.unlink(probe)
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def clone_converted(primary, dest, by_blob, files):
    """Replace each file git wrote through a conversion (path -> blob) by a clone of the
    primary's file of that blob, where both are at least CONVERTED_MIN and the bytes are the
    same (sha256); mode and mtime are kept. Returns (files cloned, bytes)."""
    done = nbytes = 0
    for path, blob in files.items():
        dst = os.path.join(dest, path)
        try:
            st = os.lstat(dst)
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_size < CONVERTED_MIN or blob not in by_blob:
            continue
        src = os.path.join(primary, by_blob[blob])
        if not os.path.isfile(src) or os.path.getsize(src) != st.st_size:
            continue
        tmp = dst + '.clone-tmp'
        try:
            want = sha256(dst)
            clonefile(src, tmp)
            if sha256(tmp) != want:
                os.unlink(tmp)
                continue
            os.chmod(tmp, st.st_mode & 0o7777)
            os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
            os.replace(tmp, dst)
        except OSError:
            if os.path.lexists(tmp):
                os.unlink(tmp)
            continue
        done += 1
        nbytes += st.st_size
    return done, nbytes


def checkout_from_clones(primary, dest, by_blob):
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
        # --cached: the attributes of the index just read from HEAD (`--source` needs git 2.40)
        out = gitb(dest, 'check-attr', '--cached', '-z', '--stdin', *CONVERSION_ATTRS,
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
            clonefile(src, dst)
        except OSError:
            continue  # git checks it out below
        os.chmod(dst, (0o777 if mode == '100755' else 0o666) & ~umask)
        os.utime(dst)  # written now, as a fresh checkout's file is
        cloned.add(path)
        nbytes += st.st_size

    rest = [p for _m, _b, p in entries if p not in cloned]
    if rest:
        gitb(dest, 'checkout-index', '-u', '-z', '--stdin', data=nul(rest))
    later, later_bytes = clone_converted(primary, dest, by_blob,
                                         {p: b for _m, b, p in entries if p in converted})
    # Git hashes every clone (no stat data yet) and records it; a clone whose bytes are not its
    # blob shows up in diff-files and is written by git instead.
    subprocess.run(['git', '-C', dest, 'update-index', '-q', '--refresh'], capture_output=True)
    bad = [os.fsdecode(p) for p in gitb(dest, 'diff-files', '--name-only', '-z').split(b'\0')
           if p]
    if bad:
        gitb(dest, 'checkout-index', '-f', '-u', '-z', '--stdin', data=nul(bad))
        cloned.difference_update(bad)
    if (subprocess.run(['git', '-C', dest, 'diff-files', '--quiet']).returncode or
            subprocess.run(['git', '-C', dest, 'diff-index', '--cached', '--quiet',
                            'HEAD']).returncode):
        raise RuntimeError('the worktree does not match HEAD after the checkout')
    return len(cloned) + later, nbytes + later_bytes, len(entries) - len(cloned) - later


def post_checkout(dest):
    """Run the post-checkout hook as `git worktree add` does: in <dest>, with the arguments
    null, HEAD, 1 and with GIT_DIR and GIT_WORK_TREE unset.

    A hook git cannot exec directly (no shebang: ENOEXEC) runs as `/bin/sh <hook> <args>`, as
    git's start_command() does. Returns the hook's exit status, which `git worktree add` makes
    its own; a hook that cannot be started at all counts as status 1. Either way the finished
    worktree and its branch stay, as git leaves them."""
    hook = gitb(dest, 'rev-parse', '--git-path', 'hooks/post-checkout').decode().strip()
    hook = hook if os.path.isabs(hook) else os.path.join(dest, hook)
    if not os.access(hook, os.X_OK) or os.path.isdir(hook):
        return 0
    head = gitb(dest, 'rev-parse', 'HEAD').decode().strip()
    env = {k: v for k, v in os.environ.items() if k not in ('GIT_DIR', 'GIT_WORK_TREE')}
    args = [hook, '0' * len(head), head, '1']
    try:
        try:
            rc = subprocess.run(args, cwd=dest, env=env).returncode
        except OSError as e:
            if e.errno != errno.ENOEXEC:
                raise
            rc = subprocess.run(['/bin/sh'] + args, cwd=dest, env=env).returncode
    except OSError as e:
        print('new_worktree: cannot run the post-checkout hook %s: %s' % (hook, e),
              file=sys.stderr)
        rc = 1
    if rc:
        rc = rc if rc > 0 else 128 - rc  # killed by a signal: the shell's 128 + signal
        print('new_worktree: the post-checkout hook exited %d; the worktree and its branch '
              'stand complete, as `git worktree add` leaves them' % rc, file=sys.stderr)
    return rc


def default_base(primary):
    """origin's default branch as last fetched, else local main or master."""
    head = git('symbolic-ref', '-q', 'refs/remotes/origin/HEAD', cwd=primary).stdout.strip()
    candidates = [head, 'refs/remotes/origin/main', 'refs/remotes/origin/master',
                  'refs/heads/main', 'refs/heads/master']
    for ref in candidates:
        if ref and git('rev-parse', '-q', '--verify', ref, cwd=primary).returncode == 0:
            return ref
    return None


def main(argv: list[str]) -> int:
    branch, base, fetch, rest = None, None, True, []
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
    base = base or default_base(primary)
    if not base:
        print('new_worktree: no base found (origin/HEAD, origin/main, main or master); '
              'pass --base', file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    reason = 'not macOS'
    if sys.platform == 'darwin':
        try:
            by_blob = clean_sources(primary)
        except (subprocess.CalledProcessError, UnicodeDecodeError, ValueError) as e:
            reason = "cannot list the primary's clean files (%s)" % e
        else:
            reason = no_clone_reason(primary, os.path.dirname(dest), by_blob)
        if reason:
            print(f'new_worktree: no clones ({reason}); plain checkout')

    if reason is None:
        added = git('worktree', 'add', '-q', '--no-checkout', '--no-track', '-b', branch, dest,
                    base, cwd=primary)
        if added.returncode != 0:
            print('new_worktree: ' + added.stderr.strip(), file=sys.stderr)
            return 1
        print(f'new_worktree: {dest} on {branch} from {base}')
        try:
            n, nbytes, normal = checkout_from_clones(primary, dest, by_blob)
        except (subprocess.CalledProcessError, RuntimeError, OSError) as e:
            err = (getattr(e, 'stderr', None) or b'').decode(errors='replace').strip()
            print(f'new_worktree: the checkout did not complete: {err or e}; the worktree '
                  f'stands unfinished, see `git -C "{dest}" status`', file=sys.stderr)
            return 1
        print(f'new_worktree: cloned {n} files ({nbytes / 2**20:.1f} MiB) from {primary}; '
              f'git checked out {normal}')
        return post_checkout(dest)

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


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
