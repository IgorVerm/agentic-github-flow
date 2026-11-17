#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/context_limit.py and context-gate.sh: python3 tests/context_limit.py.

A scratch repository with HANDOFF.md on origin/main, an issue-chat branch and transcripts whose
newest API call carries a chosen context. Each case is a way the limit could fail: a note missing
past the limit or repeated on every call, a chat working on past twice the limit without the
user's word, the hand-over itself blocked, the user's answer not letting it go on, a grant that
never ends, a subagent running on, another repository or branch touched, the gate starting Python
where it should not, or the hook's own failure stopping work. Offline; no network, no gh.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SCRIPTS = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts')
HOOK = os.path.join(SCRIPTS, 'context_limit.py')
GATE = os.path.join(SCRIPTS, 'context-gate.sh')
HANDOFF = '# Handoff\n\n## Issue chats settings\n\n| Setting | Value |\n|---|---|\n%s\n## Next\n'


def git(cwd, *args):
    subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True)


def call(ctx, side=False):
    return json.dumps({'type': 'assistant', 'isSidechain': side, 'message': {
        'role': 'assistant', 'content': [{'type': 'text', 'text': 'x'}],
        'usage': {'input_tokens': 3, 'cache_creation_input_tokens': 1000,
                  'cache_read_input_tokens': ctx - 1003, 'output_tokens': 10}}}) + '\n'


