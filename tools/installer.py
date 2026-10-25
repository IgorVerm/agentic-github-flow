#!/usr/bin/env python3
"""The agentic-github-flow installer: always-loaded rules, plugins, optional guards and overlays.

Run it through install.sh (macOS, Linux) or install.ps1 (Windows): they find Python, make sure
the clone exists in ~/.agentic-github-flow and start this file from it.

Usage:
  installer.py [--with security,web-deploy] [--guards] [--overlay <git-url-or-path>]...
               [--no-claude] [--no-codex] [--claude-bin <path>] [--codex-bin <path>]
  installer.py --update      pull the clone, then repeat the recorded install
  installer.py --uninstall   undo what the record says this installer added

What it does, per client (Claude Code, Codex):
- Rules: one marked block in ~/.claude/CLAUDE.md that imports rules/core.md and each overlay's
  AGENTS.md, and one in ~/.codex/AGENTS.md with the same text inlined (Codex does not follow
  imports there: measured with `codex debug prompt-input`, codex-cli 0.164). Lines outside the
  block are never touched. A symlinked file is refused, before anything changes.
- Plugins: registers this clone as the `agentic-github-flow` marketplace and installs the core
  plugin, plus those named with --with (web-deploy brings security).
- Guards (--guards): the guards plugin (Claude hooks), the ask and deny lists merged into
  ~/.claude/settings.json (a backup is kept), the Codex execpolicy rules linked into
  ~/.codex/rules/ and the git guard added to ~/.codex/hooks.json.
- Overlays (--overlay): a folder with an AGENTS.md, or a git URL cloned into overlays/ here
  (a second URL with the same name gets a suffix); their text follows the core rules in both
  blocks.
A client whose command and folder are both missing is skipped, and the installer says so.
Everything it adds is recorded in .state/install.json in the clone, so --update repeats it and
--uninstall removes exactly that; a file that became a symlink since is skipped, with a note. Nothing is sent anywhere except the git and plugin fetches.
Exit: 0 done; 1 a step failed (the rest ran); 2 usage; 3 refused before any change.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

CLONE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET = 'agentic-github-flow'
PLUGINS = {'core': 'agentic-github-flow-core', 'security': 'agentic-github-flow-security',
           'web-deploy': 'agentic-github-flow-web-deploy', 'guards': 'agentic-github-flow-guards'}
NEEDS = {'web-deploy': ['security']}
BEGIN = '<!-- >>> agentic-github-flow >>> -->'
END = '<!-- <<< agentic-github-flow <<< -->'
NOTE = ('<!-- Managed by the agentic-github-flow installer: edit outside these markers; '
        'remove with --uninstall. -->')
CODEX_LIMIT = 32 * 1024
WINDOWS = os.name == 'nt'


class Refused(Exception):
    """A check before any change failed; nothing was written."""


# ---- paths and state --------------------------------------------------------------------------

def home():
    return os.path.expanduser('~')


def claude_dir():
    return os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(home(), '.claude')


def codex_dir():
    return os.environ.get('CODEX_HOME') or os.path.join(home(), '.codex')


def state_path():
    return os.path.join(CLONE, '.state', 'install.json')


def load_state():
    try:
        with open(state_path(), encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(state_path()), exist_ok=True)
    with open(state_path(), 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write('\n')


def read_text(path):
    """The file's text with its line endings as they are, or None when it does not exist."""
    try:
        with open(path, encoding='utf-8', newline='') as f:
            return f.read()
    except FileNotFoundError:
        return None


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def say(status, message):
    print('%-5s %s' % (status, message), flush=True)


# ---- the rules blocks -------------------------------------------------------------------------

def import_path(path):
    """A path as a Claude `@` import: `~/` under the home folder, forward slashes, spaces escaped."""
    path = os.path.abspath(path)
    h = home()
    if path == h or path.startswith(h + os.sep):
        path = '~' + path[len(h):]
    return path.replace('\\', '/').replace(' ', '\\ ')


def claude_block(overlays):
    lines = [BEGIN, NOTE, '@' + import_path(os.path.join(CLONE, 'rules', 'core.md'))]
    lines += ['@' + import_path(os.path.join(o['path'], 'AGENTS.md')) for o in overlays]
    return '\n'.join(lines + [END]) + '\n'


