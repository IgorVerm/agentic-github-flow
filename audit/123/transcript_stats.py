#!/usr/bin/env python3
"""Aggregate counts from Claude Code session transcripts for the audit of issue #123.

Reads `<projects>/<project-dir>/*.jsonl` (main sessions) and `<project-dir>/<session>/subagents/
**/*.jsonl` (subagents), streaming, and prints ONLY aggregates: counts, rates, token sizes, tool
names, this repository's skill and script names, and command shapes with every argument that
could carry a path, a name or prose reduced to a placeholder. It never prints message text, file
contents, project directory names (other projects get a generic label) or tool output.

Usage:
  python3 audit/123/transcript_stats.py [PROJECTS_DIR] [--since YYYY-MM-DD] [--until YYYY-MM-DD]
                                        [--repo REPO_ROOT] [--json]
PROJECTS_DIR defaults to ~/.claude/projects; --repo defaults to the repository holding this file.

Matching (each count in the report names its matcher):
- skill use: `Skill` tool_use `input.skill` (plugin prefix stripped), `/<skill>` slash commands
  in user turns (`<command-name>`), and `Read` of `.../skills/<skill>/<file>.md`;
- script use: a Bash tool_use whose command contains `<script file name>` of plugins/*/scripts;
  failure = the tool_result's `is_error`;
- guard blocks: the tool_result text contains a guard's own message prefix (see GUARDS); hook
  decisions also from the entry's `permissionDecision.source == "hook"`;
- sandbox: the tool_result text matches SANDBOX_RE, or the entry carries `sandboxViolations`;
  escapes: Bash `input.dangerouslyDisableSandbox == true`;
- permission: the entry's `toolDenialKind`, and `permissionDecision.source` user_* values;
- context: per API response (deduplicated by message id), input + cache_read + cache_creation.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import shlex
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

GUARDS = [  # (label, substring of the guard's own message)
    ('git guard', 'Blocked by the git guard'),
    ('merge guard', 'Refused by the merge guard'),
    ('sandbox-network guard', 'Refused by the sandbox-network guard'),
    ('delete guard (ask)', 'Delete guard (agentic-github-flow'),
    ('personal-data check (ask)', 'Personal-data check (agentic-github-flow'),
    ('personal-data check (deny)', 'Blocked by the personal-data check'),
    ('archive guard', 'archive guard:'),
    ('context limit', 'context limit:'),
    ('question label', 'question label: this question'),
]
REPO_GROUP_RE = re.compile(r'agentic-github-flow|agent-rules')
ISSUE_BRANCH_RE = re.compile(r'^agent/\d')
SANDBOX_RE = re.compile(r'Operation not permitted|sandbox|network (?:access )?denied|'
                        r'not in this command\'s allowed_domains|Could not resolve host|'
                        r'ssh: connect to host|Connection refused', re.I)
NET_GIT = {'push', 'fetch', 'pull', 'ls-remote', 'clone'}
GIT_C_NET_RE = re.compile(r'\bgit\s+(?:(?:-C|--git-dir|--work-tree)(?:=|\s+)(?:"[^"]*"|\'[^\']*\'|\S+)\s+)+'
                          r'(?:-c\s+\S+\s+)*(push|fetch|pull|ls-remote)\b')
EDIT_ERRORS = [
    ('not read first', re.compile(r'has not been read yet|must (?:read|Read)|Read it first', re.I)),
    ('old_string not found', re.compile(r'String to replace not found|old_string.*not found', re.I)),
    ('old_string not unique', re.compile(r'Found \d+ matches|not unique', re.I)),
    ('modified since read', re.compile(r'modified since|has been modified', re.I)),
    ('file does not exist', re.compile(r'does not exist|No such file', re.I)),
]
REJECT_RE = re.compile(r"user doesn't want to proceed|user (?:has )?(?:rejected|declined)|"
                       r"Permission to use .* has been denied|has been denied", re.I)
REF_FILES = {'method.md', 'local-main.md', 'checklist.md', 'sources.md', 'skill-standard.md',
             'skeleton.md', 'cloud-run.md', 'cloud-sql.md', 'dashboard.md', 'google-auth.md',
             'iap.md', 'mail.md', 'privacy.md', 'supabase.md', 'vercel.md'}
HEADER_LANDING = re.compile(r'push|merge|land|archiv|opruim|clean|branch|worktree|\bPR\b', re.I)
COMPACT_TEXT = 'This session is being continued from a previous conversation'


def repo_inventory(repo):
    skills, scripts, hook_scripts = {}, {}, set()
    pdir = os.path.join(repo, 'plugins')
    for plugin in sorted(os.listdir(pdir)):
        sdir = os.path.join(pdir, plugin, 'skills')
        if os.path.isdir(sdir):
            for s in sorted(os.listdir(sdir)):
                skills[s] = plugin
        cdir = os.path.join(pdir, plugin, 'scripts')
        if os.path.isdir(cdir):
            for s in sorted(os.listdir(cdir)):
                if s.endswith(('.py', '.sh')):
                    scripts.setdefault(s, []).append(plugin)
        hj = os.path.join(pdir, plugin, 'hooks', 'hooks.json')
        if os.path.isfile(hj):
            text = open(hj, encoding='utf-8').read()
            for s in re.findall(r'scripts/([\w.-]+\.(?:py|sh))', text):
                hook_scripts.add(s)
    return skills, scripts, hook_scripts


PLACE = re.compile(r'^[A-Za-z][A-Za-z0-9_.:+-]{0,24}$')


def word_shape(w):
    if not w:
        return '<arg>'
    if w.startswith('-'):
        return w.split('=', 1)[0] if len(w) <= 24 and PLACE.match(w.lstrip('-') or 'x') else '<opt>'
    if '/' in w or w.startswith(('~', '.', '$')):
        base = os.path.basename(w.rstrip('/'))
        return '<path>/' + base if base in SCRIPT_NAMES else '<path>'
    if base_script(w):
        return w
    if w.isdigit():
        return '<n>'
    if '@' in w or not PLACE.match(w):
        return '<arg>'
    return w


SCRIPT_NAMES = set()
SUBCOMMAND_TOOLS = {'gh', 'cargo', 'npm', 'npx', 'pnpm', 'claude', 'codex', 'docker', 'brew',
                    'pip', 'pip3', 'go', 'ssh', 'launchctl', 'osascript', 'open'}


def guard_reason(label, text):
    """The guard's fixed reason phrase, with anything path- or name-like reduced."""
    m = None
    if label == 'git guard':
        m = re.search(r'this command (.{0,90}?)\. Use the safe form', text, re.S)
    elif label == 'archive guard':
        m = re.search(r'archive guard: (.{0,60})', text)
    elif label == 'sandbox-network guard':
        m = re.search(r'sandbox-network guard: (.{0,60})', text)
    elif label == 'merge guard':
        m = re.search(r'\(agentic-github-flow, #108\): (.{0,50})', text)
    elif label == 'context limit':
        m = re.search(r'context limit: (.{0,40})', text)
    if not m:
        return '-'
    words = []
    for w in m.group(1).split():
        if '/' in w or '~' in w or '@' in w or re.search(r'\d|[`"\'#_]', w):
            w = '<x>'
        words.append(w)
    return ' '.join(words[:12])