class ContextLimit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, 'state')
        self.env = dict(os.environ, AGENTIC_GITHUB_FLOW_CONTEXT_STATE=self.state)
        self.repo = self.make_repo('repo', '| ready label | `agent-ready` |')
        git(self.repo, 'checkout', '-q', '-b', 'agent/7-fix-it')
        self.transcript = os.path.join(self.tmp.name, 'sess.jsonl')
        self.at(100_000)

    def tearDown(self):
        self.tmp.cleanup()

    def make_repo(self, name, rows):
        path = os.path.join(self.tmp.name, name)
        os.makedirs(path)
        git(path, 'init', '-q', '-b', 'main')
        git(path, 'config', 'user.email', 'test@example.com')
        git(path, 'config', 'user.name', 'Test')
        with open(os.path.join(path, 'HANDOFF.md'), 'w') as f:
            f.write(HANDOFF % rows if rows is not None else '# Handoff\n')
        git(path, 'add', 'HANDOFF.md')
        git(path, 'commit', '-q', '-m', 'handoff')
        git(path, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
        return path

    def at(self, ctx, path=None, side=False):
        with open(path or self.transcript, 'a') as f:
            f.write('{"type":"user","message":{"role":"user","content":"hi"}}\n')
            f.write(call(ctx, side))

    def run_hook(self, event, tool=None, args=None, session='s1', cwd=None, **extra):
        data = dict(hook_event_name=event, session_id=session, cwd=cwd or self.repo,
                    transcript_path=self.transcript, **extra)
        if tool:
            data['tool_name'] = tool
            data['tool_input'] = args or {}
        p = subprocess.run([sys.executable, '-I', HOOK], input=json.dumps(data), env=self.env,
                           capture_output=True, text=True, encoding='utf-8', timeout=60)
        ctx = json.loads(p.stdout)['hookSpecificOutput']['additionalContext'] if p.stdout else ''
        return p.returncode, ctx, p.stderr

    def post(self, tool='Read', **kw):
        return self.run_hook('PostToolUse', tool, {}, **kw)

    def pre(self, tool='Edit', args=None, **kw):
        return self.run_hook('PreToolUse', tool, args or {}, **kw)

    # past the limit: notes
    def test_below_the_limit_nothing_happens(self):
        self.assertEqual(self.post(), (0, '', ''))
        self.assertEqual(self.pre()[0], 0)

    def test_note_past_the_limit_then_per_25k(self):
        self.at(310_000)
        code, ctx, _ = self.post()
        self.assertIn('past the limit (300k)', ctx)
        self.assertIn('close to a solution', ctx)
        self.at(320_000)
        self.assertEqual(self.post()[1], '')
        self.at(336_000)
        self.assertIn('336k', self.post()[1])

    def test_compaction_below_the_limit_resets_the_notes(self):
        self.at(310_000)
        self.post()
        self.at(80_000)
        self.post()
        self.at(311_000)
        self.assertIn('311k', self.post()[1])

    def test_settings_set_the_limit(self):
        for cell, expect in (('about 150,000 tokens', '150k'), ('`200k`', '200k')):
            repo = self.make_repo('r' + expect, '| context limit | %s |' % cell)
            git(repo, 'checkout', '-q', '-b', 'agent/8-x')
            self.at(250_000)
            self.assertIn('limit (%s)' % expect, self.post(cwd=repo, session='s-' + expect)[1])

    # past twice the limit: the user decides
    def test_work_past_twice_the_limit_is_refused(self):
        self.at(610_000)
        code, _, err = self.pre('Edit')
        self.assertEqual(code, 2)
        self.assertIn('issue #7', err)
        self.assertIn('AskUserQuestion', err)

    def test_asking_and_handing_over_still_run(self):
        self.at(610_000)
        for tool, args in (('AskUserQuestion', {}), ('mcp__ccd_turn__wrap_up', {'blocked': True}),
                           ('mcp__ccd_session__start_session', {}), ('ToolSearch', {}),
                           ('Bash', {'command': 'git commit -m x -- a.py && gh issue comment 7 --body y | tail -1'}),
                           ('Bash', {'command': 'python3 ~/.agentic-github-flow/plugins/core/scripts/push_branch.py --grant g'})):
            self.assertEqual(self.pre(tool, args)[0], 0, tool)
        for tool, args in (('Bash', {'command': 'python3 build.py'}), ('Bash', {'command': 'git status; make'}),
                           ('Write', {}), ('Agent', {}), ('Read', {})):
            self.assertEqual(self.pre(tool, args)[0], 2, (tool, args))

    def test_the_users_answer_lets_it_work_on_for_half_a_limit(self):
        self.at(610_000)
        self.pre('Edit')
        code, ctx, _ = self.run_hook('UserPromptSubmit', prompt='ga door')
        self.assertIn('until 760k', ctx)
        self.assertEqual(self.pre('Edit')[0], 0)
        self.at(759_000)
        self.assertEqual(self.pre('Edit')[0], 0)
        self.at(761_000)
        self.assertEqual(self.pre('Edit')[0], 2)

    def test_tool_answer_also_grants(self):
        self.at(610_000)
        self.pre('Edit')
        self.assertIn('Follow that answer', self.post('AskUserQuestion')[1])
        self.assertEqual(self.pre('Edit')[0], 0)

    def test_a_message_before_any_stop_grants_nothing(self):
        self.at(400_000)
        self.assertEqual(self.run_hook('UserPromptSubmit', prompt='hi')[1], '')
        self.at(610_000)
        self.assertEqual(self.pre('Edit')[0], 2)

    # subagents
    def test_subagent_gets_the_same_limit_and_no_way_on(self):
        sub = os.path.join(self.tmp.name, 'sess', 'subagents', 'agent-ab1.jsonl')
        os.makedirs(os.path.dirname(sub))
        self.at(310_000, sub, side=True)
        self.assertIn('report back now', self.post(agent_id='ab1')[1])
        self.at(610_000, sub, side=True)
        code, _, err = self.pre('Bash', {'command': 'git status'}, agent_id='ab1')
        self.assertEqual(code, 2)
        self.assertIn('report', err)
        self.assertEqual(self.pre('Edit')[0], 0)  # the main chat is still at 100k

    # where it does nothing
    def test_other_branch_or_repository_is_left_alone(self):
        self.at(700_000)
        git(self.repo, 'checkout', '-q', '-b', 'release/2025-01', 'main')
        self.assertEqual(self.pre('Edit', session='s2')[0], 0)
        plain = self.make_repo('plain', None)
        git(plain, 'checkout', '-q', '-b', 'agent/9-x')
        self.assertEqual(self.pre('Edit', cwd=plain, session='s3')[0], 0)

    def test_newest_call_found_behind_a_large_tool_result(self):
        self.at(610_000)
        with open(self.transcript, 'a') as f:
            f.write(json.dumps({'type': 'user', 'message': {'content': 'x' * 700_000}}) + '\n')
        self.assertEqual(self.pre('Edit')[0], 2)

    def test_own_failure_never_stops_work(self):
        for raw in ('not json', json.dumps({'hook_event_name': 'PreToolUse', 'tool_name': 'Edit',
                                            'cwd': self.repo, 'transcript_path': '/nonexistent'})):
            p = subprocess.run([sys.executable, '-I', HOOK], input=raw, env=self.env,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0)

    # the shell gate
    def gate(self, project):
        env = dict(self.env, CLAUDE_PROJECT_DIR=project)
        data = json.dumps(dict(hook_event_name='PreToolUse', tool_name='Edit', tool_input={},
                               session_id='g1', cwd=project, transcript_path=self.transcript))
        return subprocess.run(['sh', GATE], input=data, env=env, capture_output=True, text=True,
                              timeout=60)

    def test_gate_passes_issue_branches_to_the_hook(self):
        self.at(610_000)
        self.assertEqual(self.gate(self.repo).returncode, 2)

    def test_gate_stops_elsewhere_without_python(self):
        self.at(610_000)
        git(self.repo, 'checkout', '-q', 'main')
        self.assertEqual(self.gate(self.repo).returncode, 0)
        self.assertFalse(os.path.exists(self.state))


if __name__ == '__main__':
    unittest.main(verbosity=1)
