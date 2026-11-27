#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/overview_state.py in a scratch repository:
python3 tests/overview_state.py.

A stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) answers `repo view`, `issue list` and the GraphQL call
from a state file and logs every call. Each case is a way an overview successor could read the
wrong state or flood its context: an older or unsigned state comment taken for the newest, a
comment of the thread printed beside the state, an unbounded query or print, a missed rollover,
two standing issues read as one, a setting (label, the repository of a shared overview) ignored,
or a GitHub failure read as "no overview". Offline; no network, no real gh.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'overview_state.py')

STUB = r'''import json, os, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
s.setdefault('log', []).append(a)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if s.get('fail'):
    print('error connecting to api.github.com', file=sys.stderr); sys.exit(1)
if a[:2] == ['repo', 'view']:
    print(json.dumps({'nameWithOwner': s['repo']})); sys.exit(0)
if a[:2] == ['issue', 'list']:
    repo = a[a.index('-R') + 1]
    label = a[a.index('--label') + 1]
    out = [{'number': i['number'], 'title': i['title']} for i in s['issues']
           if i['repo'] == repo and label in i['labels'] and i['state'] == 'OPEN']
    print(json.dumps(out)); sys.exit(0)
if a[:2] == ['api', 'graphql']:
    f = dict(x.split('=', 1) for x in a[2:] if '=' in x and not x.startswith('query='))
    q = [x for x in a if x.startswith('query=')][0]
    last = int(q.split('comments(last:')[1].split(')')[0])
    repo = f['owner'] + '/' + f['name']
    hit = [i for i in s['issues'] if i['repo'] == repo and str(i['number']) == f['number']]
    if not hit:
        print(json.dumps({'data': {'repository': {'issue': None}}})); sys.exit(0)
    i = hit[0]
    nodes = [{'body': b, 'createdAt': '2026-11-%02dT10:00:00Z' % (1 + k % 28)}
             for k, b in enumerate(i['comments'])]
    print(json.dumps({'data': {'repository': {'issue': {
        'number': i['number'], 'title': i['title'], 'state': i['state'],
        'comments': {'totalCount': len(nodes), 'nodes': nodes[-last:]}}}}})); sys.exit(0)
sys.exit(2)
'''

ROBOT = '\N{ROBOT FACE}'
SIGN = ROBOT + ' Claude Opus 5.5 (overview 3): '


def state(text):
    return SIGN + 'overview state: ' + text


def claim(n):
    return SIGN + f'claimed for chat "#7 · overview {n}" (local_{n}), worktree /w/overview'


def issue(number, comments, repo='me/repo', labels=('overview',), state_='OPEN', title='Overview'):
    return {'number': number, 'repo': repo, 'labels': list(labels), 'state': state_,
            'title': title, 'comments': list(comments)}


