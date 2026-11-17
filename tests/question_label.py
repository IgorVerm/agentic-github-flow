#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/question_label.py: python3 tests/question_label.py.

A scratch repository with HANDOFF.md on origin/main and an issue-chat branch; a stand-in `gh`
(AGENTIC_GITHUB_FLOW_GH) answers from a state file and logs every call, so a call the hook should
not make shows up. Each case is a way the question label could lie: a question asked while the
issue does not show it, a go-ahead or another repository stopped for nothing, a question blocked
by the hook's own failure, the label left on after the answer or taken off by a message that
answered nothing, a closed issue keeping it, an open one losing it. Offline; no network, no gh.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
HOOK = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'question_label.py')

STUB = r'''import json, os, sys
p = os.environ['STUB_GH']
s = json.load(open(p))
a = sys.argv[1:]
s['log'].append(a)
json.dump(s, open(p, 'w'))
if s.get('fail'):
    print('error connecting to api.github.com', file=sys.stderr); sys.exit(1)
if a[:2] == ['issue', 'view']:
    i = s['issues'][a[2]]
    print(json.dumps({'labels': [{'name': x} for x in i['labels']], 'state': i['state']})); sys.exit(0)
if a[:2] == ['issue', 'edit'] and a[3] == '--remove-label':
    s['issues'][a[2]]['labels'].remove(a[4]); json.dump(s, open(p, 'w')); sys.exit(0)
if a[:2] == ['pr', 'view']:
    r = s['prs'][a[2]]
    refs = [{'number': n, 'repository': {'name': name, 'owner': {'login': owner}}}
            for n, owner, name in ([c, 'Owner', 'Name'] if isinstance(c, int) else c
                                   for c in r['closing'])]
    print(json.dumps({'state': r['state'], 'closingIssuesReferences': refs})); sys.exit(0)
sys.exit(2)
'''

HANDOFF = '# Handoff\n\n## Issue chats settings\n\n| Setting | Value |\n|---|---|\n%s\n## Next\n'


def git(cwd, *args):
    subprocess.run(['git', '-C', cwd, *args], check=True, capture_output=True)


