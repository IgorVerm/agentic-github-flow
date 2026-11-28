#!/usr/bin/env python3
"""Refusals, repeats and their token cost, from Claude Code transcripts (audit #123, part 2).

Same input, window and privacy rule as `transcript_stats.py` (whose helpers it imports): it
streams `<projects>/*/` main-session and subagent transcripts and prints ONLY aggregates: counts,
token sums, tool names, this repository's skill and script names, guard reason phrases and
command shapes. Never message text, file contents, paths or other projects' names.

Usage:
  python3 audit/123/refusal_stats.py [PROJECTS_DIR] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                                     [--repo REPO_ROOT] [--json]

Definitions (one per measurement of refusals.md):
- network call: a Bash call with a `gh` command or `git push|fetch|pull|ls-remote` as one of its
  simple commands. Form: `-C` (any git network command with -C/--git-dir/--work-tree), `lone`
  (the whole call is that one simple command: no `&&`, `;`, `|`, `$(`, here-document), else
  `chained`. Outcome: `escaped` (dangerouslyDisableSandbox), `blocked:<guard>`, `sandbox-fail`,
  `error`, `ok`.
- a transcript (main session or one subagent) is one unit "session".
- context of a call: input + cache_read + cache_creation tokens of the API response that issued it.
"""
import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('transcript_stats', os.path.join(HERE, 'transcript_stats.py'))
ts_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ts_mod)

GUARDS = ts_mod.GUARDS
SANDBOX_RE = ts_mod.SANDBOX_RE
SPLIT_RE = ts_mod.SPLIT_RE
tokens = ts_mod.tokens
iso_week = ts_mod.iso_week
result_text = ts_mod.result_text
guard_reason = ts_mod.guard_reason

NET_GIT = {'push', 'fetch', 'pull', 'ls-remote'}
PREFIX_WORDS = ('env', 'command', 'time', 'exec', 'do', 'then', 'else', '!', 'if', 'while', 'until', 'sudo')
ASSIGN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*=')
GIT_C_NET_RE = ts_mod.GIT_C_NET_RE
PATTERNS = {
    'git -C <path> <network>': GIT_C_NET_RE,
    'cd <path> && gh': re.compile(r'\bcd\s+[^\n;&|]+&&\s*gh\s'),
    'cd <path> && git <network>': re.compile(r'\bcd\s+[^\n;&|]+&&\s*git\s+(?:push|fetch|pull|ls-remote)\b'),
    'gh ... | <filter>': re.compile(r'\bgh\s[^\n|;&]*\|(?!\|)'),
    'gh ... && gh': re.compile(r'\bgh\s[^\n|;&]*&&\s*gh\s'),
}
FILTERS = {'head': 'head/tail', 'tail': 'head/tail', 'grep': 'grep', 'rg': 'grep', 'jq': 'jq',
           'python3': 'python', 'python': 'python', 'sed': 'sed/awk', 'awk': 'sed/awk',
           'wc': 'wc/sort/cut/uniq', 'sort': 'wc/sort/cut/uniq', 'cut': 'wc/sort/cut/uniq',
           'uniq': 'wc/sort/cut/uniq', 'cat': 'cat/tee', 'tee': 'cat/tee', 'base64': 'other',
           'xargs': 'xargs'}
DISPLAY_FILTERS = {'head/tail', 'grep', 'wc/sort/cut/uniq', 'cat/tee'}
HEREDOC_RE = re.compile(r'<<-?\s*([\'"]?)([A-Za-z_][A-Za-z0-9_]*)\1')
NET_WORDS = {'ssh', 'scp', 'rsync', 'curl', 'wget'}


