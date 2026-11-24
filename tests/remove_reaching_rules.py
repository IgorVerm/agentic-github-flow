#!/usr/bin/env python3
"""Tests of tools/remove_reaching_rules.py (#33): python3 tests/remove_reaching_rules.py.

In a temporary settings folder: without --apply nothing is written; --apply refuses while no
enabled guards plugin runs the git guard with --claude; with one it keeps a backup equal to the
file as it was and removes exactly the ask and deny rules the installer's REACHES_COMMIT names,
leaving allow rules, the other rules and the other settings as they were; a second run finds
nothing; a file that is not JSON is refused unchanged.
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TOOL = os.path.join(ROOT, 'tools', 'remove_reaching_rules.py')
GUARDS = 'agentic-github-flow-guards@agentic-github-flow'
REACHING = {'ask': ['Bash(git -C * push*)', 'Bash(git commit * --amend*)'],
            'deny': ['Bash(git -C * clean*)', 'Bash(git * --no-verify*)',
                     'Bash(git -c * core.hooksPath*)', 'Bash(git commit --all*)',
                     'Bash(git commit * -n *)']}
KEPT = {'allow': ['Bash(git -C * status*)', 'Bash(git * log*)'],
        'ask': ['Bash(git push*)', 'Bash(gh api * -X*)'],
        'deny': ['Bash(git clean*)', 'Bash(git push * --force*)', 'Bash(git commit --all *)',
                 'Read(**/.env)', 'Bash(rm -rf *)']}


class Tool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='reaching-rules-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.settings = os.path.join(self.tmp, 'settings.json')
        self.data = {'model': 'x', 'enabledPlugins': {GUARDS: True}, 'permissions': {
            'allow': list(KEPT['allow']),
            'ask': [KEPT['ask'][0], REACHING['ask'][0], KEPT['ask'][1], REACHING['ask'][1]],
            'deny': REACHING['deny'][:2] + KEPT['deny'] + REACHING['deny'][2:]}}
        self.write(self.data)

    def write(self, data):
        with open(self.settings, 'w', encoding='utf-8') as f:
            f.write(json.dumps(data, indent=4))

    def plugin(self, command):
        root = os.path.join(self.tmp, 'plugins', 'cache', 'guards', '1.0.0')
        os.makedirs(os.path.join(root, 'hooks'), exist_ok=True)
        with open(os.path.join(root, 'hooks', 'hooks.json'), 'w', encoding='utf-8') as f:
            json.dump({'hooks': {'PreToolUse': [
                {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': command}]}]}}, f)
        with open(os.path.join(self.tmp, 'plugins', 'installed_plugins.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'version': 2, 'plugins': {GUARDS: [
                {'installPath': root, 'version': '1.0.0'}]}}, f)

    def run_tool(self, *args):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.tmp)
        r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True,
                           env=env)
        return r.returncode, r.stdout + r.stderr

    def text(self):
        with open(self.settings, encoding='utf-8') as f:
            return f.read()

    def backups(self):
        return glob.glob(self.settings + '.agentic-github-flow-backup-*')

    def test_dry_run_is_the_default_and_writes_nothing(self):
        before = self.text()
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        for kind in REACHING:
            for rule in REACHING[kind]:
                self.assertIn('%-4s %s' % (kind, rule), out)
        for kind in KEPT:
            for rule in KEPT[kind]:
                self.assertNotIn(rule + '\n', out)
        self.assertIn('7 rules', out)
        self.assertIn('dry run', out)
        self.assertIn('--apply would refuse now', out)  # no plugin installed here
        self.assertEqual(self.text(), before)
        self.assertEqual(self.backups(), [])
        self.assertEqual(os.listdir(self.tmp), ['settings.json'])

    def test_apply_refuses_without_the_guard_hook(self):
        before = self.text()
        cases = [None, 'python3 pre_tool_git_guard.py', 'python3 other.py --claude']
        for command in cases:
            if command:
                self.plugin(command)
            code, out = self.run_tool('--apply')
            self.assertEqual(code, 1, out)
            self.assertIn('nothing changed', out)
            self.assertEqual(self.text(), before)
            self.assertEqual(self.backups(), [])
        self.plugin('python3 pre_tool_git_guard.py --claude')
        self.data['enabledPlugins'][GUARDS] = False  # installed, switched off
        self.write(self.data)
        before = self.text()
        code, out = self.run_tool('--apply')
        self.assertEqual(code, 1, out)
        self.assertEqual(self.text(), before)

    def test_apply_keeps_a_backup_and_removes_only_the_reaching_rules(self):
        self.plugin('sh "x/run-python.sh" "x/scripts/pre_tool_git_guard.py" --claude')
        before = self.text()
        code, out = self.run_tool('--apply')
        self.assertEqual(code, 0, out)
        self.assertIn('7 rules removed', out)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        with open(backups[0], encoding='utf-8') as f:
            self.assertEqual(f.read(), before)
        after = json.loads(self.text())
        self.assertEqual(after['permissions'], KEPT)
        expected = dict(self.data, permissions=KEPT)
        self.assertEqual(after, expected)
        code, out = self.run_tool('--apply')
        self.assertEqual(code, 0, out)
        self.assertIn('no ask or deny rule', out)
        self.assertEqual(len(self.backups()), 1)

    def test_another_file_and_the_check_switched_off(self):
        other = os.path.join(self.tmp, 'elsewhere', 'copy.json')
        os.makedirs(os.path.dirname(other))
        shutil.copy(self.settings, other)
        before = self.text()
        code, out = self.run_tool('--settings', other, '--apply')
        self.assertEqual(code, 1, out)
        code, out = self.run_tool('--settings', other, '--apply', '--without-guard-check')
        self.assertEqual(code, 0, out)
        with open(other, encoding='utf-8') as f:
            self.assertEqual(json.load(f)['permissions'], KEPT)
        self.assertEqual(self.text(), before, 'the default file is not touched')

    def test_odd_files_are_left_alone(self):
        for content in ('{not json', '[1, 2]'):
            with open(self.settings, 'w', encoding='utf-8') as f:
                f.write(content)
            code, out = self.run_tool('--apply', '--without-guard-check')
            self.assertEqual(code, 1, out)
            self.assertEqual(self.text(), content)
        for data in ({}, {'permissions': 'x'}, {'permissions': {'deny': 'x', 'ask': [1, None]}}):
            self.write(data)
            before = self.text()
            code, out = self.run_tool('--apply', '--without-guard-check')
            self.assertEqual(code, 0, out)
            self.assertEqual(self.text(), before)
        os.remove(self.settings)
        code, out = self.run_tool('--apply')
        self.assertEqual(code, 0, out)
        self.assertFalse(os.path.exists(self.settings))
        code, out = self.run_tool('--bogus')
        self.assertEqual(code, 1, out)


if __name__ == '__main__':
    unittest.main()