class QuestionLabel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.state = os.path.join(t, 'gh.json')
        stub = os.path.join(t, 'gh_stub.py')
        with open(stub, 'w') as f:
            f.write(STUB)
        self.markers = os.path.join(t, 'markers')
        self.env = dict(os.environ, STUB_GH=self.state,
                        AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, stub]),
                        AGENTIC_GITHUB_FLOW_QUESTION_STATE=self.markers)
        self.gh_state({})
        self.repo = self.make_repo('repo', '| ready label | `agent-ready` |')
        git(self.repo, 'checkout', '-q', '-b', 'agent/7-fix-it')

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
        git(path, 'remote', 'add', 'origin', 'https://github.com/owner/name.git')
        return path

    def gh_state(self, issues, prs=None, fail=False):
        with open(self.state, 'w') as f:
            json.dump({'issues': {str(k): {'labels': list(v[0]), 'state': v[1]}
                                  for k, v in issues.items()},
                       'prs': {str(k): v for k, v in (prs or {}).items()},
                       'log': [], 'fail': fail}, f)

    def gh(self):
        with open(self.state) as f:
            return json.load(f)

    def run_hook(self, event, cwd=None, session='s1', **extra):
        data = dict(hook_event_name=event, session_id=session, cwd=cwd or self.repo, **extra)
        p = subprocess.run([sys.executable, '-I', HOOK], input=json.dumps(data), env=self.env,
                           capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout, p.stderr

    def ask(self, **kw):
        return self.run_hook('PreToolUse', tool_name='AskUserQuestion',
                             tool_input={'questions': [{'question': 'Which?'}]}, **kw)

    def marker_exists(self, session='s1'):
        return os.path.exists(os.path.join(self.markers, session + '.json'))

    # asking
    def test_question_without_label_is_denied_with_the_command(self):
        self.gh_state({7: ([], 'OPEN')})
        code, _, err = self.ask()
        self.assertEqual(code, 2)
        self.assertIn('#7', err)
        self.assertIn('gh issue edit 7 --add-label needs-user', err)
        self.assertFalse(self.marker_exists())

    def test_question_with_label_passes_and_is_remembered(self):
        self.gh_state({7: (['needs-user'], 'OPEN')})
        self.assertEqual(self.ask()[0], 0)
        self.assertTrue(self.marker_exists())

    def test_blocked_wrap_up_counts_as_a_question(self):
        self.gh_state({7: ([], 'OPEN')})
        code, _, _ = self.run_hook('PreToolUse', tool_name='mcp__ccd_turn__wrap_up',
                                   tool_input={'recap': 'r', 'ask': 'A?', 'blocked': True})
        self.assertEqual(code, 2)

    def test_go_ahead_wrap_up_is_not_stopped(self):
        self.gh_state({7: ([], 'OPEN')})
        code, _, _ = self.run_hook('PreToolUse', tool_name='mcp__ccd_turn__wrap_up',
                                   tool_input={'recap': 'r', 'ask': 'Push?'})
        self.assertEqual(code, 0)
        self.assertEqual(self.gh()['log'], [])

    def test_settings_name_the_label(self):
        repo = self.make_repo('other', '| question label | `waiting` |')
        git(repo, 'checkout', '-q', '-b', 'agent/8-x')
        self.gh_state({8: ([], 'OPEN')})
        code, _, err = self.ask(cwd=repo)
        self.assertEqual(code, 2)
        self.assertIn('--add-label waiting', err)

    def test_repository_without_issue_chats_is_left_alone(self):
        repo = self.make_repo('plain', None)
        git(repo, 'checkout', '-q', '-b', 'agent/9-x')
        self.assertEqual(self.ask(cwd=repo)[0], 0)
        self.assertEqual(self.gh()['log'], [])

    def test_no_issue_branch_is_left_alone(self):
        git(self.repo, 'checkout', '-q', 'main')
        self.assertEqual(self.ask()[0], 0)
        self.assertEqual(self.gh()['log'], [])

    def test_numbered_branches_that_are_no_issue_chat_are_left_alone(self):
        self.gh_state({2025: ([], 'OPEN'), 1: ([], 'OPEN')})
        for branch in ('release/2025-01', 'hotfix/1-2-3', '2025-01-release'):
            git(self.repo, 'checkout', '-q', '-b', branch, 'main')
            self.assertEqual(self.ask()[0], 0, branch)
        self.assertEqual(self.gh()['log'], [])

    def test_numbered_primary_checkout_is_no_issue_chat(self):
        repo = self.make_repo('2024-site', '| ready label | `agent-ready` |')
        self.gh_state({2024: ([], 'OPEN')})
        self.assertEqual(self.ask(cwd=repo)[0], 0)
        self.assertEqual(self.gh()['log'], [])

    def test_linked_worktree_folder_names_the_issue(self):
        wt = os.path.join(self.tmp.name, '8-own-naming')
        git(self.repo, 'worktree', 'add', '-q', '-b', 'feature-x', wt, 'main')
        self.gh_state({8: ([], 'OPEN')})
        self.assertEqual(self.ask(cwd=wt)[0], 2)

    def test_malformed_input_never_blocks(self):
        self.gh_state({7: ([], 'OPEN')})
        code, _, err = self.run_hook('PreToolUse', tool_name='mcp__ccd_turn__wrap_up',
                                     tool_input='not a dict')
        self.assertEqual(code, 0)
        self.assertIn('hook failed', err)  # the hook's own exception, passed, not denied

    def test_untrusted_marker_folder_is_not_used(self):
        real = os.path.join(self.tmp.name, 'elsewhere')
        os.makedirs(real)
        os.symlink(real, self.markers)
        self.gh_state({7: (['needs-user'], 'OPEN')})
        self.assertEqual(self.ask()[0], 0)
        self.assertEqual(os.listdir(real), [])
        self.run_hook('UserPromptSubmit', prompt='Red')
        self.assertEqual(self.gh()['issues']['7']['labels'], ['needs-user'])

    def test_github_unreachable_never_blocks_a_question(self):
        self.gh_state({7: ([], 'OPEN')}, fail=True)
        self.assertEqual(self.ask()[0], 0)

    def test_subagent_call_is_left_alone(self):
        self.gh_state({7: ([], 'OPEN')})
        self.assertEqual(self.ask(agent_id='a1')[0], 0)

    # answering
    def test_answer_removes_the_label_and_asks_for_the_record(self):
        self.gh_state({7: (['needs-user', 'bug'], 'OPEN')})
        self.ask()
        code, out, _ = self.run_hook('UserPromptSubmit', prompt='Red')
        self.assertEqual(code, 0)
        self.assertEqual(self.gh()['issues']['7']['labels'], ['bug'])
        ctx = json.loads(out)['hookSpecificOutput']
        self.assertEqual(ctx['hookEventName'], 'UserPromptSubmit')
        self.assertIn('Record the answer on #7', ctx['additionalContext'])
        self.assertFalse(self.marker_exists())

    def test_tool_answer_removes_the_label(self):
        self.gh_state({7: (['needs-user'], 'OPEN')})
        self.ask()
        code, out, _ = self.run_hook('PostToolUse', tool_name='AskUserQuestion',
                                     tool_response={'answers': {'Which?': 'Red'}})
        self.assertEqual(code, 0)
        self.assertEqual(self.gh()['issues']['7']['labels'], [])
        self.assertEqual(json.loads(out)['hookSpecificOutput']['hookEventName'], 'PostToolUse')

    def test_message_without_a_question_keeps_the_label(self):
        self.gh_state({7: (['needs-user'], 'OPEN')})
        code, out, _ = self.run_hook('UserPromptSubmit', prompt='start brief for #7')
        self.assertEqual((code, out), (0, ''))
        self.assertEqual(self.gh()['log'], [])

    def test_another_sessions_question_is_not_answered_here(self):
        self.gh_state({7: (['needs-user'], 'OPEN')})
        self.ask(session='s1')
        self.run_hook('UserPromptSubmit', session='s2', prompt='hi')
        self.assertEqual(self.gh()['issues']['7']['labels'], ['needs-user'])

    # closing
    def bash(self, command, cwd=None):
        return self.run_hook('PostToolUse', cwd=cwd, tool_name='Bash',
                             tool_input={'command': command})

    def test_merge_removes_the_label_from_the_issues_it_closes(self):
        self.gh_state({3: (['needs-user'], 'OPEN'), 4: ([], 'OPEN')},
                      prs={12: {'state': 'MERGED', 'closing': [3, 4]}})
        elsewhere = self.tmp.name
        code, out, _ = self.bash('cd "%s" && python3 ~/x/scripts/merge_pr.py 12 --ready'
                                 % self.repo, cwd=elsewhere)
        self.assertEqual(code, 0)
        self.assertEqual(self.gh()['issues']['3']['labels'], [])
        self.assertIn('#3', json.loads(out)['hookSpecificOutput']['additionalContext'])

    def test_merge_leaves_another_repositorys_issue_number_alone(self):
        self.gh_state({3: (['needs-user'], 'OPEN')},
                      prs={12: {'state': 'MERGED', 'closing': [[3, 'someone', 'elsewhere']]}})
        self.bash('gh pr merge 12 --merge')
        self.assertEqual(self.gh()['issues']['3']['labels'], ['needs-user'])

    def test_issue_close_that_did_not_close_keeps_the_label(self):
        self.gh_state({5: (['needs-user'], 'OPEN')})
        self.bash('gh issue close 5')
        self.assertEqual(self.gh()['issues']['5']['labels'], ['needs-user'])

    def test_repo_flag_of_another_command_is_not_read(self):
        self.gh_state({5: (['needs-user'], 'CLOSED')})
        self.bash('grep -R src/lib . ; gh issue close 5')
        self.assertTrue(all('-R' not in call for call in self.gh()['log']))
        self.assertEqual(self.gh()['issues']['5']['labels'], [])

    def test_unmerged_pull_request_keeps_the_label(self):
        self.gh_state({3: (['needs-user'], 'OPEN')}, prs={12: {'state': 'OPEN', 'closing': [3]}})
        self.bash('gh pr merge 12 --auto --merge')
        self.assertEqual(self.gh()['issues']['3']['labels'], ['needs-user'])

    def test_issue_close_removes_the_label(self):
        self.gh_state({5: (['needs-user'], 'CLOSED')})
        self.bash('gh issue close 5 --comment done')
        self.assertEqual(self.gh()['issues']['5']['labels'], [])

    def test_repo_flag_is_passed_on(self):
        self.gh_state({5: (['needs-user'], 'CLOSED')})
        self.bash('gh issue close 5 -R owner/name')
        self.assertTrue(all(call[-2:] == ['-R', 'owner/name'] for call in self.gh()['log']))

    def test_other_commands_cost_no_call(self):
        self.gh_state({})
        self.assertEqual(self.bash('git status && gh issue view 5')[0], 0)
        self.assertEqual(self.gh()['log'], [])

    def test_bad_input_passes(self):
        p = subprocess.run([sys.executable, '-I', HOOK], input='not json', env=self.env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=1)
