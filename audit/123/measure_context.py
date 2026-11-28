#!/usr/bin/env python3
"""Context cost of this repository's content, by when it loads into an agent's context (#123).

Run from the repository root: `python3 audit/123/measure_context.py > out.md`. Python 3 stdlib only;
reads files, imports tools/installer.py for the exact rules blocks, and runs `--help` of the
scripts that parse their arguments with argparse (they exit before doing anything). Prints
Markdown tables. Tokens: tiktoken cl100k when importable (an estimate for Claude), otherwise
bytes / 4 (an estimate for English prose). Nothing is sent anywhere.
"""
from __future__ import annotations

import ast
import glob
import importlib.util
import os
import re
import subprocess
import sys

ROOT = os.getcwd()
try:
    import tiktoken  # type: ignore
    _ENC = tiktoken.get_encoding('cl100k_base')
    TOKEN_LABEL = 'tiktoken cl100k, an estimate for Claude'

    def tokens(text: str) -> int:
        return len(_ENC.encode(text))
except ImportError:
    TOKEN_LABEL = 'bytes / 4, an estimate for English prose'

    def tokens(text: str) -> int:
        return round(len(text.encode('utf-8')) / 4)

# Which plugin installs where (tools/installer.py: guards is Claude-only, codex only with Codex in
# the plan and issue-chats chosen; web-deploy needs security).
PLUGIN_NAMES = {'core': 'agentic-github-flow-core', 'security': 'agentic-github-flow-security',
                'web-deploy': 'agentic-github-flow-web-deploy',
                'issue-chats': 'agentic-github-flow-issue-chats',
                'guards': 'agentic-github-flow-guards', 'codex': 'agentic-github-flow-codex'}
ORDER = ['core', 'security', 'web-deploy', 'issue-chats', 'guards', 'codex']

# Reference files a SKILL.md tells the agent to read: (skill, file, when, cited at).
# The `when` column is a judgement from the instruction's wording at the cited line.
REFERENCES = [
    ('issue-handover', 'plugins/issue-chats/skills/issue-handover/method.md', 'always (named as the method; the start brief makes every new chat read §4 step 1)', 'issue-handover/SKILL.md:14, :153'),
    ('archive-finished-chats', 'plugins/issue-chats/skills/issue-handover/method.md', 'always (§1, §2, §4 Side chats, §6)', 'archive-finished-chats/SKILL.md:10'),
    ('ship-change', 'plugins/core/skills/ship-change/local-main.md', 'conditional: local-main mode only', 'ship-change/SKILL.md:32'),
    ('cleanup-merged', 'plugins/core/skills/ship-change/local-main.md', 'conditional: local-main mode only', 'cleanup-merged/SKILL.md:16'),
    ('review-change', 'plugins/core/skills/ship-change/local-main.md', 'conditional: local-main mode only', 'review-change/SKILL.md:88'),
    ('codex-issue-chats', 'plugins/core/skills/ship-change/local-main.md', 'conditional: local-main mode, §2', 'codex-issue-chats/SKILL.md:42, :55'),
    ('requirements', 'plugins/issue-chats/skills/issue-handover/method.md', 'conditional: where issue chats run (§1, §2)', 'requirements/SKILL.md:21'),
    ('repo-docs', 'plugins/core/skills/repo-docs/skill-standard.md', 'conditional: writing or changing a skill', 'repo-docs/SKILL.md:27'),
    ('repo-docs', 'plugins/core/skills/repo-docs/skeleton.md', 'conditional: a new repository', 'repo-docs/SKILL.md:51'),
    ('review-security', 'plugins/security/skills/review-security/checklist.md', 'always (step 5: the checks, area by area)', 'review-security/SKILL.md:15, :63'),
    ('review-security', 'plugins/security/skills/review-security/sources.md', 'conditional: §Installing osv-scanner; otherwise a citation', 'review-security/SKILL.md:16, :41'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/dashboard.md', 'always (step 8)', 'check-web-deploy/SKILL.md:60'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/privacy.md', 'always (step 6)', 'check-web-deploy/SKILL.md:56'),
    ('check-web-deploy', 'plugins/security/skills/review-security/checklist.md', 'always (step 7: §Report, §Severity)', 'check-web-deploy/SKILL.md:59'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/vercel.md', 'conditional: Vercel route', 'check-web-deploy/SKILL.md:51'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/supabase.md', 'conditional: Vercel + Supabase route', 'check-web-deploy/SKILL.md:40'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/google-auth.md', 'conditional: Google sign-in on', 'check-web-deploy/SKILL.md:46'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/cloud-run.md', 'conditional: Google Cloud route', 'check-web-deploy/SKILL.md:54'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/iap.md', 'conditional: Google Cloud route with IAP', 'check-web-deploy/SKILL.md:46'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/cloud-sql.md', 'conditional: Cloud SQL', 'check-web-deploy/SKILL.md:43'),
    ('check-web-deploy', 'plugins/web-deploy/skills/check-web-deploy/mail.md', 'conditional: the site sends mail', 'check-web-deploy/SKILL.md:49'),
    ('codex-worker', 'plugins/codex/skills/codex-worker/sources.md', 'conditional: a citation only', 'codex-worker/SKILL.md:122'),
]

