#!/usr/bin/env python3
"""PreToolUse hook: refuse the git commands the core rules' §Git forbids, in any spelling.

Both clients call a PreToolUse command hook the same way: one JSON object on stdin with
`tool_input.command`, exit code 2 plus a reason on stderr to block. This closes what command-text
rules cannot see (a flag after another argument, `git -C <dir> …`, a command inside
`zsh -lc "…"`, `env X=y git …`): the Codex prefix rules miss those, and Claude's deny rules miss
some of them.

It reads the command into simple commands, unwraps shell `-c` strings, `eval`, `trap`, `ssh`,
command substitutions and wrappers such as `timeout`, and judges every `git` invocation by its
subcommand and flags, wherever they stand. It is a guardrail, not a boundary: git started from a
script file or built from variables is not seen, and `git checkout <path>` cannot be told from
`git checkout <branch>`.

Exact where the reading is certain, the former rules where it is not (#33, the design of
2026-11-24, after ten review rounds each found a spelling a scanner of the whole shell language
read differently from the shell). The Reader knows a small part of the language, the part bash
(3.2 and later), zsh and sh read the same way, and reads nothing else: at a backtick, `$((`,
`$'…'`, `case`, a function, zsh's `>!`, `repeat` and `<->`, an `alias`, a backslash-newline
inside a token, a quote that does not close, it stops. The commands before
that point are judged by their words, which is exact: no rule word in a message or after
`--grep` stops a command, and a `;` splits only where the shell splits. From the start of the
command it stopped in to the end of the text, net() reads the text as Claude Code's former
permission rules did (every one of them, searched from any `git` on). So a text the reader
does not know is stopped whenever those rules stopped it, also a commit whose message names a
rule's words, and is never passed because of a misreading. That rest is also read a second
time by a Reader that skips what it does not know, so that what the words say still counts
there (a redirection between them, GIT_CONFIG_…, gh, an interpreter); a command it had to skip
in gets the belt (the maintainer, 2026-11-24): every subcommand word after its `git` is judged
as the subcommand, on its words and on its raw text (judge_loose). Both can only add a stop.
That second reading has a budget (Reader.over): past it the text is refused, because a hook
that runs out of its time stops nothing.
A word the text does not fix (`$x`, `$(…)`, `st$()ash`) is read with its unknown parts empty,
also as no word at all, `${x:-stash}`, `${@:-stash}` and `${x/a/stash}` also as `stash` (a
form of `${…}` it does not know is uncertain), an unquoted `$IFS` also as a split
(`git${IFS}stash${IFS}drop`), and a git command with one at or before its subcommand gets the
belt on its words. A here-document body is data, unless a shell or an interpreter reads it,
its delimiter is not quoted and it holds a substitution (the rules and the belt read it), or
a command in the text runs a text that is not in its own words (`eval "$(cat <<'EOF' … EOF)"`,
`sh <<< "$(…)"`, a shell reading a pipe): then every body is judged as a shell text. The reading was checked against the shells themselves: random texts
run in bash 3.2, zsh and dash with a `git` that logs its words, and every logged command the
guard refuses had to be stopped for its text (tools/fuzz_git_guard.py; not in the test gate,
it needs those shells).

Not covered: an interactive shell's own reading (history expansion with `!`, aliases, zsh
without comments, where the rest of a line after `#` is judged only as a text of its own),
a word a brace or a glob builds (`{g..g}it`, `git stash dro?`, zsh's `git (N) stash drop`), a
word a variable other than `$IFS` splits, and a script written to a file and run later
(`cat > x.sh <<'EOF' … EOF; sh x.sh`), which the former rules stopped by its body's text.
A command that may run git and is longer than MAX_INPUT characters, holds an unquoted brace
expansion in a git command (`git push origin {-f,main}`) or is nested deeper than MAX_DEPTH
(eval in eval in …) is blocked. Hook input that is JSON but not an object is blocked too. A
command the user asks for by name the user runs in their own terminal. A commit's option values
are never read as flags (`commit_flags`): `git commit -m "--no-verify"` is a message, not a
hook bypass. An option before the subcommand that is in neither GIT_VALUE_OPTS nor GIT_FLAG_OPTS
is judged both ways, as a flag and as `<option> <value>`, so a new git option cannot hide the
subcommand.

Claude Code (`--claude`, #33): the same blocks, plus "ask" for what the user approves per call:
a push, `commit --amend`, `update-ref` and changing a remote, in any spelling. It replaces the
permission rules whose `*` could reach into a commit message (`git -C * clean*` stopped
`git -C r commit -m "a clean step"`); the rules left in policy/claude-permissions.json start
with `git <subcommand>`. A call is judged for blocks first, so a block anywhere in it wins over
an ask. Under `--claude`, git text that ends inside an open quote is asked. The guards
plugin's hooks.json runs it for Bash and for the terminal tool (`mcp__*__run_in_terminal`),
which gets no permission rules. tests/claude_git_rules.py checks the rules and this mode
together against the rules as they stood before #33, each in some fifty spellings.

How it fails in Claude Code, where the `git -C` spellings now rest on this hook alone: a missing
script makes Python exit 2, which blocks every Bash call; a crash before main() (a broken
import) exits 1, which Claude Code lets through unchecked. Errors inside main() pass on purpose
(below); a fault inside the Reader does not: the text is then uncertain and goes to net().
Dropping the rules and wiring `--claude` ship together, in one plugin version.

pre_tool_personal_data.py and pre_tool_delete_guard.py reuse its older shell parsing
(split_commands, strip_heredocs, substitutions), which this guard itself no longer uses, and
pre_tool_merge_guard.py and pre_tool_sandbox_network.py its may_run_git: run
tests/personal_data_guard.py, tests/delete_guard.py, tests/merge_guard.py and
tests/sandbox_network_guard.py too.

Usage as a hook: reads JSON on stdin (`--claude` for Claude Code). For tests:
`pre_tool_git_guard.py [--claude] --check '<command>'` prints the reason and exits 2 for a
block, 3 for an ask (`--claude` only), or exits 0.
"""
import bisect, json, re, shlex, sys, time

SHELLS = {'sh', 'bash', 'zsh', 'dash', 'ksh'}
INTERPRETERS = {'python', 'python3', 'node', 'perl', 'ruby'}
KEYWORDS = {'then', 'do', 'else', 'elif', 'if', 'while', 'until', '!'}
WRAPPERS = {'env', 'command', 'builtin', 'exec', 'nohup', 'time', 'sudo', 'timeout', 'nice',
            'caffeinate', 'stdbuf', 'noglob', 'export', 'xargs', 'find'}
SEPARATORS = set(';&|(){}\n')
GIT_VALUE_OPTS = {'-C', '-c', '--git-dir', '--work-tree', '--namespace', '--exec-path',
                  '--super-prefix', '--config-env', '--attr-source'}
# git's options before the subcommand that take no separate value; any other one is read both
# ways, as a flag and as an option with a value, so a new option cannot hide the subcommand
GIT_FLAG_OPTS = {'-p', '--paginate', '-P', '--no-pager', '--bare', '--no-replace-objects',
                 '--no-lazy-fetch', '--no-optional-locks', '--no-advice', '--literal-pathspecs',
                 '--glob-pathspecs', '--noglob-pathspecs', '--icase-pathspecs', '-v',
                 '--version', '-h', '--help', '--html-path', '--man-path', '--info-path'}
