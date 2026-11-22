#!/usr/bin/env python3
"""PreToolUse hook: refuse the git commands the core rules' §Git forbids, in any spelling.

Both clients call a PreToolUse command hook the same way: one JSON object on stdin with
`tool_input.command`, exit code 2 plus a reason on stderr to block. This closes what command-text
rules cannot see (a flag after another argument, `git -C <dir> …`, a command inside
`zsh -lc "…"`, `env X=y git …`): the Codex prefix rules miss those, and Claude's deny rules miss
some of them.

It parses the command into simple commands, unwraps shell `-c` strings, `eval`, `ssh`, command
substitutions and wrappers such as `timeout`, and judges every `git` invocation by its subcommand
and flags, wherever they stand. It is a guardrail, not a boundary: git started from a script
file or built from variables is not seen, and `git checkout <path>` cannot be told from
`git checkout <branch>`. An input it cannot parse passes, except where the parse would hide git:
it blocks, rather than guesses, a command that may run git and is longer than MAX_INPUT
characters, holds an unquoted brace expansion (`git push origin {-f,main}`), an ANSI-C string it
cannot decode (`$'…'` strings are decoded first), or is nested deeper than MAX_DEPTH (eval in
eval in …). Hook input that is JSON but not an object is blocked too. A command the user asks for
by name the user runs in their own terminal. Shell comments are removed before anything is
judged (`strip_comments`), and a commit's option values are never read as flags
(`commit_flags`): `git commit -m "--no-verify"` is a message, not a hook bypass.

Claude Code (`--claude`, #33): the same blocks, plus "ask" for what the user approves per call:
a push, `commit --amend`, `update-ref` and changing a remote, in any spelling. It replaces the
permission rules whose `*` could reach into a commit message (`git -C * clean*` stopped
`git -C r commit -m "a clean step"`); the rules left in policy/claude-permissions.json start
with `git <subcommand>`. A call is judged for blocks first, so a block anywhere in it wins over
an ask. Under `--claude`, git text the parser cannot read (an open quote) is asked. The guards
plugin's hooks.json runs it for Bash and for the terminal tool (`mcp__*__run_in_terminal`),
which gets no permission rules. tests/claude_git_rules.py checks the rules and this mode
together against the rules as they stood before #33.

How it fails in Claude Code, where the `git -C` spellings now rest on this hook alone: a missing
script makes Python exit 2, which blocks every Bash call; a crash before main() (a broken
import) exits 1, which Claude Code lets through unchecked. Errors inside main() pass on purpose
(below). Dropping the rules and wiring `--claude` ship together, in one plugin version.

pre_tool_personal_data.py and pre_tool_delete_guard.py reuse its shell parsing: run
tests/personal_data_guard.py and tests/delete_guard.py too.

Usage as a hook: reads JSON on stdin (`--claude` for Claude Code). For tests:
`pre_tool_git_guard.py [--claude] --check '<command>'` prints the reason and exits 2 for a
block, 3 for an ask (`--claude` only), or exits 0.
"""
import json, re, shlex, sys

SHELLS = {'sh', 'bash', 'zsh', 'dash', 'ksh'}
INTERPRETERS = {'python', 'python3', 'node', 'perl', 'ruby'}
KEYWORDS = {'then', 'do', 'else', 'elif', 'if', 'while', 'until', '!'}
WRAPPERS = {'env', 'command', 'builtin', 'exec', 'nohup', 'time', 'sudo', 'timeout', 'nice',
            'caffeinate', 'stdbuf', 'noglob', 'export', 'xargs', 'find'}
SEPARATORS = set(';&|(){}\n')
GIT_VALUE_OPTS = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--exec-path',
                  '--super-prefix', '--config-env'}
