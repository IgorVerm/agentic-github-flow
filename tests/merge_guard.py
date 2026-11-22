#!/usr/bin/env python3
"""Checks the guards plugin's pre_tool_merge_guard.py (#108): python3 tests/merge_guard.py.

A throwaway repository whose main changed .claude/ (branch `main`) and one whose change leaves
.claude/ alone (branch `readme`); the task worktree stands in for the session's own folder. BLOCK
lists the spellings of a bare merge of `main` the guard must refuse; ALLOW what must pass. The
hook contract (JSON on stdin, the sandbox read from the settings, exit 2 to block) is exercised
for the sandbox's on, off, bypassed and excluded cases. Offline.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, '..', 'plugins', 'guards', 'scripts', 'pre_tool_merge_guard.py')
# Native Windows has no Claude Code sandbox, so there the hook never refuses (its header), and a
# Windows path written into a shell command is not what the guard's POSIX parsing reads.
NO_SANDBOX = os.name == 'nt'
skip_no_sandbox = unittest.skipIf(NO_SANDBOX, 'native Windows: no sandbox, the guard refuses '
                                  'nothing')

BLOCK = [
    'git merge main', 'git merge --no-edit main', 'git merge --ff-only main',
    'git merge -m "catch up" main', 'git merge --no-ff --no-edit main',
    'git -C {wt} merge main', 'cd {wt} && git merge main', 'cd {other} && cd {wt} && git merge main',
    'bash -c "git merge main"', "zsh -lc 'cd {wt} && git merge --no-edit main'",
    'env GIT_MERGE_AUTOEDIT=no git merge main', 'timeout 30 git merge main',
    '/usr/bin/git merge main', 'git status && git merge main', 'git merge readme main',
    'git merge',  # the upstream is main
    'git merge -S main', '(cd {other}) && git merge main', 'echo "$(cd {other})"; git merge main',
    'cd {other} && (cd {wt} && git merge main)', 'git merge conflict',
    'git merge adds',
    # `{}` in a ref is part of it, not a group (second review of #109); `{{` is format()'s `{`
    'git merge @{{u}}', 'git merge @{{upstream}}', 'git merge main@{{0}}',
    'git merge --no-edit @{{u}}', '{{ git merge main; }}',
    '{{ cd {other}; cd {wt}; }} && git merge main',
    # wrapper options with a value (third review of #109)
    'env -u GIT_DIR git merge main', 'timeout -s KILL 10 git merge main',
    'nice -n 5 git merge main', 'timeout -k 5 30 git merge main',
    # a value option of one wrapper is not one of another (fourth review of #109)
    'caffeinate -s git merge main', 'caffeinate -u git merge main',
    'stdbuf -o L git merge main', 'exec -a x git merge main',  # fifth review of #109
    # from a subfolder: judged from the top level (fourth review of #109)
    'cd src && git merge main', 'git -C src merge adds', 'cd {wt}/src && git merge main',
]
ALLOW = [
    'git merge readme', 'git merge --abort', 'git merge --continue', 'git merge no-such-ref',
    'git -C {other} merge main', 'cd {other} && git merge main', 'git merge-base main HEAD',
    'git log --merges main', 'git commit -m "git merge main"', 'echo git merge main',
    'git pull', 'git merge -h', 'cd "$X" && git merge main', 'git --git-dir=x merge main',
    'git status', 'git merge -S readme', '(cd {other} && git merge main)', 'cd {wt} && (cd {other}; git merge main)',
    'git merge readme@{{0}}', '{{ cd {other}; }} && git merge main',
    'pushd {other} && git merge main',  # pushd is not followed: the folder is unknown
    'env -C {other} git merge main', 'git merge readme && git fetch',
    'git fetch && git -C {other} merge readme',
    'git merge -s ours main', 'git merge --strategy=ours main', 'git merge -sours main',
]
# a merge after a fetch in the same call is judged before the fetch runs (third review of #109)
AFTER_FETCH = [
    'git fetch && git merge readme', 'git fetch origin && git merge origin/main',
    'git fetch -q origin main && git merge --no-edit FETCH_HEAD',
    'git pull --ff-only; git merge readme', 'bash -c "git fetch -q" && git merge readme',
    'git -C {wt} fetch && cd {wt} && git merge readme', 'git remote update && git merge readme',
]


class MergeGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = os.path.realpath(tempfile.mkdtemp(prefix='merge-guard-'))
        config = os.path.join(cls.dir, 'gitconfig')
        with open(config, 'w') as f:
            f.write('[advice]\n\tdetachedHead = false\n')
        cls.env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=config,
                       GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                       GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid')
        cls.env.pop('CLAUDE_PROJECT_DIR', None)
        repo = cls.repo = os.path.join(cls.dir, 'repo')
        cls.git(cls.dir, 'init', '-q', '-b', 'main', repo)
        cls.write(repo, 'README.md', 'start\n')
        cls.write(repo, '.claude/agents/a.md', 'agent\n')
        cls.git(repo, 'add', 'README.md', '.claude')
        cls.git(repo, 'commit', '-q', '-m', 'start')
        cls.git(repo, 'branch', 'task')
        cls.git(repo, 'branch', 'other')
        cls.git(repo, 'switch', '-q', '-c', 'conflict')
        cls.write(repo, '.claude/agents/a.md', 'agent, the other way\n')
        cls.git(repo, 'commit', '-q', '-am', 'conflicting agent')
        cls.git(repo, 'switch', '-q', 'main')
        cls.git(repo, 'switch', '-q', '-c', 'readme')
        cls.write(repo, 'README.md', 'readme\n')
        cls.git(repo, 'commit', '-q', '-am', 'readme only')
        cls.git(repo, 'switch', '-q', 'main')
        cls.write(repo, '.claude/agents/a.md', 'agent 2\n')
        cls.write(repo, 'new.txt', 'new\n')
        cls.git(repo, 'add', '.claude', 'new.txt')
        cls.git(repo, 'commit', '-q', '-m', 'main changes .claude')
        cls.wt = os.path.join(cls.dir, 'wt')
        cls.other = os.path.join(cls.dir, 'other')
        cls.git(repo, 'worktree', 'add', '-q', cls.wt, 'task')
        cls.git(repo, 'worktree', 'add', '-q', cls.other, 'other')
        cls.git(cls.wt, 'branch', '-q', '--set-upstream-to=main')
        os.makedirs(os.path.join(cls.wt, 'src'))  # a subfolder of the session's worktree
        # the task changed the agent too: merging main or `conflict` conflicts in .claude/
        cls.write(cls.wt, '.claude/agents/a.md', 'agent, the task way\n')
        cls.git(cls.wt, 'commit', '-q', '-am', 'task changes the agent')
        cls.git(repo, 'switch', '-q', '-c', 'adds', 'readme')
        cls.write(repo, '.claude/agents/b.md', 'b\n')
        cls.git(repo, 'add', '.claude')
        cls.git(repo, 'commit', '-q', '-m', 'adds an agent, no conflict')
        cls.git(repo, 'switch', '-q', 'main')
        conflicted = subprocess.run(['git', 'merge-tree', '--write-tree', 'HEAD', 'conflict'],
                                    cwd=cls.wt, env=cls.env, capture_output=True)
        assert conflicted.returncode == 1, 'the fixture must conflict'

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def git(cls, cwd, *args):
        r = subprocess.run(['git', *args], cwd=cwd, env=cls.env, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError('git %s: %s' % (' '.join(args), r.stderr))
        return r

    @staticmethod
    def write(folder, rel, text):
        path = os.path.join(folder, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            f.write(text)

    def check(self, command, cwd=None):
        command = command.format(wt=self.wt, other=self.other)
        r = subprocess.run([sys.executable, HOOK, '--check', command, '--cwd', cwd or self.wt,
                            '--project', self.wt], env=self.env, capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def hook(self, command, settings, tool_input=None, project=True):
        home = tempfile.mkdtemp(dir=self.dir)
        if settings is not None:
            with open(os.path.join(home, 'settings.json'), 'w') as f:
                json.dump(settings, f)
        env = dict(self.env, CLAUDE_CONFIG_DIR=home)
        if project:
            env['CLAUDE_PROJECT_DIR'] = self.wt
        event = {'tool_name': 'Bash', 'cwd': self.wt,
                 'tool_input': dict({'command': command}, **(tool_input or {}))}
        r = subprocess.run([sys.executable, HOOK], input=json.dumps(event), env=env,
                           capture_output=True, text=True)
        return r.returncode, r.stderr

    @skip_no_sandbox
    def test_block(self):
        for command in BLOCK:
            with self.subTest(command=command):
                code, out = self.check(command)
                self.assertEqual(code, 2, out)
                self.assertIn('merge_landing.py', out)
                self.assertIn('.claude/agents/' + ('b' if 'adds' in command else 'a') + '.md',
                              out)

    def test_allow(self):
        for command in ALLOW:
            with self.subTest(command=command):
                code, out = self.check(command)
                self.assertEqual(code, 0, out)

    @skip_no_sandbox
    def test_the_suggested_command_repeats_the_folder_and_no_ff(self):
        code, out = self.check('git -C {wt} merge --no-ff main', cwd=self.other)
        self.assertEqual(code, 2, out)
        self.assertIn(' -C %s --no-ff main' % self.wt, out)
        code, out = self.check('git merge main')
        self.assertNotIn(' -C ', out)
        self.assertNotIn('does not honour', out)

    @skip_no_sandbox
    def test_a_merge_run_in_a_subfolder_is_judged_from_the_top_level(self):
        src = os.path.join(self.wt, 'src')
        for command in ('git merge adds', 'git merge main', 'git merge @{{u}}'):
            with self.subTest(command=command):
                code, out = self.check(command, cwd=src)
                self.assertEqual(code, 2, out)
                self.assertIn('.claude/agents/', out)
        self.assertEqual(self.check('git merge readme', cwd=src)[0], 0)

    @skip_no_sandbox
    def test_a_merge_after_a_fetch_in_the_same_call_is_refused(self):
        for command in AFTER_FETCH:
            with self.subTest(command=command):
                code, out = self.check(command)
                self.assertEqual(code, 2, out)
                self.assertIn('Run the fetch as its own call', out)
        # a merge that changes .claude/ gets the refusal that names its paths
        for command in ('git fetch && git merge main', 'git fetch && git merge @{u}'):
            code, out = self.check(command.replace('{', '{{').replace('}', '}}'))
            self.assertEqual(code, 2, out)
            self.assertIn('.claude/agents/a.md', out)

    @skip_no_sandbox
    def test_the_refusal_says_which_flags_merge_landing_does_not_honour(self):
        code, out = self.check('git merge --ff-only --no-commit main')
        self.assertEqual(code, 2, out)
        self.assertIn('does not honour --ff-only, --no-commit', out)
        code, out = self.check('git merge -s ort -X theirs -m "catch up" main')
        self.assertEqual(code, 2, out)
        self.assertIn('does not honour -s, -X, -m', out)

    def test_protected_is_the_core_plugins_own(self):
        """The guard's protected() copies work_proof.protected (the core plugin, which the guards
        plugin cannot import): they must agree."""
        sys.path.insert(0, os.path.join(HERE, '..', 'plugins', 'core', 'scripts'))
        import work_proof
        import importlib.util
        spec = importlib.util.spec_from_file_location('merge_guard_hook', HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        for path in ('.claude/a.md', '.claude', '.claude/', '.mcp.json', '.mcp.jsonx', 'a/.claude/x',
                     '.claudex/y', 'README.md', '.mcp.json/x', '.CLAUDE/a'):
            with self.subTest(path=path):
                self.assertEqual(hook.protected(path), work_proof.protected(path))

    @skip_no_sandbox
    def test_a_merge_from_another_folder_into_the_own_worktree_is_judged_there(self):
        self.assertEqual(self.check('git -C {wt} merge main', cwd=self.other)[0], 2)
        self.assertEqual(self.check('git merge main', cwd=self.other)[0], 0)

    @skip_no_sandbox
    def test_the_hook_reads_the_sandbox_from_the_settings(self):
        on = {'sandbox': {'enabled': True}}
        self.assertEqual(self.hook('git merge main', on)[0], 2)
        self.assertEqual(self.hook('git merge @{u}', on)[0], 2)
        self.assertEqual(self.hook('git merge readme', on)[0], 0)
        self.assertEqual(self.hook('git merge main', {'sandbox': {'enabled': False}})[0], 0)
        self.assertEqual(self.hook('git merge main', None)[0], 0)
        self.assertEqual(self.hook('git merge main', on, {'dangerouslyDisableSandbox': True})[0],
                         0)
        excluded = {'sandbox': {'enabled': True, 'excludedCommands': ['git merge *']}}
        self.assertEqual(self.hook('git merge main', excluded)[0], 0)
        self.assertEqual(self.hook('cd {} && git merge main'.format(self.wt), excluded)[0], 2)
        # without CLAUDE_PROJECT_DIR the hook input's cwd names the session's folder
        self.assertEqual(self.hook('git merge main', on, project=False)[0], 2)

    @unittest.skipUnless(NO_SANDBOX, 'only native Windows has no sandbox')
    def test_native_windows_has_no_sandbox_so_the_hook_passes(self):
        on = {'sandbox': {'enabled': True}}
        self.assertEqual(self.hook('git merge main', on)[0], 0)

    def test_the_hook_passes_what_it_cannot_read(self):
        on = {'sandbox': {'enabled': True}}
        home = tempfile.mkdtemp(dir=self.dir)
        with open(os.path.join(home, 'settings.json'), 'w') as f:
            json.dump(on, f)
        env = dict(self.env, CLAUDE_CONFIG_DIR=home)
        for text in ('not json', '[]', json.dumps({'tool_name': 'Read'}),
                     json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 7}})):
            r = subprocess.run([sys.executable, HOOK], input=text, env=env, capture_output=True,
                               text=True)
            self.assertEqual(r.returncode, 0, text)

    @skip_no_sandbox
    def test_a_refused_merge_changed_nothing(self):
        before = self.git(self.wt, 'rev-parse', 'HEAD').stdout
        self.assertEqual(self.check('git merge main')[0], 2)
        self.assertEqual(self.git(self.wt, 'rev-parse', 'HEAD').stdout, before)
        self.assertEqual(self.git(self.wt, 'status', '--porcelain', '--untracked-files=all'
                                  ).stdout, '')


if __name__ == '__main__':
    unittest.main()