def base_script(w):
    return w in SCRIPT_NAMES


SPLIT_RE = re.compile(r'\s*(?:&&|\|\||;|\|)\s*')


def tokens(cmd):
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return cmd.split()


def segments(cmd):
    """Split the first non-comment line of a command into its simple commands (rough: quotes
    are not respected; leading `(`, `{` and comment lines are dropped)."""
    lines = [ln.strip() for ln in cmd.strip().split('\n')]
    first_line = next((ln for ln in lines if ln and not ln.startswith('#')), '')
    first_line = first_line.lstrip('({ ')
    return [s for s in SPLIT_RE.split(first_line) if s.strip() and s.strip() not in ('(', '{', ')', '}')]


def seg_shape(seg, n=3):
    t = tokens(seg)
    assigned = False
    while t and (re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', t[0]) or
                 t[0] in ('sudo', 'env', 'time', 'nice', 'command', 'exec', 'export')):
        assigned = assigned or '=' in t[0]
        t = t[1:]
    if not t:
        return 'VAR=<value>' if assigned else '<empty>'
    head = t[0]
    if head == 'git':
        out, i = ['git'], 1
        while i < len(t) and t[i].startswith('-'):
            if t[i] in ('-C', '-c', '--git-dir', '--work-tree') and i + 1 < len(t):
                out += [t[i], '<path>' if t[i] != '-c' else '<cfg>']
                i += 2
            else:
                out.append(word_shape(t[i]))
                i += 1
        if i < len(t):
            out.append(word_shape(t[i]))
        return ' '.join(out)
    if head in ('python3', 'python', 'sh', 'bash', 'zsh', 'node', 'uv', 'uvx'):
        rest = [x for x in t[1:] if not x.startswith('-')][:1]
        if head in ('sh', 'bash', 'zsh') and '-c' in t[1:3]:
            return head + ' -c <str>'
        return ' '.join([head] + [word_shape(x) for x in rest])
    if head in SUBCOMMAND_TOOLS:
        shown = [head] + [word_shape(x) for x in t[1:n] if not x.startswith('-')][:n - 1]
        return ' '.join(shown)
    return word_shape(head)


