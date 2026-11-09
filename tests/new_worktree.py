#!/usr/bin/env python3
"""Checks the core plugin's new_worktree.py in throwaway repositories: python3 tests/new_worktree.py.

Each case makes a worktree with the script beside a reference made by plain `git worktree add`
from the same primary checkout: both must hold the same paths, bytes, modes, symlinks and index,
with `git status` clean. On macOS the files the script cloned must share their blocks with the
primary checkout (same physical offset on disk) while files git wrote do not. The fixture
carries the traps: a file under 100 KB, an executable whose blob a non-executable file also
holds, a symlink, a submodule entry, a smudge filter and an eol=crlf path whose primary bytes
differ from what a checkout writes, a primary file with local edits, and post-checkout hooks
(one without a shebang, one failing). Elsewhere the script is a plain `git worktree add`, and
the same comparisons hold. Offline. Not on Windows, where the script is unchanged and
tests/worktree_tools.py covers it (the fixture needs symlinks and shell hooks).
"""
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / 'plugins' / 'core' / 'scripts' / 'new_worktree.py'
MACOS = sys.platform == 'darwin'
F_LOG2PHYS_EXT = 65  # <sys/fcntl.h>


def physical_offset(path):
    """Device offset of the file's first block; two files share blocks when these are equal."""
    import fcntl
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
        out = fcntl.fcntl(fd, F_LOG2PHYS_EXT, struct.pack('=Iqq', 0, 4096, 0))
        return struct.unpack('=Iqq', out)[2]
    finally:
        os.close(fd)


def snapshot(top):
    """rel path -> (st_mode, bytes or link target) for everything except the .git file."""
    out = {}
    for d, dirs, files in os.walk(top):
        for name in dirs + files:
            p = os.path.join(d, name)
            rel = os.path.relpath(p, top)
            if rel == '.git':
                continue
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                out[rel] = (st.st_mode, os.readlink(p))
            elif stat.S_ISREG(st.st_mode):
                out[rel] = (st.st_mode, Path(p).read_bytes())
            else:
                out[rel] = (st.st_mode, None)
    return out


@unittest.skipIf(os.name == 'nt', 'symlinks and shell hooks in the fixture')
class NewWorktree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='new-worktree-')
        self.root = Path(os.path.realpath(self.tmp.name))
        self.env = dict(os.environ, GIT_AUTHOR_NAME='Worktree fixture',
                        GIT_AUTHOR_EMAIL='fixture@example.invalid',
                        GIT_COMMITTER_NAME='Worktree fixture',
                        GIT_COMMITTER_EMAIL='fixture@example.invalid',
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                    'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
            self.env.pop(key, None)
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
            'assets/small.bin': os.urandom(2000),  # under the 100 KB of converted files
            'assets/dirty.bin': os.urandom(200_000),
            'dir with space/ünicöde.txt': 'café\n'.encode(),
            '.gitattributes': b'*.up filter=upper\n*.crlf text eol=crlf\n*.log text\n',
            'note.up': b'smudged on checkout\n',  # the primary keeps the clean bytes
            'lines.crlf': b'one\ntwo\n',          # the primary keeps LF
            'assets/text.log': b'a line of text\n' * 20_000,  # converted, same bytes
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
        self.assertEqual(self.git(p, 'status', '--porcelain'), '')
        self.assertNotEqual((p / 'note.up').read_bytes(), b'SMUDGED ON CHECKOUT\n')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, cwd, *args):
        r = subprocess.run(['git', *args], cwd=cwd, env=self.env, text=True, capture_output=True)
        if r.returncode:
            raise AssertionError('git %s: %s%s' % (args, r.stderr, r.stdout))
        return r.stdout

    def run_tool(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd or self.primary,
                              env=self.env, text=True, capture_output=True)

    def make(self, task='task', base='main'):
        """The script's worktree and a plain `git worktree add` reference from the same base."""
        ref = self.root / ('ref-' + task)
        self.git(self.primary, 'worktree', 'add', '-q', '-b', 'ref/' + task, str(ref), base)
        r = self.run_tool(task, '--base', base)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        wt = self.root / 'repo-worktrees' / task
        self.assertEqual(self.git(wt, 'rev-parse', '--abbrev-ref', 'HEAD').strip(),
                         'agent/' + task)
        return wt, ref, r.stdout

    def assert_like_reference(self, wt, ref):
        self.assertEqual(snapshot(wt), snapshot(ref))
        self.assertEqual(self.git(wt, 'ls-files', '-s'), self.git(ref, 'ls-files', '-s'))
        self.assertEqual(self.git(wt, 'status', '--porcelain', '--ignored'), '')

    def assert_shared(self, wt, rel, shared=True):
        """Whether <wt>/<rel> shares its blocks with some file of the primary checkout."""
        offsets = {physical_offset(p) for p in self.primary.rglob('*')
                   if '.git' not in p.relative_to(self.primary).parts
                   and p.is_file() and not p.is_symlink() and p.stat().st_size}
        same = physical_offset(wt / rel) in offsets
        self.assertEqual(same, shared, '%s: shares blocks with the primary: %s' % (rel, same))

    # -- the result is a normal checkout --

    def test_same_as_git_worktree_add(self):
        wt, ref, out = self.make()
        self.assert_like_reference(wt, ref)
        self.assertEqual((wt / 'note.up').read_bytes(), b'SMUDGED ON CHECKOUT\n')
        self.assertEqual((wt / 'lines.crlf').read_bytes(), b'one\r\ntwo\r\n')
        self.assertTrue(os.access(str(wt / 'bin/run.sh'), os.X_OK))
        self.assertEqual('cloned' in out, MACOS, out)

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

    # -- clones, and only where they are right --

    @unittest.skipUnless(MACOS, 'APFS clones are macOS only')
    def test_files_share_blocks_with_the_primary(self):
        wt, ref, _ = self.make()
        for rel in ('assets/big.bin', 'assets/small.bin', 'README.md', 'bin/run.sh',
                    'bin/a-copy.txt', 'dir with space/ünicöde.txt'):
            self.assert_shared(wt, rel)
        self.assert_shared(ref, 'assets/big.bin', shared=False)  # the measuring stick works
        for rel in ('note.up', 'lines.crlf'):  # a checkout conversion: git writes them
            self.assert_shared(wt, rel, shared=False)
        # A converted file git wrote with the primary's bytes becomes a clone again.
        self.assert_shared(wt, 'assets/text.log')

    @unittest.skipUnless(MACOS, 'APFS clones are macOS only')
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

    # -- where cloning cannot work: a plain checkout, with a note on macOS --

    def test_plain_checkout_under_autocrlf(self):
        self.git(self.primary, 'config', 'core.autocrlf', 'true')
        wt, ref, out = self.make()
        self.assertEqual('no clones (core.autocrlf is true)' in out, MACOS, out)
        self.assert_like_reference(wt, ref)

    def test_plain_checkout_under_sparse_checkout(self):
        self.git(self.primary, 'sparse-checkout', 'set', 'assets')
        wt, ref, out = self.make()
        self.assertEqual('no clones (sparse checkout is on)' in out, MACOS, out)
        self.assertFalse((wt / 'bin').exists())
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


if __name__ == '__main__':
    unittest.main()
