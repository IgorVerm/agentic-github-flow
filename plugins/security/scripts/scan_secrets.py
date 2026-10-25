#!/usr/bin/env python3
"""Find committed, staged or historical secrets in a repository without printing them.

Usage: python3 scan_secrets.py <repo> [--history] [--staged] [--exclude <glob>]...

Private repositories on GitHub's free plan have no secret scanning or push protection (GitHub
docs, read 2026-10-25), and a public repository's protection only starts at the push, so this
script is the local control that the `review-security` and `check-web-deploy` skills run. It
reports the pattern that matched, the file, the line and (in history) the commit; it never prints
the matched value, so its output can go on an issue. A hit means: stop, tell the user the file
and the commit, and have the secret revoked before anything else.

What it scans:
- the working tree: files git tracks plus untracked files git does not ignore (`git ls-files`);
  outside a git repository every file under <repo> except build and dependency folders.
  Ignored files such as `.env` are left alone: they are where real secrets are meant to live;
- `--staged`: the lines a commit would add (`git diff --cached`), for a pre-commit hook;
- `--history`: every line ever added on any branch (`git log -p --all`), where a removed secret
  still lives until it is revoked.

What it looks for:
- token formats of the services in use: Supabase secret keys (`sb_secret_`) and JWTs whose role
  is `service_role` (a JWT with role `anon` is the public key and is skipped), Stripe, Resend,
  OpenAI, Anthropic, GitHub, Google, AWS and Slack tokens, private-key blocks;
- an assignment of a variable named like a secret (ending in KEY, SECRET, TOKEN, PASSWORD,
  PASSWD or CREDENTIALS) to a literal value that is not a placeholder. Names with a public
  prefix (`NEXT_PUBLIC_`, `VITE_`, `PUBLIC_`) are left to the token patterns above;
- a tracked or added file whose name is in the secrets block of `gitignore-secrets` beside this
  script (a copy of the repository's `templates/gitignore-secrets`, the one owner of those
  names, kept identical by its tests), such as `.env`, `*.pem` or `service-account*.json`.

Exit 0 when nothing was found, 1 on any finding, 2 on a usage or git error. Reading is local;
nothing leaves the machine. Patterns are a known list, not entropy: a secret of a format not
listed here is not seen, which is why reviews still read the diff.
"""
from __future__ import annotations

import base64
import fnmatch
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IGNORE_TEMPLATE = os.path.join(HERE, 'gitignore-secrets')

TOKEN_PATTERNS = [
    ('supabase-secret-key', re.compile(r'\bsb_secret_[A-Za-z0-9_-]{20,}')),
    ('anthropic-api-key', re.compile(r'\bsk-ant-[A-Za-z0-9_-]{20,}')),
    ('openai-api-key', re.compile(r'\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_-]{20,}|'
                                  r'\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}')),
    ('stripe-live-secret', re.compile(r'\b[sr]k_live_[0-9A-Za-z]{20,}')),
    ('stripe-test-secret', re.compile(r'\b[sr]k_test_[0-9A-Za-z]{20,}')),
    ('stripe-webhook-secret', re.compile(r'\bwhsec_[0-9A-Za-z]{20,}')),
    ('resend-api-key', re.compile(r'\bre_[A-Za-z0-9]{6,}_[A-Za-z0-9]{16,}')),
    ('github-token', re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}|\bgithub_pat_[A-Za-z0-9_]{22,}')),
    ('google-api-key', re.compile(r'\bAIza[0-9A-Za-z_-]{35}')),
    ('google-oauth-client-secret', re.compile(r'\bGOCSPX-[A-Za-z0-9_-]{20,}')),
    ('aws-access-key-id', re.compile(r'\b(?:AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}\b')),
    ('slack-token', re.compile(r'\bxox[baprs]-[0-9A-Za-z-]{10,}')),
    ('private-key-block', re.compile(r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY(?: BLOCK)?-----')),
]
JWT = re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}')
ASSIGNMENT = re.compile(
    r'(?<![A-Za-z0-9_])(?:export\s+)?([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIALS))'
    r'\s*[=:]\s*["\']?([^\s"\'#,;]{12,})')
PUBLIC_PREFIXES = ('NEXT_PUBLIC_', 'VITE_', 'PUBLIC_', 'REACT_APP_', 'NUXT_PUBLIC_', 'EXPO_PUBLIC_')
PLACEHOLDER_WORDS = ('example', 'changeme', 'change-me', 'change_me', 'placeholder', 'your-',
                     'your_', 'yourkey', 'xxx', 'todo', 'dummy', 'sample', 'redacted', 'replace',
                     'insert', 'fill-in', 'fill_in', '<', '>', '${', '$(', '%(', '{{', '...', '…')
REFERENCE_VALUES = ('process.env', 'os.environ', 'os.getenv', 'env(', 'secrets.', 'vault:', 'op://',
                    'import.meta.env', 'getenv(', 'env[', 'env.', 'config.', 'settings.')
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'target', 'dist', 'build',
             '.next', '.turbo', '.cache', 'vendor', '.godot', 'DerivedData'}
