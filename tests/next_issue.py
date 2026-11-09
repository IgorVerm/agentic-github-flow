#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/next_issue.py in a scratch repository: python3 tests/next_issue.py.

A stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) answers `issue list` from a state file, applying the
filters the tool passes (labels, `no:assignee`, `-label:`, `--assignee *`), so a filter the tool
forgets shows up as a wrong pick. The settings live in HANDOFF.md on the default branch, so each
case commits them. Each case is a way a chain could pick wrongly: the setting off changing the
normal order, a taken area not skipped, a free area not preferred, `priority: high` pushed
behind a free area, a fallback that never comes when every area is taken, an empty area held up
as free, a GitHub failure read as "nothing ready", an issue whose branch waits for the push
holding its area, a settings change on a branch counted before its merge, or a cut list of
assigned issues read as complete. Offline; no network, no real gh.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'next_issue.py')

STUB = r'''import json, os, shlex, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
s.setdefault('log', []).append(a)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if s.get('fail'):
    print('error connecting to api.github.com', file=sys.stderr); sys.exit(1)
if a[:2] == ['issue', 'view']:
    i = [i for i in s['issues'] if str(i['number']) == a[2]][0]
    print(json.dumps({'comments': [{'body': b} for b in i.get('comments', [])]})); sys.exit(0)
if a[:2] != ['issue', 'list']:
    sys.exit(2)
out = [dict(i, comments=None) for i in s['issues']]  # list gives no comments
for k, v in zip(a, a[1:]):
    if k == '--label':
        out = [i for i in out if v in [l['name'] for l in i['labels']]]
    if k == '--assignee' and v == '*':
        out = [i for i in out if i['assignees']]
    if k == '--search':
        for term in shlex.split(v):
            if term == 'no:assignee':
                out = [i for i in out if not i['assignees']]
            elif term.startswith('-label:'):
                out = [i for i in out if term[7:] not in [l['name'] for l in i['labels']]]
            else:
                sys.exit(3)
print(json.dumps(sorted(out, key=lambda i: -i['number'])))  # gh lists newest first
'''

SETTINGS = '''# Handoff

## Issue chats settings

| Setting | Value |
|---|---|
| ready label | `agent-ready` |
| area labels | `area:a`, `area:b`, `area:c`, `art` |
{spread}
## Next section

| spread over areas | no |
'''

ROBOT = '\N{ROBOT FACE}'


def issue(n, *labels, assigned=False, ready=True, comments=()):
    names = list(labels) + (['agent-ready'] if ready else [])
    return {'number': n, 'title': 'issue %d' % n, 'labels': [{'name': x} for x in names],
            'assignees': [{'login': 'someone'}] if assigned else [], 'comments': list(comments)}


CLAIM = ROBOT + ' Claude Code (issue chat): claimed for chat "#{0} · x" (local_1), branch b, worktree w'
READY = ROBOT + ' Claude Code (issue chat): **Ready to push:** branch `agent/2-x` at `abc1234`; checks green'
OPENED = ROBOT + ' Claude Code (issue chat): pull request opened: #40'
LANDED = ROBOT + ' Claude Code (issue chat): Landed on local main at `abc1234`: the fix; checks green'


