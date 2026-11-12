#!/usr/bin/env python3
"""Checks the core plugin's new_worktree.py in throwaway repositories: python3 tests/new_worktree.py.

The script's worktree is made beside a reference made by plain `git worktree add` from the same
primary checkout, and both must hold the same paths, bytes, modes, symlinks and index, with
`git status` clean, and the post-checkout hook must have run the same way in both (one hook
without a shebang, one failing, whose status the script must exit with while the worktree
stands). Also the refusals. The fixture carries the traps for clones: a file under 100 KB, an
executable whose blob a non-executable file also holds, a symlink, a submodule entry, a smudge
filter and an eol=crlf path whose primary bytes differ from what a checkout writes, and a
converted file whose bytes equal the primary's.

Every case runs with clones switched off (AGENTIC_GITHUB_FLOW_CLONES=0) and, on macOS, again
with the variable unset, where clones are the default: there the files the script cloned must
share their blocks with the primary checkout (same physical offset on disk) while git-written
files do not, a primary file with local edits is never a source, the switches turn it off and
on, the fallbacks say why, and clone_dedupe_worktree.py turns a plain worktree's files into
clones without changing a byte. Elsewhere the default must say nothing about clones and
`--clones` must be a no-op with one note. Offline. Not on Windows (shell hooks and a symlink in the fixture);
tests/worktree_tools.py covers the script there.
"""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'plugins' / 'core' / 'scripts' / 'new_worktree.py'
DEDUPE = ROOT / 'plugins' / 'core' / 'scripts' / 'clone_dedupe_worktree.py'
CLONES_ENV = 'AGENTIC_GITHUB_FLOW_CLONES'
MACOS = sys.platform == 'darwin'
F_LOG2PHYS_EXT = 65  # <sys/fcntl.h>


def physical_offset(path):
    """Device offset of the file's first block; two files share blocks when these are equal."""
    import fcntl
    import struct
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
        out = fcntl.fcntl(fd, F_LOG2PHYS_EXT, struct.pack('=Iqq', 0, 4096, 0))
        return struct.unpack('=Iqq', out)[2]
    finally:
        os.close(fd)


def _libc():
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    libc.listxattr.restype = ctypes.c_ssize_t
    libc.listxattr.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int)
    libc.setxattr.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t,
                              ctypes.c_uint32, ctypes.c_int)
    return ctypes, libc


def xattrs(path):
    """The names of path's extended attributes (macOS), com.apple.provenance aside: the
    system gives it to a file git writes too."""
    if not MACOS:
        return ()
    ctypes, libc = _libc()
    p = os.fsencode(str(path))
    size = libc.listxattr(p, None, 0, 1)  # 1 = XATTR_NOFOLLOW
    if size <= 0:
        return ()
    buf = ctypes.create_string_buffer(size)
    size = libc.listxattr(p, buf, size, 1)
    return tuple(sorted(n for n in buf.raw[:size].split(b'\0')
                        if n and n != b'com.apple.provenance'))


def setxattr(path, name, value):
    ctypes, libc = _libc()
    if libc.setxattr(os.fsencode(str(path)), name, value, len(value), 0, 0):
        raise OSError(ctypes.get_errno(), 'setxattr')


def snapshot(top):
    """rel path -> (st_mode, bytes or link target, flags, xattr names) for everything except
    the .git file."""
    out = {}
    for d, dirs, files in os.walk(top):
        for name in dirs + files:
            p = os.path.join(d, name)
            rel = os.path.relpath(p, top)
            if rel == '.git':
                continue
            st = os.lstat(p)
            meta = (getattr(st, 'st_flags', 0), xattrs(p))
            if stat.S_ISLNK(st.st_mode):
                out[rel] = (st.st_mode, os.readlink(p)) + meta
            elif stat.S_ISREG(st.st_mode):
                out[rel] = (st.st_mode, Path(p).read_bytes()) + meta
            else:
                out[rel] = (st.st_mode, None) + meta
    return out