def cmd_shape(cmd):
    segs = segments(cmd)
    if not segs:
        return '<empty>'
    shapes = [seg_shape(s) for s in segs]
    lead = []
    while len(shapes) > 1 and len(lead) < 2 and (shapes[0].split(' ')[0] == 'cd' or shapes[0] == 'VAR=<value>'):
        lead.append('cd <path>' if shapes[0].startswith('cd') else shapes[0])
        shapes = shapes[1:]
    return ' && '.join(lead + [shapes[0]]) + (' && ...' if len(shapes) > 1 else '')


def chain_classes(cmd):
    """Classes of issue #122 / agent-rules#56: git -C network, gh in a chain, cd && network."""
    out = set()
    segs = [x for line in cmd.split('\n') if line.strip() and not line.strip().startswith('#')
            for x in SPLIT_RE.split(line.strip().lstrip('({ ')) if x.strip()]
    multi = len(segs) > 1
    for s in segs:
        t = tokens(s)
        while t and (re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', t[0]) or t[0] in ('env', 'command', 'time', 'exec')):
            t = t[1:]
        if not t:
            continue
        while t and t[0] in ('do', 'then', 'else', '!', 'if', 'while', 'until') and len(t) > 1:
            t = t[1:]
        if t[0] == 'git':
            i, has_c = 1, False
            while i < len(t) and t[i].startswith('-'):
                if t[i] in ('-C', '--git-dir', '--work-tree', '-c'):
                    has_c = has_c or t[i] != '-c'
                    i += 2
                else:
                    i += 1
            sub = t[i] if i < len(t) else ''
            if sub in NET_GIT:
                out.add('git -C <path> ' + sub if has_c else
                        ('git ' + sub + ' (chained)' if multi else 'git ' + sub + ' (lone)'))
        elif t[0] == 'gh':
            out.add('gh (chained)' if multi else 'gh (lone)')
        elif t[0] in ('ssh', 'scp', 'rsync') and multi:
            out.add(t[0] + ' (chained)')
    for m in GIT_C_NET_RE.finditer(cmd):
        out.add('git -C <path> ' + m.group(1))
    if segs and tokens(segs[0])[:1] == ['cd'] and multi and out:
        out.add('cd <path> && <network command>')
    return out


INTERP = {'python3', 'python', 'sh', 'bash', 'zsh', 'uv', 'exec'}


def run_scripts(cmd, candidates):
    """The candidate scripts this command runs: as a segment's head, or as the first
    non-option argument of an interpreter (`python3 -I <path>/x.py`)."""
    found = []
    for line in cmd.split('\n'):
        for seg in SPLIT_RE.split(line):
            t = tokens(seg.strip().lstrip('({ '))
            while t and (re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', t[0]) or t[0] in ('env', 'time', 'command', 'exec')):
                t = t[1:]
            if not t:
                continue
            target = None
            if os.path.basename(t[0]).split('.')[0] in ('python3', 'python', 'sh', 'bash', 'zsh'):
                rest = [x for x in t[1:] if not x.startswith('-')]
                target = rest[0] if rest else None
            elif t[0] == 'uv' and len(t) > 2 and t[1] == 'run':
                rest = [x for x in t[2:] if not x.startswith('-')]
                target = rest[0] if rest else None
            else:
                target = t[0]
            if target:
                b = os.path.basename(target)
                if b in candidates and b not in found:
                    found.append(b)
    return found


def result_text(block):
    c = block.get('content')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return '\n'.join(x.get('text', '') for x in c if isinstance(x, dict) and x.get('type') == 'text')
    return ''


def iso_week(ts):
    d = dt.date.fromisoformat(ts[:10])
    y, w, _ = d.isocalendar()
    return '%d-W%02d' % (y, w)


def pct(values, p):
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))]


def norm_model(m):
    m = m or '?'
    m = re.sub(r'^claude-', '', m)
    m = re.sub(r'-\d{8}$', '', m)
    return m


