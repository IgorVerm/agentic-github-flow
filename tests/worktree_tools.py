#!/usr/bin/env python3
"""Checks the core plugin's worktree scripts and templates/pre-push in throwaway repositories:
python3 tests/worktree_tools.py.

A bare repository stands in for GitHub and a small script stands in for `gh`: it answers
`gh pr list --head <branch> [--base <b>] --state merged` from FAKE_GH_PRS and `gh issue view <n>`
from FAKE_GH_ISSUES. Merges are made the ways GitHub makes them (merge commit, squash, and none),
then remove_merged_worktree.py must remove exactly the merged worktrees and keep everything else,
its --sweep must delete exactly the merged local branches and the scratch branches of closed
issues that nothing else holds, delete_merged_branch.py must delete
a remote branch only while its tip is the merged commit, and the pre-push hook must refuse force
pushes and deletions of unmerged branches. One case runs the removal behind a `git` that answers
like git before 2.31 and 2.45 (it echoes `--show-ref-format` and `--path-format=absolute`).
Offline; no network, no real gh.
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
DELETE = os.path.join(SCRIPTS, 'delete_merged_branch.py')
PRE_PUSH = os.path.join(ROOT, 'templates', 'pre-push')
WINDOWS = os.name == 'nt'

FAKE_GH = r'''import json, os, sys
args = sys.argv[1:]
if os.environ.get('FAKE_GH_LOG'):
    with open(os.environ['FAKE_GH_LOG'], 'a') as log:
        log.write(' '.join(args) + '\n')
pulls = json.loads(os.environ.get('FAKE_GH_PRS', '[]'))
if args[:2] == ['pr', 'list']:
    head = args[args.index('--head') + 1] if '--head' in args else None
    base = args[args.index('--base') + 1] if '--base' in args else None
    found = [p for p in pulls if (head is None or p.get('head') == head)
             and (base is None or p.get('base', 'main') == base)]
    if '--jq' in args:
        print('\n'.join(p['headRefOid'] for p in found))
    else:
        print(json.dumps([{'number': p['number'], 'headRefOid': p['headRefOid'],
                           'baseRefName': p.get('base', 'main')} for p in found]))
    sys.exit(0)
if args[:2] == ['issue', 'view']:
    answer = json.loads(os.environ.get('FAKE_GH_ISSUES', '{}')).get(args[2])
    if answer is None:
        sys.stderr.write('no such issue\n')
        sys.exit(1)
    print(answer)
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

    def test_stacked_pull_request_is_no_proof(self):
        wt = self.new_task('stacked')
        tip = self.tip('agent/stacked')
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 3, 'head': 'agent/stacked',
                                               'headRefOid': tip, 'base': 'feature'}])
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 1, out)
        self.assertTrue(os.path.isdir(wt))

    def test_approved_names_exactly_one_worktree(self):
        one, two = self.new_task('ap-one'), self.new_task('ap-two')
        code, out = self.run_tool(REMOVE, '--approved', 'drop both', one, two)
        self.assertEqual(code, 2, out)
        self.assertTrue(os.path.isdir(one) and os.path.isdir(two))

    @unittest.skipIf(WINDOWS, 'the old-git stand-in is a shell script')
    def test_cleanup_works_with_git_that_echoes_newer_options(self):
        real = shutil.which('git', path=self.env['PATH'])
        old = os.path.join(self.dir, 'oldgit')
        os.makedirs(old)
        with open(os.path.join(old, 'git'), 'w') as f:
            f.write('#!/bin/sh\n'
                    'for a in "$@"; do case "$a" in\n'
                    '  --show-ref-format) echo --show-ref-format; exit 0 ;;\n'
                    '  --path-format=*) echo "$a"; exit 0 ;;\n'
                    'esac; done\n'
                    'exec "%s" "$@"\n' % real)
        os.chmod(os.path.join(old, 'git'), 0o755)
        wt = self.new_task('oldgit')
        self.github_merge('agent/oldgit')
        self.env['PATH'] = old + os.pathsep + self.env['PATH']
        self.assertEqual(self.git(self.repo, 'rev-parse', '--show-ref-format').stdout.strip(),
                         '--show-ref-format')
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(wt))
        self.git(self.repo, 'branch', '--no-track', 'agent/oldgit-left', 'origin/main')
        code, out = self.run_tool(REMOVE, '--sweep')
        self.assertEqual(code, 0, out)
        self.assertIn('DELETED agent/oldgit-left at ', out)
        code, out = self.run_tool(NEW, 'after-oldgit')
        self.assertEqual(code, 0, out)

    def test_primary_checkout_is_never_removed(self):
        code, out = self.run_tool(REMOVE, self.repo)
        self.assertEqual(code, 1)
        self.assertIn('primary checkout is never removed', out)


class SweepBranchesTests(Repos):
    """--sweep after the worktrees: scratch branches of closed issues, then merged branches."""

    def setUp(self):
        super().setUp()
        self.gh_log = os.path.join(self.dir, 'gh.log')
        self.env['FAKE_GH_LOG'] = self.gh_log
        self.fake_gh = self.env['AGENTIC_GITHUB_FLOW_GH']

    def sweep(self, *args, code=0):
        got, out = self.run_tool(REMOVE, '--sweep', *args)
        self.assertEqual(got, code, out)
        return out

    def issues(self, **answers):
        """issue<n>='<STATE>' answers issue n with that state and its URL; a value starting
        with `{` or `not` is gh's output as it stands."""
        known = json.loads(self.env.get('FAKE_GH_ISSUES', '{}'))
        for name, answer in answers.items():
            number = name[len('issue'):]
            known[number] = (answer if answer.startswith(('{', 'not')) else json.dumps(
                {'state': answer, 'url': 'https://example.invalid/o/r/issues/' + number}))
        self.env['FAKE_GH_ISSUES'] = json.dumps(known)

    def gh_calls(self, kind='issue view'):
        if not os.path.exists(self.gh_log):
            return []
        with open(self.gh_log) as f:
            return [line for line in f.read().splitlines() if line.startswith(kind)]

    def scratch(self, name, base='main'):
        """A local branch whose tip nothing else holds, a commit of its own (the name is its
        message, so two made in the same second differ); returns the tip."""
        tree = self.tip(base + '^{tree}')
        tip = self.git(self.repo, 'commit-tree', tree, '-p', base, '-m',
                       'probe ' + name).stdout.strip()
        self.git(self.repo, 'branch', name, tip)
        return tip

    def has_branch(self, name):
        return not self.git(self.repo, 'rev-parse', '-q', '--verify', 'refs/heads/' + name,
                            check=False).returncode

    def reflog_file(self, branch):
        path = self.git(self.repo, 'rev-parse', '--git-path',
                        'logs/refs/heads/' + branch).stdout.strip()
        return path if os.path.isabs(path) else os.path.join(self.repo, path)

    def commit(self, wt, name):
        self.write(wt, name, name + '\n')
        self.git(wt, 'add', '--', name)
        self.git(wt, 'commit', '-q', '-m', name)
        return self.git(wt, 'rev-parse', 'HEAD').stdout.strip()

    def land(self, sha):
        """Fast-forward origin's main to sha, as a rebase merge on GitHub does; local main stays."""
        self.git(self.repo, 'push', '-q', 'origin', sha + ':refs/heads/main')
        self.git(self.repo, 'fetch', '-q', 'origin')

    def merged_branch(self, name, keep_tree=False, push=False):
        """A branch with a commit of its own in origin's main; its worktree goes unless kept."""
        self.git(self.repo, 'fetch', '-q', 'origin')
        wt = os.path.join(self.dir, 'tree-' + name.replace('/', '-'))
        self.git(self.repo, 'worktree', 'add', '-q', '--no-track', '-b', name, wt, 'origin/main')
        tip = self.commit(wt, name.replace('/', '-') + '.txt')
        self.land(tip)
        if push:
            self.git(self.repo, 'push', '-q', 'origin', name)
        if not keep_tree:
            self.git(self.repo, 'worktree', 'remove', wt)
        return tip

    # -- scratch branches --

    def test_deletes_the_scratch_branch_of_a_closed_issue(self):
        self.issues(issue101='CLOSED')
        tip = self.scratch('scratch/101-probe')
        for other in ('agent/101-probe', 'scratchpad/101-probe'):
            self.scratch(other)  # the same issue, not the form: never touched
        out = self.sweep()
        self.assertIn('DELETED scratch/101-probe at %s (issue #101 closed); '
                      'back: git branch scratch/101-probe %s' % (tip, tip), out)
        self.assertIn('scratch branches deleted: 1; kept: 0', out)
        self.assertFalse(self.has_branch('scratch/101-probe'))
        self.assertTrue(self.has_branch('agent/101-probe'))
        self.assertTrue(self.has_branch('scratchpad/101-probe'))
        self.assertEqual(self.gh_calls(), ['issue view 101 -R %s --json state,url' % self.origin])
        self.git(self.repo, 'branch', 'scratch/101-probe', tip)  # the printed way back
        self.assertEqual(self.tip('scratch/101-probe'), tip)

    def test_keeps_a_scratch_branch_it_cannot_prove_finished(self):
        def answer(state, url):
            return json.dumps({'state': state, 'url': url})
        base = 'https://example.invalid/o/r/'
        self.issues(issue102='OPEN', issue104='not json', issue105='{"state": "CLOSED"}',
                    issue106=answer('CLOSED', base + 'pull/106'),
                    issue117=answer('CLOSED', 'https://example.invalid/o/issues/pull/117'),
                    issue118=answer('CLOSED', base + 'issues/99'))
        expected = {
            'scratch/102-open': 'issue #102 is open',
            'scratch/probe': 'no issue number',
            'scratch/103': 'no issue number',
            'scratch/#107-hash': 'no issue number',
            'scratch/0107-zero': 'no issue number',
            'scratch/group/107-nested': 'no issue number',
            'scratch/999-unknown': 'issue #999 cannot be read: no such issue',
            'scratch/104-garbled': 'issue #104 cannot be read: gh gave no state',
            'scratch/105-no-url': 'issue #105 cannot be read: gh gave no state',
            'scratch/106-pull': '#106 is not an issue',
            'scratch/117-pull-of-a-repository-called-issues': '#117 is not an issue',
            'scratch/118-moved-to-another-repository': '#118 is not an issue',
        }
        tips = {name: self.scratch(name) for name in expected}
        out = self.sweep()
        for name, message in expected.items():
            with self.subTest(name):
                self.assertIn('KEPT %s at %s: %s' % (name, tips[name], message), out)
                self.assertTrue(self.has_branch(name))
        self.assertIn('scratch branches deleted: 0; kept: %d' % len(expected), out)
        self.assertEqual(len(self.gh_calls()), 7)  # never asked without a number

    def test_without_gh_or_origin_every_scratch_branch_stays(self):
        tip = self.scratch('scratch/108-probe')
        self.issues(issue108='CLOSED')
        self.env['AGENTIC_GITHUB_FLOW_GH'] = '[]'  # no gh at all
        self.assertIn('KEPT scratch/108-probe at %s: gh is not installed, so no issue can be '
                      'read as closed' % tip, self.sweep())
        self.env['AGENTIC_GITHUB_FLOW_GH'] = self.fake_gh
        self.git(self.repo, 'remote', 'remove', 'origin')  # gh alone could pick another remote
        self.assertIn('KEPT scratch/108-probe at %s: issue #108 cannot be read: no remote origin'
                      % tip, self.sweep())
        self.assertTrue(self.has_branch('scratch/108-probe'))
        self.assertEqual(self.gh_calls(), [])

    def test_keeps_a_checked_out_scratch_branch(self):
        self.issues(issue109='CLOSED', issue110='CLOSED', issue111='CLOSED')
        with self.subTest('in a linked worktree'):
            wt = os.path.join(self.dir, 'probe')
            tip = self.scratch('scratch/109-linked')
            self.git(self.repo, 'worktree', 'add', '-q', wt, 'scratch/109-linked')
            self.assertIn('KEPT scratch/109-linked at %s: checked out in %s' % (tip, wt),
                          self.sweep())
            self.assertTrue(self.has_branch('scratch/109-linked'))
        with self.subTest('in the primary checkout'):
            tip = self.scratch('scratch/110-primary')
            self.git(self.repo, 'switch', '-q', 'scratch/110-primary')
            out = self.sweep()
            self.git(self.repo, 'switch', '-q', 'main')
            self.assertIn('KEPT scratch/110-primary at %s: checked out in %s' % (tip, self.repo),
                          out)
        with self.subTest('in a rebase, where the worktree list shows no branch: git refuses'):
            wt = os.path.join(self.dir, 'rebasing')
            self.git(self.repo, 'worktree', 'add', '-q', '-b', 'scratch/111-rebase', wt, 'main')
            self.write(wt, 'clash.txt', 'probe\n')
            self.git(wt, 'add', '--', 'clash.txt')
            self.git(wt, 'commit', '-q', '-m', 'probe')
            self.write(self.repo, 'clash.txt', 'main\n')
            self.git(self.repo, 'add', '--', 'clash.txt')
            self.git(self.repo, 'commit', '-q', '-m', 'main')
            self.assertNotEqual(self.git(wt, 'rebase', 'main', check=False).returncode, 0)
            self.assertNotIn('scratch/111-rebase',
                             self.git(self.repo, 'worktree', 'list', '--porcelain').stdout)
            out = self.sweep(code=1)
            self.assertIn('KEPT scratch/111-rebase', out)
            self.assertIn('git branch -D refused', out)
            self.assertTrue(self.has_branch('scratch/111-rebase'))

    def test_dry_run_deletes_no_scratch_branch(self):
        self.issues(issue112='CLOSED', issue113='OPEN')
        closed, kept = self.scratch('scratch/112-probe'), self.scratch('scratch/113-probe')
        out = self.sweep('--dry-run')
        self.assertIn('WOULD DELETE scratch/112-probe at %s (issue #112 closed)' % closed, out)
        self.assertIn('KEPT scratch/113-probe at %s: issue #113 is open' % kept, out)
        self.assertIn('scratch branches would be deleted: 1; kept: 1', out)
        self.assertEqual(self.tip('scratch/112-probe'), closed)

    def test_a_scratch_branch_outlives_the_worktree_whose_commit_it_holds(self):
        """The no-strays check asks for a branch; the sweep must not take it before the
        worktree has gone."""
        self.issues(issue114='OPEN', issue115='CLOSED')
        trees = {}
        for number in (114, 115):
            wt = trees[number] = self.new_task('%d-task' % number, commits=0)
            probe = self.commit(wt, 'probe%d.txt' % number)
            self.git(self.repo, 'branch', 'scratch/%d-probe' % number, probe)
            self.git(self.repo, 'fetch', '-q', 'origin')
            self.git(wt, 'checkout', '-q', '-B', 'agent/%d-task' % number, 'origin/main')
            self.land(self.commit(wt, 'task%d.txt' % number))
        out = self.sweep()
        for wt in trees.values():
            self.assertIn('REMOVED ' + wt, out)
        self.assertTrue(self.has_branch('scratch/114-probe'))
        self.assertIn('DELETED scratch/115-probe', out)

    def test_only_a_sweep_that_knows_its_default_branch_deletes_a_branch(self):
        self.issues(issue116='CLOSED')
        tip = self.scratch('scratch/116-probe')
        merged = self.merged_branch('agent/116-merged')
        wt = self.new_task('named')
        self.github_merge('agent/named')
        self.assertEqual(self.run_tool(REMOVE, wt)[0], 0)  # a named removal: no sweep
        self.assertTrue(self.has_branch('scratch/116-probe'))
        self.assertTrue(self.has_branch('agent/116-merged'))
        self.git(self.repo, 'remote', 'set-url', 'origin', os.path.join(self.dir, 'missing.git'))
        out = self.sweep(code=1)
        self.assertIn('KEPT scratch/116-probe at %s: git fetch origin failed' % tip, out)
        self.assertIn('merged branches: none deleted: git fetch origin failed', out)
        self.assertTrue(self.has_branch('scratch/116-probe'))
        self.assertEqual(self.tip('agent/116-merged'), merged)

    @unittest.skipIf(WINDOWS, 'the failing git is a shell script')
    def test_a_failed_removal_keeps_every_scratch_and_merged_branch(self):
        """A branch may be what still holds that worktree's commits."""
        self.issues(issue119='CLOSED')
        tip = self.scratch('scratch/119-probe')
        merged = self.merged_branch('agent/119-merged')
        self.new_task('119-task')
        self.github_merge('agent/119-task')
        real = shutil.which('git', path=self.env['PATH'])
        bindir = os.path.join(self.dir, 'failgit')
        os.makedirs(bindir)
        with open(os.path.join(bindir, 'git'), 'w') as f:
            f.write('#!/bin/sh\ncase "$*" in *"worktree remove"*) echo no >&2; exit 1;; esac\n'
                    'exec "%s" "$@"\n' % real)
        os.chmod(os.path.join(bindir, 'git'), 0o755)
        self.env['PATH'] = bindir + os.pathsep + self.env['PATH']
        out = self.sweep(code=1)
        self.assertIn('git worktree remove refused', out)
        self.assertIn('KEPT scratch/119-probe at %s: a removal failed in this sweep' % tip, out)
        self.assertIn('merged branches: none deleted: a removal failed in this sweep', out)
        self.assertTrue(self.has_branch('scratch/119-probe'))
        self.assertEqual(self.tip('agent/119-merged'), merged)

    @unittest.skipIf(WINDOWS, 'the moving git is a shell script')
    def test_a_branch_that_moves_after_its_check_stays(self):
        """Both passes read the tip again right before `git branch -D`; a stand-in git moves the
        branch exactly then."""
        self.issues(issue190='CLOSED')
        scratch = self.scratch('scratch/190-moved')
        merged = self.merged_branch('agent/191-moved')
        other = self.scratch('agent/elsewhere')
        real = shutil.which('git', path=self.env['PATH'])
        bindir = os.path.join(self.dir, 'movegit')
        os.makedirs(bindir)
        # the script's call is `git -C <dir> rev-parse -q --verify <ref>`: $6 is the ref
        with open(os.path.join(bindir, 'git'), 'w') as f:
            f.write('#!/bin/sh\ncase "$*" in\n'
                    '  *"--verify refs/heads/scratch/190-moved"|'
                    '*"--verify refs/heads/agent/191-moved")'
                    ' "%s" -C "%s" update-ref "$6" %s ;;\n'
                    'esac\nexec "%s" "$@"\n' % (real, self.repo, other, real))
        os.chmod(os.path.join(bindir, 'git'), 0o755)
        path = self.env['PATH']
        self.env['PATH'] = bindir + os.pathsep + path
        out = self.sweep()
        self.env['PATH'] = path
        self.assertIn('KEPT scratch/190-moved at %s: it moved since the check' % scratch, out)
        self.assertIn('KEPT agent/191-moved at %s: it moved since the check' % merged, out)
        self.assertEqual(self.tip('scratch/190-moved'), other)
        self.assertEqual(self.tip('agent/191-moved'), other)

    def renamed(self, *names):
        """A branch made under the first name and renamed through the others; returns the tip."""
        tip = self.scratch(names[0])
        for old, new in zip(names, names[1:]):
            self.git(self.repo, 'branch', '-m', old, new)
        return tip

    def test_deletes_a_branch_renamed_from_a_name_with_its_number(self):
        self.issues(issue120='CLOSED', issue121='CLOSED', issue122='CLOSED')
        renames = {'agent/120-probe': 'scratch/120-probe', 'agent/fix-121': 'scratch/121-probe',
                   'scratch/122-first': 'scratch/122-second'}
        for old, new in renames.items():
            self.renamed(old, new)
        out = self.sweep()
        for new in renames.values():
            self.assertIn('DELETED %s at ' % new, out)
            self.assertFalse(self.has_branch(new))

    def test_keeps_a_branch_renamed_from_a_name_without_its_number(self):
        """The issue reads closed for every one of them: only the rename keeps them."""
        old_names = {130: 'agent/task', 131: 'claude/wizardly-hopper-97c27c',
                     132: 'agent/7-another-issue', 133: 'agent/1330-longer-number',
                     134: 'agent/5134-longer-number', 135: 'claude/a135f', 136: 'agent/issue136'}
        self.issues(**{'issue%d' % n: 'CLOSED' for n in old_names})
        tips = {n: self.renamed(old, 'scratch/%d-probe' % n) for n, old in old_names.items()}
        for dry in ('--dry-run',), ():
            out = self.sweep(*dry)
            for number, old in old_names.items():
                self.assertIn('KEPT scratch/%d-probe at %s: renamed from %s, a name without #%d'
                              % (number, tips[number], old, number), out)
        for number, tip in tips.items():
            self.assertEqual(self.tip('scratch/%d-probe' % number), tip)

    def test_reads_every_rename_of_a_branch_renamed_twice(self):
        """A rename keeps the reflog, so every old name needs the number: a branch cannot be
        laundered through a name that has it (140), and the number in an early name does not
        excuse a later name without it (141). Renamed twice between its own names (142), it
        goes as a single rename would."""
        self.issues(issue140='CLOSED', issue141='CLOSED', issue142='CLOSED')
        launder = self.renamed('agent/task-a', 'agent/140-probe', 'scratch/140-probe')
        lost = self.renamed('agent/141-probe', 'agent/task-b', 'scratch/141-probe')
        self.renamed('agent/142-probe', 'agent/142-renamed', 'scratch/142-probe')
        out = self.sweep()
        self.assertIn('KEPT scratch/140-probe at %s: renamed from agent/task-a, a name without '
                      '#140' % launder, out)
        self.assertIn('KEPT scratch/141-probe at %s: renamed from agent/task-b, a name without '
                      '#141' % lost, out)
        self.assertIn('DELETED scratch/142-probe at ', out)

    def test_reads_a_rename_made_in_a_worktree_that_then_detached(self):
        self.issues(issue143='CLOSED', issue144='CLOSED')
        tips = {}
        for number, old in ((143, 'claude/wizardly'), (144, 'agent/144-task')):
            wt = os.path.join(self.dir, 'tree-%d' % number)
            self.git(self.repo, 'worktree', 'add', '-q', '-b', old, wt, 'main')
            tips[number] = self.commit(wt, 'probe%d.txt' % number)
            self.git(wt, 'branch', '-m', old, 'scratch/%d-probe' % number)
            self.git(wt, 'switch', '-q', '--detach', 'main')
        out = self.sweep()
        self.assertIn('KEPT scratch/143-probe at %s: renamed from claude/wizardly, a name '
                      'without #143' % tips[143], out)
        self.assertIn('DELETED scratch/144-probe at %s' % tips[144], out)

    def test_keeps_a_scratch_branch_whose_reflog_cannot_rule_a_rename_out(self):
        self.issues(issue150='CLOSED', issue151='CLOSED', issue152='CLOSED')
        missing = self.scratch('scratch/150-no-reflog')
        os.unlink(self.reflog_file('scratch/150-no-reflog'))
        tips = {}
        for number in (151, 152):  # three entries: created, then two commits
            name = 'scratch/%d-probe' % number
            wt = os.path.join(self.dir, 'tree-%d' % number)
            self.git(self.repo, 'worktree', 'add', '-q', '-b', name, wt, 'main')
            self.commit(wt, 'one%d.txt' % number)
            tips[number] = self.commit(wt, 'two%d.txt' % number)
            self.git(wt, 'switch', '-q', '--detach', 'main')
            with open(self.reflog_file(name), newline='') as f:
                lines = f.read().split('\n')
            self.assertEqual(len([line for line in lines if line]), 3)
            del lines[0 if number == 151 else 1]  # an expired creation, or a hole in the middle
            with open(self.reflog_file(name), 'w', newline='') as f:
                f.write('\n'.join(lines))
        out = self.sweep()
        self.assertIn('KEPT scratch/150-no-reflog at %s: no reflog to show how it was made'
                      % missing, out)
        self.assertIn('KEPT scratch/151-probe at %s: its reflog no longer reaches its creation'
                      % tips[151], out)
        self.assertIn('KEPT scratch/152-probe at %s: its reflog has a gap' % tips[152], out)

    @unittest.skipIf(WINDOWS, 'names a Windows file system may not hold as a ref file')
    def test_reads_a_rename_from_a_name_git_allows_and_python_splits(self):
        """git refuses only ASCII spaces and controls in a name: what Python calls whitespace or
        a line end, or a regular expression's characters, must not hide the rename."""
        old_names = {170: 'agent/task nbsp', 171: 'agent/task　wide',
                     172: 'agent/task line', 173: 'agent/task\u0085next',
                     174: 'agent/(task)+$|x'}
        self.issues(**{'issue%d' % n: 'CLOSED' for n in old_names})
        tips = {n: self.renamed(old, 'scratch/%d-probe' % n) for n, old in old_names.items()}
        out = self.sweep()
        for number, old in old_names.items():
            self.assertIn('KEPT scratch/%d-probe at %s: renamed from %s, a name without #%d'
                          % (number, tips[number], old, number), out)

    def test_a_probe_on_a_branch_without_the_number_gets_a_scratch_branch_at_its_commit(self):
        """The sweep deletes the scratch branch, the old branch keeps the commit, and the
        detached worktree can still be removed by name."""
        self.issues(issue160='CLOSED')
        wt = os.path.join(self.dir, 'tree-160')
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/no-number', wt, 'main')
        tip = self.commit(wt, 'probe160.txt')
        self.git(wt, 'branch', 'scratch/160-probe', tip)
        self.git(wt, 'switch', '-q', '--detach', 'main')
        self.assertIn('DELETED scratch/160-probe at %s' % tip, self.sweep())
        self.assertEqual(self.tip('agent/no-number'), tip)
        code, out = self.run_tool(REMOVE, wt)
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(wt))
        self.assertEqual(self.tip('agent/no-number'), tip)

    # -- merged branches --

    def test_deletes_a_merged_branch_left_by_a_switch_and_names_its_remote_copy(self):
        wt = self.new_task('left')
        tip = self.tip('agent/left')
        self.github_merge('agent/left')
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 11, 'head': 'agent/left',
                                               'headRefOid': tip}])
        self.git(self.repo, 'fetch', '-q', 'origin')
        self.git(wt, 'switch', '-q', '-c', 'agent/next', 'origin/main')  # the worktree lives on
        out = self.sweep()
        self.assertIn('DELETED agent/left at %s (in refs/remotes/origin/main); back: git branch '
                      'agent/left %s; remote copy: origin/agent/left (pull request #11)\n'
                      % (tip, tip), out)
        self.assertFalse(self.has_branch('agent/left'))
        self.assertTrue(os.path.isdir(wt))
        self.assertIn('KEPT agent/next at ', out)
        self.assertIn('pr list -R %s --head agent/left ' % self.origin,
                      '\n'.join(self.gh_calls('pr list')))

    def test_a_long_lived_branch_in_main_keeps_its_remote_copy(self):
        """develop's tip sits in the default branch, but no pull request merged it: the local
        branch goes (origin still has it), the remote copy is not offered for deletion."""
        tip = self.merged_branch('develop', push=True)
        out = self.sweep()
        self.assertIn('DELETED develop at %s (in refs/remotes/origin/main); back: git branch '
                      'develop %s; remote copy kept: origin/develop (no merged pull request)\n'
                      % (tip, tip), out)
        self.env['AGENTIC_GITHUB_FLOW_GH'] = '[]'
        self.git(self.repo, 'branch', 'develop', tip)
        self.assertIn('remote copy kept: origin/develop (no merged pull request known: gh is not '
                      'installed', self.sweep())

    def test_deletes_the_merged_branch_of_a_removed_worktree_while_local_main_is_behind(self):
        tip = self.merged_branch('agent/170-gone')
        self.assertNotEqual(self.tip('main'), self.tip('origin/main'))
        out = self.sweep()
        self.assertIn('DELETED agent/170-gone at %s (in refs/remotes/origin/main); '
                      'back: git branch agent/170-gone %s\n' % (tip, tip), out)  # no remote copy
        self.assertFalse(self.has_branch('agent/170-gone'))

    def test_a_remote_copy_only_a_stale_tracking_ref_remembers_is_not_named(self):
        tip = self.merged_branch('agent/stale', push=True)
        self.git(self.dir, '--git-dir', self.origin, 'branch', '-D', 'agent/stale')
        self.assertTrue(self.tip('refs/remotes/origin/agent/stale'))
        self.assertIn('WOULD DELETE agent/stale at %s (in refs/remotes/origin/main)\n' % tip,
                      self.sweep('--dry-run'))

    def test_leaves_an_unmerged_branch_alone(self):
        wt = self.new_task('open')
        tip = self.tip('agent/open')
        self.git(self.repo, 'worktree', 'remove', wt)
        out = self.sweep()
        self.assertEqual(self.tip('agent/open'), tip)
        self.assertNotIn('agent/open', out)
        self.assertIn('not merged, left alone: 1\n', out)

    def test_a_merged_branch_a_worktree_holds_stays(self):
        self.git(self.repo, 'fetch', '-q', 'origin')
        wt = os.path.join(self.dir, 'fresh')
        self.git(self.repo, 'worktree', 'add', '-q', '--no-track', '-b',
                 'agent/171-fresh', wt, 'origin/main')
        tip = self.tip('origin/main')
        with self.subTest('in a linked worktree'):
            self.assertIn('KEPT agent/171-fresh at %s: checked out in %s' % (tip, wt),
                          self.sweep())
        with self.subTest('in the primary checkout'):
            self.git(self.repo, 'switch', '-q', '-c', 'agent/172-primary')
            self.assertIn('KEPT agent/172-primary at %s: checked out in %s'
                          % (self.tip('HEAD'), self.repo), self.sweep())
            self.git(self.repo, 'switch', '-q', 'main')
        with self.subTest('in a worktree whose directory is gone, until the prune'):
            shutil.rmtree(wt)
            self.assertIn('KEPT agent/171-fresh at %s: held by %s, whose directory is gone: '
                          'stays until `git worktree prune`' % (tip, wt), self.sweep())
            self.assertTrue(self.has_branch('agent/171-fresh'))
            self.git(self.repo, 'worktree', 'prune')
            self.assertIn('DELETED agent/171-fresh at %s' % tip, self.sweep())

    def test_a_commit_only_the_reflog_holds_keeps_a_merged_branch(self):
        self.git(self.repo, 'fetch', '-q', 'origin')
        wt = os.path.join(self.dir, 'tree-dropped')
        self.git(self.repo, 'worktree', 'add', '-q', '--no-track', '-b',
                 'agent/173-dropped', wt, 'origin/main')
        dropped = self.commit(wt, 'dropped.txt')
        self.git(wt, 'push', '-q', '-u', 'origin', 'agent/173-dropped')  # a tracking ref: no proof
        self.git(wt, 'checkout', '-q', '-B', 'agent/173-dropped', 'origin/main')
        self.git(self.repo, 'worktree', 'remove', wt)
        tip = self.tip('agent/173-dropped')
        self.assertIn('KEPT agent/173-dropped at %s: its reflog holds commits that are not in '
                      'refs/remotes/origin/main: %s' % (tip, dropped[:12]), self.sweep())
        self.assertTrue(self.has_branch('agent/173-dropped'))
        self.land(dropped)
        self.assertIn('DELETED agent/173-dropped at %s' % tip, self.sweep())

    def test_a_commit_amend_replaced_does_not_keep_a_merged_branch(self):
        self.git(self.repo, 'fetch', '-q', 'origin')
        wt = os.path.join(self.dir, 'tree-amended')
        self.git(self.repo, 'worktree', 'add', '-q', '--no-track', '-b',
                 'agent/174-amended', wt, 'origin/main')
        self.commit(wt, 'amended.txt')
        self.write(wt, 'amended.txt', 'second\n')
        self.git(wt, 'commit', '-q', '--amend', '-m', 'amended', '--', 'amended.txt')
        tip = self.git(wt, 'rev-parse', 'HEAD').stdout.strip()
        self.land(tip)
        self.git(self.repo, 'worktree', 'remove', wt)
        self.assertIn('DELETED agent/174-amended at %s' % tip, self.sweep())

    def test_a_merged_branch_without_a_reflog_goes(self):
        tip = self.merged_branch('agent/175-no-reflog')
        os.unlink(self.reflog_file('agent/175-no-reflog'))
        self.assertIn('DELETED agent/175-no-reflog at %s' % tip, self.sweep())

    def test_a_merged_claude_branch_stays(self):
        tip = self.merged_branch('claude/176-chat')
        self.assertIn('KEPT claude/176-chat at %s: claude/* belongs to a desktop-app session'
                      % tip, self.sweep())
        self.assertTrue(self.has_branch('claude/176-chat'))

    def test_the_merged_pass_leaves_scratch_branches_to_their_own_pass(self):
        self.issues(issue177='OPEN')
        tip = self.merged_branch('scratch/177-probe')
        out = self.sweep()
        self.assertIn('KEPT scratch/177-probe at %s: issue #177 is open' % tip, out)
        self.assertEqual(out.count('scratch/177-probe at'), 1)

    def test_a_refused_delete_is_kept_and_no_failure(self):
        """In a rebase the worktree list shows no branch; git branch -D still refuses."""
        wt = os.path.join(self.dir, 'tree-agent-179-rebasing')
        tip = self.merged_branch('agent/179-rebasing', keep_tree=True)
        self.assertNotEqual(self.git(wt, 'rebase', '--exec', 'false', 'HEAD~1',
                                     check=False).returncode, 0)
        self.assertNotIn('agent/179-rebasing',
                         self.git(self.repo, 'worktree', 'list', '--porcelain').stdout)
        self.assertIn('KEPT agent/179-rebasing at %s: git branch -D refused: ' % tip,
                      self.sweep())
        self.assertTrue(self.has_branch('agent/179-rebasing'))

    def test_protected_names_stay(self):
        self.git(self.repo, 'push', '-q', 'origin', 'main:trunk')
        self.git(self.repo, 'remote', 'set-head', 'origin', 'trunk')
        for name in ('master', 'trunk'):
            self.git(self.repo, 'branch', name, 'main')
        self.git(self.repo, 'switch', '-q', '-c', 'agent/180-primary')  # nothing holds main
        out = self.sweep()
        self.assertIn('default branch: refs/remotes/origin/trunk', out)
        for name in ('main', 'master', 'trunk'):
            with self.subTest(name):
                self.assertTrue(self.has_branch(name))
                self.assertNotIn(' %s at ' % name, out)

    def test_a_repository_without_a_remote_counts_against_local_main(self):
        wt = os.path.join(self.dir, 'tree-local')
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/182-local', wt, 'main')
        tip = self.commit(wt, 'local.txt')
        self.git(self.repo, 'merge', '-q', '--ff-only', tip)
        self.git(self.repo, 'worktree', 'remove', wt)
        self.git(self.repo, 'remote', 'remove', 'origin')
        self.assertIn('DELETED agent/182-local at %s (in refs/heads/main); back: git branch '
                      'agent/182-local %s\n' % (tip, tip), self.sweep())

    def test_no_fetch_skips_the_merged_pass(self):
        self.merged_branch('agent/183-merged')
        out = self.sweep('--no-fetch')
        self.assertIn('merged branches: none deleted: --no-fetch', out)
        self.assertTrue(self.has_branch('agent/183-merged'))

    def test_dry_run_of_the_merged_pass_deletes_nothing(self):
        tip = self.merged_branch('agent/184-merged')
        wt = self.new_task('184-task')
        self.github_merge('agent/184-task')
        out = self.sweep('--dry-run')
        self.assertIn('WOULD DELETE agent/184-merged at %s (in refs/remotes/origin/main)' % tip,
                      out)
        self.assertIn('merged branches would be deleted: 1; ', out)
        self.assertTrue(self.has_branch('agent/184-merged'))
        # a worktree the same run would remove still holds its branch: the removal takes it
        self.assertIn('WOULD REMOVE %s and branch agent/184-task' % wt, out)
        self.assertIn('KEPT agent/184-task at ', out)

    # -- squash and rebase merges: the merged pull request's head --

    def squashed(self, name, number):
        """A branch squash-merged on GitHub; the fake gh knows its pull request when number."""
        wt = self.new_task(name, commits=2)
        tip = self.tip('agent/' + name)
        self.github_merge('agent/' + name, squash=True)
        self.git(self.repo, 'worktree', 'remove', wt)
        if number:
            pulls = json.loads(self.env['FAKE_GH_PRS'])
            pulls.append({'number': number, 'head': 'agent/' + name, 'headRefOid': tip})
            self.env['FAKE_GH_PRS'] = json.dumps(pulls)
        return tip

    def test_a_squash_merged_branch_goes_by_its_merged_pull_request(self):
        tip = self.squashed('sq-proven', 21)
        unproven = self.squashed('sq-unknown', None)
        out = self.sweep()
        self.assertIn('DELETED agent/sq-proven at %s (the head of merged pull request #21); '
                      'back: git branch agent/sq-proven %s; remote copy: origin/agent/sq-proven '
                      '(pull request #21)\n' % (tip, tip), out)
        self.assertFalse(self.has_branch('agent/sq-proven'))
        self.assertEqual(self.tip('agent/sq-unknown'), unproven)
        self.assertIn('not merged, left alone: 1\n', out)

    def test_a_squash_merged_branch_with_a_dropped_commit_stays(self):
        wt = self.new_task('sq-dropped')
        dropped = self.tip('agent/sq-dropped')
        self.git(wt, 'checkout', '-q', '-B', 'agent/sq-dropped', 'origin/main')
        self.commit(wt, 'kept.txt')
        tip = self.tip('agent/sq-dropped')
        self.github_merge('agent/sq-dropped', squash=True)
        self.git(self.repo, 'worktree', 'remove', wt)
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 22, 'head': 'agent/sq-dropped',
                                               'headRefOid': tip}])
        self.assertIn('KEPT agent/sq-dropped at %s: its reflog holds commits that are not in '
                      'refs/remotes/origin/main: %s' % (tip, dropped[:12]), self.sweep())

    def test_without_gh_a_squash_merged_branch_is_only_counted(self):
        tip = self.squashed('sq-nogh', 23)
        self.env['AGENTIC_GITHUB_FLOW_GH'] = '[]'
        out = self.sweep()
        self.assertEqual(self.tip('agent/sq-nogh'), tip)
        self.assertIn('not merged, left alone: 1 (squash merges not checked: gh is not '
                      'installed', out)


