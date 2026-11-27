#!/usr/bin/env python3
"""Checks plugins/core/scripts/verify.py on temporary repositories: python3 tests/verify.py.

The command comes from the `## Verification` section of HANDOFF.md on the default branch, not
from the working tree or the branch (a change cannot rewrite what judges it): origin/HEAD when
there is a remote, else local main. Every run appends one line to the record in the git
directory, which a second worktree reaches too; a failing command is recorded as failed, with its
last line of output, and exits non-zero. `fast` gets the changed paths in a file named by
VERIFY_CHANGED (committed since the default branch, staged, unstaged and untracked) and the base
commit in VERIFY_BASE. Several commands in one cell run in order and stop at the first failure.
Without the section or the row it refuses and records nothing. No network.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'verify.py')

# Writes its first argument to the file `ran` in the current folder, appends its second to the
# file `env` when given (an environment variable's name), and exits with the third (default 0).
MARKER = r'''import os, sys
open('ran', 'a').write(sys.argv[1] + '\n')
if len(sys.argv) > 2 and sys.argv[2] != '-':
    open('env', 'w').write(os.environ.get(sys.argv[2], '<unset>'))
print('marker ' + sys.argv[1])
sys.exit(int(sys.argv[3]) if len(sys.argv) > 3 else 0)
'''

PY = '"%s"' % sys.executable


def handoff(fast=None, full=None, extra=''):
    rows = ''.join('| `%s` | %s |\n' % (k, v) for k, v in (('fast', fast), ('full', full)) if v)
    return ('# Tool: current state\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n'
            '| landing | `pull request` |\n\n## Verification\n\n| Setting | Value |\n|---|---|\n'
            + rows + '| `verification gate` | `off` |\n' + extra + '\n## Standing permissions\n'
            'None.\n')


def marker(word, env='-', code=0):
    return '`%s marker.py %s %s %d`' % (PY, word, env, code)


class Verify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.com',
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        self.env.pop('VERIFY_CHANGED', None)
        self.repo = os.path.join(self.tmp, 'repo')
        os.mkdir(self.repo)
        self.git(self.repo, 'init', '-q', '-b', 'main')
        self.write(self.repo, 'marker.py', MARKER)
        self.write(self.repo, 'HANDOFF.md', handoff(fast=marker('main-fast', 'VERIFY_CHANGED'),
                                                    full=marker('main-full')))
        self.write(self.repo, '.gitignore', 'ran\nenv\n')
        self.commit(self.repo, 'start')
        self.git(self.repo, 'checkout', '-q', '-b', 'feature')

    def git(self, cwd, *args):
        r = subprocess.run(['git', '-C', cwd, *args], capture_output=True, text=True,
                           env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def write(self, cwd, name, text):
        path = os.path.join(cwd, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)

    def commit(self, cwd, message):
        self.git(cwd, 'add', '-A')
        self.git(cwd, 'commit', '-q', '-m', message)

    def verify(self, cwd, *args):
        return subprocess.run([sys.executable, TOOL, *args], cwd=cwd, capture_output=True,
                              text=True, env=self.env)

    def ran(self, cwd):
        path = os.path.join(cwd, 'ran')
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8') as f:
            return f.read().split()

    def record(self, cwd):
        common = self.git(cwd, 'rev-parse', '--path-format=absolute', '--git-common-dir')
        path = os.path.join(common, 'verify-record.tsv')
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8') as f:
            return [line.rstrip('\n').split('\t') for line in f if not line.startswith('#')]

    def test_runs_the_default_branch_command_not_the_working_tree(self):
        self.write(self.repo, 'HANDOFF.md', handoff(fast=marker('branch-fast')))
        self.commit(self.repo, 'the branch rewrites its own check')
        self.write(self.repo, 'HANDOFF.md', handoff(fast=marker('tree-fast')))
        r = self.verify(self.repo, 'fast')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ran(self.repo), ['main-fast'])

    def test_default_branch_is_origin_head_before_local_main(self):
        origin = os.path.join(self.tmp, 'origin.git')
        self.git(self.tmp, 'clone', '-q', '--bare', self.repo, origin)
        clone = os.path.join(self.tmp, 'clone')
        self.git(self.tmp, 'clone', '-q', '-b', 'main', origin, clone)
        self.git(clone, 'checkout', '-q', '-b', 'work')
        # local main moves on; origin/main, as last fetched, still holds the old command
        self.git(clone, 'checkout', '-q', 'main')
        self.write(clone, 'HANDOFF.md', handoff(fast=marker('local-main-fast')))
        self.commit(clone, 'unpushed change on local main')
        self.git(clone, 'checkout', '-q', 'work')
        r = self.verify(clone, 'fast')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ran(clone), ['main-fast'])

    def test_record_line_per_run_and_shared_by_worktrees(self):
        self.assertEqual(self.verify(self.repo, 'fast').returncode, 0)
        self.assertEqual(self.verify(self.repo, 'full').returncode, 0)
        second = os.path.join(self.tmp, 'second')
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'other', second, 'main')
        r = self.verify(second, 'full')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = self.record(self.repo)
        self.assertEqual(lines, self.record(second))
        self.assertEqual(len(lines), 3, lines)
        self.assertEqual([(l[1], l[2], l[4]) for l in lines],
                         [('feature', 'fast', 'passed'), ('feature', 'full', 'passed'),
                          ('other', 'full', 'passed')])
        date, _, _, seconds, _, command = lines[0]
        self.assertRegex(date, r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertGreaterEqual(float(seconds), 0)
        self.assertIn('marker.py main-fast', command)
        self.assertNotIn('verify-record', self.git(self.repo, 'status', '--porcelain'))

    def test_failing_command_is_recorded_as_failed(self):
        self.git(self.repo, 'checkout', '-q', 'main')
        self.write(self.repo, 'HANDOFF.md',
                   handoff(fast=marker('one') + ', ' + marker('two', '-', 3) + ', '
                           + marker('three')))
        self.commit(self.repo, 'a failing check')
        self.git(self.repo, 'checkout', '-q', 'feature')
        r = self.verify(self.repo, 'fast')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('marker two', r.stdout)
        self.assertEqual(self.ran(self.repo), ['one', 'two'])
        [line] = self.record(self.repo)
        self.assertEqual(line[2], 'fast')
        self.assertTrue(line[4].startswith('failed: exit 3'), line)
        self.assertIn('marker two', line[4])

    def test_fast_gets_the_changed_paths(self):
        copy = r'''import os, shutil
shutil.copy(os.environ['VERIFY_CHANGED'], 'changed-copy')
open('base-copy', 'w').write(os.environ['VERIFY_BASE'] + '\n' + os.environ['VERIFY_CHANGED'])
'''
        self.git(self.repo, 'checkout', '-q', 'main')
        self.write(self.repo, 'copy.py', copy)
        self.write(self.repo, '.gitignore', 'ran\nenv\nchanged-copy\nbase-copy\n')
        self.write(self.repo, 'HANDOFF.md', handoff(fast='`%s copy.py`' % PY,
                                                    full='`%s copy.py`' % PY))
        self.commit(self.repo, 'copy the list')
        base = self.git(self.repo, 'rev-parse', 'HEAD')
        self.git(self.repo, 'checkout', '-q', '-b', 'second')
        self.write(self.repo, 'committed.txt', 'x')
        self.commit(self.repo, 'one file')
        self.write(self.repo, 'sub/untracked.txt', 'x')
        self.write(self.repo, 'marker.py', MARKER + '\n')
        self.write(self.repo, 'staged.txt', 'x')
        self.git(self.repo, 'add', 'staged.txt')
        r = self.verify(self.repo, 'fast')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('4 changed paths', r.stdout)
        with open(os.path.join(self.repo, 'changed-copy'), encoding='utf-8') as f:
            self.assertEqual(f.read().splitlines(),
                             ['committed.txt', 'marker.py', 'staged.txt', 'sub/untracked.txt'])
        with open(os.path.join(self.repo, 'base-copy'), encoding='utf-8') as f:
            got_base, listed = f.read().split('\n')
        self.assertEqual(got_base, base)
        self.assertFalse(os.path.exists(listed), 'the list is removed after the run')
        # `full` runs everything and gets no list
        r = self.verify(self.repo, 'full')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('VERIFY_CHANGED', r.stdout)

    def test_escaped_pipe_in_a_cell(self):
        self.git(self.repo, 'checkout', '-q', 'main')
        self.write(self.repo, 'HANDOFF.md',
                   handoff(full='`%s -c "print(1)" \\| %s marker.py piped`' % (PY, PY)))
        self.commit(self.repo, 'a pipe')
        r = self.verify(self.repo, 'full')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ran(self.repo), ['piped'])

    def test_no_section_or_row_refuses_and_records_nothing(self):
        self.git(self.repo, 'checkout', '-q', 'main')
        self.write(self.repo, 'HANDOFF.md', handoff(full=marker('only-full')))
        self.commit(self.repo, 'no fast row')
        r = self.verify(self.repo, 'fast')
        self.assertEqual(r.returncode, 2)
        self.assertIn('`fast`', r.stderr)
        self.write(self.repo, 'HANDOFF.md', '# Tool\n\n## Build, test, run\n\nmake test\n')
        self.commit(self.repo, 'no section')
        r = self.verify(self.repo, 'full')
        self.assertEqual(r.returncode, 2)
        self.assertIn('## Verification', r.stderr)
        self.assertEqual(self.ran(self.repo), [])
        self.assertEqual(self.record(self.repo), [])

    def test_usage(self):
        self.assertEqual(self.verify(self.repo).returncode, 2)
        self.assertEqual(self.verify(self.repo, 'drive').returncode, 2)
        self.assertEqual(self.verify(self.tmp, 'fast').returncode, 2)  # outside git


if __name__ == '__main__':
    unittest.main()
