#!/usr/bin/env python3
"""PreToolUse hook (Claude Code): the user approves a destructive delete before it runs.

Enforces the core rule (rules/core.md §Git) "Outside a repository, delete with the system's
trash, not `rm -rf`": a guarded delete asks the user and runs on the user's approval; nothing
is denied outright, because a deny would make a needed delete impossible. The safe form its
message names: the system's trash (`trash` on macOS, `gio trash` on Linux, the Recycle Bin on
Windows) with literal, quoted, absolute paths that were listed and checked first. The occasion
was an agent that built paths with `xargs -n1 dirname`: `xargs` split
`~/Library/Application Support/…` on its space, `dirname` returned `~/Library`, and `rm -rf`
ran on it.

It answers `permissionDecision: "ask"` with a plain reason, never "deny", so the permission
prompt says what the delete would hit. A hook's "ask" also prompts in auto mode, and an allow
rule such as `Bash(find *)` does not skip it (Claude Code documentation). It asks for a Bash
command (or a `run_in_terminal` call) that:
- deletes (`rm`, `rmdir`, `unlink`, `find … -delete`, `find … -exec rm`) a target that resolves
  to the root of the disk or of a drive, a folder directly in it, a folder directly in
  /Users, /home, /Volumes, /Library, /Applications, /private, /var, /mnt or /media, a home
  folder (the user's own, `/Users/<anyone>`, `/home/<anyone>`, `C:/Users/<anyone>`) or
  anything directly in one (`~/Library`, `~/Documents`, `~/.zshrc`), anything in a home's app
  data (`~/Library` except inside `Caches` and `Logs`; `~/AppData` except inside
  `Local/Temp`), anything in `~/.ssh` or `~/.gnupg`, or in a system folder (`/System`, `/usr`,
  `/bin`, `/sbin`, `/lib`, `/etc`, `/private/etc`, `C:/Windows`, `C:/Program Files`,
  `C:/ProgramData`);
- deletes with a glob that reaches such a target (`rm -rf ~/*`, `~/Library/*`, `/*`) or that
  empties such a folder in a home folder (`~/Documents/*`);
- deletes recursively a target that is computed rather than literal: a variable other than
  `$HOME`, `$PWD`, the temporary folder's variable (`$TMPDIR`, `$TEMP`, `$TMP`, when it names
  a usable temporary folder), one assigned a literal earlier in the same command or one
  assigned `$(mktemp -d)`; a `$(…)` or backtick substitution; a relative path after a `cd` to
  a computed folder. A computed part in double quotes after a literal folder inside a git
  worktree or a temporary folder passes (`rm -rf "$S/package-$C"`): the path is judged with
  that part empty, and the guard assumes it holds no `..`. An unquoted one asks, because it
  splits on spaces. A known variable used unquoted is split at white space and its `*?[`
  expand (`D="$HOME/Documents backup"; rm -rf $D` deletes `~/Documents`). `${NAME:-word}` is
  NAME's value when NAME is known, word (a leading `~`, `~+` or `~+0` expanded; `~-` and `~N`
  make it unknown) when NAME is known to be empty, and otherwise word only when it lies in a
  temporary folder or a git worktree; else it is unknown (`rm -rf ${CLEAN:-~}` and
  `rm -rf ${CLEAN:-~+}` in a repository ask);
- deletes recursively a repository or worktree root (a folder holding `.git`, or one directly
  holding such folders) or a `.git` folder; worktrees go through the cleanup-merged skill;
- deletes what `xargs` or GNU `parallel` hands over, or hands it to a shell: the command
  xargs runs (the word after its options, and the next one too after an option the guard does
  not know) names a delete program or a shell (`… | xargs rm`,
  `xargs -n1 dirname | xargs rm -rf`, `xargs -i rm -rf {}`, `xargs -I{} sh -c '…'`);
- runs `find … -delete` or `find … -exec rm` (also `-exec sh -c '…rm…'`, `-exec sudo rm`) from a
  folder outside a git worktree and the temporary folders;
- starts a shell that reads its commands from a pipe (`echo … | sh`) while the command names a
  delete; runs a computed command name, a shell's computed `-c` script or an `eval` of
  computed text while the text names a delete (`$(echo rm -rf x)`, `` `…` ``,
  `eval $(…)`, `sh -c "$(printf …)"`), or a computed command name with a flag cluster holding
  both `r` and `f` (`$R -rf x`; `-r` alone would also catch `pytest -rA`); nests commands
  deeper than pre_tool_git_guard.MAX_DEPTH levels, or is longer than its MAX_INPUT characters,
  while it names a delete; holds a `$'…'` string the guard cannot decode while it names a
  delete; names more than MAX_PATHS paths to delete; holds a brace expansion of more than
  MAX_BRACES texts with an alternative holding `/` or `..` (without one, everything from the
  first `{` is judged as a glob: `rm -f out/file{1..100}.txt` stays in `out`; one with an
  alternative that starts with `~` asks); or, while it names a delete or holds an `-rf`-style
  flag cluster, takes longer than DEADLINE seconds to judge or blocks in a call (a hung mount)
  past HARD_DEADLINE, after which the hook answers without waiting for it (the hook's timeout
  in hooks.json is 10 s).
Working folders: a `cd` in a loop, or anywhere once the command defines a function, makes the
folder unknown. Otherwise a `cd` is trusted for the rest of its list when what follows runs
only on its success (`cd x && …`, `cd x || exit`). When the list ends (`;`, a newline, `&`), and after
any other `cd`, relative paths are judged against both the folder before and the one after
the `cd`, and the command asks if either is protected (`cd /tmp/x; rm -rf build` from a
repository passes, `cd /tmp/gone && echo; rm -rf *` from the home folder asks). A subshell's
`cd` ends at its `)`; `env -C <folder>` and `sudo -D <folder>` count as a trusted `cd`.
Next to these folders it keeps a second set (MoreFolders) that only ever adds folders, and
judges every command in both: a `cd` behind `time`, `noglob`, `nocorrect`, `-`, `!`, an
assignment or zsh's `repeat N`; the folder before a `cd` that may be skipped (after `||`, in a
pipeline, negated); for popd and pushd any folder the command was in, for `cd -` and zsh's
`cd ±N` also an unknown one; zsh's `cd OLD NEW`; a CDPATH the command sets; a `cd` in a loop
as often as the loop runs (the words of `for x in a b`, `repeat N`, else any number of
times), also for a delete before it in the loop; the folders an `eval` or a variable holding a
command (`C='cd ~'; $C`) may end in; an unknown folder after a computed command whose text
names a `cd` (`$(echo cd) ~`, `eval "$(echo cd ~)"`); and the `cd`s of a function body where
the function is called, and of a DEBUG, RETURN or ERR trap after each command. Function
bodies and trap texts are judged again at the end of their shell, in every folder it may be
in from their definition on (`trap 'rm -rf Documents' EXIT; cd ~`).
The temporary folders: `/tmp`, `/private/tmp`, `/var/tmp`, `/var/folders`, `/private/var/folders`
and the folder that `TMPDIR`, `TEMP` or `TMP` names, unless that is a root or holds a home
folder; a path inside a home folder counts only when the temporary folder lies inside that home
too (Windows' `AppData/Local/Temp`).

It reads the command as the shell would: behind `sh -c`, `bash -c --`, `su … -c`, `csh`,
`fish`, `eval`, `$(…)`, a here-document or here-string a shell reads, wrappers (`sudo`, `env`,
`nice`, `timeout`, `arch`, `script`, `command`, `builtin`, `busybox`, `pkexec`, `runuser`),
the precommands `time`, `noglob`, `nocorrect` and `-`, zsh's `repeat N`, a one-line function
header (`function f { rm -rf x; }`), quoting and escapes in the command name (`\\rm`, `"r"m`,
`$'rm'`, zsh's `=rm`, `rm.exe`, `C:\\…\\rm.exe`, a glob such as `/bin/r[m]`), a variable that
holds the command (`R=rm; $R -rf x`), the text of `trap [--] '…' EXIT`, `~user`, `~+` and
`~+0`, brace expansion (also `{a..c}`), `cd` (also inside `if` and `{ }`), find's `-O3` and
`-D <flags>` before its folders, command names in any case. A `~` form the shell expands that
the literal reading leaves alone is judged in addition to it: a brace alternative that starts
with `~` (`{~,a}`, `~{/.zshrc,/.bashrc}`), and the folder stack's `~-`, `~N`, `~+N` and `~-N`
as every folder the command was in and an unknown one. Literal paths inside a git worktree or
a temporary folder pass, and `trash` always passes. Paths are compared without regard to case,
as the macOS and Windows file systems do (on Linux that only asks more), both as written and
with links resolved. On Windows, Git Bash paths (`/c/Users/…`, `/cygdrive/c/…`) and `C:\\…` or `C:/…`
are read as the same drive paths; on every system WSL's `/mnt/<letter>/…` is also judged as
that Windows drive.

Not seen: deletes by a script file or program the command starts (`python3 x.py`,
`shutil.rmtree` in `python -c`), `rsync --delete`, `mv` over a folder, `dd`, `diskutil`, a
remote command run through `ssh`, text written into a running shell, a link the same command
creates before deleting through it, a computed command name whose text names no delete and
has no `-rf`-style flag (`$PROG -r x` with PROG set outside the command), a non-recursive
delete of a computed target (`for f in ~/.ssh/*; do rm "$f"; done`), lines after a
here-document marker that stands inside quotes or a comment (read as a body, so a `)` in a
commit message cannot end a substitution), brace expansion of the command word, wrappers it
does not know (`watch`, `tmux`, `env -S`, `osascript`), GNU `grm` and `gfind`, `fd -X rm`,
`rmdir -p`, encoded commands piped into a shell, and PowerShell (`Remove-Item -Recurse`,
`rd /s` in `cmd`). Variables set by the user's shell profile or a SessionStart environment
file, which the hook does not inherit: such a variable counts as unknown, except in
`${NAME:-word}` with word in a temporary folder or a git worktree, where the guard reads word.
A quoted variable after a safe folder is assumed to hold no `..`. Deliberate evasion is the
job of a sandbox, not of this hook.

Not for Codex: Codex accepts only "deny" from a PreToolUse hook, and a deny would make a
guarded delete impossible, so the installer does not wire it there. Codex gets its own layers
instead: its sandbox (`workspace-write` asks before a command writes outside the workspace),
its built-in check of `rm -f`, and the prompt rules in policy/delete-guard.rules (recursive
deletes without `-f`, `xargs … rm`), which the installer copies into ~/.codex/rules/. The
written rule binds Codex where those do not reach.

An input it cannot parse is asked about when it names a delete program or holds an
`-rf`-style flag cluster (what a computed command name may run), and passes otherwise; a fault
in the guard itself asks in the same case. tests/delete_guard_differential.py checks that the
guard asks for every command the guard as it was before issue #4 asks for. Any other input,
a malformed event included, passes with exit 0. Nothing is ever denied. The shell helpers it
shares (`base`, `SHELLS`, `KEYWORDS`, `ASSIGN`, `HEREDOC`, `$'…'` decoding, the input and
depth limits) have one owner, pre_tool_git_guard.py.

Usage as a hook: reads the PreToolUse JSON on stdin, prints the "ask" decision on stdout or
nothing, and exits 0. For tests: `pre_tool_delete_guard.py --check '<command>' [cwd]` prints the
reason and exits 1, or exits 0. Test: `python3 tests/delete_guard.py`.
"""
import bisect, fnmatch, functools, importlib.util, json, os, posixpath, re, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('pre_tool_git_guard',
                                               os.path.join(HERE, 'pre_tool_git_guard.py'))
