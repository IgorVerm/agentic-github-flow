#!/usr/bin/env python3
"""Raise a plugin's version in the three places that hold it: python3 tools/bump_version.py
<plugin> [patch|minor|major] (#125).

A plugin's version lives in `plugins/<plugin>/.claude-plugin/plugin.json`,
`plugins/<plugin>/.codex-plugin/plugin.json` and its entry in `.claude-plugin/marketplace.json`
(`.agents/plugins/marketplace.json` holds none). `tests/repo_checks.py` checks that the three
agree and that a plugin changed since the default branch has a new version; this script makes
that one command. `<plugin>` is the folder name (`core`) or the full name
(`agentic-github-flow-core`); the part defaults to `patch`.

It refuses, changing nothing, when the three places disagree before the bump, or when a version
is not three numbers. Each file is edited in place on the one `"version"` value that changes, so
the rest of its formatting stays; the result is parsed again and must differ from the original
in that value only.

Prints one line: `<name> <old> -> <new>`. Exit 0 on success, 1 on a refusal, 2 on bad usage.
`--root <dir>` works on another checkout (the tests use a temporary one).
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
PARTS = ('major', 'minor', 'patch')
VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)')
VALUE = re.compile(r'("version"\s*:\s*)"([^"\\]*)"')


class Refusal(Exception):
    pass


def raised(version, part):
    m = VERSION.fullmatch(version or '')
    if not m:
        raise Refusal('version %r is not three numbers (major.minor.patch)' % version)
    numbers = [int(n) for n in m.groups()]
    i = PARTS.index(part)
    numbers[i] += 1
    numbers[i + 1:] = [0] * (2 - i)
    return '%d.%d.%d' % tuple(numbers)


def rewrite(text, expected, new):
    """`text` with exactly one `"version"` value replaced by `new`, so that it parses to
    `expected`."""
    found = []
    for m in VALUE.finditer(text):
        candidate = text[:m.start(2)] + new + text[m.end(2):]
        try:
            if json.loads(candidate) == expected:
                found.append(candidate)
        except ValueError:
            pass
    if len(found) != 1:
        raise Refusal('could not change exactly one "version" value (%d candidates)' % len(found))
    return found[0]


def bump(root, plugin, part):
    plugin = plugin[len('agentic-github-flow-'):] if plugin.startswith('agentic-github-flow-') \
        else plugin
    folder = os.path.join(root, 'plugins', plugin)
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', plugin) or not os.path.isdir(folder):
        raise Refusal('no plugin folder plugins/%s' % plugin)
    files = {kind: os.path.join(folder, kind, 'plugin.json')
             for kind in ('.claude-plugin', '.codex-plugin')}
    market = os.path.join(root, '.claude-plugin', 'marketplace.json')
    texts, datas = {}, {}
    for path in list(files.values()) + [market]:
        try:
            with open(path, encoding='utf-8', newline='') as f:
                texts[path] = f.read()
            datas[path] = json.loads(texts[path])
        except (OSError, ValueError) as e:
            raise Refusal('cannot read %s: %s' % (os.path.relpath(path, root), e))
    name = datas[files['.claude-plugin']].get('name')
    entries = [e for e in datas[market].get('plugins', []) if e.get('name') == name]
    if len(entries) != 1:
        raise Refusal('%s has %d entries in .claude-plugin/marketplace.json, not one'
                      % (name, len(entries)))
    places = {os.path.relpath(files['.claude-plugin'], root): datas[files['.claude-plugin']],
              os.path.relpath(files['.codex-plugin'], root): datas[files['.codex-plugin']],
              '.claude-plugin/marketplace.json (%s)' % name: entries[0]}
    old = {place.replace(os.sep, '/'): data.get('version') for place, data in places.items()}
    if len(set(old.values())) != 1:
        raise Refusal('the three places disagree before the bump; make them agree first: '
                      + ', '.join('%s %s' % (p, v) for p, v in old.items()))
    before = next(iter(old.values()))
    after = raised(before, part)
    new_texts = {}
    for path, data in datas.items():
        expected = json.loads(json.dumps(data))
        target = next(e for e in expected['plugins'] if e.get('name') == name) \
            if path == market else expected
        target['version'] = after
        new_texts[path] = rewrite(texts[path], expected, after)
    for path, text in new_texts.items():  # written only once every file has its new text
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)
    return name, before, after


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('plugin')
    parser.add_argument('part', nargs='?', default='patch', choices=PARTS)
    parser.add_argument('--root', default=ROOT)
    args = parser.parse_args(argv)
    try:
        name, before, after = bump(os.path.abspath(args.root), args.plugin, args.part)
    except Refusal as e:
        print('bump_version: refused: %s' % e)
        return 1
    print('%s %s -> %s' % (name, before, after))
    return 0


if __name__ == '__main__':
    sys.exit(main())