CONFIG_KEYS = ('core.hookspath', 'alias.', 'pull.rebase')
BLIND_PATHS = {'.', './', '*', ':/', ':/.', ':(top)', '..', '../'}
ASSIGN = re.compile(r'[A-Za-z_][A-Za-z0-9_]*=.*', re.S)
# the marker as tests/fixtures/delete_guard_main.py reads it (that baseline stays as it was)
HEREDOC = re.compile(r'<<(-?)\s*\\?["\']?([A-Za-z_][A-Za-z0-9_]*)["\']?')
# a here-document marker: (dash, the delimiter as written); heredoc_word() gives the closing
# line, quotes and backslashes removed (`<<E\\OF`, `<<'EOF'`, `<<"E"OF` all close at EOF)
HEREDOC_MARK = re.compile(r'<<(-?)[ \t]*((?:[A-Za-z0-9_.-]|\\.|\'[^\'\n]*\'|"[^"\n]*")+)')
# arithmetic, where `<<` is a shift, not a here-document: $((1<<X)), (( y = 1 << X ))
ARITHMETIC = re.compile(r'\$?\(\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)\)')
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
# reads whose option values may be the word --no-verify (`git log --grep --no-verify`); on any
# other subcommand, an alias included (`git ci --no-verify`), the flag is refused
NO_HOOKS = {'log', 'show', 'grep', 'shortlog', 'rev-list', 'whatchanged', 'blame', 'diff',
            'status', 'describe', 'for-each-ref', 'ls-files', 'cat-file', 'rev-parse', 'help'}


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


def heredoc_word(written):
    """The closing line of a here-document whose delimiter is written so."""
    return re.sub(r'\\(.)|[\'"]', r'\1', written)


def heredoc_at(text, i, shifts):
    """(dash, closing line) of the here-document marker at i, or None: not `<<<`, nor a shift
    inside arithmetic. shifts: the sorted spans of ARITHMETIC in text."""
    k = bisect.bisect_right(shifts, (i, len(text) + 1)) - 1
    if text.startswith('<<<', i) or k >= 0 and shifts[k][0] < i < shifts[k][1]:
        return None
    m = HEREDOC_MARK.match(text, i)
    return m and (m.group(1), heredoc_word(m.group(2)))


def closing_tick(text, j):
    """Where the backtick substitution whose body starts at j closes, or -1: a backtick after
    a backslash does not close it."""
    while j < len(text):
        if text[j] == '\\':
            j += 2
            continue
        if text[j] == '`':
            return j
        j += 1
    return -1


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
        shifts = [m.span() for m in ARITHMETIC.finditer(line)] if '((' in line else []
        while k < len(line):
            c = line[k]
            if quote == "'":
                quote = None if c == "'" else quote
            elif c == '\\':
                k += 1
            elif c in '"\'' and quote in (None, c):
                quote = None if quote else c
            elif quote is None and line.startswith('<<', k):
                mark = heredoc_at(line, k, shifts)
                m = mark and HEREDOC_MARK.match(line, k)
                if m:
                    marks.append(mark)
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
    """Texts the shell runs as commands inside `…` and $(…), also within double quotes. In a
    backtick body the shell drops a backslash before ` $ or \\, so a nested `\\`git …\\`` runs."""
    return [re.sub(r'\\([`$\\])', r'\1', text[a:b]) if text[a - 1] == '`' else text[a:b]
            for a, b in substitution_spans(text)]


def substitution_spans(text):
    """(start, end) of the text inside each `…` and $(…)."""
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
            j = closing_tick(text, i + 1)
            if j < 0:
                break
            found.append((i + 1, j))
            i = j
        elif c == '$' and text[i + 1:i + 2] == '(' and text[i + 2:i + 3] != '(':
            j = closing_paren(text, i + 2)
            found.append((i + 2, j))
            i = j
        i += 1
    return found


def closing_paren(text, j):
    """Where the `$(` that opened before j closes (or len(text)): parentheses inside quotes,
    after a backslash or in a nested `$(…)` do not count. Linear: each character is read once,
    and without recursion, so no nesting depth can crash it."""
    n, stack, single = len(text), [1], False  # per level: the open parentheses, or '"'
    while j < n:
        c = text[j]
        if single:
            single = c != "'"
        elif c == '\\':
            j += 1
        elif stack[-1] == '"':
            if c == '"':
                stack.pop()
            elif text.startswith('$(', j):
                stack.append(1)
                j += 1
        elif c == '"':
            stack.append('"')
        elif c == "'":
            single = True
        elif c == '(':
            stack[-1] += 1
        elif c == ')':
            stack[-1] -= 1
            if not stack[-1]:
                stack.pop()
                if not stack:
                    return j
        j += 1
    return n


def base(word):
    return word.rsplit('/', 1)[-1]


SHORT = re.compile(r'-([A-Za-z0-9]+)')


def has_short(args, letter):
    """True if a short-flag cluster such as -am contains the letter, also one with a value
    attached (`git tag -fmv1.0`, `git push -f4`): the letters and digits after the `-`."""
    return any(letter in m.group(1) for m in (SHORT.match(a) for a in args) if m)


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
                out.append(chr(int(digits, 8) & 0xff if not m.groups() else int(digits, 16)))
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


def brace_expansion(text):
    """True when text holds an unquoted brace expansion: {a,b} or {1..3}, not ${x} or @{1}.
    One pass with a stack of the braces open in the current word, so the time stays linear
    (a scan per `{` took 18 s on 22,000 of them)."""
    quote, i, n, opened = None, 0, len(text), []  # per open brace: [after a $, holds , or ..]
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
        elif c in ' \t\n;|&':
            opened = []
        elif c == '{':
            opened.append([i > 0 and text[i - 1] == '$', False])
        elif c == '}' and opened:
            param, listed = opened.pop()
            if listed and not param:
                return True
        elif opened and (c == ',' or text.startswith('..', i)):
            opened[-1][1] = True
        i += 1
    return False


ENV_S_GLUED = re.compile(r'(?<![\w-])-[A-Za-z0-9]*S')


def may_run_git(text):
    """True when git or gh can appear as a command word, or a GIT_ variable is set, once quotes,
    escapes and braces are resolved; everything else is no business of this guard. Only whole
    words count, so `src/{high,low}`, `night.txt{,.bak}` and `.github/{a,b}` are not git."""
    if "$'" in text or re.search(r'[<>]&[ \t]*-git', text):  # >&-git: bash closes, runs git
        return True
    if 'git' in text and ENV_S_GLUED.search(text):  # env -vSgit …: -S with its text attached
        return True
    joined = text.replace('\\\n', '')  # g\<newline>it; in a comment the lines stay apart
    empty = EXPANSION.sub('', joined)  # g${x}it, $1git, gi"$x"t: an expansion that is empty
    filled = re.sub(r'\$\{\w*:{0,2}[-=+]', '', joined)  # ${:-git}: one that is its word
    return any(GIT_WORD.search(re.sub(r'[\'"\\{},$]', gap, form))
               for form in {text, joined, empty, filled} for gap in ('', ' '))  # g''it


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


def unknown_options(args):
    """How many options before the subcommand are in neither GIT_VALUE_OPTS nor GIT_FLAG_OPTS.
    Each is judged both ways, which doubles the work, so more than MAX_UNKNOWN are refused
    (git itself refuses them too)."""
    i, count = 0, 0
    while i < len(args) and args[i].startswith('-'):
        count += args[i] not in GIT_VALUE_OPTS | GIT_FLAG_OPTS and '=' not in args[i]
        i += 2 if args[i] in GIT_VALUE_OPTS else 1
    return count


MAX_UNKNOWN = 2


