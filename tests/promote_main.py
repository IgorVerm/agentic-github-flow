#!/usr/bin/env python3
"""Checks plugins/core/scripts/promote_main.py in throwaway repositories: python3 tests/promote_main.py.

Each repository has a bare `origin` on disk (not on GitHub, so the landing mode comes from the
setting `landing` in HANDOFF.md on origin's main, or, without a remote, from rule 2). The
candidate is a commit on a task branch in a linked worktree. Each case is a way a landing could
lose or bypass something: landing in pull-request mode, a landing branch that moved, a remote
commit the candidate lacks, a primary checkout on another branch, a git operation in progress,
staged changes, a local file of another session that the change would overwrite, and the
landing branch setting. Offline: no network, no gh.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'promote_main.py')
LOCAL_MAIN = ('# Handoff\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n'
              '| landing | local main |\n%s')


def git(cwd, *args, check=True):
    r = subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
    if check and r.returncode:
        raise AssertionError('git %s: %s' % (' '.join(args), r.stderr))
    return r.stdout.strip()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(text)


class Promote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.bare = os.path.join(t, 'origin.git')
        self.primary = os.path.join(t, 'repo')
        self.wt = os.path.join(t, 'repo-worktrees', 'task')
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', self.bare], check=True)
        os.makedirs(self.primary)
        git(self.primary, 'init', '-q', '-b', 'main')
        self.ident(self.primary)
        self.handoff('')

    def ident(self, where):
        git(where, 'config', 'user.email', 'test@example.com')
        git(where, 'config', 'user.name', 'Test')

    def handoff(self, extra_rows):
        write(os.path.join(self.primary, 'HANDOFF.md'), LOCAL_MAIN % extra_rows)
        write(os.path.join(self.primary, 'app.txt'), 'one\n')
        git(self.primary, 'add', '--', 'HANDOFF.md', 'app.txt')
        git(self.primary, 'commit', '-q', '-m', 'base')
        git(self.primary, 'remote', 'add', 'origin', self.bare)
        git(self.primary, 'push', '-q', 'origin', 'main')
        git(self.primary, 'fetch', '-q', 'origin')
        git(self.primary, 'remote', 'set-head', 'origin', 'main')

    def task(self, files, branch='agent/task', base='main'):
        git(self.primary, 'worktree', 'add', '-q', '-b', branch, self.wt, base)
        for name, text in files.items():
            write(os.path.join(self.wt, name), text)
            git(self.wt, 'add', '--', name)
        git(self.wt, 'commit', '-q', '-m', 'task')
        return git(self.wt, 'rev-parse', 'HEAD')

    def promote(self, *args, cwd=None):
        return subprocess.run([sys.executable, TOOL, *args], cwd=cwd or self.wt,
                              capture_output=True, text=True)

    def assertRefused(self, r, text):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(text, r.stderr)

    def test_lands_by_fast_forward(self):
        sha = self.task({'app.txt': 'two\n'})
        r = self.promote(sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(self.primary, 'rev-parse', 'main'), sha)
        with open(os.path.join(self.primary, 'app.txt')) as f:
            self.assertEqual(f.read(), 'two\n')
        self.assertIn('landing mode local main', r.stdout)

    def test_refuses_in_pull_request_mode(self):
        write(os.path.join(self.primary, 'HANDOFF.md'), '# Handoff\n')
        git(self.primary, 'commit', '-q', '-am', 'no setting')
        git(self.primary, 'push', '-q', 'origin', 'main')
        git(self.primary, 'fetch', '-q', 'origin')
        before = git(self.primary, 'rev-parse', 'main')
        sha = self.task({'app.txt': 'two\n'})
        self.assertRefused(self.promote(sha), 'lands through pull requests')
        self.assertEqual(git(self.primary, 'rev-parse', 'main'), before)

    def test_refuses_when_main_moved(self):
        sha = self.task({'new.txt': 'n\n'})
        write(os.path.join(self.primary, 'other.txt'), 'o\n')
        git(self.primary, 'add', '--', 'other.txt')
        git(self.primary, 'commit', '-q', '-m', 'moved')
        self.assertRefused(self.promote(sha), 'is not an ancestor')

    def test_refuses_when_the_remote_has_a_commit_the_candidate_lacks(self):
        other = os.path.join(self.tmp.name, 'other')
        subprocess.run(['git', 'clone', '-q', self.bare, other], check=True)
        self.ident(other)
        write(os.path.join(other, 'remote.txt'), 'r\n')
        git(other, 'add', '--', 'remote.txt')
        git(other, 'commit', '-q', '-m', 'remote')
        git(other, 'push', '-q', 'origin', 'main')
        sha = self.task({'new.txt': 'n\n'})
        self.assertRefused(self.promote(sha), 'is not in the candidate')

    def test_refuses_when_the_primary_is_off_the_landing_branch(self):
        git(self.primary, 'switch', '-q', '-c', 'elsewhere')
        sha = self.task({'new.txt': 'n\n'}, base='main')
        self.assertRefused(self.promote(sha), 'is not on main')

    def test_refuses_an_operation_in_progress(self):
        sha = self.task({'new.txt': 'n\n'})
        write(os.path.join(self.primary, '.git', 'MERGE_HEAD'), sha + '\n')
        self.assertRefused(self.promote(sha), 'in progress')

    def test_refuses_staged_changes(self):
        sha = self.task({'new.txt': 'n\n'})
        write(os.path.join(self.primary, 'staged.txt'), 's\n')
        git(self.primary, 'add', '--', 'staged.txt')
        self.assertRefused(self.promote(sha), 'staged changes')

    def test_refuses_a_local_file_the_change_overlaps(self):
        sha = self.task({'notes/plan.txt': 'p\n'})
        write(os.path.join(self.primary, 'notes', 'plan.txt'), 'someone else\n')
        self.assertRefused(self.promote(sha), 'overlap the change')
        with open(os.path.join(self.primary, 'notes', 'plan.txt')) as f:
            self.assertEqual(f.read(), 'someone else\n')

    def test_keeps_an_unrelated_local_file(self):
        sha = self.task({'app.txt': 'two\n'})
        write(os.path.join(self.primary, 'scratch.txt'), 'mine\n')
        r = self.promote(sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.primary, 'scratch.txt')) as f:
            self.assertEqual(f.read(), 'mine\n')

    def test_landing_branch_setting(self):
        git(self.primary, 'remote', 'remove', 'origin')
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main',
                        os.path.join(self.tmp.name, 'o2.git')], check=True)
        self.bare = os.path.join(self.tmp.name, 'o2.git')
        self.handoff('| landing branch | `editor` |\n')
        git(self.primary, 'branch', 'editor')
        git(self.primary, 'push', '-q', 'origin', 'editor')
        sha = self.task({'app.txt': 'two\n'}, base='editor')
        self.assertRefused(self.promote(sha), 'is not on editor')
        git(self.primary, 'switch', '-q', 'editor')
        r = self.promote(sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(self.primary, 'rev-parse', 'editor'), sha)
        self.assertNotEqual(git(self.primary, 'rev-parse', 'main'), sha)

    def test_repository_without_a_remote(self):
        git(self.primary, 'remote', 'remove', 'origin')
        write(os.path.join(self.primary, 'HANDOFF.md'), '# Handoff\n')
        git(self.primary, 'commit', '-q', '-am', 'no setting')
        sha = self.task({'app.txt': 'two\n'})
        r = self.promote(sha)
        self.assertIn("no remote 'origin': nothing to fetch", r.stdout)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(git(self.primary, 'rev-parse', 'main'), sha)


if __name__ == '__main__':
    unittest.main(verbosity=1)
