#!/usr/bin/env python3
"""Checks plugins/core/scripts/overlap_check.py in a scratch repository: python3 tests/overlap_check.py.

The repository has an origin whose default branch (origin/HEAD) is ahead of local main by a
merged branch, a candidate branch and other unmerged branches: one that shares a file with it,
one that does not, one that shares a file but went quiet long ago, one that the candidate already
contains, one that renames the shared file away, one squash-merged by a pull request, and a
second branch of the candidate's own issue. A stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) answers
from a state file. Each case is a way the check could let two sessions collide unnoticed (a
missed branch, pull request or claimed issue, a design note not named, a GitHub failure read as
"no overlap") or bury a real hit in noise; the last case checks that the tool changed nothing.
Offline; no network, no real gh.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'overlap_check.py')
URL = 'https://github.com/o/r/issues/'
ROBOT = '\N{ROBOT FACE}'

STUB = r'''import json, os, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
s.setdefault('log', []).append(a)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if s.get('fail'):
    print('error connecting to api.github.com', file=sys.stderr); sys.exit(1)
issues = s['issues']
def arg(name):
    return a[a.index(name) + 1] if name in a else None
if a[:2] == ['issue', 'view']:
    print(json.dumps(next(i for i in issues if str(i['number']) == a[2])))
elif a[:2] == ['issue', 'list'] and arg('--assignee') == '*':
    print(json.dumps([i for i in issues if i['assignees']]))
elif a[:2] == ['pr', 'list'] and arg('--state') == 'open':
    print(json.dumps(s['pulls']))
elif a[:2] == ['pr', 'list'] and arg('--state') == 'merged':
    print(json.dumps([p for p in s['merged'] if p['headRefName'] == arg('--head')]))
else:
    sys.exit(2)
'''


def issue(n, body='', assigned=False, comments=()):
    return {'number': n, 'title': 'issue %d' % n, 'url': URL + str(n), 'body': body,
            'assignees': [{'login': 'someone'}] if assigned else [],
            'comments': [{'body': b, 'url': '%s%d#c%d' % (URL, n, k)} for k, b in enumerate(comments)]}


def pull(n, head, sha, files, title='work', comments=()):
    return {'number': n, 'title': title, 'url': 'https://github.com/o/r/pull/%d' % n,
            'headRefName': head, 'headRefOid': sha, 'files': [{'path': p} for p in files],
            'comments': [{'body': b, 'url': 'https://github.com/o/r/pull/%d#c%d' % (n, k)}
                         for k, b in enumerate(comments)]}


class OverlapCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='overlap-check-')
        root = os.path.realpath(cls.tmp.name)
        cls.env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t.invalid',
                       GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t.invalid',
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        stub = os.path.join(root, 'fake_gh.py')
        with open(stub, 'w') as f:
            f.write(STUB)
        cls.env['AGENTIC_GITHUB_FLOW_GH'] = json.dumps([sys.executable, stub])
        cls.state = os.path.join(root, 'gh.json')
        origin = os.path.join(root, 'origin.git')
        cls.repo = r = os.path.join(root, 'repo')
        cls.git('init', '-q', '--bare', '-b', 'main', origin, cwd=root)
        cls.git('init', '-q', '-b', 'main', r, cwd=root)
        cls.git('remote', 'add', 'origin', origin)
        cls.commit('src/hot.rs', 'a\n', 'base')
        cls.commit('src/other.rs', 'a\n', 'base 2')
        cls.commit('src/mod.rs', 'a\n', 'base 3')
        cls.git('push', '-q', 'origin', 'main')
        cls.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        for name, path, old in [('agent/7-hot', 'src/hot.rs', False),
                                ('agent/8-cold', 'src/other.rs', False),
                                ('agent/9-stale', 'src/hot.rs', True),
                                ('agent/10-dup', 'src/new.rs', False),
                                ('agent/10-mine', 'src/hot.rs', False),
                                ('agent/13-merged', 'src/hot.rs', False),
                                ('agent/14-squashed', 'src/hot.rs', False)]:
            cls.git('checkout', '-q', '-b', name, 'main')
            cls.commit(path, name + '\n', 'work on ' + name, old=old)
        # merged into the default branch on origin; local main is behind
        cls.git('push', '-q', 'origin', 'agent/13-merged:main')
        cls.git('checkout', '-q', '-b', 'agent/11-part', 'main')
        cls.commit('src/hot.rs', 'part\n', 'part (#11)')
        cls.git('checkout', '-q', '-b', 'integrate/11-whole', 'agent/11-part')
        cls.commit('src/whole.rs', 'x\n', 'more (#11)')
        cls.git('checkout', '-q', '-b', 'agent/12-move', 'main')
        cls.git('mv', 'src/other.rs', 'src/moved.rs')
        cls.git('commit', '-q', '-m', 'move')
        cls.git('checkout', '-q', 'main')
        cls.sha = {b: cls.git('rev-parse', b).strip()
                   for b in ('agent/7-hot', 'agent/10-mine', 'agent/14-squashed')}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def git(cls, *args, cwd=None, env=None):
        return subprocess.run(['git', *args], cwd=cwd or cls.repo, env=env or cls.env, check=True,
                              capture_output=True, text=True).stdout

    @classmethod
    def commit(cls, path, text, msg, old=False):
        full = os.path.join(cls.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w') as f:
            f.write(text)
        env = dict(cls.env)
        if old:
            stamp = '@%d +0000' % (time.time() - 60 * 86400)
            env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        cls.git('add', path, env=env)
        cls.git('commit', '-q', '-m', msg, env=env)

    def run_tool(self, *args, issues=(), pulls=(), merged=(), fail=False, env=None):
        with open(self.state, 'w') as f:
            json.dump({'issues': list(issues), 'pulls': list(pulls), 'merged': list(merged),
                       'fail': fail}, f)
        env = dict(env or self.env, STUB_GH=self.state)
        p = subprocess.run([sys.executable, TOOL, '-C', self.repo, *args], env=env,
                           capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout

    def test_seeded_overlapping_branch_found(self):
        code, out = self.run_tool('--branch', 'agent/10-mine', '--no-github')
        self.assertEqual(code, 1, out)
        self.assertIn('overlap: branch agent/7-hot (#7)', out)
        self.assertIn('src/hot.rs', out)
        self.assertNotIn('agent/8-cold', out)

    def test_base_is_the_default_branch_on_origin(self):
        code, out = self.run_tool('--branch', 'agent/10-mine', '--no-github')
        self.assertNotIn('agent/13-merged', out)  # in origin/main, not in local main
        code, out = self.run_tool('--branch', 'agent/10-mine', '--no-github', '--base', 'main')
        self.assertIn('agent/13-merged', out)

    def test_quiet_branch_counted_not_listed(self):
        code, out = self.run_tool('--branch', 'agent/10-mine', '--no-github')
        self.assertNotIn('agent/9-stale', out)
        self.assertIn('skipped: 1 unmerged branch', out)
        code, out = self.run_tool('--branch', 'agent/10-mine', '--no-github', '--days', '90')
        self.assertIn('agent/9-stale', out)

    def test_second_session_on_the_same_issue(self):
        code, out = self.run_tool('--paths', 'src/elsewhere.rs', '--issue', '10', '--no-github')
        self.assertEqual(code, 1, out)
        self.assertIn('same issue: branch agent/10-dup', out)

    def test_branch_contained_in_the_candidate_left_out(self):
        code, out = self.run_tool('--branch', 'integrate/11-whole', '--no-github')
        self.assertNotIn('agent/11-part', out)
        self.assertIn('agent/7-hot', out)

    def test_rename_counts_on_both_sides(self):
        code, out = self.run_tool('--paths', 'src/other.rs', '--issue', '99', '--no-github')
        self.assertEqual(code, 1, out)
        self.assertIn('agent/12-move', out)
        self.assertIn('agent/8-cold', out)

    def test_no_overlap(self):
        code, out = self.run_tool('--paths', 'docs/x.md', '--no-github')
        self.assertEqual(code, 0, out)
        self.assertTrue(out.strip().splitlines()[-1].startswith('none:'), out)

    def test_squash_merged_branch_not_counted(self):
        code, out = self.run_tool('--branch', 'agent/10-mine', '--no-github')
        self.assertIn('agent/14-squashed', out)  # without GitHub a squash merge is unknown
        merged = [{'number': 5, 'headRefName': 'agent/14-squashed', 'baseRefName': 'main',
                   'headRefOid': self.sha['agent/14-squashed']},
                  {'number': 6, 'headRefName': 'agent/7-hot', 'baseRefName': 'release',
                   'headRefOid': self.sha['agent/7-hot']}]  # merged elsewhere: still unmerged
        code, out = self.run_tool('--branch', 'agent/10-mine', merged=merged)
        self.assertEqual(code, 1, out)
        self.assertNotIn('overlap: branch agent/14-squashed', out)
        self.assertIn('merged: 1 branch(es) merged by pull request', out)
        self.assertIn('overlap: branch agent/7-hot', out)

    def test_open_pull_requests(self):
        pulls = [
            pull(30, 'teammate/hot-fix', 'a' * 40, ['src/hot.rs', 'docs/a.md'],
                 comments=[ROBOT + ' Codex (author): design note: keep the API']),
            pull(31, 'agent/7-hot', self.sha['agent/7-hot'], ['src/hot.rs']),  # judged locally
            pull(32, 'agent/10-mine', self.sha['agent/10-mine'], ['src/hot.rs']),  # the candidate
            pull(33, 'teammate/docs', 'b' * 40, ['docs/b.md']),
            pull(34, 'teammate/40-other', 'c' * 40, ['src/hot.rs']),
        ]
        issues = [issue(40, comments=[ROBOT + ' Claude Code (author): design delta: Y'])]
        code, out = self.run_tool('--branch', 'agent/10-mine', '--days', '1', pulls=pulls,
                                  issues=issues)
        self.assertEqual(code, 1, out)
        self.assertIn("overlap: pull request #30 (teammate/hot-fix) 'work': src/hot.rs", out)
        self.assertIn('note: https://github.com/o/r/pull/30#c0', out)
        self.assertIn('overlap: pull request #34 (teammate/40-other) (#40)', out)
        self.assertIn('note: %s40#c0' % URL, out)
        for absent in ('#31', '#32', '#33'):
            self.assertNotIn('pull request ' + absent, out)
        code, out = self.run_tool('--paths', 'src/elsewhere.rs', '--issue', '40', pulls=pulls,
                                  issues=issues)
        self.assertIn('same issue: pull request #34', out)

    def test_claimed_issue_and_design_notes(self):
        issues = [
            issue(7, assigned=True, comments=[ROBOT + ' Claude Code (author): starting',
                                              ROBOT + ' Claude Code (author): design note: X']),
            issue(20, body='Touches `hot.rs` and src/mod.rs', assigned=True,
                  comments=[ROBOT + ' Codex (author): claimed']),
            issue(22, body='edits src/hot.rs'),  # not claimed: nobody works on it
            issue(23, body='only src/mod.rs and lib.rs', assigned=True),
            issue(99, body='src/hot.rs', assigned=True),  # the issue being picked
        ]
        code, out = self.run_tool('--paths', 'src/hot.rs', 'src/x/mod.rs', '--issue', '99',
                                  issues=issues)
        self.assertEqual(code, 1, out)
        self.assertIn('note: %s7#c1' % URL, out)
        self.assertIn('overlap: issue #20 (claimed)', out)
        self.assertIn('newest signed comment: %s20#c0' % URL, out)
        self.assertNotIn('#22', out)
        self.assertNotIn('#23', out)
        self.assertNotIn('issue #99', out)

    def test_github_unreadable_is_not_none(self):
        code, out = self.run_tool('--paths', 'docs/x.md', fail=True)
        self.assertEqual(code, 3, out)
        self.assertIn('unchecked:', out)
        code, out = self.run_tool('--branch', 'agent/10-mine', fail=True)
        self.assertEqual(code, 3, out)  # branch hits do not hide that GitHub went unread
        self.assertIn('overlap: branch agent/7-hot', out)
        self.assertTrue(out.strip().splitlines()[-1].startswith('unchecked:'), out)
        env = dict(self.env, AGENTIC_GITHUB_FLOW_GH='not json')  # as if gh were missing
        code, out = self.run_tool('--paths', 'docs/x.md', env=env)
        self.assertEqual(code, 3, out)
        self.assertIn('gh is not installed', out)

    def test_bad_arguments(self):
        self.assertEqual(self.run_tool()[0], 2)
        self.assertEqual(self.run_tool('--branch', 'no/such-branch', '--no-github')[0], 2)
        self.assertEqual(self.run_tool('--paths', 'a', '--base', 'nope', '--no-github')[0], 2)

    def test_changes_nothing(self):
        before = (self.git('for-each-ref'), self.git('status', '--porcelain', '--ignored'),
                  self.git('rev-parse', 'HEAD'))
        self.run_tool('--branch', 'agent/10-mine', issues=[issue(7, assigned=True)])
        after = (self.git('for-each-ref'), self.git('status', '--porcelain', '--ignored'),
                 self.git('rev-parse', 'HEAD'))
        self.assertEqual(before, after)
        with open(self.state) as f:
            log = json.load(f)['log']
        self.assertTrue(all(c[:2] in (['issue', 'list'], ['issue', 'view'], ['pr', 'list'])
                            for c in log), log)


if __name__ == '__main__':
    unittest.main(verbosity=1)
