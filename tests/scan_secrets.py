#!/usr/bin/env python3
"""Checks the security plugin's scan_secrets.py in throwaway repositories: python3 tests/scan_secrets.py.

Every planted token is built by concatenation, so this file holds nothing token-shaped and the
scanner's own run over this repository stays clean. Offline; no network, no real keys.
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
SCRIPTS = os.path.join(ROOT, 'plugins', 'security', 'scripts')
TOOL = os.path.join(SCRIPTS, 'scan_secrets.py')
sys.path.insert(0, SCRIPTS)
import scan_secrets  # noqa: E402

XDG = tempfile.mkdtemp(prefix='scan-secrets-xdg-')  # no global ignore file: *.pem must be addable
EMPTY_CONFIG = os.path.join(XDG, 'gitconfig')
open(EMPTY_CONFIG, 'w').close()
GIT_ENV = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=EMPTY_CONFIG, XDG_CONFIG_HOME=XDG,
               GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@localhost',
               GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@localhost')


def jwt(role):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    return '.'.join([b64({'alg': 'HS256', 'typ': 'JWT'}),
                     b64({'iss': 'supabase', 'ref': 'abcdefghij', 'role': role, 'iat': 1}),
                     'c' * 43])


A = 'A' * 24
PLANTED = {  # pattern name -> a line that must match it
    'supabase-secret-key': 'const k = "' + 'sb_' + 'secret_' + 'a1b2c3d4e5f6g7h8i9j0k1l2m3" ',
    'supabase-service-role-jwt': 'SUPABASE_SERVICE_ROLE_KEY=' + jwt('service_role'),
    'anthropic-api-key': 'key = "' + 'sk-' + 'ant-' + 'api03-' + A + '"',
    'openai-api-key': 'OPENAI="' + 'sk-' + 'proj-' + A + 'bb"',
    'stripe-live-secret': 'stripe = "' + 'sk_' + 'live_' + '51H' + A + '"',
    'stripe-test-secret': 'stripe = "' + 'sk_' + 'test_' + '51H' + A + '"',
    'stripe-webhook-secret': 'hook: ' + 'whsec_' + '1234567890abcdefghijklmn',
    'resend-api-key': 'RESEND=' + 're_' + 'AbCdEf12' + '_' + 'GhIjKlMnOpQrStUvWxYz1234',
    'github-token': 'token: ' + 'ghp_' + 'a' * 36,
    'google-api-key': 'maps = "' + 'AIza' + 'Sy' + 'B' * 33 + '"',
    'google-oauth-client-secret': 'client_secret = "' + 'GOCSPX-' + 'abcdefghij1234567890' + '"',
    'aws-access-key-id': 'aws_access_key_id = ' + 'AKIA' + 'Q3M7ZP2RT8KX4VW9',
    'slack-token': 'slack = "' + 'xoxb-' + '1234567890-abcdefghij' + '"',
    'private-key-block': '-----BEGIN ' + 'RSA PRIVATE KEY-----',
    'jwt': 'bearer ' + jwt('authenticated_user'),
    'secret-named-assignment:DATABASE_PASSWORD': 'DATABASE_PASSWORD=' + 'p4ssw0rd' + 'Z9' + 'q7m2x1',
    'secret-named-assignment:STRIPE_SECRET_KEY': 'STRIPE_SECRET_KEY: "' + 'live9' + 'K2m8Q4z7W1x3' + '"',
    'secret-named-assignment:CLOUDFLARE_API_TOKEN': 'export CLOUDFLARE_API_TOKEN=' + 'cf' + 'T0k3n' + 'Qw9Er8Ty7Ui6Op5As4Df3Gh2Jk1Lz0Vc',
}
CLEAN = [  # lines that must not match anything
    'NEXT_PUBLIC_SUPABASE_ANON_KEY=' + jwt('anon'),
    'SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here',
    'OPENAI_API_KEY=${OPENAI_API_KEY}',
    'const key = process.env.RESEND_API_KEY',
    'API_TOKEN = os.environ["API_TOKEN"]',
    'DATABASE_PASSWORD=changeme',
    'SESSION_SECRET=<generate one with openssl rand -hex 32>',
    'NEXT_PUBLIC_SITE_URL=https://example.test',
    'AWS_SECRET_ACCESS_KEY=EXAMPLEKEY' + 'wJalrXUtnFEMI',
    'sha512-' + 'Q' * 86 + '==',
    'JWT_SECRET=' + 'a' * 40,
    "SUPABASE_URL = 'https://abcdefghij.supabase.co'",
    'The sk_live_ prefix marks a live key (documentation).',
    'const SAFE_TOKEN = /^[A-Za-z0-9_-]{1,127}$/',
    'GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D',
]


def run(*args):
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=GIT_ENV)
    return r.returncode, r.stdout, r.stderr


def git(repo, *args):
    subprocess.run(['git', '-C', repo, *args], check=True, capture_output=True, env=GIT_ENV)


def write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


class LineTests(unittest.TestCase):
    def test_every_planted_pattern_is_found_by_name(self):
        for name, line in PLANTED.items():
            with self.subTest(name=name):
                self.assertIn(name, scan_secrets.findings_in_line(line))

    def test_clean_lines_match_nothing(self):
        for line in CLEAN:
            with self.subTest(line=line[:40]):
                self.assertEqual(scan_secrets.findings_in_line(line), [])

    def test_file_names_come_from_the_ignore_template(self):
        self.assertTrue(scan_secrets.FILE_PATTERNS)
        for name in ('.env', '.env.production', 'id_rsa', 'server.pem', 'service-account-x.json',
                     'credentials.json', 'prod.tfvars', 'client_secret_123.apps.googleusercontent.com.json'):
            self.assertIsNotNone(scan_secrets.secret_file_name('a/b/' + name), name)
        self.assertEqual(scan_secrets.secret_file_name('ops/.secrets/token.txt'), '.secrets/')
        self.assertIsNone(scan_secrets.secret_file_name('ops/secrets/README.md'))
        for name in ('.env.example', 'README.md', 'package-lock.json', '.DS_Store',
                     'settings.local.json'):
            self.assertIsNone(scan_secrets.secret_file_name('a/' + name), name)


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='scan-secrets-')
        self.repo = os.path.join(self.dir, 'repo')
        os.makedirs(self.repo)
        git(self.repo, 'init', '-q', '-b', 'main')
        write(self.repo, '.gitignore', '.env\n.env.*\n!.env.example\n')
        write(self.repo, 'README.md', 'clean\n')
        write(self.repo, '.env.example', '\n'.join(CLEAN) + '\n')
        git(self.repo, 'add', '--', '.gitignore', 'README.md', '.env.example')
        git(self.repo, 'commit', '-q', '-m', 'clean')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_clean_repo_exits_zero(self):
        code, out, err = run(self.repo, '--history', '--staged')
        self.assertEqual(code, 0, out + err)
        self.assertIn('0 finding(s)', out)

    def test_ignored_env_file_is_not_scanned(self):
        write(self.repo, '.env', PLANTED['stripe-live-secret'] + '\n')
        code, out, _ = run(self.repo)
        self.assertEqual(code, 0, out)

    def test_tree_findings_name_pattern_file_and_line_but_never_the_value(self):
        write(self.repo, 'src/config.ts', 'line one\n' + PLANTED['stripe-live-secret'] + '\n')
        write(self.repo, 'keys/service-account-prod.json', '{}\n')
        code, out, _ = run(self.repo)
        self.assertEqual(code, 1)
        self.assertIn('tree\tstripe-live-secret\tsrc/config.ts:2', out)
        self.assertIn('tree\tsecret-file-name:service-account*.json\tkeys/service-account-prod.json', out)
        self.assertNotIn('51H' + A, out)

    def test_staged_lines_are_seen(self):
        write(self.repo, 'worker/.env.worker', 'x\n')
        write(self.repo, 'lib/admin.ts', PLANTED['supabase-service-role-jwt'] + '\n')
        git(self.repo, 'add', '--', 'lib/admin.ts')
        code, out, _ = run(self.repo, '--staged', '--exclude', 'worker/*')
        self.assertEqual(code, 1)
        self.assertIn('staged\tsupabase-service-role-jwt\tlib/admin.ts:1', out)
        self.assertNotIn(jwt('service_role'), out)

    def test_history_finds_a_secret_removed_later_with_its_commit(self):
        write(self.repo, 'deploy.sh', '#!/bin/sh\n' + PLANTED['github-token'] + '\n')
        git(self.repo, 'add', '--', 'deploy.sh')
        git(self.repo, 'commit', '-q', '-m', 'leak')
        sha = subprocess.run(['git', '-C', self.repo, 'rev-parse', '--short=12', 'HEAD'],
                             capture_output=True, text=True, env=GIT_ENV).stdout.strip()
        write(self.repo, 'deploy.sh', '#!/bin/sh\necho fixed\n')
        git(self.repo, 'commit', '-q', '-m', 'remove', '--', 'deploy.sh')
        code, out, _ = run(self.repo)
        self.assertEqual(code, 0, out)
        code, out, _ = run(self.repo, '--history')
        self.assertEqual(code, 1)
        self.assertIn('history\tgithub-token\tdeploy.sh:2\t' + sha, out)
        self.assertNotIn('ghp_' + 'a' * 36, out)

    def test_history_sees_a_secret_file_added_on_another_branch(self):
        git(self.repo, 'checkout', '-q', '-b', 'feature')
        write(self.repo, 'certs/server.pem', PLANTED['private-key-block'] + '\n')
        git(self.repo, 'add', '--', 'certs/server.pem')
        git(self.repo, 'commit', '-q', '-m', 'cert')
        git(self.repo, 'checkout', '-q', 'main')
        code, out, _ = run(self.repo, '--history')
        self.assertEqual(code, 1)
        self.assertIn('history\tsecret-file-name:*.pem\tcerts/server.pem', out)
        self.assertIn('history\tprivate-key-block\tcerts/server.pem:1', out)

    def test_added_line_starting_with_plus_plus_is_content_not_a_header(self):
        write(self.repo, 'notes.md', '++ not a header\n' + PLANTED['slack-token'] + '\n')
        git(self.repo, 'add', '--', 'notes.md')
        code, out, _ = run(self.repo, '--staged')
        self.assertEqual(code, 1)
        self.assertIn('staged\tslack-token\tnotes.md:2', out)

    def test_binary_and_large_files_are_skipped(self):
        with open(os.path.join(self.repo, 'blob.bin'), 'wb') as f:
            f.write(b'\0' + PLANTED['slack-token'].encode())
        write(self.repo, 'big.txt', 'x' * (scan_secrets.MAX_BYTES + 1) + PLANTED['slack-token'])
        code, out, _ = run(self.repo)
        self.assertEqual(code, 0, out)

    def test_plain_folder_without_git(self):
        plain = os.path.join(self.dir, 'plain')
        write(plain, 'node_modules/x/index.js', PLANTED['aws-access-key-id'] + '\n')
        write(plain, 'app/settings.py', PLANTED['secret-named-assignment:DATABASE_PASSWORD'] + '\n')
        code, out, _ = run(plain)
        self.assertEqual(code, 1)
        self.assertIn('secret-named-assignment:DATABASE_PASSWORD\tapp/settings.py:1', out)
        self.assertNotIn('node_modules', out)
        code, _, err = run(plain, '--history')
        self.assertEqual(code, 2)
        self.assertIn('not a git repository', err)

    def test_usage_errors(self):
        self.assertEqual(run()[0], 2)
        self.assertEqual(run(os.path.join(self.dir, 'missing'))[0], 2)
        self.assertEqual(run(self.repo, '--bogus')[0], 2)


class SelfScanTest(unittest.TestCase):
    def test_this_repository_is_clean(self):
        code, out, err = run(ROOT)
        self.assertEqual(code, 0, out + err)


if __name__ == '__main__':
    unittest.main()
