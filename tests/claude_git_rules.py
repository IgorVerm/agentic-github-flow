#!/usr/bin/env python3
"""Checks Claude Code's git protection as a whole: python3 tests/claude_git_rules.py.

The decision for a Bash call is what Claude Code makes of the guards plugin's
policy/claude-permissions.json together with the git guard hook in its `--claude` mode: "deny"
when a deny rule matches or the guard blocks, "ask" when an ask rule matches or the guard asks,
else "allow". Rules are matched with the client's wildcard rule (`pattern_regex` in
pre_tool_sandbox_network.py, measured on Claude Code 2.1.317), on the whole call and on each
simple command.

Both directions (#33; the user, 2026-11-09: "betere regel dat een correcte commit niet gestopt
wordt", a better rule so that a correct commit is not stopped):
- STOPPED: an example of every git deny and ask rule as it stood before #33
  (claude_git_rules_former.json, the dropped rules included) keeps its decision, in the plain and
  the `git -C <dir>` spelling. The git guard's own BLOCK list stays blocked.
- PASSES: a commit whose message holds the words of any of those rules is allowed, through `-m`,
  several `-m`, `--allow-empty`, `-q`, `-uno`, a here-document body and `-F`, also with
  `git -C` and `git -c`. So do read commands that name a rule word
  (`git -C <dir> log --grep clean`).
tests/claude_permissions.py checks that no rule left in the policy can reach into a commit.
"""
import ast
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, '..', 'plugins', 'guards', 'scripts')
POLICY = os.path.join(HERE, '..', 'plugins', 'guards', 'policy', 'claude-permissions.json')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard_block_list():
    """tests/git_guard.py's BLOCK list, without running that test: only its top-level
    assignments to BLOCK are executed."""
    path = os.path.join(HERE, 'git_guard.py')
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), path)
    names = {}
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else \
            [node.target] if isinstance(node, ast.AugAssign) else []
        if any(isinstance(t, ast.Name) and t.id == 'BLOCK' for t in targets):
            exec(compile(ast.Module([node], []), path, 'exec'), names)
    return names['BLOCK']


guard = load('git_guard_under_test', os.path.join(SCRIPTS, 'pre_tool_git_guard.py'))
matcher = load('sandbox_network_matcher', os.path.join(SCRIPTS, 'pre_tool_sandbox_network.py'))
GUARD_BLOCK = guard_block_list()

# The git rules of the policy before #33, kept as the forms that must stay stopped.
with open(os.path.join(HERE, 'claude_git_rules_former.json'), encoding='utf-8') as f:
    FORMER = json.load(f)


def rule_matches(rule, command):
    content = rule[5:-1]
    try:
        parts = [command] + [' '.join(t) for t in guard.split_commands(command)]
    except ValueError:  # the client matches the text as written
        parts = [command]
    return any(matcher.pattern_regex(content, False).fullmatch(re.sub(r'[ \t]+', ' ', p.strip()))
               for p in parts)


def decide(command, rules):
    if any(rule_matches(r, command) for r in rules['deny']) or guard.check(command):
        return 'deny'
    if any(rule_matches(r, command) for r in rules['ask']) or guard.check_ask(command):
        return 'ask'
    return 'allow'


SPECIAL = {  # rules whose generated example would not be the act they stop
    'git -c core.hooksPath*': 'git -c core.hooksPath=/dev/null commit -m x',
    'git -c * core.hooksPath*': 'git -c user.name=x -c core.hooksPath=/dev/null commit -m x',
    'git * --no-verify*': 'git merge main --no-verify',
}


def example(rule, folder):
    """A command the rule was written to stop: `*` before a space or at the end -> a word, and a
    config rule's example is a write (a read changes nothing)."""
    text = rule[5:-1]
    if text in SPECIAL:
        return SPECIAL[text].replace('git ', 'git -C /repo ', 1) if folder else SPECIAL[text]
    text = re.sub(r'^git -C \* ', 'git -C /repo ', text)
    if not folder and text.startswith('git -C /repo '):
        return ''
    text = re.sub(r'\* ', 'x ', text)
    text = re.sub(r' \*$', ' x', text)
    text = re.sub(r'\*$', '', text)
    text = text.replace('*', 'x')
    if re.search(r'\bconfig (core|user|credential)\.?x?$', text):
        text += 'x y'  # a write, not a read
    elif re.search(r'\bconfig --(global|system) x$', text):
        text += ' y'
    return text


def message_words(rule):
    text = re.sub(r'^(git -C \* |git \* |git )', '', rule[5:-1])
    return re.sub(r'\s+', ' ', text.replace('*', ' ')).strip()


def main():
    with open(POLICY, encoding='utf-8') as f:
        rules = json.load(f)['permissions']
    failures, stopped = [], 0
    for name in ('deny', 'ask'):
        for rule in FORMER[name]:
            for folder in (False, True):
                command = example(rule, folder)
                if not command:
                    continue
                if folder and not command.startswith('git -C'):
                    command = command.replace('git ', 'git -C /repo ', 1)
                got = decide(command, rules)
                stopped += 1
                if got == 'allow' or (name == 'deny' and got != 'deny'):
                    failures.append(f'STOPPED {command!r} (from {rule}): {got}, wanted {name}')
    for command in ("git -C /repo push origin main # it's ready", 'git -C /repo commit -m "open'):
        stopped += 1  # a comment or unreadable text is asked, not passed
        if decide(command, rules) != 'ask':
            failures.append(f'STOPPED (ask) {command!r}: {decide(command, rules)}')
    for command in GUARD_BLOCK:
        stopped += 1
        if decide(command, rules) != 'deny':
            failures.append(f'STOPPED guard BLOCK {command!r}: {decide(command, rules)}')
    words = sorted({message_words(r) for n in ('deny', 'ask') for r in FORMER[n]} | {
        'clean', 'push', 'push --force', 'rebase', 'restore', 'prune', 'replace', 'reset --hard',
        '-n', '--amend', '+main', '--no-verify', 'checkout -- .', 'add -A', 'branch -D',
        'stash drop', 'tag -d', 'filter-branch', 'update-ref -d', 'remote add', 'commit -a',
        '--all'})
    passes = 0
    for w in words:
        msg = f'note: {w} (#33)'
        for command in (
                f'git commit -m "{msg}" -- a.md',
                f'git -C /repo commit -q -m "{msg}" -- a.md',
                f'git -C /repo commit -q --allow-empty -m "{msg}"',
                f'git commit --allow-empty -m "first" -m "{msg}"',
                f"git -C /repo commit -m \"$(cat <<'EOF'\n{msg}\n\nCo-Authored-By: x\nEOF\n)\" -- a.md",
                'git -C /repo commit -F /tmp/msg.txt -- a.md',
                f'git -C /repo commit -uno -m "{msg}" -- a.md',
                f'git -c commit.gpgsign=false commit -m "{msg}" -- a.md',
                f"git -C /repo commit -m \"$(cat <<'EOF'\nit's {msg}\nEOF\n)\" -- a.md # it's",
                f'git -C /repo log --oneline --grep "{w}"'):
            passes += 1
            got = decide(command, rules)
            if got != 'allow':
                failures.append(f'PASSES {command!r}: {got}')
    for line in failures:
        print('FAIL', line)
    print(f'claude_git_rules: {stopped} stopped forms, {passes} correct commands, '
          f'{len(failures)} failures')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