CONFIG_KEYS = ('core.hookspath', 'alias.', 'pull.rebase')
BLIND_PATHS = {'.', './', '*', ':/', ':/.', ':(top)', '..', '../'}
ASSIGN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*=.*', re.S)
HEREDOC = re.compile(r'<<(-?)\s*["\']?([A-Za-z_][A-Za-z0-9_]*)["\']?')
EXEC_HINT = re.compile(r'subprocess|system|popen|exec|spawn|check_output|check_call|`|%x')
MAX_INPUT = 32_000  # characters; a longer command that may run git is blocked, not parsed
MAX_DEPTH = 8
GIT_WORD = re.compile(r'(?<![\w.-])(?:git|gh)(?![\w-])|\bGIT_\w+', re.I)
ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)
ANSI_ESCAPES = {'a': '\a', 'b': '\b', 'e': '\x1b', 'E': '\x1b', 'f': '\f', 'n': '\n',
                'r': '\r', 't': '\t', 'v': '\v', '\\': '\\', "'": "'", '"': '"', '?': '?'}
COMMIT_VALUE_SHORT = set('mFcCt')  # -m <msg>, -F <file>, -c/-C <commit>, -t <template>
COMMIT_ATTACHED_SHORT = set('uS')  # -u<mode>, -S<keyid>: an optional value, attached only
COMMIT_VALUE_LONG = ('--message', '--file', '--reuse-message', '--reedit-message', '--template',
                     '--author', '--date', '--trailer', '--fixup', '--squash', '--cleanup',
                     '--pathspec-from-file')
COMMIT_FLAG_LONG = ('--amend', '--all', '--allow-empty', '--allow-empty-message', '--no-verify')
HOOK_RUNNERS = {'commit', 'push', 'merge', 'am', 'pull', 'rebase', 'cherry-pick', 'revert',
                'send-email'}  # the subcommands where --no-verify skips a hook


def split_commands(text):
    """Yield token lists, one per simple command."""
    lex = shlex.shlex(text, posix=True, punctuation_chars=';&|(){}\n')
    lex.whitespace = ' \t\r'
    lex.whitespace_split = True
    lex.commenters = ''
    current = []
    for tok in lex:
        if tok and set(tok) <= SEPARATORS:
            if current:
                yield current
            current = []
        else:
            current.append(tok)
    if current:
        yield current


def strip_comments(text):
    """The text without shell comments: an unquoted `#` at the start of a word, to the end of
    its line. Here-document bodies are copied as they are, without reading quotes in them. It
    runs before the here-document and substitution passes, so they see the same quoting as the
    shell: an apostrophe in `git -C r stash drop # don't` once left them an open quote, which
    hid the command (#33)."""
    lines, out, quote, i = text.split('\n'), [], None, 0
    while i < len(lines):
        line, kept, marks, k = lines[i], [], [], 0
        while k < len(line):
            c = line[k]
            if quote:
                kept.append(c)
                if c == '\\' and quote == '"' and k + 1 < len(line):
                    kept.append(line[k + 1])
                    k += 1
                elif c == quote:
                    quote = None
            elif c == '\\' and k + 1 < len(line):
                kept.append(line[k:k + 2])
                k += 1
            elif c in '"\'':
                quote = c
                kept.append(c)
            elif c == '#' and (k == 0 or line[k - 1] in ' \t;&|()'):
                break
            elif line.startswith('<<', k) and not line.startswith('<<<', k) and HEREDOC.match(line, k):
                m = HEREDOC.match(line, k)
                marks.append(m.groups())
                kept.append(line[k:m.end()])
                k = m.end()
                continue
            else:
                kept.append(c)
            k += 1
        out.append(''.join(kept))
        i += 1
        for dash, word in marks:  # the body, verbatim, up to its closing line
            while i < len(lines):
                out.append(lines[i])
                i += 1
                if (lines[i - 1].lstrip('\t') if dash else lines[i - 1]) == word:
                    break
    return '\n'.join(out)