def split_simple(cmd):
    """Quote-aware split into (simple command text, separator after it). Respects '...', "...",
    backslashes, $(...) and backticks; skips here-document bodies and comments."""
    out, cur, i, n = [], [], 0, len(cmd)
    quote, depth, pending, word_start = None, 0, [], True
    def emit(sep):
        seg = ''.join(cur).strip()
        if seg:
            out.append((seg, sep))
        cur.clear()
    while i < n:
        c = cmd[i]
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            elif c == '\\' and quote == '"' and i + 1 < n:
                cur.append(cmd[i + 1])
                i += 1
            i += 1
            continue
        if c == '\\' and i + 1 < n:
            cur.append(c + cmd[i + 1])
            i += 2
            continue
        if c in '"\'`' and not (c == '`' and depth):
            quote = c
            cur.append(c)
            i += 1
            continue
        if cmd.startswith('$(', i):
            depth += 1
            cur.append('$(')
            i += 2
            continue
        if c == ')' and depth:
            depth -= 1
            cur.append(c)
            i += 1
            continue
        if depth:
            cur.append(c)
            i += 1
            continue
        if c == '#' and (not cur or cur[-1] in ' \t'):
            j = cmd.find('\n', i)
            i = n if j < 0 else j
            continue
        if cmd.startswith('<<', i) and not cmd.startswith('<<<', i):
            m = HEREDOC_RE.match(cmd, i)
            if m:
                pending.append((m.group(2), cmd.startswith('<<-', i)))
        if c == '\n':
            emit(';')
            i += 1
            while pending:
                d, strip = pending.pop(0)
                while i < n:
                    j = cmd.find('\n', i)
                    line = cmd[i:] if j < 0 else cmd[i:j]
                    i = n if j < 0 else j + 1
                    if (line.lstrip('\t') if strip else line).strip() == d:
                        break
            continue
        for sep in ('&&', '||', ';', '|', '&'):
            if cmd.startswith(sep, i) and not (sep == '&' and (cmd.startswith('&>', i) or (cur and cur[-1] in '<>'))) \
                    and not (sep == '|' and cur and cur[-1] == '>'):
                emit(sep)
                i += len(sep)
                break
        else:
            cur.append(c)
            i += 1
    emit('')
    return out


def simple_commands(cmd):
    """Simple commands with their tokens (prefix words and assignments dropped)."""
    out = []
    for seg, sep in split_simple(cmd):
        seg = seg.lstrip('({ ').rstrip(')} ')
        if not seg:
            continue
        t = tokens(seg)
        env = False
        while t and (ASSIGN.match(t[0]) or t[0] in PREFIX_WORDS) and len(t) > 1:
            env = env or bool(ASSIGN.match(t[0]))
            t = t[1:]
        if t and not ASSIGN.match(t[0]):
            out.append({'t': t, 'env': env, 'sep': sep})
    return out


def git_sub(t):
    i = 1
    has_c = False
    while i < len(t) and t[i].startswith('-'):
        if t[i] in ('-C', '--git-dir', '--work-tree', '-c'):
            has_c = has_c or t[i] != '-c'
            i += 2
        else:
            has_c = has_c or t[i].startswith(('--git-dir=', '--work-tree='))
            i += 1
    return (t[i] if i < len(t) else ''), has_c


def substitutions(cmd):
    """Bodies of $(...) substitutions (approximate: parentheses counted, quotes ignored)."""
    out, i = [], cmd.find('$(')
    while i >= 0:
        depth, j = 1, i + 2
        while j < len(cmd) and depth:
            depth += (cmd[j] == '(') - (cmd[j] == ')')
            j += 1
        out.append(cmd[i + 2:j - 1])
        i = cmd.find('$(', i + 2)
    return out


def net_info(cmd):
    """Network form of a Bash call, or None when it runs no gh / git network command."""
    segs = simple_commands(cmd)
    inner = [x for body in substitutions(cmd) for x in simple_commands(body)]
    net = []
    for s in segs + inner:
        t = s['t']
        if t[0] == 'gh':
            net.append(('gh', False))
        elif t[0] == 'git':
            sub, has_c = git_sub(t)
            if sub in NET_GIT:
                net.append(('git ' + sub, has_c))
    if GIT_C_NET_RE.search(cmd) and not any(c for _, c in net):
        net.append(('git -C', True))
    if not net:
        return None
    if any(c for _, c in net):
        form = '-C'
    elif len(segs) == 1 and '$(' not in cmd and '<<' not in cmd and '`' not in cmd:
        form = 'lone'
    else:
        form = 'chained'
    return {'form': form, 'cmds': [n for n, _ in net], 'segs': segs}