# Rare branches of each SKILL.md: line ranges (inclusive) a run needs only in a rare or
# conditional case. A judgement; the script measures the bytes.
RARE = [
    ('plugins/issue-chats/skills/issue-handover/SKILL.md', [
        (9, 12, 'another client than Claude Code'),
        (63, 66, 'a probe that must not be merged'),
        (163, 180, 'the fallback (a failed start)'),
        (220, 223, 'starting chains (orchestrator only)'),
        (225, 230, 'the card fallback'),
        (232, 240, 'a hand-over before the branch is ready'),
        (31, 34, 'local-main mode (intro)'),
        (81, 87, 'local-main mode (step 2)'),
        (186, 188, 'local-main mode (step 6)'),
        (216, 218, 'local-main mode (step 7)')]),
    ('plugins/core/skills/ship-change/SKILL.md', [
        (33, 36, 'mode unknown'),
        (38, 53, 'fixing the mode in HANDOFF.md (repository setup)'),
        (93, 100, 'merge conflicts, inside and outside .claude/')]),
    ('plugins/core/skills/cleanup-merged/SKILL.md', [
        (61, 108, 'What the script checks (the script header owns it)')]),
    ('plugins/issue-chats/skills/archive-finished-chats/SKILL.md', [
        (20, 31, 'the worktree check in detail (the script owns it)'),
        (33, 39, 'step 0, a chat a card started')]),
    ('plugins/codex/skills/codex-issue-chats/SKILL.md', [
        (41, 79, 'start the integrator (local-main mode only)')]),
    ('plugins/codex/skills/codex-worker/SKILL.md', [
        (25, 31, 'the settings row (repository setup)'),
        (103, 122, 'What the route does not give (background)')]),
    ('plugins/core/skills/requirements/SKILL.md', [
        (18, 31, 'where issue chats run')]),
    ('plugins/core/skills/review-change/SKILL.md', [
        (83, 89, 'a branch without a pull request (local-main mode)')]),
    ('plugins/security/skills/review-security/SKILL.md', [
        (41, 50, 'osv-scanner second opinion and Rust reachability')]),
]

HOOK_SCRIPTS = ['plugins/issue-chats/scripts/context_limit.py',
                'plugins/issue-chats/scripts/question_label.py',
                'plugins/issue-chats/scripts/archive_guard.py',
                'plugins/guards/scripts/pre_tool_git_guard.py',
                'plugins/guards/scripts/pre_tool_merge_guard.py']