@unittest.skipIf(os.name == 'nt', 'symlinks and shell hooks in the fixture')
class NewWorktree(unittest.TestCase):
    CLONES = '0'  # the environment variable's value for this class's cases; None: unset

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='new-worktree-')
        self.root = Path(os.path.realpath(self.tmp.name))
        self.env = dict(os.environ, GIT_AUTHOR_NAME='Worktree fixture',
                        GIT_AUTHOR_EMAIL='fixture@example.invalid',
                        GIT_COMMITTER_NAME='Worktree fixture',
                        GIT_COMMITTER_EMAIL='fixture@example.invalid',
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                    'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', CLONES_ENV):
            self.env.pop(key, None)
        if self.CLONES is not None:
            self.env[CLONES_ENV] = self.CLONES
        p = self.primary = self.root / 'repo'
        self.git(self.root, 'init', '-q', '-b', 'main', str(p))
        self.git(p, 'config', 'filter.upper.smudge', 'tr a-z A-Z')
        self.git(p, 'config', 'filter.upper.clean', 'tr A-Z a-z')
        files = {
            'README.md': b'# fixture\n',
            'empty.txt': b'',
            'bin/run.sh': b'#!/bin/sh\necho run\n',
            'bin/a-copy.txt': b'#!/bin/sh\necho run\n',  # same blob, not executable
            'assets/big.bin': os.urandom(1 << 20),
            'assets/small.bin': os.urandom(2000),  # under clone_dedupe_worktree's 100 KB
            'assets/dirty.bin': os.urandom(200_000),
            'dir with space/ünicöde.txt': 'café\n'.encode(),
            '.gitattributes': b'*.up filter=upper\n*.crlf text eol=crlf\n*.log text\n',
            'note.up': b'smudged on checkout\n',  # the primary keeps the clean bytes
            'lines.crlf': b'one\ntwo\n',          # the primary keeps LF
            'assets/text.log': b'a line of text\n' * 20_000,  # converted, same bytes
            'flags/locked.bin': os.urandom(200_000),  # Finder's "Locked" (uchg) on macOS
            'flags/hidden.txt': b'hidden\n',           # the hidden flag
            'flags/tagged.sh': b'#!/bin/sh\n',         # quarantine and a user attribute
        }
        for rel, data in files.items():
            (p / rel).parent.mkdir(parents=True, exist_ok=True)
            (p / rel).write_bytes(data)
        (p / 'bin/run.sh').chmod(0o755)
        (p / 'link').symlink_to('README.md')
        self.git(p, 'add', '.')
        self.git(p, 'commit', '-q', '-m', 'Fixture')
        self.git(p, 'update-index', '--add', '--cacheinfo',
                 '160000,%s,sub' % self.git(p, 'rev-parse', 'HEAD').strip())
        self.git(p, 'commit', '-q', '-m', 'Fixture submodule entry')
        (p / 'sub').mkdir()  # an uninitialised submodule is an empty directory
        if MACOS:  # metadata a clone must not take over from the primary's files
            for rel in ('flags/locked.bin', '.gitattributes'):  # .gitattributes: the probe
                os.chflags(str(p / rel), stat.UF_IMMUTABLE)
            os.chflags(str(p / 'flags/hidden.txt'), stat.UF_HIDDEN)
            setxattr(p / 'flags/tagged.sh', b'user.note', b'a tag')
            setxattr(p / 'flags/tagged.sh', b'com.apple.quarantine', b'0081;00000000;Test;')
        self.assertEqual(self.git(p, 'status', '--porcelain'), '')
        self.assertNotEqual((p / 'note.up').read_bytes(), b'SMUDGED ON CHECKOUT\n')

    def unlock(self):
        """Clear the flags of every file below the test folder, so it can change or go."""
        if MACOS:
            for d, _dirs, files in os.walk(str(self.root)):
                for name in files:
                    if getattr(os.lstat(os.path.join(d, name)), 'st_flags', 0):
                        os.chflags(os.path.join(d, name), 0, follow_symlinks=False)

    def tearDown(self):
        self.unlock()
        self.tmp.cleanup()

    def git(self, cwd, *args):
        r = subprocess.run(['git', *args], cwd=cwd, env=self.env, text=True, capture_output=True)
        if r.returncode:
            raise AssertionError('git %s: %s%s' % (args, r.stderr, r.stdout))
        return r.stdout

    def run_tool(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd or self.primary,
                              env=self.env, text=True, capture_output=True)

    def make(self, task='task', base='main', extra=()):
        """The script's worktree and a plain `git worktree add` reference from the same base."""
        ref = self.root / ('ref-' + task)
        self.git(self.primary, 'worktree', 'add', '-q', '-b', 'ref/' + task, str(ref), base)
        r = self.run_tool(task, '--base', base, *extra)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        wt = self.root / 'repo-worktrees' / task
        self.assertEqual(self.git(wt, 'rev-parse', '--abbrev-ref', 'HEAD').strip(),
                         'agent/' + task)
        return wt, ref, r.stdout

    def assert_like_reference(self, wt, ref):
        self.assertEqual(snapshot(wt), snapshot(ref))
        self.assertEqual(self.git(wt, 'ls-files', '-s'), self.git(ref, 'ls-files', '-s'))
        self.assertEqual(self.git(wt, 'status', '--porcelain', '--ignored'), '')

    def shared(self, wt, rel):
        """Whether <wt>/<rel> shares its blocks with some file of the primary checkout."""
        offsets = {physical_offset(p) for p in self.primary.rglob('*')
                   if '.git' not in p.relative_to(self.primary).parts
                   and p.is_file() and not p.is_symlink() and p.stat().st_size}
        return physical_offset(wt / rel) in offsets

    # -- the result is a normal checkout --

    def test_same_as_git_worktree_add(self):
        wt, ref, out = self.make()
        self.assert_like_reference(wt, ref)
        self.assertEqual((wt / 'note.up').read_bytes(), b'SMUDGED ON CHECKOUT\n')
        self.assertEqual((wt / 'lines.crlf').read_bytes(), b'one\r\ntwo\r\n')
        self.assertTrue(os.access(str(wt / 'bin/run.sh'), os.X_OK))

    def test_from_another_base(self):
        # Files that differ from the primary or are missing there come from git.
        self.git(self.primary, 'switch', '-q', '-c', 'other')
        (self.primary / 'README.md').write_text('# changed on other\n')
        (self.primary / 'only-other.bin').write_bytes(os.urandom(150_000))
        self.git(self.primary, 'add', '.')
        self.git(self.primary, 'commit', '-q', '-m', 'Other')
        self.git(self.primary, 'switch', '-q', 'main')
        wt, ref, _ = self.make(base='other')
        self.assert_like_reference(wt, ref)
        self.assertEqual((wt / 'README.md').read_text(), '# changed on other\n')

    def test_paths_differing_only_in_case_end_as_git_leaves_them(self):
        probe = self.root / 'Case-Probe'
        probe.mkdir()
        if not (self.root / 'case-probe').exists():
            self.skipTest('a case-sensitive file system')
        blob = subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=str(self.primary),
                              env=self.env, input='lower\n', text=True,
                              capture_output=True).stdout.strip()
        self.git(self.primary, 'update-index', '--add', '--cacheinfo',
                 '100644,%s,readme.md' % blob)
        self.git(self.primary, 'commit', '-q', '-m', 'README.md and readme.md')
        wt, ref, out = self.make()
        if self.CLONES != '0':
            self.assertIn('git checks out every file', out)
        self.assertEqual(snapshot(wt), snapshot(ref))
        self.assertEqual(self.git(wt, 'ls-files', '-s'), self.git(ref, 'ls-files', '-s'))
        self.assertEqual(self.git(wt, 'status', '--porcelain'),
                         self.git(ref, 'status', '--porcelain'))

    # -- clones by default on macOS only, and off when switched off --

    @unittest.skipUnless(MACOS, 'APFS clones are macOS only')
    def test_switched_off_nothing_is_cloned(self):
        if self.CLONES != '0':
            self.skipTest('clones are on in this class')
        wt, ref, out = self.make()
        self.assertNotIn('clone', out)
        self.assertFalse(self.shared(wt, 'assets/big.bin'))

    @unittest.skipIf(MACOS, 'the default off macOS')
    def test_off_macos_the_default_is_todays_worktree(self):
        self.env.pop(CLONES_ENV, None)
        wt, ref, out = self.make()
        self.assertNotIn('clone', out)
        self.assert_like_reference(wt, ref)

    @unittest.skipIf(MACOS, 'the no-op note is for systems without APFS clones')
    def test_clones_are_a_no_op_off_macos(self):
        self.env.pop(CLONES_ENV, None)
        wt, ref, out = self.make(extra=('--clones',))
        self.assertEqual(out.count('no clones (APFS clones are macOS only); a plain checkout\n'),
                         1, out)
        self.assertNotIn('dedupe', out)
        self.assert_like_reference(wt, ref)

    # -- the post-checkout hook, as git runs it --

    def hook(self, text):
        hook = self.primary / '.git' / 'hooks' / 'post-checkout'
        hook.write_text(text)
        hook.chmod(0o755)

    def test_post_checkout_hook_runs_as_in_git_worktree_add(self):
        self.hook('#!/bin/sh\n'
                  'log="%s/hook-$(basename "$PWD").log"\n'
                  'echo "$@" "GIT_DIR=${GIT_DIR-unset}" > "$log"\n'
                  'git ls-files -m | wc -l | tr -d " " >> "$log"\n' % self.root)
        self.make()
        mine = (self.root / 'hook-task.log').read_text()
        self.assertEqual(mine, (self.root / 'hook-ref-task.log').read_text())
        self.assertTrue(mine.endswith('GIT_DIR=unset\n0\n'), mine)  # files in place at hook time

    def test_post_checkout_hook_without_shebang_runs_through_sh(self):
        # git execs /bin/sh <hook> <args> when the hook itself fails with ENOEXEC.
        self.hook('echo hook-ran "$@" > "%s/proof-$(basename "$PWD").txt"\n' % self.root)
        wt, ref, _ = self.make()
        mine = (self.root / 'proof-task.txt').read_text()
        self.assertEqual(mine, (self.root / 'proof-ref-task.txt').read_text())
        self.assertTrue(mine.startswith('hook-ran '), mine)
        self.assert_like_reference(wt, ref)

    def test_failing_post_checkout_hook_keeps_the_worktree_as_git_does(self):
        self.hook('#!/bin/sh\nexit 3\n')
        ref = self.root / 'ref-task'
        r = subprocess.run(['git', 'worktree', 'add', '-q', '-b', 'ref/task', str(ref), 'main'],
                           cwd=str(self.primary), env=self.env, capture_output=True)
        self.assertEqual(r.returncode, 3)  # git: the hook's status, the worktree kept
        r = self.run_tool('task')
        self.assertEqual(r.returncode, 3, r.stderr + r.stdout)
        self.assertIn('the post-checkout hook exited 3', r.stderr)
        wt = self.root / 'repo-worktrees' / 'task'
        self.assertEqual(self.git(wt, 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'agent/task')
        self.assert_like_reference(wt, ref)

    # -- every refusal stays --

    def assert_refused(self, r, reason):
        self.assertEqual(r.returncode, 1, r.stderr + r.stdout)
        self.assertIn(reason, r.stderr)

    def test_refusals(self):
        self.assert_refused(self.run_tool('../escape'), 'plain name')
        self.git(self.primary, 'branch', 'agent/taken')
        self.assert_refused(self.run_tool('taken'), 'exists already')
        (self.root / 'repo-worktrees' / 'there').mkdir(parents=True)
        self.assert_refused(self.run_tool('there'), 'exists already')
        wt, _, _ = self.make('first')
        self.assert_refused(self.run_tool('second', cwd=wt), 'primary checkout')
        self.assertEqual(sorted(p.name for p in (self.root / 'repo-worktrees').iterdir()),
                         ['first', 'there'])
        self.assertEqual(self.run_tool().returncode, 2)


@unittest.skipUnless(MACOS, 'APFS clones are macOS only')
class NewWorktreeWithClones(NewWorktree):
    """Every case above again with the variable unset (clones by default), and the clones."""
    CLONES = None

    def assert_shared(self, wt, rel, shared=True):
        same = self.shared(wt, rel)
        self.assertEqual(same, shared, '%s: shares blocks with the primary: %s' % (rel, same))

    def test_files_share_blocks_with_the_primary(self):
        wt, ref, out = self.make()
        self.assertIn('cloned', out)
        for rel in ('assets/big.bin', 'assets/small.bin', 'README.md', 'bin/run.sh',
                    'bin/a-copy.txt', 'dir with space/ünicöde.txt', '.gitattributes',
                    'flags/locked.bin', 'flags/hidden.txt', 'flags/tagged.sh'):
            self.assert_shared(wt, rel)
        self.assert_shared(ref, 'assets/big.bin', shared=False)  # the measuring stick works
        for rel in ('note.up', 'lines.crlf'):  # a checkout conversion: git writes them
            self.assert_shared(wt, rel, shared=False)
        # A converted file git wrote with the primary's bytes becomes a clone after all.
        self.assert_shared(wt, 'assets/text.log')

    def test_the_switches_turn_clones_off_and_on(self):
        # (environment value, flags, cloned): the flag wins over the variable.
        for i, (value, flags, cloned) in enumerate((('1', (), True),
                                                    (None, ('--no-clones',), False),
                                                    ('0', (), False),
                                                    ('0', ('--clones',), True))):
            self.env.pop(CLONES_ENV, None)
            if value is not None:
                self.env[CLONES_ENV] = value
            wt, ref, out = self.make('switch-%d' % i, extra=flags)
            self.assertEqual('cloned' in out, cloned, out)
            self.assert_shared(wt, 'assets/big.bin', shared=cloned)
            self.assert_like_reference(wt, ref)

    def test_primary_file_with_local_edits_is_not_cloned(self):
        committed = (self.primary / 'assets/dirty.bin').read_bytes()
        (self.primary / 'assets/dirty.bin').write_bytes(os.urandom(len(committed)))
        # An edit that `git status` does not show: git's re-hash of the clone must catch it.
        self.git(self.primary, 'update-index', '--assume-unchanged', 'README.md')
        (self.primary / 'README.md').write_text('# hidden local edit\n')
        wt, ref, _ = self.make()
        self.assertEqual((wt / 'assets/dirty.bin').read_bytes(), committed)
        self.assertEqual((wt / 'README.md').read_text(), '# fixture\n')
        for rel in ('assets/dirty.bin', 'README.md'):
            self.assert_shared(wt, rel, shared=False)
        self.assert_like_reference(wt, ref)

    # -- where cloning cannot work: a plain checkout, with a note --

    def test_falls_back_under_autocrlf(self):
        self.git(self.primary, 'config', 'core.autocrlf', 'true')
        wt, ref, out = self.make()
        self.assertIn('no clones (core.autocrlf is true); a plain checkout, then deduplication',
                      out)
        self.assertIn('dedupe: task: cloned', out)
        self.assert_like_reference(wt, ref)

    def test_falls_back_under_sparse_checkout(self):
        self.unlock()  # the sparse checkout removes flags/locked.bin from the primary
        self.git(self.primary, 'sparse-checkout', 'set', 'assets')
        wt, ref, out = self.make()
        self.assertIn('no clones (sparse checkout is on)', out)
        self.assertFalse((wt / 'bin').exists())
        self.assert_like_reference(wt, ref)

    # -- clone_dedupe_worktree.py on a plain worktree --

    def test_dedupe_turns_a_plain_worktree_into_clones(self):
        wt = self.root / 'plain'
        self.git(self.primary, 'worktree', 'add', '-q', '-b', 'plain', str(wt), 'main')
        (wt / 'assets/dirty.bin').write_bytes(b'local edit\n' * 20_000)
        before = snapshot(wt)
        mtime = os.stat(str(wt / 'assets/big.bin')).st_mtime_ns
        dry = subprocess.run([sys.executable, str(DEDUPE), str(self.primary), str(wt)],
                             env=self.env, text=True, capture_output=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('would clone 3 files', dry.stdout)  # big.bin, text.log, locked.bin
        self.assert_shared(wt, 'assets/big.bin', shared=False)
        r = subprocess.run([sys.executable, str(DEDUPE), '--apply', str(self.primary), str(wt)],
                           env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('plain: cloned 3 files', r.stdout)
        self.assert_shared(wt, 'flags/locked.bin')  # unlocked, as git wrote it: snapshot
        self.assert_shared(wt, 'assets/big.bin')
        self.assert_shared(wt, 'assets/text.log')
        self.assert_shared(wt, 'assets/dirty.bin', shared=False)  # modified: never touched
        self.assert_shared(wt, 'assets/small.bin', shared=False)  # under --min-kb
        self.assertEqual(snapshot(wt), before)
        self.assertEqual(os.stat(str(wt / 'assets/big.bin')).st_mtime_ns, mtime)
        self.assertEqual(self.git(wt, 'status', '--porcelain'), ' M assets/dirty.bin\n')


if __name__ == '__main__':
    unittest.main()