def gh_chain_features(cmd, segs):
    f = set()
    heads = [s['t'][0] for s in segs]
    if heads and heads[0] == 'cd':
        f.add('cd <path> && in front')
    if heads.count('gh') >= 2:
        f.add('&& with another gh')
    for i, s in enumerate(segs):
        if s['t'][0] == 'gh':
            if s['env']:
                f.add('env-var prefix on gh')
            if s['sep'] == '|' and i + 1 < len(segs):
                f.add('pipe to ' + FILTERS.get(os.path.basename(segs[i + 1]['t'][0]), 'other'))
    if any(h in ('for', 'while', 'until') for h in heads) or re.search(r'\bfor\s+\w+\s+in\b|\bdo\b', cmd):
        f.add('loop')
    if '<<' in cmd:
        f.add('here-document')
    if '$(' in cmd or '`' in cmd:
        f.add('$(...) substitution')
    if re.search(r'\d?>&\d|>\s*/dev/null|\s>\s*\S', cmd):
        f.add('redirection')
    others = [h for h in heads if h not in ('gh', 'cd') and h not in [ss for ss in []]]
    piped_into = {segs[i + 1]['t'][0] for i, s in enumerate(segs) if s['sep'] == '|' and i + 1 < len(segs)}
    if any(h not in piped_into for h in others):
        f.add('&& / ; with other commands')
    return f


def rewrite_class(feat):
    restructure = {'&& with another gh', 'loop', 'here-document', '$(...) substitution',
                   '&& / ; with other commands', 'pipe to python', 'pipe to sed/awk', 'pipe to other',
                   'pipe to xargs'}
    if feat & restructure:
        return 'needs restructuring (two or more calls, or a file)'
    if any(x.startswith('pipe to ') and x[8:] in DISPLAY_FILTERS for x in feat):
        return 'mechanical, but drops a display filter'
    return 'faithful mechanical rewrite (--jq, -R, drop 2>&1)'


# ---- brace classification (git guard refusals for brace expansion) ----



def contexts(text):
    """Per character: 'heredoc', 'single', 'double' or 'plain', and the simple command (by index)
    each character belongs to; heredoc bodies belong to the command that opened them."""
    ctx = ['plain'] * len(text)
    seg_of = [0] * len(text)
    seg_start = [0]
    lines = text.split('\n')
    pos, quote, seg = 0, None, 0
    pending = []  # heredoc delimiters opened on this line: (delim, strip_tabs, seg)
    in_body = None
    for line in lines:
        start = pos
        if in_body:
            d, strip, opener = in_body
            for k in range(len(line) + 1):
                if start + k < len(text):
                    ctx[start + k] = 'heredoc'
                    seg_of[start + k] = opener
            if (line.lstrip('\t') if strip else line) == d:
                pending.pop(0) if pending else None
                in_body = pending[0] if pending else None
            pos = start + len(line) + 1
            continue
        i = 0
        while i < len(line):
            c = line[i]
            p = start + i
            if quote:
                ctx[p] = 'single' if quote == "'" else 'double'
                if c == quote:
                    quote = None
                elif c == '\\' and quote == '"':
                    i += 1
                    if start + i < len(text):
                        ctx[start + i] = 'double'
            else:
                if c == '\\':
                    i += 1
                elif c in '"\'':
                    quote = c
                    ctx[p] = 'single' if c == "'" else 'double'
                elif c in ';|&' or line.startswith('&&', i):
                    seg += 1
                    seg_start.append(p + 1)
                elif c == '<' and line.startswith('<<', i) and not line.startswith('<<<', i):
                    m = HEREDOC_RE.match(line, i)
                    if m:
                        pending.append((m.group(2), line.startswith('<<-', i), seg))
            seg_of[p] = seg
            i += 1
        pos = start + len(line) + 1
        if not quote:
            if pending:
                in_body = pending[0]
            seg += 1
            seg_start.append(pos)
    return ctx, seg_of, seg_start


