#!/usr/bin/env python3
"""Usage: python3 tests/claude_permissions.py   (exits non-zero on any finding)

Checks the guards plugin's policy/claude-permissions.json, the one owner of the Claude Code ask
and deny rules that the installer merges with --guards: it parses, no rule appears twice or in
both lists, there is no allow list, and every plain git rule has its `git -C *` twin. Claude rules
match command text, and `git -C <dir>` puts the folder before the subcommand, so a rule without
its twin is bypassed by the spelling agents use most. A rule that already starts with `git *` or
`git -c` needs no twin.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY = os.path.join(HERE, '..', 'plugins', 'guards', 'policy', 'claude-permissions.json')


def main():
    with open(POLICY, encoding='utf-8') as f:
        rules = json.load(f)['permissions']
    findings = []
    if set(rules) != {'ask', 'deny'}:
        findings.append('permissions must hold exactly ask and deny, found %s' % sorted(rules))
    for name in ('ask', 'deny'):
        entries = rules[name]
        findings += [f'{name}: duplicate {r}' for r in sorted(set(entries))
                     if entries.count(r) > 1]
        git = [r[5:-1] for r in entries if r.startswith('Bash(git ')]
        for rule in git:
            if re.match(r'git (-C |-c |\* )', rule):
                continue
            twin = f'git -C * {rule[4:]}'
            if twin not in git:
                findings.append(f'{name}: Bash({rule}) has no Bash({twin})')
        print(f'{name}: {len(entries)} rules, {len(git)} git rules')
    findings += [f'in both ask and deny: {r}' for r in sorted(set(rules['ask']) & set(rules['deny']))]
    for rule in ('Bash(git push --force*)', 'Bash(git reset --hard*)', 'Bash(git push*)'):
        if rule not in rules['deny'] + rules['ask']:
            findings.append(f'missing core rule {rule}')
    for finding in findings:
        print('FAIL ' + finding)
    print('OK' if not findings else f'{len(findings)} findings')
    return 1 if findings else 0


if __name__ == '__main__':
    sys.exit(main())