def strip_heredocs(text):
    """Return the text without here-document bodies, and (command line, body) pairs.

    A body is data for the command that reads it, so it is judged only when that command is a
    shell or an interpreter. A marker without its closing line is left in place, and `<<`
    inside quotes or after a backslash is text, not a marker.
    """
    lines, out, bodies, i, quote = text.split('\n'), [], [], 0, None
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        marks, k = [], 0
        while k < len(line):
            c = line[k]
            if quote == "'":
                quote = None if c == "'" else quote
            elif c == '\\':
                k += 1
            elif c in '"\'' and quote in (None, c):
                quote = None if quote else c
            elif quote is None and line.startswith('<<', k):
                m = None if line.startswith('<<<', k) else HEREDOC.match(line, k)
                if m:
                    marks.append(m.groups())
                k += 2 if not m else m.end() - k - 1
                while line.startswith('<', k + 1):
                    k += 1
            k += 1
        for dash, word in marks:
            j = i
            while j < len(lines) and (lines[j].lstrip('\t') if dash else lines[j]) != word:
                j += 1
            if j == len(lines):
                continue
            bodies.append((line, '\n'.join(lines[i:j])))
            i = j + 1
    return '\n'.join(out), bodies


def substitutions(text):
    """Texts the shell runs as commands inside `…` and $(…), also within double quotes."""
    found, i, n, quote = [], 0, len(text), None
    while i < n:
        c = text[i]
        if quote == "'":
            if c == "'":
                quote = None
        elif c == '\\':
            i += 1
        elif c == "'" and quote is None:
            quote = "'"
        elif c == '"':
            quote = None if quote else '"'
        elif c == '`':
            j = text.find('`', i + 1)
            if j < 0:
                break
            found.append(text[i + 1:j])
            i = j
        elif c == '$' and text[i + 1:i + 2] == '(' and text[i + 2:i + 3] != '(':
            depth, j = 1, i + 2
            while j < n and depth:
                depth += (text[j] == '(') - (text[j] == ')')
                j += 1
            found.append(text[i + 2:j - 1] if depth == 0 else text[i + 2:j])
            i = j - 1
        i += 1
    return found


def base(word):
    return word.rsplit('/', 1)[-1]


def has_short(args, letter):
    """True if a short-flag cluster such as -am contains the letter."""
    return any(re.fullmatch(r'-[A-Za-z]+', a) and letter in a[1:] for a in args)


def has_long(args, *names):
    """True if an argument is one of these long options or a prefix of one: git accepts
    `--har` for `--hard`."""
    for a in args:
        stem = a.split('=', 1)[0]
        if stem.startswith('--') and len(stem) >= 3 and any(n.startswith(stem) for n in names):
            return True
    return False


def decode_ansi_c(body):
    """The text of a bash $'…' string, or None when an escape is not one bash defines."""
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c != '\\':
            out.append(c)
            i += 1
            continue
        nxt = body[i + 1:i + 2]
        if nxt in ANSI_ESCAPES:
            out.append(ANSI_ESCAPES[nxt])
            i += 2
            continue
        m = (re.match(r'[0-7]{1,3}', body[i + 1:]) or
             re.match(r'x([0-9A-Fa-f]{1,2})', body[i + 1:]) or
             re.match(r'u([0-9A-Fa-f]{1,4})', body[i + 1:]) or
             re.match(r'U([0-9A-Fa-f]{1,8})', body[i + 1:]))
        if m:
            digits = m.group(1) if m.groups() else m.group(0)
            try:
                out.append(chr(int(digits, 8 if not m.groups() else 16)))
            except (ValueError, OverflowError):
                return None
            i += 1 + m.end()
            continue
        if nxt == 'c' and i + 2 < len(body):
            out.append(chr(ord(body[i + 2]) & 0x1f))
            i += 3
            continue
        return None
    return ''.join(out)


def unquote_ansi_c(text):
    """(text with every $'…' replaced by its decoded, single-quoted value, ok)."""
    ok = True

    def plain(m):
        nonlocal ok
        value = decode_ansi_c(m.group(1))
        if value is None:
            ok = False
            return m.group(0)
        return shlex.quote(value)
    return ANSI_C.sub(plain, text), ok


def brace_expansion(text):
    """True when text holds an unquoted brace expansion: {a,b} or {1..3}, not ${x} or @{1}."""
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
                return True
        i += 1
    return False