gg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gg)  # the shell parsing helpers have one owner: the git guard

WINDOWS = os.name == 'nt'
DELETERS = {'rm', 'rmdir', 'unlink'}
SHELLS = set(gg.SHELLS) | {'csh', 'tcsh', 'fish'}
WRAPPERS = {'env', 'command', 'builtin', 'exec', 'nohup', 'time', 'sudo', 'doas', 'timeout',
            'gtimeout', 'nice', 'ionice', 'caffeinate', 'stdbuf', 'noglob', 'export', 'arch',
            'script', 'xcrun', 'setsid', 'unbuffer', 'flock', 'chrt', 'taskset', 'busybox',
            'pkexec', 'runuser'}
RUNS = DELETERS | WRAPPERS | SHELLS | {'find', 'xargs', 'eval', 'su'}
FIND_EXEC = {'-exec', '-execdir', '-ok', '-okdir'}
# xargs long options that take a value (attached with `=` or the next word), and long options
# without a separate value (`--replace`, `--max-lines`, `--eof` take theirs only attached);
# short options: xargs_options
XARGS_LONG_VALUE = {'--max-args', '--max-procs', '--max-chars', '--delimiter', '--arg-file',
                    '--process-slot-var'}
XARGS_FLAGS = {'-i', '-l', '-e', '--replace', '--max-lines', '--eof', '--null',
               '--no-run-if-empty', '--verbose', '--interactive', '--exit', '--open-tty',
               '--show-limits'}
TEMP_FOLDERS = ('/tmp', '/private/tmp', '/var/tmp', '/private/var/tmp', '/var/folders',
                '/private/var/folders')
TEMP_VARIABLES = ('TMPDIR', 'TEMP', 'TMP')
SYSTEM_TREES = ('/system', '/usr', '/bin', '/sbin', '/lib', '/lib64', '/etc', '/private/etc')
WINDOWS_SYSTEM = re.compile(r'[a-z]:/(windows|program files|program files \(x86\)|programdata)'
                            r'(/|$)')
ONE_LEVEL = ('/library', '/applications', '/users', '/home', '/volumes', '/private',
             '/private/var', '/private/var/folders', '/var', '/mnt', '/media')
OTHER_HOME = re.compile(r'(/users|/home|[a-z]:/users)/[^/]+')
APP_DATA = (('Library', ('Caches', 'Logs')), ('AppData', ('Local/Temp',)))
KEYS = ('.ssh', '.gnupg')
MKTEMP = re.compile(r'\$\(\s*mktemp(\s+-[dqtu]+)*\s*(\s[^/)\s]+)?\s*\)')
DELETE_WORD = re.compile(r'(^|[\s;&|(`$/{])(rm|rmdir|unlink|xargs)\b|-delete\b', re.I)
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
DRIVE = re.compile(r'[A-Za-z]:(/|$)')
WSL_DRIVE = re.compile(r'/mnt/([A-Za-z])(/|$)')  # WSL's view of a Windows drive
UNKNOWN = None  # the value of a variable this hook cannot know
MAX_PATHS = 4096  # paths judged per command, brace expansions included; more asks
MAX_BRACES = 64   # texts one brace expansion may make; more asks
DEADLINE = 4.0    # seconds of judging (hooks.json allows 10); past it, a delete asks
HARD_DEADLINE = DEADLINE + 2.0  # the judging thread's limit, for a call that blocks (a hung mount)
MAX_FOLDERS = 8   # working folders a command may be in after `cd`s that may have failed
MAX_MORE = 32     # folders the second reading adds; past it, one unknown folder stands for the rest
MAX_LATER = 16    # function and trap bodies judged again at the end of a shell
LIST_ENDS = (';', ';;', '\n', '&', '')  # operators after which a `cd …&&` list is over
CD_WORDS = ('cd', 'pushd', 'popd', 'chdir')
CD_TEXT = re.compile(r'(^|[^\w.-])(cd|pushd|popd|chdir)([^\w.-]|$)')
LOOP_ENDS = {'for': 'done', 'while': 'done', 'until': 'done', 'select': 'done', 'foreach': 'end'}
PRECOMMANDS = ('time', 'noglob', 'nocorrect', '-', 'builtin', 'command')  # run the next word
STACK_TILDE = re.compile(r'~([+-]?\d+|[+-])')  # `~+`, `~-`, `~+1`, `~-1`, `~2`: the folder stack
RF_FLAG = re.compile(r'(^|\s)-[A-Za-z]*([rR][A-Za-z]*f|f[A-Za-z]*[rR])')
RULE = "Outside a repository, delete with the system's trash, not `rm -rf`"
SAFE_FORM = ("the system's trash (`trash` on macOS, `gio trash` on Linux, the Recycle Bin on "
             "Windows)")


class Overtime(Exception):
    """Judging took longer than DEADLINE."""


# --- words ---------------------------------------------------------------------------------

class Word:
    """One shell word: its parts with their quoting, and whether it is a redirection."""

    def __init__(self):
        self.parts = []          # (quote, text): quote '' (bare), "'" or '"'
        self.redirect = False    # the target of `>`/`<`, not an argument
        self.herestring = False  # the text after `<<<`, which a shell reads as its script

    def add(self, quote, text):
        self.parts.append((quote, text))

    def raw(self):
        return ''.join(t for _, t in self.parts)


