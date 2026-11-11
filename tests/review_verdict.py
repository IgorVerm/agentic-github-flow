#!/usr/bin/env python3
"""Checks plugins/core/scripts/review_verdict.py: python3 tests/review_verdict.py.

The script owns the review comment's format: it writes the approval or the findings, posts them
with `gh pr comment`, and parses a comment for merge_pr.py. A stand-in `gh`
(AGENTIC_GITHUB_FLOW_GH) answers `pr view` from a fixture and records `pr comment` with the body
it was given. The cases: the approval it writes parses back to the full SHA it names; findings
never parse as an approval; it refuses a short or foreign SHA, a head that moved, a closed pull
request, an agent name that would break the signature, empty or non-UTF-8 findings; and it
exits 3 when it posted but cannot vouch for the head afterwards. That merge_pr.py
accepts what it writes is checked in tests/merge_pr.py. Offline: no network, no real gh.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SCRIPTS = os.path.join(ROOT, 'plugins', 'core', 'scripts')
TOOL = os.path.join(SCRIPTS, 'review_verdict.py')
sys.path.insert(0, SCRIPTS)  # for landing.py, which the script imports
_spec = importlib.util.spec_from_file_location('review_verdict_script', TOOL)
rv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rv)  # by path: this test file has the same name

ROBOT = '\N{ROBOT FACE}'
HEAD = 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678'
OTHER = 'ffffffffffffffffffffffffffffffffffffffff'

STUB = r'''import json, os, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
entry = list(a)
if a[:2] == ['pr', 'comment']:
    entry.append(sys.stdin.read())
s.setdefault('log', []).append(entry)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if a[:2] == ['pr', 'view']:
    views = s['views']
    print(json.dumps(views[min(s.get('n', 0), len(views) - 1)]))
    s['n'] = s.get('n', 0) + 1
    json.dump(s, open(os.environ['STUB_GH'], 'w'))
    sys.exit(0)
if a[:2] == ['pr', 'comment']:
    print('https://github.com/acme/tool/pull/7#issuecomment-1'); sys.exit(0)
sys.exit(3)
'''


class Format(unittest.TestCase):
    def test_approval_parses_back_to_its_sha(self):
        for note in ('', 'No findings. Efficient design: checked, O(changed files).'):
            body = rv.approval('Claude Code', HEAD, note)
            self.assertTrue(body.startswith(ROBOT + ' Claude Code (review): Approved ' + HEAD))
            self.assertEqual(rv.verdict(body), (HEAD, body[len(ROBOT + ' Claude Code (review): '):].strip()))
            self.assertEqual(rv.approved_sha(body), HEAD)

    def test_findings_never_approve(self):
        for text in ('1. The loop rescans every row.', 'Approved ' + HEAD,
                     ROBOT + ' Codex (review): Approved ' + HEAD):
            body = rv.findings('Codex', HEAD, text)
            self.assertIsNone(rv.approved_sha(body), body)
            self.assertIsNotNone(rv.verdict(body))

    def test_the_writer_refuses_what_would_not_parse(self):
        for agent in ('', '  ', 'Claude (Opus)', 'Claude\nCode', 'A)'):
            with self.subTest(agent=agent), self.assertRaises(ValueError):
                rv.approval(agent, HEAD)
        for sha in (HEAD[:10], HEAD[:39], HEAD + '0', HEAD.upper().replace('A', 'G'), ''):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                rv.approval('Codex', sha)
        with self.assertRaises(ValueError):
            rv.findings('Codex', HEAD, '   ')

    def test_only_the_signed_review_role_counts(self):
        self.assertIsNone(rv.verdict('Approved ' + HEAD))
        self.assertIsNone(rv.verdict(ROBOT + ' Claude Code (author): Approved ' + HEAD))
        self.assertEqual(rv.approved_sha(ROBOT + ' Codex (reviewer): Approved ' + HEAD), HEAD)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stub = os.path.join(self.tmp.name, 'gh_stub.py')
        self.state = os.path.join(self.tmp.name, 'state.json')
        with open(self.stub, 'w') as f:
            f.write(STUB)

    def view(self, **over):
        return dict({'number': 7, 'state': 'OPEN', 'headRefOid': HEAD}, **over)

    def run_tool(self, *args, views=None, stdin=None):
        with open(self.state, 'w') as f:
            json.dump({'views': views or [self.view()]}, f)
        env = dict(os.environ, STUB_GH=self.state,
                   AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, self.stub]))
        r = subprocess.run([sys.executable, TOOL, *args, '-C', self.tmp.name, '-R', 'acme/tool'],
                           capture_output=True,
                           text=True, env=env, input=stdin, encoding='utf-8')
        with open(self.state) as f:
            self.log = json.load(f).get('log', [])
        return r

    def posted(self):
        return [a for a in self.log if a[:2] == ['pr', 'comment']]

    def test_head_prints_the_head(self):
        r = self.run_tool('head', '7')
        self.assertEqual((r.returncode, r.stdout.strip()), (0, HEAD), r.stderr)

    def test_approve_posts_the_template(self):
        r = self.run_tool('approve', '7', '--sha', HEAD, '--agent', 'Claude Code',
                          '--note', 'No findings.')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [call] = self.posted()
        self.assertEqual(call[:6], ['pr', 'comment', '7', '-R', 'acme/tool', '--body-file'])
        self.assertEqual(call[6], '-')
        self.assertEqual(call[7], rv.approval('Claude Code', HEAD, 'No findings.'))

    def test_dry_run_prints_the_body_only(self):
        r = self.run_tool('approve', '7', '--sha', HEAD, '--agent', 'Codex', '--dry-run')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, rv.approval('Codex', HEAD))
        self.assertEqual(self.posted(), [])

    def test_refuses_a_sha_other_than_the_head(self):
        for sha in (OTHER, HEAD[:12]):
            with self.subTest(sha=sha):
                r = self.run_tool('approve', '7', '--sha', sha, '--agent', 'Codex')
                self.assertEqual(r.returncode, 1 if sha == OTHER else 2, r.stdout + r.stderr)
                self.assertEqual(self.posted(), [])

    def test_refuses_a_closed_pull_request(self):
        r = self.run_tool('approve', '7', '--sha', HEAD, '--agent', 'Codex',
                          views=[self.view(state='MERGED')])
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('MERGED', r.stderr)
        self.assertEqual(self.posted(), [])

    def test_head_moving_while_posting_is_reported(self):
        r = self.run_tool('approve', '7', '--sha', HEAD, '--agent', 'Codex',
                          views=[self.view(), self.view(headRefOid=OTHER)])
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('moved', r.stderr)
        [call] = self.posted()
        self.assertIn('Approved ' + HEAD, call[-1])

    def test_findings_from_a_file_or_stdin(self):
        path = os.path.join(self.tmp.name, 'findings.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('1. merge_pr.py:42 reads every comment twice.\n')
        r = self.run_tool('findings', '7', '--sha', HEAD, '--agent', 'Codex', '--body-file', path)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        [call] = self.posted()
        self.assertEqual(call[-1], rv.findings('Codex', HEAD,
                                              '1. merge_pr.py:42 reads every comment twice.'))
        self.assertIsNone(rv.approved_sha(call[-1]))
        r = self.run_tool('findings', '7', '--sha', HEAD, '--agent', 'Codex', '--body-file', '-',
                          stdin='2. a finding\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.posted()[0][-1], rv.findings('Codex', HEAD, '2. a finding'))
        r = self.run_tool('findings', '7', '--sha', HEAD, '--agent', 'Codex', '--body-file', '-',
                          stdin='\ufeff3. caf\u00e9 \u2192 na\u00efve\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.posted()[0][-1].endswith('3. caf\u00e9 \u2192 na\u00efve\n'))
        empty = self.run_tool('findings', '7', '--sha', HEAD, '--agent', 'Codex',
                              '--body-file', '-', stdin='\n')
        self.assertEqual(empty.returncode, 2)
        self.assertEqual(self.posted(), [])
        with open(path, 'wb') as f:
            f.write('1. a finding'.encode('utf-16'))  # PowerShell 5.1's `>`
        r = self.run_tool('findings', '7', '--sha', HEAD, '--agent', 'Codex', '--body-file', path)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('UTF-8', r.stderr)
        self.assertEqual(self.posted(), [])

    def test_check_reads_a_comment(self):
        path = os.path.join(self.tmp.name, 'c.md')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(rv.approval('Codex', HEAD))
        r = self.run_tool('check', '--body-file', path)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'approves ' + HEAD))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(ROBOT + ' Codex (review): LGTM, approved ' + HEAD)
        self.assertEqual(self.run_tool('check', '--body-file', path).returncode, 1)

    def test_usage(self):
        for args in ([], ['approve', '7', '--agent', 'Codex'], ['approve', '7', '--sha', HEAD],
                     ['approve', 'x', '--sha', HEAD, '--agent', 'Codex'], ['findings', '7',
                     '--sha', HEAD, '--agent', 'Codex'], ['nonsense']):
            with self.subTest(args=args):
                self.assertEqual(self.run_tool(*args).returncode, 2)
        self.assertEqual(self.posted(), [])
        self.assertEqual(self.run_tool('--help').returncode, 0)
        r = self.run_tool('approve', '7', '--sha', HEAD, '--agent', 'Codex', '--note', '-h',
                          '--dry-run')  # a value is never the help flag
        self.assertEqual((r.returncode, r.stdout), (0, rv.approval('Codex', HEAD, '-h')))

    def test_a_gh_that_hangs_or_fails_after_posting(self):
        r = self.run_tool('approve', '7', '--sha', HEAD, '--agent', 'Codex',
                          views=[self.view(), {'state': 'OPEN'}])
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('posted, but the head could not be read', r.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=1)