def may_run_git(text):
    """True when git or gh can appear as a command word, or a GIT_ variable is set, once quotes,
    escapes and braces are resolved; everything else is no business of this guard. Only whole
    words count, so `src/{high,low}`, `night.txt{,.bak}` and `.github/{a,b}` are not git."""
    return "$'" in text or any(GIT_WORD.search(re.sub(r'[\'"\\{},$]', gap, text))
                               for gap in ('', ' '))  # g''it, and -S'git …'


def commit_flags(rest):
    """The flags of `git commit`, without option values: a message is never a flag, also when
    it is attached (`-mnote`) or looks like one (`-m "--amend"`)."""
    flags, i = [], 0
    while i < len(rest):
        a = rest[i]
        if a == '--':
            break
        if a.startswith('--'):
            name = a.split('=', 1)[0]
            flags.append(a)
            if '=' not in a and len(name) >= 4 and any(v.startswith(name) for v in COMMIT_VALUE_LONG) \
                    and not any(f.startswith(name) for f in COMMIT_FLAG_LONG):
                i += 1  # its value is the next word
        elif a.startswith('-') and a != '-':
            kept = ''
            for j, c in enumerate(a[1:]):
                kept += c
                if c in COMMIT_ATTACHED_SHORT:
                    break
                if c in COMMIT_VALUE_SHORT:
                    if j == len(a) - 2:
                        i += 1  # the value is the next word
                    break
            flags.append('-' + kept)
        i += 1
    return flags


