#!/usr/bin/env python3
"""Checks the core plugin's worktree scripts and templates/pre-push in throwaway repositories:
python3 tests/worktree_tools.py.

A bare repository stands in for GitHub and a small script stands in for `gh`: it answers
`gh pr list --head <branch> --state merged` from FAKE_GH_PRS. Merges are made the three ways
GitHub makes them (merge commit, squash, and none), then remove_merged_worktree.py must remove
exactly the merged worktrees and keep everything else, and the pre-push hook must refuse force
pushes and deletions of unmerged branches. Offline; no network, no real gh.
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
SCRIPTS = os.path.join(ROOT, 'plugins', 'core', 'scripts')
NEW = os.path.join(SCRIPTS, 'new_worktree.py')
REMOVE = os.path.join(SCRIPTS, 'remove_merged_worktree.py')
PRE_PUSH = os.path.join(ROOT, 'templates', 'pre-push')
WINDOWS = os.name == 'nt'

FAKE_GH = r'''import json, os, sys
args = sys.argv[1:]
pulls = json.loads(os.environ.get('FAKE_GH_PRS', '[]'))
if args[:2] == ['pr', 'list']:
    head = args[args.index('--head') + 1] if '--head' in args else None
    found = [p for p in pulls if head is None or p.get('head') == head]
    if '--jq' in args:
        print('\n'.join(p['headRefOid'] for p in found))
    else:
        print(json.dumps([{'number': p['number'], 'headRefOid': p['headRefOid']} for p in found]))
    sys.exit(0)
sys.exit(1)
'''


class Repos(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix='worktree-tools-'))
        config = os.path.join(self.dir, 'gitconfig')
        with open(config, 'w') as f:
            f.write('[advice]\n\tdetachedHead = false\n')
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=config,
                        GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                        GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
                        FAKE_GH_PRS='[]')
        fake = os.path.join(self.dir, 'fake_gh.py')
        with open(fake, 'w') as f:
            f.write(FAKE_GH)
        self.env['AGENTIC_GITHUB_FLOW_GH'] = json.dumps([sys.executable, fake])
        bindir = os.path.join(self.dir, 'bin')  # a `gh` on PATH for the pre-push hook
        os.makedirs(bindir)
        shim = os.path.join(bindir, 'gh')
        with open(shim, 'w') as f:
            f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable.replace('\\', '/'),
                                                       fake.replace('\\', '/')))
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IEXEC)
        self.env['PATH'] = bindir + os.pathsep + self.env.get('PATH', '')
        self.origin = os.path.join(self.dir, 'origin.git')
        self.repo = os.path.join(self.dir, 'repo')
        self.git(self.dir, 'init', '-q', '--bare', '-b', 'main', self.origin)
        self.git(self.dir, 'clone', '-q', self.origin, self.repo)
        self.write(self.repo, 'README.md', 'start\n')
        self.write(self.repo, '.gitignore', 'secret.txt\n')
        self.git(self.repo, 'add', '--', 'README.md', '.gitignore')
        self.git(self.repo, 'commit', '-q', '-m', 'start')
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'remote', 'set-head', 'origin', 'main')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    # helpers
    def git(self, cwd, *args, check=True):
        r = subprocess.run(['git', *args], cwd=cwd, env=self.env, capture_output=True, text=True)
        if check and r.returncode:
            raise AssertionError('git %s: %s' % (' '.join(args), r.stderr))
        return r

    def write(self, folder, rel, text):
        path = os.path.join(folder, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', newline='') as f:
            f.write(text)

    def run_tool(self, tool, *args, cwd=None):
        r = subprocess.run([sys.executable, tool, *args], cwd=cwd or self.repo, env=self.env,
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def new_task(self, task, commits=1):
        code, out = self.run_tool(NEW, task)
        self.assertEqual(code, 0, out)
        wt = os.path.join(self.dir, 'repo-worktrees', task)
        for i in range(commits):
            self.write(wt, '%s-%d.txt' % (task, i), 'work %d\n' % i)
            self.git(wt, 'add', '--', '%s-%d.txt' % (task, i))
            self.git(wt, 'commit', '-q', '-m', '%s %d' % (task, i))
        return wt

    def tip(self, ref):
        return self.git(self.repo, 'rev-parse', ref).stdout.strip()

    def github_merge(self, branch, squash=False):
        """Merge branch into origin/main from a second clone, as GitHub's merge button does."""
        self.git(self.repo, 'push', '-q', 'origin', branch)
        other = os.path.join(self.dir, 'merger')
        if not os.path.isdir(other):
            self.git(self.dir, 'clone', '-q', self.origin, other)
        self.git(other, 'fetch', '-q', 'origin')
        self.git(other, 'checkout', '-q', 'main')
        self.git(other, 'merge', '-q', '--ff-only', 'origin/main')
        if squash:
            self.git(other, 'merge', '-q', '--squash', 'origin/' + branch)
            self.git(other, 'commit', '-q', '-m', 'squash ' + branch)
        else:
            self.git(other, 'merge', '-q', '--no-ff', '-m', 'merge ' + branch, 'origin/' + branch)
        self.git(other, 'push', '-q', 'origin', 'main')

    def branches(self):
        return self.git(self.repo, 'branch', '--format=%(refname:short)').stdout.split()


