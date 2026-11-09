#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/chat_archivable.py in a scratch repository:
python3 tests/chat_archivable.py.

The repository has a bare origin whose default branch is main, and worktrees in each state a
finished chat can leave behind. Every "keep" case is a way archiving a chat could lose work or
take work off the sidebar that is only on this machine (changes, untracked files, a merge in
progress, commits never pushed, no origin at all); every "ok" case is a finished chat that would
otherwise clutter the sidebar for good (the worktree gone, HEAD in the default branch, the
branch pushed, a merge on GitHub seen only after the fetch). Offline: origin is a local folder.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'chat_archivable.py')


class ChatArchivable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='chat-archivable-')
        root = os.path.realpath(cls.tmp)
        cls.env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                       GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t.invalid',
                       GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t.invalid')
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
            cls.env.pop(key, None)
        cls.root = root
        cls.origin = os.path.join(root, 'origin.git')
        cls.repo = os.path.join(root, 'repo')
        cls.git(root, 'init', '-q', '--bare', '-b', 'main', cls.origin)
        cls.git(root, 'init', '-q', '-b', 'main', cls.repo)
        cls.git(cls.repo, 'remote', 'add', 'origin', cls.origin)
        with open(os.path.join(cls.repo, '.gitignore'), 'w') as f:
            f.write('build/\n')
        with open(os.path.join(cls.repo, 'f.txt'), 'w') as f:
            f.write('one\n')
        cls.git(cls.repo, 'add', '.gitignore', 'f.txt')
        cls.git(cls.repo, 'commit', '-q', '-m', 'init')
        cls.git(cls.repo, 'push', '-q', 'origin', 'main')
        cls.git(cls.repo, 'fetch', '-q', 'origin')
        cls.git(cls.repo, 'remote', 'set-head', 'origin', 'main')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def git(cls, cwd, *args):
        return subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True,
                              text=True, env=cls.env).stdout.strip()

    def worktree(self, name, base='origin/main'):
        path = os.path.join(self.root, 'repo-worktrees', name)
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/' + name, path, base)
        return path

    def commit(self, wt, text='more\n'):
        with open(os.path.join(wt, 'f.txt'), 'a') as f:
            f.write(text)
        self.git(wt, 'commit', '-q', '-am', 'work')

    def check(self, path, *extra):
        r = subprocess.run([sys.executable, TOOL, path, *extra], capture_output=True, text=True,
                           env=self.env)
        return r.returncode, r.stdout.strip()

    def assertOk(self, path, *extra):
        code, line = self.check(path, *extra)
        self.assertEqual(code, 0, line)
        self.assertTrue(line.startswith('ok'), line)
        return line

    def assertKeep(self, path, reason, *extra):
        code, line = self.check(path, *extra)
        self.assertEqual(code, 1, line)
        self.assertTrue(line.startswith('keep: '), line)
        self.assertIn(reason, line)

    def test_gone(self):
        self.assertIn('gone', self.assertOk(os.path.join(self.root, 'never-made')))

    def test_clean_on_the_default_branch(self):
        wt = self.worktree('clean')
        os.makedirs(os.path.join(wt, 'build'))
        with open(os.path.join(wt, 'build', 'out.o'), 'w') as f:
            f.write('ignored build output\n')
        self.assertIn('in origin/main', self.assertOk(wt))

    def test_changes_and_untracked_files_keep(self):
        wt = self.worktree('dirty')
        with open(os.path.join(wt, 'f.txt'), 'a') as f:
            f.write('unsaved\n')
        self.assertKeep(wt, 'changed or untracked')
        wt = self.worktree('untracked')
        with open(os.path.join(wt, 'new.txt'), 'w') as f:
            f.write('new\n')
        self.assertKeep(wt, 'new.txt')

    def test_untracked_files_hidden_by_configuration_keep(self):
        # status.showUntrackedFiles=no would hide them from a plain `git status --porcelain`
        wt = self.worktree('hidden-untracked')
        self.git(wt, 'config', 'status.showUntrackedFiles', 'no')
        try:
            os.makedirs(os.path.join(wt, 'deep', 'er'))
            with open(os.path.join(wt, 'deep', 'er', 'new.txt'), 'w') as f:
                f.write('new\n')
            self.assertKeep(wt, 'deep/er/new.txt')
        finally:
            self.git(wt, 'config', '--unset', 'status.showUntrackedFiles')

    def test_assume_unchanged_and_skip_worktree_keep(self):
        for flag, name in (('--assume-unchanged', 'assumed'), ('--skip-worktree', 'skipped')):
            wt = self.worktree(name)
            self.git(wt, 'update-index', flag, 'f.txt')
            with open(os.path.join(wt, 'f.txt'), 'a') as f:
                f.write('a change git status does not show\n')
            self.assertEqual(self.git(wt, 'status', '--porcelain'), '', flag)
            self.assertKeep(wt, 'hidden from git status')

    def test_a_folder_without_its_git_link_is_not_judged_by_the_enclosing_checkout(self):
        # a worktree made inside the primary checkout loses its .git link: git would answer for
        # the enclosing checkout, which is clean and on GitHub, and the work inside would go
        inner = os.path.join(self.repo, 'inner-wt')
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/inner', inner, 'origin/main')
        os.remove(os.path.join(inner, '.git'))
        with open(os.path.join(self.repo, '.git', 'info', 'exclude'), 'a') as f:
            f.write('inner-wt/\n')  # so the enclosing checkout itself stays clean
        self.assertKeep(inner, 'not the top of its own git worktree')
        # outside any checkout, the same folder is no worktree at all
        wt = self.worktree('lost-link')
        os.remove(os.path.join(wt, '.git'))
        code, line = self.check(wt)
        self.assertEqual(code, 1, line)

    def test_commit_not_pushed_keeps_until_the_branch_is_pushed(self):
        wt = self.worktree('ahead')
        self.commit(wt)
        self.assertKeep(wt, 'not on GitHub')
        self.git(wt, 'push', '-q', 'origin', 'agent/ahead')
        self.assertIn('origin/agent/ahead', self.assertOk(wt))
        # a later commit that was not pushed keeps it again
        self.commit(wt, 'later\n')
        self.assertKeep(wt, '1 commit(s) of agent/ahead')

    def test_a_merge_on_github_is_seen_after_the_fetch(self):
        wt = self.worktree('merged')
        self.commit(wt, 'merged\n')
        # someone merges it on GitHub: origin's main moves, nothing here knows yet
        self.git(self.origin, 'fetch', '-q', self.repo, 'agent/merged:main')
        self.assertKeep(wt, 'not on GitHub', '--no-fetch')
        self.assertIn('origin/main', self.assertOk(wt))

    def test_a_deleted_remote_branch_still_counts_as_pushed(self):
        wt = self.worktree('deleted')
        self.commit(wt, 'deleted\n')
        self.git(wt, 'push', '-q', 'origin', 'agent/deleted')
        self.git(self.origin, 'branch', '-D', 'agent/deleted')  # GitHub deleted it after merge
        self.assertIn('origin/agent/deleted', self.assertOk(wt))

    def test_detached_head(self):
        wt = self.worktree('detached')
        self.git(wt, 'switch', '-q', '--detach', 'origin/main')
        self.assertOk(wt)
        self.commit(wt, 'probe\n')
        self.assertKeep(wt, 'detached HEAD')

    def test_operation_in_progress_keeps(self):
        wt = self.worktree('merging')
        self.commit(wt, 'side a\n')
        other = self.worktree('other')
        self.commit(other, 'side b\n')
        subprocess.run(['git', '-C', wt, 'merge', 'agent/other'], capture_output=True,
                       env=self.env)  # conflicts on f.txt
        self.assertKeep(wt, 'in progress (MERGE_HEAD)')

    def test_no_origin_keeps(self):
        lone = os.path.join(self.root, 'lone')
        self.git(self.root, 'init', '-q', '-b', 'main', lone)
        self.git(lone, 'commit', '-q', '--allow-empty', '-m', 'x')
        self.assertKeep(lone, 'no remote origin')

    def test_not_a_worktree_and_usage(self):
        plain = os.path.join(self.root, 'plain')
        os.makedirs(plain, exist_ok=True)
        if not os.path.exists(os.path.join(self.root, '.git')):
            self.assertKeep(plain, 'not a git worktree')
        r = subprocess.run([sys.executable, TOOL], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, TOOL, 'a', 'b'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_a_failed_fetch_judges_on_the_refs_as_last_fetched(self):
        wt = self.worktree('offline')
        self.commit(wt, 'offline\n')
        self.git(wt, 'push', '-q', 'origin', 'agent/offline')
        moved = self.origin + '.away'
        os.rename(self.origin, moved)
        try:
            line = self.assertOk(wt)
            self.assertIn('fetch failed', line)
            self.commit(wt, 'unpushed\n')
            self.assertKeep(wt, 'fetch failed')
        finally:
            os.rename(moved, self.origin)


if __name__ == '__main__':
    unittest.main(verbosity=1)
