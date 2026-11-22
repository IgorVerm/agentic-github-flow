#!/usr/bin/env python3
"""Checks plugins/issue-chats/scripts/context_limit.py and context-gate.sh: python3 tests/context_limit.py.

A scratch repository with HANDOFF.md on origin/main, an issue-chat branch and transcripts whose
newest API call carries a chosen context. Each case is a way the limit could fail: a note missing
past the limit or repeated on every call, a chat working on past twice the limit without the
user's word, the hand-over itself blocked, the user's answer not letting it go on, a grant that
never ends, a subagent running on, another repository or branch touched, the gate starting Python
where it should not, or the hook's own failure stopping work; and for the limit per label (#82):
a labelled issue kept at the default or an unlabelled one raised, a hand-over's successor losing
the label, a setting landed on local main or changed in a running session not counting, a
network call per tool call. Offline; a stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) logs its calls.
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
PER_LABEL = ('| context limit | `300k`; label `work: model`: `600k`; label `work: animation`: '
             '`600k` |')
GH = r'''import json, os, sys
with open(os.environ['GH_LOG'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\n')
labels = os.environ.get('GH_LABELS')
if labels is None:
    sys.exit(1)
print(json.dumps({'labels': [{'name': n} for n in json.loads(labels)]}))
'''


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
        self.records = os.path.join(self.tmp.name, 'records')
        self.gh_log = os.path.join(self.tmp.name, 'gh.log')
        gh = os.path.join(self.tmp.name, 'gh.py')
        with open(gh, 'w') as f:
            f.write(GH)
        self.env = dict(os.environ, AGENTIC_GITHUB_FLOW_CONTEXT_STATE=self.state,
                        AGENTIC_GITHUB_FLOW_LIMIT_RECORDS=self.records, GH_LOG=self.gh_log,
                        AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, gh]))
        self.env.pop('GH_LABELS', None)
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
        for cell, expect in (('about 150,000 tokens', '150k'), ('`200k`', '200k'),
                             ('0.25M', '250k'), ('120,000, 200k', '120k')):
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

    def message(self, kind, when='2999-01-01T00:00:00.000Z', text='ga door'):
        with open(self.transcript, 'a') as f:
            f.write(json.dumps({'type': 'user', 'timestamp': when, 'origin': {'kind': kind},
                                'message': {'role': 'user', 'content': text}}) + '\n')

    def test_the_users_typed_answer_lets_it_work_on_for_half_a_limit(self):
        self.at(610_000)
        self.assertEqual(self.pre('Edit')[0], 2)
        self.message('human')
        self.assertEqual(self.pre('Edit')[0], 0)
        self.assertIn('until 760k', self.post('Edit')[1])
        self.at(759_000)
        self.assertEqual(self.pre('Edit')[0], 0)
        self.at(761_000)
        self.assertEqual(self.pre('Edit')[0], 2)

    def test_notifications_and_other_sessions_grant_nothing(self):
        self.at(610_000)
        self.pre('Edit')
        for kind in ('task-notification', 'peer', None):
            self.message(kind, text='<task-notification>done</task-notification>')
            self.assertEqual(self.pre('Edit')[0], 2, kind)

    def test_a_message_before_the_stop_grants_nothing(self):
        self.at(400_000)
        self.message('human', when='2000-01-01T00:00:00.000Z')
        self.at(610_000)
        self.assertEqual(self.pre('Edit')[0], 2)  # the stop
        self.assertEqual(self.pre('Edit')[0], 2)  # the older message is no answer to it

    def test_tool_answer_also_grants(self):
        self.at(610_000)
        self.pre('Edit')
        self.assertIn('Follow that answer', self.post('AskUserQuestion')[1])
        self.assertEqual(self.pre('Edit')[0], 0)

    def test_compaction_clears_stop_and_grant(self):
        self.at(610_000)
        self.pre('Edit')
        self.post('AskUserQuestion')  # grant until 760k
        self.at(80_000)
        self.post()
        self.at(650_000)
        self.assertEqual(self.pre('Edit')[0], 2)

    def test_a_question_on_the_issue_runs_while_stopped(self):
        self.at(610_000)
        for command in ("gh issue comment 7 --body 'Continue? a; b | c `x`' && gh issue edit 7 --add-label needs-user",
                        "gh issue comment 7 --body \"$(cat <<'EOF'\nContinue past 600k?\n| a | b |\nEOF\n)\"",
                        "git log --oneline -3 2>&1 | tail -3"):
            self.assertEqual(self.pre('Bash', {'command': command})[0], 0, command)
        for command in ("git status\nmake", "git status $(make)", "git -c alias.x='!make' x",
                        "echo x > f.txt", "gh issue comment 7 --body \"`make`\""):
            self.assertEqual(self.pre('Bash', {'command': command})[0], 2, command)
        self.assertEqual(self.pre('Skill', {'skill': 'issue-handover'})[0], 0)

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
        self.assertEqual(self.pre('SubagentHandback', agent_id='ab1')[0], 0)  # its report goes
        self.assertEqual(self.pre('Edit')[0], 0)  # the main chat is still at 100k

    # the limit per label (#82)
    def per_label_repo(self, name='lab'):
        repo = self.make_repo(name, PER_LABEL)
        git(repo, 'checkout', '-q', '-b', 'agent/82-x')
        return repo

    def record(self, repo, labels, issue=82):
        sys.path.insert(0, SCRIPTS)
        import context_limit
        os.environ[context_limit.RECORDS_ENV] = self.records
        try:
            context_limit.record_labels(repo, issue, labels, 'test')
        finally:
            os.environ.pop(context_limit.RECORDS_ENV, None)

    def gh_calls(self):
        if not os.path.exists(self.gh_log):
            return 0
        with open(self.gh_log) as f:
            return len(f.read().splitlines())

    def limit_in_state(self, session):
        with open(os.path.join(self.state, session + '.json')) as f:
            return json.load(f)['limit']

    def test_the_cell_form_per_label(self):
        sys.path.insert(0, SCRIPTS)
        from context_limit import limit_of, limits_in
        default, per = limits_in(PER_LABEL.split('|')[2])
        self.assertEqual((default, per), (300_000, {'work: model': 600_000,
                                                    'work: animation': 600_000}))
        self.assertEqual(limit_of(default, per, ['bug', 'Work: Model']), 600_000)
        self.assertEqual(limit_of(default, per, ['bug']), 300_000)
        self.assertEqual(limits_in("`250k`; label `big`: `1M`; label `odd`: `x`"),
                         (250_000, {'big': 1_000_000}))
        self.assertEqual(limits_in("label `big`: `500k`"), (300_000, {'big': 500_000}))
        self.assertEqual(limits_in("`300k`; labels `work: model`, `work: animation`: `600k`"),
                         (300_000, {'work: model': 600_000, 'work: animation': 600_000}))
        self.assertEqual(limits_in("`300k`; label `a` and `b`: `400k`; label `c`: `0.5M`"),
                         (300_000, {'a': 400_000, 'b': 400_000, 'c': 500_000}))

    def test_git_failing_falls_back_to_the_default(self):
        sys.path.insert(0, SCRIPTS)
        from context_limit import git_out, settings_now
        self.assertIsNone(git_out(os.path.join(self.tmp.name, 'nowhere'), 'status'))
        self.assertEqual(settings_now(os.path.join(self.tmp.name, 'nowhere'), {}), (300_000, {}))

    def test_a_labelled_issue_gets_its_label_limit_from_the_record(self):
        repo = self.per_label_repo()
        self.record(repo, ['work: model', 'agent-ready'])
        self.at(400_000)
        self.assertEqual(self.post(cwd=repo, session='lab1'), (0, '', ''))
        self.assertEqual(self.limit_in_state('lab1'), 600_000)
        self.at(610_000)
        self.assertIn('past the limit (600k)', self.post(cwd=repo, session='lab1')[1])
        self.assertEqual(self.pre('Edit', cwd=repo, session='lab1')[0], 0)
        self.at(1_210_000)
        self.assertEqual(self.pre('Edit', cwd=repo, session='lab1')[0], 2)
        self.assertEqual(self.gh_calls(), 0)

    def test_an_unlabelled_issue_keeps_the_default(self):
        repo = self.per_label_repo()
        self.record(repo, ['agent-ready'])
        self.at(310_000)
        self.assertIn('past the limit (300k)', self.post(cwd=repo, session='un1')[1])
        self.assertEqual(self.gh_calls(), 0)

    def test_the_successor_of_a_hand_over_keeps_the_label_limit(self):
        repo = self.per_label_repo()
        self.record(repo, ['work: animation'])
        self.at(400_000)
        self.post(cwd=repo, session='old')
        self.assertEqual(self.limit_in_state('old'), 600_000)
        self.post(cwd=repo, session='successor')  # a new session id in the same worktree
        self.assertEqual(self.limit_in_state('successor'), 600_000)
        self.assertEqual(self.gh_calls(), 0)

    def test_a_chat_started_otherwise_reads_its_labels_once(self):
        repo = self.per_label_repo()
        self.env['GH_LABELS'] = json.dumps(['work: model'])
        self.at(400_000)
        for _ in range(3):
            self.post(cwd=repo, session='other1')
            self.pre('Edit', cwd=repo, session='other1')
        self.assertEqual(self.limit_in_state('other1'), 600_000)
        self.assertEqual(self.gh_calls(), 1)
        self.post(cwd=repo, session='other2')  # the record serves the next session
        self.assertEqual(self.gh_calls(), 1)
        self.assertEqual(self.limit_in_state('other2'), 600_000)

    def test_no_answer_from_github_gives_the_default_and_no_retry_per_call(self):
        repo = self.per_label_repo()
        self.at(310_000)
        self.assertIn('limit (300k)', self.post(cwd=repo, session='nogh')[1])
        self.post(cwd=repo, session='nogh')
        self.assertEqual(self.gh_calls(), 1)

    def test_no_label_rows_no_labels_read(self):
        self.at(310_000)
        self.post(session='plain1')
        self.assertEqual(self.gh_calls(), 0)

    def test_a_setting_landed_on_local_main_counts_before_the_push(self):
        repo = self.make_repo('lm', '| context limit | `300k` |')
        git(repo, 'checkout', '-q', '-b', 'agent/5-x')
        self.at(350_000)
        self.assertIn('limit (300k)', self.post(cwd=repo, session='lm1')[1])
        git(repo, 'checkout', '-q', 'main')
        with open(os.path.join(repo, 'HANDOFF.md'), 'w') as f:
            f.write(HANDOFF % '| context limit | `400k` |')
        git(repo, 'commit', '-q', '-am', 'raise the limit')  # landed on local main, not pushed
        git(repo, 'checkout', '-q', 'agent/5-x')
        self.assertEqual(self.post(cwd=repo, session='lm1')[1], '')
        self.assertEqual(self.limit_in_state('lm1'), 400_000)

    def test_local_main_behind_origin_does_not_count(self):
        repo = self.make_repo('behind', '| context limit | `300k` |')
        git(repo, 'checkout', '-q', '-b', 'agent/5-x')
        with open(os.path.join(repo, 'HANDOFF.md'), 'w') as f:
            f.write(HANDOFF % '| context limit | `200k` |')
        git(repo, 'commit', '-q', '-am', 'fetched from origin')
        git(repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')  # origin ahead of local main
        self.at(250_000)
        self.assertIn('limit (200k)', self.post(cwd=repo, session='bh')[1])

    def test_a_changed_setting_counts_in_a_running_session(self):
        repo = self.make_repo('chg', '| context limit | `300k` |')
        git(repo, 'checkout', '-q', '-b', 'agent/5-x')
        self.at(250_000)
        self.assertEqual(self.post(cwd=repo, session='chg1')[1], '')
        git(repo, 'checkout', '-q', 'main')
        with open(os.path.join(repo, 'HANDOFF.md'), 'w') as f:
            f.write(HANDOFF % '| context limit | `200k` |')
        git(repo, 'commit', '-q', '-am', 'lower the limit')
        git(repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')  # fetched
        git(repo, 'checkout', '-q', 'agent/5-x')
        self.assertIn('limit (200k)', self.post(cwd=repo, session='chg1')[1])

    def test_a_session_begun_under_the_previous_hook_is_still_limited(self):
        os.makedirs(self.state, exist_ok=True)
        with open(os.path.join(self.state, 'oldsess.json'), 'w') as f:
            json.dump({'issue': 7, 'limit': 300_000}, f)  # the state the hook of #77 wrote
        self.at(310_000)
        self.assertIn('past the limit (300k)', self.post(session='oldsess')[1])

    def test_a_label_limit_set_in_a_running_session_counts(self):
        repo = self.make_repo('later', '| context limit | `300k` |')
        git(repo, 'checkout', '-q', '-b', 'agent/82-x')
        self.record(repo, ['work: model'])
        self.at(400_000)
        self.assertIn('limit (300k)', self.post(cwd=repo, session='lt')[1])
        git(repo, 'checkout', '-q', 'main')
        with open(os.path.join(repo, 'HANDOFF.md'), 'w') as f:
            f.write(HANDOFF % PER_LABEL)
        git(repo, 'commit', '-q', '-am', 'per label')
        git(repo, 'update-ref', 'refs/remotes/origin/main', 'HEAD')
        git(repo, 'checkout', '-q', 'agent/82-x')
        self.post(cwd=repo, session='lt')
        self.assertEqual(self.limit_in_state('lt'), 600_000)
        self.assertEqual(self.gh_calls(), 0)

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