ON_DEMAND = ['HANDOFF.md', 'DESIGN_DECISIONS.md', 'README.md', 'NOTICE', 'docs/install.md',
             'docs/guide.md', 'templates/README.md', 'templates/company-overlay/AGENTS.md',
             'audit/123/README.md']


def read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding='utf-8', newline='') as f:
        return f.read()


def size(text: str) -> tuple[int, int, int, int]:
    b = len(text.encode('utf-8'))
    return b, text.count('\n'), len(text.split()), tokens(text)


def frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not m:
        return {}, text
    fields = {}
    for line in m.group(1).split('\n'):
        k, _, v = line.partition(':')
        if v and not line.startswith(' '):
            fields[k.strip()] = v.strip()
    return fields, text[m.end():]


def table(head: list[str], rows: list[list]) -> str:
    out = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    for r in rows:
        out.append('| ' + ' | '.join(f'{c:,}' if isinstance(c, int) else str(c) for c in r) + ' |')
    return '\n'.join(out)


def lines_bytes(text: str, start: int, end: int) -> int:
    ls = text.split('\n')
    return len(('\n'.join(ls[start - 1:end]) + '\n').encode('utf-8'))


def skills() -> list[dict]:
    out = []
    for plugin in ORDER:
        for path in sorted(glob.glob(f'plugins/{plugin}/skills/*/SKILL.md')):
            text = read(path)
            fm, body = frontmatter(text)
            name, desc = fm.get('name', ''), fm.get('description', '')
            listing = f'- {PLUGIN_NAMES[plugin]}:{name}: {desc}\n'
            out.append({'plugin': plugin, 'path': path, 'name': name, 'desc': desc,
                        'compat': fm.get('compatibility', ''), 'listing': listing,
                        'text': text, 'body': body})
    return out


