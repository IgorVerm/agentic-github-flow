#!/usr/bin/env python3
"""Checks plugins/core/scripts/merge_pr.py in a throwaway repository: python3 tests/merge_pr.py.

A bare origin on disk holds the base branch and the pull request's head at refs/pull/7/head; a
stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) answers `pr view` from a fixture and records `pr merge`.
A folder remote is not GitHub, so landing.py decides pull request unless HANDOFF.md says local
main. Each case is a way an agent could merge what it may not: automatic merging not switched
on in HANDOFF.md (whatever --grant says), local-main mode, a draft without --ready, a merge state other than CLEAN, a failed, pending or missing check, no review, a review
that does not approve or was edited after posting, an approval of an older commit followed by a commit of the author or by
a merge with a conflict resolved by hand, no overlap result, a path that merges only on the
user's word (built in, or named in HANDOFF.md), and a base other than the landing branch. And the
cases that may merge: a review of the head, and of a commit followed only by a clean merge of
the base; with --ready a draft is marked ready first and merged only once GitHub calls it CLEAN. The review comment that review_verdict.py writes is accepted, and hand-written
variants that deviate from it are refused. Offline: no network, no real gh.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'merge_pr.py')
VERDICT = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'review_verdict.py')
ROBOT = '\N{ROBOT FACE}'
SWITCH = '## Standing permissions\n\n| Permission | Value |\n|---|---|\n| automatic merge | `on` |\n'


def handoff(*sections):
    """HANDOFF.md with automatic merging switched on, and the sections given."""
    return '# Handoff\n\n' + '\n'.join(sections + (SWITCH,))

STUB = r'''import json, os, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
s.setdefault('log', []).append(a)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if a[:2] == ['pr', 'view']:
    print(json.dumps(s['pr'])); sys.exit(0)
if a[:2] == ['pr', 'merge']:
    sys.exit(0)
if a[:2] == ['pr', 'ready']:
    s['pr'].update(isDraft=False, mergeStateStatus=s.get('after_ready', 'CLEAN'))
    json.dump(s, open(os.environ['STUB_GH'], 'w'))
    sys.exit(0)
if a[0] == 'api':
    status, body = s['api'].get(a[1], [404, {'message': 'Not Found'}])
    print(json.dumps(body))
    if status != 200:
        print('gh: %s (HTTP %d)' % (body.get('message', ''), status), file=sys.stderr); sys.exit(1)
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
        self.write('HANDOFF.md', handoff())
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
              'comments': [self.comment('Approved %s: no findings' % self.head[:10])],
              'reviews': [],
              'statusCheckRollup': [
                  {'__typename': 'CheckRun', 'name': 'test (%s)' % os_name,
                   'status': 'COMPLETED', 'conclusion': 'SUCCESS'}
                  for os_name in ('ubuntu', 'macos', 'windows')]}
        pr.update(over)
        return pr

    def comment(self, text, role='review', login='me', when='2026-11-09T10:00:00Z'):
        return {'createdAt': when, 'author': {'login': login}, 'includesCreatedEdit': False,
                'body': ROBOT + ' Claude Code (%s): %s' % (role, text)}

    def run_tool(self, pr, *args, grant=None, api=None, after_ready=None):
        rules = [{'type': 'required_status_checks', 'parameters': {'required_status_checks': [
            {'context': 'test (%s)' % o} for o in ('ubuntu', 'macos', 'windows')]}}]
        answers = {'user': [200, {'login': 'me'}],
                   'repos/acme/tool/rules/branches/main': [200, rules]}
        answers.update(api or {})
        with open(self.state, 'w') as f:
            json.dump({'pr': pr, 'api': answers, 'after_ready': after_ready or 'CLEAN'}, f)
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

    def assertMerged(self, pr, *args, **kw):
        r = self.run_tool(pr, *args, **kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def assertRefused(self, pr, text, *args, **kw):
        r = self.run_tool(pr, *args, **kw)
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
        self.assertEqual(self.run_tool(self.pr(), '--grant', '--dry-run').returncode, 2)
        self.assertEqual(self.merged(), [])
        self.assertEqual(self.run_tool(self.pr(), '--method', 'rebase').returncode, 2)

    def test_the_switch_in_handoff_decides_not_a_grant(self):
        for text in ('# Handoff\n',
                     '# Handoff\n\n## Standing permissions\n\nNone.\n',
                     SWITCH.replace('`on`', '`off`'),
                     '# Handoff\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n'
                     '| automatic merge | on |\n'):
            with self.subTest(text=text):  # the task branch keeps the switch; main decides
                self.git('switch', '-q', 'main')
                self.write('HANDOFF.md', text)
                self.git('commit', '-q', '-am', 'no switch')
                self.git('push', '-q', 'origin', 'main')
                self.git('switch', '-q', 'agent/7-x')
                self.assertRefused(self.pr(), 'not switched on', grant='agent-rules overlay')

    def test_ready_marks_a_draft_only_when_everything_else_holds(self):
        draft = self.pr(isDraft=True, mergeStateStatus='DRAFT')
        r = self.assertMerged(draft, '--ready')
        self.assertIn(['pr', 'ready', '7', '-R', 'acme/tool'], self.log)
        self.assertEqual(len(self.merged()), 1)
        r = self.assertMerged(draft, '--ready', '--dry-run')
        self.assertIn('would mark ready and merge', r.stdout)
        self.assertNotIn(['pr', 'ready', '7', '-R', 'acme/tool'], self.log)
        # anything else failing: never marked ready
        self.assertRefused(dict(draft, comments=[]), 'no signed review', '--ready')
        self.assertNotIn(['pr', 'ready', '7', '-R', 'acme/tool'], self.log)
        # GitHub blocks it once ready: reported, not merged
        self.assertRefused(draft, 'merge state BLOCKED', '--ready', after_ready='BLOCKED')
        self.assertIn(['pr', 'ready', '7', '-R', 'acme/tool'], self.log)

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
        self.assertRefused(self.pr(statusCheckRollup=[]), 'not passed on the head')
        skipped = runs[:2] + [dict(runs[2], conclusion='SKIPPED')]
        self.assertRefused(self.pr(statusCheckRollup=skipped), 'test (windows)')
        none = {'repos/acme/tool/rules/branches/main': [200, []]}
        self.assertRefused(self.pr(), 'no required checks', api=none)
        extra = runs + [{'__typename': 'CheckRun', 'name': 'lint', 'status': 'COMPLETED',
                         'conclusion': 'SKIPPED'}]
        self.assertMerged(self.pr(statusCheckRollup=extra), '--dry-run')

    def test_review(self):
        self.assertRefused(self.pr(comments=[]), 'no signed review')
        unsigned = [{'createdAt': '1', 'author': {'login': 'me'},
                     'body': 'Approved %s' % self.head}]
        self.assertRefused(self.pr(comments=unsigned), 'no signed review')
        later = self.pr()['comments'] + [self.comment('two findings, see below',
                                                      when='2026-11-09T11:00:00Z')]
        self.assertRefused(self.pr(comments=later), 'does not approve')
        approve = self.pr()['comments'][0]
        as_review = self.pr(comments=[], reviews=[{'submittedAt': '2026-11-09T10:00:00Z',
                                                   'state': 'COMMENTED', 'author': {'login': 'me'},
                                                   'body': approve['body']}])
        self.assertRefused(as_review, 'never approves')  # gh cannot tell if it was edited
        # a stranger's approval, a self-review, a pending review and a negative text never count
        self.assertRefused(self.pr(comments=[self.comment('Approved %s' % self.head,
                                                          login='stranger')]), 'no signed review')
        self.assertRefused(self.pr(comments=[self.comment('Approved %s' % self.head,
                                                          role='author, self-review')]),
                           'no signed review')
        pending = self.pr(comments=[], reviews=[dict(as_review['reviews'][0], state='PENDING',
                                                     submittedAt=None)])
        self.assertRefused(pending, 'no signed review')
        self.assertRefused(self.pr(comments=[self.comment('Approved? No. %s is broken'
                                                          % self.head[:10])]), 'does not approve')
        # a later "changes requested" review, with or without a signed body
        changes = self.pr(reviews=[{'submittedAt': '2026-11-09T12:00:00Z', 'author':
                                    {'login': 'me'}, 'state': 'CHANGES_REQUESTED', 'body': ''}])
        self.assertRefused(changes, 'does not approve')
        self.assertRefused(self.pr(reviewDecision='CHANGES_REQUESTED'), 'requests changes')

    def verdict_script(self, *args):
        """The comment review_verdict.py would post, from its --dry-run, with the same stub."""
        with open(self.state, 'w') as f:
            json.dump({'pr': self.pr(), 'api': {}}, f)
        env = dict(os.environ, STUB_GH=self.state,
                   AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, self.stub]))
        r = subprocess.run([sys.executable, VERDICT, *args, '--dry-run', '-C', self.repo,
                            '-R', 'acme/tool'], capture_output=True, text=True, env=env,
                           encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return {'createdAt': '2026-11-09T10:00:00Z', 'author': {'login': 'me'}, 'body': r.stdout,
                'includesCreatedEdit': False}

    def test_the_review_skills_comment_is_accepted(self):
        approval = self.verdict_script('approve', '7', '--sha', self.head, '--agent',
                                       'Claude Code', '--note', 'No findings.')
        self.assertMerged(self.pr(comments=[approval]), '--dry-run')
        path = os.path.join(self.tmp.name, 'findings.md')
        with open(path, 'w') as f:
            f.write('Approved %s\n1. a finding\n' % self.head)
        findings = self.verdict_script('findings', '7', '--sha', self.head, '--agent', 'Codex',
                                       '--body-file', path)
        later = dict(findings, createdAt='2026-11-09T11:00:00Z')
        self.assertRefused(self.pr(comments=[approval, later]), 'does not approve')

    def test_hand_written_variants_are_refused(self):
        sha = self.head
        for body in ('Approved %s' % sha,                                     # unsigned
                     ROBOT + ' Claude Code (review) Approved %s' % sha,        # no colon
                     ROBOT + ' Claude Code (review): Approve %s' % sha,        # not "Approved"
                     ROBOT + ' Claude Code (review): LGTM, approved %s' % sha,
                     ROBOT + ' Claude Code (review): Approved, %s' % sha,
                     ROBOT + ' Claude Code (review): Approved %s' % sha[:6],   # too short
                     ROBOT + ' Claude Code (review): Approved %sx' % sha,      # not a SHA
                     ROBOT + ' Claude Code (review): Approved head',
                     ROBOT + ' Claude Code (author): Approved %s' % sha,       # not the reviewer
                     ROBOT + ' Claude Code (review): Approved %s' % ('0' * 40)):  # unknown commit
            with self.subTest(body=body):
                comment = {'createdAt': '2026-11-09T10:00:00Z', 'author': {'login': 'me'},
                           'body': body, 'includesCreatedEdit': False}
                r = self.run_tool(self.pr(comments=[comment]))
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertRegex(r.stdout, 'no signed review|does not approve|not in this '
                                           'repository')
                self.assertEqual(self.merged(), [])

    def test_an_edited_review_never_approves(self):
        edited = dict(self.comment('Approved %s' % self.head), includesCreatedEdit=True)
        self.assertRefused(self.pr(comments=[edited]), 'edited after it was posted')
        older = self.comment('Approved %s' % self.head, when='2026-11-09T09:00:00Z')
        self.assertRefused(self.pr(comments=[older, edited]), 'edited after it was posted')
        unknown = dict(edited)
        del unknown['includesCreatedEdit']  # a gh that does not report it: counts as edited
        self.assertRefused(self.pr(comments=[unknown]), 'edited after it was posted')
        newer = self.comment('Approved %s' % self.head, when='2026-11-09T11:00:00Z')
        self.assertMerged(self.pr(comments=[edited, newer]), '--dry-run')

    def test_a_ref_named_like_the_prefix_does_not_count(self):
        reviewed = self.head
        self.head = self.change('skills.md', 'unreviewed\n')
        self.git('tag', reviewed[:10], self.head)
        self.git('push', '-q', 'origin', 'refs/tags/' + reviewed[:10])
        self.assertRefused(self.pr(comments=[self.comment('Approved %s' % reviewed[:10])]),
                           'not unique')

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
        pr = self.pr(comments=[self.comment('Approved `%s`' % reviewed[:12])])
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
        pr = self.pr(comments=[self.comment('Approved %s' % reviewed)])
        self.assertRefused(pr, 'conflict or an edit')

    def test_overlap_result(self):
        self.assertRefused(self.pr(body=ROBOT + ' Claude Code (author): no overlap line'),
                           'overlap check result')

    def test_paths_on_the_users_word(self):
        for path in ('rules/core.md', '.github/workflows/ci.yml', 'plugins/guards/x.py',
                     '.claude/settings.json', 'AGENTS.md', 'tools/installer.py', 'vercel.json',
                     'Agents.md', 'Plugins/Guards/x.py', 'plugins/core/scripts/merge_pr.py',
                     'plugins/x/hooks/hooks.json', '.github/dependabot.yml',
                     'plugins/core/scripts/review_verdict.py'):
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
        pr = self.pr(comments=[self.comment('Approved %s' % self.head)])
        self.assertRefused(pr, 'db/001.sql')

    def test_handoff_grant_and_settings_are_guarded(self):
        self.head = self.change('HANDOFF.md', handoff('More state.\n'))
        self.assertMerged(self.pr(comments=[self.comment('Approved %s' % self.head)]), '--dry-run')
        for text in ('## Landing settings\n\nGranted.\n',
                     SWITCH + '| unasked push | on |\n', '# Handoff\n'):
            with self.subTest(text=text):
                self.head = self.change('HANDOFF.md', '# Handoff\n\n' + text)
                self.assertRefused(self.pr(comments=[self.comment('Approved %s' % self.head)]),
                                   'merges only on the user')

    def test_a_teammates_changes_requested(self):
        review = {'submittedAt': '2026-11-09T12:00:00Z', 'state': 'CHANGES_REQUESTED',
                  'author': {'login': 'teammate'}, 'body': 'please fix the loop'}
        self.assertRefused(self.pr(reviews=[dict(review, authorAssociation='COLLABORATOR')]),
                           'teammate requests changes')
        later = dict(review, state='APPROVED', submittedAt='2026-11-09T13:00:00Z',
                     authorAssociation='COLLABORATOR')
        self.assertMerged(self.pr(reviews=[dict(review, authorAssociation='COLLABORATOR'),
                                           later]), '--dry-run')
        self.assertMerged(self.pr(reviews=[dict(review, authorAssociation='NONE')]), '--dry-run')

    def test_new_headings_naming_the_grant(self):
        for text in ('## Standing permissions (2026-11)\n\nAutomatic merging.\n',
                     '### Standing permissions\n\nAutomatic merging.\n',
                     'Our landing settings changed: local main.\n'):
            with self.subTest(text=text):
                self.head = self.change('HANDOFF.md', handoff(text))
                self.assertRefused(self.pr(comments=[self.comment('Approved %s' % self.head)]),
                                   'line naming them')

    def test_required_checks_row_and_app_checks(self):
        self.git('switch', '-q', 'main')
        self.write('HANDOFF.md', handoff("## Landing settings\n\n| Setting | Value |\n|---|---|\n"
                                         "| required checks | test (ubuntu, 3.12); lint |\n"))
        self.git('commit', '-q', '-am', 'settings')
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        self.git('switch', '-q', 'agent/7-x')
        self.git('merge', '-q', '--no-edit', 'origin/main')
        self.head = self.change('skills.md', 'v2\n')
        none = {'repos/acme/tool/rules/branches/main': [200, []]}
        run = lambda name, **kw: dict({'__typename': 'CheckRun', 'name': name,  # noqa: E731
                                       'status': 'COMPLETED', 'conclusion': 'SUCCESS'}, **kw)
        ok = [run('test (ubuntu, 3.12)'), run('lint')]
        pr = self.pr(statusCheckRollup=ok, comments=[self.comment('Approved %s' % self.head)])
        self.assertMerged(pr, '--dry-run', api=none)
        self.assertRefused(dict(pr, statusCheckRollup=ok[:1]), 'lint', api=none)
        # a check GitHub ties to an app: a status of the same name does not satisfy it
        app = {'repos/acme/tool/rules/branches/main': [200, [{
            'type': 'required_status_checks', 'parameters': {'required_status_checks': [
                {'context': 'build', 'integration_id': 15368}]}}]]}
        spoof = ok + [{'__typename': 'StatusContext', 'context': 'build', 'state': 'SUCCESS'}]
        self.assertRefused(dict(pr, statusCheckRollup=spoof), 'app:build', api=app)
        self.assertMerged(dict(pr, statusCheckRollup=ok + [run('build')]), '--dry-run', api=app)

    def test_manifest_versions_alone_pass(self):
        manifest = 'plugins/core/.claude-plugin/plugin.json'
        self.git('switch', '-q', 'main')
        self.write(manifest, json.dumps({'name': 'core', 'version': '0.1.0'}))
        self.git('add', '--', manifest)
        self.git('commit', '-q', '-m', 'manifest')
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        self.git('switch', '-q', 'agent/7-x')
        self.git('merge', '-q', '--no-edit', 'origin/main')
        self.head = self.change(manifest, json.dumps({'name': 'core', 'version': '0.2.0'}))
        self.assertMerged(self.pr(comments=[self.comment('Approved %s' % self.head)]), '--dry-run')
        self.head = self.change(manifest, json.dumps({'name': 'core', 'version': '0.2.0',
                                                      'hooks': './hooks.json'}))
        self.assertRefused(self.pr(comments=[self.comment('Approved %s' % self.head)]),
                           'plugin.json')

    def test_local_main_mode(self):
        self.git('switch', '-q', 'main')
        self.write('HANDOFF.md', handoff("## Landing settings\n\n| Setting | Value |\n|---|---|\n"
                                         "| landing | `local main` |\n"))
        self.git('commit', '-q', '-am', 'settings')
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        self.git('switch', '-q', 'agent/7-x')
        self.assertRefused(self.pr(), 'not through pull requests')


if __name__ == '__main__':
    unittest.main(verbosity=1)
