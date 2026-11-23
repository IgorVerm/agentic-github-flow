#!/usr/bin/env python3
"""Tests of the maintainers' tools (#125): python3 tests/maint_tools.py.

- tools/bump_version.py raises a plugin's version in its two manifests and its
  .claude-plugin/marketplace.json entry, changes no other byte, and refuses (changing nothing)
  when the three disagree;
- tools/sync_copies.py finds a copy that differs from its owner, writes it (a whole file, or a
  block of definitions with the text around it kept), and exits 0 with --check on this tree;
- the skill budget of tests/skills_format.py fails when a body or the descriptions grow, naming
  the skill and both numbers.
Each case works on a temporary copy of the repository's files.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
BUMP = os.path.join(ROOT, 'tools', 'bump_version.py')
SYNC = os.path.join(ROOT, 'tools', 'sync_copies.py')


def tracked():
    out = subprocess.run(['git', '-C', ROOT, 'ls-files', '-z', '--cached', '--others',
                          '--exclude-standard'], capture_output=True, text=True, check=True)
    return [p for p in out.stdout.split('\0') if p and os.path.isfile(os.path.join(ROOT, p))]


FILES = tracked()


class Tree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='maint-tools-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for rel in FILES:
            target = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), target)

    def path(self, rel):
        return os.path.join(self.tmp, *rel.split('/'))

    def read(self, rel):
        with open(self.path(rel), 'rb') as f:
            return f.read()

    def write(self, rel, data):
        with open(self.path(rel), 'wb') as f:
            f.write(data)

    def run_tool(self, script, *args):
        return subprocess.run([sys.executable, script, *args, '--root', self.tmp],
                              capture_output=True, text=True)


MANIFESTS = ('plugins/security/.claude-plugin/plugin.json',
             'plugins/security/.codex-plugin/plugin.json')
MARKET = '.claude-plugin/marketplace.json'


class BumpVersion(Tree):
    def version_of(self, rel, name=None):
        data = json.loads(self.read(rel))
        if name:
            data = next(e for e in data['plugins'] if e['name'] == name)
        return data['version']

    def set_all(self, version):
        """Give the security plugin `version` in all three places, the way a hand edit would."""
        old = self.version_of(MANIFESTS[0])
        for rel in MANIFESTS + (MARKET,):
            data = self.read(rel).decode('utf-8')
            if rel == MARKET:
                at = data.index('"name": "agentic-github-flow-security"')
                end = data.index('"version": "%s"' % old, at)
                data = data[:end] + data[end:].replace(old, version, 1)
            else:
                data = data.replace('"version": "%s"' % old, '"version": "%s"' % version, 1)
            self.write(rel, data.encode('utf-8'))

    def places(self):
        return [self.version_of(MANIFESTS[0]), self.version_of(MANIFESTS[1]),
                self.version_of(MARKET, 'agentic-github-flow-security')]

    def test_patch_minor_major_raise_all_three_places(self):
        self.set_all('1.4.9')
        for part, want in (('patch', '1.4.10'), ('minor', '1.5.0'), ('major', '2.0.0')):
            with self.subTest(part=part):
                r = self.run_tool(BUMP, 'security', part)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(self.places(), [want] * 3)
                self.set_all('1.4.9')

    def test_default_is_patch_and_the_line_names_both_versions(self):
        before = self.version_of(MANIFESTS[0])
        r = self.run_tool(BUMP, 'agentic-github-flow-security')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.places()[0]
        self.assertEqual(r.stdout.strip(), 'agentic-github-flow-security %s -> %s' % (before, after))
        major, minor, patch = before.split('.')
        self.assertEqual(after, '%s.%s.%d' % (major, minor, int(patch) + 1))

    def test_only_the_version_values_change(self):
        originals = {rel: self.read(rel) for rel in MANIFESTS + (MARKET,)}
        old = self.version_of(MANIFESTS[0])
        r = self.run_tool(BUMP, 'security')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new = self.version_of(MANIFESTS[0])
        for rel, data in originals.items():
            now = self.read(rel).splitlines()
            was = data.splitlines()
            changed = [(a, b) for a, b in zip(was, now) if a != b]
            self.assertEqual(len(was), len(now), rel)
            self.assertEqual(len(changed), 1, rel)
            self.assertEqual(changed[0][0].replace(old.encode(), new.encode()), changed[0][1])
        for plugin in ('core', 'guards', 'issue-chats', 'web-deploy', 'codex'):
            for kind in ('.claude-plugin', '.codex-plugin'):
                rel = 'plugins/%s/%s/plugin.json' % (plugin, kind)
                with open(os.path.join(ROOT, rel), 'rb') as f:
                    self.assertEqual(self.read(rel), f.read(), rel)

    def test_a_disagreement_is_refused_and_nothing_changes(self):
        rel = MANIFESTS[1]
        data = self.read(rel).replace(b'"version": "', b'"version": "9', 1)
        self.write(rel, data)
        before = {r: self.read(r) for r in MANIFESTS + (MARKET,)}
        r = self.run_tool(BUMP, 'security')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('disagree', r.stdout)
        self.assertIn('.codex-plugin/plugin.json 9', r.stdout)
        self.assertEqual(before, {r: self.read(r) for r in MANIFESTS + (MARKET,)})

    def test_an_unknown_plugin_or_a_bad_version_is_refused(self):
        r = self.run_tool(BUMP, 'nonesuch')
        self.assertEqual(r.returncode, 1)
        self.assertIn('no plugin folder', r.stdout)
        for name in ('../plugins', '..', ''):
            r = self.run_tool(BUMP, name)
            self.assertEqual(r.returncode, 1, name)
            self.assertIn('no plugin folder', r.stdout)
        self.set_all('1.4')
        r = self.run_tool(BUMP, 'security')
        self.assertEqual(r.returncode, 1)
        self.assertIn('not three numbers', r.stdout)

    def test_the_marketplace_metadata_version_is_not_taken_for_the_plugins(self):
        meta = json.loads(self.read(MARKET))['metadata']['version']
        self.set_all(meta)
        r = self.run_tool(BUMP, 'security')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(self.read(MARKET))['metadata']['version'], meta)
        self.assertNotEqual(self.places()[0], meta)


class SyncCopies(Tree):
    def test_this_tree_has_no_difference(self):
        r = subprocess.run([sys.executable, SYNC, '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_a_whole_file_copy_is_found_and_written(self):
        rel = 'plugins/issue-chats/scripts/landing.py'
        self.write(rel, self.read(rel) + b'# drift\n')
        r = self.run_tool(SYNC, '--check')
        self.assertEqual(r.returncode, 1)
        self.assertIn(rel + ' differs from plugins/core/scripts/landing.py', r.stdout)
        self.assertIn(b'# drift', self.read(rel))  # --check writes nothing
        r = self.run_tool(SYNC)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('wrote ' + rel, r.stdout)
        self.assertIn('bump_version.py issue-chats', r.stdout)
        self.assertEqual(self.read(rel), self.read('plugins/core/scripts/landing.py'))
        self.assertEqual(self.run_tool(SYNC, '--check').returncode, 0)

    def test_a_block_copy_keeps_the_text_around_it(self):
        owner = 'plugins/security/scripts/scan_secrets.py'
        copy = 'plugins/guards/scripts/pre_tool_personal_data.py'
        self.write(owner, self.read(owner).replace(b'FIRST_FEW_BYTES = 8000',
                                                   b'FIRST_FEW_BYTES = 9000'))
        around = self.read(copy).replace(b'NEW_BLOB = re.compile(', b'NEW_BLOB  = re.compile(')
        self.write(copy, around)
        r = self.run_tool(SYNC, '--check')
        self.assertEqual(r.returncode, 1)
        self.assertIn('(FIRST_FEW_BYTES through binary_blobs)', r.stdout)
        r = self.run_tool(SYNC)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read(copy), around.replace(b'FIRST_FEW_BYTES = 8000',
                                                         b'FIRST_FEW_BYTES = 9000'))
        self.assertIn(b'NEW_BLOB  = re.compile(', self.read(copy))  # outside the block: kept

    def test_a_one_function_block(self):
        copy = 'plugins/guards/scripts/pre_tool_merge_guard.py'
        data = self.read(copy)
        self.write(copy, data.replace(b"path.startswith('.claude/')",
                                      b"path.startswith('.claude')"))
        r = self.run_tool(SYNC, '--check')
        self.assertEqual(r.returncode, 1)
        self.assertIn(copy + ' differs from plugins/core/scripts/work_proof.py (protected)', r.stdout)
        self.assertEqual(self.run_tool(SYNC).returncode, 0)
        self.assertEqual(self.read(copy), data)

    def test_a_missing_block_is_an_error_not_a_write(self):
        copy = 'plugins/guards/scripts/pre_tool_merge_guard.py'
        data = self.read(copy).replace(b'def protected(path):', b'def guarded(path):')
        self.write(copy, data)
        r = self.run_tool(SYNC)
        self.assertEqual(r.returncode, 2)
        self.assertIn('no single block from protected through protected', r.stdout)
        self.assertEqual(self.read(copy), data)

    def test_repo_checks_reads_the_same_list(self):
        rel = 'plugins/security/scripts/gitignore-secrets'
        self.write(rel, self.read(rel) + b'extra\n')
        r = subprocess.run([sys.executable, self.path('tests/repo_checks.py')],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn(rel + ' differs from templates/gitignore-secrets', r.stdout)


class SkillBudget(Tree):
    SKILL = 'plugins/core/skills/spec-first/SKILL.md'

    def check(self):
        return subprocess.run([sys.executable, self.path('tests/skills_format.py')],
                              capture_output=True, text=True)

    def test_the_tree_is_within_its_budget(self):
        r = self.check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_100_more_bytes_in_a_body_fail_with_the_name_and_both_numbers(self):
        data = self.read(self.SKILL)
        body = len(data) - data.index(b'\n---\n', 4) - len(b'\n---\n')
        self.write(self.SKILL, data + b'x' * 99 + b'\n')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn('spec-first: SKILL.md body is %d bytes, over its budget of %d'
                      % (body + 100, body), r.stdout)

    def test_longer_descriptions_fail_with_both_numbers(self):
        data = self.read(self.SKILL)
        self.write(self.SKILL, data.replace(b'\ndescription: ', b'\ndescription: Longer now. ', 1))
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertRegex(r.stdout, r'descriptions of all skills are (\d+) bytes together, over '
                                   r'the budget of (\d+)')

    def test_a_new_skill_needs_a_row(self):
        folder = self.path('plugins/core/skills/new-skill')
        os.makedirs(folder)
        with open(os.path.join(folder, 'SKILL.md'), 'w', encoding='utf-8') as f:
            f.write('---\nname: new-skill\ndescription: A new skill that does one thing, used '
                    'when the test says so.\n---\n\nBody.\n')
        r = self.check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no row in BODY_BUDGET (tests/skills_format.py); add 'new-skill': 7",
                      r.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=1)
