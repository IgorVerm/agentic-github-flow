#!/usr/bin/env python3
"""Checks plugins/core/scripts/landing.py on offline fixtures: python3 tests/landing.py.

A stand-in `gh` (AGENTIC_GITHUB_FLOW_GH) answers each call from a fixture: a JSON body and an
HTTP status, printed the way gh prints them (the body on stdout, `gh: <message> (HTTP <n>)` on
stderr, exit 1), or a network failure without a body. Each case is one signal of the detection
rule, or a way it could choose local main where a pull request is required: the setting both
ways and overruled by the server, no remote, a remote off GitHub, every ruleset type that
forbids a direct push and one that does not (`non_fast_forward`), a rule type it does not know,
legacy protection readable and unreadable, the free plan's 403 on both endpoints (which means
"no protection possible", not "unknown"), an Organization owner, no push permission, two
writers, CODEOWNERS, pull requests merged by someone else, by a bot, long ago and by the user,
and API errors. GitHub that cannot be asked from here gives no decision (`landing: unknown`, exit
3): no gh, a gh that cannot read its configuration (as inside the Claude Code sandbox), a gh that
is not signed in, a network failure or a sandbox's proxy; the `landing` setting still wins there.
Also: the landing branch setting, the scripts that need the mode refusing on unknown, and that
the issue-chats plugin's copy of the script is identical. No network, no real gh.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'landing.py')
COPY = os.path.join(ROOT, 'plugins', 'issue-chats', 'scripts', 'landing.py')

STUB = r'''import json, os, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
s.setdefault('log', []).append(a)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if s.get('fail'):
    print('error connecting to api.github.com', file=sys.stderr); sys.exit(1)
key = a[1].split('?')[0] if a[0] == 'api' else ' '.join(a[:2])
if key not in s['answers']:
    print('gh: Not Found (HTTP 404)', file=sys.stderr); print('{"message": "Not Found"}'); sys.exit(1)
status, body = s['answers'][key]
print(json.dumps(body))
if status != 200:
    print('gh: %s (HTTP %d)' % (body.get('message', ''), status), file=sys.stderr); sys.exit(1)
'''

REPO = 'repos/acme/tool'
ADVICE = ('run landing.py outside the sandbox, or set the `landing` row in HANDOFF.md '
          '\N{SECTION SIGN}Landing settings')
SANDBOXED = ('gh could not run here (its configuration is unreadable, as inside a sandbox): '
             + ADVICE)


def failing_gh(stderr, code=1):
    """A gh that prints <stderr> and exits <code> without an answer."""
    return [sys.executable, '-c', 'import sys; sys.stderr.write(%r); sys.exit(%d)' % (stderr, code)]


# gh inside the Claude Code sandbox, where ~/.config/gh/hosts.yml is unreadable
CONFIG_DENIED = failing_gh(
    'warning: failed to load config: open ~/.config/gh/hosts.yml: operation not '
    'permitted\nfailed to create root command: failed to read configuration: open '
    '~/.config/gh/hosts.yml: operation not permitted\n')
# gh behind the sandbox's network proxy, which refuses api.github.com
PROXY_DENIED = failing_gh('Get "https://api.github.com/repos/acme/tool/rules/branches/main": '
                          'Forbidden\n')
SIGNED_OUT = failing_gh('To get started with GitHub CLI, please run:  gh auth login\n', 4)
PLAN = [403, {'message': 'Upgrade to GitHub Pro or make this repository public to enable this '
                         'feature.', 'status': '403'}]
NOT_PROTECTED = [404, {'message': 'Branch not protected', 'status': '404'}]


def now(days_ago=0):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return t.strftime('%Y-%m-%dT%H:%M:%SZ')


def solo(**over):
    """A user-owned repository with one writer, no protection and no team signal."""
    answers = {
        REPO + '/rules/branches/main': [200, []],
        REPO + '/branches/main/protection': NOT_PROTECTED,
        REPO + '/branches/main': [200, {'name': 'main', 'protected': False}],
        REPO: [200, {'owner': {'type': 'User'}, 'permissions': {'push': True, 'admin': True}}],
        REPO + '/collaborators': [200, [{'login': 'me', 'permissions': {'push': True}}]],
        'user': [200, {'login': 'me'}],
        'pr list': [200, [{'author': {'login': 'me', 'is_bot': False}, 'mergedAt': now(1)}]],
    }
    answers.update(over)
    return answers


def settings(rows):
    return '# Handoff\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n%s\n## Next\n' % (
        ''.join('| %s | %s |\n' % r for r in rows))


class Landing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, 'repo')
        self.stub = os.path.join(self.tmp.name, 'gh_stub.py')
        self.state = os.path.join(self.tmp.name, 'state.json')
        with open(self.stub, 'w') as f:
            f.write(STUB)
        os.makedirs(self.repo)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Test')
        self.commit({'README.md': 'x\n'})
        self.git('remote', 'add', 'origin', 'https://github.com/acme/tool.git')
        self.publish('main')

    def git(self, *args):
        r = subprocess.run(['git', '-C', self.repo, *args], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, files):
        for name, text in files.items():
            path = os.path.join(self.repo, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(text)
            self.git('add', '--', name)
        self.git('commit', '-q', '-m', 'c')

    def publish(self, branch):
        """Make origin/<branch> the current commit and origin's default branch main."""
        self.git('update-ref', 'refs/remotes/origin/' + branch, 'HEAD')
        if branch == 'main':
            self.git('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')

    def run_tool(self, answers=None, fail=False, gh=None, args=()):
        with open(self.state, 'w') as f:
            json.dump({'answers': answers or {}, 'fail': fail}, f)
        env = dict(os.environ, STUB_GH=self.state,
                   AGENTIC_GITHUB_FLOW_GH=json.dumps(gh or [sys.executable, self.stub]))
        r = subprocess.run([sys.executable, TOOL, '-C', self.repo, *(args or ('--explain',))],
                           capture_output=True, text=True, env=env)
        with open(self.state) as f:
            self.log = json.load(f).get('log', [])
        return r

    def mode(self, answers=None, **kw):
        r = self.run_tool(answers, **kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        last = r.stdout.strip().splitlines()[-1]
        self.assertTrue(last.startswith('landing: '), r.stdout)
        self.out = r.stdout
        return last[len('landing: '):]

    def unknown(self, answers=None, **kw):
        """Run with GitHub unaskable: exit 3, last line `landing: unknown`; the cause line."""
        r = self.run_tool(answers, **kw)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[-1], 'landing: unknown', r.stdout)
        checks = [line for line in lines if line.startswith('check: ')]
        self.assertTrue(checks, r.stdout)
        self.out = r.stdout
        return checks[-1][len('check: '):]

    # --- 6: one writer, nothing else -------------------------------------------------------
    def test_solo_repository_lands_on_local_main(self):
        self.assertEqual(self.mode(solo()), 'local main')
        self.assertIn('landing branch: main', self.out)

    def test_without_explain_only_the_branch_and_the_mode(self):
        self.assertEqual(self.mode(solo(), args=('-C', self.repo)), 'local main')
        self.assertEqual(self.out.splitlines(), ['landing branch: main', 'landing: local main'])

    def test_free_plan_403_is_no_protection_not_unknown(self):
        self.assertEqual(self.mode(solo(**{REPO + '/rules/branches/main': PLAN,
                                           REPO + '/branches/main/protection': PLAN})),
                         'local main')
        self.assertIn('no protection possible', self.out)

    # --- 1: the setting -----------------------------------------------------------------------
    def test_setting_pull_request_wins_without_asking_github(self):
        self.commit({'HANDOFF.md': settings([('landing', '`pull request`')])})
        self.publish('main')
        self.assertEqual(self.mode(solo()), 'pull request')
        self.assertEqual(self.log, [])

    def test_setting_local_main_skips_team_signals(self):
        self.commit({'HANDOFF.md': settings([('landing', 'local main')])})
        self.publish('main')
        org = solo(**{REPO: [200, {'owner': {'type': 'Organization'},
                                   'permissions': {'push': True}}]})
        self.assertEqual(self.mode(org), 'local main')

    def test_setting_local_main_cannot_overrule_the_server(self):
        self.commit({'HANDOFF.md': settings([('landing', 'local main')])})
        self.publish('main')
        rules = solo(**{REPO + '/rules/branches/main': [200, [{'type': 'pull_request'}]]})
        self.assertEqual(self.mode(rules), 'pull request')
        self.assertIn('overrules the setting', self.out)

    def test_setting_local_main_holds_when_the_server_cannot_be_read(self):
        self.commit({'HANDOFF.md': settings([('landing', 'local main')])})
        self.publish('main')
        self.assertEqual(self.mode(solo(), fail=True), 'local main')
        self.git('remote', 'set-url', 'origin', 'https://gitlab.com/acme/tool.git')
        self.assertEqual(self.mode(solo()), 'local main')
        self.assertIn('server not checked', self.out)

    def test_unknown_setting_value_is_pull_request(self):
        self.commit({'HANDOFF.md': settings([('landing', 'trunk')])})
        self.publish('main')
        self.assertEqual(self.mode(solo()), 'pull request')

    def test_setting_on_an_unmerged_branch_does_not_count(self):
        self.git('switch', '-q', '-c', 'agent/x')
        self.commit({'HANDOFF.md': settings([('landing', 'pull request')])})
        self.assertEqual(self.mode(solo()), 'local main')

    # --- 2 and 5: the remote ------------------------------------------------------------------
    def test_no_remote_is_local_main(self):
        self.git('remote', 'remove', 'origin')
        self.assertEqual(self.mode(solo()), 'local main')
        self.assertEqual(self.log, [])

    def test_remote_off_github_is_pull_request(self):
        self.git('remote', 'set-url', 'origin', 'https://gitlab.com/acme/tool.git')
        self.assertEqual(self.mode(solo()), 'pull request')

    def test_ssh_remote_is_read(self):
        self.git('remote', 'set-url', 'origin', 'git@github.com:acme/tool.git')
        self.assertEqual(self.mode(solo()), 'local main')

    # --- 5: GitHub cannot be asked from here: no decision -------------------------------------
    def test_gh_that_cannot_read_its_configuration_is_unknown(self):
        self.assertEqual(self.unknown(solo(), gh=CONFIG_DENIED), SANDBOXED)
        r = self.run_tool(solo(), gh=CONFIG_DENIED, args=('-C', self.repo))
        self.assertEqual((r.returncode, r.stdout.splitlines()), (3, [
            'check: ' + SANDBOXED, 'landing branch: main', 'landing: unknown']))

    def test_the_setting_wins_where_github_cannot_be_asked(self):
        for value, expected in (('local main', 'local main'), ('pull request', 'pull request')):
            with self.subTest(setting=value):
                self.commit({'HANDOFF.md': settings([('landing', value)])})
                self.publish('main')
                self.assertEqual(self.mode(solo(), gh=CONFIG_DENIED), expected)
                if value == 'local main':
                    self.assertIn('server not checked', self.out)

    def test_the_branch_needs_no_github(self):
        r = self.run_tool(solo(), gh=CONFIG_DENIED, args=('-C', self.repo, '--branch'))
        self.assertEqual((r.returncode, r.stdout), (0, 'main\n'))

    def test_no_gh_is_unknown(self):
        cause = self.unknown(solo(), gh=[os.path.join(self.tmp.name, 'no-gh')])
        self.assertIn('gh could not run here', cause)
        bin_dir = os.path.join(self.tmp.name, 'bin')  # git, and no gh
        os.makedirs(bin_dir)
        git_exe = shutil.which('git')  # git.exe on Windows: the link keeps that name
        os.symlink(git_exe, os.path.join(bin_dir, os.path.basename(git_exe)))
        env = {k: v for k, v in os.environ.items() if k != 'AGENTIC_GITHUB_FLOW_GH'}
        r = subprocess.run([sys.executable, TOOL, '-C', self.repo], capture_output=True,
                           text=True, env=dict(env, PATH=bin_dir))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('gh is not installed', r.stdout)

    def test_network_failure_and_a_proxy_are_unknown(self):
        self.assertIn('GitHub could not be reached', self.unknown(solo(), fail=True))
        self.assertIn('Forbidden', self.unknown(solo(), gh=PROXY_DENIED))

    def test_not_signed_in_is_unknown(self):
        self.assertIn('gh auth login', self.unknown(solo(), gh=SIGNED_OUT))

    def test_a_failure_that_names_no_cause_stays_the_safe_default(self):
        self.assertEqual(self.mode(solo(), gh=failing_gh('something odd\n')), 'pull request')
        self.assertIn('the safe default', self.out)

    def test_other_403_is_pull_request(self):
        denied = [403, {'message': 'Resource not accessible by integration'}]
        self.assertEqual(self.mode(solo(**{REPO + '/rules/branches/main': denied})),
                         'pull request')

    def test_missing_repository_is_pull_request(self):
        self.assertEqual(self.mode(solo(**{REPO + '/rules/branches/main':
                                           [404, {'message': 'Not Found'}]})), 'pull request')

    # --- 3: the server ------------------------------------------------------------------------
    def test_every_pushing_rule_requires_a_pull_request(self):
        for kind in ('pull_request', 'update', 'required_status_checks', 'merge_queue',
                     'required_deployments', 'workflows', 'code_scanning', 'rule_of_the_future'):
            with self.subTest(kind=kind):
                rules = [{'type': 'deletion'}, {'type': kind}]
                self.assertEqual(self.mode(solo(**{REPO + '/rules/branches/main': [200, rules]})),
                                 'pull request')

    def test_non_fast_forward_alone_allows_local_main(self):
        rules = [{'type': 'non_fast_forward'}, {'type': 'deletion'},
                 {'type': 'required_signatures'}]
        self.assertEqual(self.mode(solo(**{REPO + '/rules/branches/main': [200, rules]})),
                         'local main')

    def test_legacy_protection(self):
        cases = [
            ({'required_pull_request_reviews': {'required_approving_review_count': 1}},
             'pull request'),
            ({'required_status_checks': {'strict': True, 'contexts': ['ci']}}, 'pull request'),
            ({'restrictions': {'users': [], 'teams': []}}, 'pull request'),
            ({'lock_branch': {'enabled': True}}, 'pull request'),
            ({'required_status_checks': {'strict': True, 'contexts': [], 'checks': []},
              'allow_force_pushes': {'enabled': False}}, 'local main'),
        ]
        for body, want in cases:
            with self.subTest(body=body):
                self.assertEqual(self.mode(solo(**{REPO + '/branches/main/protection':
                                                   [200, body]})), want)

    def test_unreadable_protection_counts_when_branch_is_protected(self):
        hidden = [404, {'message': 'Not Found'}]
        for protected, want in ((True, 'pull request'), (False, 'local main')):
            with self.subTest(protected=protected):
                self.assertEqual(self.mode(solo(**{
                    REPO + '/branches/main/protection': hidden,
                    REPO + '/branches/main': [200, {'protected': protected}]})), want)

    # --- 4: team signals ----------------------------------------------------------------------
    def test_organization_owner(self):
        self.assertEqual(self.mode(solo(**{REPO: [200, {'owner': {'type': 'Organization'},
                                                        'permissions': {'push': True}}]})),
                         'pull request')

    def test_no_push_permission(self):
        self.assertEqual(self.mode(solo(**{REPO: [200, {'owner': {'type': 'User'},
                                                        'permissions': {'push': False}}]})),
                         'pull request')

    def test_two_writers(self):
        people = [{'login': 'me', 'permissions': {'push': True}},
                  {'login': 'colleague', 'permissions': {'push': True}},
                  {'login': 'reader', 'permissions': {'push': False}}]
        self.assertEqual(self.mode(solo(**{REPO + '/collaborators': [200, people]})),
                         'pull request')

    def test_one_writer_and_a_reader(self):
        people = [{'login': 'me', 'permissions': {'push': True}},
                  {'login': 'reader', 'permissions': {'push': False}}]
        self.assertEqual(self.mode(solo(**{REPO + '/collaborators': [200, people]})),
                         'local main')

    def test_codeowners(self):
        self.commit({'.github/CODEOWNERS': '* @acme/team\n'})
        self.assertEqual(self.mode(solo()), 'local main')  # not on origin/main yet
        self.publish('main')
        self.assertEqual(self.mode(solo()), 'pull request')

    def test_merged_pull_requests(self):
        cases = [
            ({'login': 'colleague', 'is_bot': False}, now(3), 'pull request'),
            ({'login': 'dependabot', 'is_bot': True}, now(3), 'local main'),
            ({'login': 'app/renovate', 'is_bot': False}, now(3), 'local main'),
            ({'login': 'colleague', 'is_bot': False}, now(200), 'local main'),
            ({'login': 'ME', 'is_bot': False}, now(3), 'local main'),
        ]
        for author, when, want in cases:
            with self.subTest(author=author, when=when):
                pulls = [200, [{'author': author, 'mergedAt': when}]]
                self.assertEqual(self.mode(solo(**{'pr list': pulls})), want)

    def test_a_fork_is_pull_request(self):
        info = [200, {'owner': {'type': 'User'}, 'permissions': {'push': True}, 'fork': True,
                      'parent': {'full_name': 'acme-org/tool'}}]
        self.assertEqual(self.mode(solo(**{REPO: info})), 'pull request')
        self.assertIn('acme-org/tool', self.out)

    def test_remotes_without_origin_are_unknown(self):
        self.git('remote', 'rename', 'origin', 'upstream')
        self.assertEqual(self.mode(solo()), 'pull request')
        self.assertEqual(self.log, [])

    def test_owner_missing_from_collaborators_still_counts_a_writer(self):
        people = [{'login': 'colleague', 'permissions': {'push': True}}]
        self.assertEqual(self.mode(solo(**{REPO + '/collaborators': [200, people]})),
                         'pull request')

    def test_plan_limit_on_one_endpoint(self):
        self.assertEqual(self.mode(solo(**{REPO + '/branches/main/protection': PLAN})),
                         'local main')
        rules = solo(**{REPO + '/rules/branches/main': PLAN,
                        REPO + '/branches/main/protection': [200, {
                            'required_pull_request_reviews': {}, 'restrictions': {'users': []}}]})
        self.assertEqual(self.mode(rules), 'pull request')

    def test_url_forms(self):
        for url in ('https://someone' + '@' + 'github.com/acme/tool', 'ssh://git@github.com/acme/tool.git',
                    'git@github.com:acme/tool'):
            with self.subTest(url=url):
                self.git('remote', 'set-url', 'origin', url)
                self.assertEqual(self.mode(solo()), 'local main')

    def test_codeowners_everywhere_and_unfetched(self):
        for where in ('CODEOWNERS', 'docs/CODEOWNERS'):
            with self.subTest(where=where):
                self.commit({where: '* @acme/team\n'})
                self.publish('main')
                self.assertEqual(self.mode(solo()), 'pull request')
                self.git('rm', '-q', where)
                self.git('commit', '-q', '-m', 'rm')
                self.publish('main')
        self.git('update-ref', '-d', 'refs/remotes/origin/main')
        self.git('symbolic-ref', '-d', 'refs/remotes/origin/HEAD')
        self.assertEqual(self.mode(solo()), 'pull request')
        self.assertIn('not fetched', self.out)

    def test_bot_suffix_and_failing_calls(self):
        pulls = [200, [{'author': {'login': 'renovate[bot]', 'is_bot': False}, 'mergedAt': now(1)}]]
        self.assertEqual(self.mode(solo(**{'pr list': pulls})), 'local main')
        for key in ('user', 'pr list'):
            with self.subTest(failing=key):
                self.assertEqual(self.mode(solo(**{key: [500, {'message': 'Server Error'}]})),
                                 'pull request')

    def test_non_ascii_handoff(self):
        self.commit({'HANDOFF.md': '# H \u201cquoted\u201d \u2190 \u00e9\n\n' + settings(
            [('landing', 'pull request')])})
        self.publish('main')
        self.assertEqual(self.mode(solo()), 'pull request')

    def test_unreadable_collaborators_is_pull_request(self):
        self.assertEqual(self.mode(solo(**{REPO + '/collaborators':
                                           [403, {'message': 'Must have push access'}]})),
                         'pull request')

    # --- the landing branch -------------------------------------------------------------------
    def test_landing_branch_setting(self):
        self.commit({'HANDOFF.md': settings([('landing branch', '`editor`')])})
        self.publish('main')
        self.publish('editor')
        answers = {k.replace('/main', '/editor'): v for k, v in solo().items()}
        self.assertEqual(self.mode(answers), 'local main')
        self.assertIn('landing branch: editor', self.out)
        self.assertIn([ 'api', REPO + '/rules/branches/editor'], self.log)
        r = self.run_tool(args=('--branch',))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'editor'))

    def test_automatic_merge_is_off_unless_the_row_says_on(self):
        self.assertEqual(self.mode(solo()), 'local main')
        self.assertIn('automatic merge: off', self.out)
        for value, shown in (('`on`', 'on'), ('On', 'on'), ('`off`', 'off'), ('yes', 'off')):
            with self.subTest(value=value):
                self.commit({'HANDOFF.md': settings([('landing', 'pull request'),
                                                     ('automatic merge', value)])})
                self.publish('main')
                self.assertEqual(self.mode(solo()), 'pull request')
                self.assertIn('automatic merge: %s' % shown, self.out)
        r = self.run_tool(solo(), args=('-C', self.repo))
        self.assertNotIn('automatic merge', r.stdout)

    def test_invalid_landing_branch_is_an_error(self):
        self.commit({'HANDOFF.md': settings([('landing branch', 'a..b')])})
        self.publish('main')
        r = self.run_tool(solo())
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_landing_ref_prefers_the_remote_tracking_branch(self):
        sys.path.insert(0, os.path.dirname(TOOL))
        try:
            import landing
        finally:
            sys.path.pop(0)
        self.assertEqual(landing.landing_ref(self.repo), 'refs/remotes/origin/main')
        self.git('remote', 'remove', 'origin')
        self.assertEqual(landing.landing_ref(self.repo), 'refs/heads/main')

    def test_outside_git_is_an_error(self):
        r = subprocess.run([sys.executable, TOOL, '-C', self.tmp.name], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


class Consumers(unittest.TestCase):
    """The scripts that count "merged" or start from the default branch follow the setting."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bare = os.path.join(self.tmp.name, 'origin.git')
        self.repo = os.path.join(self.tmp.name, 'repo')
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', self.bare], check=True)
        os.makedirs(self.repo)
        for args in (('init', '-q', '-b', 'main'), ('config', 'user.email', 'test@example.com'),
                     ('config', 'user.name', 'Test')):
            self.git(*args)
        with open(os.path.join(self.repo, 'HANDOFF.md'), 'w') as f:
            f.write(settings([('landing branch', '`editor`')]))
        self.git('add', '--', 'HANDOFF.md')
        self.git('commit', '-q', '-m', 'base')
        self.git('switch', '-q', '-c', 'editor')
        self.git('commit', '-q', '--allow-empty', '-m', 'editor only')
        self.editor = self.git('rev-parse', 'HEAD')
        self.git('switch', '-q', 'main')
        self.git('remote', 'add', 'origin', self.bare)
        self.git('push', '-q', 'origin', 'main', 'editor')
        self.git('fetch', '-q', 'origin')
        self.git('remote', 'set-head', 'origin', 'main')

    def git(self, *args):
        r = subprocess.run(['git', '-C', self.repo, *args], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def module(self, name):
        sys.path.insert(0, os.path.dirname(TOOL))
        try:
            return __import__(name)
        finally:
            sys.path.pop(0)

    def test_new_worktree_starts_from_the_landing_branch(self):
        self.assertEqual(self.module('new_worktree').default_base(self.repo),
                         'refs/remotes/origin/editor')

    def test_overlap_check_compares_with_the_landing_branch(self):
        self.assertEqual(self.module('overlap_check').default_base(self.repo),
                         'refs/remotes/origin/editor')

    def test_cleanup_counts_against_the_landing_branch(self):
        ref, error = self.module('remove_merged_worktree').default_ref(self.repo, fetch=False)
        self.assertEqual((ref, error), ('refs/remotes/origin/editor', None))
        self.assertIn('editor', self.module('remove_merged_worktree').protected_branches(
            self.repo, ref))

    def test_unpushed_landings_are_the_base_in_local_main_mode(self):
        self.git('switch', '-q', 'editor')
        self.git('commit', '-q', '--allow-empty', '-m', 'landed, not pushed')
        self.git('switch', '-q', 'main')
        # a folder remote is not GitHub: auto gives pull request, so origin's branch stays the base
        for name in ('new_worktree', 'overlap_check'):
            self.assertEqual(self.module(name).default_base(self.repo), 'refs/remotes/origin/editor')
        with open(os.path.join(self.repo, 'HANDOFF.md'), 'w') as f:
            f.write(settings([('landing branch', 'editor'), ('landing', 'local main')]))
        self.git('commit', '-q', '-am', 'local main')
        self.git('push', '-q', 'origin', 'main')
        self.git('fetch', '-q', 'origin')
        for name in ('new_worktree', 'overlap_check'):
            self.assertEqual(self.module(name).default_base(self.repo), 'refs/heads/editor')

    def test_unpushed_landings_with_the_mode_unknown_refuse(self):
        # GitHub cannot be asked (the sandbox): the base is origin's branch while nothing is
        # unpushed, which needs no mode; with unpushed landings the scripts refuse, not guess
        self.git('remote', 'set-url', 'origin', 'https://github.com/acme/tool.git')
        with mock.patch.dict(os.environ, {'AGENTIC_GITHUB_FLOW_GH': json.dumps(CONFIG_DENIED)}):
            for name in ('new_worktree', 'overlap_check'):
                self.assertEqual(self.module(name).default_base(self.repo),
                                 'refs/remotes/origin/editor')
            self.git('switch', '-q', 'editor')
            self.git('commit', '-q', '--allow-empty', '-m', 'landed, not pushed')
            self.git('switch', '-q', 'main')
            with self.assertRaises(self.module('new_worktree').SettingError) as e:
                self.module('new_worktree').default_base(self.repo)
            with self.assertRaises(self.module('overlap_check').Usage) as u:
                self.module('overlap_check').default_base(self.repo)
        for error in (e.exception, u.exception):
            self.assertIn('landing mode unknown: ' + SANDBOXED, str(error))

    def test_the_landing_branch_is_never_deleted(self):
        script = os.path.join(os.path.dirname(TOOL), 'delete_merged_branch.py')
        r = subprocess.run([sys.executable, script, 'editor', '--dry-run'], cwd=self.repo,
                           capture_output=True, text=True,
                           env=dict(os.environ, AGENTIC_GITHUB_FLOW_GH='["false"]'))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('never deleted', r.stdout)


class Copy(unittest.TestCase):
    def test_issue_chats_copy_is_identical(self):
        with open(TOOL, 'rb') as a, open(COPY, 'rb') as b:
            self.assertEqual(a.read(), b.read(), 'copy plugins/core/scripts/landing.py to %s'
                             % os.path.relpath(COPY, ROOT))


if __name__ == '__main__':
    unittest.main(verbosity=1)