def guard_brace_positions(text):
    """Positions where the guard's brace_expansion() would answer True (its own scan)."""
    out = []
    quote, i, n = None, 0, len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == quote:
                quote = None
            elif c == '\\' and quote == '"':
                i += 1
        elif c == '\\':
            i += 1
        elif c in '"\'':
            quote = c
        elif c == '{' and (i == 0 or text[i - 1] != '$'):
            depth, j = 1, i + 1
            while j < n and depth and text[j] not in ' \t\n;|&':
                depth += (text[j] == '{') - (text[j] == '}')
                j += 1
            inner = text[i + 1:j - 1] if depth == 0 else ''
            if ',' in inner or '..' in inner:
                out.append(i)
        i += 1
    return out


def seg_head(text, seg_start, seg):
    start = seg_start[seg] if seg < len(seg_start) else 0
    s = text[start:].split('\n', 1)[0]
    s = SPLIT_RE.split(s, 1)[0].strip().lstrip('({ ')
    t = tokens(s)
    while t and (ASSIGN.match(t[0]) or t[0] in PREFIX_WORDS) and len(t) > 1:
        t = t[1:]
    return os.path.basename(t[0]) if t else ''


def head_class(h):
    if h == 'git':
        return 'git'
    if h == 'gh':
        return 'gh'
    if h in ('python3', 'python', 'node', 'jq', 'awk', 'perl', 'ruby', 'sed'):
        return 'program (python/jq/awk/sed/node)'
    if h in ('cat', 'echo', 'printf', 'tee'):
        return 'cat/echo/printf'
    if h in ('for', 'while', 'if', 'case'):
        return 'shell control'
    return 'other command'


def classify_brace(cmd):
    text = cmd.replace('\\\n', ' ')
    found = guard_brace_positions(text)
    if not found:
        return None
    ctx, seg_of, seg_start = contexts(text)
    p = found[0]
    where = ctx[p] if p < len(ctx) else 'plain'
    head = head_class(seg_head(text, seg_start, seg_of[p] if p < len(seg_of) else 0))
    shape = {'heredoc': 'inside a here-document body', 'single': 'inside a single-quoted string',
             'double': 'inside a double-quoted string', 'plain': 'unquoted'}[where]
    if where == 'plain':
        j = p + 1
        depth = 1
        while j < len(text) and depth and text[j] not in ' \t\n;|&':
            depth += (text[j] == '{') - (text[j] == '}')
            j += 1
        inner = text[p + 1:j - 1]
        if '"' in inner or ':' in inner:
            shape = 'unquoted, JSON-like literal'
        elif p > 0 and text[p - 1] == '@':
            shape = 'unquoted @{...} form'
        else:
            shape = 'unquoted {a,b} / {1..3} expansion'
    extra = []
    if '${' in text:
        extra.append('${var} also present')
    if re.search(r'@\{', text):
        extra.append('@{...} also present')
    return shape, head, extra


# ---- main pass ----