class OverviewState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, 'repo')
        os.makedirs(self.repo)
        self.git('init', '-q', '-b', 'main')
        self.handoff('')
        self.stub = os.path.join(self.tmp.name, 'gh_stub.py')
        with open(self.stub, 'w') as f:
            f.write(STUB)
        self.state_file = os.path.join(self.tmp.name, 'gh.json')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(['git', '-C', self.repo, '-c', 'user.name=t', '-c', 'user.email=t@example.com',
                        *args], check=True, capture_output=True)

    def handoff(self, rows):
        with open(os.path.join(self.repo, 'HANDOFF.md'), 'w') as f:
            f.write('# Handoff\n\n## Issue chats settings\n\n| Setting | Value |\n|---|---|\n'
                    '| ready label | `agent-ready` |\n' + rows + '\n## Next\n')
        self.git('add', 'HANDOFF.md')
        self.git('commit', '-q', '-m', 'settings')

    def run_tool(self, issues, *args, fail=False, repo='me/repo'):
        with open(self.state_file, 'w') as f:
            json.dump({'issues': issues, 'repo': repo, 'fail': fail}, f)
        env = dict(os.environ, STUB_GH=self.state_file,
                   AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, self.stub]))
        p = subprocess.run([sys.executable, TOOL, '-C', self.repo, *args], capture_output=True,
                           text=True, env=env)
        with open(self.state_file) as f:
            self.log = json.load(f).get('log', [])
        return p

    def test_prints_only_the_newest_signed_state_and_claim(self):
        thread = [state('OLD STATE'), claim(2), 'a long discussion THREAD TEXT ' * 50,
                  'overview state: UNSIGNED', claim(3), state('NEW STATE'),
                  SIGN + 'a note after it, OTHER COMMENT']
        p = self.run_tool([issue(7, thread)])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('standing issue: me/repo#7 · Overview', p.stdout)
        self.assertIn('NEW STATE', p.stdout)
        self.assertIn('local_3', p.stdout)
        for absent in ('OLD STATE', 'THREAD TEXT', 'UNSIGNED', 'OTHER COMMENT', 'local_2'):
            self.assertNotIn(absent, p.stdout)
        self.assertIn('comments: 7, rollover at 100\n', p.stdout)
        self.assertNotIn('rollover due', p.stdout)

    def test_query_is_bounded_and_rollover_named(self):
        thread = [state('S%d' % k) for k in range(150)]
        p = self.run_tool([issue(7, thread)])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('comments: 150, rollover at 100\nrollover due\n', p.stdout)
        self.assertIn('S149', p.stdout)
        query = [x for call in self.log if call[:2] == ['api', 'graphql'] for x in call
                 if x.startswith('query=')]
        self.assertTrue(query and 'comments(last:100)' in query[0], self.log)
        call = [c for c in self.log if c[:2] == ['api', 'graphql']][0]
        self.assertIn('owner=me', call[call.index('owner=me') - 1:])
        self.assertEqual(call[call.index('owner=me') - 1], '-f', 'a string variable gh may convert')
        self.assertFalse([c for c in self.log if c[:2] == ['issue', 'view']],
                         'the whole thread was fetched')

    def test_long_state_named_and_print_cut(self):
        p = self.run_tool([issue(7, [claim(1), state('x' * 1600)])])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('over the 1,500 the method allows', p.stdout)
        p = self.run_tool([issue(7, [claim(1), state('y' * 9000)])])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('[cut at 4000 of', p.stdout)
        self.assertLess(len(p.stdout), 5000)

    def test_no_state_comment(self):
        p = self.run_tool([issue(7, [claim(1), 'chatter'])])
        self.assertEqual(p.returncode, 1)
        self.assertIn('no signed `overview state:` comment', p.stderr)

    def test_state_older_than_the_window_is_not_found(self):
        p = self.run_tool([issue(7, [state('ANCIENT')] + ['chatter'] * 120)])
        self.assertEqual(p.returncode, 1)
        self.assertNotIn('ANCIENT', p.stdout)

    def test_no_and_two_standing_issues(self):
        p = self.run_tool([issue(7, [state('a')], labels=('other',))])
        self.assertEqual(p.returncode, 1)
        self.assertIn("no open issue labelled 'overview'", p.stderr)
        p = self.run_tool([issue(7, [state('a')]), issue(9, [state('b')])])
        self.assertEqual(p.returncode, 1)
        self.assertIn('#7, #9', p.stderr)
        p = self.run_tool([issue(7, [state('a')], state_='CLOSED'), issue(9, [state('b')])])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('#9', p.stdout)

    def test_issue_flag_skips_the_label_and_refuses_a_closed_issue(self):
        p = self.run_tool([issue(5, [state('given')], labels=())], '--issue', '5')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('given', p.stdout)
        self.assertFalse([c for c in self.log if c[:2] == ['issue', 'list']])
        p = self.run_tool([issue(5, [state('given')], state_='CLOSED')], '--issue', '5')
        self.assertEqual(p.returncode, 1)
        self.assertNotIn('given', p.stdout)

    def test_settings_label_and_shared_overview_repository(self):
        self.handoff('| overview label | `standing: overview` |\n'
                     '| overview repository | `them/home` |\n')
        p = self.run_tool([issue(3, [state('SHARED')], repo='them/home',
                                 labels=('standing: overview',))])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('them/home#3', p.stdout)
        self.assertIn('SHARED', p.stdout)
        self.assertFalse([c for c in self.log if c[:2] == ['repo', 'view']])

    def test_unknown_issue_and_malformed_answer(self):
        p = self.run_tool([issue(7, [state('a')])], '--issue', '8')
        self.assertEqual(p.returncode, 1)
        self.assertIn('no issue #8', p.stderr)
        p = self.run_tool([{'number': 'x', 'repo': 'me/repo', 'labels': ['overview'],
                            'state': 'OPEN', 'title': 'T', 'comments': []}])
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertNotIn('Traceback', p.stderr)

    def test_default_text_of_the_repository_row(self):
        self.handoff("| overview repository | this repository's own |\n")
        p = self.run_tool([issue(7, [state('HERE')])])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('HERE', p.stdout)

    def test_bad_repository_setting(self):
        self.handoff('| overview repository | `not a repo` |\n')
        p = self.run_tool([])
        self.assertEqual(p.returncode, 2)
        p = self.run_tool([], '-R', 'bad')
        self.assertEqual(p.returncode, 2)

    def test_github_unread_is_exit_3(self):
        p = self.run_tool([issue(7, [state('a')])], fail=True)
        self.assertEqual(p.returncode, 3)
        self.assertIn('GitHub was not read', p.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=1)
