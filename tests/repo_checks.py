#!/usr/bin/env python3
"""Checks that hold for the repository as a whole: python3 tests/repo_checks.py.

- hygiene: no e-mail address in a tracked file other than no-reply, git-host and example
  domains (tests/personal_data_guard.py is exempt: its fixtures must look real to the hook), and no
  absolute home path (a macOS or Windows user folder, or a Linux home); the secret scanner of the
  security plugin is clean on the tree;
- attribution: NOTICE carries the copyright line; every plugin manifest has the author and
  homepage, both marketplace files the owner; the author is named nowhere in rules/ or a skill;
- manifests: each plugin's two manifests and both marketplace entries agree on name and version,
  every plugin folder is listed, the repository URL is the same everywhere it is written, and a
  plugin whose files differ from the default branch (origin/main, when fetched) has a new version;
- copies: the security plugin's gitignore-secrets is byte-identical to templates/gitignore-secrets;
- installer commands: every option on a line of README.md or docs/*.md that runs install.sh or
  install.ps1, and every row of an options table (a row starting with a backticked `--option`),
  is one tools/installer.py accepts, with a known plugin after --with and a known guard after
  --guards, so a guide never names a stale command (#91);
- review dates: a DESIGN_DECISIONS.md entry with `**Review by:** YYYY-MM-DD` fails the check once
  that date has passed, so the value it fixes is looked at again (#77).
The author's name is assembled below, so this file does not count as a mention.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
AUTHOR = 'MAI' + '-Tech'
SITE = 'https://mai-tech' + '.be'
NOTICE_LINE = 'agentic-github-flow, Copyright 2026 %s (%s)' % (AUTHOR, SITE)
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}')
ALLOWED_EMAIL = re.compile(r'(?:^|[.@])(?:example\.(?:com|org|net)|[a-z0-9-]+\.(?:example|test|'
                           r'invalid|localhost))$|^(?:no-?reply|noreply\+[^@]*)@|'
                           r'@users\.noreply\.github\.com$|^git@|'
                           r'\.(?:service|socket|target|timer|slice|scope|mount)$', re.I)
EMAIL_EXEMPT = {'tests/personal_data_guard.py'}
HOME_PATH = re.compile(r'/' + r'Users/[A-Za-z]|[A-Za-z]:\\\\?' + r'Users\\\\?[A-Za-z]|/' +
                       r'home/[a-z][a-z0-9_-]+/', re.I)
HOME_OK = re.compile(r'/' + r'home/runner/')  # GitHub's runner, should a path to it be written
errors = []


def fail(message):
    errors.append(message)


def git(*args):
    return subprocess.run(['git', '-C', ROOT, *args], capture_output=True, text=True)


def tracked_files():
    listed = git('ls-files', '-z', '--cached', '--others', '--exclude-standard')
    if listed.returncode == 0:
        return [p for p in listed.stdout.split('\0') if p]
    found = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', '.state', 'overlays')]
        found += [os.path.relpath(os.path.join(base, f), ROOT).replace(os.sep, '/') for f in files]
    return found


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8', errors='replace') as f:
        return f.read()


def load(rel):
    return json.loads(read(rel))


files = tracked_files()

# hygiene
for rel in files:
    if rel == 'LICENSE' or rel.endswith(('.png', '.jpg', '.ico')):
        continue
    text = read(rel)
    for address in [] if rel in EMAIL_EXEMPT else EMAIL.findall(text):
        if not ALLOWED_EMAIL.search(address):
            fail('%s: an e-mail address that is not no-reply or an example domain (%s…)'
                 % (rel, address[:2]))
    for m in HOME_PATH.finditer(text):
        if not HOME_OK.match(text, m.start()):
            fail('%s: an absolute home path at offset %d' % (rel, m.start()))
scan = subprocess.run([sys.executable, os.path.join(ROOT, 'plugins', 'security', 'scripts',
                                                    'scan_secrets.py'), ROOT],
                      capture_output=True, text=True)
if scan.returncode != 0:
    fail('scan_secrets: ' + scan.stdout.strip().replace('\n', '; '))

# attribution
if NOTICE_LINE not in read('NOTICE'):
    fail('NOTICE lacks the line: ' + NOTICE_LINE)
if SITE not in read('README.md'):
    fail('README.md lacks the link to ' + SITE)
plugins = sorted(p for p in os.listdir(os.path.join(ROOT, 'plugins'))
                 if os.path.isdir(os.path.join(ROOT, 'plugins', p)))
manifests = {}
for plugin in plugins:
    for kind in ('.claude-plugin', '.codex-plugin'):
        rel = 'plugins/%s/%s/plugin.json' % (plugin, kind)
        if rel not in files:
            fail('%s is missing' % rel)
            continue
        data = load(rel)
        manifests[(plugin, kind)] = data
        if (data.get('author') or {}).get('name') != AUTHOR:
            fail('%s: author.name must be %s' % (rel, AUTHOR))
        if data.get('homepage') != SITE:
            fail('%s: homepage must be %s' % (rel, SITE))
markets = {'.claude-plugin/marketplace.json': load('.claude-plugin/marketplace.json'),
           '.agents/plugins/marketplace.json': load('.agents/plugins/marketplace.json')}
for rel, data in markets.items():
    if (data.get('owner') or {}).get('name') != AUTHOR:
        fail('%s: owner.name must be %s' % (rel, AUTHOR))
for rel in files:
    if rel.startswith('rules/') or '/skills/' in rel:
        if AUTHOR.lower() in read(rel).lower():
            fail('%s names the author; attribution belongs in README, NOTICE and manifests' % rel)

# manifests agree
claude_entries = {e['name']: e for e in markets['.claude-plugin/marketplace.json']['plugins']}
codex_entries = {e['name']: e for e in markets['.agents/plugins/marketplace.json']['plugins']}
repo_urls = set()
for plugin in plugins:
    claude, codex = manifests.get((plugin, '.claude-plugin')), manifests.get((plugin, '.codex-plugin'))
    if not claude or not codex:
        continue
    name = claude['name']
    if not name.startswith('agentic-github-flow-'):
        fail('%s: plugin name %s must start with agentic-github-flow-' % (plugin, name))
    if codex['name'] != name or codex.get('version') != claude.get('version'):
        fail('%s: the Claude and Codex manifests differ in name or version' % plugin)
    entry = claude_entries.get(name)
    if not entry:
        fail('%s is not listed in .claude-plugin/marketplace.json' % name)
    elif entry.get('version') != claude.get('version') or entry.get('source') != './plugins/' + plugin:
        fail('%s: its .claude-plugin/marketplace.json entry differs in version or source' % name)
    if plugin != 'guards':
        centry = codex_entries.get(name)
        if not centry or (centry.get('source') or {}).get('path') != './plugins/' + plugin:
            fail('%s is not listed with its path in .agents/plugins/marketplace.json' % name)
    elif name in codex_entries:
        fail('the guards plugin holds Claude hooks only; keep it out of the Codex marketplace')
    repo_urls |= {claude.get('repository'), codex.get('repository'), (entry or {}).get('repository')}
for rel in ('install.sh', 'install.ps1', 'README.md', 'docs/install.md'):
    repo_urls |= {u[:-4] for u in re.findall(r'https://github\.com/[\w.-]+/agentic-github-flow\.git',
                                            read(rel))}
if len(repo_urls - {None}) != 1:
    fail('the repository URL differs between files: %s' % sorted(u for u in repo_urls if u))
base = git('rev-parse', '-q', '--verify', 'refs/remotes/origin/main')
if base.returncode == 0:
    for plugin in plugins:
        rel = 'plugins/%s/.claude-plugin/plugin.json' % plugin
        changed = git('diff', '--quiet', 'origin/main', '--', 'plugins/' + plugin).returncode != 0
        old = git('show', 'origin/main:' + rel)
        if changed and old.returncode == 0 and \
                json.loads(old.stdout).get('version') == manifests[(plugin, '.claude-plugin')].get('version'):
            fail('%s changed since origin/main but its version did not: installed copies would '
                 'keep the old files' % plugin)

# installer commands in the user documents (#91)
installer = read('tools/installer.py')
accepted = set(re.findall(r"add_argument\('(--[\w-]+)'", installer)) - {'--resume-update'}
known = {'--with': set(re.findall(r"'([\w-]+)': 'agentic-github-flow-", installer)) - {'core', 'guards'},
         '--guards': set(re.findall(r"'(\w+)'", re.search(r'GUARD_EXTRAS = \(([^)]*)\)',
                                                         installer).group(1)))}
OPTION = re.compile(r'(?<![\w-])(--[a-z][\w-]*)(?: ([a-z][\w,-]*))?')
for rel in ['README.md'] + sorted(f for f in files if f.startswith('docs/') and f.endswith('.md')):
    for number, line in enumerate(read(rel).splitlines(), 1):
        if re.search(r'install\.(?:sh|ps1)', line):
            text = re.split(r'install\.(?:sh|ps1)', line, maxsplit=1)[1]
        elif re.match(r'\|\s*`--', line):
            text = line.split('|')[1]
        else:
            continue
        for option, value in OPTION.findall(text):
            if option not in accepted:
                fail('%s:%d: the installer has no option %s' % (rel, number, option))
            elif option in known and value and not set(value.split(',')) <= known[option]:
                fail('%s:%d: %s %s names what the installer does not know (choose from %s)'
                     % (rel, number, option, value, ', '.join(sorted(known[option]))))

# copies
if read('templates/gitignore-secrets') != read('plugins/security/scripts/gitignore-secrets'):
    fail('plugins/security/scripts/gitignore-secrets differs from templates/gitignore-secrets')

# review dates: a decision that carries `**Review by:** YYYY-MM-DD` is looked at again by then
import datetime  # noqa: E402
today = datetime.date.today().isoformat()
for m in re.finditer(r'^## (.+?)\n(?:(?!^## ).*\n)*?.*\*\*Review by:\*\* (\d{4}-\d{2}-\d{2})(.*)$',
                     read('DESIGN_DECISIONS.md'), re.M):
    if m.group(2) < today:
        fail('DESIGN_DECISIONS.md: "%s" was due for review on %s%s Review it with the '
             'maintainer, record the outcome and set the next date.'
             % (m.group(1), m.group(2), m.group(3).rstrip()))

if errors:
    print('\n'.join(errors))
    sys.exit(1)
print('OK: %d files clean; attribution, %d plugins and their manifests agree; copies identical'
      % (len(files), len(plugins)))