def judge_git(args):
    """args: tokens after `git`. Return a reason string or None."""
    if unknown_options(args) > MAX_UNKNOWN:
        return 'uses git options the guard does not know'
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
            if opt not in GIT_FLAG_OPTS and '=' not in opt:
                other = judge_git(args[:i] + args[i + 2:])  # read as `<opt> <value>`
                if other:
                    return other
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

    if sub not in NO_HOOKS and any(f.startswith('--no-v') and '--no-verify'.startswith(f)
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
    elif sub == 'restore':  # --staged too, as the Codex rules and Claude's `git restore *`
        if (has_long(flags, '--staged') or has_short(flags, 'S')) \
                and not (has_long(flags, '--worktree') or has_short(flags, 'W')):
            return 'discards staged changes (restore --staged; unstage with git reset -- <path>)'
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


ALT_OPEN, ALT_CLOSE = '\ue000', '\ue001'  # around the word of a ${x:-word}, inside the reader
ALT = re.compile('\ue000[^\ue001]*\ue001')
NUL_MARK = '\ue003'  # where a NUL ended a $'…' (the loose reading)
SPLIT = '\ue002'  # where an unquoted $IFS stands in a word: sh splits the word there


class Unsure(Exception):
    """The reader met text it does not read for certain."""


class Word(str):
    """A shell word as the reader read it: its literal text, with the parts the text does not
    fix (`$x`, `$(…)`) left out. known: every part is literal. one: it is exactly one word (an
    unquoted `$x` or a glob may be none or several). brace: an unquoted brace expansion."""
    known, one, brace, alt, pieces = True, True, False, None, None

    def __new__(cls, value, known=True, one=True, brace=False):
        alt = pieces = None
        if SPLIT in value:  # git${IFS}stash: the words it is when the expansion splits it
            pieces = ([p for p in ALT.sub('', value).split(SPLIT) if p],  # expansions empty
                      [p for p in value.replace(ALT_OPEN, '').replace(ALT_CLOSE, '').split(SPLIT)
                       if p])  # and a ${x:-word} as its word
            value = value.replace(SPLIT, '')
        if ALT_OPEN in value:  # ${x:-word}: read as nothing, and (alt) as word
            alt = value.replace(ALT_OPEN, '').replace(ALT_CLOSE, '')
            value = ALT.sub('', value)
        word = str.__new__(cls, value)
        word.known, word.one, word.brace, word.alt = known, one, brace, alt
        word.pieces = pieces
        return word


class Command:
    """One simple command: its words, the here-document bodies and here-strings it reads, and
    whether it is a shell that reads its script from standard input."""

    def __init__(self):
        self.words, self.bodies, self.strings, self.stdin = [], [], [], False
        self.both = False  # it has a `&>`: more words after it are another command in sh
        self.cond = False  # inside `[[`, before its `]]`
        self.closed = False  # after that `]]`
        self.runs = False  # it runs a text the guard cannot see (`eval "$(…)"`, `sh -c "$x"`)
        self.loose = False  # read past something unknown: its words are not certain
        self.span = None  # where such a command stands in the text


# characters that are themselves in a word, in every shell (a carriage return too: only blank,
# tab and newline end a word); a glob or a brace changes only the word's value, never its end
PLAIN = re.compile(r'[A-Za-z0-9_./:=@%+,^~\-{}\[\]*?!#\r\x80-\U0010ffff]+')
DQ_PLAIN = re.compile(r'[^"\\$`]+')
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
SUBSCRIPT = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\[')  # a[…]=: bash reads to the `]` on its own
# ${…} without a quote, a blank, a `$`, a backslash or a brace inside: it ends at the first `}`
PARAM = re.compile(r'\{([A-Za-z0-9_:#%/.,^@*!?+=~\[\]-]*)\}')
# ${x:-word}, ${x:+word}, ${@:-word}, ${!x:-word}, zsh's ${:-word}, and ${x/pattern/word}:
# the word may be the value
DEFAULT = re.compile(r'(?:!?[A-Za-z_0-9]*|[@*#?$!-]):{0,2}[-=+](.*)'
                     r'|(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*])//?[^/]*/(.*)')
# the other forms it reads, none of which can hold a word of the text: ${x}, ${1}, ${@},
# ${#x}, ${x%pattern}, ${x#pattern}, ${x:1:2}, ${x:?message}. Not read (Unsure): ${!x},
# zsh's ${+x}, ${=x}, ${x:s/a/b/}
PLAIN_PARAM = re.compile(r'(?:#?(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*])|[#?$!-])'
                         r'(?:(?:%%?|##?|:\??|\?)[^/]*)?')
DELIMITER = re.compile(r'''(?:([A-Za-z_][A-Za-z0-9_]*)|'([A-Za-z_][A-Za-z0-9_]*)'|'''
                       r'''"([A-Za-z_][A-Za-z0-9_]*)")(?=[ \t\n;|&)<>]|\Z)''')
IFS = re.compile(r'\$IFS|\$\{IFS[^}]*\}')  # also ${IFS%x}, ${IFS:-x}: still blanks
RANGE_GLOB = re.compile(r'<[0-9]*-[0-9]*>')
REDIRECTS = ('<<<', '<<-', '<<', '<>', '<&', '<', '>>', '>&', '>|', '>', '&>>', '&>')
MAX_NEST = 40  # $(…) and (…) inside each other; deeper is not read
MAX_AGAIN = 400_000  # characters the loose reading may read a second time (Reader.over)
MAX_SECONDS = 3.0  # and the time one check may take before it does (the hook has 10 s)
DEADLINE = [float('inf')]  # set by check() and check_ask()


class Reader:
    """Reads a shell text once, left to right, into simple commands, as far as it is certain.

    It knows only what bash (3.2 and later), zsh and sh read the same way: words of plain
    characters, `'…'`, `"…"`, `\\x`, `$name`, `${name}` and `${…}` without quotes inside,
    `$(…)`, `<(…)`, a `#` comment, the separators `; & | newline`, `(…)`, `[[ … ]]`
    of words only and with no word after it, the redirections in REDIRECTS with a word as target, and a here-document
    whose delimiter is a plain name. Everything else raises Unsure: a backtick, `$((`, `$[`,
    `((`, `$'…'`, `case`, a function, an `alias`, `a[…`, zsh's `>!`, `<->`, `{ … } always`,
    `repeat` (also after `do`, `then`, `!`), a `}` or `{` glued
    to a word, sh's `a &>f b`, bash's `>&-x`, a descriptor of two digits, a backslash-newline
    that is not after a blank, a quote that does not close, a control character. It never
    guesses: `uncertain` is then where the command it was reading started, and judge() reads
    the text from there to the end as the former permission rules did (net); the words it had
    read of that command stay, as a command.

    Where it leaves text out it is strictest, because that is where a misreading hides a
    command: a comment only at the start of a word and outside `$(…)`, its rest kept in
    `rests`; a here-document body only for a delimiter it read whole, and inside `$(…)` only
    when bash 3.2 would end the substitution at the same `)` (old_bash).

    loose=True is judge()'s second reading of an uncertain rest: at an Unsure in a command it
    skips a character and reads on in that command (cmd.loose, cmd.span), so it finds the
    words a strict reading stops before. What it reads is added to what is judged, never
    trusted to pass anything."""

    def __init__(self, text, comments=True, loose=False):
        for mark in (ALT_OPEN, ALT_CLOSE, SPLIT, NUL_MARK):  # the reader's own marks
            if mark in text:
                text = text.replace(mark, '?')
        self.t, self.n, self.i = text, len(text), 0
        self.comments = comments  # False: `#` is a character (the rest of a comment, re-read)
        self.loose = loose  # True: read on past what it does not know (judge's second reading)
        self.commands, self.rests, self.nets = [], [], []
        self.uncertain, self.quote = None, False
        self.open, self.pending = [], []  # commands being read; here-documents without body
        self.depth = self.subs = self.docs = 0
        self.last = 0  # where the last command outside any other started
        self.carry = None  # the words before a `&>` that has words after it (loose)
        self.old_dead = False  # bash 3.2 stopped at a `$(` it could not close: it runs no more
        self.spent = 0  # characters the loose reading read again after a stop
        self.gave_up = False  # it read the text again too often: the text is refused
        floor = 0
        while self.i < self.n:
            start = self.i
            try:
                self.read_list()
                break
            except Exception as fault:  # Unsure, or a fault in the reader: never passed
                if loose and self.over(self.i - start):
                    break
                if self.uncertain is None:
                    self.uncertain = self.open[0][0] if self.open else min(self.i, self.n)
                    if fault.args == ('glued',) and not self.open:
                        self.uncertain = self.last  # it joins the command before it
                # the words read so far of the commands it was in are words for certain
                self.commands += [cmd for _, cmd in self.open]
                if not loose:
                    break
                self.open, self.pending, self.depth, self.subs = [], [], 0, 0
                self.i = floor = max(self.i, floor) + 1

    def over(self, again):
        """True once the loose reading has spent its budget: each stop makes it read on one
        character further, and a word that stops at its end is then read whole each time (the
        second review: 38 s for 32,000 braces, where the hook has 10 s). MAX_AGAIN characters
        read again, or DEADLINE passed, and it gives up; judge() then refuses the text."""
        self.spent += max(again, 1)
        if self.spent > MAX_AGAIN or time.monotonic() > DEADLINE[0]:
            self.gave_up = True
        return self.gave_up

    def blanks(self):
        """Skip blanks, and a backslash-newline after a blank: the shell deletes it before it
        reads tokens, so one glued to a character can join two (`2\\<newline>>f`, `(\\<newline>(`)."""
        t, n = self.t, self.n
        while self.i < n:
            if t[self.i] in ' \t':
                self.i += 1
            elif t.startswith('\\\n', self.i):
                if self.i and t[self.i - 1] not in ' \t\n':
                    raise Unsure('glued')
                self.i += 2
            else:
                break

    def read_list(self, closer=None):
        """Commands up to the end of the text, or up to the `)` that closes a `(` or `$(`."""
        t, n = self.t, self.n
        while True:
            self.blanks()
            if self.i >= n:
                if closer:
                    raise Unsure
                return
            c = t[self.i]
            if c == '\n':
                self.i += 1
                self.read_bodies()
            elif c in ';|' or c == '&' and not t.startswith('&>', self.i):
                self.i += 1
            elif c == ')':
                if not closer:
                    raise Unsure  # a `case` pattern, or a `)` too many
                self.i += 1
                return
            elif c == '(':
                if t.startswith('((', self.i):
                    raise Unsure  # arithmetic: `<<` is a shift there
                self.i += 1
                self.nest()
                self.read_list(')')
                self.depth -= 1
            else:
                self.read_command()

    def nest(self):
        self.depth += 1
        if self.depth > MAX_NEST:
            raise Unsure('deep')

    def read_command(self):
        t, n = self.t, self.n
        cmd = Command()
        self.open.append((self.i, cmd))
        outer, depth, subs = len(self.open) == 1, self.depth, self.subs
        carry, self.carry = self.carry, None
        if outer:
            self.last = self.i
        while True:
            at = self.i
            try:
                if self.read_part(cmd):
                    break
            except Unsure as stop:
                if not (self.loose and outer) or self.over(self.i - at):
                    raise
                # the second reading: skip the character it stopped at and read on in this
                # command, whose words are then no longer certain (cmd.loose: the belt)
                cmd.loose = True
                cmd.span = (self.open[0][0], self.n)
                self.commands += [inner for _, inner in self.open[1:]]
                del self.open[1:]
                self.pending, self.depth, self.subs = [], depth, subs
                # read on one character after where the part started; past all of it when it
                # was nested too deeply, or each level would be read MAX_NEST times
                self.i = max(self.i, at + 1) if stop.args == ('deep',) else at + 1
        self.open.pop()
        self.commands.append(cmd)
        if carry:
            joined = Command()
            joined.words = carry + cmd.words
            self.commands.append(joined)
        if cmd.loose:
            cmd.span = (cmd.span[0], self.i)
        if cmd.cond:
            raise Unsure  # [[ without its ]]: an operator inside it ended the command

    def read_part(self, cmd):
        """Read the next word, redirection or comment of cmd; True at the command's end."""
        t, n = self.t, self.n
        if True:
            self.blanks()
            if self.loose and cmd.loose and 0 < self.i < n and t[self.i] in '&|!' \
                    and t[self.i - 1] in '<>&':
                self.i += 1  # what is left of an operator it skipped into (`>&|`, `>!`)
                return False
            if self.i >= n or t[self.i] in '\n;|)':
                return True
            c = t[self.i]
            if cmd.cond and c in '<>&':
                raise Unsure  # inside [[ … ]] these compare, or end the command
            if c == '&':
                if not t.startswith('&>', self.i):
                    return True
                self.redirect(cmd)
                cmd.both = True
            elif c in '<>' and t[self.i + 1:self.i + 2] != '(':
                if c == '<' and RANGE_GLOB.match(t, self.i):
                    raise Unsure  # zsh: <-> and <1-9> are globs for numbers
                self.redirect(cmd)
            elif c == '#' and self.comments and not cmd.loose:
                if self.subs:
                    raise Unsure  # bash 3.2 looks for the `)` inside the comment
                eol = t.find('\n', self.i)
                eol = n if eol < 0 else eol
                self.rests.append(t[self.i + 1:eol])
                self.i = eol
                return True
            else:
                at = self.i
                word = self.read_word()
                if self.i < n and t[self.i] in '<>':
                    raw = t[at:self.i]
                    if raw.isascii() and raw.isdigit():  # 2>…: the file descriptor
                        if len(raw) > 1:
                            raise Unsure  # 12>…: a word in zsh and sh
                        self.redirect(cmd)
                        return False
                    if raw.startswith('{'):
                        raise Unsure  # {fd}>…
                if cmd.both:  # `a &>f b`: bash runs `a b`, sh runs `a &` and then `b`
                    if not self.loose:
                        raise Unsure
                    self.i, self.carry = at, cmd.words  # the second reading: both
                    return True
                if cmd.closed:
                    raise Unsure  # zsh: `if [[ a ]] git …` runs the words after the `]]`
                # the first word, also after `then`, `do`, `!`, `{`, an assignment
                first = all(base(w) in LEADING or SETS.fullmatch(w) for w in cmd.words)
                cmd.words.append(word)
                if word in ('case', 'esac') and (self.subs or first) or \
                        first and word in ('select', 'function', 'repeat', 'always', 'foreach',
                                           'alias'):
                    # a case pattern's `)` would end a $(…); zsh's own loops; an alias changes
                    # how the lines after it are read
                    raise Unsure
                if cmd.words[0] == 'set' and (word == '-H' or 'hist' in word):
                    raise Unsure  # history expansion switched on: `!:1-3` is a command
                if word in ('{', '}') and not first:
                    raise Unsure  # zsh ends a `{ … }` group here (`{ a } always { b }`)
                if word == '[[':
                    cmd.cond = True  # a command like another, while it holds only words
                elif word == ']]':
                    cmd.cond, cmd.closed = False, True
                elif cmd.cond and word in ('=~', '&&', '||'):
                    raise Unsure  # a pattern is read by rules of its own
            return False

    def redirect(self, cmd):
        t, n = self.t, self.n
        op = next(o for o in REDIRECTS if t.startswith(o, self.i))
        self.i += len(op)
        if op in ('<<', '<<-'):
            while self.i < n and t[self.i] in ' \t':
                self.i += 1
            m = DELIMITER.match(t, self.i)
            if not m:
                raise Unsure
            self.i = m.end()
            self.pending.append((cmd, op == '<<-', m.group(1) or m.group(2) or m.group(3),
                                 not m.group(1), self.subs))
            return
        if t[self.i:self.i + 1] in ('|', '!', '&'):
            raise Unsure  # zsh: >! >>| >&| &>!
        self.blanks()
        if self.i >= n or t[self.i] in '\n;|&()#!' or \
                t[self.i] in '<>' and t[self.i + 1:self.i + 2] != '(':
            raise Unsure  # no target, or one another shell reads as part of the operator
        if op in ('>&', '<&') and t[self.i] == '-':
            self.i += 1  # >&- closes; bash ends it there (`>&-git` runs git), other shells do not
            if self.i < n and t[self.i] not in ' \t\n;|&)':
                raise Unsure
            return
        word = self.read_word()
        if op == '<<<':
            cmd.strings.append(word)

    def read_bodies(self):
        """After a newline: the bodies of the here-documents opened on the line before it."""
        t, n = self.t, self.n
        pending, self.pending = self.pending, []
        for cmd, dash, word, quoted, level in pending:
            if level != self.subs:
                raise Unsure  # opened outside this $(…), or inside one that closed already
            lines = []
            while self.i < n:
                j = t.find('\n', self.i)
                end = n if j < 0 else j
                line = t[self.i:end]
                self.i = min(end + 1, n)
                if (line.lstrip('\t') if dash else line) == word:
                    break
                if not quoted and line.endswith('\\'):
                    raise Unsure  # a backslash-newline joins the lines of an unquoted body
                lines.append(line)
            body = '\n'.join(lines)
            cmd.bodies.append(body)
            if not quoted and ('$(' in body or '`' in body):
                self.nets.append(body)  # an unquoted body runs its substitutions: body_reason
            self.docs += 1

    def read_word(self):
        t, n = self.t, self.n
        start, parts, known, one, braces = self.i, [], True, True, 0
        if t[start] in '<>':  # <(…) or >(…)
            self.i += 2
            self.sub(self.i)
            known = one = False
        elif SUBSCRIPT.match(t, start):
            raise Unsure
        while self.i < n:
            c = t[self.i]
            if c in ' \t\n;|&<>)':
                break
            m = PLAIN.match(t, self.i)
            if m:
                run = m.group()
                if '*' in run or '?' in run or '[' in run:
                    if run[0] == '[' and not known:
                        raise Unsure  # $x[…]: zsh reads a subscript
                    known = one = False  # a glob: the text stays, the words are not fixed
                if '}' in run:
                    for ch in run:
                        braces += (ch == '{') - (ch == '}')
                        if braces < 0 and run != '}':
                            raise Unsure  # zsh ends the word, and a `{ …` group, at this `}`
                    braces = max(braces, 0)
                elif '{' in run:
                    braces += run.count('{')
                parts.append(run)
                self.i = m.end()
            elif c == '\\':
                if self.i + 1 >= n or t[self.i + 1] == '\n':
                    raise Unsure  # a backslash-newline inside a word may join a token
                parts.append(t[self.i + 1])
                self.i += 2
            elif c == "'":
                j = t.find("'", self.i + 1)
                if j < 0:
                    self.quote = True
                    raise Unsure
                parts.append(self.quoted(t[self.i + 1:j]))
                self.i = j + 1
            elif c == '"':
                text, fixed, single = self.read_dq()
                parts.append(text)
                known, one = known and fixed, one and single
            elif c == '$':
                at = self.i
                text, fixed, single = self.read_dollar(False)
                # unquoted, sh splits the word at $IFS (git${IFS}stash${IFS}drop): the one
                # variable whose value the text need not set; any other is a word built from
                # a variable, which the guard does not see
                parts.append(SPLIT if IFS.fullmatch(t, at, self.i) else text)
                known, one = known and fixed, one and single
            else:
                raise Unsure  # a backtick, `(`, a control character
        raw = t[start:self.i]
        if braces and raw != '{':
            raise Unsure  # `{git`: zsh opens a group and runs git
        text = ''.join(parts)
        word = Word(text.split(NUL_MARK)[0], known, one, '{' in raw and brace_expansion(raw))
        if NUL_MARK in text and word.alt is None:  # bash's reading beside zsh's
            word.alt = str(Word(text.replace(NUL_MARK, '')))
        return word

    def quoted(self, text):
        if self.pending and '\n' in text:
            raise Unsure  # a quoted newline before a here-document's body
        return text

    def read_dq(self):
        """(text, known, one) of the double-quoted string at i."""
        t, n = self.t, self.n
        self.i += 1
        out, known, one = [], True, True
        while self.i < n:
            c = t[self.i]
            if c == '"':
                self.i += 1
                return ''.join(out), known, one
            if c == '\\':
                if self.i + 1 >= n:
                    break
                nxt = t[self.i + 1]
                if nxt == '\n':
                    if t[self.i - 1] == '$':
                        raise Unsure  # "$\<newline>x" is "$x"
                    self.quoted(nxt)
                else:
                    out.append(nxt if nxt in '$`"\\' else '\\' + nxt)
                self.i += 2
            elif c == '$':
                text, fixed, single = self.read_dollar(True)
                out.append(text)
                known, one = known and fixed, one and single
            elif c == '`':
                raise Unsure
            else:
                m = DQ_PLAIN.match(t, self.i)
                out.append(self.quoted(m.group()))
                self.i = m.end()
        self.quote = True
        raise Unsure

    def read_dollar(self, in_dq):
        """(text, known, one) of what starts at the `$` at i."""
        t, i = self.t, self.i
        nxt = t[i + 1:i + 2]
        if nxt == '(':
            if t.startswith('$((', i):
                raise Unsure
            self.i += 2
            self.sub(self.i)
            return '', False, in_dq
        if nxt == '{':
            m = PARAM.match(t, i + 1)
            if not m:
                raise Unsure
            self.i = m.end()
            default = DEFAULT.fullmatch(m.group(1))
            if not default and not PLAIN_PARAM.fullmatch(m.group(1)):
                raise Unsure  # ${x/#/stash}: a form whose value may be a word of the text
            text = ALT_OPEN + (default.group(1) or default.group(2) or '') + ALT_CLOSE \
                if default else ''
            return text, False, in_dq and '@' not in m.group(1) and '*' not in m.group(1)
        if nxt == "'" and not in_dq:
            if not self.loose:
                # no two shells read $'…' alike: dash reads `$` and a quoted string, bash 3.2
                # knows no \u, zsh no \c, an octal number over \377 wraps, a NUL ends the
                # string in bash and the whole word in zsh (the second review). The loose
                # reading takes bash's.
                raise Unsure
            m = ANSI_C.match(t, i)
            value = decode_ansi_c(m.group(1)) if m and "'" not in m.group(1) else None
            if value is None:  # no bash escape, or `\'`, where sh ends the quote
                raise Unsure
            self.i = m.end()
            if '\\' in m.group(1) and self.open:
                # read as bash reads it, and its raw text by the belt (zsh: `$'\clean'`)
                self.open[0][1].loose, self.open[0][1].span = True, (self.open[0][0], self.n)
            if '\0' in value:  # a NUL ends the string in bash and the whole word in zsh
                value = value.split('\0')[0] + NUL_MARK
            return self.quoted(value), True, True
        if nxt in ('"', '[') and not in_dq or nxt == '[':
            raise Unsure  # $"…", $[…]
        m = NAME.match(t, i + 1)
        if m:
            self.i = m.end()
            if t.startswith('[', self.i):
                raise Unsure  # $x[…]: zsh reads a subscript
            return '', False, in_dq
        if nxt and (nxt.isascii() and nxt.isdigit() or nxt in '@*#?$!-'):
            self.i += 2
            return '', False, in_dq and nxt not in '@*'
        if nxt in ('=', '~', '^') and NAME.match(t, i + 2):
            self.i = NAME.match(t, i + 2).end()
            return '', False, False  # zsh: $=x, $~x, $^x expand x; elsewhere a word `$=x`
        if nxt and nxt not in ' \t\n";|&)/.,:\\':
            raise Unsure
        self.i += 1
        return '$', True, True

    def sub(self, opened):
        """The commands of a `$(…)`, `<(…)` or `>(…)` whose text starts at opened."""
        self.nest()
        docs = self.docs
        self.subs += 1
        self.read_list(')')
        if self.pending and self.pending[-1][4] == self.subs:
            raise Unsure  # a here-document whose body would start after the `)`
        self.subs -= 1
        self.depth -= 1
        if self.docs > docs and not self.old_dead:
            self.old_bash(opened, self.i - 1)

    def old_bash(self, opened, closed):
        """A here-document inside the `$(…)` from opened to closed. bash 3.2 (macOS /bin/sh)
        finds the `)` by counting parentheses and quotes, without knowing the body: measured,
        a body `x)" ; cmd ; echo "$(echo y` runs cmd there. So the body is trusted only when
        that count ends at the same `)`, with and without its reading of a `#`; when the count
        never ends, that shell runs nothing from here on; otherwise Unsure."""
        ends = {self.old_scan(opened, comments) for comments in (False, True)}
        if ends == {-1}:
            self.old_dead = True
        elif ends != {closed}:
            raise Unsure

    def old_scan(self, i, comments):
        """Where a count of parentheses and quotes from i ends the `$(…)`, or -1 for never: a
        quote, a backtick pair, `$(…)`, `${…}` and `$[…]` are each read to their end, and a
        `(` outside them is one more to close."""
        t, n, stack = self.t, self.n, [')']
        while i < n:
            c, top = t[i], stack[-1]
            if c == '\\':
                i += 1
            elif top == '`':
                if c == '`':
                    stack.pop()
            elif c == "'" and top != '"':
                i = t.find("'", i + 1)
                if i < 0:
                    return -1
            elif c == '"':
                if top == '"':
                    stack.pop()
                else:
                    stack.append('"')
            elif c == '`':
                stack.append('`')
            elif c == '$' and t[i + 1:i + 2] in ('(', '{', '['):
                stack.append({'(': ')', '{': '}', '[': ']'}[t[i + 1]])
                i += 1
            elif top == '"':
                pass
            elif c == '#' and comments and top == ')' and t[i - 1] in ' \t\n':
                i = t.find('\n', i)
                if i < 0:
                    return -1
            elif c == '(' and top == ')':
                stack.append(')')
            elif c == top:
                stack.pop()
                if not stack:
                    return i
            i += 1
        return -1


ASKING = False  # set by judge_ask(): the judges then report what the user is asked about
# the subcommands judge_git() or ask_git() can refuse or ask about
RULED = {'push', 'pull', 'reset', 'clean', 'restore', 'checkout', 'switch', 'stash', 'rebase',
         'tag', 'branch', 'filter-branch', 'filter-repo', 'replace', 'reflog', 'gc', 'prune',
         'update-ref', 'worktree', 'commit', 'add', 'config', 'remote'}
MAX_LOOSE = 16
LOOSE_WORD = re.compile(r'''(?:"[^"]*"|'[^']*'|\\.|[^\s"'\\]|["'\\])+''')
LOOSE_SEGMENT = re.compile(r'(?:[^\n;|&]|(?<=[<>])&|&(?=>))+')  # `>&` and `&>` split nothing
ALL_SHELLS = SHELLS | {'csh', 'tcsh', 'fish'}
SOURCES = {'.', 'source'}
STDIN = {'-s', '-', '/dev/stdin', '/dev/fd/0', '/proc/self/fd/0'}
SHELL_C = re.compile(r'-[A-Za-z]*c[A-Za-z]*')  # a shell's -c, also in a cluster (-lc)
ENV_S = re.compile(r'-[A-Za-z0-9]*S(.*)', re.S)  # env's -S, also in a cluster (-vS)
SETS = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\+?=.*', re.S)  # an assignment, also `a+=x`
# quotes and what opens or closes a substitution or a group, as blanks: the belt then reads a
# text that is not a command line (a here-document body, a text piped into a shell)
UNWORD = re.compile(r'[\'"`(){}]|\$\(|\$\{\w*:?[-=+]?')
UNQUOTE = re.compile(r'\$?[\'"]')  # a quote, and the `$` of a $'…'


def unworded(text):
    """The belt on a text that is not a command line: with each quote as a blank, and with the
    quotes dropped (`$(git stash d$'r'op)` in a here-document body)."""
    return judge_loose(UNWORD.sub(' ', text)) or judge_loose(UNWORD.sub(' ', UNQUOTE.sub('', text)))


LOOSE_PART = re.compile(r'\$?\{\w*:?[-=+]?')  # the start of what is left of a `${x:-word}`


def loose_word(word):
    """A word of a command read past something unknown, as the belt reads it: `{x:-stash}`,
    left of `${x:-stash}`, is `stash`. Its value is not known."""
    m = LOOSE_PART.match(word)
    text = word[m.end():].replace('}', '', 1) if m else str(word)
    return Word(text, False, getattr(word, 'one', True), getattr(word, 'brace', False))


# words before a command that are not the command (zsh: `- git …`, `nocorrect git …`)
LEADING = KEYWORDS | {'{', '}', 'coproc', '-', 'nocorrect'}

# Claude Code's git permission rules as they stood before #33, each without its `git `; every
# one also stood as `git -C * <rule>`. The rules whose `*` reached into a commit message were
# dropped from policy/claude-permissions.json; net() reads a text by all of them where the
# reader is not certain of it. tests/claude_git_rules.py checks the list against
# tests/claude_git_rules_former.json.
NET_DENY = (
    'push --force*|push -f*|push * --force*|push * -f*|push --mirror*|push * --mirror*|'
    'push --prune*|push * --prune*|push * +*|reset --hard*|reset * --hard*|branch -D*|'
    'branch * -D*|branch -f*|branch * -f*|branch --force*|branch * --force*|clean*|restore *|'
    'checkout -- *|checkout * -- *|checkout .|checkout * .|checkout -f*|checkout * -f*|'
    'checkout * --force*|switch -f*|switch * -f*|switch * --force*|switch --discard-changes*|'
    'stash drop*|stash clear*|rebase*|tag -d*|tag --delete*|tag -f*|tag * -f*|'
    'worktree remove*|filter-branch*|filter-repo*|replace*|reflog expire*|reflog delete*|'
    'gc --prune*|gc * --prune*|prune*|update-ref -d*|update-ref * -d*|* --no-verify*|'
    'commit -n*|commit * -n *|-c core.hooksPath*|-c * core.hooksPath*|config --global *|'
    'config --system *|config core.*|config credential*|config user.*|config * --unset*|'
    'add -A*|add * -A*|add --all*|add .|add -f*|add * -f*|add --force*|add * --force*|'
    'commit -a*|commit --all*').split('|')
NET_ASK = ('push*|commit --amend*|commit * --amend*|update-ref*|remote add*|remote set-url*|'
           'remote remove*|remote rm*|remote rename*').split('|')
NET_REASON = {'push': 'pushes to a remote', 'commit': 'amends a commit (commit --amend)',
              'update-ref': 'moves a ref (update-ref)', 'remote': 'changes a remote'}
NET_END = ' ;|&()<>{}"\'`'  # what may follow a rule that does not end in `*` (zsh: `.(N)`)
# read as a blank by net(): `<` and `>` (`git>f`, `drop<<E`: a redirection glued to a word) and
# a substitution without another inside it (`git `true` -C r …`), which may be no word at all
EXPANSION = re.compile(r'`[^`]*`|\$\([^()]*\)|\$\{[^{}]*\}|\$[A-Za-z_]\w*|\$[@*#?!$0-9-]')
NET_APART = re.compile(r'[<>]|`[^`]*`|\$\([^()]*\)|\$\{[^{}]*\}|\$[A-Za-z_]\w*|\$[@*#?!$0-9-]')


def net_rules(rules):
    """[(rule, its literal parts in order, whether the last part must end the command)] for
    each rule and its `git -C * ` form. A `*` is any text; one trailing ` *` also matches no
    arguments (the client's rule, pattern_regex in pre_tool_sandbox_network.py)."""
    out = []
    for rule in ['git ' + r for r in rules] + ['git -C * ' + r for r in rules]:
        if rule.count('*') == 1 and rule.endswith(' *'):
            out.append((rule, [rule[:-2]], True))
        else:
            parts = rule.split('*')
            out.append((rule, [p for p in parts if p], parts[-1] != ''))
    return out


NET = {False: net_rules(NET_DENY), True: net_rules(NET_ASK)}


def glob_hit(flat, parts, ends):
    """True when the parts stand in flat in this order, the first where a command can start
    (not inside a word) and, with ends, the last where one can end. The leftmost place for each
    part is enough, since a `*` between them is any text: linear, a few str.find calls."""
    pos, last = 0, len(parts) - 1
    for k, part in enumerate(parts):
        while True:
            p = flat.find(part, pos)
            if p < 0:
                return False
            pos, end = p + 1, p + len(part)
            if k == 0 and p and (flat[p - 1].isalnum() or flat[p - 1] == '_'):
                continue
            if k == last and ends and end < len(flat) and flat[end] not in NET_END:
                continue
            break
        pos = end
    return True


def net(text):
    """The reason to stop a text the reader is not certain of, or None: the text read as the
    former permission rules read it.

    Each rule is searched in the raw text from any `git` on, blanks and newlines as one blank,
    backslash-newlines removed; once more with quotes and backslashes removed; and once more
    with NET_APART as blanks. The client
    matched a rule against the whole call and each command of it; a search that may start at
    any `git` and span any text matches at least that, whatever the client split. So an
    uncertain text is stopped whenever those rules stopped it: also a commit whose message
    names a rule's words, which is the cost of not being certain."""
    flat = ' '.join(text.replace('\\\n', '').split())
    bare = re.sub(r'\$?[\'"]|\\', '', flat)  # also the `$` of a $'…'
    apart = NET_APART.sub(' ', bare)
    empty = EXPANSION.sub('', bare)  # g`true`it: an expansion that is nothing
    forms = (flat, ' '.join(bare.split()), ' '.join(apart.split()), ' '.join(empty.split()))
    for form in dict.fromkeys(f for f in forms if 'git' in f):
        for rule, parts, ends in NET[ASKING]:
            if glob_hit(form, parts, ends):
                if ASKING:
                    return NET_REASON[rule.replace('git -C * ', 'git ').split()[1].rstrip('*')]
                return 'cannot be read for certain and matches the rule `%s`' % rule
    return None


def judge_loose(text):
    """The belt (the maintainer, 2026-11-24): in each stretch of text between newlines and
    `; | &`, every word in RULED after a `git` word, up to the next one, is judged as the
    subcommand with the words after it. A quoted stretch stays in its word (`-m "push it"` is
    no push), a quote that does not close is a character; then quotes and backslashes are
    dropped and a word is read without the `$(`, `(`, `{` or backtick before it and the `)`,
    `}` or backtick after it. Linear: each word belongs to one git; past MAX_LOOSE candidates
    for one git it gives up and refuses."""
    one = ask_git if ASKING else judge_git
    for segment in LOOSE_SEGMENT.findall(text):
        if 'git' not in segment:
            continue
        words = [re.sub(r'[\'"\\]', '', w).lstrip('$(`{').rstrip(')`}')
                 for w in LOOSE_WORD.findall(segment)]
        starts = [k for k, w in enumerate(words) if base(w) == 'git'] + [len(words)]
        for a, b in zip(starts, starts[1:]):
            reason = belt(words[a + 1:b], one, 0)
            if reason:
                return reason
    return None


def belt(args, one, first):
    """Every word in RULED from args[first] on, judged as the subcommand with the words after
    it, and every `-c` as git's own option (`git >! out -c core.hooksPath=… commit`); None when
    none is refused."""
    tried = 0
    for k in range(first, len(args)):
        if args[k] in RULED or args[k] in ('-c', '--config-env') or \
                args[k].startswith('--config-env='):
            tried += 1
            if tried > MAX_LOOSE:
                return 'cannot be read by the git guard (git with many subcommand words)'
            reason = one(args[k:])
            if reason:
                return reason
    return None


def unfixed(args):
    """Where the words of a git command (after `git`) stop being fixed by the text, at or
    before the subcommand: an unknown word where an option or the subcommand stands, or an
    unquoted one as an option's value, which may be no word at all. None when the subcommand
    is a known word."""
    i = 0
    while i < len(args):
        a = args[i]
        if not getattr(a, 'known', True):
            return i
        if not a.startswith('-'):
            return None
        if a in GIT_VALUE_OPTS:
            if i + 1 < len(args) and not getattr(args[i + 1], 'one', True):
                return i + 1
            i += 1
        i += 1
    return None


def ask_git(args):
    """args: tokens after `git`. The reason the user is asked first (Claude Code), or None."""
    if unknown_options(args) > MAX_UNKNOWN:
        return 'uses git options the guard does not know'
    i = 0
    while i < len(args) and args[i].startswith('-'):
        opt = args[i]
        if opt not in GIT_VALUE_OPTS and opt not in GIT_FLAG_OPTS and '=' not in opt:
            other = ask_git(args[:i] + args[i + 2:])  # read as `<opt> <value>`
            if other:
                return other
        i += 2 if opt in GIT_VALUE_OPTS else 1
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


def command_name(word):
    """The command a word names: without its folder, zsh's `=`, and in lower case (a
    case-insensitive disk runs `GIT`)."""
    return base(word).lstrip('=').lower()


def judge_command(tokens, depth, cmd=None, scan=True):
    """Judge one simple command, given as its words; cmd is the Command they came from."""
    k = 0
    while k < len(tokens) and (SETS.fullmatch(tokens[k]) or base(tokens[k]) in LEADING):
        if tokens[k].startswith('GIT_CONFIG'):
            return 'changes git configuration through the environment'
        k += 1
    tokens = tokens[k:]
    if not tokens:
        return None
    if depth > MAX_DEPTH:
        return 'is nested too deeply to check'
    loose = getattr(cmd, 'loose', False)
    if loose:  # read past something unknown
        tokens = [loose_word(t) for t in tokens]
    name = command_name(tokens[0])
    if getattr(tokens[0], 'brace', False) and 'git' in name:
        return 'uses brace expansion, which the guard cannot read safely'
    if not getattr(tokens[0], 'known', True):
        # `$pfx git …`, `$x sh -c '…'`: an unknown first word may be a wrapper or no word, and
        # each later `git` the command (`$x env -u git git stash drop`)
        later = [1] if not tokens[0] else [j for j, tok in enumerate(tokens[1:], 1)
                                           if command_name(tok) == 'git'][:MAX_LOOSE]
        for nxt in later:
            reason = judge_command(tokens[nxt:], depth + 1, cmd, not tokens[0])
            if reason:
                return reason
        if not tokens[0] and any(SHELL_C.fullmatch(tok) for tok in tokens[1:]):
            for tok in tokens[1:]:  # `$SHELL -c '…'`, `$0 -c '…'`
                reason = judge(tok, depth + 1) if may_run_git(tok) else None
                if reason:
                    return reason
    if name == 'git':  # also `$(true)git`: read with its unknown part empty
        args = tokens[1:]
        if any(getattr(a, 'brace', False) for a in args):
            return 'uses brace expansion, which the guard cannot read safely'
        one = ask_git if ASKING else judge_git
        reason, first = one(args), -1 if loose else unfixed(args)
        if not reason and first is not None:  # the belt, on the words as read
            reason = belt(args, one, first + 1)
        if not reason and not all(a or getattr(a, 'one', True) for a in args):
            # `git stash "$@" drop`: a word that may be no word at all, read as none
            reason = one([a for a in args if a or getattr(a, 'one', True)])
        return reason
    if name == 'gh':
        if tokens[1:2] in (['config'], ['alias']) and tokens[2:3] in (
                ['set'], ['delete'], ['import'], ['clear-cache']):
            return 'changes gh configuration'
    elif name in ALL_SHELLS:
        if any(SHELL_C.fullmatch(tok) for tok in tokens[1:]):
            for tok in tokens[1:]:  # `-c -- '…'`, `-c -x '…'`, `-co pipefail '…'`: any of them
                reason = judge(tok, depth + 1) if may_run_git(tok) else None
                if reason:
                    return reason
                if cmd is not None and not getattr(tok, 'known', True):
                    cmd.runs = True  # sh -c "$(cat <<'EOF' … EOF)": the script is elsewhere
        elif cmd is not None:
            rest = [t for j, t in enumerate(tokens[1:], 1)  # without `-o errexit`, `+e`
                    if t[:1] not in ('-', '+') and tokens[j - 1] not in ('-o', '+o', '-O', '+O')]
            if not rest or STDIN & set(tokens[1:]):
                cmd.stdin = True  # no script: it reads one from a pipe, `echo git … | bash`
    elif name in INTERPRETERS:
        for j, tok in enumerate(tokens[1:], 1):
            if tok in ('-c', '-e') and j + 1 < len(tokens):
                return judge_raw(tokens[j + 1], needs_exec=True)
    elif name == 'eval':
        if cmd is not None and not all(getattr(tok, 'known', True) for tok in tokens[1:]):
            cmd.runs = True  # eval "$(cat <<'EOF' … EOF)"
        return judge(' '.join(tokens[2:] if tokens[1:2] == ['--'] else tokens[1:]), depth + 1)
    elif name in SOURCES:
        if cmd is not None and STDIN & set(tokens[1:]):
            cmd.stdin = True  # . /dev/stdin <<< 'git …'
    elif name == 'trap':
        for tok in tokens[1:]:  # the action runs later, as a shell text
            reason = judge(tok, depth + 1) if may_run_git(tok) else None
            if reason:
                return reason
    elif name == 'ssh':
        for j, tok in enumerate(tokens[1:], 1):
            if 'git' in tok:
                return judge(' '.join(tokens[j:]), depth + 1)
    elif name in WRAPPERS:
        runs = ALL_SHELLS | INTERPRETERS | WRAPPERS | {'git', 'eval', 'ssh', 'trap'}
        seen = 0
        for j, tok in enumerate(tokens[1:], 1):
            cluster = ENV_S.fullmatch(tok) if name == 'env' else None  # -S, -vS, -iS'git …'
            if name == 'env' and (tok == '--split-string' or cluster or
                                  tok.startswith('--split-string=')):
                if tok == '--split-string' or cluster and not cluster.group(1):
                    split, after = ' '.join(tokens[j + 1:j + 2]), tokens[j + 2:]
                elif cluster:  # env -S 'git …' splits its argument
                    split, after = cluster.group(1), tokens[j + 1:]
                else:
                    split, after = tok.split('=', 1)[1], tokens[j + 1:]
                reason = judge(' '.join([split] + [shlex.quote(t) for t in after]), depth + 1)
                if reason:
                    return reason
                continue  # `-uGIT_SSH` is no -S: the words after it are judged as well
            if ASSIGN.fullmatch(tok) and tok.startswith('GIT_CONFIG'):
                return 'changes git configuration through the environment'
            if command_name(tok) in runs:
                # the first such word is the command, unless it is an option's value
                # (`env -u git sh -c '…'`, `find -name git -exec sh -c '…'`): judge each
                reason = judge_command(tokens[j:], depth + 1, cmd, False)
                seen += 1
                if reason or not scan:
                    return reason
                if seen > MAX_LOOSE:
                    return 'cannot be read by the git guard (many commands in one)'
    return None


def judge(text, depth=0, lenient=False):
    """The reason to block (or, under judge_ask, to ask about) a shell text, or None.

    Exact where the reading is certain, the former rules where it is not (#33): the commands
    the Reader is certain of are judged by their words; from where it stops being certain, the
    rest of the text is judged by net(), and by its words as a loose Reader finds them. Each
    can only add a reason, so what the reader does not know is never passed on its account. The rest of a line after a `#` is judged too, as a
    text of its own in which `#` is a character (lenient): a shell that reads no comments there
    runs it (the maintainer, 2026-11-23)."""
    if depth > MAX_DEPTH:
        return 'is nested too deeply to check'
    read = Reader(text, comments=not lenient)
    commands, rests, nets = read.commands, read.rests, read.nets
    if read.uncertain is not None:
        # a second reading of the uncertain rest, which skips what it does not know: what
        # judge_command knows (a redirection between the words, GIT_CONFIG_…, gh, an
        # interpreter) holds there too. It can only add a reason.
        rest = text[read.uncertain:]
        for form in dict.fromkeys((rest.replace('\\\n', ''), rest)):  # the shell deletes them
            again = Reader(form, comments=not lenient, loose=True)
            if again.gave_up:
                return 'cannot be read by the git guard (too much of it is unknown to read ' \
                       'within the hook\'s time)'
            for cmd in again.commands:
                if cmd.loose and cmd.span:
                    cmd.span = form[cmd.span[0]:cmd.span[1]]  # its raw text, for the belt
            commands, rests, nets = (commands + again.commands, rests + again.rests,
                                     nets + again.nets)
    piped = False
    for cmd in commands:
        reason = judge_command(cmd.words, depth, cmd)
        if not reason and any(w.alt is not None for w in cmd.words):  # ${x:-word} as word
            reason = judge_command([w if w.alt is None else Word(w.alt, False, w.one, w.brace)
                                    for w in cmd.words], depth, cmd)
        if not reason and any(w.pieces for w in cmd.words):  # git${IFS}stash${IFS}drop
            for k in (0, 1):
                reason = reason or judge_command(
                    [Word(p, False, True, w.brace) for w in cmd.words
                     for p in (w.pieces[k] if w.pieces else [w if w.alt is None or not k
                                                             else w.alt])], depth, cmd)
        if reason:
            return reason
        readers = {command_name(w) for w in cmd.words}
        for body in cmd.bodies + cmd.strings:  # data, unless a shell or an interpreter reads it
            reason = judge(body, depth + 1) if readers & (ALL_SHELLS | SOURCES) else \
                judge_raw(body, needs_exec=True) if readers & INTERPRETERS else None
            if reason:
                return reason
        # a shell that reads the other commands' output, or runs a text that is not in its
        # own words (`eval "$(cat <<'EOF' … EOF)"`, `sh <<< "$(…)"`): any of the text may run
        piped = piped or cmd.stdin and not cmd.bodies and not cmd.strings or cmd.runs or \
            bool(readers & (ALL_SHELLS | SOURCES)) and not all(w.known for w in cmd.strings)
    for rest in rests:
        reason = judge(rest, depth, lenient=True) if may_run_git(rest) else None
        if reason:
            return reason
    for body in nets:
        reason = net(body) or unworded(body)
        if reason:
            return reason
    for cmd in commands:
        if cmd.loose and cmd.span:  # the belt on the raw text of a command read loosely
            raw = cmd.span
            reason = judge_loose(raw) or judge_loose(NET_APART.sub(' ', raw))
            if reason:
                return reason
    if read.uncertain is not None:
        rest = text[read.uncertain:]
        reason = net(rest)
        if reason:
            return reason
        if ASKING and read.quote and not lenient and re.search(r'\bgit\b', rest):
            return 'cannot be read by the git guard (an open quote?)'
    if piped:  # a shell reads the output of the other commands: any of the text may be run
        for cmd in commands:
            for body in cmd.bodies + cmd.strings:
                reason = judge(body, depth + 1)
                if reason:
                    return reason
        return net(text) or unworded(text)
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
RAW_ASK = [((r'git\b', r'\bpush\b'), 'pushes to a remote'),
           ((r'git\b', r'\bcommit\b', r'--amend'), 'amends a commit (commit --amend)'),
           ((r'git\b', r'\bupdate-ref\b'), 'moves a ref (update-ref)'),
           ((r'git\b', r'\bremote\b', r'\b(add|set-url|remove|rm|rename)\b'), 'changes a remote')]
RAW_ASK = [(tuple(re.compile(p) for p in parts), reason) for parts, reason in RAW_ASK]
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
    """Plain pattern search, for code handed to an interpreter. It is judged only when it can
    start a process: code that merely prints or compares such a string passes. Under judge_ask
    it searches for the asked commands (RAW_ASK)."""
    if needs_exec and not EXEC_HINT.search(code):
        return None
    for segment in SEGMENT.findall(code):
        if 'git' not in segment:
            continue
        for patterns, reason in RAW_ASK if ASKING else RAW:
            if in_order(segment, patterns):
                return reason
    return None


def check(command):
    """The reason to block a command, or None."""
    if not may_run_git(command):
        return None
    if len(command) > MAX_INPUT:
        return 'is longer than %d characters, too long to check' % MAX_INPUT
    DEADLINE[0] = time.monotonic() + MAX_SECONDS
    return judge(command)


def check_ask(command):
    """The reason to ask the user first (Claude Code), for a command check() lets through."""
    if not may_run_git(command):
        return None
    DEADLINE[0] = time.monotonic() + MAX_SECONDS
    return judge_ask(command)


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