def judge_git(args):
    """args: tokens after `git`. Return a reason string or None."""
    i, config = 0, []
    while i < len(args) and args[i].startswith('-'):
        opt = args[i]
        if opt in GIT_VALUE_OPTS:
            if opt in ('-c', '--config-env') and i + 1 < len(args):
                config.append(args[i + 1])
            i += 2
        else:
            if opt.startswith('--config-env='):
                config.append(opt.split('=', 1)[1])
            i += 1
    for c in config:
        if c.lower().startswith(CONFIG_KEYS):
            return 'overrides git configuration for one command (-c %s)' % c.split('=')[0]
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if rest[:1] == ['--help'] or rest == ['-h']:
        return None
    opts = [a for a in rest if a.startswith('-')]
    before_dd = rest[:rest.index('--')] if '--' in rest else rest
    flags = commit_flags(rest) if sub == 'commit' else [a for a in before_dd if a.startswith('-')]
    words = [a for a in before_dd if not a.startswith('-')]

    if sub in HOOK_RUNNERS and any(f.startswith('--no-v') and '--no-verify'.startswith(f)
                                   for f in flags):
        return 'bypasses a hook (--no-verify)'
    if sub == 'push':
        if has_short(flags, 'f') or has_long(flags, '--force', '--force-with-lease',
                                             '--force-if-includes', '--mirror', '--prune'):
            return 'force-pushes or prunes the remote'
        after = rest[rest.index('--') + 1:] if '--' in rest else []
        if any(a.startswith('+') for a in words + after):
            return 'force-pushes a ref (+ref)'
    elif sub == 'pull':
        if has_short(flags, 'r') or (has_long(flags, '--rebase')
                                     and not any(f.endswith('=false') for f in flags)):
            return 'rewrites history (pull --rebase)'
    elif sub == 'reset':
        if has_long(flags, '--hard'):
            return 'discards work (reset --hard)'
    elif sub == 'clean':
        return 'deletes untracked files (clean)'
    elif sub == 'restore':
        if not (has_long(flags, '--staged') or has_short(flags, 'S')) \
                or has_long(flags, '--worktree') or has_short(flags, 'W'):
            return 'discards uncommitted work (restore)'
    elif sub == 'checkout':
        if has_short(flags, 'B'):
            return 'moves a branch (checkout -B)'
        if '--' in rest or has_long(flags, '--force') or has_short(flags, 'f') \
                or BLIND_PATHS & set(words):
            return 'discards uncommitted work (checkout)'
        creates = has_short(flags, 'b') or has_long(flags, '--orphan')
        if len(words) >= 2 and not creates:
            return 'overwrites files from another commit (checkout <ref> <path>)'
    elif sub == 'switch':
        if has_short(flags, 'f') or has_short(flags, 'C') \
                or has_long(flags, '--force', '--force-create', '--discard-changes'):
            return 'discards uncommitted work or moves a branch (switch)'
    elif sub == 'stash':
        if rest[:1] in (['drop'], ['clear']):
            return 'discards a stash'
    elif sub == 'rebase':
        return 'rewrites history (rebase)'
    elif sub == 'tag':
        if has_short(flags, 'd') or has_short(flags, 'f') or has_long(flags, '--delete', '--force'):
            return 'deletes or moves a tag'
    elif sub == 'branch':
        if any(has_short(flags, x) for x in 'DfMC') or has_long(flags, '--force'):
            return 'force-deletes or moves a branch'
    elif sub in ('filter-branch', 'filter-repo', 'replace'):
        return 'rewrites history (%s)' % sub
    elif sub == 'reflog':
        if rest[:1] in (['expire'], ['delete']):
            return 'destroys the reflog'
    elif sub == 'gc':
        if has_long(flags, '--prune'):
            return 'prunes unreachable objects'
    elif sub == 'prune':
        return 'prunes unreachable objects'
    elif sub == 'update-ref':
        if has_short(flags, 'd') or has_long(flags, '--delete'):
            return 'deletes a ref'
    elif sub == 'worktree':
        if rest[:1] == ['remove']:
            return 'removes a worktree by hand (use the cleanup-merged skill\'s script)'
        if rest[:1] == ['add'] and has_short(flags, 'B'):
            return 'moves a branch (worktree add -B)'
    elif sub == 'commit':
        if has_short(flags, 'n'):
            return 'bypasses a hook (commit -n)'
        if has_short(flags, 'a') or has_long(flags, '--all'):
            return 'stages everything (commit -a)'
    elif sub == 'add':
        if has_short(flags, 'A') or has_short(flags, 'f') or has_long(flags, '--all', '--force'):
            return 'stages blindly or past the ignore list (add -A/-f)'
        if BLIND_PATHS & set(a for a in rest if not a.startswith('-')):
            return 'stages everything (add .)'
    elif sub == 'config':
        names = [a for a in rest if not a.startswith('-')]
        if has_short(opts, 'e') or has_long(opts, '--unset', '--unset-all', '--add', '--edit',
                                            '--replace-all', '--remove-section', '--rename-section'):
            return 'changes git configuration'
        if names[:1] and names[0] in ('set', 'unset', 'edit', 'rename-section', 'remove-section'):
            return 'changes git configuration'
        reads = names[:1] and names[0] in ('get', 'list')
        if not reads and not has_short(opts, 'l') and len(names) >= 2 and not has_long(
                opts, '--get', '--get-all', '--get-regexp', '--get-urlmatch', '--list'):
            return 'changes git configuration'
    return None


ASKING = False  # set by judge_ask(): judge_command then reports ask_git() reasons


def ask_git(args):
    """args: tokens after `git`. The reason the user is asked first (Claude Code), or None."""
    i = 0
    while i < len(args) and args[i].startswith('-'):
        i += 2 if args[i] in GIT_VALUE_OPTS else 1
    if i >= len(args):
        return None
    sub, rest = args[i], args[i + 1:]
    if rest[:1] == ['--help'] or rest == ['-h']:
        return None
    flags = commit_flags(rest) if sub == 'commit' else \
        [a for a in (rest[:rest.index('--')] if '--' in rest else rest) if a.startswith('-')]
    if sub == 'push':
        return 'pushes to a remote'
    if sub == 'commit' and has_long(flags, '--amend'):
        return 'amends a commit (commit --amend)'
    if sub == 'update-ref':
        return 'moves a ref (update-ref)'
    if sub == 'remote' and rest[:1] in (['add'], ['set-url'], ['remove'], ['rm'], ['rename']):
        return 'changes a remote (remote %s)' % rest[0]
    return None


def judge_ask(text):
    """The ask reason for a command that judge() lets through, or None."""
    global ASKING
    ASKING = True
    try:
        return judge(text)
    finally:
        ASKING = False