class DeleteMergedTests(Repos):
    def remote_has(self, branch):
        return bool(self.git(self.repo, 'ls-remote', '--heads', 'origin', branch).stdout.strip())

    def test_squash_merged_branch_is_deleted_while_its_tip_is_the_merged_head(self):
        self.new_task('del-squash')
        tip = self.tip('agent/del-squash')
        self.github_merge('agent/del-squash', squash=True)
        code, out = self.run_tool(DELETE, 'agent/del-squash', '--dry-run')
        self.assertEqual(code, 1, out)  # no merged pull request known yet
        log = os.path.join(self.dir, 'gh.log')
        self.env['FAKE_GH_LOG'] = log
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 4, 'head': 'agent/del-squash',
                                               'headRefOid': tip}])
        code, out = self.run_tool(DELETE, 'agent/del-squash', '--dry-run')
        self.assertEqual(code, 0, out)
        self.assertIn('WOULD DELETE', out)
        with open(log) as f:  # the repository named outright, never gh's own pick
            self.assertIn('pr list -R %s --head agent/del-squash ' % self.origin, f.read())
        self.assertTrue(self.remote_has('agent/del-squash'))
        code, out = self.run_tool(DELETE, 'agent/del-squash')
        self.assertEqual(code, 0, out)
        self.assertFalse(self.remote_has('agent/del-squash'))
        code, out = self.run_tool(DELETE, 'agent/del-squash')
        self.assertEqual(code, 0, out)
        self.assertIn('GONE', out)

    def test_a_commit_pushed_after_the_merge_keeps_the_remote_branch(self):
        wt = self.new_task('del-moved')
        tip = self.tip('agent/del-moved')
        self.github_merge('agent/del-moved', squash=True)
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 5, 'head': 'agent/del-moved',
                                               'headRefOid': tip}])
        self.write(wt, 'teammate.txt', 'pushed after the merge\n')
        self.git(wt, 'add', '--', 'teammate.txt')
        self.git(wt, 'commit', '-q', '-m', 'late')
        self.git(wt, 'push', '-q', 'origin', 'agent/del-moved')
        code, out = self.run_tool(DELETE, 'agent/del-moved')
        self.assertEqual(code, 1, out)
        self.assertIn('KEPT', out)
        self.assertTrue(self.remote_has('agent/del-moved'))

    def test_merge_commit_needs_no_pull_request_and_default_branch_is_refused(self):
        self.new_task('del-merged')
        self.github_merge('agent/del-merged')
        code, out = self.run_tool(DELETE, 'agent/del-merged')
        self.assertEqual(code, 0, out)
        self.assertFalse(self.remote_has('agent/del-merged'))
        code, out = self.run_tool(DELETE, 'main')
        self.assertEqual(code, 1, out)
        self.assertIn('never deleted', out)


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

    def test_lease_protected_delete_passes_the_hook(self):
        self.new_task('pp-lease')
        self.github_merge('agent/pp-lease')
        code, out = self.run_tool(DELETE, 'agent/pp-lease')
        self.assertEqual(code, 0, out)

    @unittest.skipIf(WINDOWS, 'the stand-in gh is a shell script; Git for Windows may not run it')
    def test_squash_merged_branch_deletion_needs_the_merged_pull_request(self):
        self.new_task('pp-squash')
        tip = self.tip('agent/pp-squash')
        self.github_merge('agent/pp-squash', squash=True)
        self.git(self.repo, 'fetch', '-q', 'origin')
        self.assertNotEqual(self.push('--delete', 'agent/pp-squash').returncode, 0)
        self.env['FAKE_GH_PRS'] = json.dumps([{'number': 9, 'head': 'agent/pp-squash',
                                               'headRefOid': tip}])
        log = os.path.join(self.dir, 'gh.log')
        self.env['FAKE_GH_LOG'] = log
        self.assertEqual(self.push('--delete', 'agent/pp-squash').returncode, 0)
        with open(log) as f:  # the pushed-to remote named outright, never gh's own pick
            self.assertIn('pr list -R %s --head agent/pp-squash ' % self.origin, f.read())


if __name__ == '__main__':
    unittest.main()
