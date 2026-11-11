#!/usr/bin/env python3
"""Checks merge_landing.py (#50, frozen .claude) in throwaway repositories:
python3 tests/merge_landing.py.

A bare repository stands in for GitHub. The task worktree's .claude/ is made read-only (mode
555 directories, 444 files) to stand in for the Claude Code sandbox, which keeps a session from
writing its own working directory's .claude/: a plain `git merge` of a main that changed
.claude/ then fails as it does in the sandbox. On Windows, or as root, a mode cannot protect a
folder: there the cases run unprotected, which the tool treats the same, and only the baseline
failure is skipped. Then remove_merged_worktree.py and chat_archivable.py must accept the frozen
worktree once its work is merged, and keep it when a frozen file changed. Offline.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'merge_landing.py')
REMOVE = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'remove_merged_worktree.py')
ARCHIVABLE = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'chat_archivable.py')
CAN_PROTECT = os.name != 'nt' and os.geteuid() != 0


class FrozenMerge(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix='merge-landing-'))
        config = os.path.join(self.dir, 'gitconfig')
        with open(config, 'w') as f:
            f.write('[advice]\n\tdetachedHead = false\n')
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=config,
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                        AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, '-c',
                                                           'print("[]")']))
        self.origin = os.path.join(self.dir, 'origin.git')
        self.repo = os.path.join(self.dir, 'repo')
        self.wt = os.path.join(self.dir, 'repo-worktrees', 'task')
        self.git(self.dir, 'init', '-q', '--bare', '-b', 'main', self.origin)
        self.git(self.dir, 'clone', '-q', self.origin, self.repo)
        for rel, text in (('README.md', 'start\n'), ('.claude/settings.json', 's1\n'),
                          ('.claude/old.md', 'old\n'), ('.claude/agents/a.md', 'agent\n'),
                          ('.claude/.gitignore', 'settings.local.json\n'), ('.mcp.json', '{}\n')):
            self.write(self.repo, rel, text)
        self.commit(self.repo, 'start', 'README.md', '.claude', '.mcp.json')
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'remote', 'set-head', 'origin', 'main')
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/task', self.wt, 'origin/main')
        self.write(self.wt, 'task.txt', 'task\n')
        self.commit(self.wt, 'task', 'task.txt')
        self.write(self.wt, '.claude/settings.local.json', 'local\n')  # ignored, never tracked
        self.protected = False

    def tearDown(self):
        self.protect(False)
        shutil.rmtree(self.dir, ignore_errors=True)

    # helpers
    def git(self, cwd, *args, check=True):
        r = subprocess.run(['git', *args], cwd=cwd, env=self.env, capture_output=True, text=True)
        if check and r.returncode:
            raise AssertionError('git %s: %s' % (' '.join(args), r.stderr))
        return r

    def write(self, folder, rel, text):
        path = os.path.join(folder, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', newline='') as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.wt, *rel.split('/')), newline='') as f:
            return f.read()

    def commit(self, cwd, message, *paths):
        self.git(cwd, 'add', '--', *paths)
        self.git(cwd, 'commit', '-q', '-m', message)

    def land_on_main(self, message, writes=(), deletes=()):
        """A commit on origin's main made from the primary checkout, as another chat's merge."""
        for rel, text in writes:
            self.write(self.repo, rel, text)
        if deletes:
            self.git(self.repo, 'rm', '-q', '--', *deletes)
        self.commit(self.repo, message, *[rel for rel, _ in writes] or ['README.md'])
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.git(self.wt, 'fetch', '-q', 'origin')

    def protect(self, on=True):
        """Stand in for the sandbox: the task worktree's .claude/ becomes read-only."""
        if on and not CAN_PROTECT:
            return
        for folder, _, files in os.walk(os.path.join(self.wt, '.claude')):
            for name in files:
                os.chmod(os.path.join(folder, name), 0o444 if on else 0o644)
            os.chmod(folder, 0o555 if on else 0o755)
        self.protected = on

    def tool(self, *args):
        r = subprocess.run([sys.executable, TOOL, '-C', self.wt, *args], env=self.env,
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def claude_files(self):
        found = {}
        for folder, _, files in os.walk(os.path.join(self.wt, '.claude')):
            for name in files:
                full = os.path.join(folder, name)
                with open(full, 'rb') as f:
                    found[os.path.relpath(full, self.wt).replace(os.sep, '/')] = f.read()
        return found

    def head(self, ref='HEAD'):
        return self.git(self.wt, 'rev-parse', ref).stdout.strip()

    def merge_tree(self):
        return self.git(self.wt, 'merge-tree', '--write-tree', 'HEAD', 'origin/main'
                        ).stdout.split()[0]

    def main_changes_claude(self):
        self.land_on_main('main changes .claude',
                          writes=[('README.md', 'main\n'), ('.claude/settings.json', 's2\n'),
                                  ('.claude/skills/x/SKILL.md', 'skill\n')],
                          deletes=['.claude/old.md'])

    # cases
    @unittest.skipUnless(CAN_PROTECT, 'a file mode cannot protect a folder here')
    def test_baseline_a_plain_merge_fails_on_a_protected_claude(self):
        self.main_changes_claude()
        before = self.head()
        self.protect()
        r = self.git(self.wt, 'merge', '--no-edit', 'origin/main', check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('.claude', r.stderr)
        self.assertEqual(self.head(), before)

    def test_a_merge_without_claude_changes_is_a_plain_merge(self):
        self.land_on_main('readme only', writes=[('README.md', 'main\n')])
        self.protect()
        expected = self.merge_tree()
        code, out = self.tool('origin/main')
        self.assertEqual(code, 0, out)
        self.assertNotIn('frozen', out)
        self.assertEqual(self.head('HEAD^{tree}'), expected)
        self.assertEqual(len(self.git(self.wt, 'rev-list', '--parents', '-1', 'HEAD'
                                      ).stdout.split()), 3)
        self.assertFalse(os.path.exists(os.path.join(
            self.git(self.wt, 'rev-parse', '--absolute-git-dir').stdout.strip(),
            'agentic-github-flow-frozen.json')))
        code, out = self.tool('origin/main')
        self.assertEqual(code, 0, out)
        self.assertIn('nothing to merge', out)

    def test_the_frozen_merge_commits_the_merge_and_leaves_claude_alone(self):
        self.main_changes_claude()
        self.protect()
        before = self.claude_files()
        expected = self.merge_tree()
        code, out = self.tool('origin/main')
        self.assertEqual(code, 0, out)
        self.assertIn('frozen', out)
        self.assertEqual(self.head('HEAD^{tree}'), expected)
        self.assertEqual(len(self.git(self.wt, 'rev-list', '--parents', '-1', 'HEAD'
                                      ).stdout.split()), 3)
        self.assertEqual(self.read('README.md'), 'main\n')
        after = self.claude_files()
        if self.protected:  # the deleted file stays on disk, untracked
            self.assertEqual(after, before)
            self.assertEqual(self.git(self.wt, 'status', '--porcelain').stdout,
                             '?? .claude/old.md\n')
        else:  # unprotected, git deletes what main deleted, and writes nothing else
            del before['.claude/old.md']
            self.assertEqual(after, before)
            self.assertEqual(self.git(self.wt, 'status', '--porcelain').stdout, '')
        self.assertEqual(self.read('.claude/settings.local.json'), 'local\n')
        self.assertEqual(self.git(self.wt, 'show', 'HEAD:.claude/settings.json').stdout, 's2\n')
        flags = self.git(self.wt, 'ls-files', '-v', '--', '.claude').stdout.splitlines()
        self.assertIn('S .claude/settings.json', flags)
        self.assertIn('S .claude/skills/x/SKILL.md', flags)
        self.assertIn('H .claude/agents/a.md', flags)
        # a follow-up commit, and later merges: one of other files, one of a frozen path again
        self.write(self.wt, 'more.txt', 'more\n')
        self.commit(self.wt, 'follow-up', 'more.txt')
        self.land_on_main('readme again', writes=[('README.md', 'again\n')])
        code, out = self.tool('origin/main')
        self.assertEqual(code, 0, out)
        self.land_on_main('settings again', writes=[('.claude/settings.json', 's3\n'),
                                                    ('.mcp.json', '{"x": 1}\n')])
        expected = self.merge_tree()
        code, out = self.tool('origin/main')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.head('HEAD^{tree}'), expected)
        self.assertEqual(self.read('.claude/settings.json'), 's1\n')
        self.assertEqual(self.read('.mcp.json'), '{}\n')
        self.assertEqual(self.read('README.md'), 'again\n')

    def test_a_conflict_in_claude_is_refused_and_changes_nothing(self):
        self.land_on_main('main settings', writes=[('.claude/settings.json', 'main\n')])
        self.write(self.wt, '.claude/settings.json', 'task\n')
        self.commit(self.wt, 'task settings', '.claude/settings.json')
        self.protect()
        before, flags = self.head(), self.git(self.wt, 'ls-files', '-v').stdout
        code, out = self.tool('origin/main')
        self.assertEqual(code, 1, out)
        self.assertIn('integration worktree', out)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.git(self.wt, 'ls-files', '-v').stdout, flags)
        self.assertEqual(self.git(self.wt, 'status', '--porcelain').stdout, '')

    def test_a_changed_claude_file_on_disk_is_refused(self):
        self.main_changes_claude()
        self.write(self.wt, '.claude/settings.json', 'edited\n')
        before = self.head()
        code, out = self.tool('origin/main')
        self.assertEqual(code, 1, out)
        self.assertIn('.claude/settings.json differs from HEAD', out)
        self.assertEqual(self.head(), before)
        self.assertNotIn('S ', self.git(self.wt, 'ls-files', '-v').stdout)

    def test_the_primary_checkout_is_refused(self):
        other = os.path.join(self.dir, 'other')
        self.git(self.dir, 'clone', '-q', self.origin, other)
        self.main_changes_claude()
        self.git(other, 'fetch', '-q', 'origin')
        self.write(other, 'own.txt', 'own\n')
        self.commit(other, 'own', 'own.txt')
        r = subprocess.run([sys.executable, TOOL, '-C', other, 'origin/main'], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('primary checkout', r.stderr)

    def test_the_frozen_worktree_is_archivable_and_removable_once_merged(self):
        self.main_changes_claude()
        self.protect()
        code, out = self.tool('origin/main')
        self.assertEqual(code, 0, out)
        self.git(self.wt, 'push', '-q', 'origin', 'agent/task')
        r = subprocess.run([sys.executable, ARCHIVABLE, self.wt], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith('ok'), r.stdout)
        # the sandbox ends with the chat; the cleanup runs from another session. An ignored
        # file keeps a worktree unless proven regenerable, frozen or not: not this test's case
        self.protect(False)
        os.remove(os.path.join(self.wt, '.claude', 'settings.local.json'))
        self.git(self.repo, 'merge', '-q', '--no-ff', '-m', 'merge task', 'origin/agent/task')
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.write(self.wt, '.claude/settings.json', 'changed after the freeze\n')
        r = subprocess.run([sys.executable, REMOVE, self.wt], cwd=self.repo, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('settings.json (hidden by skip-worktree)', r.stdout)
        r = subprocess.run([sys.executable, ARCHIVABLE, self.wt], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.write(self.wt, '.claude/settings.json', 's1\n')
        if CAN_PROTECT:
            self.assertTrue(os.path.isfile(os.path.join(self.wt, '.claude', 'old.md')))
        r = subprocess.run([sys.executable, REMOVE, self.wt], cwd=self.repo, env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('frozen by merge_landing.py', r.stdout)
        self.assertFalse(os.path.exists(self.wt))

    def test_an_untracked_file_that_is_not_frozen_still_keeps_the_worktree(self):
        self.main_changes_claude()
        self.protect()
        self.assertEqual(self.tool('origin/main')[0], 0)
        self.protect(False)
        self.write(self.wt, '.claude/notes.md', 'mine\n')
        self.git(self.wt, 'push', '-q', 'origin', 'agent/task')
        r = subprocess.run([sys.executable, ARCHIVABLE, self.wt], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('.claude/notes.md', r.stdout)


if __name__ == '__main__':
    unittest.main()