def installer_blocks() -> tuple[str, str]:
    spec = importlib.util.spec_from_file_location('installer', os.path.join(ROOT, 'tools', 'installer.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.CLONE = ROOT
    codex = mod.codex_block([])
    mod.CLONE = os.path.join(os.path.expanduser('~'), '.agentic-github-flow')  # the default clone
    claude = mod.claude_block([])
    return claude, codex


def sections(text: str, level: str) -> list[tuple[str, int]]:
    """(heading, bytes up to the next heading of that level or higher) for `##` or `###`."""
    ls = text.split('\n')
    marks = [i for i, l in enumerate(ls) if re.match(r'#{1,%d} ' % len(level), l)]
    out = []
    for n, i in enumerate(marks):
        if not ls[i].startswith(level + ' '):
            continue
        j = next((m for m in marks[n + 1:]), len(ls))
        out.append((ls[i], len(('\n'.join(ls[i:j]) + '\n').encode('utf-8'))))
    return out


def message_literals(path: str) -> int:
    """Literal bytes of the longest message a hook script prints or returns as context."""
    tree = ast.parse(read(path))
    best = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, 'id', '') in ('print', 'note', 'deny', 'refuse', 'block', 'ask'):
            for arg in node.args:
                parts = arg.values if isinstance(arg, ast.JoinedStr) else [arg]
                n = sum(len(p.value.encode('utf-8')) for p in parts
                        if isinstance(p, ast.Constant) and isinstance(p.value, str))
                best = max(best, n)
    return best


def script_help(path: str) -> tuple[int, str]:
    src = read(path)
    doc = ast.get_docstring(ast.parse(src), clean=False) or ''
    if 'argparse' in src:
        try:
            p = subprocess.run([sys.executable, '-I', path, '--help'], cwd=ROOT, capture_output=True,
                               text=True, timeout=20, stdin=subprocess.DEVNULL)
            return len(p.stdout.encode('utf-8')), 'argparse `--help`, run'
        except (OSError, subprocess.TimeoutExpired):
            return -1, 'argparse `--help` failed'
    if re.search(r"""['"]--help['"]""", src) and 'print(__doc__)' in src:
        return len((doc + '\n').encode('utf-8')), 'module docstring (`--help` prints it)'
    if '__doc__' in src:
        return len((doc + '\n').encode('utf-8')), 'module docstring (printed on a usage error)'
    return len((doc + '\n').encode('utf-8')), 'module docstring (no `--help`)'


def main() -> int:
    head = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()
    print(f'# Context cost by load class (measured at {head}; tokens: {TOKEN_LABEL})\n')
    sk = skills()

    # ---- 1. always ----------------------------------------------------------------------------
    claude, codex = installer_blocks()
    core = read('rules/core.md')
    imports = [l for l in claude.split('\n') if l.startswith('@')]
    claude_visible = '\n'.join(imports) + '\n'
    print('## 1. Always: rules blocks\n')
    rows = [
        ['Claude: block lines in ~/.claude/CLAUDE.md (markers are HTML comments, not shown to the model)',
         *size(claude)],
        ['Claude: the `@` import line(s) the model sees', *size(claude_visible)],
        ['Claude: rules/core.md, expanded from the import', *size(core)],
        ['Codex: the whole inlined block in ~/.codex/AGENTS.md (core.md + codex.md + markers)', *size(codex)],
        ['  of which rules/codex.md', *size(read('rules/codex.md'))],
    ]
    print(table(['item', 'bytes', 'lines', 'words', 'tokens'], rows))
    print(f'\nrules/core.md budget (AGENTS.md: under 8,000 bytes): {len(core.encode())} bytes. '
          f'Codex block share of the 32 KiB AGENTS.md read limit: '
          f'{len(codex.encode()) * 100 / (32 * 1024):.1f} %.\n')

    print('## 1. Always: skill listing (name + description per installed skill)\n')
    print('Claude line form `- <plugin>:<name>: <description>` as this session\'s own listing shows '
          'it; `compatibility` is not in the listing.\n')
    rows = []
    for s in sk:
        flag = []
        if len(s['desc']) > 500:
            flag.append('over 500 (repo limit)')
        if len(s['desc']) > 1024:
            flag.append('over 1024 (standard)')
        rows.append([s['plugin'], s['name'], len(s['desc']), len(s['listing'].encode()),
                     len(s['compat']), tokens(s['listing']), ', '.join(flag) or 'ok'])
    print(table(['plugin', 'skill', 'description chars', 'Claude listing bytes', 'compatibility chars (not listed)',
                 'tokens', 'limit'], rows))
    print()
    rows = []
    for p in ORDER:
        mine = [s for s in sk if s['plugin'] == p]
        b = sum(len(s['listing'].encode()) for s in mine)
        rows.append([p, len(mine), b, sum(tokens(s['listing']) for s in mine)])
    tot = sum(len(s['listing'].encode()) for s in sk)
    rows.append(['all', len(sk), tot, sum(tokens(s['listing']) for s in sk)])
    print(table(['plugin', 'skills', 'listing bytes', 'tokens'], rows))
    print()

    # hooks
    print('## 1. Always: hooks\n')
    rows = []
    for hj in sorted(glob.glob('plugins/*/hooks/hooks.json')):
        import json
        data = json.loads(read(hj))
        for event, entries in data['hooks'].items():
            for e in entries:
                for h in e['hooks']:
                    script = re.findall(r'scripts/([\w.-]+\.(?:py|sh))', h['command'])
                    rows.append([hj.split('/')[1], event, e.get('matcher', '(every prompt)').replace('|', '\\|'),
                                 ' → '.join(script)])
    print(table(['plugin', 'event', 'matcher', 'script'], rows))
    print('\nNo SessionStart hook. Text reaches the context only when a hook denies, asks or adds a '
          'note; longest message literal per script (placeholders not counted):\n')
    print(table(['script', 'longest literal message bytes'],
                [[p, message_literals(p)] for p in HOOK_SCRIPTS]))
    print()

    print('## 1. Always for maintainers of this repository only\n')
    print(table(['file', 'bytes', 'lines', 'words', 'tokens'],
                [[p, *size(read(p))] for p in ('AGENTS.md', 'CLAUDE.md')]))
    print()

    # per plugin always totals
    print('## 1. Always: totals per plugin and client\n')
    rows = []
    core_b = len(core.encode()) + len(claude_visible.encode())
    codex_b = len(codex.encode())
    for p in ORDER:
        lb = sum(len(s['listing'].encode()) for s in sk if s['plugin'] == p)
        rows.append([p, lb, round(lb / 4)])
    print(table(['plugin', 'skill listing bytes', 'tokens (bytes/4)'], rows))
    print(f'\nClaude, all plugins: rules {core_b:,} + listing {tot:,} = {core_b + tot:,} bytes '
          f'(~{round((core_b + tot) / 4):,} tokens). Codex, all plugins but guards: rules {codex_b:,} '
          f'+ name/description {sum(len(s["name"]) + len(s["desc"]) for s in sk):,} bytes '
          f'(plus a path per skill, not measured).\n')

    # ---- 2. per skill run ---------------------------------------------------------------------
    print('## 2. Per skill run: SKILL.md\n')
    rows = []
    for s in sorted(sk, key=lambda s: -len(s['text'].encode())):
        b, l, w, t = size(s['text'])
        bb, bl, bw, bt = size(s['body'])
        flag = []
        if l >= 500:
            flag.append('500 lines')
        if bt > 5000:
            flag.append('5000 tokens')
        rows.append([s['plugin'], s['name'], b, l, w, t, bb, bt, ', '.join(flag) or 'ok'])
    print(table(['plugin', 'skill', 'file bytes', 'lines', 'words', 'tokens', 'body bytes', 'body tokens', 'over limit'], rows))
    print()

    print('## 2. Per skill run: reference files the SKILL.md sends the agent to\n')
    rows = []
    for skill, path, when, cite in REFERENCES:
        b, l, w, t = size(read(path))
        rows.append([skill, path.split('skills/')[1], when, cite, b, l, t])
    print(table(['skill', 'file', 'when', 'instruction at', 'bytes', 'lines', 'tokens'], rows))
    print()
    print('### Typical run cost (SKILL.md + always-read references)\n')
    always = {}
    for skill, path, when, _ in REFERENCES:
        if when.startswith('always'):
            always.setdefault(skill, set()).add(path)
    rows = []
    for s in sk:
        refs = always.get(s['name'], set())
        rb = sum(len(read(p).encode()) for p in refs)
        b = len(s['text'].encode())
        rows.append([s['name'], b, rb, b + rb, round((b + rb) / 4)])
    rows.sort(key=lambda r: -r[3])
    print(table(['skill', 'SKILL.md bytes', 'always-read refs bytes', 'total bytes', 'tokens (bytes/4)'], rows))
    print()

    print('### Rare branches inside SKILL.md bodies (judgement; bytes measured)\n')
    rows = []
    for path, ranges in RARE:
        text = read(path)
        total = len(text.encode())
        moved = 0
        for a, z, label in ranges:
            b = lines_bytes(text, a, z)
            moved += b
            rows.append([path.split('skills/')[1], f'{a}-{z}', label, b])
        rows.append([path.split('skills/')[1], 'sum', f'{moved * 100 / total:.0f} % of {total:,} bytes', moved])
    print(table(['file', 'lines', 'branch', 'bytes'], rows))
    print()

    print('### method.md by section\n')
    mtext = read('plugins/issue-chats/skills/issue-handover/method.md')
    rows = [[h.replace('|', '\\|'), b] for h, b in sections(mtext, '##')]
    rows += [['  ' + h, b] for h, b in sections(mtext, '###')]
    print(table(['section', 'bytes (### included in their ##)'], rows))
    ls = mtext.split('\n')
    a = next(i for i, l in enumerate(ls) if l.startswith('1. **Start:**'))
    z = next(i for i, l in enumerate(ls) if l.startswith('2. **Work:**'))
    step1 = len(('\n'.join(ls[a:z]) + '\n').encode())
    print(f'\nmethod.md §4 step 1 (the chat start): lines {a + 1}-{z}, {step1:,} bytes.\n')

    # ---- 3. issue-chat start ------------------------------------------------------------------
    print('## 3. Per issue-chat start (Claude Code)\n')
    ih = read('plugins/issue-chats/skills/issue-handover/SKILL.md')
    af = read('plugins/issue-chats/skills/archive-finished-chats/SKILL.md')
    ready = 'Reply with exactly one line: ready. Use no tools.'
    rows = [
        ['0', 'always: rules/core.md + import line (overlays not counted)', 'every session', core_b],
        ['0', 'always: skill listing, all six plugins', 'every session', tot],
        ['1', 'ready prompt of start_issue_chat.py', 'start_issue_chat.py:87', len(ready)],
        ['2', 'the start brief (written by the previous chat; not in the repository)', 'issue-handover/SKILL.md:146-161', 'variable'],
        ['3', 'issue-handover SKILL.md (the brief names the skill)', 'issue-handover/SKILL.md:153', len(ih.encode())],
        ['4a', 'method.md, read whole', 'issue-handover/SKILL.md:14, :153', len(mtext.encode())],
        ['4b', '  or only §4 step 1', 'method.md §4', step1],
        ['5', 'the issue with its comments, settings start reading', 'method.md §4 step 1.1', 'variable'],
        ['6', 'archive-finished-chats SKILL.md (housekeeping)', 'method.md §4 step 1.4', len(af.encode())],
        ['7', 'its tool output: list_sessions (limit 50), chat_archivable.py per chat', 'archive-finished-chats/SKILL.md:40, :54', 'variable'],
    ]
    print(table(['order', 'what', 'instruction at', 'bytes'], rows))
    fixed_whole = len(ih.encode()) + len(mtext.encode()) + len(af.encode())
    fixed_step = len(ih.encode()) + step1 + len(af.encode())
    print(f'\nRepository files read at a chat start, beyond the always-loaded part: {fixed_whole:,} bytes '
          f'(~{round(fixed_whole / 4):,} tokens) with method.md whole; {fixed_step:,} bytes '
          f'(~{round(fixed_step / 4):,} tokens) with §4 step 1 only. With the always-loaded part: '
          f'{fixed_whole + core_b + tot:,} bytes (~{round((fixed_whole + core_b + tot) / 4):,} tokens).\n')

    # ---- Codex text in what Claude loads (#98) -------------------------------------------------
    print('## Codex text in what a Claude-only install loads (#98 check)\n')
    files = ['rules/core.md'] + [s['path'] for s in sk if s['plugin'] != 'codex'] + sorted(
        set(p for _, p, _, _ in REFERENCES if '/codex/' not in p))
    rows = []
    for p in files:
        hits = [l for l in read(p).split('\n') if re.search(r'codex', l, re.I)]
        if hits:
            rows.append([p, len(hits), sum(len(l.encode()) + 1 for l in hits)])
    print(table(['file', 'lines naming Codex', 'bytes of those lines'], rows) if rows else 'None.')
    print()

    # ---- 4. on demand ------------------------------------------------------------------------
    print('## 4. On demand: documents\n')
    print(table(['file', 'bytes', 'lines', 'words', 'tokens'], [[p, *size(read(p))] for p in ON_DEMAND]))
    print()
    print('## 4. On demand: script help (what `--help` or a usage error prints)\n')
    rows = []
    for p in sorted(glob.glob('plugins/*/scripts/*.py')):
        b, how = script_help(p)
        rows.append([p, len(read(p).encode()), b, how])
    rows.sort(key=lambda r: -r[2])
    print(table(['script', 'file bytes', 'help bytes', 'source'], rows))
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
