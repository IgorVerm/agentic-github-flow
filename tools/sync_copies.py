#!/usr/bin/env python3
"""The deliberate copies in this repository, and the tool that writes them: python3
tools/sync_copies.py [--check] (#125).

A plugin is installed as a copy of its own folder, without the rest of the repository, so code
or data two plugins need lives twice. COPIES below is the one list of those copies: for each, the
owner (the file you edit) and the copy (written from it). A copy is a whole file, or a block of
top-level definitions of a Python file: the lines from the first named definition through the
last, found by parsing both files, so a copy may differ around the block (its imports, its
comments) but not inside it.

Without options the tool writes every copy that differs from its owner and names each one; a
plugin whose file it wrote needs a new version (`tools/bump_version.py <plugin>`). With
`--check` it writes nothing and exits 1 when a copy differs, naming it. `tests/repo_checks.py`
runs the same check. `--root <dir>` works on another checkout (the tests use a temporary one).
Exit 0 when every copy equals its owner (after writing, without --check), 1 when a copy differs
under --check, 2 when the list cannot be applied (a missing file or block).
"""
import argparse
import ast
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

# (owner, copy, block): block is None for a whole file, else (first, last) top-level names.
COPIES = [
    # the secret file names: the security plugin is installed on its own
    ('templates/gitignore-secrets', 'plugins/security/scripts/gitignore-secrets', None),
    # the landing mode and the landing branch (#13), for the issue-chats scripts
    ('plugins/core/scripts/landing.py', 'plugins/issue-chats/scripts/landing.py', None),
    # what proves a chat's work is on GitHub (#50), for the issue-chats scripts
    ('plugins/core/scripts/work_proof.py', 'plugins/issue-chats/scripts/work_proof.py', None),
    # the binary classifier of the push checks (#55): the security and guards plugins
    ('plugins/security/scripts/scan_secrets.py', 'plugins/guards/scripts/pre_tool_personal_data.py',
     ('FIRST_FEW_BYTES', 'binary_blobs')),
    # the paths the Claude Code sandbox keeps a worktree from writing (#50): the merge guard
    ('plugins/core/scripts/work_proof.py', 'plugins/guards/scripts/pre_tool_merge_guard.py',
     ('protected', 'protected')),
]


class ListError(Exception):
    pass


def read(root, rel):
    path = os.path.join(root, *rel.split('/'))
    try:
        with open(path, 'rb') as f:
            return f.read()
    except OSError as e:
        raise ListError('%s: %s' % (rel, e.strerror or e))


def defined(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {t.id for t in targets if isinstance(t, ast.Name)}
    return set()


def block_span(rel, data, block):
    """(start, end) byte offsets of the lines that hold the top-level definitions from
    block[0] through block[1] in the Python file `data`."""
    text = data.decode('utf-8')
    try:
        body = ast.parse(text, rel).body
    except SyntaxError as e:
        raise ListError('%s does not parse: %s' % (rel, e))
    first = [i for i, node in enumerate(body) if block[0] in defined(node)]
    last = [i for i, node in enumerate(body) if block[1] in defined(node)]
    if len(first) != 1 or len(last) != 1 or first[0] > last[0]:
        raise ListError('%s: no single block from %s through %s' % (rel, block[0], block[1]))
    start_node, end_node = body[first[0]], body[last[0]]
    start = min([start_node.lineno] + [d.lineno for d in
                                       getattr(start_node, 'decorator_list', [])])
    lines = data.splitlines(keepends=True)
    offset = sum(len(line) for line in lines[:start - 1])
    return offset, sum(len(line) for line in lines[:end_node.end_lineno])


def wanted(root, owner, copy, block):
    """(current, wanted) bytes of the copy."""
    source, current = read(root, owner), read(root, copy)
    if block is None:
        return current, source
    a, b = block_span(owner, source, block)
    c, d = block_span(copy, current, block)
    return current, current[:c] + source[a:b] + current[d:]


def differences(root=ROOT):
    """The copies that differ from their owner, as (owner, copy, block, wanted bytes)."""
    out = []
    for owner, copy, block in COPIES:
        current, want = wanted(root, owner, copy, block)
        if current != want:
            out.append((owner, copy, block, want))
    return out


def describe(owner, copy, block):
    what = 'the whole file' if block is None else \
        (block[0] if block[0] == block[1] else '%s through %s' % block)
    return '%s differs from %s (%s)' % (copy, owner, what)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true',
                        help='write nothing; exit 1 when a copy differs')
    parser.add_argument('--root', default=ROOT)
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        found = differences(root)
    except ListError as e:
        print('sync_copies: %s' % e)
        return 2
    if args.check:
        for owner, copy, block, _ in found:
            print(describe(owner, copy, block) + '; run python3 tools/sync_copies.py')
        if not found:
            print('OK: %d copies equal their owners' % len(COPIES))
        return 1 if found else 0
    plugins = set()
    for owner, copy, block, want in found:
        with open(os.path.join(root, *copy.split('/')), 'wb') as f:
            f.write(want)
        print('wrote %s from %s' % (copy, owner))
        if copy.startswith('plugins/'):
            plugins.add(copy.split('/')[1])
    if plugins:
        print('raise the version of: ' + ', '.join(
            'python3 tools/bump_version.py %s' % p for p in sorted(plugins)))
    else:
        print('OK: %d copies equal their owners' % len(COPIES))
    return 0


if __name__ == '__main__':
    sys.exit(main())
