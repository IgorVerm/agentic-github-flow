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
import importlib.util
import os
import shutil
import struct
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
# model bytes of a .glb that read as an address (#55: `lacus_early.glb` in pax_deorum)
MODEL_ADDRESS = 'D-D.D' + '@' + 'DAD.DAD'


def glb(*runs):
    """A .glb-like binary file: the glTF header, NUL bytes, noise and the given byte runs."""
    body = b''.join(b'\x00\x01\xfe\x9c ' + run.encode('ascii') + b' \x00\x00\xa7' for run in runs)
    return b'glTF' + struct.pack('<II', 2, 12 + len(body)) + body


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

    def commit_bytes(self, rel, data, message):
        path = os.path.join(self.repo, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        self.git(self.repo, 'add', '--', rel)
        self.git(self.repo, 'commit', '-q', '-m', message)

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
        for value in (TOKEN, EMAIL, OTHER, NAME, 'fixture' + '@' + 'work-place.be'):
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

    def test_text_after_a_lone_carriage_return_is_read(self):
        b = self.branch()
        self.commit('log.txt', 'progress\rexport GH=' + TOKEN + '\n', 'log')
        self.refused(self.push(b), 'github-token', 'log.txt:1')
        self.git(self.repo, 'switch', '-q', '-C', 'agent/cr', 'main')
        self.commit('log.txt', 'step\rcontact ' + OTHER + '\n', 'log')
        self.refused(self.push('agent/cr'), 'e-mail address', 'log.txt:1')

    def test_rename_to_a_secret_file_name_is_refused(self):
        self.commit('notes.txt', 'just notes\n', 'notes')
        self.assertEqual(self.push('main').returncode, 0)
        b = self.branch()
        self.git(self.repo, 'mv', 'notes.txt', '.env')
        self.git(self.repo, 'commit', '-q', '-m', 'rename')
        self.refused(self.push(b), 'secret-file-name', '.env')

    def test_utf16_text_is_read(self):
        b = self.branch()
        for name, text, rule in (('ps.txt', 'GH=' + TOKEN, 'github-token'),
                                 ('mail.txt', 'mail ' + OTHER, 'e-mail address')):
            self.git(self.repo, 'switch', '-q', '-C', b, 'main')
            with open(os.path.join(self.repo, name), 'wb') as f:
                f.write(('\ufeff' + text + '\r\n').encode('utf-16-le'))
            self.git(self.repo, 'add', '--', name)
            self.git(self.repo, 'commit', '-q', '-m', name)
            self.refused(self.push(b), rule, name)

    # --- binary files (#55): their content is not read, their names are ---------------------

    def test_binary_file_content_is_not_read(self):
        b = self.branch()
        self.commit_bytes('models/lacus_early.glb', glb(MODEL_ADDRESS, OTHER, TOKEN, 'GH=' + TOKEN),
                          'model')
        self.commit_bytes('models/lacus_early.glb', glb(TOKEN, MODEL_ADDRESS, OTHER), 'remodel')
        r = self.push(b)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_utf16_and_plain_text_are_still_read(self):
        for codec, bom in (('utf-16-le', True), ('utf-16-le', False), ('utf-16-be', True),
                           ('utf-16-be', False), ('utf-8', False)):
            for text, rule in (('GH=' + TOKEN, 'github-token'),
                               ('mail ' + OTHER, 'e-mail address')):
                self.git(self.repo, 'switch', '-q', '-C', 'agent/u', 'main')
                data = (('\ufeff' if bom else '') + 'notes\r\n' + text + '\r\n').encode(codec)
                self.commit_bytes('out.txt', data, 'out')
                self.refused(self.push('agent/u'), rule, 'out.txt:2')

    def test_a_binary_files_name_is_still_judged(self):
        for name, rule in (('models/' + OTHER + '.glb', 'e-mail address'),
                           ('models/' + TOKEN + '.glb', 'github-token'),
                           ('deploy/.env', 'secret-file-name')):
            self.git(self.repo, 'switch', '-q', '-C', 'agent/n', 'main')
            self.commit_bytes(name, glb('mesh'), 'model')
            self.refused(self.push('agent/n'), rule)

    def test_a_file_that_is_text_in_one_commit_is_read_there(self):
        for text, rule in (('GH=' + TOKEN, 'github-token'), ('mail ' + OTHER, 'e-mail address')):
            self.git(self.repo, 'switch', '-q', '-C', 'agent/t', 'main')
            self.commit_bytes('data.bin', (text + '\n').encode('ascii'), 'text first')
            self.commit_bytes('data.bin', glb('mesh'), 'then binary')
            self.refused(self.push('agent/t'), rule, 'data.bin:1')
            self.git(self.repo, 'switch', '-q', '-C', 'agent/b', 'main')
            self.commit_bytes('data.bin', glb('mesh'), 'binary first')
            self.commit_bytes('data.bin', (text + '\n').encode('ascii'), 'then text')
            self.refused(self.push('agent/b'), rule, 'data.bin:1')

    def test_blob_and_tree_pushes_are_refused(self):
        blob = \
            subprocess.run(['git', 'hash-object', '-w', '--stdin'], cwd=self.repo, env=self.env,
                           input=TOKEN + '\n', capture_output=True, text=True).stdout.strip()
        self.refused(self.push(blob + ':refs/blobs/x'), 'not a commit')
        self.git(self.repo, 'tag', 'blobtag', blob)
        self.refused(self.push('blobtag'), 'not a commit')
        self.git(self.repo, 'tag', '-a', '-m', 'on a blob', 'blobtag2', blob)
        self.refused(self.push('blobtag2'), 'not a commit')
        tree = self.git(self.repo, 'rev-parse', 'HEAD^{tree}').stdout.strip()
        self.refused(self.push(tree + ':refs/trees/x'), 'not a commit')

    def test_log_encoding_setting_does_not_blind_the_message_checks(self):
        self.git(self.repo, 'config', 'i18n.logOutputEncoding', 'UTF-16LE')
        b = self.branch()
        self.commit('a.txt', 'a\n', 'use ' + TOKEN + ' and ' + OTHER)
        self.refused(self.push(b), 'github-token', 'commit message')

    def test_push_url_other_than_the_fetch_url_trusts_no_tracking_refs(self):
        # main as fetched from the private origin holds a token; pushes go to a public repository
        other = os.path.join(self.dir, 'other')
        self.git(self.dir, 'clone', '-q', self.origin, other)
        self.commit('k.txt', TOKEN + '\n', 'k', repo=other)
        self.git(other, 'push', '-q', 'origin', 'main')
        self.git(self.repo, 'fetch', '-q', 'origin')
        self.git(self.repo, 'merge', '-q', '--ff-only', 'origin/main')
        public = os.path.join(self.dir, 'public.git')
        self.git(self.dir, 'init', '-q', '--bare', public)
        self.git(self.repo, 'config', 'remote.origin.pushurl', public)
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a')
        self.refused(self.push(b), 'github-token', 'k.txt:1')

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

    def test_address_or_token_in_a_file_name_is_refused_and_not_printed(self):
        b = self.branch()
        self.commit('contacts/' + OTHER + '.md', 'hello\n', 'contact')
        self.refused(self.push(b), 'e-mail address', '(a file name)')
        self.git(self.repo, 'switch', '-q', '-C', 'agent/t', 'main')
        self.commit('k/' + TOKEN + '.txt', 'GH=' + TOKEN + '\n', 'k')
        self.refused(self.push('agent/t'), 'github-token', '(a file name)')
        # an empty file shows no `+++` header in a diff: its name is still read
        for name, rule in (('users/' + OTHER + '/.gitkeep', 'e-mail address'),
                           ('k/' + TOKEN, 'github-token'), ('deploy/.env', 'secret-file-name')):
            self.git(self.repo, 'switch', '-q', '-C', 'agent/e', 'main')
            self.commit(name, '', 'empty')
            self.refused(self.push('agent/e'), rule)

    def test_someone_elses_address_as_author_is_refused(self):
        b = self.branch()
        with open(os.path.join(self.repo, 'a.txt'), 'w') as f:
            f.write('a\n')
        self.git(self.repo, 'add', '--', 'a.txt')
        self.git(self.repo, 'commit', '-q', '-m', 'a', '--author', 'Jan <' + OTHER + '>')
        self.refused(self.push(b), 'e-mail address', 'author or committer')

    def test_a_repository_identity_as_author_passes(self):
        local = 'fixture' + '@' + 'work-place.be'
        self.git(self.repo, 'config', 'user.email', local)
        b = self.branch()
        self.commit('a.txt', 'a\n', 'a')
        r = self.push(b)
        self.assertEqual(r.returncode, 0, r.stderr)

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

    def test_both_checks_tell_binary_files_alike(self):
        # the two plugins are installed apart, so each holds its own copy of the classifier
        def load(rel):
            spec = importlib.util.spec_from_file_location(rel.replace('/', '_'),
                                                          os.path.join(ROOT, *rel.split('/')))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module.skipped_binary
        secrets = load('plugins/security/scripts/scan_secrets.py')
        personal = load('plugins/guards/scripts/pre_tool_personal_data.py')
        text = 'GH=' + TOKEN + ' mail ' + OTHER + '\r\n'
        cases = [
            (glb(MODEL_ADDRESS, TOKEN), True),
            (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + bytes(range(256)) * 8, True),
            (b'\x00' * 64, True),
            (b'\xff\xfe' + bytes(range(256)) * 4, False),  # a byte-order mark: read as UTF-16
            (('\ufeff' + text).encode('utf-16-le'), False),
            (('\ufeff' + text).encode('utf-16-be'), False),
            ((text * 400).encode('utf-16-le'), False),  # no mark, past the first 8000 bytes
            ((text * 400).encode('utf-16-be'), False),
            (('Caf\u00e9 na\u00efef ' + text).encode('utf-16-le'), False),
            (text.encode('utf-8'), False),
            ('caf\u00e9 \u2014 ok\n'.encode('utf-8'), False),
            (b'', False),
            (b'a' * 8000 + b'\x00tail', False),  # git reads only the first 8000 bytes
            (b'a' * 7999 + b'\x00tail', True),
        ]
        for data, skipped in cases:
            self.assertEqual((secrets(data), personal(data)), (skipped, skipped), data[:40])
        twins = []
        for rel in ('plugins/security/scripts/scan_secrets.py',
                    'plugins/guards/scripts/pre_tool_personal_data.py'):
            with open(os.path.join(ROOT, *rel.split('/')), encoding='utf-8') as f:
                text = f.read()
            start = text.index('FIRST_FEW_BYTES = ')
            twins.append(text[start:text.index('\n', text.index('NEW_BLOB = ', start))])
        self.assertEqual(twins[0], twins[1], 'the binary-file code of the two checks differs')


if __name__ == '__main__':
    unittest.main()
