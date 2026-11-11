#!/usr/bin/env python3
"""Checks the content checks of templates/pre-push in throwaway repositories (#40):
python3 tests/pre_push_checks.py.

The hook lists the commits a push sends and runs, from the installed clone
(`$HOME/.agentic-github-flow`, here a temporary HOME holding a copy of this checkout's scripts):
the secret scan, the personal-data check and, when the push goes out without the user's yes
(AGENTIC_GITHUB_FLOW_UNASKED_PUSH, set by #26's route), the protected-path check. Each case
pushes to a bare repository on disk; nothing reaches the network. Every planted token and
e-mail address is built by concatenation, so this file holds nothing the scanners or
tests/repo_checks.py would report. A refusal must name the file and the rule and never print
the value. The force, tag and deletion refusals are tests/worktree_tools.py's.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
PRE_PUSH = os.path.join(ROOT, 'templates', 'pre-push')
SCRIPT_DIRS = ('plugins/security/scripts', 'plugins/guards/scripts', 'plugins/core/scripts')

NAME = 'Fixture Persona'
EMAIL = 'fixture.persona' + '@' + 'fixture-persona.eu'
OTHER = 'jan.peeters' + '@' + 'acme-bouw.be'
TOKEN = 'ghp_' + 'Q7m' * 12  # github-token: ghp_ and 36 letters or digits
NOREPLY = 'Co-Authored-By: Claude <' + 'noreply' + '@' + 'anthropic.com>'


def install_clone(home):
    """The scripts the hook runs, where the installer keeps its clone."""
    clone = os.path.join(home, '.agentic-github-flow')
    for rel in SCRIPT_DIRS:
        shutil.copytree(os.path.join(ROOT, *rel.split('/')), os.path.join(clone, *rel.split('/')),
                        ignore=shutil.ignore_patterns('__pycache__'))
    return clone


def install_hook(repo, env):
    hooks = subprocess.run(['git', 'rev-parse', '--git-path', 'hooks'], cwd=repo, env=env,
                           capture_output=True, text=True, check=True).stdout.strip()
    hooks = hooks if os.path.isabs(hooks) else os.path.join(repo, hooks)
    os.makedirs(hooks, exist_ok=True)
    shutil.copyfile(PRE_PUSH, os.path.join(hooks, 'pre-push'))
    os.chmod(os.path.join(hooks, 'pre-push'), 0o755)


class Push(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix='pre-push-checks-'))
        self.home = os.path.join(self.dir, 'fixtureperson')
        os.makedirs(os.path.join(self.home, 'cfg', 'agentic-github-flow'))
        with open(os.path.join(self.home, '.gitconfig'), 'w') as f:
            f.write('[user]\n\tname = %s\n\temail = %s\n[advice]\n\tdetachedHead = false\n'
                    '[init]\n\tdefaultBranch = main\n' % (NAME, EMAIL))
        self.clone = install_clone(self.home)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(('GIT_', 'GH_', 'XDG_', 'AGENTIC_GITHUB_FLOW_'))
                    and k != 'CLAUDE_PROJECT_DIR'}
        self.env.update(HOME=self.home, USERPROFILE=self.home, GIT_CONFIG_NOSYSTEM='1',
                        XDG_CONFIG_HOME=os.path.join(self.home, 'cfg'),
                        GH_CONFIG_DIR=os.path.join(self.home, 'gh'))
        self.origin = os.path.join(self.dir, 'origin.git')
        self.repo = os.path.join(self.dir, 'repo')
        self.git(self.dir, 'init', '-q', '--bare', '-b', 'main', self.origin)
        self.git(self.dir, 'clone', '-q', self.origin, self.repo)
        self.commit('README.md', 'start\n', 'start')
        self.git(self.repo, 'push', '-q', 'origin', 'main')  # no hook yet
        self.git(self.repo, 'remote', 'set-head', 'origin', 'main')
        install_hook(self.repo, self.env)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def git(self, cwd, *args, check=True, env=None):
        r = subprocess.run(['git', *args], cwd=cwd, env=env or self.env, capture_output=True,
                           text=True, encoding='utf-8', errors='replace')
        if check and r.returncode:
            raise AssertionError('git %s: %s' % (' '.join(args), r.stderr))
        return r

    def commit(self, rel, text, message, repo=None):
        repo = repo or self.repo
        path = os.path.join(repo, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
        self.git(repo, 'add', '--', rel)
        self.git(repo, 'commit', '-q', '-m', message)

    def push(self, *args, env=None):
        return self.git(self.repo, 'push', '-q', 'origin', *args, check=False, env=env)

    def branch(self, name='agent/task'):
        self.git(self.repo, 'switch', '-q', '-c', name)
        return name

    def refused(self, r, *names):
        self.assertNotEqual(r.returncode, 0, r.stderr)
        self.assertIn('pre-push: refusing', r.stderr)
        for name in names:
            self.assertIn(name, r.stderr)
        for value in (TOKEN, EMAIL, OTHER, NAME):
            self.assertNotIn(value, r.stderr + r.stdout)

    def on_remote(self, ref):
        return self.git(self.origin, 'rev-parse', '-q', '--verify', ref, check=False).returncode == 0

    # --- clean pushes pass --------------------------------------------------------------------

    def test_clean_push_passes(self):
        b = self.branch()
        self.commit('src/app.py', 'print("hello")\n', 'add app\n\n' + NOREPLY)
        r = self.push(b)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.on_remote('refs/heads/' + b))
        self.git(self.repo, 'switch', '-q', 'main')
        self.commit('docs/a.md', 'Write to someone' + '@' + 'example.com.\r\n', 'docs')
        self.assertEqual(self.push('main').returncode, 0)

    def test_already_pushed_content_is_not_judged_again(self):
        # main got an address and a token from a clone without the hook: already public
        other = os.path.join(self.dir, 'other')
        self.git(self.dir, 'clone', '-q', self.origin, other)
        self.commit('contacts.txt', OTHER + '\n' + TOKEN + '\n', 'contacts', repo=other)
        self.git(other, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'fetch', '-q', 'origin')
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a')
        self.git(self.repo, 'merge', '-q', '--no-edit', 'origin/main')
        r = self.push(b)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_deletion_needs_no_checks(self):
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a')
        self.assertEqual(self.push(b).returncode, 0)
        self.git(self.repo, 'switch', '-q', 'main')
        self.git(self.repo, 'merge', '-q', '--ff-only', b)
        self.assertEqual(self.push('main').returncode, 0)
        shutil.rmtree(self.clone)  # deleting sends no content: no scripts needed
        r = self.push('--delete', b)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_push_from_a_bare_repository_is_checked(self):
        bare = os.path.join(self.dir, 'mirror.git')
        self.git(self.dir, 'clone', '-q', '--bare', self.origin, bare)
        install_hook(bare, self.env)
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a')
        self.git(bare, 'fetch', '-q', self.repo, '%s:%s' % (b, b))  # a fetch runs no pre-push
        r = self.git(bare, 'push', '-q', self.origin, b, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.commit('b.txt', TOKEN + '\n', 'b')
        self.git(bare, 'fetch', '-q', self.repo, '%s:%s' % (b, b))
        r = self.git(bare, 'push', '-q', self.origin, b, check=False)
        self.refused(r, 'github-token', 'b.txt:1')

    # --- secrets ------------------------------------------------------------------------------

    def test_token_in_a_diff_is_refused(self):
        b = self.branch()
        self.commit('config/deploy.env.example', 'GITHUB=' + TOKEN + '\r\n', 'config')
        r = self.push(b)
        self.refused(r, 'github-token', 'config/deploy.env.example:1', 'secret scan')
        self.assertFalse(self.on_remote('refs/heads/' + b))

    def test_token_added_and_removed_again_is_refused(self):
        b = self.branch()
        self.commit('a.txt', TOKEN + '\n', 'oops')
        self.commit('a.txt', 'gone\n', 'remove it')
        self.refused(self.push(b), 'github-token', 'a.txt:1')

    def test_token_in_a_commit_message_is_refused(self):
        b = self.branch()
        self.commit('a.txt', 'a\n', 'use token ' + TOKEN)
        self.refused(self.push(b), 'github-token', 'commit message')

    def test_secret_in_a_merge_resolution_is_refused(self):
        b = self.branch()
        self.commit('f.txt', 'mine\n', 'mine')
        self.git(self.repo, 'switch', '-q', 'main')
        self.commit('f.txt', 'theirs\n', 'theirs')
        self.assertEqual(self.push('main').returncode, 0)
        self.git(self.repo, 'switch', '-q', b)
        self.git(self.repo, 'merge', '-q', 'main', check=False)  # conflict
        with open(os.path.join(self.repo, 'f.txt'), 'w', newline='') as f:
            f.write('resolved with ' + TOKEN + '\n')
        self.git(self.repo, 'add', '--', 'f.txt')
        self.git(self.repo, 'commit', '-q', '--no-edit')
        self.refused(self.push(b), 'github-token', 'f.txt')

    # --- personal data ------------------------------------------------------------------------

    def test_address_in_a_commit_message_is_refused(self):
        b = self.branch()
        self.commit('a.txt', 'a\n', 'fix\n\nReported-by: Jan <' + OTHER + '>')
        self.refused(self.push(b), 'personal data', 'commit message', 'e-mail address')

    def test_address_in_a_diff_is_refused(self):
        b = self.branch()
        self.commit('docs/team/contacts.md', '# Team\n\nmail ' + OTHER + '\n', 'contacts')
        self.refused(self.push(b), 'personal data', 'docs/team/contacts.md:3', 'e-mail address')

    def test_the_users_identifiers_in_a_diff_are_refused(self):
        b = self.branch()
        self.commit('NOTICE', 'Copyright 2026 ' + NAME + '\n', 'notice')
        self.refused(self.push(b), "the user's name", 'NOTICE:1')

    def test_the_commits_own_identity_in_its_message_passes(self):
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a\n\nSigned-off-by: %s <%s>\n%s' % (NAME, EMAIL, NOREPLY))
        r = self.push(b)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_address_in_an_annotated_tag_is_refused(self):
        self.git(self.repo, 'tag', '-a', 'v1', '-m', 'release for ' + OTHER)
        self.refused(self.push('v1'), 'personal data', 'tag message')

    def test_exempt_folder_skips_only_the_personal_data_check(self):
        with open(os.path.join(self.home, 'cfg', 'agentic-github-flow', 'exempt-dirs'), 'w') as f:
            f.write(self.repo + '\n')
        b = self.branch()
        self.commit('a.txt', OTHER + '\n', 'a')
        self.assertEqual(self.push(b).returncode, 0)
        self.commit('b.txt', TOKEN + '\n', 'b')
        self.refused(self.push(b), 'github-token')

    # --- protected paths, only for a push without the user's yes ------------------------------

    def unasked(self):
        return dict(self.env, AGENTIC_GITHUB_FLOW_UNASKED_PUSH='1')

    def test_protected_paths_pass_when_the_user_said_yes(self):
        b = self.branch()
        self.commit('.github/workflows/ci.yml', 'on: push\n', 'ci')
        self.commit('.claude/settings.json', '{}\n', 'settings')
        r = self.push(b)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_protected_paths_are_refused_without_the_users_yes(self):
        for rel in ('.github/workflows/ci.yml', '.claude/settings.local.json', 'rules/core.md',
                    'tools/installer.py', 'templates/pre-push', 'plugins/guards/hooks/hooks.json'):
            self.git(self.repo, 'switch', '-q', '-C', 'agent/p', 'main')
            self.commit(rel, 'changed\n', 'change ' + rel)
            r = self.push('agent/p', env=self.unasked())
            self.refused(r, 'protected path', rel)
        self.git(self.repo, 'switch', '-q', '-C', 'agent/clean', 'main')
        self.commit('src/app.py', 'x = 1\n', 'app')
        r = self.push('agent/clean', env=self.unasked())
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_manifest_version_bump_passes_without_the_users_yes(self):
        manifest = 'plugins/core/.claude-plugin/plugin.json'
        self.commit(manifest, '{"name": "core", "version": "1.0.0"}\n', 'manifest')
        self.assertEqual(self.push('main').returncode, 0)
        b = self.branch()
        self.commit(manifest, '{"name": "core", "version": "1.0.1"}\n', 'bump')
        r = self.push(b, env=self.unasked())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.commit(manifest, '{"name": "core", "version": "1.0.2", "hooks": "x"}\n', 'hook')
        self.refused(self.push(b, env=self.unasked()), 'protected path', manifest)

    # --- the checks cannot be skipped by a missing piece --------------------------------------

    def test_missing_clone_refuses(self):
        shutil.rmtree(self.clone)
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a')
        r = self.push(b)
        self.refused(r, 'cannot run', '.agentic-github-flow')

    def test_an_old_clone_refuses(self):
        script = os.path.join(self.clone, 'plugins', 'security', 'scripts', 'scan_secrets.py')
        with open(script, 'w') as f:
            f.write('import sys\nsys.exit(2)\n')  # a scanner without --commits: usage error
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a')
        self.refused(self.push(b), 'secret scan could not run')


class Units(unittest.TestCase):
    """The scripts' push entry points without a hook around them."""

    def test_personal_data_hook_mode_is_unchanged_by_the_new_entry_point(self):
        hook = os.path.join(ROOT, 'plugins', 'guards', 'scripts', 'pre_tool_personal_data.py')
        r = subprocess.run([sys.executable, hook, '--commits'], input='', capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 2)  # the push mode needs the remote's URL
        r = subprocess.run([sys.executable, hook, '--bogus'], input='{}', capture_output=True,
                           text=True)
        self.assertEqual((r.returncode, r.stdout), (0, ''))  # hook mode: a wiring mistake passes


if __name__ == '__main__':
    unittest.main()
