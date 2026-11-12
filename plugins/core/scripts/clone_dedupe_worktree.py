#!/usr/bin/env python3
"""Free disk on APFS (macOS): make a worktree's large tracked files clones of the primary checkout's.

Usage: python3 clone_dedupe_worktree.py [--apply] [--min-kb 100] <primary> <worktree>

A plain `git worktree add` writes its own copy of every tracked file. For each regular tracked
file in <worktree> that is unmodified (`git status`), at least --min-kb large, and whose index
blob a clean file of <primary> also holds, the file is replaced by an APFS clone (copy-on-write,
`clonefile`) of the primary's file. The bytes never change: the clone's sha256 must equal the
file it replaces, mode and mtime are kept, the flags and extended attributes clonefile would
take over from the primary's file are cleared (`clone_plain()`), and a file that changed
meanwhile is left alone.
Without --apply it only reports, on any system; --apply needs macOS. Modified, untracked and
ignored files are never touched. Skip a worktree a process is working in. `du` keeps counting
clones in full; measure the gain with `df`.

This file owns what may serve as a clone source (`sources()`) and the clone itself
(`clone_plain()`); new_worktree.py uses both.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
import sys


def git(cwd: str, *args: str) -> bytes:
    return subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True).stdout


XATTR_NOFOLLOW = 1  # <sys/xattr.h>
# The system's own record of where a file came from: a file git writes gets it too, and it
# cannot always be removed.
KEEP_XATTRS = {b'com.apple.provenance'}
# Flags a clone must not take over by clearing them: a compressed file's data lives in its
# attributes, and the system flags only root may change. Such a source is left to git.
KEEP_SOURCE_FLAGS = getattr(stat, 'UF_COMPRESSED', 0x20) | getattr(stat, 'SF_SETTABLE',
                                                                   0x3fff0000)


def _libc():
    import ctypes
    return ctypes, ctypes.CDLL(None, use_errno=True)


def _oserror(ctypes, what):
    err = ctypes.get_errno()
    return OSError(err, f'{what}: {os.strerror(err)}')


def clonefile(src: str, dst: str) -> None:
    """APFS clone of the regular file src at the new path dst, with src's flags and extended
    attributes as clonefile(2) copies them; raises OSError where impossible."""
    if sys.platform != 'darwin':
        raise OSError(45, 'clonefile() is macOS only')
    ctypes, libc = _libc()
    fn = getattr(libc, 'clonefile', None)
    if fn is None:
        raise OSError(45, 'clonefile() is not available on this system')
    fn.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32)
    if fn(os.fsencode(src), os.fsencode(dst), 1) != 0:  # 1 = CLONE_NOFOLLOW
        raise _oserror(ctypes, 'clonefile')


def strip_xattrs(path: str) -> None:
    """Remove every extended attribute of path except KEEP_XATTRS; raises OSError."""
    ctypes, libc = _libc()
    p = os.fsencode(path)
    libc.listxattr.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int)
    libc.listxattr.restype = ctypes.c_ssize_t
    libc.removexattr.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int)
    size = libc.listxattr(p, None, 0, XATTR_NOFOLLOW)
    if size < 0:
        raise _oserror(ctypes, 'listxattr')
    if not size:
        return
    buf = ctypes.create_string_buffer(size)
    size = libc.listxattr(p, buf, size, XATTR_NOFOLLOW)
    if size < 0:
        raise _oserror(ctypes, 'listxattr')
    for name in buf.raw[:size].split(b'\0'):
        if name and name not in KEEP_XATTRS and libc.removexattr(p, name, XATTR_NOFOLLOW):
            raise _oserror(ctypes, 'removexattr ' + os.fsdecode(name))


def discard(path: str) -> None:
    """Remove a clone this script made, also when it took over a lock flag; never raises."""
    try:
        os.chflags(path, 0)
    except (OSError, AttributeError):
        pass
    try:
        os.unlink(path)
    except OSError:
        pass


def clone_plain(src: str, dst: str) -> None:
    """A clone of src at dst that carries what a file git writes carries: src's bytes, without
    the flags (hidden, locked) and extended attributes (quarantine, tags) clonefile copies.
    Raises OSError, leaving nothing at dst, where that cannot be done: a compressed source, a
    source with system flags, an attribute that cannot be removed."""
    st = os.lstat(src)
    if getattr(st, 'st_flags', 0) & KEEP_SOURCE_FLAGS:
        raise OSError(1, f'{src} is compressed or has system flags')
    clonefile(src, dst)
    try:
        if getattr(st, 'st_flags', 0):
            os.chflags(dst, 0)
        strip_xattrs(dst)
    except OSError:
        discard(dst)
        raise


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def index(cwd: str) -> dict[str, str]:
    """path -> blob for the regular tracked files of <cwd> that `git status` reports unmodified."""
    dirty = set()
    recs = git(cwd, 'status', '--porcelain', '-z', '--untracked-files=no').split(b'\0')
    i = 0
    while i < len(recs):
        rec = recs[i]
        if rec:
            dirty.add(os.fsdecode(rec[3:]))
            if rec[:1] in (b'R', b'C') or rec[1:2] in (b'R', b'C'):
                i += 1  # the next record is the rename's or copy's source path
                if i < len(recs) and recs[i]:
                    dirty.add(os.fsdecode(recs[i]))
        i += 1
    out = {}
    for rec in git(cwd, 'ls-files', '-s', '-z').split(b'\0'):
        if not rec:
            continue
        meta, path = rec.split(b'\t', 1)
        mode, blob, _stage = meta.decode().split()
        name = os.fsdecode(path)
        if mode in ('100644', '100755') and name not in dirty:
            out[name] = blob
    return out


def sources(primary: str) -> dict[str, str]:
    """blob -> a path in <primary> whose file may serve as the clone source for that blob.

    The one rule for what may be cloned, also used by new_worktree.py: a regular tracked file
    that `git status` reports unmodified, so a file with local edits is never a source. A source
    whose bytes still differ from the blob (an edit git's stat check missed, a checkout
    conversion) is caught after cloning: new_worktree.py has git re-hash every clone, and this
    script compares sha256 with the file it replaces."""
    by_blob: dict[str, str] = {}
    for path, blob in index(primary).items():
        by_blob.setdefault(blob, path)
    return by_blob


def replace_with_clones(primary: str, wt: str, by_blob: dict[str, str], files: dict[str, str],
                        min_kb: int, apply: bool) -> tuple[int, int, int]:
    """Replace each file of <wt> in files (path -> blob, unmodified) by a clone of its source.

    Only where the bytes are the same (sha256); also used by new_worktree.py for the files git
    wrote through a checkout conversion. Returns (files cloned, bytes, files skipped)."""
    done = skipped = nbytes = 0
    for path, blob in files.items():
        dst = os.path.join(wt, path)
        try:
            st = os.lstat(dst)
        except FileNotFoundError:
            continue
        if st.st_size < min_kb * 1024 or blob not in by_blob:
            continue
        src = os.path.join(primary, by_blob[blob])
        if not os.path.isfile(src) or os.path.getsize(src) != st.st_size:
            skipped += 1
            continue
        if not apply:
            done += 1
            nbytes += st.st_size
            continue
        want = sha256(dst)
        tmp = dst + '.clone-tmp'
        try:
            clone_plain(src, tmp)
        except OSError:
            skipped += 1
            continue
        try:
            if sha256(tmp) != want:
                raise OSError(0, 'the clone differs')
            os.chmod(tmp, st.st_mode & 0o7777)
            os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
            now = os.lstat(dst)
            if (now.st_mtime_ns, now.st_size) != (st.st_mtime_ns, st.st_size):
                raise OSError(0, 'changed under us')  # leave it
            os.replace(tmp, dst)
        except OSError:
            discard(tmp)
            skipped += 1
            continue
        done += 1
        nbytes += st.st_size
    return done, nbytes, skipped


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('primary')
    ap.add_argument('worktree')
    ap.add_argument('--min-kb', type=int, default=100)
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args(argv)
    if a.apply and sys.platform != 'darwin':
        print('clone_dedupe_worktree: --apply needs macOS (APFS clones)', file=sys.stderr)
        return 2
    primary, wt = os.path.realpath(a.primary), os.path.realpath(a.worktree)
    done, nbytes, skipped = replace_with_clones(primary, wt, sources(primary), index(wt),
                                                a.min_kb, a.apply)
    verb = 'cloned' if a.apply else 'would clone'
    print(f'{os.path.basename(wt)}: {verb} {done} files, {nbytes / 2**30:.2f} GiB; '
          f'skipped {skipped}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
