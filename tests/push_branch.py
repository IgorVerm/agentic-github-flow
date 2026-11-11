#!/usr/bin/env python3
"""Checks plugins/core/scripts/push_branch.py in throwaway repositories (#26):
python3 tests/push_branch.py.

A bare origin on disk, a clone with the real templates/pre-push installed, and a temporary HOME
holding the hook's scripts (as tests/pre_push_checks.py builds them); a stand-in `gh`
(AGENTIC_GITHUB_FLOW_GH) answers `pr list` from a fixture and records `pr create`. A folder
remote is not GitHub, so landing.py decides pull request unless HANDOFF.md says local main.
The cases that push: a clean task branch, which then gets its pull request, with the hook run
under AGENTIC_GITHUB_FLOW_UNASKED_PUSH and no tag following the branch; a later push to a branch
whose pull request is open (a fork's of the same name is not it); a grant in HANDOFF.md; a
title starting with a dash. Each refusal is one condition broken on its own: no grant, a grant
file that is missing, only mentions the script (as the core rules do), lies in a checkout of
this repository or in the installed clone, a HANDOFF.md that only mentions it or grants it on
the task branch alone, the default branch (as GitHub reports it now, whatever origin/HEAD
says; unreadable refuses), a detached HEAD, local-main mode, pull-request mode only as the
safe default, no hook or another hook, a protected path, no
overlap result, a branch behind origin's; the hook's own refusal (a secret) is the script's
refusal; a pull request that cannot be opened after the push exits 3. Planted values are built
by concatenation. Offline.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pre_push_checks import EMAIL, NAME, TOKEN, install_clone, install_hook  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..'))
TOOL = os.path.join(ROOT, 'plugins', 'core', 'scripts', 'push_branch.py')
ROBOT = '\N{ROBOT FACE}'
SETTINGS = ('# H\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n'
            '| landing | `pull request` |\n')
BODY = ROBOT + ' Claude Code (author): the change\n\nOverlap check: none\n\nCloses #7\n'

STUB = r'''import json, os, sys
s = json.load(open(os.environ['STUB_GH']))
a = sys.argv[1:]
s.setdefault('log', []).append(a)
json.dump(s, open(os.environ['STUB_GH'], 'w'))
if a[:2] == ['pr', 'list']:
    print(json.dumps(s.get('prs', []))); sys.exit(0)
if a[:2] == ['repo', 'view']:
    if not s.get('default'):
        print('gh: Could not resolve to a Repository', file=sys.stderr); sys.exit(1)
    print(json.dumps({'defaultBranchRef': {'name': s['default']}})); sys.exit(0)
if a[:2] == ['pr', 'create']:
    if s.get('create_fails'):
        print('GraphQL: was submitted too quickly', file=sys.stderr); sys.exit(1)
    print('https://github.com/acme/tool/pull/8'); sys.exit(0)
sys.exit(3)
'''


class PushBranch(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix='push-branch-'))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.home = os.path.join(self.dir, 'home')
        os.makedirs(os.path.join(self.home, 'cfg'))
        with open(os.path.join(self.home, '.gitconfig'), 'w') as f:
            f.write('[user]\n\tname = %s\n\temail = %s\n[advice]\n\tdetachedHead = false\n'
                    '[init]\n\tdefaultBranch = main\n' % (NAME, EMAIL))
        install_clone(self.home)
        self.stub = os.path.join(self.dir, 'gh_stub.py')
        self.state = os.path.join(self.dir, 'state.json')
        with open(self.stub, 'w') as f:
            f.write(STUB)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('GIT_', 'GH_', 'XDG_', 'AGENTIC_GITHUB_FLOW_'))
                    and k != 'CLAUDE_PROJECT_DIR'}
        self.env.update(HOME=self.home, USERPROFILE=self.home, GIT_CONFIG_NOSYSTEM='1',
                        XDG_CONFIG_HOME=os.path.join(self.home, 'cfg'),
                        GH_CONFIG_DIR=os.path.join(self.home, 'gh'), STUB_GH=self.state,
                        AGENTIC_GITHUB_FLOW_GH=json.dumps([sys.executable, self.stub]))
        self.origin = os.path.join(self.dir, 'origin.git')
        self.repo = os.path.join(self.dir, 'repo')
        self.git(self.dir, 'init', '-q', '--bare', '-b', 'main', self.origin)
        self.git(self.dir, 'clone', '-q', self.origin, self.repo)
        self.commit('HANDOFF.md', SETTINGS)
        self.git(self.repo, 'push', '-q', 'origin', 'main')  # no hook yet
        self.git(self.repo, 'remote', 'set-head', 'origin', 'main')
        install_hook(self.repo, self.env)
        self.git(self.repo, 'switch', '-q', '-c', 'agent/7-x')
        self.commit('plugins/core/skills/x/SKILL.md', 'a skill\n')
        self.body = os.path.join(self.dir, 'body.md')
        self.write_body(BODY)
        self.overlay = os.path.join(self.dir, 'overlay', 'AGENTS.md')
        os.makedirs(os.path.dirname(self.overlay))
        with open(self.overlay, 'w') as f:
            f.write('Push your own task branch without asking.\n\n'
                    '| Grant | Script |\n|---|---|\n| standing grant | `push_branch.py` |\n')

    def git(self, cwd, *args, check=True):
        r = subprocess.run(['git', *args], cwd=cwd, env=self.env, capture_output=True,
                           text=True, encoding='utf-8', errors='replace')
        if check and r.returncode:
            raise AssertionError('git %s: %s' % (' '.join(args), r.stderr))
        return r.stdout.strip()

    def commit(self, rel, text, repo=None):
        repo = repo or self.repo
        path = os.path.join(repo, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        self.git(repo, 'add', '--', rel)
        self.git(repo, 'commit', '-q', '-m', 'change ' + rel)

    def write_body(self, text):
        with open(self.body, 'w', encoding='utf-8') as f:
            f.write(text)

    def run_tool(self, *args, prs=None, grant='', pr=True, create_fails=False, default='main'):
        grant = self.overlay if grant == '' else grant
        with open(self.state, 'w') as f:
            json.dump({'prs': prs or [], 'create_fails': create_fails, 'default': default}, f)
        cmd = [sys.executable, TOOL, '-C', self.repo, '-R', 'acme/tool', *args]
        if grant:
            cmd += ['--grant', grant]
        if pr:
            cmd += ['--title', 'A change (#7)', '--body-file', self.body, '--draft']
        r = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        with open(self.state) as f:
            self.log = json.load(f).get('log', [])
        return r

    def on_origin(self, branch='agent/7-x'):
        return self.git(self.origin, 'rev-parse', '-q', '--verify', 'refs/heads/' + branch,
                        check=False)

    def created(self):
        return [a for a in self.log if a[:2] == ['pr', 'create']]

    def assertRefused(self, text, *args, **kw):
        r = self.run_tool(*args, **kw)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(text, r.stdout)
        self.assertEqual(self.created(), [])
        return r

    # --- what pushes --------------------------------------------------------------------------

    def test_pushes_a_clean_task_branch_and_opens_its_pull_request(self):
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.on_origin(), self.git(self.repo, 'rev-parse', 'HEAD'))
        self.assertEqual(self.created(), [['pr', 'create', '-R', 'acme/tool', '--base', 'main',
                                           '--head', 'agent/7-x', '--title', 'A change (#7)',
                                           '--body-file', self.body, '--draft']])
        self.assertIn('pull/8', r.stdout)
        self.assertIn(self.overlay, r.stdout)
        # no upstream written into the git configuration
        self.assertEqual(self.git(self.repo, 'config', '--get', 'branch.agent/7-x.remote',
                                  check=False), '')

    def test_a_later_push_to_an_open_pull_request(self):
        self.assertEqual(self.run_tool().returncode, 0)
        self.commit('plugins/core/skills/x/SKILL.md', 'a review finding fixed\n')
        open_pr = [{'number': 8, 'url': 'https://github.com/acme/tool/pull/8', 'body': BODY,
                    'baseRefName': 'main', 'isCrossRepository': False}]
        r = self.run_tool(prs=open_pr, pr=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.on_origin(), self.git(self.repo, 'rev-parse', 'HEAD'))
        self.assertEqual(self.created(), [])
        self.assertRefused('no overlap check result', prs=[dict(open_pr[0], body='no line')],
                           pr=False)

    def test_the_branch_alone_goes_out_whatever_the_push_settings(self):
        self.git(self.repo, 'config', 'push.followTags', 'true')
        self.git(self.repo, 'tag', '-a', '-m', 'release', 'v9')
        r = self.run_tool()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.git(self.origin, 'tag', '--list'), '')

    def test_the_hook_runs_with_the_protected_path_check_switched_on(self):
        hook = os.path.join(self.repo, '.git', 'hooks', 'pre-push')
        seen = os.path.join(self.dir, 'seen.txt')
        with open(hook, 'w') as f:  # the marks, and a record of what the hook was given
            f.write('#!/bin/sh\n# agentic-github-flow pre-push hook (stand-in)\n'
                    'echo "${AGENTIC_GITHUB_FLOW_UNASKED_PUSH:-unset}" > "%s"\nexit 0\n'
                    % seen.replace('\\', '/'))
        os.chmod(hook, 0o755)
        self.assertEqual(self.run_tool().returncode, 0)
        with open(seen) as f:
            self.assertEqual(f.read().strip(), '1')

    def test_pushed_without_a_pull_request_exits_3(self):
        r = self.run_tool(create_fails=True)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('was not opened', r.stdout)
        self.assertNotEqual(self.on_origin(), '')

    def test_a_grant_in_handoff(self):
        self.git(self.repo, 'switch', '-q', 'main')
        self.commit('HANDOFF.md', SETTINGS + '\n## Standing permissions\n\n'
                    'standing grant: push_branch.py\n')
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'switch', '-q', 'agent/7-x')
        r = self.run_tool(grant='HANDOFF.md')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_dry_run_pushes_nothing(self):
        r = self.run_tool('--dry-run')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('would push agent/7-x', r.stdout)
        self.assertEqual(self.on_origin(), '')
        self.assertEqual(self.created(), [])

    # --- each condition broken on its own refuses ---------------------------------------------

    def test_the_grant_is_read_where_it_is_named(self):
        self.assertRefused('cannot read the grant file', grant=self.overlay + '.missing')
        silent = os.path.join(self.dir, 'other.md')
        with open(silent, 'w') as f:
            f.write('Ask before every push.\n')
        self.assertRefused('has no line', grant=silent)
        # a mention is no grant: the core rules name the script too
        rules = os.path.join(self.dir, 'rules.md')
        with open(rules, 'w') as f:
            f.write('- **Ask before every push**, unless a standing grant covers your own task\n'
                    '  branch: then push it through `push_branch.py`.\n')
        self.assertRefused('has no line', grant=rules)
        grant = '| standing grant | `push_branch.py` |\n'
        inside = os.path.join(self.repo, 'grant.md')
        with open(inside, 'w') as f:
            f.write(grant)
        self.assertRefused('in a checkout of this repository', grant=inside)
        sibling = os.path.join(self.dir, 'sibling')
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/8-y', sibling, 'origin/main')
        with open(os.path.join(sibling, 'grant.md'), 'w') as f:
            f.write(grant)
        self.assertRefused('in a checkout of this repository',
                           grant=os.path.join(sibling, 'grant.md'))
        installed = os.path.join(self.home, '.agentic-github-flow', 'grant.md')
        with open(installed, 'w') as f:
            f.write(grant)
        self.assertRefused('installed agentic-github-flow', grant=installed)
        self.assertRefused('has no line', grant='HANDOFF.md')
        # a mention in §Standing permissions is no grant either
        self.git(self.repo, 'switch', '-q', 'main')
        self.commit('HANDOFF.md', SETTINGS + '\n## Standing permissions\n\nNone; '
                    'push_branch.py is not granted.\n')
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'switch', '-q', 'agent/7-x')
        self.assertRefused('has no line', grant='HANDOFF.md')
        # a grant written on the task branch alone does not count
        self.commit('HANDOFF.md', SETTINGS + '\n## Standing permissions\n\n' + grant)
        self.assertRefused('has no line', grant='HANDOFF.md')
        self.assertEqual(self.on_origin(), '')

    def test_pull_request_mode_only_as_the_safe_default(self):
        self.git(self.repo, 'switch', '-q', 'main')
        self.commit('HANDOFF.md', '# H\n')
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'switch', '-q', 'agent/7-x')
        self.assertRefused('only the safe default')
        self.assertEqual(self.on_origin(), '')

    def test_usage(self):
        self.assertEqual(self.run_tool(grant=None).returncode, 2)
        self.assertEqual(self.run_tool('--title', 'only a title', pr=False).returncode, 2)
        self.assertEqual(self.on_origin(), '')

    def test_the_default_branch_and_a_detached_head(self):
        self.git(self.repo, 'switch', '-q', 'main')
        self.commit('docs/a.md', 'a\n')
        self.assertRefused('not a task branch')
        self.git(self.repo, 'switch', '-q', '--detach', 'agent/7-x')
        self.assertRefused('no branch is checked out')
        self.assertEqual(self.git(self.origin, 'rev-parse', 'main'),
                         self.git(self.repo, 'rev-parse', 'origin/main'))

    def test_the_default_branch_is_read_from_github(self):
        # origin/HEAD here still says main; GitHub says develop, and develop is checked out
        self.git(self.repo, 'switch', '-q', '-c', 'develop', 'origin/main')
        self.commit('docs/d.md', 'd\n')
        self.assertRefused('not a task branch', default='develop')
        self.git(self.repo, 'switch', '-q', 'agent/7-x')
        self.assertRefused("cannot read acme/tool's default branch", default='')
        self.assertEqual(self.on_origin('develop'), '')
        self.assertEqual(self.on_origin(), '')

    def test_a_forks_pull_request_of_the_same_name_is_not_this_one(self):
        fork = [{'number': 9, 'url': 'https://github.com/acme/tool/pull/9', 'body': BODY,
                 'baseRefName': 'main', 'isCrossRepository': True}]
        self.assertRefused('pass --title and --body-file', prs=fork, pr=False)
        r = self.run_tool(prs=fork)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.created()), 1)

    def test_a_title_may_start_with_a_dash(self):
        r = self.run_tool('--title', '-x: a title', '--body-file', self.body, pr=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('-x: a title', self.created()[0])

    def test_local_main_mode(self):
        self.git(self.repo, 'switch', '-q', 'main')
        self.commit('HANDOFF.md', '# H\n\n## Landing settings\n\n| Setting | Value |\n|---|---|\n'
                    '| landing | `local main` |\n')
        self.git(self.repo, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'switch', '-q', 'agent/7-x')
        self.assertRefused('not through pull requests')
        self.assertEqual(self.on_origin(), '')

    def test_no_hook_or_another_hook(self):
        hook = os.path.join(self.repo, '.git', 'hooks', 'pre-push')
        os.remove(hook)
        self.assertRefused('no pre-push hook')
        with open(hook, 'w') as f:
            f.write('#!/bin/sh\nexit 0\n')
        os.chmod(hook, 0o755)
        self.assertRefused('not the agentic-github-flow pre-push hook')
        self.assertEqual(self.on_origin(), '')

    def test_protected_paths(self):
        for n, rel in enumerate(('.github/workflows/ci.yml', 'rules/core.md',
                                 '.claude/settings.json', 'plugins/guards/scripts/x.py',
                                 'templates/pre-push', 'plugins/core/scripts/push_branch.py')):
            with self.subTest(rel=rel):
                self.git(self.repo, 'switch', '-q', '-c', 'agent/7-p%d' % n, 'origin/main')
                self.commit(rel, 'changed\n')
                self.assertRefused(rel)
                self.assertEqual(self.on_origin('agent/7-p%d' % n), '')

    def test_the_hooks_own_refusal_is_a_refusal(self):
        self.commit('src/config.txt', 'token = ' + TOKEN + '\n')
        r = self.assertRefused('REFUSED by the push')
        self.assertIn('secret', r.stdout)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)
        self.assertEqual(self.on_origin(), '')

    def test_no_overlap_result(self):
        self.write_body(ROBOT + ' Claude Code (author): the change\n')
        self.assertRefused('no overlap check result')
        self.assertRefused('pass --title and --body-file', pr=False)
        self.assertEqual(self.on_origin(), '')

    def test_a_branch_behind_origins_copy(self):
        other = os.path.join(self.dir, 'other')
        self.git(self.dir, 'clone', '-q', '-b', 'main', self.origin, other)
        self.git(other, 'switch', '-q', '-c', 'agent/7-x')
        self.commit('docs/other.md', 'someone else\n', repo=other)
        self.git(other, 'push', '-q', 'origin', 'agent/7-x')  # no hook in this clone
        self.assertRefused('has commits HEAD lacks')


if __name__ == '__main__':
    unittest.main(verbosity=1)