def judge_command(tokens, depth):
    """Judge one simple command, given as tokens."""
    while tokens and (ASSIGN.fullmatch(tokens[0]) or base(tokens[0]) in KEYWORDS):
        if tokens[0].startswith('GIT_CONFIG'):
            return 'changes git configuration through the environment'
        tokens = tokens[1:]
    if not tokens:
        return None
    if depth > MAX_DEPTH:
        return 'is nested too deeply to check'
    name = base(tokens[0])
    if name == 'git':
        return ask_git(tokens[1:]) if ASKING else judge_git(tokens[1:])
    if name == 'gh':
        if tokens[1:2] in (['config'], ['alias']) and tokens[2:3] in (
                ['set'], ['delete'], ['import'], ['clear-cache']):
            return 'changes gh configuration'
    elif name in SHELLS:
        for j, tok in enumerate(tokens[1:], 1):
            if re.fullmatch(r'-[a-z]*c[a-z]*', tok) and j + 1 < len(tokens):
                return judge(tokens[j + 1], depth + 1)
            if tok.startswith('<<<'):
                return judge(tok[3:] or ' '.join(tokens[j + 1:j + 2]), depth + 1)
    elif name in INTERPRETERS:
        for j, tok in enumerate(tokens[1:], 1):
            if tok in ('-c', '-e') and j + 1 < len(tokens):
                return judge_raw(tokens[j + 1], needs_exec=True)
    elif name == 'eval':
        return judge(' '.join(tokens[1:]), depth + 1)
    elif name == 'ssh':
        for j, tok in enumerate(tokens[1:], 1):
            if 'git' in tok:
                return judge(' '.join(tokens[j:]), depth + 1)
    elif name in WRAPPERS:
        runs = SHELLS | INTERPRETERS | WRAPPERS | {'git', 'eval', 'ssh'}
        for j, tok in enumerate(tokens[1:], 1):
            if name == 'env' and (tok in ('-S', '--split-string') or
                                  tok.startswith(('-S', '--split-string='))):
                if tok in ('-S', '--split-string'):  # env -S 'git …' splits its argument
                    split, after = ' '.join(tokens[j + 1:j + 2]), tokens[j + 2:]
                elif tok.startswith('--split-string='):
                    split, after = tok.split('=', 1)[1], tokens[j + 1:]
                else:
                    split, after = tok[2:], tokens[j + 1:]
                return judge(' '.join([split] + [shlex.quote(t) for t in after]), depth + 1)
            if ASSIGN.fullmatch(tok) and tok.startswith('GIT_CONFIG'):
                return 'changes git configuration through the environment'
            if base(tok) in runs:
                return judge_command(tokens[j:], depth + 1)
    return None


def judge(text, depth=0):
    if depth > MAX_DEPTH:
        return 'is nested too deeply to check'
    text, decoded = unquote_ansi_c(text)
    if not decoded and may_run_git(text):
        return "holds a $'…' string the guard cannot decode"
    text = strip_comments(text.replace('\\\n', ' '))
    if brace_expansion(text) and may_run_git(text):
        return 'uses brace expansion, which the guard cannot read safely'
    text, bodies = strip_heredocs(text)
    for line, body in bodies:
        readers = {base(w) for w in re.findall(r'[\w./-]+', line)}
        reason = judge(body, depth + 1) if readers & SHELLS else \
            judge_raw(body, needs_exec=True) if readers & INTERPRETERS else None
        if reason:
            return reason
    for inner in substitutions(text):
        reason = judge(inner, depth + 1)
        if reason:
            return reason
    try:
        commands = list(split_commands(text))
    except ValueError:
        if ASKING and re.search(r'\bgit\b', text):
            return 'cannot be read by the git guard (an open quote?)'
        return judge_raw(text)
    for tokens in commands:
        reason = judge_command(tokens, depth)
        if reason:
            return reason
        if base(tokens[0]) in SHELLS and all(t.startswith('-') for t in tokens[1:]):
            # a shell without a script reads its commands from a pipe: `echo git … | bash`
            reason = judge_raw(text)
            if reason:
                return reason
    return None


