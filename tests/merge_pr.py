#!/usr/bin/env python3
"""Checks plugins/core/scripts/merge_pr.py in a throwaway repository: python3 tests/merge_pr.py.

A bare origin on disk holds the base branch and the pull request's head at refs/pull/7/head; a
stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) answers `pr view` from a fixture and records `pr merge`.
A folder remote is not GitHub, so landing.py decides pull request unless HANDOFF.md says local
main. Each case is a way an agent could merge what it may not: no grant named, local-main mode,
a draft, a merge state other than CLEAN, a failed, pending or missing check, no review, a review
that does not approve, an approval of an older commit followed by a commit of the author or by
a merge with a conflict resolved by hand, no overlap result, a path that merges only on the
user's word (built in, or named in HANDOFF.md), and a base other than the landing branch. And the
cases that may merge: a review of the head, and of a commit followed only by a clean merge of
the base. Offline: no network, no real gh.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'merge_pr.py')
ROBOT = '\N{ROBOT FACE}'

STUB = r'''import json, os, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
s.setdefault('log', []).append(a)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if a[:2] == ['pr', 'view']:
    print(json.dumps(s['pr'])); sys.exit(0)
if a[:2] == ['pr', 'merge']:
    sys.exit(0)
sys.exit(3)
'''


class MergePr(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.bare = os.path.join(t, 'origin.git')
        self.repo = os.path.join(t, 'repo')
        self.stub = os.path.join(t, 'gh_stub.py')
        self.state = os.path.join(t, 'state.json')
        with open(self.stub, 'w') as f:
            f.write(STUB)
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', self.bare], check=True)
        os.makedirs(self.repo)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Test')
        self.write('app.txt', 'one\n')
        self.write('HANDOFF.md', '# Handoff\n')
        self.git('add', '--', 'app.txt', 'HANDOFF.md')
        self.git('commit', '-q', '-m', 'base')
        self.git('remote', 'add', 'origin', self.bare)
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        self.git('remote', 'set-head', 'origin', 'main')
        self.git('switch', '-q', '-c', 'agent/7-x')
        self.head = self.change('skills.md', 'a skill\n')

    def git(self, *args, check=True):
        r = subprocess.run(['git', '-C', self.repo, *args], capture_output=True, text=True)
        if check:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def write(self, name, text):
        path = os.path.join(self.repo, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)

    def change(self, name, text):
        self.write(name, text)
        self.git('add', '--', name)
        self.git('commit', '-q', '-m', 'change ' + name)
        sha = self.git('rev-parse', 'HEAD')
        self.git('push', '-q', '-f', 'origin', 'HEAD:refs/pull/7/head')
        return sha

    def pr(self, **over):
        pr = {'number': 7, 'state': 'OPEN', 'isDraft': False, 'mergeStateStatus': 'CLEAN',
              'headRefOid': self.head, 'baseRefName': 'main',
              'body': ROBOT + ' Claude Code (author): the change\n\nOverlap check: none\n',
              'comments': [{'createdAt': '2026-11-09T10:00:00Z',
                            'body': ROBOT + ' Claude Code (review): Approved %s: no findings'
                            % self.head[:10]}],
              'reviews': [],
              'statusCheckRollup': [
                  {'__typename': 'CheckRun', 'name': 'test (%s)' % os_name,
                   'status': 'COMPLETED', 'conclusion': 'SUCCESS'}
                  for os_name in ('ubuntu', 'macos', 'windows')]}
        pr.update(over)
        return pr

    def run_tool(self, pr, *args, grant='HANDOFF.md Standing permissions'):
        with open(self.state, 'w') as f:
            json.dump({'pr': pr}, f)
        env = dict(os.environ, STUB_GH=self.state,
                   AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, self.stub]))
        cmd = [sys.executable, TOOL, '7', '-C', self.repo, '-R', 'acme/tool', *args]
        if grant:
            cmd += ['--grant', grant]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        with open(self.state) as f:
            self.log = json.load(f).get('log', [])
        return r

    def merged(self):
        return [a for a in self.log if a[:2] == ['pr', 'merge']]

    def assertMerged(self, pr, *args):
        r = self.run_tool(pr, *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def assertRefused(self, pr, text, *args):
        r = self.run_tool(pr, *args)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(text, r.stdout)
        self.assertEqual(self.merged(), [])

    def test_merges_with_the_head_pinned(self):
        self.assertMerged(self.pr())
        self.assertEqual(self.merged(), [['pr', 'merge', '7', '-R', 'acme/tool', '--merge',
                                          '--match-head-commit', self.head, '--delete-branch']])

    def test_dry_run_and_usage(self):
        r = self.assertMerged(self.pr(), '--dry-run')
        self.assertIn('would merge', r.stdout)
        self.assertEqual(self.merged(), [])
        self.assertEqual(self.run_tool(self.pr(), grant=None).returncode, 2)
        self.assertEqual(self.run_tool(self.pr(), '--method', 'rebase').returncode, 2)

    def test_state(self):
        self.assertRefused(self.pr(isDraft=True), 'a draft')
        self.assertRefused(self.pr(mergeStateStatus='BLOCKED'), 'not CLEAN')
        self.assertRefused(self.pr(state='MERGED'), 'state MERGED')
        self.assertRefused(self.pr(baseRefName='develop'), 'not the landing branch')

    def test_checks(self):
        runs = self.pr()['statusCheckRollup']
        failed = runs[:2] + [dict(runs[2], conclusion='FAILURE')]
        pending = runs[:2] + [dict(runs[2], status='IN_PROGRESS', conclusion='')]
        status = runs + [{'__typename': 'StatusContext', 'context': 'deploy', 'state': 'PENDING'}]
        self.assertRefused(self.pr(statusCheckRollup=failed), 'FAILURE')
        self.assertRefused(self.pr(statusCheckRollup=pending), 'IN_PROGRESS')
        self.assertRefused(self.pr(statusCheckRollup=status), 'status deploy')
        self.assertRefused(self.pr(statusCheckRollup=[]), 'no checks')

    def test_review(self):
        self.assertRefused(self.pr(comments=[]), 'no signed review')
        unsigned = [{'createdAt': '1', 'body': 'Approved %s' % self.head}]
        self.assertRefused(self.pr(comments=unsigned), 'no signed review')
        later = self.pr()['comments'] + [{'createdAt': '2026-11-09T11:00:00Z', 'body':
                                          ROBOT + ' Codex (review): two findings, see below'}]
        self.assertRefused(self.pr(comments=later), 'does not approve')
        as_review = self.pr(comments=[], reviews=[{'submittedAt': '2026-11-09T10:00:00Z',
                                                   'body': self.pr()['comments'][0]['body']}])
        self.assertMerged(as_review)

    def test_approval_of_an_older_commit(self):
        reviewed = self.head
        # a clean merge of the base after the review: green checks suffice
        self.git('switch', '-q', 'main')
        self.write('other.txt', 'o\n')
        self.git('add', '--', 'other.txt')
        self.git('commit', '-q', '-m', 'main moved')
        self.git('push', '-q', 'origin', 'main')
        self.git('switch', '-q', 'agent/7-x')
        self.git('fetch', '-q', 'origin')
        self.git('merge', '-q', '--no-edit', 'origin/main')
        self.head = self.git('rev-parse', 'HEAD')
        self.git('push', '-q', '-f', 'origin', 'HEAD:refs/pull/7/head')
        pr = self.pr(comments=[{'createdAt': '1', 'body': ROBOT +
                                ' Claude Code (review): Approved `%s`' % reviewed[:12]}])
        r = self.assertMerged(pr, '--dry-run')
        self.assertIn('conflict-free merges', r.stdout)
        # an author commit after the review needs a new review
        self.head = self.change('skills.md', 'a skill, changed\n')
        pr['headRefOid'] = self.head
        self.assertRefused(pr, 'review the head again')

    def test_merge_with_a_hand_resolved_conflict_needs_a_new_review(self):
        reviewed = self.head
        self.git('switch', '-q', 'main')
        self.write('skills.md', 'main version\n')
        self.git('add', '--', 'skills.md')
        self.git('commit', '-q', '-m', 'conflicting')
        self.git('push', '-q', 'origin', 'main')
        self.git('switch', '-q', 'agent/7-x')
        self.git('fetch', '-q', 'origin')
        self.git('merge', '-q', 'origin/main', check=False)
        self.write('skills.md', 'resolved by hand\n')
        self.git('add', '--', 'skills.md')
        self.git('commit', '-q', '--no-edit')
        self.head = self.git('rev-parse', 'HEAD')
        self.git('push', '-q', '-f', 'origin', 'HEAD:refs/pull/7/head')
        pr = self.pr(comments=[{'createdAt': '1', 'body': ROBOT +
                                ' Claude Code (review): Approved %s' % reviewed}])
        self.assertRefused(pr, 'conflict or an edit')

    def test_overlap_result(self):
        self.assertRefused(self.pr(body=ROBOT + ' Claude Code (author): no overlap line'),
                           'overlap check result')

    def test_paths_on_the_users_word(self):
        for path in ('rules/core.md', '.github/workflows/ci.yml', 'plugins/guards/x.py',
                     '.claude/settings.json', 'AGENTS.md', 'tools/installer.py', 'vercel.json'):
            with self.subTest(path=path):
                self.head = self.change(path, 'x\n')
                self.assertRefused(self.pr(), "merge only on the user's word")
                self.git('rm', '-q', '--', path)
                self.git('commit', '-q', '-m', 'undo')

    def test_paths_named_in_handoff(self):
        self.git('switch', '-q', 'main')
        self.write('HANDOFF.md', "# H\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n"
                   "| merge on the user's word | `schema/*`, `*.sql` |\n")
        self.git('commit', '-q', '-am', 'settings')
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        self.git('switch', '-q', 'agent/7-x')
        self.git('merge', '-q', '--no-edit', 'origin/main')
        self.head = self.change('db/001.sql', 'create table t();\n')
        pr = self.pr(comments=[{'createdAt': '1', 'body': ROBOT +
                                ' Claude Code (review): Approved %s' % self.head}])
        self.assertRefused(pr, 'db/001.sql')

    def test_local_main_mode(self):
        self.git('switch', '-q', 'main')
        self.write('HANDOFF.md', "# H\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n"
                   "| landing | `local main` |\n")
        self.git('commit', '-q', '-am', 'settings')
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        self.git('switch', '-q', 'agent/7-x')
        self.assertRefused(self.pr(), 'not through pull requests')


if __name__ == '__main__':
    unittest.main(verbosity=1)