def codex_block(overlays):
    parts = [read_text(os.path.join(CLONE, 'rules', 'core.md')).strip('\n')]
    for o in overlays:
        parts.append(read_text(os.path.join(o['path'], 'AGENTS.md')).strip('\n'))
    return '\n'.join([BEGIN, NOTE, '\n\n'.join(parts), END]) + '\n'


def find_block(text):
    """(start, end) of the block's lines in text, or None."""
    begin = text.find(BEGIN)
    if begin < 0:
        return None
    finish = text.find(END, begin)
    if finish < 0:
        raise Refused('a block start marker without its end marker; fix the file by hand')
    start = text.rfind('\n', 0, begin) + 1
    end = text.find('\n', finish)
    return start, (len(text) if end < 0 else end + 1)


def put_block(path, block, record):
    """Insert or replace the block. record holds how the file looked before the first install."""
    text = read_text(path)
    if text is None:
        record.setdefault('created', True)
        record.setdefault('added_newline', False)
        write_text(path, block)
        return
    found = find_block(text)
    if found:
        record.setdefault('created', False)
        record.setdefault('added_newline', False)
        write_text(path, text[:found[0]] + block + text[found[1]:])
        return
    record['created'] = False
    record['added_newline'] = bool(text) and not text.endswith('\n')
    write_text(path, text + ('\n' if record['added_newline'] else '') + block)


def drop_block(path, record):
    """Remove the block, restoring the file's bytes from before the install."""
    text = read_text(path)
    if text is None:
        return False
    found = find_block(text)
    if not found:
        return False
    start, end = found
    rest = text[:start] + text[end:]
    if record.get('added_newline') and end == len(text) and rest.endswith('\n'):
        rest = rest[:-1]
    if record.get('created') and rest == '':
        os.remove(path)
    else:
        write_text(path, rest)
    return True


# ---- running the clients ----------------------------------------------------------------------