RAW = [  # each a sequence of patterns that must follow each other within one simple command
    ((r'git\b', r'\bpush\b', r'--force|\s-f\b|--mirror'), 'force-pushes'),
    ((r'git\b', r'\breset\b', r'--hard'), 'discards work (reset --hard)'),
    ((r'git\b', r'\bclean\b'), 'deletes untracked files (clean)'),
    ((r'git\b', r'--no-verify'), 'bypasses a hook (--no-verify)'),
    ((r'git\b', r'\b(rebase|filter-branch|filter-repo)\b'), 'rewrites history'),
    ((r'git\b', r'\bbranch\b', r'\s-D\b'), 'force-deletes a branch'),
    ((r'git\b', r'\bcheckout\b', r'\s--\s'), 'discards uncommitted work (checkout)'),
]
RAW = [(tuple(re.compile(p) for p in parts), reason) for parts, reason in RAW]
SEGMENT = re.compile(r'[^\n;|&]+')


def in_order(segment, patterns):
    """True when the patterns match one after another in segment. Each search starts where the
    previous match ended, so the time stays linear in the length of the text (one combined
    pattern with `[^…]*` between the parts backtracked for 20 s on 9 KB of input)."""
    pos = 0
    for pattern in patterns:
        found = pattern.search(segment, pos)
        if not found:
            return False
        pos = found.end()
    return True


def judge_raw(code, needs_exec=False):
    """Plain pattern search, for text shlex cannot parse and for code handed to an
    interpreter. Interpreter code is judged only when it can start a process: code that
    merely prints or compares such a string passes. Never used for asks."""
    if ASKING or needs_exec and not EXEC_HINT.search(code):
        return None
    for segment in SEGMENT.findall(code):
        if 'git' not in segment:
            continue
        for patterns, reason in RAW:
            if in_order(segment, patterns):
                return reason
    return None


def check(command):
    """The reason to block a command, or None."""
    if not may_run_git(command):
        return None
    if len(command) > MAX_INPUT:
        return 'is longer than %d characters, too long to check' % MAX_INPUT
    return judge(command)


def check_ask(command):
    """The reason to ask the user first (Claude Code), for a command check() lets through."""
    return judge_ask(command) if may_run_git(command) else None


def main():
    args = sys.argv[1:]
    claude = '--claude' in args
    if claude:
        args.remove('--claude')
    if len(args) == 2 and args[0] == '--check':
        command = args[1]
    else:
        try:
            event = json.load(sys.stdin)
        except ValueError:
            return 0
        if not isinstance(event, dict):
            sys.stderr.write('Blocked by the git guard: the hook input is not a JSON object.\n')
            return 2
        tool_input = event.get('tool_input') or {}
        command = tool_input.get('command') if isinstance(tool_input, dict) else None
        if isinstance(command, list):
            command = ' '.join(shlex.quote(str(c)) for c in command)
        if not isinstance(command, str):
            return 0
    try:
        reason = check(command)
        ask = check_ask(command) if claude and not reason else None
    except Exception:
        # Deliberate: a guard that fails on an input it cannot read must not stop all shell
        # work. The client rules and the written rules still apply to that command.
        return 0
    if ask:
        if args[:1] == ['--check']:
            print(ask)
            return 3
        json.dump({'hookSpecificOutput': {
            'hookEventName': 'PreToolUse', 'permissionDecision': 'ask',
            'permissionDecisionReason': 'git guard (agentic-github-flow rules, §Git): this '
                                        'command %s, which the user approves per call.' % ask}},
                  sys.stdout)
        return 0
    if not reason:
        return 0
    sys.stderr.write(
        'Blocked by the git guard (agentic-github-flow rules, §Git): this command %s. '
        'Use the safe form (git revert, an explicit path, the cleanup script), or ask the user: '
        'an operation the user asks for by name, the user runs in their own terminal.\n' % reason)
    return 2


if __name__ == '__main__':
    sys.exit(main())
