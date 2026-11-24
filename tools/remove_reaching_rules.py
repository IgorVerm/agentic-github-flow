#!/usr/bin/env python3
"""Removes the Claude Code git rules whose `*` reaches into a commit message (#33).

Usage: python3 tools/remove_reaching_rules.py [--settings <file>] [--apply]
                                              [--without-guard-check]

A rule such as `Bash(git -C * clean*)` stops `git -C r commit -m "a clean step"`: its `*` spans
the rest of the command. The installer removes the ones it added itself and only names the
user's own (tools/installer.py, REACHES_COMMIT, the one owner of which rules these are). This
tool removes those too, from the ask and deny lists of ~/.claude/settings.json (or
$CLAUDE_CONFIG_DIR/settings.json, or --settings <file>).

Without --apply it changes nothing: it prints the rules it would remove. With --apply it first
copies the file to <file>.agentic-github-flow-backup-<time>, then writes it without those
rules; nothing else in the file changes but its layout (two-space JSON, as the installer
writes it). An allow rule is never touched.

Once the rules are gone, `git -C <dir> …` rests on the guards plugin's git guard alone. So
--apply refuses unless the settings folder shows an enabled guards plugin whose hooks run
`pre_tool_git_guard.py --claude` (guards 0.10.1 and later): update first, then run this.
--without-guard-check skips that check, for a settings file that is not beside the plugins.
Exit code: 0 done or nothing to do, 1 refused.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('installer', os.path.join(HERE, 'installer.py'))
installer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(installer)
GUARDS = 'agentic-github-flow-guards@'  # the plugin's name, before the marketplace's


def reaching(data):
    """{'ask': [...], 'deny': [...]}: the rules of each list that reach into a commit."""
    permissions = data.get('permissions')
    found = {}
    for kind in ('ask', 'deny'):
        rules = permissions.get(kind) if isinstance(permissions, dict) else None
        found[kind] = [r for r in rules if isinstance(r, str)
                       and installer.REACHES_COMMIT.match(r)] if isinstance(rules, list) else []
    return found


def guard_wired(settings_path, data):
    """None when an enabled guards plugin beside the settings runs the git guard with --claude,
    else the reason it does not look that way."""
    enabled = data.get('enabledPlugins')
    names = [k for k, v in enabled.items() if k.startswith(GUARDS) and v is True] \
        if isinstance(enabled, dict) else []
    if not names:
        return 'no enabled guards plugin (%s…) in enabledPlugins' % GUARDS
    record = os.path.join(os.path.dirname(settings_path), 'plugins', 'installed_plugins.json')
    try:
        with open(record, encoding='utf-8') as f:
            plugins = json.load(f).get('plugins', {})
    except (OSError, ValueError, AttributeError) as error:
        return 'cannot read %s (%s)' % (record, error)
    for name in names:
        installs = plugins.get(name) if isinstance(plugins, dict) else None
        for install in installs if isinstance(installs, list) else []:
            root = install.get('installPath') if isinstance(install, dict) else None
            if not isinstance(root, str):
                continue
            try:
                with open(os.path.join(root, 'hooks', 'hooks.json'), encoding='utf-8') as f:
                    hooks = json.load(f)
            except (OSError, ValueError):
                continue
            entries = hooks.get('hooks', {}).get('PreToolUse', []) \
                if isinstance(hooks, dict) and isinstance(hooks.get('hooks'), dict) else []
            for entry in entries if isinstance(entries, list) else []:
                for hook in entry.get('hooks', []) if isinstance(entry, dict) else []:
                    command = hook.get('command', '') if isinstance(hook, dict) else ''
                    if 'pre_tool_git_guard.py' in command and '--claude' in command.split():
                        return None
            return 'the installed guards plugin (%s, %s) does not run the git guard with ' \
                   '--claude; update it first' % (install.get('version', '?'), root)
    return 'no installed guards plugin in %s' % record


def main(argv):
    apply = '--apply' in argv
    check = '--without-guard-check' not in argv
    path = os.path.join(installer.claude_dir(), 'settings.json')
    rest = [a for a in argv if a not in ('--apply', '--without-guard-check')]
    if rest[:1] == ['--settings'] and len(rest) == 2:
        path = os.path.abspath(rest[1])
    elif rest:
        print(__doc__.split('\n\n')[1])
        return 1
    try:
        data = installer.load_json(path)
    except installer.Refused as error:
        installer.say('stop', str(error))
        return 1
    if data is None:
        installer.say('ok', '%s does not exist or is empty: nothing to do' % path)
        return 0
    found = reaching(data)
    count = len(found['ask']) + len(found['deny'])
    if not count:
        installer.say('ok', 'no ask or deny rule in %s reaches into a commit message' % path)
        return 0
    wired = guard_wired(path, data) if check else None
    installer.say('note', '%d rules in %s reach into a commit message%s:' % (
        count, path, '' if apply else ' (dry run: nothing is changed)'))
    for kind in ('ask', 'deny'):
        for rule in found[kind]:
            print('      %-4s %s' % (kind, rule))
    if not apply:
        if wired:
            installer.say('note', '--apply would refuse now: %s' % wired)
        installer.say('ok', 'to remove them: the same command with --apply (a backup is kept)')
        return 0
    if wired:
        installer.say('stop', 'nothing changed: %s. Without that hook nothing would judge '
                              '`git -C <dir> …` once these rules are gone.' % wired)
        return 1
    installer.backup(path)
    for kind in ('ask', 'deny'):
        gone = set(found[kind])
        data['permissions'][kind] = [r for r in data['permissions'][kind]
                                     if not (isinstance(r, str) and r in gone)]
    installer.dump_json(path, data)
    installer.say('ok', '%d rules removed from %s; the backup is beside it '
                        '(%s.agentic-github-flow-backup-<time>)' % (count, path,
                                                                     os.path.basename(path)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