class NewWorktreeTests(Repos):
    def test_creates_branch_and_folder_from_the_fetched_default_branch(self):
        code, out = self.run_tool(NEW, 'task-1')
        self.assertEqual(code, 0, out)
        wt = os.path.join(self.dir, 'repo-worktrees', 'task-1')
        self.assertTrue(os.path.isfile(os.path.join(wt, 'README.md')))
        self.assertEqual(self.git(wt, 'branch', '--show-current').stdout.strip(), 'agent/task-1')
        self.assertIn('from refs/remotes/origin/main', out)

    def test_refusals(self):
        self.assertEqual(self.run_tool(NEW, 'task-1')[0], 0)
        code, out = self.run_tool(NEW, 'task-1')
        self.assertEqual(code, 1)
        self.assertIn('exists already', out)
        self.assertEqual(self.run_tool(NEW, '../escape')[0], 1)
        code, out = self.run_tool(NEW, 'task-2', cwd=os.path.join(self.dir, 'repo-worktrees',
                                                                  'task-1'))
        self.assertEqual(code, 1)
        self.assertIn('primary checkout', out)


class RemoveMergedTests(Repos):
    def test_merge_commit_removes_worktree_and_branch(self):
        wt = self.new_task('merged')
        self.github_merge('agent/merged')
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 0, out)
        self.assertIn('REMOVED', out)
        self.assertFalse(os.path.exists(wt))
        self.assertNotIn('agent/merged', self.branches())

    def test_squash_merge_is_proven_by_the_merged_pull_request(self):
        wt = self.new_task('squashed', commits=2)
        tip = self.tip('agent/squashed')
        self.github_merge('agent/squashed', squash=True)
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 1, out)
        self.assertIn('not merged', out)
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 7, 'head': 'agent/squashed',
                                               'headRefOid': tip}])
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 0, out)
        self.assertIn('merged pull request #7', out)
        self.assertNotIn('agent/squashed', self.branches())

    def test_a_commit_after_the_merged_head_keeps_the_worktree(self):
        wt = self.new_task('late')
        tip = self.tip('agent/late')
        self.github_merge('agent/late', squash=True)
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 8, 'head': 'agent/late',
                                               'headRefOid': tip}])
        self.write(wt, 'after.txt', 'more\n')
        self.git(wt, 'add', '--', 'after.txt')
        self.git(wt, 'commit', '-q', '-m', 'after the merge')
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 1, out)
        self.assertTrue(os.path.isdir(wt))
        self.assertIn('agent/late', self.branches())

    def test_dirty_and_unproven_ignored_files_keep_the_worktree(self):
        wt = self.new_task('dirty')
        self.github_merge('agent/dirty')
        self.write(wt, 'README.md', 'edited\n')
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 1)
        self.assertIn('not clean', out)
        with open(os.path.join(wt, 'README.md'), 'w', newline='') as f:
            f.write('start\n')
        self.write(wt, 'secret.txt', 'data no tool can regenerate\n')
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 1)
        self.assertIn('secret.txt (not proven regenerable)', out)
        self.assertTrue(os.path.isfile(os.path.join(wt, 'secret.txt')))

    def test_sweep_keeps_fresh_and_unmerged_worktrees(self):
        merged = self.new_task('sweep-merged')
        self.github_merge('agent/sweep-merged')
        fresh = self.new_task('sweep-fresh', commits=0)
        open_work = self.new_task('sweep-open')
        code, out = self.run_tool(REMOVE, '--sweep', '--dry-run')
        self.assertEqual(code, 0, out)
        self.assertIn('WOULD REMOVE ' + merged, out)
        self.assertIn('KEPT %s: no commits of its own' % fresh, out)
        self.assertIn('KEPT ' + open_work, out)
        code, out = self.run_tool(REMOVE, '--sweep')
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(merged))
        self.assertTrue(os.path.isdir(fresh) and os.path.isdir(open_work))

    def test_approved_abandon_keeps_the_branch(self):
        wt = self.new_task('abandon')
        code, out = self.run_tool(REMOVE, '--approved', 'drop it, we chose another route', wt)
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(wt))
        self.assertIn('agent/abandon', self.branches())
        self.assertEqual(self.run_tool(REMOVE, '--approved', '  ', wt)[0], 2)

    def test_primary_checkout_is_never_removed(self):
        code, out = self.run_tool(REMOVE, self.repo)
        self.assertEqual(code, 1)
        self.assertIn('primary checkout is never removed', out)