class NextIssue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='next-issue-')
        root = os.path.realpath(self.tmp.name)
        self.repo = os.path.join(root, 'repo')
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                   GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t.invalid',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t.invalid')
        for key in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'):
            env.pop(key, None)
        self.genv = env
        subprocess.run(['git', 'init', '-q', '-b', 'main', self.repo], check=True, env=env)
        self.git('commit', '-q', '--allow-empty', '-m', 'init')
        stub = os.path.join(root, 'fake_gh.py')
        with open(stub, 'w') as f:
            f.write(STUB)
        self.state = os.path.join(root, 'gh.json')
        self.env = dict(env, STUB_GH=self.state,
                        AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, stub]))
        # area:a is taken (#2 assigned); area:b has ready work and is free; area:c is empty;
        # art is ready work outside the spread areas; #5 has no area; #9 is high in taken area:a.
        self.issues = [
            issue(2, 'area:a', assigned=True),
            issue(3, 'area:a'),
            issue(4, 'area:a', 'needs-spec'),
            issue(5),
            issue(6, 'art'),
            issue(7, 'area:b'),
            issue(8, 'area:b'),
            issue(9, 'area:a', 'priority: high'),
            issue(10, 'area:c', ready=False),
            issue(11, 'priority: critical'),
        ]
        self.write_state(self.issues)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(['git', '-C', self.repo, *args], check=True, capture_output=True,
                       env=self.genv)

    def write_state(self, issues, fail=False):
        with open(self.state, 'w') as f:
            json.dump({'issues': issues, 'fail': fail}, f)

    def settings(self, spread_row, text=None):
        """Commit the settings to main, where the tool reads them."""
        with open(os.path.join(self.repo, 'HANDOFF.md'), 'w', encoding='utf-8') as f:
            f.write(text if text is not None else
                    SETTINGS.format(spread=spread_row + '\n' if spread_row else ''))
        self.git('add', 'HANDOFF.md')
        self.git('commit', '-q', '-m', 'settings')

    def run_tool(self, *args):
        return subprocess.run([sys.executable, TOOL, *args], cwd=self.repo, env=self.env,
                              text=True, capture_output=True, encoding='utf-8')

    def picks(self, *args):
        r = self.run_tool(*args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [int(line.split()[0][1:]) for line in r.stdout.splitlines()], r

    def test_off_is_the_normal_order(self):
        for row in ('', '| spread over areas | no |'):
            self.settings(row)
            self.write_state(self.issues)  # a fresh call log
            r = self.run_tool()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stderr, '')
            self.assertEqual([int(x.split()[0][1:]) for x in r.stdout.splitlines()],
                             [11, 9, 3, 5, 6, 7, 8])
            self.assertEqual(r.stdout.splitlines()[0], '#11 issue 11')
            with open(self.state) as f:
                log = json.load(f)['log']
            self.assertEqual(len(log), 1)  # no taken query when the setting is off
            self.assertIn('no:assignee -label:needs-spec', log[0])

    def test_no_handoff_file_takes_the_defaults(self):
        order, _ = self.picks()
        self.assertEqual(order, [11, 9, 3, 5, 6, 7, 8])

    def test_spread_skips_a_taken_area_and_keeps_high_first(self):
        self.settings('| spread over areas | yes: `area:a`, `area:b`, `area:c`; not `art` |')
        order, r = self.picks()
        # art after the semicolon is a comment, not an area: #6 stays behind #3 and #5
        # critical, then high in the taken area:a, then free area:b, then the rest by number
        self.assertEqual(order, [11, 9, 7, 8, 3, 5, 6])
        self.assertIn('taken area:a; free with ready work area:b', r.stderr)

    def test_all_areas_taken_falls_back_to_the_normal_order(self):
        self.issues.append(issue(12, 'area:b', assigned=True))
        self.write_state(self.issues)
        self.settings('| spread over areas | yes: `area:a`, `area:b`, `area:c` |')
        order, r = self.picks()
        self.assertEqual(order, [11, 9, 3, 5, 6, 7, 8])
        self.assertIn('free with ready work -', r.stderr)

    def test_an_empty_area_is_skipped(self):
        # area:c is free but has no ready issue: the pick goes on to area:b, never waits on c
        self.settings('| spread over areas | yes: `area:c`, `area:b` |')
        order, r = self.picks()
        self.assertEqual(order[2], 7)
        self.assertIn('free with ready work area:b', r.stderr)
        self.assertNotIn('area:c', r.stderr.split('free with ready work')[1])

    def test_a_branch_ready_to_push_frees_its_area_until_a_new_claim(self):
        self.settings('| spread over areas | yes: `area:a`, `area:b` |')
        for handoff in (READY, OPENED, LANDED):
            # #2 in area:a: claim, then ready to push (or its pull request opened), then a
            # question: no chat works there any more, so area:a is free again
            self.issues[0]['comments'] = [CLAIM.format(2), handoff, ROBOT + ' Codex (review): a question']
            self.write_state(self.issues)
            order, r = self.picks()
            self.assertEqual(order, [11, 9, 3, 7, 8, 5, 6], handoff)
            self.assertIn('taken -; free with ready work area:a, area:b', r.stderr)
        # a claim newer than the hand-off takes the area again; a hand-off quoted mid-text
        # or unsigned is none
        self.issues[0]['comments'] += [CLAIM.format(2), 'Reviewer: ready to push: really?',
                                       ROBOT + ' Claude Code (issue chat): is it ready to push: no']
        self.write_state(self.issues)
        self.assertEqual(self.picks()[0], [11, 9, 7, 8, 3, 5, 6])

    def test_yes_without_labels_takes_the_area_labels_row(self):
        self.settings('| spread over areas | yes |')
        order, _ = self.picks()
        # art and area:b are free (area:a taken): #6, #7, #8 before #3 and #5
        self.assertEqual(order, [11, 9, 6, 7, 8, 3, 5])

    def test_area_and_no_spread_keep_the_normal_order(self):
        self.settings('| spread over areas | yes: `area:a`, `area:b` |')
        self.assertEqual(self.picks('--no-spread')[0], [11, 9, 3, 5, 6, 7, 8])
        self.assertEqual(self.picks('--area', 'area:a')[0], [9, 3])

    def test_settings_count_only_on_the_default_branch(self):
        self.settings('| spread over areas | yes: `area:a`, `area:b` |')
        # an unmerged change in the working tree (another label, the setting off) does not count
        with open(os.path.join(self.repo, 'HANDOFF.md'), 'w', encoding='utf-8') as f:
            f.write(SETTINGS.format(spread='| spread over areas | no |\n').replace(
                '`agent-ready`', '`other-label`'))
        order, r = self.picks()
        self.assertEqual(order, [11, 9, 7, 8, 3, 5, 6])
        # with an origin, origin/HEAD is the default branch, not local main
        origin = os.path.join(os.path.dirname(self.repo), 'origin.git')
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', origin], check=True,
                       capture_output=True, env=self.genv)
        self.git('remote', 'add', 'origin', origin)
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        self.git('remote', 'set-head', 'origin', 'main')
        self.git('commit', '-q', '-m', 'local only', '--', 'HANDOFF.md')
        self.assertEqual(self.picks()[0], [11, 9, 7, 8, 3, 5, 6])

    def test_other_ready_and_requirements_labels(self):
        self.settings('', text=SETTINGS.format(spread='').replace(
            '| ready label | `agent-ready` |',
            '| ready label | `go` |\n| requirements label | `open questions` |'))
        for i in self.issues:
            i['labels'] = [{'name': 'go' if x['name'] == 'agent-ready' else x['name']}
                           for x in i['labels']]
        self.issues[2]['labels'].append({'name': 'open questions'})
        self.write_state(self.issues)
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.state) as f:
            log = json.load(f)['log']
        self.assertIn('go', log[0])
        self.assertIn('no:assignee -label:"open questions"', log[0])

    def test_bad_setting_and_github_failure_refuse(self):
        self.settings('| spread over areas | maybe |')
        self.assertEqual(self.run_tool().returncode, 2)
        with open(os.path.join(self.repo, 'HANDOFF.md'), encoding='utf-8') as f:
            text = f.read().replace('`area:a`, `area:b`, `area:c`, `art`', 'none')
        self.settings('', text=text.replace('maybe', 'yes'))
        self.assertEqual(self.run_tool().returncode, 2)
        self.settings('| spread over areas | yes: `area:a` |')
        self.write_state(self.issues, fail=True)
        r = self.run_tool()
        self.assertEqual((r.returncode, r.stdout), (3, ''))
        self.assertIn('GitHub was not read', r.stderr)
        # 1000 assigned issues: the taken areas may be cut, so no order
        self.write_state(self.issues + [issue(100 + k, assigned=True, ready=False)
                                        for k in range(1000)])
        r = self.run_tool()
        self.assertEqual((r.returncode, r.stdout), (3, ''))
        self.assertIn('assigned issues', r.stderr)
        # no gh at all: not read, never "nothing ready"
        env = dict(self.env, AGENTIC_GITHUB_FLOW_GH='not json')
        r = subprocess.run([sys.executable, TOOL], cwd=self.repo, env=env, text=True,
                           capture_output=True)
        self.assertEqual((r.returncode, r.stdout), (3, ''))

    def test_outside_a_repository_is_a_usage_error(self):
        r = subprocess.run([sys.executable, TOOL, '-C', os.path.dirname(self.repo)],
                           env=self.env, text=True, capture_output=True)
        self.assertEqual(r.returncode, 2, r.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=1)