MAX_BYTES = 2 * 1024 * 1024


def file_name_patterns():
    """The secret file names of gitignore-secrets, up to its OS/agent-state section."""
    patterns, dirs, keep = [], [], []
    try:
        with open(IGNORE_TEMPLATE, encoding='utf-8') as f:
            lines = f.read().splitlines()
    except OSError:
        return patterns, dirs, keep
    for line in lines:
        line = line.strip()
        if line.startswith('# --- OS'):
            break
        if not line or line.startswith('#'):
            continue
        if line.startswith('!'):
            keep.append(line[1:])
        elif line.endswith('/'):
            dirs.append(line[:-1])  # a directory pattern matches any folder on the path
        else:
            patterns.append(line)
    return patterns, dirs, keep


FILE_PATTERNS, DIR_PATTERNS, FILE_EXCEPTIONS = file_name_patterns()


def secret_file_name(path):
    parts = path.replace(os.sep, '/').split('/')
    base = parts[-1]
    if any(fnmatch.fnmatch(base, pat) for pat in FILE_EXCEPTIONS):
        return None
    for pat in FILE_PATTERNS:
        if fnmatch.fnmatch(base, pat):
            return pat
    for pat in DIR_PATTERNS:
        if any(fnmatch.fnmatch(part, pat) for part in parts[:-1]):
            return pat + '/'
    return None


REGEX_CHARS = set('^$[](){}|*?\\')


def is_placeholder(value):
    low = value.lower()
    if any(w in low for w in PLACEHOLDER_WORDS) or any(r in low for r in REFERENCE_VALUES):
        return True
    if REGEX_CHARS & set(value):  # a regular expression or code, not a token (measured)
        return True
    if len(set(low.strip('"\''))) <= 2:
        return True
    if re.fullmatch(r'[x*.#_\-0]+', low):
        return True
    return False


def jwt_role(token):
    """The `role` claim of a JWT payload, or None when it cannot be decoded."""
    try:
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims.get('role')
    except (ValueError, IndexError, TypeError):
        return None


def findings_in_line(line):
    """The pattern names that match one line of text; values stay inside this function."""
    found = []
    for name, rx in TOKEN_PATTERNS:
        if any(not is_placeholder(m.group(0)) for m in rx.finditer(line)):
            found.append(name)
    for m in JWT.finditer(line):
        role = jwt_role(m.group(0))
        if role == 'service_role':
            found.append('supabase-service-role-jwt')
        elif role not in ('anon', 'authenticated'):
            found.append('jwt')
    for m in ASSIGNMENT.finditer(line):
        name, value = m.group(1), m.group(2)
        if name.startswith(PUBLIC_PREFIXES) or is_placeholder(value):
            continue
        if (name == 'GPG_KEY' or name.endswith('_FINGERPRINT')) and re.fullmatch(r'[0-9A-Fa-f]{40}', value):
            continue  # a public key fingerprint, as in the official Python Docker image
        if JWT.fullmatch(value) and jwt_role(value) in ('anon', 'authenticated'):
            continue
        if not (re.search(r'[A-Za-z]', value) and re.search(r'[0-9]', value)) and '-----' not in value:
            continue
        found.append('secret-named-assignment:' + name)
    return found


def git(repo, *args, check=True):
    r = subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, errors='replace')
    if check and r.returncode != 0:
        raise RuntimeError('git %s: %s' % (args[0], r.stderr.strip()))
    return r.stdout