def run(command, cwd=None):
    """(ok, output) of a client command; output is the last lines of stdout and stderr."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, cwd=cwd or home(),
                                timeout=600, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    output = (result.stdout + '\n' + result.stderr).strip().splitlines()
    return result.returncode == 0, ' / '.join(output[-3:])


def find_client(name, override):
    if override:
        return override if os.path.exists(override) else None
    return shutil.which(name)


def client_plan(args, state):
    """{client: {'bin': path or None, 'dir': config dir}} for the clients this run sets up."""
    plan = {}
    for name, folder, skip, override in (
            ('claude', claude_dir(), args.no_claude, args.claude_bin or state.get('claude_bin')),
            ('codex', codex_dir(), args.no_codex, args.codex_bin or state.get('codex_bin'))):
        if skip:
            say('skip', '%s: --no-%s' % (name, name))
            continue
        binary = find_client(name, override)
        if not binary and not os.path.isdir(folder):
            say('skip', '%s: neither the `%s` command nor %s was found' % (name, name, folder))
            continue
        plan[name] = {'bin': binary, 'dir': folder}
    return plan


def marketplace_names(binary):
    """The configured marketplace names; both clients print a list or {"marketplaces": [...]}."""
    try:
        result = subprocess.run([binary, 'plugin', 'marketplace', 'list', '--json'],
                                capture_output=True, text=True, cwd=home(), timeout=120,
                                stdin=subprocess.DEVNULL)
        data = json.loads(result.stdout or '[]')
    except (OSError, subprocess.SubprocessError, ValueError):
        return set()
    items = data if isinstance(data, list) else data.get('marketplaces', [])
    return {m.get('name') for m in items if isinstance(m, dict)}


def install_plugins(client, binary, wanted, state, failures, updating):
    """Register the marketplace and install the wanted plugins for one client."""
    record = state.setdefault('plugins', {}).setdefault(client, [])
    if MARKET not in marketplace_names(binary):
        ok, out = run([binary, 'plugin', 'marketplace', 'add', CLONE])
        if not ok:
            failures.append('%s: marketplace add: %s' % (client, out))
            say('FAIL', '%s: marketplace add: %s' % (client, out))
            return
        state.setdefault('marketplace', {})[client] = True
        say('ok', '%s: marketplace %s added from %s' % (client, MARKET, CLONE))
    elif updating and client == 'claude':
        ok, out = run([binary, 'plugin', 'marketplace', 'update', MARKET])
        say('ok' if ok else 'FAIL', 'claude: marketplace update: %s' % out)
    for key in wanted:
        plugin = '%s@%s' % (PLUGINS[key], MARKET)
        if client == 'claude':
            command = [binary, 'plugin', 'update' if updating and key in record else 'install',
                       plugin]
        else:
            command = [binary, 'plugin', 'add', plugin]
        ok, out = run(command)
        if ok:
            if key not in record:
                record.append(key)
            say('ok', '%s: %s %s' % (client, command[2], plugin))
        else:
            failures.append('%s: %s: %s' % (client, plugin, out))
            say('FAIL', '%s: %s %s: %s' % (client, command[2], plugin, out))


def remove_plugins(client, binary, state):
    for key in reversed(state.get('plugins', {}).get(client, [])):
        plugin = '%s@%s' % (PLUGINS[key], MARKET)
        command = [binary, 'plugin', 'uninstall' if client == 'claude' else 'remove', plugin]
        ok, out = run(command)
        say('ok' if ok else 'FAIL', '%s: remove %s%s' % (client, plugin, '' if ok else ': ' + out))
    if state.get('marketplace', {}).get(client):
        ok, out = run([binary, 'plugin', 'marketplace', 'remove', MARKET])
        say('ok' if ok else 'FAIL', '%s: marketplace %s removed%s' % (
            client, MARKET, '' if ok else ': ' + out))


# ---- guards -----------------------------------------------------------------------------------

def load_json(path):
    text = read_text(path)
    if text is None or not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError as error:
        raise Refused('%s is not valid JSON (%s); fix it by hand first' % (path, error))
    if not isinstance(data, dict):
        raise Refused('%s does not hold a JSON object; fix it by hand first' % path)
    return data


def dump_json(path, data):
    write_text(path, json.dumps(data, indent=2) + '\n')


def backup(path):
    if os.path.exists(path):
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        shutil.copy2(path, '%s.agentic-github-flow-backup-%s' % (path, stamp))


def merge_permissions(state):
    path = os.path.join(claude_dir(), 'settings.json')
    with open(os.path.join(CLONE, 'plugins', 'guards', 'policy', 'claude-permissions.json'),
              encoding='utf-8') as f:
        wanted = json.load(f)['permissions']
    data = load_json(path)
    created = data is None
    data = data if data is not None else {}
    permissions = data.setdefault('permissions', {})
    record = state.setdefault('settings', {'created': created, 'added': {}})
    added_now = 0
    for kind in ('ask', 'deny'):
        current = permissions.setdefault(kind, [])
        for rule in wanted[kind]:
            if rule not in current:
                current.append(rule)
                record['added'].setdefault(kind, []).append(rule)
                added_now += 1
    if added_now:
        backup(path)
        dump_json(path, data)
    say('ok', 'claude: %d ask and deny rules merged into %s (%d new)' % (
        len(wanted['ask']) + len(wanted['deny']), path, added_now))


def linked(path, what):
    """True (and says so) when path is a symlink, which the installer never writes through."""
    if os.path.islink(path):
        say('skip', '%s is a symlink (to %s); %s left as they are: remove them by hand'
            % (path, os.readlink(path), what))
        return True
    return False


def unmerge_permissions(state):
    record = state.get('settings')
    path = os.path.join(claude_dir(), 'settings.json')
    if not record or linked(path, 'the merged ask and deny rules'):
        return
    data = load_json(path) or {}
    permissions = data.get('permissions', {})
    removed = 0
    for kind, rules in record.get('added', {}).items():
        current = permissions.get(kind, [])
        for rule in rules:
            if rule in current:
                current.remove(rule)
                removed += 1
        if kind in permissions and not current:
            del permissions[kind]
    if 'permissions' in data and not data['permissions']:
        del data['permissions']
    backup(path)
    if record.get('created') and not data:
        os.remove(path)
    else:
        dump_json(path, data)
    say('ok', 'claude: %d rules removed from %s' % (removed, path))


def guard_command():
    script = os.path.join(CLONE, 'plugins', 'guards', 'scripts', 'pre_tool_git_guard.py')
    return '"%s" "%s"' % (sys.executable, script)


def codex_guards(state):
    rules_dir = os.path.join(codex_dir(), 'rules')
    target = os.path.join(rules_dir, 'agentic-github-flow-git-safety.rules')
    source = os.path.join(CLONE, 'plugins', 'guards', 'policy', 'git-safety.rules')
    os.makedirs(rules_dir, exist_ok=True)
    if os.path.lexists(target):
        os.remove(target)
    if WINDOWS:
        shutil.copyfile(source, target)
    else:
        os.symlink(source, target)
    state['codex_rules'] = target
    say('ok', 'codex: execpolicy rules %s at %s' % ('copied' if WINDOWS else 'linked', target))

    path = os.path.join(codex_dir(), 'hooks.json')
    data = load_json(path)
    created = data is None
    data = data if data is not None else {}
    entries = data.setdefault('hooks', {}).setdefault('PreToolUse', [])
    command = guard_command()
    entry = {'matcher': 'Bash', 'hooks': [{'type': 'command', 'command': command, 'timeout': 10,
                                           'statusMessage': 'Checking git command'}]}
    old = state.get('codex_hook', {}).get('entry')
    if old in entries and old != entry:
        entries.remove(old)
    if entry not in entries:
        backup(path)
        entries.append(entry)
        dump_json(path, data)
        say('ok', 'codex: git guard added to %s; trust it once in Codex with /hooks' % path)
    else:
        say('ok', 'codex: git guard already in %s' % path)
    state['codex_hook'] = {'entry': entry,
                           'created': state.get('codex_hook', {}).get('created', created)}


def remove_codex_guards(state):
    target = state.get('codex_rules')
    source = os.path.join(CLONE, 'plugins', 'guards', 'policy', 'git-safety.rules')
    if target and os.path.lexists(target):
        ours = (os.path.islink(target) and os.path.realpath(target) == os.path.realpath(source)) \
            or (not os.path.islink(target) and read_text(target) == read_text(source))
        if ours:
            os.remove(target)
            say('ok', 'codex: removed %s' % target)
        else:
            say('skip', 'codex: %s changed since the install; left as it is' % target)
    hook = state.get('codex_hook')
    path = os.path.join(codex_dir(), 'hooks.json')
    if not hook or linked(path, 'the git guard entry'):
        return
    data = load_json(path) or {}
    entries = data.get('hooks', {}).get('PreToolUse', [])
    if hook['entry'] in entries:
        entries.remove(hook['entry'])
        if not entries:
            del data['hooks']['PreToolUse']
        if not data.get('hooks'):
            data.pop('hooks', None)
        backup(path)
        if hook.get('created') and not data:
            os.remove(path)
        else:
            dump_json(path, data)
        say('ok', 'codex: git guard removed from %s' % path)


# ---- overlays ---------------------------------------------------------------------------------

def resolve_overlays(sources, updating, failures):
    """[{source, path, cloned}] for the overlays, cloning or pulling git URLs."""
    result = []
    for source in sources:
        local = os.path.expanduser(source)
        if os.path.isdir(local):
            entry = {'source': source, 'path': os.path.abspath(local), 'cloned': False}
        else:
            name = re.sub(r'[^A-Za-z0-9._-]', '-', source.rstrip('/').rsplit('/', 1)[-1])
            name = name[:-4] if name.endswith('.git') else name
            dest = os.path.join(CLONE, 'overlays', name or 'overlay')
            if os.path.isdir(dest) and run(['git', '-C', dest, 'remote', 'get-url', 'origin'])[1] \
                    != source:  # another overlay with the same name: keep both apart
                dest += '-' + hashlib.sha1(source.encode('utf-8')).hexdigest()[:8]
            if not os.path.isdir(dest):
                ok, out = run(['git', 'clone', '--quiet', source, dest])
                if not ok:
                    raise Refused('overlay %s: git clone failed: %s' % (source, out))
                say('ok', 'overlay cloned into %s' % dest)
            elif updating:
                ok, out = run(['git', '-C', dest, 'pull', '--ff-only', '--quiet'])
                if not ok:
                    failures.append('overlay %s: pull: %s' % (source, out))
                say('ok' if ok else 'FAIL', 'overlay %s pulled%s' % (dest, '' if ok else ': ' + out))
            entry = {'source': source, 'path': dest, 'cloned': True}
        if not os.path.isfile(os.path.join(entry['path'], 'AGENTS.md')):
            raise Refused('overlay %s has no AGENTS.md at its root' % source)
        result.append(entry)
    return result


# ---- the steps --------------------------------------------------------------------------------

def preflight(plan, guards, state):
    """Refuse before any change when a file this run would edit is a symlink or unreadable."""
    rules = os.path.join(codex_dir(), 'rules', 'agentic-github-flow-git-safety.rules')
    if guards and 'codex' in plan and os.path.lexists(rules) and not state.get('codex_rules'):
        raise Refused('%s exists and was not made by this installer; move it away first' % rules)
    files = []
    if 'claude' in plan:
        files.append(os.path.join(claude_dir(), 'CLAUDE.md'))
        if guards:
            files.append(os.path.join(claude_dir(), 'settings.json'))
    if 'codex' in plan:
        files.append(os.path.join(codex_dir(), 'AGENTS.md'))
        if guards:
            files.append(os.path.join(codex_dir(), 'hooks.json'))
    for path in files:
        if os.path.islink(path):
            raise Refused(
                '%s is a symlink (to %s). The installer does not write through a link: that would '
                'change the file it points to. Replace the link with a plain file (for example '
                'by copying its target), or skip this client with --no-claude or --no-codex, and '
                'run the installer again. Nothing was changed.' % (path, os.readlink(path)))
        if path.endswith('.json'):
            load_json(path)
        else:
            text = read_text(path)
            if text is not None:
                find_block(text)


def install(args, state, updating=False):
    failures = []
    wanted = ['core'] + [w for w in args.with_plugins if w != 'core']
    for key in list(wanted):
        for need in NEEDS.get(key, []):
            if need not in wanted:
                wanted.insert(wanted.index(key), need)
    plan = client_plan(args, state)
    if not plan:
        say('FAIL', 'no client found: install Claude Code or Codex first')
        return 1
    preflight(plan, args.guards, state)
    overlays = resolve_overlays(args.overlay, updating, failures)
    state.update({'with': [w for w in wanted if w != 'core'], 'guards': args.guards,
                  'overlays': overlays, 'clients': sorted(plan),
                  'claude_bin': args.claude_bin or state.get('claude_bin'),
                  'codex_bin': args.codex_bin or state.get('codex_bin')})
    blocks = state.setdefault('blocks', {})
    for client, info in plan.items():
        if client == 'claude':
            path = os.path.join(info['dir'], 'CLAUDE.md')
            put_block(path, claude_block(overlays), blocks.setdefault('claude', {'path': path}))
            say('ok', 'claude: rules block in %s' % path)
        else:
            path = os.path.join(info['dir'], 'AGENTS.md')
            block = codex_block(overlays)
            put_block(path, block, blocks.setdefault('codex', {'path': path}))
            size = len(read_text(path).encode('utf-8'))
            say('ok', 'codex: rules block (%d bytes) in %s' % (len(block.encode('utf-8')), path))
            if size > CODEX_LIMIT * 3 // 4:
                say('warn', 'codex: %s is %d bytes; Codex reads 32 KiB of global and project '
                            'AGENTS.md together' % (path, size))
        save_state(state)
        if not info['bin']:
            say('skip', '%s: plugins not installed: the `%s` command was not found (run '
                        '--update once it is on PATH)' % (client, client))
            continue
        keys = wanted + (['guards'] if args.guards and client == 'claude' else [])
        install_plugins(client, info['bin'], keys, state, failures, updating)
        save_state(state)
    if args.guards:
        if 'claude' in plan:
            merge_permissions(state)
        if 'codex' in plan:
            codex_guards(state)
        save_state(state)
    say('done' if not failures else 'FAIL', 'installed from %s%s' % (
        CLONE, '' if not failures else '; failed: ' + '; '.join(failures)))
    if 'claude' in plan or 'codex' in plan:
        print('      Start a new session in each client to load the rules and skills.')
    return 1 if failures else 0


def uninstall(args, state):
    if not state:
        say('warn', 'no install record in %s: removing the rules blocks only' % state_path())
    plan = {}
    for client, folder in (('claude', claude_dir()), ('codex', codex_dir())):
        binary = find_client(client, state.get('%s_bin' % client))
        plan[client] = {'bin': binary, 'dir': folder}
    if state.get('guards'):
        unmerge_permissions(state)
        remove_codex_guards(state)
    for client, info in plan.items():
        if info['bin']:
            remove_plugins(client, info['bin'], state)
        elif state.get('plugins', {}).get(client):
            say('FAIL', '%s: the `%s` command is gone; remove the plugins by hand' % (
                client, client))
    for client, name in (('claude', 'CLAUDE.md'), ('codex', 'AGENTS.md')):
        record = state.get('blocks', {}).get(client, {})
        path = record.get('path') or os.path.join(plan[client]['dir'], name)
        if os.path.islink(path):
            say('skip', '%s is a symlink; not touched' % path)
        elif drop_block(path, record):
            say('ok', '%s: rules block removed from %s' % (client, path))
    try:
        os.remove(state_path())
    except FileNotFoundError:
        pass
    say('done', 'uninstalled. The clone %s stays; delete that folder to remove it completely.'
        % CLONE)
    return 0


def update(args, state):
    if not state:
        say('FAIL', 'no install record in %s: run the installer without --update first'
            % state_path())
        return 1
    if os.path.isdir(os.path.join(CLONE, '.git')):
        dirty = subprocess.run(['git', '-C', CLONE, 'status', '--porcelain',
                                '--untracked-files=no'], capture_output=True, text=True).stdout
        if dirty.strip():
            raise Refused('the clone %s has local changes; the update would not merge them' % CLONE)
        ok, out = run(['git', '-C', CLONE, 'pull', '--ff-only', '--quiet'])
        if not ok:
            say('FAIL', 'git pull in %s: %s' % (CLONE, out))
            return 1
        say('ok', 'clone updated: %s' % subprocess.run(
            ['git', '-C', CLONE, 'log', '-1', '--format=%h %s'], capture_output=True,
            text=True).stdout.strip())
    # the pulled installer may differ from the one running: hand over to it
    command = [sys.executable, os.path.abspath(__file__), '--resume-update']
    return subprocess.run(command).returncode


def resume_update(args, state):
    args.with_plugins = state.get('with', [])
    args.guards = state.get('guards', False)
    args.overlay = [o['source'] for o in state.get('overlays', [])]
    clients = state.get('clients', ['claude', 'codex'])
    args.no_claude = 'claude' not in clients
    args.no_codex = 'codex' not in clients
    return install(args, state, updating=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='install', description='Install agentic-github-flow for Claude Code and Codex.')
    parser.add_argument('--with', dest='with_plugins', default='',
                        help='extra plugins, comma-separated: security, web-deploy')
    parser.add_argument('--guards', action='store_true',
                        help='also install the git and personal-data guards')
    parser.add_argument('--overlay', action='append', default=[], metavar='GIT-URL-OR-PATH',
                        help='a company or personal overlay with an AGENTS.md (repeatable)')
    parser.add_argument('--update', action='store_true', help='pull and repeat the install')
    parser.add_argument('--uninstall', action='store_true', help='undo the install')
    parser.add_argument('--no-claude', action='store_true', help='leave Claude Code alone')
    parser.add_argument('--no-codex', action='store_true', help='leave Codex alone')
    parser.add_argument('--claude-bin', help='path to the claude command')
    parser.add_argument('--codex-bin', help='path to the codex command')
    parser.add_argument('--resume-update', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    args.with_plugins = [w.strip() for w in args.with_plugins.split(',') if w.strip()]
    unknown = [w for w in args.with_plugins if w not in PLUGINS or w == 'guards']
    if unknown:
        parser.error('unknown plugin(s) for --with: %s (choose from security, web-deploy; '
                     'guards come with --guards)' % ', '.join(unknown))
    if sum(map(bool, (args.update, args.uninstall))) > 1:
        parser.error('--update and --uninstall do not combine')
    if (args.update or args.uninstall) and (args.with_plugins or args.guards or args.overlay):
        parser.error('--update and --uninstall repeat or undo the recorded install; '
                     'run the installer without them to change what is installed')
    state = load_state()
    try:
        if args.uninstall:
            return uninstall(args, state)
        if args.resume_update:
            return resume_update(args, state)
        if args.update:
            return update(args, state)
        if state:  # a second plain run keeps what an earlier run installed
            args.with_plugins = sorted(set(args.with_plugins) | set(state.get('with', [])),
                                       key=list(PLUGINS).index)
            args.guards = args.guards or state.get('guards', False)
            known = [o['source'] for o in state.get('overlays', [])]
            args.overlay = known + [o for o in args.overlay if o not in known]
        return install(args, state)
    except Refused as error:
        say('STOP', str(error))
        return 3


if __name__ == '__main__':
    sys.exit(main())