def lex(text):
    """(commands, the texts of command substitutions in them); a here-document body is removed
    before. commands holds (Words of a simple command, the operator after it: `&&`, `||`, `;`,
    `|`, `&`, a newline, `(`, `)` or '' at the end); a `(` or `)` comes with no Words of its
    own when nothing stands before it."""
    commands, words, word, i, n, subs = [], [], None, 0, len(text), []
    redirect_next = herestring_next = False

    def close():
        nonlocal word, redirect_next, herestring_next
        if word is not None:
            word.redirect = redirect_next or herestring_next
            word.herestring = herestring_next
            redirect_next = herestring_next = False
            words.append(word)
            word = None

    def balanced(j, opener, closer):
        """Index after the closer that matches the opener before j; quotes are skipped."""
        depth, q = 1, None
        while j < n and depth:
            c = text[j]
            if q:
                if c == '\\' and q == '"':
                    j += 1
                elif c == q:
                    q = None
            elif c in '"\'':
                q = c
            elif c == '\\':
                j += 1
            elif c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
            j += 1
        return j

    while i < n:
        c = text[i]
        if c == '\\' and text[i + 1:i + 2] == '\n':
            i += 2
            continue
        if c in ' \t\r':
            close()
            i += 1
            continue
        if c == '#' and word is None:
            while i < n and text[i] != '\n':
                i += 1
            continue
        if c in ';&|()\n':
            close()
            op = text[i:i + 2] if text.startswith(('&&', '||', ';;'), i) else c
            if words or op in '()':
                commands.append((words, op))
            words = []
            i += len(op)
            continue
        if c in '<>':
            if word is not None and re.fullmatch(r'\d+', word.raw() or 'x'):
                word = None  # a file-descriptor number: `2>&1`
            close()
            j = i
            while j < n and text[j] in '<>&|':
                j += 1
            if text[i:j] in ('<', '>', '>>', '>&', '&>', '>|', '<>', '&>>', '<&'):
                redirect_next = True
            elif text[i:j] == '<<<':
                herestring_next = True
            if text[j:j + 1] == '(' and text[i:j] in ('<', '>'):
                j = balanced(j + 1, '(', ')')  # process substitution: `<(…)`
                subs.append(text[i + 2:j - 1])
                word = Word()
                word.add('', '$(' + text[i + 2:j])
                close()
            i = j
            continue
        if word is None:
            word = Word()
        if c == "'":
            j = text.find("'", i + 1)
            if j < 0:
                raise ValueError('unterminated quote')
            word.add("'", text[i + 1:j])
            i = j + 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == '\\' and j + 1 < n:
                    buf.append(text[j:j + 2] if text[j + 1] not in '"\\$`' else text[j + 1])
                    j += 2
                elif text.startswith('$(', j):
                    k = balanced(j + 2, '(', ')')
                    subs.append(text[j + 2:k - 1])
                    buf.append(text[j:k])
                    j = k
                elif text[j] == '`':
                    k = text.find('`', j + 1)
                    k = n - 1 if k < 0 else k
                    subs.append(text[j + 1:k])
                    buf.append(text[j:k + 1])
                    j = k + 1
                else:
                    buf.append(text[j])
                    j += 1
            if j >= n:
                raise ValueError('unterminated quote')
            word.add('"', ''.join(buf))
            i = j + 1
        elif c == '\\':
            word.add("'", text[i + 1:i + 2])
            i += 2
        elif text.startswith("$'", i):
            m = gg.ANSI_C.match(text, i)  # ANSI-C quoting: `$'rm'`
            if not m:
                raise ValueError('unterminated quote')
            value = gg.decode_ansi_c(m.group(1))
            if value is None:
                raise ValueError("a $'…' string the guard cannot decode")
            word.add("'", value)
            i = m.end()
        elif text.startswith('$(', i):
            j = balanced(i + 2, '(', ')')
            subs.append(text[i + 2:j - 1])
            word.add('', text[i:j])
            i = j
        elif text.startswith('${', i):
            j = balanced(i + 2, '{', '}')
            word.add('', text[i:j])
            i = j
        elif c == '`':
            j = text.find('`', i + 1)
            j = n - 1 if j < 0 else j
            subs.append(text[i + 1:j])
            word.add('', text[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r;&|()\n<>"\'\\`' and not text.startswith(
                    ('$(', '${', "$'"), j):
                j += 1
            if j == i:  # a lone `$` before a quote
                j = i + 1
            word.add('', text[i:j])
            i = j
    close()
    if words:
        commands.append((words, ''))
    return commands, subs


VAR = re.compile(r'\$(\{[^}]*\}|[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?!$-])')


class Value:
    """A word's value. text has unknown parts left empty; prefix is the known text before the
    first unknown part (None when nothing is unknown); quoted says every unknown part was in
    double quotes, so it cannot split into several words; split says an unquoted variable put
    white space into it, so the shell splits it into several words."""

    def __init__(self, text, why, glob, prefix, quoted, split=False):
        self.text, self.why, self.glob = text, why, glob
        self.prefix, self.quoted, self.split = prefix, quoted, split
        self.computed = prefix is not None

    def fields(self):
        """(text, glob) for each word the shell makes of this value."""
        if not self.split:
            return [(self.text, self.glob)]
        return [(f, self.glob and any(ch in f for ch in '*?[')) for f in self.text.split()]


DEFAULT = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)(:?)-([^}$`]*)')


def default_word(word, env):
    """The word of `${NAME:-word}` as the shell expands it: a leading `~` is a home folder."""
    if word == '~' or word.startswith('~/'):
        return env['HOME'] + word[1:]
    stack = STACK_TILDE.match(word)
    if stack and word[stack.end():stack.end() + 1] in ('', '/'):
        # `~+` and `~+0` are the working folder; `~-` and `~N` a folder of the stack
        if stack.group(1) in ('+', '+0') and isinstance(env.get('PWD'), str):
            return env['PWD'] + word[stack.end():]
        return UNKNOWN
    user = re.match(r'~([A-Za-z0-9_.-]+)(/|$)', word)
    if user:
        home = os.path.expanduser('~' + user.group(1))
        return UNKNOWN if home.startswith('~') else canon(home) + word[1 + len(user.group(1)):]
    return word


def variable(name, env):
    """The value of `$name` or `${name}`: a string, a Partial or UNKNOWN. `${NAME:-word}` and
    `${NAME-word}` give NAME's value when it is known, word when NAME is known to be empty, and
    otherwise word only when it names a folder in a temporary folder or a git worktree (NAME may
    be set by a shell profile or an environment file the hook never sees, so an unknown NAME
    stays unknown elsewhere: `${CLEAN:-~}` asks)."""
    default = DEFAULT.fullmatch(name)
    if default:
        var, colon, word = default.groups()
        word = default_word(word, env)
        if var in env:
            value = env[var]
            return word if isinstance(value, str) and colon and not value else value
        state = env.get(' state')
        if isinstance(word, str) and word and state is not None and var not in os.environ:
            path = norm(word, state.cwd)
            if path is not None and not protected(path, state.homes) and (
                    in_safe_area(path, state) or variants(path) & state.temp):
                return word
        return UNKNOWN
    return env.get(name) if NAME.fullmatch(name) else UNKNOWN


class Partial:
    """A variable whose value starts with known text and continues with something unknown:
    `PKG=$S/package-$(git rev-parse --short HEAD)`."""

    def __init__(self, prefix):
        self.prefix = prefix


def evaluate(word, env):
    out, why, glob, prefix, quoted, split = [], '', False, None, True, False

    def unknown(reason, known='', in_quotes=False):
        nonlocal why, prefix, quoted
        out.append(known)
        if prefix is None:
            prefix = ''.join(out)
        why = why or reason
        quoted = quoted and in_quotes

    for k, (quote, text) in enumerate(word.parts):
        if quote == "'":
            out.append(text)
            continue
        if quote == '' and k == 0 and (text == '~' or text.startswith('~/')):
            out.append(env['HOME'])
            text = text[1:]
        elif quote == '' and k == 0 and re.match(r'~[+-](/|$)', text):
            if text[1] == '+' and isinstance(env.get('PWD'), str):
                out.append(env['PWD'])  # `~+` is the working folder
            else:
                unknown('uses `~-`, the previous working folder')
            text = text[2:]
        elif quote == '' and k == 0 and re.match(r'~[A-Za-z0-9_.-]+(/|$)', text):
            user = re.match(r'~([A-Za-z0-9_.-]+)', text).group(1)
            home = os.path.expanduser('~' + user)  # `~name/Library`: another spelling of a home
            if home.startswith('~'):
                unknown('names the home folder of the account %s' % user)
            else:
                out.append(canon(home))
            text = text[1 + len(user):]
        pos = 0
        while pos < len(text):
            if text.startswith('$(', pos) or text[pos] == '`':
                if text[pos] == '$':
                    depth, end = 0, pos + 1
                    while end < len(text):
                        depth += (text[end] == '(') - (text[end] == ')')
                        end += 1
                        if depth == 0:
                            break
                else:
                    end = text.find('`', pos + 1) + 1 or len(text)
                unknown('is built from command output (%s)' % text[pos:end][:60],
                        in_quotes=quote == '"')
                pos = end
                continue
            m = VAR.match(text, pos)
            if m:
                name = m.group(1).strip('{}')
                value = variable(name, env)
                if isinstance(value, str):
                    out.append(value)
                    if quote == '':  # unquoted: the shell splits it and expands its globs
                        split = split or bool(re.search(r'\s', value))
                        glob = glob or any(ch in value for ch in '*?[')
                elif isinstance(value, Partial):
                    unknown('uses the variable $%s, whose value is partly computed' % name,
                            value.prefix, quote == '"')
                else:
                    plain = NAME.fullmatch(name.split(':')[0].split('[')[0])
                    unknown('uses the variable $%s, which may be empty or hold anything' % name
                            if plain else 'uses a shell parameter', in_quotes=quote == '"')
                pos = m.end()
                continue
            ch = text[pos]
            if quote == '' and ch in '*?[':
                glob = True
            out.append(ch)
            pos += 1
    return Value(''.join(out), why, glob, prefix, quoted, split)


# --- paths ---------------------------------------------------------------------------------
# A path is a string with forward slashes: `/…` on every system, `c:/…` on Windows too; a
# variant for comparison may also be a drive path elsewhere (WSL's `/mnt/c/…` as `c:/…`).

def canon(path):
    """The path with forward slashes; on Windows Git Bash's `/c/…` and `/cygdrive/c/…` become
    `c:/…`."""
    if not WINDOWS:
        return path
    path = path.replace('\\', '/')
    if path.startswith('//?/'):
        path = path[4:]
    m = re.match(r'(?:/cygdrive)?/([A-Za-z])(/|$)', path)
    if m:
        path = m.group(1) + ':/' + path[m.end():]
    return path


def split_drive(path):
    if DRIVE.match(path):
        return path[:2], path[2:] or '/'
    return '', path


def is_abs(path):
    return path.startswith('/') or (WINDOWS and bool(DRIVE.match(path)))


def norm(path, cwd):
    """The absolute, normalized form of path, or None when it is relative and cwd unknown."""
    path = canon(path)
    if not is_abs(path):
        if cwd is None:
            return None
        path = cwd.rstrip('/') + '/' + path
    drive, rest = split_drive(path)
    return drive + posixpath.normpath('/' + rest.lstrip('/'))


def parent(path):
    drive, rest = split_drive(path)
    return drive + posixpath.dirname(rest)


def is_root(path):
    return split_drive(path)[1] == '/'


def under(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


@functools.lru_cache(maxsize=None)
def variants(path):
    """The path as written and with links resolved, both case-folded, and WSL's `/mnt/<drive>/…`
    also as the Windows drive path it is."""
    found = {path.casefold()}
    resolvable = DRIVE.match(path) if WINDOWS else path.startswith('/')
    if resolvable and os.path.isabs(path):
        try:
            found.add(canon(os.path.realpath(path)).casefold())
        except (OSError, ValueError):
            pass
    for v in list(found):
        m = WSL_DRIVE.match(v)
        if m:
            found.add(m.group(1) + ':/' + v[m.end():])
    return frozenset(found)


def protected(path, homes):
    """A reason when deleting this path needs the user, or None."""
    for p in variants(path):
        if is_root(p):
            return 'the whole disk'
        up = parent(p)
        if is_root(up):
            return 'a top-level folder of the disk'
        # any account's home: `/Users/<name>`, `/home/<name>`, `C:/Users/<name>`
        other = OTHER_HOME.match(p)
        for home_f in set(homes) | ({other.group(0)} if other else set()):
            if p == home_f:
                return 'a home folder'
            if under(home_f, p):
                return 'a folder that holds a home folder'
            if up == home_f:
                return 'something directly in a home folder'
            for folder, free in APP_DATA:
                data = home_f + '/' + folder.casefold()
                if under(p, data) and not any(
                        under(p, data + '/' + d.casefold()) and p != data + '/' + d.casefold()
                        for d in free):
                    return 'app data in ~/%s (only %s are free to delete in)' % (
                        folder, ' and '.join(free))
            if any(under(p, home_f + '/' + d) for d in KEYS):
                return 'keys in ~/.ssh or ~/.gnupg'
        if any(under(p, t) for t in SYSTEM_TREES) or WINDOWS_SYSTEM.match(p):
            return 'a system folder'
        if up in ONE_LEVEL:
            return 'a folder directly in %s' % up
    return None


@functools.lru_cache(maxsize=None)
def git_root(path):
    """The folder holding `.git` at or above path, or None."""
    p = path
    for _ in range(256):
        if os.path.exists(p.rstrip('/') + '/.git'):
            return p
        up = parent(p)
        if up == p:
            return None
        p = up
    return None


def in_safe_area(path, state):
    """Inside a git worktree, or inside a temporary folder; a path in a home folder counts only
    when that temporary folder lies inside the same home."""
    if git_root(path) is not None:
        return True
    for v in variants(path):
        if not any(under(v, r) and v != r and not any(under(v, h) and under(h, r)
                                                       for h in state.homes)
                   for r in state.temp):
            return False
    return True


@functools.lru_cache(maxsize=None)
def holds_repository(path):
    """True for a repository or worktree root, a `.git` folder, or a folder that directly holds
    repositories (a folder of worktrees)."""
    if posixpath.basename(path) == '.git' or os.path.exists(path.rstrip('/') + '/.git'):
        return True
    try:
        with os.scandir(path) as it:
            for k, entry in enumerate(it):
                if k > 2000:
                    break
                if entry.is_dir(follow_symlinks=False) and os.path.exists(
                        os.path.join(entry.path, '.git')):
                    return True
    except OSError:
        pass
    return False


def glob_base(text):
    """The folder before the first path component with a glob character."""
    parts = text.split('/')
    for k, part in enumerate(parts):
        if any(ch in part for ch in '*?['):
            return '/'.join(parts[:k]) or ('/' if text.startswith('/') else '.')
    return text


# --- the judgement -------------------------------------------------------------------------

class State:
    def __init__(self, cwd, home, homes, temp, env, text=''):
        self.cwd = cwd
        self.home = home        # what `~` and `$HOME` mean
        self.homes = homes      # every spelling of the user's home, case-folded
        self.temp = temp        # the temporary folders, case-folded
        self.env = dict(env)
        self.text = text        # the whole command, for a shell that reads it from a pipe
        self.budget = [MAX_PATHS]  # paths left to judge, shared with the child states
        self.deadline = time.monotonic() + DEADLINE
        self.alt = ()  # other folders the command may be in: a `cd` that may have failed
        self.ext = ()  # the folders of the second reading (MoreFolders), judged next to these
        self.landing = []  # folders a text this shell runs (eval, `$C`) may end in
        self.shell = Shell()

    def folders(self):
        return [self.cwd] + list(self.alt)

    def set_folders(self, folders):
        unique = []
        for f in folders:
            if f not in unique:
                unique.append(f)
        if len(unique) > MAX_FOLDERS:
            unique = unique[:MAX_FOLDERS - 1] + [None]
        self.cwd, self.alt = unique[0], tuple(unique[1:])

    def check_time(self):
        if time.monotonic() > self.deadline:
            raise Overtime()

    @classmethod
    def start(cls, cwd, home, text):
        homes = set()
        for h in (home, os.environ.get('HOME'), os.environ.get('USERPROFILE') if WINDOWS
                  else None, os.path.expanduser('~')):
            h = norm(h, None) if h else None
            if h and not is_root(h):
                homes |= variants(h)
        env, temp = {'HOME': home}, set()
        for t in TEMP_FOLDERS:
            temp |= variants(t)
        mktemp = None
        for name in TEMP_VARIABLES:
            value = os.environ.get(name) or ''
            t = norm(value, None) if value else None
            if not t or is_root(t) or any(under(h, v) for v in variants(t) for h in homes) \
                    or any(parent(v) in homes for v in variants(t)):
                continue  # not a usable temporary folder: `TMPDIR=~` must not free the home
            env[name] = t  # Bash inherits the client's temporary folder
            temp |= variants(t)
            mktemp = mktemp or t
        if WINDOWS and os.environ.get('USERPROFILE'):
            env['USERPROFILE'] = norm(os.environ['USERPROFILE'], None)
        state = cls(cwd, home, frozenset(homes), frozenset(temp), env, text)
        state.mktemp = mktemp or '/tmp'
        return state

    def values(self):
        env = dict(self.env)
        env['PWD'] = self.cwd if self.cwd is not None else UNKNOWN
        env[' state'] = self  # not a shell name: for `${NAME:-word}`
        return env

    def child(self, text='', shared=False):
        """A state for a nested text; shared when this shell runs it (eval, `$C`, a function or
        trap body), so its folders, functions and traps stay in this shell."""
        state = State(self.cwd, self.home, self.homes, self.temp, self.env, text or self.text)
        state.mktemp, state.budget, state.deadline = self.mktemp, self.budget, self.deadline
        state.alt = self.alt
        if shared:
            state.shell = self.shell
        return state


class Shell:
    """What the second reading collects about one shell process: every folder it may have been
    in (where popd, `cd -`, `~-` and a function or trap body can lead), the function and trap
    bodies it may run later, the folder changes in those bodies, and a CDPATH it set."""

    def __init__(self):
        self.seen = []
        self.later = []    # [kind, item, folders]: a function body ('body', its commands) or a
        #                    trap ('text'), judged at the end in the folders the shell may be in
        #                    from its definition on
        self.moves = []    # (function name, or None for a DEBUG trap; cd specs of its body):
        #                    folder changes that happen where the function is called
        self.cdpath = None
        self.keys = set()

    def run_later(self, kind, item, key):
        if key not in self.keys and len(self.later) < MAX_LATER:
            self.keys.add(key)
            self.later.append([kind, item, []])


def safe_prefix(value, state):
    """True when the unknown part of a computed path sits in double quotes after a literal
    folder inside a git worktree or a temporary folder: `"$S/package-$C"`. The guard then judges
    the path as if the unknown part were empty; it assumes that part holds no `..`."""
    if not value.quoted or not value.prefix or '/' not in canon(value.prefix):
        return False
    prefix = canon(value.prefix)
    folder = prefix[:prefix.rfind('/')]
    path = norm(folder or '/', state.cwd)
    return path is not None and not protected(path, state.homes) and in_safe_area(path, state)


def braces(word, text):
    """The texts brace expansion makes of an unquoted `{a,b}`, `{1..3}` or `{a..c}`, or None when
    it makes more than MAX_BRACES."""
    if not any(q == '' and '{' in t for q, t in word.parts):
        return [text]
    out, todo = [], [text]
    while todo:
        t = todo.pop()
        m = re.search(r'\{([^{}]*)\}', t)
        if not m or (',' not in m.group(1) and '..' not in m.group(1)):
            out.append(t)
            continue
        inner = m.group(1)
        if ',' in inner:
            choices = inner.split(',')
        else:
            a, _, b = inner.partition('..')
            if re.fullmatch(r'-?\d+', a) and re.fullmatch(r'-?\d+', b):
                a, b = int(a), int(b)
            elif len(a) == len(b) == 1 and a.isalpha() and b.isalpha():
                a, b = ord(a), ord(b)
            else:
                a = b = None
            if a is None:
                choices = [inner.partition('..')[0], inner.partition('..')[2]]
            elif abs(b - a) >= MAX_BRACES:
                return None
            else:
                step = 1 if b >= a else -1
                letters = not re.fullmatch(r'-?\d+', inner.partition('..')[0])
                choices = [chr(x) if letters else str(x) for x in range(a, b + step, step)]
        todo += [t[:m.start()] + c + t[m.end():] for c in choices]
        if len(out) + len(todo) > MAX_BRACES:
            return None
    return out


TOO_MANY_BRACES = 'uses a brace expansion of more than %d paths (%%s)' % MAX_BRACES


def brace_as_glob(text):
    """For a brace expansion over MAX_BRACES: the text with everything from its first `{` read
    as a glob (`out/file{1..100}.txt` stays in `out`), or None (ask) when the expansion could
    lead elsewhere: a `/` anywhere from the first `{` on, an alternative holding `..`, or a last
    path component that could become `.` or `..` (an alternative that is empty or only dots,
    or literal text in that component that is only dots)."""
    k = text.find('{')
    if k < 0 or '/' in text[k:]:
        return None
    component = text[text.rfind('/', 0, k) + 1:]
    for m in re.finditer(r'\{([^{}]*)\}', component):
        inner = m.group(1)
        alternatives = inner.split(',') if ',' in inner else []
        if any('..' in a or not a.strip('.') for a in alternatives):
            return None
    literal = re.sub(r'\{[^{}]*\}', '', component)
    if literal and not literal.strip('.'):
        return None
    return text[:k] + '*'


def judge_targets(targets, recursive, state, program):
    for word in targets:
        value = evaluate(word, state.values())
        if value.computed and recursive and not safe_prefix(value, state):
            return 'deletes recursively a target that %s (%s)' % (value.why, word.raw())
        for field, glob in value.fields():
            texts = braces(word, field)
            if texts is None:
                texts, glob = [brace_as_glob(field)], True
                if texts[0] is None:
                    return 'deletes and ' + TOO_MANY_BRACES % word.raw()
            for text in texts:
                reason = judge_path(text, glob, word, recursive, state, program)
                if reason:
                    return reason
        more = more_texts(word, state)
        if more is None:
            return 'deletes and ' + TOO_MANY_BRACES % word.raw() + ' with a `~` alternative'
        for path, glob in more:
            if path is None:
                if recursive:
                    return ('deletes recursively a target in a folder of the folder stack, which '
                            'the delete guard cannot know (%s)' % word.raw())
                continue
            reason = judge_path(path, glob, word, recursive, state, program)
            if reason:
                return reason
    return None


def more_texts(word, state):
    """The paths a `~` form in word makes that the first reading leaves literal (issue #4): an
    alternative of a brace expansion that starts with `~` (`{~,a}`, `~{/.zshrc,/.bashrc}`: the
    shell expands braces first), and the folder stack's `~+0`, `~-`, `~1`, `~-1`. They are
    judged in addition to the literal reading, never in its place. Returns [(path or None for a
    folder it cannot know, glob)], or None when a brace expansion over MAX_BRACES has an
    alternative that starts with `~`."""
    if not word.parts or word.parts[0][0] != '' or '~' not in word.parts[0][1]:
        return []
    first = word.parts[0][1]
    lead = re.match(r'~[^/{]*', first)
    literal = Word()  # the word with its leading `~` form kept as text
    if lead:
        literal.add("'", lead.group(0))
        first = first[lead.end():]
    if first:
        literal.add('', first)
    literal.parts += word.parts[1:]
    stack = bool(lead and STACK_TILDE.fullmatch(lead.group(0)))
    out = []
    for field, glob in evaluate(literal, state.values()).fields():
        texts = braces(word, field)
        if texts is None:
            if re.search(r'(^|[{,])~', field):
                return None
            continue
        for text in texts:
            if text.startswith('~') and (stack or text != field):
                out += [(None if f is None else f + rest, glob)
                        for f, rest in tilde_folders(text, state)]
    return out


def tilde_folders(text, state):
    """[(folder or None, the rest of text)] for a text that starts with a `~` form."""
    m = re.match(r'~([^/]*)', text)
    tag, rest = m.group(1), text[m.end():]
    if tag == '':
        return [(state.home, rest)]
    if tag in ('+', '+0'):
        return [(state.cwd, rest)]
    if re.fullmatch(r'[+-]?\d+|-', tag):
        return [(f, rest) for f in state.shell.seen if f is not None] + [(None, rest)]
    if re.fullmatch(r'[A-Za-z0-9_.-]+', tag):
        home = os.path.expanduser('~' + tag)
        return [(None if home.startswith('~') else canon(home), rest)]
    return []


def judge_path(text, glob, word, recursive, state, program):
    state.check_time()
    state.budget[0] -= 1
    if state.budget[0] < 0:
        return 'names more paths than the delete guard reads (%d)' % MAX_PATHS
    if glob:
        text = glob_base(text)
    if not text:
        return None  # `rm "$f"` with f unknown: a plain file, empty or not
    path = norm(text, state.cwd)
    if path is None:
        if recursive:
            return ('deletes recursively a relative path (%s) after a `cd` that may not have '
                    'happened or went to a computed folder' % word.raw())
        return None
    if glob:
        # what the glob reaches: `~/*` deletes what is directly in the home folder;
        # `~/Documents/*` empties a protected folder; `/tmp/x.*` stays inside /tmp
        reason = protected(path.rstrip('/') + '/x', state.homes) or (
            any(under(v, h) for v in variants(path) for h in state.homes)
            and protected(path, state.homes))
        if reason:
            return '%s with a glob in %s: %s (%s)' % (program, path, reason, word.raw())
        return None
    reason = protected(path, state.homes)
    if reason:
        return '%s %s (%s)' % (program, reason, word.raw())
    if recursive and holds_repository(path):
        return ('deletes recursively a repository, worktree or folder of worktrees (%s); '
                'worktrees go through the cleanup-merged skill' % word.raw())
    return None


def rm_args(words):
    """(recursive, targets) for the arguments of rm; quoting does not hide an option."""
    recursive, targets, options = False, [], True
    for w in words:
        raw = w.raw()
        if options and raw == '--':
            options = False
        elif options and raw.startswith('-') and len(raw) > 1:
            stem = raw.split('=', 1)[0]
            if stem.startswith('--'):
                recursive = recursive or (len(stem) >= 3 and '--recursive'.startswith(stem))
            elif re.search(r'[rR]', raw):
                recursive = True
        else:
            targets.append(w)
    return recursive, targets


def name_of(word):
    """The program a command word names: zsh runs `=rm` as rm's full path, Git Bash `rm.exe`."""
    name = gg.base(word.raw().lstrip('=').replace('\\', '/')).casefold()
    return name[:-4] if name.endswith('.exe') else name


def unwrap(words):
    """The words from the program a wrapper (`sudo`, `env`, `nice -n 5`, `arch -arm64`) runs."""
    for _ in range(gg.MAX_DEPTH + 1):
        if not words or name_of(words[0]) not in WRAPPERS:
            return words
        rest = words[1:]
        k = next((k for k, w in enumerate(rest) if name_of(w) in RUNS), None)
        if k is None:
            return []
        words = rest[k:]
    return words


def deletes_inside(words):
    """True when words run a delete program, directly or as a shell command string."""
    words = unwrap(words)
    if not words:
        return False
    name = name_of(words[0])
    return name in DELETERS or ((name in SHELLS or name in ('eval', 'su', 'find', 'xargs'))
                                and has_delete_word(' '.join(w.raw() for w in words)))


def judge_find(words, state):
    raws = [w.raw() for w in words]
    exec_rm = False
    for k, r in enumerate(raws):
        if r in FIND_EXEC:
            end = next((j for j in range(k + 1, len(raws)) if raws[j] in (';', '+')), len(raws))
            exec_rm = exec_rm or deletes_inside(words[k + 1:end])
    if '-delete' not in raws and not exec_rm:
        return None
    k, starts = 0, []
    while k < len(words):
        if raws[k] in ('-H', '-L', '-P', '-E', '-X', '-s', '-x', '-d', '--') or re.fullmatch(
                r'-O\d*', raws[k]):
            k += 1
        elif raws[k] == '-D' and k + 1 < len(words):  # GNU find's debug option and its value
            k += 2
        elif raws[k] == '-f' and k + 1 < len(words):
            starts.append(words[k + 1])
            k += 2
        else:
            break
    while k < len(words) and not raws[k].startswith(('-', '(', '!')):
        starts.append(words[k])
        k += 1
    if not starts:
        starts = [Word()]
        starts[0].add("'", '.')
    for word in starts:
        value = evaluate(word, state.values())
        if value.computed and not safe_prefix(value, state):
            return 'runs find with a delete from a folder that %s (%s)' % (value.why, word.raw())
        for field, glob in value.fields():
            texts = braces(word, glob_base(field) if glob else field)
            if texts is None:
                texts = [brace_as_glob(field)]
                if texts[0] is None:
                    return 'runs find with a delete and ' + TOO_MANY_BRACES % word.raw()
                texts = [glob_base(texts[0])]
            for text in texts:
                reason = judge_find_start(text, word, state)
                if reason:
                    return reason
        more = more_texts(word, state)
        if more is None:
            return ('runs find with a delete and ' + TOO_MANY_BRACES % word.raw() +
                    ' with a `~` alternative')
        for path, glob in more:
            reason = judge_find_start(glob_base(path) if glob and path else path, word, state)
            if reason:
                return reason
    return None


def judge_find_start(text, word, state):
    """The reason a find with a delete from text needs the user, or None; text None is a folder
    the guard cannot know."""
    state.check_time()
    path = None if text is None else norm(text, state.cwd)
    if path is None:
        return ('runs find with a delete from a relative folder after a `cd` that may not have '
                'happened or went to a computed folder')
    reason = protected(path, state.homes)
    if reason:
        return 'runs find with a delete in %s (%s)' % (reason, word.raw())
    if not in_safe_area(path, state):
        return ('runs find with a delete outside a git worktree and the temporary folders (%s)'
                % word.raw())
    return None


def xargs_options(args):
    """(index of the command xargs runs, sure): its options read letter by letter. A letter in
    `nILPsdEJRSa` takes the rest of its cluster or the next word, one in `iel` the rest of its
    cluster; sure is False after an option the guard does not fully know (an abbreviated long
    option such as `--max-a`, a letter it has no rule for)."""
    k = 0
    while k < len(args):
        raw = args[k].raw()
        if not raw.startswith('-') or raw == '-':
            return k, True
        if raw == '--':
            return k + 1, True
        if raw.startswith('--'):
            stem = raw.split('=', 1)[0]
            if stem in XARGS_LONG_VALUE:
                k += 1 if '=' in raw else 2
            elif stem in XARGS_FLAGS:
                k += 1
            else:
                return k, False
            continue
        letters, step = raw[1:], 1
        for j, ch in enumerate(letters):
            if ch in 'nILPsdEJRSa':
                step = 2 if j == len(letters) - 1 else 1
                break
            if ch in 'iel':
                break
            if ch not in '0rtxpo':
                return k, False
        k += step
    return k, True


def judge_xargs(args, state, depth):
    k, sure = xargs_options(args)
    named = [name_of(w) for w in args] if not sure else []
    rest = unwrap(args[k:])
    if rest and sure:
        named = [name_of(rest[0])]
    if DELETERS & set(named):
        return ('deletes what xargs hands over (%s): xargs splits paths on spaces, so the '
                'targets are not the paths that were listed' % ' '.join(w.raw() for w in args))
    if SHELLS & set(named):
        return ('hands what xargs reads to a shell (%s), which may run it as commands'
                % ' '.join(w.raw() for w in args))
    if not sure:  # an option it does not know may take the next words: try every start
        for j in range(k, len(args)):
            tail = unwrap(args[j:])
            if tail and deletes_inside(tail):
                return ('hands what xargs reads to a program that deletes (%s)'
                        % ' '.join(w.raw() for w in tail))
    if not rest:
        return None
    if deletes_inside(rest):
        return ('hands what xargs reads to a program that deletes (%s)'
                % ' '.join(w.raw() for w in rest))
    return judge_command(rest, state, depth + 1)


def shell_script(args, state):
    """(script text, reads stdin, computed) for `sh -c '…'`, `bash -lc -- '…'`,
    `su user -c '…'`, `bash <<< '…'`; computed when the script is built at run time."""
    script = None
    for k, w in enumerate(args):
        raw = w.raw()
        if re.fullmatch(r'-[A-Za-z]*c[A-Za-z]*', raw) or raw == '--command':
            rest = [x for x in args[k + 1:] if x.raw() != '--']
            if not rest:
                return '', False, False
            script = rest[0]
            break
    if script is None:
        herestrings = [w for w in args if w.herestring]
        script = herestrings[0] if herestrings else None
    if script is not None:
        value = evaluate(script, state.values())
        return (script.raw() if value.computed else value.text), False, value.computed
    plain = [w for w in args if not w.redirect and not w.raw().startswith('-')]
    return '', not plain, False  # no script file: the shell reads its commands from stdin


def too_deep(text):
    return ('nests commands deeper than the delete guard reads, and names a delete'
            if has_delete_word(text) else None)


def judge_command(words, state, depth):
    """The reason a simple command needs the user, or None: the forms the guard read before
    issue #4 (judge_core), then the ones it added (judge_added_forms)."""
    return judge_core(words, state, depth) or judge_added_forms(words, state, depth)


def judge_here(text, state, depth):
    """judge for a text this shell runs itself (eval, `$C`): its folder changes, functions and
    traps stay in this shell, so the folders it may end in go to state.landing."""
    child = state.child(shared=True)
    reason = judge(text, child, depth, own=False)
    state.landing.extend(child.folders() + list(child.ext))
    return reason


def strip_head(words):
    """(the words from the program a command runs, flags), past what judge_core skips (keywords,
    assignments, `{`, `}`) and also past `!`, the precommands `time`, `noglob`, `nocorrect`, `-`,
    `builtin` and `command`, zsh's `repeat N`, and a `function NAME` header. flags holds
    'negated', 'repeat' and 'repeat-do' (`repeat N do … done`)."""
    flags = set()
    words = [w for w in words if not w.redirect]
    while words:
        raw = words[0].raw()
        if raw == '!':
            flags.add('negated')
            words = words[1:]
        elif raw in gg.KEYWORDS or raw in ('{', '}') or raw in PRECOMMANDS or \
                gg.ASSIGN.fullmatch(raw):
            words = words[1:]
        elif raw == 'repeat' and len(words) > 1:
            flags.add('repeat')
            words = words[2:]
            if words and words[0].raw() == 'do':
                flags.add('repeat-do')
        elif raw == 'function' and len(words) > 1:
            words = words[1:] if words[1].raw() == '{' else words[2:]
        else:
            break
    return words, flags


def judge_added_forms(words, state, depth):
    """Forms judge_core does not read (issue #4): the command behind a precommand, `repeat N` or
    a one-line function header (`function f { rm -rf ~/Library; }`), and `trap` behind them or
    with `--`. It only adds reasons to ask."""
    if depth > gg.MAX_DEPTH:
        return None  # judge_core has answered
    herestrings = [w for w in words if w.herestring]
    plain = [w for w in words if not w.redirect]
    core = plain
    while core and (gg.ASSIGN.fullmatch(core[0].raw()) or core[0].raw() in gg.KEYWORDS
                    or core[0].raw() in ('{', '}')):
        core = core[1:]
    rest, _ = strip_head(plain)
    if rest and len(rest) < len(core):
        reason = judge_command(rest + herestrings, state, depth + 1)
        if reason:
            return reason
    if rest and rest[0].raw() == 'trap':
        return judge_trap(rest, state, depth)
    return None


def judge_trap(words, state, depth):
    """`trap [--] ACTION SIGNAL…`: the action is judged here, and again at the end of the shell
    in every folder it may be in then (judge_later), with its folder changes counted as ones
    that may happen at any later point (a DEBUG trap runs before each command)."""
    args = words[1:]
    if args and args[0].raw() == '--':
        args = args[1:]
    elif args and args[0].raw().startswith('-'):
        return None  # `trap -p`, `trap -l`: print
    if len(args) < 2 or args[0].raw() in ('', '-'):
        return None  # no action, or a reset
    value = evaluate(args[0], state.values())
    text = args[0].raw() if value.computed else value.text
    if value.computed and has_delete_word(text):
        return 'sets a computed trap that names a delete (%s)' % text[:80]
    reason = judge(text, state.child(), depth + 1)
    if reason:
        return reason
    state.shell.run_later('text', text, ('text', text))
    if {w.raw().upper().lstrip('SIG') for w in args[1:]} & {'DEBUG', 'RETURN', 'ERR', 'ZERR'}:
        state.shell.moves.append((None, moves_in(text, state)))  # runs around every command
    return None


def judge_core(words, state, depth):
    raws = ' '.join(w.raw() for w in words)
    if depth > gg.MAX_DEPTH:
        return too_deep(raws)
    state.check_time()
    herestrings = [w for w in words if w.herestring]
    words = [w for w in words if not w.redirect]
    while words and (gg.ASSIGN.fullmatch(words[0].raw()) or words[0].raw() in gg.KEYWORDS
                     or words[0].raw() in ('{', '}')):
        words = words[1:]
    if not words:
        return None
    head = evaluate(words[0], state.values())
    if any(q != "'" and ('$' in t or '`' in t) for q, t in words[0].parts):
        if head.computed:
            if has_delete_word(raws):
                return ('runs a command whose name is computed, and the command names a delete '
                        '(%s)' % raws[:80])
            if any(re.fullmatch(r'-[A-Za-z]*[rR][A-Za-z]*', w.raw()) and 'f' in w.raw()
                   for w in words[1:]):
                return 'runs a computed command name with a recursive flag (%s)' % raws[:80]
        elif head.text.strip():
            # `R=rm; $R -rf x` or `CMD='rm -rf x'; $CMD`: read the command as the shell does
            return judge_here(head.text + ' ' + ' '.join(w.raw() for w in words[1:]),
                              state, depth + 1)
    name = name_of(words[0])
    if any(ch in name for ch in '*?[') and any(q == '' and any(ch in t for ch in '*?[')
                                               for q, t in words[0].parts):
        # a glob in the command name (`/bin/r[m]`): the program it can match
        name = next((p for p in sorted(DELETERS) + sorted(RUNS | {'parallel', 'trap'})
                     if fnmatch.fnmatchcase(p, name)), name)
    args = words[1:] + herestrings
    if name in DELETERS:
        if name == 'rm':
            recursive, targets = rm_args(words[1:])
        else:
            recursive = False
            targets = [w for w in words[1:] if not w.raw().startswith('-')]
        return judge_targets(targets, recursive, state, 'deletes')
    if name == 'find':
        return judge_find(words[1:], state)
    if name == 'xargs':
        return judge_xargs(words[1:], state, depth)
    if name == 'parallel' and has_delete_word(raws):
        return 'hands what GNU parallel reads to a delete (%s)' % raws[:80]
    if name in SHELLS or name == 'su':
        script, reads_stdin, computed = shell_script(args, state)
        if computed and has_delete_word(script):
            return ('starts a shell whose script is computed, and the script names a delete '
                    '(%s)' % script[:80])
        if script:
            return judge(script, state.child(script), depth + 1)
        if reads_stdin and name != 'su' and has_delete_word(state.text):
            return ('starts a shell that reads its commands from a pipe, and the command names '
                    'a delete')
        return None
    if name == 'eval':
        parts, computed = [], False
        for w in words[1:]:
            value = evaluate(w, state.values())
            computed = computed or value.computed
            parts.append(w.raw() if value.computed else value.text)
        if computed and has_delete_word(' '.join(parts)):
            return 'evaluates computed text that names a delete (%s)' % raws[:80]
        return judge_here(' '.join(parts), state, depth + 1)
    if name == 'trap' and len(words) > 1 and not words[1].raw().startswith('-'):
        # `trap '…' EXIT`: the shell runs the text later
        value = evaluate(words[1], state.values())
        text = words[1].raw() if value.computed else value.text
        if value.computed and has_delete_word(text):
            return 'sets a computed trap that names a delete (%s)' % raws[:80]
        return judge(text, state.child(), depth + 1)
    if name in WRAPPERS:
        folder = wrapper_chdir(name, words[1:])
        if folder is not None:  # `env -C <folder> …`, `sudo -D <folder> …`
            value = evaluate(folder, state.values())
            state = state.child()
            state.cwd = None if value.computed else norm(value.text, state.cwd)
            state.alt = ()
        inner = unwrap(words)
        return judge_command(inner, state, depth + 1) if inner else None
    return None


# per wrapper: (its change-folder short option, its long one, short options taking a value,
# long options taking a value)
CHDIR_OPTIONS = {
    'env': ('C', '--chdir', 'uSP', {'--unset', '--split-string'}),
    'sudo': ('D', '--chdir', 'ugpCrtUTh', {'--user', '--group', '--prompt', '--close-from',
                                         '--role', '--type', '--other-user', '--command-timeout',
                                         '--host'}),
}


def tail_word(word, skip):
    """The word without its first skip characters (which lie in its first part), or None."""
    if not word.parts or len(word.parts[0][1]) < skip:
        return None
    rest = Word()
    rest.add(word.parts[0][0], word.parts[0][1][skip:])
    for part in word.parts[1:]:
        rest.add(*part)
    return rest


def wrapper_chdir(name, args):
    """The folder word of `env -C <folder>` (also `-iC`, `-C<folder>`, `--chdir[=]<folder>`,
    after `-u NAME`) or `sudo -D <folder>`, before the command the wrapper runs; or None."""
    if name not in CHDIR_OPTIONS:
        return None
    letter, long_name, valued, long_valued = CHDIR_OPTIONS[name]
    k = 0
    while k < len(args):
        w, raw = args[k], args[k].raw()
        if raw == long_name:
            return args[k + 1] if k + 1 < len(args) else None
        if raw.startswith(long_name + '='):
            return tail_word(w, len(long_name) + 1)
        if raw in long_valued:
            k += 2
            continue
        if raw.startswith('--') and raw != '--':
            k += 1
            continue
        cluster = re.match(r'-([A-Za-z]+)', raw)
        if cluster and raw != '-':
            letters = cluster.group(1)
            for j, ch in enumerate(letters):
                if ch == letter:
                    if len(raw) > 2 + j:
                        return tail_word(w, 2 + j)
                    return args[k + 1] if k + 1 < len(args) else None
                if ch in valued:  # the rest of the cluster, or the next word, is its value
                    k += 1 if len(raw) > 2 + j else 2
                    break
            else:
                k += 1
            continue
        if raw == '-' or gg.ASSIGN.fullmatch(raw):
            k += 1
            continue
        return None
    return None


def track(words, state, trusted=True):
    """Follow `cd` and literal assignments, so later commands resolve against them; True when
    a `cd` changed the working folders. A trusted `cd` (what follows runs on its success alone:
    `cd x && …`, `cd x || exit`) sets the folder; any other leaves both the folder before and
    the one after possible, since the `cd` may have failed."""
    words = [w for w in words if not w.redirect]
    while words and (words[0].raw() in gg.KEYWORDS or words[0].raw() in ('{', '}', 'if')
                     or name_of(words[0]) in ('builtin', 'command')):
        words = words[1:]
    if not words:
        return False
    first = words[0].raw()
    if first in ('cd', 'pushd', 'chdir'):
        target = [w for w in words[1:] if not w.raw().startswith('-') or w.raw() == '-']
        old = state.folders()
        if not target:
            new = [state.home]
        else:
            value = evaluate(target[0], state.values())
            new = [None] if value.computed or value.text == '-' else [
                norm(value.text, f) for f in old]
        state.set_folders(new if trusted else new + old)
        return True
    if first in ('export', 'local', 'declare', 'readonly', 'typeset'):
        words = [w for w in words[1:] if not w.raw().startswith('-')]
    if words and all(gg.ASSIGN.fullmatch(w.raw()) for w in words):
        for w in words:
            name = w.raw().split('=', 1)[0]
            rest = Word()
            first_quote, first_text = w.parts[0]
            rest.add(first_quote, first_text.split('=', 1)[1])
            for part in w.parts[1:]:
                rest.add(*part)
            if MKTEMP.fullmatch(rest.raw()) and all(q == '' for q, _ in rest.parts):
                # `T=$(mktemp -d)`: a new folder in the temporary folder
                state.env[name] = state.mktemp + '/mktemp-' + name
                continue
            value = evaluate(rest, state.values())
            if value.glob:
                state.env[name] = UNKNOWN
            elif value.computed:
                state.env[name] = Partial(value.prefix) if value.prefix else UNKNOWN
            else:
                state.env[name] = value.text
    elif first in ('read', 'for', 'select'):
        for w in words[1:]:
            if NAME.fullmatch(w.raw()):
                state.env[w.raw()] = UNKNOWN
    return False


def strip_heredocs(text):
    """The text without here-document bodies, and (command line, body) pairs. Unlike
    gg.strip_heredocs it also removes a body whose marker stands inside quotes, as in
    `git commit -m "$(cat <<'EOF' … EOF)"`, so a `)` in that body cannot end the substitution.
    The closing line is looked up in an index, so the time stays linear in the input."""
    lines, out, bodies, i = text.split('\n'), [], [], 0
    exact, tabbed = {}, {}
    for k, line in enumerate(lines):
        exact.setdefault(line, []).append(k)
        tabbed.setdefault(line.lstrip('\t'), []).append(k)
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for dash, word in gg.HEREDOC.findall(line.replace('<<<', '')):
            found = (tabbed if dash else exact).get(word, [])
            k = bisect.bisect_left(found, i)
            if k < len(found):
                bodies.append((line, '\n'.join(lines[i:found[k]])))
                i = found[k] + 1
    return '\n'.join(out), bodies


def judge(text, state, depth=0, own=True):
    """The reason text needs the user, or None. own: text is a shell of its own (the command,
    `sh -c`, a substitution), so the function and trap bodies it defines are judged at its end;
    a text this shell runs (judge_here, judge_later) leaves them to the shell's own judge."""
    if depth > gg.MAX_DEPTH:
        return too_deep(text)
    text, bodies = strip_heredocs(text.replace('\\\n', ' '))
    for line, body in bodies:
        if {name_of_text(w) for w in re.findall(r'[\w./\\-]+', line)} & SHELLS:
            reason = judge(body, state.child(body), depth + 1)
            if reason:
                return reason
    commands, subs = lex(text)
    for inner in subs:
        reason = judge(inner, state.child(), depth + 1)
        if reason:
            return reason
    reason = run(commands, state, depth)
    if reason or not own:
        return reason
    return judge_later(state, depth)


def run(commands, state, depth):
    """Judge lexed commands in order, following the working folders: the first reading (track
    and the loop below) and the second (MoreFolders), which only adds folders."""
    saved = []    # (working folders, variables, list start) at each `(`, restored at its `)`
    before = None  # the working folders before the current `&&`/`||` list, once a cd changed them
    loops = 0      # loops open: a cd in one may run any number of times
    functions = False  # a function was defined: its cds run wherever it is called
    more = MoreFolders(commands, state)
    for k, (words, op) in enumerate(commands):
        pre = state.folders()
        if words:
            first = words[0].raw()
            if first in ('for', 'while', 'until', 'select'):
                loops += 1
            following = commands[k + 1] if k + 1 < len(commands) else ([], '')
            if first == 'function' or (len(words) == 1 and op == '(' and not following[0]
                                       and following[1] == ')'):
                functions = True
            reason = judge_in_each_folder(words, state, depth)
            if reason:
                return reason
            folders = state.folders()
            if track(words, state, op == '&&' or (op == '||' and bool(following[0]) and
                                                   following[0][0].raw() in ('exit', 'return'))):
                before = folders if before is None else before
                if loops or functions:
                    state.set_folders([None])  # where it ends up is unknown
            if first == 'done':
                loops = max(0, loops - 1)
        if op in LIST_ENDS and before is not None:
            # the list is over: its cds may not have happened
            state.set_folders(before + state.folders())
            before = None
        if op == '(':
            saved.append((state.folders(), dict(state.env), before))
            before = None
        elif op == ')' and saved:
            folders, state.env, before = saved.pop()
            state.set_folders(folders)
        more.after(k, pre)
    return None


def judge_in_each_folder(words, state, depth):
    """judge_command in each folder the command may run in: the first reading's, then the ones
    only the second reading has."""
    folders = state.folders()
    folders += [f for f in state.ext if f not in folders]
    if len(folders) == 1:
        return judge_command(words, state, depth)
    kept = state.cwd, state.alt, state.ext
    try:
        for folder in folders:
            state.cwd, state.alt, state.ext = folder, (), ()
            reason = judge_command(words, state, depth)
            if reason:
                return reason
    finally:
        state.cwd, state.alt, state.ext = kept
    return None


def judge_later(state, depth):
    """Judge the function and trap bodies a shell defined again, in every folder it may have
    been in, since they run where they are called or when the trap fires."""
    shell, k = state.shell, 0
    frozen = [list(entry[2]) for entry in shell.later]  # not grown by the bodies judged here
    while k < len(shell.later):
        kind, item, folders = shell.later[k]
        folders = frozen[k] if k < len(frozen) else list(folders)
        k += 1
        for folder in folders:
            child = state.child(shared=True)
            child.cwd, child.alt = folder, ()
            reason = (run(item, child, depth + 1) if kind == 'body'
                      else judge(item, child, depth + 1, own=False))
            if reason:
                return '%s, in a function or trap body that runs later' % reason
    return None


# --- the second reading of the working folders (issue #4) ----------------------------------
# The first reading (track and run's loop) is the guard as it was before issue #4. Its folders
# are never replaced: the second reading keeps a list of its own (state.ext) of folders the
# shell may also be in, and every command is judged in both. Unknown folders (None) are only
# ever added. It reads what the first does not: a cd behind a precommand, `!`, an assignment or
# `repeat`; a cd that may be skipped (after `||`, in a pipeline); popd, pushd and `cd -` with
# the folders the command was in; zsh's `cd OLD NEW`; CDPATH; a cd in a loop applied as often
# as it may run, also before the loop's first delete; eval and `$C` that run a cd; a cd hidden
# in computed text; and the cds of function and trap bodies, which may run at any later point.

def union(*lists):
    out = []
    for items in lists:
        for f in items:
            if f not in out:
                out.append(f)
    return out


def capped(folders):
    folders = list(folders)
    return folders if len(folders) <= MAX_MORE else folders[:MAX_MORE - 1] + [None]


def cd_specs(words, state):
    """What a cd-like command (after strip_head) changes to, as a list of specs, or None for
    another command: ('home',), ('path', text), ('subst', old, new) for zsh's `cd OLD NEW`,
    ('stack', unknown) for popd, pushd, `cd -` and `cd ±N` (a folder the command was in, and an
    unknown one when unknown), ('unknown',)."""
    if not words or words[0].raw() not in CD_WORDS:
        return None
    if words[0].raw() == 'popd':
        return [('stack', False)]
    args = [w for w in words[1:] if not re.fullmatch(r'-[LPe@qs]+|--', w.raw())]
    if not args:
        return [('stack', True), ('home',)] if words[0].raw() == 'pushd' else [('home',)]
    if args[0].raw() == '-' or re.fullmatch(r'[-+]\d+', args[0].raw()):
        return [('stack', True)]
    value = evaluate(args[0], state.values())
    if value.computed:
        return [('unknown',)]
    specs = [('path', value.text)]
    if len(args) > 1:
        new = evaluate(args[1], state.values())
        specs.append(('unknown',) if new.computed else ('subst', value.text, new.text))
    return specs


def moves_in(text, state):
    """The cd specs of every cd in text, at any depth: a body that may run anywhere later."""
    try:
        commands, _ = lex(text)
    except ValueError:
        return [('unknown',)] if CD_TEXT.search(text) else []
    specs = []
    for words, _ in commands:
        rest, _ = strip_head(words)
        specs += cd_specs(rest, state) or []
        if rest and computed_cd(rest[0]):
            specs.append(('unknown',))
    return specs


def computed_cd(word):
    """True for a computed command word whose text names a cd: `$(echo cd)`."""
    return any(q != "'" and ('$' in t or '`' in t) for q, t in word.parts) and bool(
        CD_TEXT.search(word.raw()))


def resolve(specs, folders, state):
    out = []
    for spec in specs:
        if spec[0] == 'home':
            out.append(state.home)
        elif spec[0] == 'unknown':
            out.append(None)
        elif spec[0] == 'stack':
            out += state.shell.seen + ([None] if spec[1] else [])
        elif spec[0] == 'path':
            text = spec[1]
            out += [norm(text, f) for f in folders]
            if state.shell.cdpath and not is_abs(text) and not text.startswith(('.', '~')):
                out += [norm(text, c) for c in state.shell.cdpath]
        elif spec[0] == 'subst':
            out += [norm(f.replace(spec[1], spec[2], 1), None) for f in folders
                    if f is not None and spec[1] and spec[1] in f
                    and is_abs(f.replace(spec[1], spec[2], 1))]
    return out


def closure(folders, specs, state, times=None):
    """folders and every folder the specs lead to from them, applied again and again (a cd in a
    loop, or in a body that may run any number of times), at most times rounds when given."""
    found, frontier = list(folders), list(folders)
    while frontier and times != 0:
        times = None if times is None else times - 1
        state.check_time()
        new = [f for f in resolve(specs, frontier, state) if f not in found]
        found += union(new)
        frontier = [f for f in union(new) if f is not None]
        if len(found) > MAX_MORE:
            return found + [None]
    return found


def rounds(words, head, flags):
    """How often a loop runs, when its header says so: `for x in a b c` (literal words) or zsh's
    `repeat 3`; else None (any number of times)."""
    raws = [w.raw() for w in words if not w.redirect]
    if 'repeat' in flags:
        k = raws.index('repeat') if 'repeat' in raws else -1
        return int(raws[k + 1]) if 0 <= k < len(raws) - 1 and raws[k + 1].isdigit() else None
    if head == 'for' and 'in' in raws:
        items = raws[raws.index('in') + 1:]
        if items and not any(ch in ''.join(items) for ch in '$`*?[{~'):
            return len(items)
    return None


class MoreFolders:
    """The second reading of the working folders for one list of commands (see above)."""

    def __init__(self, commands, state):
        self.commands, self.state = commands, state
        self.heads = [strip_head(words) for words, _ in commands]
        self.before = None  # the second reading's folders before the current `&&`/`||` list
        self.contexts = []  # open `(` (with the folders to restore) and `case`
        n = len(commands)
        self.untrusted = [False] * n  # in a loop or a function body: a cd there is never sure
        self.loops = {}     # loop start -> (indexes of the cds in it, times it runs or None)
        self.bodies = {}    # function definition -> (name, indexes of its cds, its commands)
        for k in range(n):
            rest, flags = self.heads[k]
            head = rest[0].raw() if rest else ''
            if head in LOOP_ENDS or 'repeat' in flags:
                end = k if 'repeat' in flags and 'repeat-do' not in flags else self.find_end(
                    k, ['end' if head == 'foreach' else 'done'])
                self.loops[k] = self.cds(k, end), rounds(commands[k][0], head, flags)
            words, op = commands[k]
            following = commands[k + 1] if k + 1 < n else ([], '')
            plain = [w for w in words if not w.redirect]
            while plain and plain[0].raw() in gg.KEYWORDS:
                plain = plain[1:]
            if (len(plain) == 1 and op == '(' and not following[0] and following[1] == ')') or (
                    plain and plain[0].raw() == 'function'):
                start = k + 2 if op == '(' and following == ([], ')') else k
                if start < n:
                    end = self.find_body_end(start)
                    name = plain[0].raw() if len(plain) == 1 else (
                        plain[1].raw() if len(plain) > 1 and plain[1].raw() != '{' else None)
                    self.bodies[k] = name, self.cds(start, end), commands[start:end + 1]
        state.shell.seen = capped(union(state.shell.seen, state.folders(), state.ext))

    def find_end(self, k, stack):
        for j in range(k + 1, len(self.commands)):
            rest, flags = self.heads[j]
            head = rest[0].raw() if rest else ''
            if head == stack[-1]:
                stack.pop()
                if not stack:
                    return j
            elif head in LOOP_ENDS:
                stack.append(LOOP_ENDS[head])
            elif 'repeat-do' in flags:
                stack.append('done')
        return len(self.commands) - 1

    def find_body_end(self, start):
        balance = 0
        for j in range(start, len(self.commands)):
            words = self.commands[j][0]
            balance += sum(w.raw() == '{' and w.parts[0][0] == '' for w in words)
            if words and words[0].raw() == '}' and words[0].parts[0][0] == '':
                balance -= 1
            if balance <= 0:
                return j
        return len(self.commands) - 1

    def cds(self, start, end):
        """Indexes of the cds in commands start..end outside a subshell; marks them untrusted."""
        found, depth = [], 0
        for j in range(start, end + 1):
            self.untrusted[j] = True
            if depth <= 0 and cd_specs(self.heads[j][0], self.state) is not None:
                found.append(j)
            depth += {'(': 1, ')': -1}.get(self.commands[j][1], 0)
        return found

    def trusted(self, k, op):
        """A cd the rest of its list runs only after: as track's trusted cd, unless it may be
        skipped or runs in a pipeline, is negated, or is in a loop or a function body."""
        if self.untrusted[k] or 'negated' in self.heads[k][1]:
            return False
        if k and self.commands[k - 1][1] in ('||', '|'):
            return False
        following = self.commands[k + 1] if k + 1 < len(self.commands) else ([], '')
        return op == '&&' or (op == '||' and bool(following[0]) and
                              following[0][0].raw() in ('exit', 'return'))

    def after(self, k, pre):
        """Update the second reading's folders after command k; pre: the first reading's
        folders before it."""
        state, shell = self.state, self.state.shell
        words, op = self.commands[k]
        rest, _ = self.heads[k]
        view = union(pre, state.ext)
        ext = view
        for w in words:
            if w.raw().startswith('CDPATH='):
                value = evaluate(tail_word(w, len('CDPATH=')) or Word(), state.values())
                shell.cdpath = [None] if value.computed else [
                    norm(p or '.', state.cwd) for p in value.text.split(':')]
        specs = cd_specs(rest, state)
        if specs is not None:
            targets = resolve(specs, view, state)
            if self.trusted(k, op):
                self.before = view if self.before is None else self.before
                ext = targets
            else:
                ext = union(view, targets)
        if state.landing:  # eval or `$C` ran in this shell
            ext = union(ext, state.landing)
            state.landing = []
        if rest and computed_cd(rest[0]):
            ext = union(ext, shell.seen, [None])
        if k in self.loops:
            cds, times = self.loops[k]
            specs = []
            for j in cds:
                specs += cd_specs(self.heads[j][0], state)
            ext = closure(ext, specs, state, times and times * len(specs))
        named = {w.raw() for w in words}
        specs = [s for name, moves in shell.moves if name is None or name in named
                 for s in moves]  # a DEBUG trap, or a call of a function that cds
        if specs:
            ext = closure(union(state.folders(), ext), specs, state)
        if k in self.bodies:
            name, cds, body = self.bodies[k]
            shell.run_later('body', body, ('body', tuple(
                (tuple(w.raw() for w in ws), o) for ws, o in body)))
            specs = []
            for j in cds:
                specs += cd_specs(self.heads[j][0], state)
            if specs:
                shell.moves.append((name, specs))
        following = self.commands[k + 1] if k + 1 < len(self.commands) else ([], '')
        if self.before is not None and (op in LIST_ENDS or (op == '||' and not (
                following[0] and following[0][0].raw() in ('exit', 'return')))):
            ext = union(self.before, ext)  # a cd of the list may have failed
            if op in LIST_ENDS:
                self.before = None
        head = rest[0].raw() if rest else ''
        if head == 'case':
            self.contexts.append('case')
        elif head == 'esac' and 'case' in self.contexts:
            while self.contexts.pop() != 'case':
                pass
        if op == '(':
            self.contexts.append((ext, self.before))
            self.before = None
        elif op == ')' and self.contexts and self.contexts[-1] != 'case':
            ext, self.before = self.contexts.pop()
        state.ext = tuple(capped(ext))
        shell.seen = capped(union(shell.seen, state.folders(), state.ext))
        for entry in shell.later:
            entry[2] = capped(union(entry[2], state.folders(), state.ext))


def name_of_text(text):
    word = Word()
    word.add('', text)
    return name_of(word)


def has_delete_word(text):
    """True when the text names a delete program once quotes are gone: `r\\m` without the
    backslash, `C:\\…\\rm.exe` with it read as a path separator."""
    text = re.sub(r'[\'"]', '', text)
    return bool(DELETE_WORD.search(text.replace('\\', '')) or
                DELETE_WORD.search(text.replace('\\', '/')))


def decide(command, cwd, home=None):
    """The reason the user must approve this command, or None."""
    home = home or os.environ.get('HOME') or os.path.expanduser('~')
    home = norm(home, None) or '/'
    cwd = norm(cwd, None) if cwd else None
    if len(command) > gg.MAX_INPUT:
        return ('is longer than %d characters, too long to check, and names a delete'
                % gg.MAX_INPUT if has_delete_word(command) else None)
    try:
        return judge(command, State.start(cwd, home, command))
    except Overtime:
        if names_delete(command):
            return ('took the delete guard longer than %.0f seconds to read, and names a delete'
                    % DEADLINE)
        return None
    except Exception:
        # Deliberate: a fault, or a command it cannot parse, asks rather than passes when the
        # command names a delete, and never denies.
        if names_delete(command):
            return 'deletes, and the delete guard could not read the command'
        return None


def names_delete(text):
    """True when a command the guard could not finish reading asks: it names a delete program,
    or holds a flag cluster with r and f that a computed command name may run (`$R -rf x`), the
    one ask that needs no delete word."""
    return has_delete_word(text) or bool(RF_FLAG.search(re.sub(r'[\'"\\]', '', text)))


def reason_text(reason):
    return ('Delete guard (agentic-github-flow rules, §Git: "%s."): this command %s. Approve '
            'only if the user confirms this delete. The safe form: %s, with literal, quoted, '
            'absolute paths that were listed and checked first.' % (RULE, reason, SAFE_FORM))


def hook():
    try:
        event = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace'))
    except ValueError:
        return
    if not isinstance(event, dict):
        return
    tool = str(event.get('tool_name') or '')
    if tool != 'Bash' and not tool.endswith('__run_in_terminal'):
        return
    tool_input = event.get('tool_input') or {}
    command = tool_input.get('command') if isinstance(tool_input, dict) else None
    if isinstance(command, list):
        command = ' '.join(str(c) for c in command)
    if not isinstance(command, str):
        return
    cwd = event.get('cwd')
    reason, finished = decide_bounded(command, cwd if isinstance(cwd, str) else '')
    if reason:
        json.dump({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                          'permissionDecision': 'ask',
                                          'permissionDecisionReason': reason_text(reason)}},
                  sys.stdout)
    if not finished:
        sys.stdout.flush()
        os._exit(0)  # the judging thread is stuck in a call; do not wait for it


def decide_bounded(command, cwd):
    """(reason, finished): decide in a daemon thread for at most HARD_DEADLINE seconds, so a
    stat or realpath that blocks (a hung network mount) cannot outrun the hook's timeout. A
    command still unjudged then asks when it names a delete."""
    result = []
    thread = threading.Thread(target=lambda: result.append(decide(command, cwd)), daemon=True)
    thread.start()
    thread.join(HARD_DEADLINE)
    if result:
        return result[0], True
    if thread.is_alive():
        return ('could not be read by the delete guard within %.0f seconds, and names a delete'
                % HARD_DEADLINE if names_delete(command) else None), False
    return None, True  # the thread failed, which decide never does


def main(argv):
    if argv[:1] == ['--check'] and len(argv) in (2, 3):
        reason, finished = decide_bounded(argv[1], argv[2] if len(argv) == 3 else os.getcwd())
        if reason:
            print(reason_text(reason))
        if not finished:
            sys.stdout.flush()
            os._exit(1 if reason else 0)
        return 1 if reason else 0
    try:
        hook()
    except Exception:
        pass  # the hook contract: exit 0, and nothing on stdout but a decision
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