class PrePushTests(Repos):
    def setUp(self):
        super().setUp()
        hooks = self.git(self.repo, 'rev-parse', '--git-path', 'hooks').stdout.strip()
        hooks = os.path.join(self.repo, hooks) if not os.path.isabs(hooks) else hooks
        os.makedirs(hooks, exist_ok=True)
        shutil.copyfile(PRE_PUSH, os.path.join(hooks, 'pre-push'))
        os.chmod(os.path.join(hooks, 'pre-push'), 0o755)

    def push(self, *args):
        return self.git(self.repo, 'push', '-q', 'origin', *args, check=False)

    def test_force_push_and_tag_move_are_refused(self):
        self.write(self.repo, 'a.txt', 'a\n')
        self.git(self.repo, 'add', '--', 'a.txt')
        self.git(self.repo, 'commit', '-q', '-m', 'a')
        self.assertEqual(self.push('main').returncode, 0)
        self.git(self.repo, 'tag', 'v1')
        self.assertEqual(self.push('v1').returncode, 0)
        r = self.push('+HEAD~1:main')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('NON-FAST-FORWARD', r.stderr)
        self.git(self.repo, 'tag', '-f', 'v1', 'HEAD~1')
        r = self.push('+v1')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('MOVE tag', r.stderr)
        r = self.push('--delete', 'main')
        self.assertNotEqual(r.returncode, 0)

    def test_branch_deletion_only_when_merged(self):
        self.new_task('pp-merged')
        self.github_merge('agent/pp-merged')
        self.git(self.repo, 'fetch', '-q', 'origin')
        self.assertEqual(self.push('--delete', 'agent/pp-merged').returncode, 0)
        self.new_task('pp-open')
        self.assertEqual(self.push('agent/pp-open').returncode, 0)
        r = self.push('--delete', 'agent/pp-open')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('not the head', r.stderr)

    @unittest.skipIf(WINDOWS, 'the stand-in gh is a shell script; Git for Windows may not run it')
    def test_squash_merged_branch_deletion_needs_the_merged_pull_request(self):
        self.new_task('pp-squash')
        tip = self.tip('agent/pp-squash')
        self.github_merge('agent/pp-squash', squash=True)
        self.git(self.repo, 'fetch', '-q', 'origin')
        self.assertNotEqual(self.push('--delete', 'agent/pp-squash').returncode, 0)
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 9, 'head': 'agent/pp-squash',
                                               'headRefOid': tip}])
        self.assertEqual(self.push('--delete', 'agent/pp-squash').returncode, 0)


if __name__ == '__main__':
    unittest.main()