def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('projects', nargs='?', default=os.path.expanduser('~/.claude/projects'))
    ap.add_argument('--since', default='2026-10-12')
    ap.add_argument('--until', default='2099-01-01')
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(HERE)))
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    skills, scripts, _ = ts_mod.repo_inventory(a.repo)
    script_names = set(scripts)
    skill_files = {}
    for s in skills:
        skill_files[s] = True
    since_epoch = dt.datetime.fromisoformat(a.since).timestamp()

    C = collections.defaultdict(collections.Counter)
    TOK = collections.defaultdict(list)          # class -> [context tokens]
    TOKW = collections.defaultdict(collections.Counter)  # class -> week -> tokens
    sessions = []  # per-session summaries for Q2

    def unit_files():
        for d in sorted(os.listdir(a.projects)):
            full = os.path.join(a.projects, d)
            if not os.path.isdir(full):
                continue
            for root, _, files in os.walk(full):
                for f in sorted(files):
                    if f.endswith('.jsonl'):
                        p = os.path.join(root, f)
                        if os.path.getmtime(p) >= since_epoch:
                            yield p

    for path in unit_files():
        is_sub = '/subagents/' in path
        calls, index = [], {}
        first_user_seen = False
        sources = []  # (label, set(pattern names)) until the first network call
        first_net_done = False
        start_ts = None
        with open(path, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                is_att = '"type":"attachment"' in line
                if not (is_att or '"type":"assistant"' in line or '"type":"user"' in line):
                    continue
                if is_att and first_net_done:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                t = o.get('type')
                ts = o.get('timestamp') or ''
                if not ts or ts[:10] < a.since or ts[:10] > a.until:
                    continue
                if start_ts is None and t in ('assistant', 'user'):
                    start_ts = ts
                if t == 'attachment':
                    at = o.get('attachment') or {}
                    blob = json.dumps(at.get('content', ''))
                    hits = {k for k, r in PATTERNS.items() if r.search(blob.replace('\\n', '\n'))}
                    if hits:
                        sources.append(('attachment: ' + str(at.get('type')), hits))
                    continue
                m = o.get('message') or {}
                content = m.get('content')
                if t == 'assistant':
                    u = m.get('usage') or {}
                    ctx = (u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0) + \
                          (u.get('cache_creation_input_tokens') or 0)
                    if not isinstance(content, list):
                        continue
                    for b in content:
                        if not isinstance(b, dict) or b.get('type') != 'tool_use':
                            continue
                        inp = b.get('input') or {}
                        c = {'name': b.get('name'), 'ts': ts, 'ctx': ctx, 'out': 'ok',
                             'inhash': hash(json.dumps(inp, sort_keys=True, default=str))}
                        if c['name'] == 'Bash':
                            cmd = str(inp.get('command', ''))
                            c['dds'] = bool(inp.get('dangerouslyDisableSandbox'))
                            ni = net_info(cmd)
                            if ni:
                                c['net'] = ni['form']
                                c['netcmds'] = ni['cmds']
                                if c['dds']:
                                    feats = None
                                    heads = [s['t'][0] for s in ni['segs']]
                                    if 'gh' in ni['cmds'] and ni['form'] != 'lone':
                                        feats = gh_chain_features(cmd, ni['segs'])
                                        for f in feats:
                                            C['Q3 escaped gh chained/piped: feature'][f] += 1
                                        C['Q3 escaped gh chained/piped: rewrite class'][rewrite_class(feats)] += 1
                                        C['Q3 escaped gh chained/piped: total']['calls'] += 1
                            if c['dds']:
                                segs = simple_commands(cmd)
                                if len(segs) > 1 and segs[0]['t'][0] == 'cd':
                                    nxt = None
                                    for s in segs[1:]:
                                        h = s['t'][0]
                                        if h == 'gh':
                                            nxt = 'gh'
                                        elif h == 'git':
                                            sub, _ = git_sub(s['t'])
                                            nxt = 'git ' + sub if sub in NET_GIT | {'clone'} else None
                                        elif os.path.basename(h) in NET_WORDS or h in ('npm', 'npx', 'pnpm', 'pip', 'pip3', 'cargo', 'brew'):
                                            nxt = os.path.basename(h)
                                        if nxt:
                                            break
                                    if nxt:
                                        target = segs[0]['t'][1] if len(segs[0]['t']) > 1 else ''
                                        same = os.path.realpath(os.path.expanduser(target)) == os.path.realpath(o.get('cwd') or '')
                                        C['Q3 escaped cd <path> && <network>: command'][nxt] += 1
                                        C['Q3 escaped cd <path> && <network>: cd target'][(nxt.split()[0], 'session folder' if same else 'another folder')] += 1
                                        C['Q3 escaped cd <path> && <network>: total']['calls'] += 1
                                        rest = len(segs) > 2
                                        C['Q3 escaped cd <path> && <network>: more commands after it'][(nxt.split()[0], 'yes' if rest else 'no')] += 1
                            if '{' in cmd:
                                c['cmd_brace'] = cmd
                            sc = [x for x in script_names if x in cmd]
                            if sc:
                                c['script'] = sorted(sc)[0]
                        if c['name'] == 'Read':
                            fp = str(inp.get('file_path', ''))
                            mm = re.search(r'/skills/([\w-]+)/([\w.-]+\.md)$', fp)
                            if mm and mm.group(1) in skills:
                                c['readname'] = mm.group(1) + '/' + mm.group(2)
                            elif os.path.basename(fp) in ('AGENTS.md', 'HANDOFF.md', 'CLAUDE.md', 'core.md', 'README.md'):
                                c['readname'] = os.path.basename(fp) + ' (a repository document)'
                        bid = b.get('id')
                        calls.append(c)
                        if bid:
                            index[bid] = c
                        if c.get('net') and not first_net_done:
                            first_net_done = True
                            c['first_net'] = True
                            c['sources'] = sources
                    continue
                # user
                if isinstance(content, str):
                    blocks = [{'type': 'text', 'text': content}]
                elif isinstance(content, list):
                    blocks = content
                else:
                    continue
                pd = o.get('permissionDecision') if isinstance(o.get('permissionDecision'), dict) else {}
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    if b.get('type') == 'text':
                        txt = b.get('text') or ''
                        if first_net_done:
                            continue
                        hits = {k for k, r in PATTERNS.items() if r.search(txt)}
                        mm = re.search(r'Base directory for this skill: \S*/skills/([\w-]+)', txt)
                        if mm:
                            label = 'skill body: ' + (mm.group(1) if mm.group(1) in skills else '<other skill>')
                        elif not first_user_seen and not o.get('isMeta'):
                            label = 'start brief (first user message)'
                        elif o.get('isMeta'):
                            label = 'injected text (meta)'
                        else:
                            label = 'later user / coordinator message'
                        if not o.get('isMeta'):
                            first_user_seen = True
                        if hits:
                            sources.append((label, hits))
                        continue
                    if b.get('type') != 'tool_result':
                        continue
                    c = index.pop(b.get('tool_use_id'), None)
                    text = result_text(b)
                    if c is None:
                        continue
                    err = bool(b.get('is_error'))
                    src = pd.get('source')
                    label = next((lb for lb, nd in GUARDS if nd in text), None)
                    if (src == 'hook' or pd.get('reasonType') == 'hook') and pd.get('decision') == 'reject':
                        c['out'] = 'blocked:' + (label or 'other hook')
                        c['reason'] = guard_reason(label, text)
                    elif c['name'] == 'Bash' and (o.get('sandboxViolations') or (err and SANDBOX_RE.search(text[:3000]))):
                        c['out'] = 'sandbox-fail'
                    elif err:
                        c['out'] = 'error'
                    tdk = o.get('toolDenialKind')
                    if tdk:
                        c['tdk'] = tdk
                        if tdk in ('automode-blocked', 'automode-unavailable'):
                            cause = ('a hook changed this call\'s input after review' if "a hook changed this call's input" in text else
                                     'another call in the same response was changed' if 'another call in this response was changed' in text else
                                     'classifier gave no verdict (other cause)' if 'gave no verdict' in text else
                                     'denied by the classifier' if 'denied by the Claude' in text or 'auto mode' in text.lower() else 'other wording')
                            c['automode_cause'] = cause
                            C['Q5 auto-mode denials by cause'][(tdk, cause)] += 1
                            C['Q5 auto-mode denials by cause and call'][(cause, ('Bash, dds' if c.get('dds') else 'Bash, sandbox on') if c['name'] == 'Bash' else c['name'])] += 1
                    if "a hook changed this call's input" in text or 'another call in this response was changed' in text:
                        c['hook_changed'] = True
                    if not first_net_done:
                        hits = {k for k, r in PATTERNS.items() if r.search(text)}
                        if hits:
                            if c['name'] == 'Read':
                                lab = 'file read' + (': ' + c['readname'] if c.get('readname') else '')
                            elif c['name'] == 'Bash':
                                lab = 'command output' + (': ' + c['script'] if c.get('script') else '')
                            elif c['name'] == 'Skill':
                                lab = 'skill tool result'
                            else:
                                lab = 'tool output: ' + str(c['name'])
                            sources.append((lab, hits))
        if not calls:
            continue
        analyse(calls, is_sub, start_ts, C, TOK, TOKW, sessions)

    # Q2 split by the guard's first block
    guard_day = min((s['first_block_ts'] for s in sessions if s.get('first_block_ts')), default=None)
    for s in sessions:
        if not s.get('first_net'):
            continue
        era = ('before' if guard_day is None or (s['start'] or '') < guard_day else 'after') + \
              ' the sandbox-network guard'
        unit = 'subagent' if s['is_sub'] else 'main session'
        C['Q2 first network call'][(unit, era, s['first_net'])] += 1
        C['Q2 first network call, all'][s['first_net']] += 1
        C['Q2 first network call by week'][(iso_week(s['start']), s['first_net'])] += 1
    R = {'guard first block (UTC)': guard_day,
         'tokens': {k: {'n': len(v), 'median': statistics.median(v) if v else 0, 'sum': sum(v)}
                    for k, v in sorted(TOK.items())},
         'tokens per week': {k: dict(sorted(v.items())) for k, v in sorted(TOKW.items())},
         'counters': {k: [[list(x) if isinstance(x, tuple) else x, n] for x, n in v.most_common()]
                      for k, v in C.items()}}
    if a.json:
        json.dump(R, sys.stdout, indent=1, default=str)
    else:
        print('guard first block:', guard_day)
        print('\n## tokens (context of the issuing turn, per failed/blocked call)')
        for k, v in R['tokens'].items():
            print('  %-48s n=%6d median=%8d sum=%12d  weeks=%s' % (k, v['n'], v['median'], v['sum'],
                  {w: n for w, n in R['tokens per week'].get(k, {}).items() if w >= '2026-W46'}))
        for k, v in R['counters'].items():
            print('\n## ' + k)
            for x, n in v[:40]:
                print('  %6d  %s' % (n, x))
    return 0


def first_net_class(c):
    if c.get('dds'):
        return '(d) sandbox off pre-emptively'
    return {'lone': '(a) lone, sandbox on', 'chained': '(b) chained/piped, sandbox on',
            '-C': '(c) git -C, sandbox on'}[c['net']]


def analyse(calls, is_sub, start, C, TOK, TOKW, sessions):
    unit = 'subagent' if is_sub else 'main'
    summary = {'is_sub': is_sub, 'start': start}
    # Q6 token cost of failed round trips
    for c in calls:
        cls = None
        if c['out'].startswith('blocked:'):
            cls = 'guard block: ' + c['out'][8:]
        elif c['out'] == 'sandbox-fail':
            cls = 'sandbox failure (Bash)'
        elif c['name'] == 'mcp__ccd_session_mgmt__archive_session' and c['out'] != 'ok':
            cls = 'archive_session failure (not the guard)'
        elif c.get('tdk') and c['out'] != 'ok':
            cls = 'denial: ' + c['tdk']
        elif c['out'] == 'error' and c['name'] == 'Bash':
            cls = 'other Bash error'
        if cls:
            TOK[cls].append(c['ctx'])
            TOKW[cls][iso_week(c['ts'])] += c['ctx']
            TOK['ALL failed or refused calls'].append(c['ctx'])
            TOKW['ALL failed or refused calls'][iso_week(c['ts'])] += c['ctx']
        if c.get('hook_changed'):
            C['Q5 refusals because a hook changed the input'][c['name']] += 1
    # Q1 per guard
    for guard, sel in (('sandbox-network guard', lambda c: c.get('net') in ('chained', '-C') or c['out'] == 'blocked:sandbox-network guard'),
                       ('git guard', lambda c: c['name'] == 'Bash'),
                       ('archive guard', lambda c: c['name'] == 'mcp__ccd_session_mgmt__archive_session')):
        tag = 'blocked:' + guard
        idx = [i for i, c in enumerate(calls) if c['out'] == tag]
        if not idx:
            continue
        n = len(idx)
        C['Q1 %s: blocks per session' % guard][(unit, '1' if n == 1 else '2' if n == 2 else '3+')] += 1
        C['Q1 %s: sessions' % guard][(unit, 'repeated after the first block' if n > 1 else 'never repeated')] += 1
        if guard == 'sandbox-network guard' and summary.get('first_block_ts') is None:
            summary['first_block_ts'] = calls[idx[0]]['ts']
        first = idx[0]
        if guard == 'git guard':
            reasons = [calls[i].get('reason') for i in idx]
            C['Q1 git guard: later blocks']['same reason as the first'] += sum(r == reasons[0] for r in reasons[1:])
            C['Q1 git guard: later blocks']['another reason'] += sum(r != reasons[0] for r in reasons[1:])
            later_git = [c for c in calls[first + 1:] if c['name'] == 'Bash' and c['out'] != tag]
            C['Q1 git guard: later Bash calls in the session'][('passed the guard')] += len(later_git)
            continue
        for c in calls[first + 1:]:
            if not sel(c):
                continue
            if guard == 'archive guard':
                k = 'blocked again' if c['out'] == tag else 'archived (no error)' if c['out'] == 'ok' else 'failed otherwise (' + (c.get('tdk') or c['out']) + ')'
            else:
                if c['out'] == tag:
                    k = '(a) blocked again'
                elif c.get('dds'):
                    k = '(c) escaped the sandbox'
                else:
                    k = 'ran chained/-C in the sandbox, not blocked (' + c['out'] + ')'
                C['Q1 %s: later calls of the class after the first block' % guard][k] += 1
                continue
            C['Q1 %s: later calls of the class after the first block' % guard][k] += 1
        if guard == 'sandbox-network guard':
            lone = sum(1 for c in calls[first + 1:] if c.get('net') == 'lone' and not c.get('dds'))
            C['Q1 sandbox-network guard: later calls of the class after the first block']['(b) lone network call, sandbox on'] += lone
        if guard == 'archive guard':
            gs = any(c['name'] == 'mcp__ccd_session_mgmt__get_session' for c in calls[first + 1:])
            C['Q1 archive guard: get_session called after the first block'][gs] += 1
    # Q1 plain sandbox failure of a network call
    idx = [i for i, c in enumerate(calls) if c.get('net') and c['out'] == 'sandbox-fail']
    if idx:
        first = idx[0]
        C['Q1 network sandbox failures per session'][(unit, '1' if len(idx) == 1 else '2' if len(idx) == 2 else '3+')] += 1
        for c in calls[first + 1:]:
            if not c.get('net'):
                continue
            if c.get('dds'):
                k = 'sandbox off (escape)'
            elif c['net'] == 'lone':
                k = 'lone form, sandbox on'
            elif c['out'].startswith('blocked:'):
                k = 'chained/-C, blocked by a guard'
            else:
                k = 'chained/-C again in the sandbox (' + ('failed again' if c['out'] == 'sandbox-fail' else 'ran') + ')'
            C['Q1 later network calls after the first network sandbox failure'][k] += 1
    # Q2 first network call; Q4 sources of its form
    fn = next((c for c in calls if c.get('first_net')), None)
    if fn:
        cls = first_net_class(fn)
        summary['first_net'] = cls
        if fn['net'] in ('chained', '-C'):
            want = set()
            if fn['net'] == '-C':
                want.add('git -C <path> <network>')
            else:
                want |= {'cd <path> && gh', 'cd <path> && git <network>', 'gh ... | <filter>', 'gh ... && gh'}
            hits = [lab for lab, h in fn.get('sources', []) if h & want]
            C['Q4 sessions whose first network call is chained/-C'][unit] += 1
            C['Q4 ... of which the form appeared earlier in the session'][(unit, bool(hits))] += 1
            for lab in sorted(set(hits)):
                C['Q4 where it appeared earlier (sessions)'][lab] += 1
    sessions.append(summary)
    # Q5 next call after a hook-changed input
    for i, c in enumerate(calls):
        if c.get('hook_changed'):
            nxt = next((d for d in calls[i + 1:] if d['name'] == c['name']), None)
            k = ('no later call of that tool' if nxt is None else
                 'identical retry' if nxt['inhash'] == c['inhash'] else 'same tool, changed input')
            out = '' if nxt is None else ' -> ' + nxt['out']
            C['Q5 next call of the same tool after a hook-changed refusal'][(c['name'], k + out)] += 1
    # Q7 brace blocks
    for c in calls:
        if c['out'] == 'blocked:git guard' and 'brace' in (c.get('reason') or ''):
            r = classify_brace(c.get('cmd_brace', ''))
            if r is None:
                C['Q7 brace blocks: shape']['(guard scan not reproduced)'] += 1
                continue
            shape, head, extra = r
            C['Q7 brace blocks: shape x segment'][(shape, head)] += 1
            C['Q7 brace blocks: shape'][shape] += 1
            C['Q7 brace blocks: brace in the git segment itself'][head == 'git'] += 1
            for e in extra:
                C['Q7 brace blocks: also present'][e] += 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
