#!/usr/bin/env python3
"""Checks the installer in temporary home folders: python3 tests/installer.py [--real].

Each case gets a fresh HOME (USERPROFILE on Windows) and a source repository made from this
checkout's files, which the installer clones the way a colleague's machine clones GitHub. It runs
the real entry point: install.sh on macOS and Linux, install.ps1 on Windows. By default `claude`
and `codex` are stand-ins that record their plugin state in a JSON file, so the test runs offline
and anywhere; with --real it uses the installed clients instead (CLAUDE=<path>, CODEX=<path> to
point at them), still in the temporary homes, and checks the plugins they report.

Cases: install over existing files, an idempotent second run, --update after a change in the
source, --uninstall leaving CLAUDE.md and AGENTS.md byte-identical (or absent when they were),
a symlinked ~/.codex/AGENTS.md refused before any change, a missing client skipped, --guards
merging and removing the settings, rules and hooks (the git guard and the personal-data hook in
~/.codex/hooks.json beside the user's own entries, the latter added by --update to an older
install), the Codex rules as regular copies (refreshed by
--update, a link of an earlier version replaced, a changed copy left by --uninstall), --with
issue-chats installed beside core in both clients and kept on a plain rerun, an unknown plugin
refused, and an overlay in both blocks.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
WINDOWS = os.name == 'nt'
REAL = '--real' in sys.argv
if REAL:
    sys.argv.remove('--real')
BEGIN = '<!-- >>> agentic-github-flow >>> -->'
CORE_TITLE = '# agentic-github-flow: rules for every session'
PD_MATCHER = r'^(Bash|webrun|web\.run|mcp__.*)$'  # what the personal-data hook judges in Codex
BUNDLED_CODEX = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'

FAKE = r'''import json, os, sys
client = sys.argv[1]
args = sys.argv[2:]
path = os.path.join(os.environ['FAKE_CLIENT_STATE'], client + '.json')
try:
    state = json.load(open(path))
except (OSError, ValueError):
    state = {'marketplaces': {}, 'plugins': {}, 'calls': []}
state['calls'].append(args)
def done(code=0, out=''):
    if out:
        print(out)
    json.dump(state, open(path, 'w'), indent=1)
    sys.exit(code)
if args[:3] == ['plugin', 'marketplace', 'list']:
    items = [{'name': n, 'path': p} for n, p in state['marketplaces'].items()]
    done(0, json.dumps(items if client == 'claude' else {'marketplaces': items}))
if args[:3] == ['plugin', 'marketplace', 'add']:
    source = args[3]
    with open(os.path.join(source, '.claude-plugin', 'marketplace.json')) as f:
        name = json.load(f)['name']
    if name in state['marketplaces']:
        done(1, 'already added')
    state['marketplaces'][name] = source
    done(0, 'added ' + name)
if args[:3] in (['plugin', 'marketplace', 'remove'], ['plugin', 'marketplace', 'rm']):
    done(0 if state['marketplaces'].pop(args[3], None) else 1)
if args[:3] == ['plugin', 'marketplace', 'update']:
    done(0 if args[3] in state['marketplaces'] else 1)
if args[:2] in (['plugin', 'install'], ['plugin', 'add'], ['plugin', 'update']):
    name, market = args[2].split('@')
    if market not in state['marketplaces']:
        done(1, 'unknown marketplace')
    folder = os.path.join(state['marketplaces'][market], 'plugins', name.replace('agentic-github-flow-', ''))
    with open(os.path.join(folder, '.claude-plugin', 'plugin.json')) as f:
        version = json.load(f)['version']
    if args[1] == 'update' and name not in state['plugins']:
        done(1, 'not installed')
    state['plugins'][name] = version
    done(0, 'installed %s %s' % (name, version))
if args[:2] in (['plugin', 'uninstall'], ['plugin', 'remove']):
    done(0 if state['plugins'].pop(args[2].split('@')[0], None) else 1)
done(2, 'fake %s: unsupported %s' % (client, args))
'''


def source_repo(dest):
    """A git repository holding this checkout's files as they are now."""
    listed = subprocess.run(['git', '-C', ROOT, 'ls-files', '-z', '--cached', '--others',
                             '--exclude-standard'], capture_output=True, text=True)
    files = [p for p in listed.stdout.split('\0') if p and os.path.isfile(os.path.join(ROOT, p))]
    for rel in files:
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(ROOT, rel), target)
    return files


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = os.path.realpath(tempfile.mkdtemp(prefix='agf-installer-'))
        config = os.path.join(cls.base, 'gitconfig')
        # No automatic maintenance: once the source repository holds enough loose objects, the
        # commit below starts a detached `git maintenance run --auto` that packs them while the
        # installer clones, and the clone fails on a vanished object (measured with git 2.54).
        with open(config, 'w') as f:
            f.write('[maintenance]\n\tauto = false\n[gc]\n\tauto = 0\n')
        cls.git_env = {'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': config,
                       'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.invalid',
                       'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.invalid'}
        cls.source = os.path.join(cls.base, 'source')
        files = source_repo(cls.source)
        cls.sgit('init', '-q', '-b', 'main')
        cls.sgit('add', '--', *files)
        cls.sgit('commit', '-q', '-m', 'source')
        cls.fakebin = os.path.join(cls.base, 'fakebin')
        os.makedirs(cls.fakebin)
        fake = os.path.join(cls.base, 'fake_client.py')
        with open(fake, 'w') as f:
            f.write(FAKE)
        for client in ('claude', 'codex'):
            if WINDOWS:
                with open(os.path.join(cls.fakebin, client + '.cmd'), 'w') as f:
                    f.write('@"%s" "%s" %s %%*\r\n' % (sys.executable, fake, client))
            else:
                path = os.path.join(cls.fakebin, client)
                with open(path, 'w') as f:
                    f.write('#!/bin/sh\nexec "%s" "%s" %s "$@"\n' % (sys.executable, fake, client))
                os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    @classmethod
    def sgit(cls, *args):
        subprocess.run(['git', '-C', cls.source, *args], check=True, capture_output=True,
                       env=dict(os.environ, **cls.git_env))

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix='home-', dir=self.base)
        self.state_dir = os.path.join(self.home, '.fake-state')
        os.makedirs(self.state_dir)
        self.clients = ['claude', 'codex']
        self.extra = []
        if REAL:
            codex = os.environ.get('CODEX') or shutil.which('codex') or (
                BUNDLED_CODEX if os.path.exists(BUNDLED_CODEX) else None)
            if codex and not shutil.which('codex'):
                self.extra = ['--codex-bin', codex]

    # helpers
    def env(self, clients=None):
        clients = self.clients if clients is None else clients
        env = {k: v for k, v in os.environ.items()
               if k not in ('CLAUDE_CONFIG_DIR', 'CODEX_HOME', 'XDG_CONFIG_HOME')}
        env.update(self.git_env, HOME=self.home, USERPROFILE=self.home,
                   AGENTIC_GITHUB_FLOW_REPO=self.source, FAKE_CLIENT_STATE=self.state_dir)
        if not REAL:
            paths = [p for p in env.get('PATH', '').split(os.pathsep) if p and not any(
                os.path.exists(os.path.join(p, c + ext)) for c in ('claude', 'codex')
                for ext in ('', '.cmd', '.exe'))]
            only = os.path.join(self.home, '.fakebin-%s' % '-'.join(clients))
            if not os.path.isdir(only):
                os.makedirs(only)
                for name in os.listdir(self.fakebin):
                    if name.split('.')[0] in clients:
                        shutil.copy2(os.path.join(self.fakebin, name), only)
            env['PATH'] = os.pathsep.join([only] + paths)
        return env

    def install(self, *args, clients=None):
        if WINDOWS:
            entry = os.path.join(self.source, 'install.ps1')
            command = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', entry]
        else:
            command = ['bash', os.path.join(self.source, 'install.sh')]
        r = subprocess.run(command + list(args) + self.extra, cwd=self.home,
                           env=self.env(clients), capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout + r.stderr

    def path(self, *parts):
        return os.path.join(self.home, *parts)

    def read(self, *parts):
        try:
            with open(self.path(*parts), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return None

    def write(self, data, *parts):
        os.makedirs(os.path.dirname(self.path(*parts)), exist_ok=True)
        with open(self.path(*parts), 'wb') as f:
            f.write(data)

    def plugins(self, client):
        if REAL:
            return self.real_plugins(client)
        try:
            with open(os.path.join(self.state_dir, client + '.json')) as f:
                return json.load(f)['plugins']
        except OSError:
            return {}

    def real_plugins(self, client):
        env = self.env()
        if client == 'claude':
            r = subprocess.run([shutil.which('claude'), 'plugin', 'list', '--json'],
                               capture_output=True, text=True, env=env, cwd=self.home)
            items = json.loads(r.stdout or '[]')
            items = items if isinstance(items, list) else items.get('plugins', [])
            return {i.get('id', i.get('name', '')).split('@')[0]: i.get('version') for i in items}
        codex = self.extra[1] if self.extra else shutil.which('codex')
        r = subprocess.run([codex, 'plugin', 'list'], capture_output=True, text=True, env=env,
                           cwd=self.home)
        found = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if parts and '@agentic-github-flow' in parts[0] and 'installed,' in line:
                found[parts[0].split('@')[0]] = None
        return found

    # cases
    def test_install_update_uninstall_round_trip(self):
        claude_before = b'# My own notes\r\nKeep this line.'  # CRLF, no newline at the end
        codex_before = b'Codex notes\n'
        self.write(claude_before, '.claude', 'CLAUDE.md')
        self.write(codex_before, '.codex', 'AGENTS.md')
        code, out = self.install()
        self.assertEqual(code, 0, out)
        claude_md = self.read('.claude', 'CLAUDE.md').decode()
        self.assertTrue(claude_md.startswith(claude_before.decode() + '\n' + BEGIN), claude_md)
        self.assertIn('@~/.agentic-github-flow/rules/core.md', claude_md)
        codex_md = self.read('.codex', 'AGENTS.md').decode()
        self.assertTrue(codex_md.startswith(codex_before.decode() + BEGIN))
        self.assertEqual(codex_md.count(CORE_TITLE), 1)
        for client in ('claude', 'codex'):
            self.assertIn('agentic-github-flow-core', self.plugins(client), out)

        first = (self.read('.claude', 'CLAUDE.md'), self.read('.codex', 'AGENTS.md'))
        code, out = self.install()
        self.assertEqual(code, 0, out)
        self.assertEqual((self.read('.claude', 'CLAUDE.md'), self.read('.codex', 'AGENTS.md')),
                         first, 'a second run must not change the files')

        clone = self.path('.agentic-github-flow')
        rules = os.path.join(self.source, 'rules', 'core.md')
        with open(rules, encoding='utf-8') as f:
            text = f.read()
        try:
            with open(rules, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text.replace('## Memory', 'UPDATED-RULE-MARKER\n\n## Memory'))
            self.sgit('commit', '-q', '-m', 'change the rules', '--', 'rules/core.md')
            code, out = self.install('--update')
            self.assertEqual(code, 0, out)
            self.assertIn('UPDATED-RULE-MARKER', self.read('.codex', 'AGENTS.md').decode())
            with open(os.path.join(clone, 'rules', 'core.md'), encoding='utf-8') as f:
                self.assertIn('UPDATED-RULE-MARKER', f.read())
        finally:
            with open(rules, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
            self.sgit('commit', '-q', '-m', 'restore the rules', '--', 'rules/core.md')

        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read('.claude', 'CLAUDE.md'), claude_before)
        self.assertEqual(self.read('.codex', 'AGENTS.md'), codex_before)
        for client in ('claude', 'codex'):
            self.assertEqual({k: v for k, v in self.plugins(client).items()
                              if k.startswith('agentic-github-flow')}, {})
        self.assertFalse(os.path.exists(os.path.join(clone, '.state', 'install.json')))

    def test_files_absent_before_are_absent_after(self):
        code, out = self.install('--with', 'web-deploy')
        self.assertEqual(code, 0, out)
        for client in ('claude', 'codex'):
            self.assertLessEqual({'agentic-github-flow-core', 'agentic-github-flow-security',
                                  'agentic-github-flow-web-deploy'}, set(self.plugins(client)))
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        self.assertIsNone(self.read('.claude', 'CLAUDE.md'))
        self.assertIsNone(self.read('.codex', 'AGENTS.md'))

    def test_issue_chats_with_core_kept_on_a_plain_rerun_and_removed(self):
        code, out = self.install('--with', 'issue-chats')
        self.assertEqual(code, 0, out)
        wanted = {'agentic-github-flow-core', 'agentic-github-flow-issue-chats'}
        for client in ('claude', 'codex'):
            self.assertLessEqual(wanted, set(self.plugins(client)), out)
            self.assertNotIn('agentic-github-flow-guards', self.plugins(client))
        code, out = self.install()  # a plain second run keeps what the first installed
        self.assertEqual(code, 0, out)
        for client in ('claude', 'codex'):
            self.assertLessEqual(wanted, set(self.plugins(client)), out)
        settings = self.read('.claude', 'settings.json')
        if settings:  # the installer adds no permission rule for the plugin's scripts
            self.assertNotIn(b'start_issue_chat', settings)
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        for client in ('claude', 'codex'):
            self.assertEqual({k for k in self.plugins(client) if k.startswith('agentic-github-flow')},
                             set())

    def test_unknown_plugin_is_refused(self):
        code, out = self.install('--with', 'issue-chat')
        self.assertEqual(code, 2, out)
        self.assertIn('issue-chats', out)
        self.assertIsNone(self.read('.claude', 'CLAUDE.md'))

    @unittest.skipIf(WINDOWS, 'creating a symlink needs extra rights on Windows')
    def test_symlinked_codex_agents_md_is_refused_before_any_change(self):
        target = self.path('dotfiles', 'AGENTS.md')
        self.write(b'shared rules\n', 'dotfiles', 'AGENTS.md')
        os.makedirs(self.path('.codex'))
        os.symlink(target, self.path('.codex', 'AGENTS.md'))
        self.write(b'mine\n', '.claude', 'CLAUDE.md')
        code, out = self.install()
        self.assertEqual(code, 3, out)
        self.assertIn('is a symlink', out)
        self.assertEqual(self.read('dotfiles', 'AGENTS.md'), b'shared rules\n')
        self.assertEqual(self.read('.claude', 'CLAUDE.md'), b'mine\n')
        self.assertEqual(self.plugins('claude'), {})
        code, out = self.install('--no-codex')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read('dotfiles', 'AGENTS.md'), b'shared rules\n')

    @unittest.skipIf(REAL, 'needs a client to be absent')
    def test_missing_client_is_skipped(self):
        code, out = self.install(clients=['claude'])
        self.assertEqual(code, 0, out)
        self.assertIn('codex: neither the `codex` command', out)
        self.assertIsNone(self.read('.codex', 'AGENTS.md'))
        self.assertIn('agentic-github-flow-core', self.plugins('claude'))

    def test_guards_merge_and_unmerge(self):
        settings = {'model': 'example', 'permissions': {'deny': ['Bash(git reset --hard*)'],
                                                        'allow': ['Bash(ls*)']}}
        self.write(json.dumps(settings).encode(), '.claude', 'settings.json')
        os.makedirs(self.path('.codex'))
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        merged = json.loads(self.read('.claude', 'settings.json'))
        self.assertEqual(merged['model'], 'example')
        self.assertEqual(merged['permissions']['allow'], ['Bash(ls*)'])
        self.assertIn('Bash(git push --force*)', merged['permissions']['deny'])
        self.assertEqual(merged['permissions']['deny'].count('Bash(git reset --hard*)'), 1)
        self.assertIn('agentic-github-flow-guards', self.plugins('claude'))
        self.assertNotIn('agentic-github-flow-guards', self.plugins('codex'))
        hooks = json.loads(self.read('.codex', 'hooks.json'))
        command = hooks['hooks']['PreToolUse'][0]['hooks'][0]['command']
        self.assertIn('pre_tool_git_guard.py', command)
        self.assertEqual(self.codex_personal_data_entries(), [PD_MATCHER])
        # the delete guard can only ask, which Codex hooks cannot: it stays out of Codex
        self.assertNotIn(b'pre_tool_delete_guard.py', self.read('.codex', 'hooks.json'))
        rules = self.path('.codex', 'rules', 'agentic-github-flow-git-safety.rules')
        self.assertTrue(os.path.exists(rules))
        self.assertTrue(any(n.startswith('settings.json.agentic-github-flow-backup-')
                            for n in os.listdir(self.path('.claude'))))
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        after = json.loads(self.read('.claude', 'settings.json'))
        for key in ('enabledPlugins', 'extraKnownMarketplaces'):  # the client's own bookkeeping
            if after.get(key) == {}:
                del after[key]
        self.assertEqual(after, settings)
        self.assertIsNone(self.read('.codex', 'hooks.json'))
        self.assertFalse(os.path.lexists(rules))

    def codex_personal_data_entries(self):
        """The matchers of the ~/.codex/hooks.json entries that run the personal-data hook."""
        data = json.loads(self.read('.codex', 'hooks.json') or b'{}')
        found = []
        for entry in data.get('hooks', {}).get('PreToolUse', []):
            for hook in entry['hooks']:
                if 'pre_tool_personal_data.py' in hook['command']:
                    self.assertTrue(hook['command'].endswith('pre_tool_personal_data.py" --codex'),
                                    hook['command'])
                    self.assertEqual(hook['timeout'], 10)
                    found.append(entry['matcher'])
        return found

    def test_codex_personal_data_hook_beside_the_users_own_hooks(self):
        own = {'hooks': {'PreToolUse': [{'matcher': 'Bash', 'hooks': [
            {'type': 'command', 'command': 'my-own-hook', 'timeout': 5}]}]}, 'other': 1}
        self.write(json.dumps(own).encode(), '.codex', 'hooks.json')
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        entries = json.loads(self.read('.codex', 'hooks.json'))['hooks']['PreToolUse']
        self.assertEqual(entries[0], own['hooks']['PreToolUse'][0])
        self.assertEqual(len(entries), 3, entries)
        self.assertEqual(self.codex_personal_data_entries(), [PD_MATCHER])
        self.assertIn('personal-data guard added', out)
        # an install recorded before the personal-data hook existed gets it on --update, once
        state_file = self.path('.agentic-github-flow', '.state', 'install.json')
        with open(state_file, encoding='utf-8') as f:
            state = json.load(f)
        state.pop('codex_personal_data_hook')
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        data = json.loads(self.read('.codex', 'hooks.json'))
        data['hooks']['PreToolUse'] = [e for e in data['hooks']['PreToolUse']
                                       if 'pre_tool_personal_data.py' not in json.dumps(e)]
        self.write(json.dumps(data).encode(), '.codex', 'hooks.json')
        code, out = self.install('--update')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.codex_personal_data_entries(), [PD_MATCHER])
        code, out = self.install('--update')
        self.assertEqual(code, 0, out)
        self.assertEqual(len(json.loads(self.read('.codex', 'hooks.json'))['hooks']['PreToolUse']),
                         3)
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(self.read('.codex', 'hooks.json')), own)

    def rules_copies(self):
        folder = self.path('.codex', 'rules')
        return [(os.path.join(folder, 'agentic-github-flow-' + name),
                 os.path.join(self.source, 'plugins', 'guards', 'policy', name))
                for name in ('git-safety.rules', 'delete-guard.rules')]

    def test_codex_rules_are_copies_refreshed_and_removed_only_unchanged(self):
        # Codex skips a symlinked .rules file without a warning: both must be regular copies
        os.makedirs(self.path('.codex'))
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        (git_copy, git_source), (delete_copy, delete_source) = self.rules_copies()
        for copy, source in self.rules_copies():
            self.assertTrue(os.path.isfile(copy) and not os.path.islink(copy), copy)
            with open(copy, 'rb') as a, open(source, 'rb') as b:
                self.assertEqual(a.read(), b.read())
        with open(delete_source, encoding='utf-8') as f:
            text = f.read()
        try:
            with open(delete_source, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text + '# UPDATED-RULES-MARKER\n')
            self.sgit('commit', '-q', '-m', 'change the rules', '--',
                      'plugins/guards/policy/delete-guard.rules')
            code, out = self.install('--update')
            self.assertEqual(code, 0, out)
            with open(delete_copy, 'rb') as f:
                self.assertIn(b'UPDATED-RULES-MARKER', f.read())
            self.assertFalse(os.path.islink(delete_copy))
        finally:
            with open(delete_source, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
            self.sgit('commit', '-q', '-m', 'restore the rules', '--',
                      'plugins/guards/policy/delete-guard.rules')
        with open(git_copy, 'ab') as f:
            f.write(b'# a line the user added\n')
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(git_copy), 'a changed copy must stay')
        self.assertIn('changed since the install', out)
        self.assertIn('Codex keeps loading it', out)
        self.assertFalse(os.path.lexists(delete_copy))
        # a later install recognises the copy it left, keeps the edit, and does not refuse
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        with open(git_copy, 'rb') as f:
            self.assertIn(b'a line the user added', f.read())
        self.assertTrue(os.path.isfile(delete_copy))

    def legacy_install(self, content):
        """An install whose record names the git rules by path alone, as 0.1 wrote it, with
        content in that copy (0.1 copied the file on Windows) and no delete rules yet."""
        os.makedirs(self.path('.codex'))
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        (git_copy, _), (delete_copy, _) = self.rules_copies()
        record = self.path('.agentic-github-flow', '.state', 'install.json')
        with open(record, encoding='utf-8') as f:
            state = json.load(f)
        state['codex_rules'] = git_copy
        with open(record, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        with open(git_copy, 'wb') as f:
            f.write(content)
        os.remove(delete_copy)

    def rules_of_0_1(self):
        # git-safety.rules as 0.1 shipped it (commit d0edd54), kept as a fixture so a shallow
        # clone runs these cases too
        with open(os.path.join(HERE, 'fixtures', 'git-safety-0.1.rules'), 'rb') as f:
            return f.read()

    def test_legacy_hashes_are_the_0_1_rules(self):
        # the installer knows the 0.1 rules by these hashes, with LF and with CRLF endings
        spec = importlib.util.spec_from_file_location(
            'installer_module', os.path.join(ROOT, 'tools', 'installer.py'))
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        rules = self.rules_of_0_1()
        self.assertNotIn(b'\r', rules)
        self.assertEqual({hashlib.sha256(rules).hexdigest(),
                          hashlib.sha256(rules.replace(b'\n', b'\r\n')).hexdigest()},
                         installer.LEGACY_HASHES)

    def test_rules_copy_recorded_by_path_alone_is_refreshed_and_removed(self):
        # 0.1 recorded the git rules by path and copied them on Windows: a copy that still
        # holds the 0.1 rules is the installer's own
        self.legacy_install(self.rules_of_0_1())
        (git_copy, git_source), (delete_copy, _) = self.rules_copies()
        code, out = self.install('--update')
        self.assertEqual(code, 0, out)
        with open(git_copy, 'rb') as a, open(git_source, 'rb') as b:
            self.assertEqual(a.read(), b.read())
        self.assertTrue(os.path.isfile(delete_copy))
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.lexists(git_copy))
        self.assertFalse(os.path.lexists(delete_copy))

    def test_edited_rules_copy_recorded_by_path_alone_survives(self):
        edited = self.rules_of_0_1() + b'# a line the user added\n'
        self.legacy_install(edited)
        (git_copy, _), (delete_copy, _) = self.rules_copies()
        code, out = self.install('--update')
        self.assertEqual(code, 0, out)
        self.assertIn('changed since the install', out)
        with open(git_copy, 'rb') as f:
            self.assertEqual(f.read(), edited)
        self.assertTrue(os.path.isfile(delete_copy))
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        with open(git_copy, 'rb') as f:
            self.assertEqual(f.read(), edited)
        self.assertFalse(os.path.lexists(delete_copy))

    @unittest.skipIf(WINDOWS, 'creating a symlink needs extra rights on Windows')
    def test_rules_link_of_an_earlier_version_becomes_a_copy(self):
        os.makedirs(self.path('.codex'))
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        (git_copy, _), _ = self.rules_copies()
        record = self.path('.agentic-github-flow', '.state', 'install.json')
        with open(record, encoding='utf-8') as f:
            state = json.load(f)
        state['codex_rules'] = git_copy  # the earlier record: one linked file
        with open(record, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        os.remove(git_copy)
        os.symlink(self.path('.agentic-github-flow', 'plugins', 'guards', 'policy',
                             'git-safety.rules'), git_copy)
        os.remove(self.rules_copies()[1][0])
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        for copy, _ in self.rules_copies():
            self.assertTrue(os.path.isfile(copy) and not os.path.islink(copy), copy)

    @unittest.skipIf(WINDOWS, 'creating a symlink needs extra rights on Windows')
    def test_uninstall_does_not_write_through_symlinked_settings(self):
        os.makedirs(self.path('.codex'))
        code, out = self.install('--guards')
        self.assertEqual(code, 0, out)
        moved = {}
        for folder, name in (('.claude', 'settings.json'), ('.codex', 'hooks.json')):
            target = self.path('dotfiles', name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(self.path(folder, name), target)
            os.symlink(target, self.path(folder, name))
            moved[target] = self.read('dotfiles', name)
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count('is a symlink'), 2, out)
        for target, before in moved.items():
            with open(target, 'rb') as f:
                after = f.read()
            if REAL:  # the real Claude CLI edits its own keys through the link; ours stay
                self.assertEqual(json.loads(after).get('permissions'),
                                 json.loads(before).get('permissions'), target)
            else:
                self.assertEqual(after, before, target)
        self.assertTrue(os.path.islink(self.path('.claude', 'settings.json')))

    @unittest.skipIf(REAL, 'a stand-in case: two overlay repositories with the same name')
    def test_overlays_with_the_same_name_stay_apart(self):
        urls = []
        for team in ('team-a', 'team-b'):
            repo = os.path.join(self.home, team, 'overlay')
            os.makedirs(repo)
            with open(os.path.join(repo, 'AGENTS.md'), 'w') as f:
                f.write('# %s\n\nMARKER-%s\n' % (team, team))
            env = dict(os.environ, **self.git_env)
            subprocess.run(['git', '-C', repo, 'init', '-q', '-b', 'main'], check=True, env=env)
            subprocess.run(['git', '-C', repo, 'add', '--', 'AGENTS.md'], check=True, env=env)
            subprocess.run(['git', '-C', repo, 'commit', '-q', '-m', 'x'], check=True, env=env)
            posix = repo.replace('\\', '/')
            urls.append('file://' + (posix if posix.startswith('/') else '/' + posix))
        code, out = self.install('--overlay', urls[0], '--overlay', urls[1])
        self.assertEqual(code, 0, out)
        codex_md = self.read('.codex', 'AGENTS.md').decode()
        self.assertIn('MARKER-team-a', codex_md)
        self.assertIn('MARKER-team-b', codex_md)

    def test_overlay_in_both_blocks(self):
        overlay = self.path('company-overlay')
        self.write(b'# Example Company rules\n\nOVERLAY-MARKER: data classes apply.\n',
                   'company-overlay', 'AGENTS.md')
        code, out = self.install('--overlay', overlay)
        self.assertEqual(code, 0, out)
        claude_md = self.read('.claude', 'CLAUDE.md').decode()
        self.assertIn('@~/company-overlay/AGENTS.md', claude_md)
        self.assertLess(claude_md.index('rules/core.md'), claude_md.index('company-overlay'))
        codex_md = self.read('.codex', 'AGENTS.md').decode()
        self.assertLess(codex_md.index(CORE_TITLE), codex_md.index('OVERLAY-MARKER'))
        code, out = self.install('--uninstall')
        self.assertEqual(code, 0, out)
        self.assertIsNone(self.read('.claude', 'CLAUDE.md'))


if __name__ == '__main__':
    unittest.main()