def is_git_repo(repo):
    r = subprocess.run(['git', '-C', repo, 'rev-parse', '--is-inside-work-tree'],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == 'true'


def tree_files(repo):
    if is_git_repo(repo):
        out = git(repo, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
        return [p for p in out.split('\0') if p]
    files = []
    for root, dirs, names in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            files.append(os.path.relpath(os.path.join(root, n), repo).replace(os.sep, '/'))
    return sorted(files)


def excluded(path, excludes):
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(os.path.basename(path), g) for g in excludes)


def scan_tree(repo, excludes):
    results = []
    for rel in tree_files(repo):
        if excluded(rel, excludes):
            continue
        pat = secret_file_name(rel)
        if pat:
            results.append(('tree', 'secret-file-name:' + pat, rel, 0, ''))
        full = os.path.join(repo, rel)
        try:
            if os.path.islink(full) or not os.path.isfile(full) or os.path.getsize(full) > MAX_BYTES:
                continue
            with open(full, 'rb') as f:
                head = f.read(8192)
                if b'\0' in head:
                    continue
                data = head + f.read()
        except OSError:
            continue
        for i, line in enumerate(data.decode('utf-8', errors='replace').splitlines(), 1):
            for name in findings_in_line(line):
                results.append(('tree', name, rel, i, ''))
    return results


def scan_diff(text, kind, excludes):
    """Findings in the added lines of a unified diff; `commit` lines mark history commits."""
    results, commit, path, line_no, after_minus = [], '', '', 0, False
    for raw in text.split('\n'):
        if raw.startswith('@@commit '):
            commit = raw[len('@@commit '):].strip()[:12]
        elif raw.startswith('--- ') and not after_minus:
            after_minus = True  # the next '+++ ' line is the file header, not content starting with '++ '
            continue
        elif raw.startswith('+++ ') and after_minus:
            after_minus = False
            path = raw[4:].strip()
            path = path[2:] if path.startswith('b/') else path
            if path != '/dev/null' and not excluded(path, excludes):
                pat = secret_file_name(path)
                if pat:
                    results.append((kind, 'secret-file-name:' + pat, path, 0, commit))
        elif raw.startswith('@@'):
            after_minus = False
            m = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)', raw)
            line_no = int(m.group(1)) - 1 if m else 0
        elif raw.startswith('+'):  # the '+++ ' header case was taken above
            line_no += 1
            if path == '/dev/null' or excluded(path, excludes):
                continue
            for name in findings_in_line(raw[1:]):
                results.append((kind, name, path, line_no, commit))
        elif raw.startswith(' '):
            line_no += 1
    return results


def scan_staged(repo, excludes):
    return scan_diff(git(repo, 'diff', '--cached', '--no-color', '-U0', '--no-ext-diff'), 'staged', excludes)


def scan_history(repo, excludes):
    text = git(repo, 'log', '--all', '--no-color', '-p', '-U0', '--no-ext-diff', '--format=@@commit %H')
    return scan_diff(text, 'history', excludes)


def main(argv):
    repo, history, staged, excludes = None, False, False, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--history':
            history = True
        elif a == '--staged':
            staged = True
        elif a == '--exclude':
            if i + 1 >= len(argv):
                print(__doc__, file=sys.stderr); return 2
            excludes.append(argv[i + 1]); i += 1
        elif a in ('-h', '--help'):
            print(__doc__); return 0
        elif a.startswith('-') or repo is not None:
            print(__doc__, file=sys.stderr); return 2
        else:
            repo = a
        i += 1
    if repo is None or not os.path.isdir(repo):
        print(__doc__, file=sys.stderr); return 2
    repo = os.path.abspath(repo)
    try:
        results = scan_tree(repo, excludes)
        if staged or history:
            if not is_git_repo(repo):
                print('scan_secrets: %s is not a git repository; --staged/--history need one' % repo,
                      file=sys.stderr)
                return 2
            if staged:
                results += scan_staged(repo, excludes)
            if history:
                results += scan_history(repo, excludes)
    except RuntimeError as exc:
        print('scan_secrets: %s' % exc, file=sys.stderr)
        return 2
    seen = set()
    for kind, name, path, line, commit in results:
        key = (kind, name, path, line, commit)
        if key in seen:
            continue
        seen.add(key)
        where = path if not line else '%s:%d' % (path, line)
        print('%s\t%s\t%s%s' % (kind, name, where, ('\t' + commit) if commit else ''))
    counts = {}
    for kind, *_ in seen:
        counts[kind] = counts.get(kind, 0) + 1
    scope = ['tree'] + (['staged'] if staged else []) + (['history'] if history else [])
    print('scan_secrets: %s; %d finding(s)%s' % (
        ', '.join(scope), len(seen),
        '' if not seen else ' (' + ', '.join('%s %d' % kv for kv in sorted(counts.items())) + ')'))
    return 1 if seen else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