class Session:
    __slots__ = ('sid', 'group', 'project', 'issue_chat', 'start', 'models', 'ctx', 'seen_ids',
                 'out_tokens', 'cache_read', 'tool_uses', 'ctx_after10', 'compactions',
                 'questions', 'handovers', 'is_sub', 'branch', 'lines', 'entry', 'ho_skill', 'ho_note')

    def __init__(self, sid, group, project, is_sub):
        self.sid, self.group, self.project, self.is_sub = sid, group, project, is_sub
        self.issue_chat = False
        self.branch = None
        self.start = None
        self.models = collections.Counter()
        self.ctx = []
        self.seen_ids = set()
        self.out_tokens = self.cache_read = self.tool_uses = 0
        self.ctx_after10 = None
        self.compactions = self.questions = self.handovers = self.lines = 0
        self.entry = None
        self.ho_skill = self.ho_note = 0


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('projects', nargs='?', default=os.path.expanduser('~/.claude/projects'))
    ap.add_argument('--since', default='2026-10-12')
    ap.add_argument('--until', default='2099-01-01')
    ap.add_argument('--repo', default=os.path.dirname(os.path.dirname(HERE)))
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)

    skills, scripts, hook_scripts = repo_inventory(a.repo)
    SCRIPT_NAMES.update(scripts)
    script_res = {s: re.compile(r'(?<![\w.-])' + re.escape(s) + r'(?![\w.-])') for s in scripts}
    skill_ref_re = re.compile(r'/skills/([\w-]+)/([\w.-]+\.md)$')

    since, until = a.since, a.until
    since_epoch = dt.datetime.fromisoformat(since).timestamp()

    # project dir -> label
    dirs = sorted(d for d in os.listdir(a.projects) if os.path.isdir(os.path.join(a.projects, d)))
    def base_project(d):
        b = re.sub(r'-(?:worktrees|-claude-worktrees)-.*$', '', d)
        b = re.sub(r'-worktrees$', '', b)
        return b
    sizes = collections.Counter()
    for d in dirs:
        for root, _, files in os.walk(os.path.join(a.projects, d)):
            for f in files:
                if f.endswith('.jsonl'):
                    p = os.path.join(root, f)
                    if os.path.getmtime(p) >= since_epoch:
                        sizes[base_project(d)] += os.path.getsize(p)
    labels = {}
    n = 0
    for b, _ in sizes.most_common():
        if REPO_GROUP_RE.search(b):
            labels[b] = 'this repository' if 'agentic-github-flow' in b else 'agent-rules (overlay)'
        else:
            labels[b] = 'other project %s' % (chr(65 + n) if n < 26 else str(n))
            n += 1

    C = collections.defaultdict(collections.Counter)
    sessions = {}
    tool_index = {}  # tool_use id -> info
    last_bash = {}   # session key -> list of recent bash infos
    files_read = lines_read = 0
    skill_weeks = collections.defaultdict(collections.Counter)
    ask_per_session = collections.Counter()
    ctxnote_files = set()

    for d in dirs:
        group_label = labels.get(base_project(d))
        if group_label is None:
            continue
        group = 'repo' if group_label in ('this repository', 'agent-rules (overlay)') else 'other'
        for root, _, files in os.walk(os.path.join(a.projects, d)):
            for f in sorted(files):
                if not f.endswith('.jsonl'):
                    continue
                path = os.path.join(root, f)
                if os.path.getmtime(path) < since_epoch:
                    continue
                is_sub = '/subagents/' in path
                files_read += 1
                skey = path  # one Session per file (main session or one subagent)
                S = None
                with open(path, encoding='utf-8', errors='replace') as fh:
                    for line in fh:
                        if '"type":"attachment"' in line and 'context limit' in line:
                            try:
                                o = json.loads(line)
                            except ValueError:
                                continue
                            at = o.get('attachment') or {}
                            ts = o.get('timestamp') or ''
                            if o.get('type') == 'attachment' and since <= ts[:10] <= until and \
                                    'context limit' in json.dumps(at.get('content', ''))[:300]:
                                C['context limit notes (hook additionalContext)'][at.get('hookEvent') or at.get('type')] += 1
                                ctxnote_files.add(path)
                            continue
                        if not ('"type":"assistant"' in line or '"type":"user"' in line or
                                '"type":"system"' in line):
                            continue
                        try:
                            o = json.loads(line)
                        except ValueError:
                            C['meta']['unparsable lines'] += 1
                            continue
                        t = o.get('type')
                        if t not in ('assistant', 'user', 'system'):
                            continue
                        ts = o.get('timestamp') or ''
                        if not ts or ts[:10] < since or ts[:10] > until:
                            continue
                        lines_read += 1
                        if S is None:
                            S = Session(o.get('sessionId'), group, group_label, is_sub)
                            sessions[skey] = S
                        S.lines += 1
                        if S.start is None:
                            S.start = ts
                        if S.entry is None and o.get('entrypoint'):
                            S.entry = o['entrypoint']
                        if S.branch is None and o.get('gitBranch'):
                            S.branch = o['gitBranch']
                            S.issue_chat = bool(ISSUE_BRANCH_RE.match(S.branch))
                        if t == 'system':
                            if o.get('subtype') == 'compact_boundary':
                                S.compactions += 1
                                md = o.get('compactMetadata') or {}
                                C['compact trigger'][str(md.get('trigger'))] += 1
                            continue
                        m = o.get('message') or {}
                        content = m.get('content')
                        if t == 'assistant':
                            mid = m.get('id') or o.get('requestId')
                            u = m.get('usage') or {}
                            model = m.get('model')
                            if model and model != '<synthetic>' and mid and mid not in S.seen_ids and u:
                                S.seen_ids.add(mid)
                                S.models[norm_model(model)] += 1
                                ctx = (u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0) + \
                                      (u.get('cache_creation_input_tokens') or 0)
                                S.ctx.append(ctx)
                                S.out_tokens += u.get('output_tokens') or 0
                                S.cache_read += u.get('cache_read_input_tokens') or 0
                                if S.ctx_after10 is None and S.tool_uses >= 10:
                                    S.ctx_after10 = ctx
                            elif mid and mid in S.seen_ids and u:
                                # later block of the same response: output tokens are final here
                                pass
                            if not isinstance(content, list):
                                continue
                            for b in content:
                                if not isinstance(b, dict) or b.get('type') != 'tool_use':
                                    continue
                                S.tool_uses += 1
                                name = b.get('name') or '?'
                                inp = b.get('input') or {}
                                C['tool uses'][name] += 1
                                info = {'name': name, 'skey': skey, 'group': group}
                                if name == 'Skill':
                                    sk = str(inp.get('skill', '')).split(':')[-1]
                                    pref = str(inp.get('skill', '')).split(':')[0] if ':' in str(inp.get('skill', '')) else '<none>'
                                    if sk in skills:
                                        C['skill invoked (Skill tool)'][sk] += 1
                                        C['skill invoked by group'][(sk, group)] += 1
                                        C['skill plugin prefix'][pref if REPO_GROUP_RE.search(pref) or pref == '<none>' else '<other prefix>'] += 1
                                        C['skill plugin prefix per week'][(iso_week(ts), 'agentic-github-flow-*' if pref.startswith('agentic-github-flow') else pref if pref == '<none>' else '<other prefix>')] += 1
                                        skill_weeks[sk][iso_week(ts)] += 1
                                        if sk == 'issue-handover':
                                            S.handovers += 1
                                            S.ho_skill += 1
                                    else:
                                        C['other skills invoked (count only)']['other'] += 1
                                    info['skill'] = sk
                                elif name == 'Read':
                                    fp = str(inp.get('file_path', ''))
                                    mm = skill_ref_re.search(fp)
                                    if mm and mm.group(1) in skills:
                                        C['skill file read'][(mm.group(1), mm.group(2))] += 1
                                        if mm.group(2) == 'SKILL.md':
                                            skill_weeks[mm.group(1) + ' (Read)'][iso_week(ts)] += 1
                                elif name == 'AskUserQuestion':
                                    S.questions += 1
                                    for q in inp.get('questions') or []:
                                        if isinstance(q, dict) and q.get('header'):
                                            h = str(q['header'])
                                            C['AskUserQuestion header class'][
                                                'landing/cleanup (push, merge, archive, clean up)' if HEADER_LANDING.search(h) else
                                                'names an issue number' if h.lstrip().startswith('#') else
                                                'other (project content; text not printed)'] += 1
                                elif name == 'Bash':
                                    cmd = str(inp.get('command', ''))
                                    info['cmd'] = cmd
                                    info['shape'] = cmd_shape(cmd)
                                    info['dds'] = bool(inp.get('dangerouslyDisableSandbox'))
                                    info['classes'] = chain_classes(cmd)
                                    mentioned = [s for s, r in script_res.items() if s in cmd and r.search(cmd)]
                                    info['scripts'] = run_scripts(cmd, mentioned) if mentioned else []
                                    for s in mentioned:
                                        if s not in info['scripts']:
                                            C['script mentioned, not run (read/grep/test)'][s] += 1
                                    for s in info['scripts']:
                                        C['script runs'][s] += 1
                                        C['script runs by group'][(s, group)] += 1
                                        C['script-run weeks'][iso_week(ts)] += 1
                                        if s in ('start_issue_chat.py', 'handover_note.py'):
                                            S.handovers += 1
                                        if s == 'handover_note.py':
                                            S.ho_note += 1
                                        if '.agentic-github-flow' in cmd or '/.claude/plugins/' in cmd:
                                            C['script run from'][(s, 'installed plugin')] += 1
                                        elif 'agentic-github-flow' in cmd:
                                            C['script run from'][(s, 'repository checkout')] += 1
                                        elif 'agent-rules' in cmd:
                                            C['script run from'][(s, 'agent-rules (predecessor)')] += 1
                                        else:
                                            C['script run from'][(s, 'other/relative')] += 1
                                    C['bash total'][group] += 1
                                    C['bash calls per week'][iso_week(ts)] += 1
                                    if info['dds']:
                                        C['dangerouslyDisableSandbox by shape'][info['shape']] += 1
                                        C['dangerouslyDisableSandbox total'][group] += 1
                                        C['dangerouslyDisableSandbox per week'][iso_week(ts)] += 1
                                    for k in info['classes']:
                                        C['network class calls'][k] += 1
                                        if info['dds']:
                                            C['network class escaped at once'][k] += 1
                                    prev = last_bash.setdefault(skey, [])
                                    if prev and prev[-1].get('cmd') == cmd:
                                        C['repeated identical Bash command (consecutive)'][info['shape']] += 1
                                        if prev[-1].get('dds') != info['dds']:
                                            C['identical command, sandbox flag flipped']['count'] += 1
                                    info['prev'] = prev[-3:]
                                    prev.append(info)
                                    if len(prev) > 5:
                                        del prev[0]
                                elif name in ('Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
                                    pass
                                bid = b.get('id')
                                if bid:
                                    tool_index[bid] = info
                            continue
                        # user entries
                        if isinstance(content, str):
                            mm = re.search(r'<command-name>/?([\w:-]+)</command-name>', content)
                            if mm:
                                sk = mm.group(1).split(':')[-1]
                                if sk in skills:
                                    C['skill invoked (slash command)'][sk] += 1
                                    skill_weeks[sk + ' (slash)'][iso_week(ts)] += 1
                            if o.get('isCompactSummary') or content.startswith(COMPACT_TEXT):
                                C['compact summaries'][group] += 1
                            continue
                        if not isinstance(content, list):
                            continue
                        if o.get('isCompactSummary'):
                            C['compact summaries'][group] += 1
                        pd = o.get('permissionDecision') if isinstance(o.get('permissionDecision'), dict) else {}
                        tdk = o.get('toolDenialKind')
                        sv = o.get('sandboxViolations') or []
                        for b in content:
                            if not isinstance(b, dict):
                                continue
                            if b.get('type') == 'text':
                                mm = re.search(r'<command-name>/?([\w:-]+)</command-name>', b.get('text', ''))
                                if mm:
                                    sk = mm.group(1).split(':')[-1]
                                    if sk in skills:
                                        C['skill invoked (slash command)'][sk] += 1
                                        skill_weeks[sk + ' (slash)'][iso_week(ts)] += 1
                                if (b.get('text') or '').startswith(COMPACT_TEXT):
                                    C['compact summaries (text)'][group] += 1
                                continue
                            if b.get('type') != 'tool_result':
                                continue
                            info = tool_index.pop(b.get('tool_use_id'), None) or {'name': '?'}
                            name = info['name']
                            text = result_text(b)
                            err = bool(b.get('is_error'))
                            C['tool results'][name] += 1
                            if err:
                                C['tool errors'][name] += 1
                            shape = info.get('shape')
                            # permission
                            src = pd.get('source')
                            if tdk:
                                C['toolDenialKind x decision source'][(tdk, src)] += 1
                                if src != 'hook':  # hook refusals are counted under the guards
                                    C['denial (not by a hook) by tool/shape'][(tdk, name, shape or '-')] += 1
                            if src:
                                C['permissionDecision source x reasonType'][(src, pd.get('reasonType'), pd.get('decision'))] += 1
                                C['permissionDecision source'][(src, pd.get('decision'))] += 1
                                # a prompt shown now: user_temporary / user_reject, or user_permanent
                                # without a matched rule (the "always allow" answer); AskUserQuestion
                                # is the question itself, not a permission prompt
                                if name != 'AskUserQuestion' and (src in ('user_temporary', 'user_reject') or
                                        (src == 'user_permanent' and not pd.get('reasonType'))):
                                    C['permission prompt answered by user, by tool/shape'][(src, name, shape or '-')] += 1
                                    C['permission prompts total'][(group, src)] += 1
                                if src == 'hook':
                                    C['hook decision'][(pd.get('decision'), name)] += 1
                                if pd.get('reasonType') == 'classifier' and pd.get('decision') == 'reject':
                                    C['classifier rejected'][(name, shape or '-')] += 1
                            if err and REJECT_RE.search(text[:400]):
                                C['rejected/denied text'][(name, shape or '-')] += 1
                            # guards: a hook decision (permissionDecision.source == "hook") named by
                            # the guard's message; the message alone also appears in test output
                            glabel = next((lb for lb, nd in GUARDS if nd in text), None)
                            if glabel:
                                C['guard message anywhere (incl. tests, --check runs)'][glabel] += 1
                            if src == 'hook' or pd.get('reasonType') == 'hook':
                                C['hook decision by guard'][(glabel or 'unidentified hook', src, pd.get('decision'), name)] += 1
                                if pd.get('decision') == 'reject' and name == 'Bash':
                                    info['blocked_by'] = glabel or 'unidentified hook'
                                    C['hook block by shape'][(glabel or 'unidentified hook', shape)] += 1
                                if pd.get('decision') == 'reject':
                                    C['hook block reason'][(glabel or 'unidentified hook', guard_reason(glabel, text))] += 1
                                    if not glabel:
                                        head = re.sub(r'\S*[/~@\d_`"\'#]\S*', '<x>', text.strip()[:60]).split()[:5]
                                        C['unidentified hook block, first words'][(name, ' '.join(head))] += 1
                            if 'hook' in text[:200].lower() and err:
                                C['other hook error results'][name] += 1
                            # sandbox
                            if name == 'Bash':
                                sbx = bool(sv) or (err and SANDBOX_RE.search(text[:3000]))
                                if sbx:
                                    C['sandbox failure by shape'][shape] += 1
                                    C['sandbox failure total'][info['group']] += 1
                                    for k in info.get('classes', ()):
                                        C['network class sandbox failures'][k] += 1
                                    info['sbx_fail'] = True
                                if sv:
                                    C['sandboxViolations entries']['results with violations'] += 1
                                if o.get('sandboxed') is True:
                                    C['bash sandboxed flag']['sandboxed'] += 1
                                elif o.get('sandboxed') is False:
                                    C['bash sandboxed flag']['not sandboxed'] += 1
                                if info.get('dds'):
                                    prevs = info.get('prev') or []
                                    if any(p.get('sbx_fail') for p in prevs[-2:]):
                                        C['escape after a sandbox failure'][shape] += 1
                                        C['escape after a sandbox failure total']['count'] += 1
                                    else:
                                        C['escape at once (no sandbox failure just before)']['count'] += 1
                                if err:
                                    C['bash error by shape'][shape] += 1
                                    info['err'] = True
                                    prevs = info.get('prev') or []
                                for s in info.get('scripts', ()):
                                    if err:
                                        C['script errors'][s] += 1
                                        mx = re.search(r'Exit code (\d+)', text[:200])
                                        why = ('sandbox' if info.get('sbx_fail') else
                                               'hook block' if info.get('blocked_by') else
                                               'permission denied' if tdk else 'other')
                                        C['script error class'][(s, 'exit ' + (mx.group(1) if mx else '?'), why)] += 1
                                # retried after a guard block / an error
                                prevs = info.get('prev') or []
                                if prevs:
                                    p = prevs[-1]
                                    if p.get('blocked_by'):
                                        C['next Bash after guard block'][(p['blocked_by'],
                                            'same command' if p.get('cmd') == info.get('cmd') else
                                            'same shape, changed' if p.get('shape') == shape else 'other command')] += 1
                                    if p.get('err'):
                                        C['next Bash after a Bash error'][
                                            'identical retry' if p.get('cmd') == info.get('cmd') else
                                            'same shape, changed' if p.get('shape') == shape else 'other command'] += 1
                            elif name in ('Edit', 'Write', 'MultiEdit') and err:
                                for label, rx in EDIT_ERRORS:
                                    if rx.search(text[:500]):
                                        C['edit failure class'][(name, label)] += 1
                                        break
                                else:
                                    C['edit failure class'][(name, 'other')] += 1
                            if name == 'AskUserQuestion':
                                pass
                # end file

    # ---- aggregate sessions ----
    main_s = [s for s in sessions.values() if not s.is_sub and s.ctx]
    sub_s = [s for s in sessions.values() if s.is_sub and s.ctx]
    R = {'window': [since, until], 'files_read': files_read, 'lines_parsed': lines_read,
         'main_sessions': len(main_s), 'subagent_transcripts': len(sub_s),
         'project_labels': sorted(set(labels.values()))}

    def kind(s):
        if s.entry and s.entry.startswith('sdk'):
            return 'headless (claude -p / SDK)'
        if len(s.ctx) <= 3:
            return 'short probe (<=3 API calls)'
        if s.issue_chat:
            return ('repo issue chat' if s.group == 'repo' else 'other issue chat')
        return 'repo other session' if s.group == 'repo' else 'other session'

    def model_of(s):
        return s.models.most_common(1)[0][0] if s.models else '?'

    ctxstats = collections.defaultdict(list)
    for s in main_s:
        ctxstats[(model_of(s), 'all')].append(max(s.ctx))
    R['peak context per main session by model'] = {
        m: {'n': len(v), 'median': statistics.median(v), 'p90': pct(v, 90), 'max': max(v),
            '>200k': sum(x > 200_000 for x in v), '>300k': sum(x > 300_000 for x in v),
            '>600k': sum(x > 600_000 for x in v)}
        for (m, _), v in sorted(ctxstats.items()) if len(v) >= 3}
    by_kind = collections.defaultdict(list)
    for s in main_s:
        by_kind[kind(s)].append(max(s.ctx))
    R['peak context by session kind'] = {k: {'n': len(v), 'median': statistics.median(v), 'p90': pct(v, 90),
                                             'max': max(v), '>200k': sum(x > 200_000 for x in v),
                                             '>300k': sum(x > 300_000 for x in v)} for k, v in sorted(by_kind.items())}
    start = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in main_s:
        k = (kind(s), model_of(s))
        start[k]['call1'].append(s.ctx[0])
        if len(s.ctx) > 1:
            start[k]['call2'].append(s.ctx[1])
        if s.ctx_after10 is not None:
            start[k]['after10tools'].append(s.ctx_after10)
    R['start cost (median context)'] = {
        '%s | %s' % k: {p: {'n': len(v), 'median': statistics.median(v), 'p90': pct(v, 90)} for p, v in d.items() if v}
        for k, d in sorted(start.items()) if len(d['call1']) >= 3}
    R['sessions with a compaction'] = collections.Counter(kind(s) for s in main_s if s.compactions)
    R['compactions total'] = sum(s.compactions for s in sessions.values())
    R['sessions with handover activity'] = collections.Counter(kind(s) for s in main_s if s.handovers)
    R['sessions that invoked issue-handover'] = collections.Counter(kind(s) for s in main_s if s.ho_skill)
    R['sessions that ran handover_note.py'] = collections.Counter(kind(s) for s in main_s if s.ho_note)
    R['sessions that got a context-limit note'] = collections.Counter(
        kind(sessions[p]) for p in ctxnote_files if p in sessions and not sessions[p].is_sub and sessions[p].ctx)
    R['entrypoints of main sessions'] = collections.Counter(s.entry for s in main_s)
    vol = collections.defaultdict(collections.Counter)
    for s in main_s:
        vol[iso_week(s.start)][kind(s)] += 1
    R['main sessions per week by kind'] = {w: dict(c) for w, c in sorted(vol.items())}
    subvol = collections.Counter(iso_week(s.start) for s in sub_s)
    R['subagent transcripts per week'] = dict(sorted(subvol.items()))
    tok = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in main_s:
        tok[kind(s)]['output'].append(s.out_tokens)
        tok[kind(s)]['cache_read'].append(s.cache_read)
        tok[kind(s)]['api_calls'].append(len(s.ctx))
    for s in sub_s:
        tok['subagent']['output'].append(s.out_tokens)
        tok['subagent']['cache_read'].append(s.cache_read)
        tok['subagent']['api_calls'].append(len(s.ctx))
    R['tokens per session'] = {k: {m: {'median': statistics.median(v), 'p90': pct(v, 90), 'sum': sum(v)}
                                   for m, v in d.items()} for k, d in sorted(tok.items())}
    by_label = collections.Counter(s.project for s in main_s)
    R['main sessions by project label'] = dict(by_label.most_common())
    ask = collections.Counter()
    for s in main_s:
        ask[min(s.questions, 10)] += 1
    R['AskUserQuestion calls per main session (10 = 10+)'] = dict(sorted(ask.items()))
    R['AskUserQuestion total'] = sum(s.questions for s in sessions.values())
    R['skill weeks'] = {k: dict(sorted(v.items())) for k, v in sorted(skill_weeks.items())}
    R['skills never invoked'] = sorted(s for s in skills if not C['skill invoked (Skill tool)'][s]
                                       and not C['skill invoked (slash command)'][s])
    R['skills never invoked nor read'] = sorted(s for s in R['skills never invoked']
                                                if not any(k[0] == s for k in C['skill file read']))
    R['scripts never run from Bash'] = sorted(s for s in scripts if not C['script runs'][s])
    R['hook scripts (hooks.json)'] = sorted(hook_scripts)
    R['skills'] = skills
    R['counters'] = {k: [[list(x) if isinstance(x, tuple) else x, n] for x, n in v.most_common()]
                     for k, v in C.items()}
    if a.json:
        json.dump(R, sys.stdout, indent=1, default=lambda x: dict(x) if isinstance(x, collections.Counter) else str(x))
    else:
        for k, v in R.items():
            if k == 'counters':
                for ck, cv in v.items():
                    print('\n## ' + ck)
                    for x, n in cv[:40]:
                        print('  %6d  %s' % (n, x))
            else:
                print('\n## ' + k)
                print(json.dumps(v, indent=1, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
