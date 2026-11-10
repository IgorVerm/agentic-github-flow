#!/usr/bin/env python3
"""PreToolUse hook (Claude Code, Bash), opt-in: refuse a network call the sandbox would keep
inside, naming the lone call that runs as the user's `excludedCommands` allow.

Claude Code runs a Bash call outside its sandbox only when every part of the call matches an
entry of `sandbox.excludedCommands`. A call that starts with `cd` never matches. It stays in the
sandbox, where gh, ssh and similar tools fail, and the agent retries it with
`dangerouslyDisableSandbox`. In one measured setup a fifth of all Bash calls left the sandbox
that way, most of them starting with `cd` (#20). What matches was measured on Claude Code
2.1.317; re-measure on a new client:
- every unescaped `*` of an entry is "any characters", `/`, quotes and spaces included; a single
  trailing ` *` also matches no arguments; `X:*` is a prefix;
- a quoted or backslash-escaped command name never matches, while quoted arguments do;
- a pipe into a command that is not excluded keeps a call inside; so does a redirection to a
  file or a here-document, while `2>&1` does not;
- `git -C <dir>` and `--git-dir` never match, not even an exact entry.

**It refuses ("deny") only when it can name a lone call that does the same and matches an entry
the user configured.** It never answers "allow" or "ask", so it cannot let anything run that
would not run without it, and no other guard's answer is weakened: Claude Code takes the
strictest answer of all hooks. It reads `sandbox.enabled` and `sandbox.excludedCommands` from the
user's Claude Code settings (`$CLAUDE_CONFIG_DIR/settings.json`, else `~/.claude/settings.json`)
and checks every rewrite with the client's matching rules (`matches()`); with the sandbox not
enabled there, or no entries, it does nothing. Two kinds of call are refused:
1. `cd <dir> && ...` (also `;`, a newline, several `cd`s, a later literal `cd`, `$HOME`) whose
   remainder runs a network command:
   - gh: `-R owner/repo`, right after the subcommand, for the repository gh itself would pick in
     `<dir>`: the remote marked `gh-resolved` (`gh repo set-default`), else the one repository
     all remotes name on github.com. A read-only pull-request command without a selector
     (`pr view|checks|diff`) gets `<dir>`'s current branch, and `gh pr create` gets
     `--head <branch>`. `gh repo view|edit|archive|unarchive|delete` get the repository as their
     argument; `gh api` gets `{owner}`, `{repo}` and `{branch}` filled into its endpoint. The
     file arguments it knows (`--body-file`, `-F`, `--notes-file`, `--input`, `-D`, `--env-file`,
     release files) become absolute. gh commands that do not depend on the folder lose only the
     `cd`, and `--body "$(cat <file>)"` becomes `--body-file <file>`;
   - `scp`/`rsync` with a remote operand: local paths become absolute (option values only where
     they are files read from the folder); `ssh`: `-F`, `-i`, `-E` and `-S` become absolute.
     An unquoted `~`, `$HOME/…` and `$TMPDIR/…` stay; a variable assigned a literal earlier in
     the call is filled in;
   - `git fetch|pull|push|ls-remote`: loses the `cd` when `<dir>` is the session's folder;
   - a script called by path whose `bash "<absolute path>"` form matches an entry: when `<dir>`
     is the session's folder, or when the script is listed in the user's `sandbox-scripts`
     (below), because only then does it do the same from the session's folder. A script without
     an entry is an ordinary command.
2. A command that matches an excluded wildcard entry only loosely, which today runs outside the
   sandbox: through `..`, or with a `*` in the middle of the entry spanning a quote or a space
   (`bash "<dir>/evil.sh" "/tools/…"`). Also, without a `cd`, a call to such a script in a form
   its entry does not match.

It passes, so the call runs as before, whenever a faithful lone call does not exist or cannot be
shown to match:
- the network command reads input (`< file`, a here-document or here-string, a pipe into it),
  writes output to a file, runs in the background (`&`), contains `$(...)` or a backtick, has a
  leading environment assignment or wrapper, or, after a `cd` to another folder, a glob (`*`,
  `?`, `[`) the shell would expand against the wrong folder;
- a path it would have to rewrite holds `..` (the shell resolves it through symlinks), is `.`,
  starts with a quoted `~`, or holds a variable without a literal value;
- its output goes through a pipe to anything other than a display filter (`head`, `tail`,
  `grep`, `jq`, ...), or to one that writes a file;
- the call has a loop or conditional, a computed `cd` target, `cd -`, `pushd` or `popd`;
- a gh command acts on the folder (`pr checkout`, `pr status`, `pr create --fill`,
  `issue develop --checkout`, `repo clone|create|fork|sync|set-default`, downloads without
  `-D`, `ruleset check`, `pr merge --delete-branch`), changes a pull request chosen by the
  folder's branch (`pr merge|close|comment|edit…` without a selector: a branch name could match
  another fork's pull request), or is one this hook does not know; `GH_REPO` or `GH_HOST` is set
  in the hook's environment; the folder's remotes leave gh's choice open, or point to another
  host than github.com; a branch is needed and the folder has several remotes or tracks a branch
  of another name;
- scp or rsync are local only, or have an option the hook cannot place: a relative file in an
  ssh `-o` option, in rsync's `-e` command, scp's `-S` program, `ProxyCommand` and the like,
  rsync's `-R`/`--relative` or a filter that reads a rules file, ssh options after the host;
- a script run with `sh`, through `..`, from a glob, or directly while its first line names
  another interpreter than bash; after a `cd` to another folder, a listed script with an
  argument that names a file in that folder;
- input it cannot parse, or longer than MAX_INPUT characters.
The rewrite drops `2>&1` and display-filter pipes, and the reason says what to use instead
(`--jq`, filtering on the remote side, `--body-file`). It is a redirect, not a boundary: it does
not see network commands started by scripts, `sh -c` strings or `ssh` remote commands, nor a
`GH_REPO` the user's shell profile sets for Bash calls (then `-R` overrides it). An entry
such as `rsync *` also matches local copies, which then run outside the sandbox; that is the
entry's doing, and this guard does not change it.

The user's settings, beside the personal-data guard's in
`${XDG_CONFIG_HOME:-~/.config}/agentic-github-flow/`: `sandbox-scripts`, one absolute path pattern
per line (`~` expanded, `*` matches any characters, `/` included; blank lines, `#` comments and
relative lines ignored) of scripts that find their own folder from `$0` and so do the same from
any working folder. Listing one only lets this guard name its excluded form after a `cd` to
another folder; what runs outside the sandbox is still decided by `excludedCommands`.

Faults: a crash or an unreadable input passes the call (exit 0). Installed by
`install.sh --guards sandbox`, which adds it to `~/.claude/settings.json` as
`sh run-python.sh <this file> || true`, so a missing file or Python passes too.

Usage as a hook: JSON on stdin. For tests:
`pre_tool_sandbox_network.py --check '<command>' [--cwd <dir>]` prints the reason and exits 2,
or exits 0. Test: `python3 tests/sandbox_network_guard.py`.
"""
from __future__ import annotations

import fnmatch
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from typing import NamedTuple

REASON_MARKER = "sandbox-network guard"  # a measurement can count refusals by this text
GIT_NETWORK = {"fetch", "pull", "push", "ls-remote"}
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                  "--config-env"}
# gh: commands that take -R; those that do not depend on the folder; those that act on it
GH_REPO_FLAG = {"issue", "pr", "release", "run", "workflow", "label", "cache", "ruleset",
                "variable", "secret", "browse"}
GH_FOLDER_FREE = {"auth", "search", "status", "org", "completion", "alias", "help",
                  "version"}
GH_FOLDER_BOUND = {("pr", "checkout"), ("pr", "status"), ("ruleset", "check"), ("repo", "clone"),
                   ("repo", "create"),
                   ("repo", "fork"), ("repo", "sync"), ("repo", "set-default")}
GH_PR_SELECTOR = {"view", "checks", "diff", "comment", "merge", "close", "reopen", "edit",
                  "ready", "review", "update-branch", "lock", "unlock"}
GH_PR_READ = {"view", "checks", "diff"}  # the only ones that get the folder's branch filled in
GH_REPO_ARG = {"view", "edit", "archive", "unarchive", "delete"}
GH_API_VALUE_OPTS = {"-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header",
                     "--input", "-q", "--jq", "-t", "--template", "--cache", "--hostname", "-p",
                     "--preview"}
SSH_VALUE_OPTS = {"-B", "-b", "-c", "-D", "-E", "-e", "-F", "-I", "-i", "-J", "-L", "-l", "-m",
                  "-O", "-o", "-p", "-Q", "-R", "-S", "-W", "-w"}
SSH_FILE_OPTS = {"-F", "-i", "-E", "-S"}  # values read or written relative to the folder
# ssh -o keys whose value is a file relative to the folder, or a command run in it
SSH_FILE_KEYS = {"identityfile", "certificatefile", "userknownhostsfile", "globalknownhostsfile",
                 "controlpath", "identityagent", "include", "revokedhostkeys",
                 "securitykeyprovider", "pkcs11provider", "xauthlocation"}
SSH_COMMAND_KEYS = {"proxycommand", "localcommand", "knownhostscommand"}
SCP_VALUE_OPTS = {"-c", "-D", "-F", "-i", "-J", "-l", "-o", "-P", "-S", "-X"}
RSYNC_VALUE_OPTS = {"-e", "-f", "-T", "-B", "-M"}
RSYNC_LONG_VALUE = {"--exclude", "--include", "--filter", "--rsh", "--exclude-from",
                    "--include-from", "--files-from", "--link-dest", "--compare-dest",
                    "--copy-dest", "--backup-dir", "--partial-dir", "--temp-dir", "--log-file",
                    "--password-file", "--chmod", "--chown", "--timeout", "--bwlimit",
                    "--max-size", "--min-size", "--port", "--out-format", "--suffix",
                    "--rsync-path", "--contimeout", "--iconv", "--info", "--debug",
                    "--skip-compress", "--usermap", "--groupmap", "--modify-window",
                    "--max-delete", "--block-size", "--write-batch", "--only-write-batch",
                    "--read-batch"}
# read from the folder; --link-dest & co. are relative to the destination and stay as written
RSYNC_LONG_FILE = {"--exclude-from", "--include-from", "--files-from", "--log-file",
                   "--password-file", "--write-batch", "--only-write-batch", "--read-batch"}
RSYNC_LONG_FLAG = {"--archive", "--verbose", "--compress", "--recursive", "--delete",
                   "--delete-after", "--delete-before", "--delete-during", "--delete-excluded",
                   "--progress", "--dry-run", "--checksum", "--partial", "--update", "--inplace",
                   "--times", "--perms", "--links", "--human-readable", "--stats",
                   "--itemize-changes", "--mkpath", "--remove-source-files",
                   "--ignore-existing", "--existing", "--size-only", "--no-perms",
                   "--no-owner", "--no-group", "--quiet", "--whole-file", "--sparse",
                   "--hard-links", "--copy-links", "--safe-links", "--one-file-system",
                   "--prune-empty-dirs", "--list-only", "--append", "--append-verify",
                   "--omit-dir-times", "--no-times", "--protect-args", "--relative"}
DISPLAY_FILTERS = {"head", "tail", "grep", "egrep", "fgrep", "rg", "cut", "wc", "sort", "uniq",
                   "tr", "cat", "less", "jq", "column", "nl", "fold"}  # not sed: it can write
CONTROL = {"for", "while", "until", "if", "case", "select", "function"}
WRAPPERS = {"time", "nohup", "command", "builtin", "exec"}
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
MAX_INPUT = 32_000  # characters; a longer command passes unjudged (the parsing is not linear)
HEREDOC_MARKER = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

_spec = importlib.util.spec_from_file_location(
    "pre_tool_git_guard", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "pre_tool_git_guard.py"))
gg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gg)  # owner of here-document stripping (strip_heredocs)
SHELL_INTERPRETERS = {"bash", "sh"}


class Unparsed(Exception):
    """The command is not something this hook can judge; it passes."""


class Unsafe(Exception):
    """No faithful lone call exists for this command; the whole call passes."""


# --- reading the command line ------------------------------------------------------------------

def scan(text: str) -> list[dict]:
    """Split a command line at top-level `&&`, `||`, `;`, `|`, `&` and newlines.

    Returns one dict per simple command: `text` without top-level redirections, `op` (the
    operator after it) and flags `outfile` (output to a file), `infile` (`< file`), `heredoc`
    and `subst`. Quotes, backslashes and `$(...)` nesting are honoured. A here-document body
    must have been stripped before (`gg.strip_heredocs`); one inside `$(...)` stays in the text.
    """
    parts, cur = [], []
    new_flags = lambda: {"outfile": False, "infile": False, "heredoc": False, "subst": False}
    flags = new_flags()
    i, n, stack = 0, len(text), []  # open contexts: ' " ` $( (

    def close(op: str) -> None:
        nonlocal cur, flags
        parts.append({"text": "".join(cur).strip(), "op": op, **flags})
        cur, flags = [], new_flags()

    while i < n:
        c, top = text[i], (stack[-1] if stack else None)
        if top == "'":
            cur.append(c)
            if c == "'":
                stack.pop()
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            if text[i + 1] != "\n":
                cur.append(text[i:i + 2])
            i += 2
            continue
        if c == "`":
            if top == "`":
                stack.pop()
            else:
                flags["subst"] = True
                stack.append("`")
            cur.append(c)
            i += 1
            continue
        if text.startswith("$(", i):
            flags["subst"] = True
            stack.append("$(")
            cur.append("$(")
            i += 2
            continue
        if top == '"':
            if c == '"':
                stack.pop()
            cur.append(c)
            i += 1
            continue
        if c in "\"'(":
            stack.append(c)
            cur.append(c)
            i += 1
            continue
        if c == ")" and top in ("$(", "("):
            stack.pop()
            cur.append(c)
            i += 1
            continue
        if text.startswith("<<<", i):
            raise Unparsed("here-string")
        if text.startswith("<<", i):
            flags["heredoc"] = True
            marker = HEREDOC_MARKER.match(text, i)
            if not stack and marker:  # the body was stripped before: skip the marker word
                i = marker.end()
                continue
            cur.append(text[i:])  # inside $(...) or unreadable: the rest is opaque
            stack = []
            break
        if stack:  # inside `...`, $(...) or (...): no top-level operators here
            cur.append(c)
            i += 1
            continue
        m = re.match(r"(\d*|&)(>>?|<)(&\d+|&-)?", text[i:])
        if m and m.group(2) and (not m.group(1) or not cur or cur[-1] in " \t"):
            i += m.end()
            if not m.group(3):  # a file follows; `2>&1` alone keeps a call excluded (measured)
                flags["infile" if m.group(2) == "<" else "outfile"] = True
                while i < n and text[i] in " \t":
                    i += 1
                start = i
                while i < n and text[i] not in " \t;&|<>\n":
                    if text[i] in "\"'":
                        end = text.find(text[i], i + 1)
                        i = n if end < 0 else end + 1
                    else:
                        i += 1
                if i == start:
                    raise Unparsed("redirection without a target")
            continue
        for op in ("&&", "||", ";", "|", "&", "\n"):
            if text.startswith(op, i):
                close(op)
                i += len(op)
                break
        else:
            cur.append(c)
            i += 1
    if stack:
        raise Unparsed("unbalanced quote or substitution")
    close("")
    return [p for p in parts if p["text"]]


class Word(NamedTuple):
    raw: str    # as written, quotes included: kept in the rewrite unless the word changes
    value: str  # with the quotes removed: what the decisions read


def raw_split(text: str) -> list[str]:
    """Split at unquoted blanks, keeping each word's quoting; `$(...)` and `(...)` stay whole."""
    out, cur, stack, i = [], [], [], 0
    while i < len(text):
        c, top = text[i], (stack[-1] if stack else None)
        if top == "'":
            if c == "'":
                stack.pop()
        elif c == "\\" and i + 1 < len(text):
            cur.append(text[i:i + 2])
            i += 2
            continue
        elif c == "`":
            if top == "`":
                stack.pop()
            else:
                stack.append("`")
        elif text.startswith("$(", i):
            stack.append("$(")
            cur.append("$(")
            i += 2
            continue
        elif top == '"':
            if c == '"':
                stack.pop()
        elif c in "\"'(":
            stack.append(c)
        elif c == ")" and top in ("$(", "("):
            stack.pop()
        elif c in " \t\n" and not stack:
            if cur:
                out.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if stack:
        raise Unparsed("unbalanced quote or substitution")
    if cur:
        out.append("".join(cur))
    return out


def dequote(raw: str) -> str:
    try:
        return " ".join(shlex.split(raw, comments=False)) if raw else ""
    except ValueError as exc:
        raise Unparsed(str(exc)) from exc


def words(text: str) -> list[Word]:
    return [Word(raw, dequote(raw)) for raw in raw_split(text)]


def quote(value: str) -> Word:
    """A new word for `value`, quoted for the shell; the value is literal."""
    if value and re.fullmatch(r"[A-Za-z0-9_@%+=:,./{}-]+", value):
        return Word(value, value)
    if not re.search(r'["$`\\!]', value):
        return Word(f'"{value}"', value)
    return Word(shlex.quote(value), value)


def substituted(word: Word) -> bool:
    """`$(...)` or a backtick outside single quotes: the word is computed by the shell."""
    return bool(re.search(r"\$\(|`", re.sub(r"'[^']*'", "", word.raw)))


def globbed(word: Word) -> bool:
    """An unquoted `*`, `?` or `[`: the shell expands it against the working folder."""
    raw = re.sub(r"\\.", "", word.raw)
    raw = re.sub(r"'[^']*'|\"[^\"]*\"", "", raw)
    return bool(re.search(r"[*?\[]", raw))


def absolute(path: str, base: str) -> str:
    """`path` made absolute against `base`; a trailing slash stays (rsync reads it)."""
    expanded = os.path.expanduser(path)
    result = os.path.normpath(expanded if os.path.isabs(expanded) else os.path.join(base, expanded))
    return result + "/" if path.endswith("/") and result != "/" else result


def relative_file(value: str) -> bool:
    return bool(value) and not value.startswith(("/", "~", "$", "-", "<"))


def local_path(word: Word, directory: str) -> Word:
    """A local path word, written so that it names from any folder what it names in `directory`;
    Unsafe where that cannot be written faithfully. `-` (standard input), absolute paths, an
    unquoted `~` and `$HOME/…` or `$TMPDIR/…` stay as they are."""
    v = word.value
    if not v or v in ("-", "<file>"):  # standard input; the placeholder for a here-document
        return word
    if "$" in word.raw or "`" in word.raw:
        if re.fullmatch(r'"?\$\{?(HOME|TMPDIR)\}?/[^$`"]*"?', word.raw):
            return word
        raise Unsafe("a computed path")
    if v.startswith("~"):
        if word.raw.startswith("~"):
            return word
        raise Unsafe("a quoted ~ names a folder called ~")
    if v.startswith("/"):
        return word
    if ".." in v.split("/"):
        raise Unsafe("`..` in a path: the shell resolves it through symlinks")
    if v == "." or v.endswith("/."):
        raise Unsafe("`.` as a path")
    return quote(absolute(v, directory))


def attached_path(word: Word, prefix: str, value: str, directory: str) -> Word:
    """`--flag=<path>` or `key=@<path>`: the word with its path read as from `directory`."""
    if "$" in word.raw or "`" in word.raw or value.startswith("~"):
        raise Unsafe("a computed or ~ path inside an option")
    if value == "-" or value.startswith("/"):
        return word
    return quote(prefix + local_path(Word(value, value), directory).value)


def heredoc_part(text: str) -> list[Word]:
    """Words of a part whose here-document sits inside `$(...)`, the usual
    `--body "$(cat <<'EOF' ... EOF\\n)"`: the substitution becomes `--body-file "<file>"` after
    `--body`/`-b`, and the words after it stay. Anything else raises Unsafe."""
    marker = HEREDOC_MARKER.search(text)
    if not marker:
        raise Unsafe("here-document")
    start = max(text.rfind(' "$(', 0, marker.start()), text.rfind(" $(", 0, marker.start()))
    lines = text[marker.end():].split("\n")
    for k, line in enumerate(lines[1:], 1):
        if line.strip() == marker.group(2):
            rest = "\n".join(lines[k + 1:]).lstrip()
            break
    else:
        raise Unsafe("here-document without its end")
    if start < 0 or not rest.startswith(")"):
        raise Unsafe("here-document outside a substitution")
    rest = rest[1:]
    if text[start + 1] == '"':
        if not rest.startswith('"'):
            raise Unsafe("here-document substitution")
        rest = rest[1:]
    empty = {"text": "", "op": "", "outfile": False, "infile": False, "heredoc": False,
             "subst": False}
    lead = rest.lstrip(" \t")
    if lead.startswith(("&", ";", "\n")) or lead.startswith("||"):
        raise Unsafe("a command after the here-document")
    if lead.startswith("|"):  # the gh command's own words end at the substitution
        after = [dict(empty, op="|")] + scan(lead[1:])
    else:
        after = scan(rest) if rest.strip() else [empty]
    if not after:  # only a redirection followed
        raise Unsafe("redirection after the here-document")
    if after[0]["outfile"] or after[0]["infile"] or after[0]["heredoc"]:
        raise Unsafe("redirection after the here-document")
    for prev, nxt in zip(after, after[1:]):  # only display filters may follow
        filt = words(nxt["text"])
        if prev["op"] != "|" or not filt or filt[0].value not in DISPLAY_FILTERS or nxt["outfile"]:
            raise Unsafe("a command after the here-document")
    head, tail = words(text[:start]), words(after[0]["text"])
    if not head or head[-1].value not in ("--body", "-b"):
        raise Unsafe("here-document as a value other than a gh body")
    return head[:-1] + [Word("--body-file", "--body-file"), quote("<file>")] + tail


def split_command(tokens: list[Word]) -> tuple[list[Word], list[Word], bool]:
    """(leading wrappers, the command, whether an assignment or `env` came first):
    `timeout 60 gh ...` -> ([timeout, 60], [gh, ...], False). An assignment before a network
    command makes the call pass: a rewrite would drop it, or the variable changes what the
    command does (`GH_REPO=...`)."""
    prefix, out, assigned = [], list(tokens), False
    while out:
        head = out[0].value
        if head in WRAPPERS:
            prefix.append(out.pop(0))
        elif head == "timeout" and len(out) > 1:
            prefix += out[:2]
            out = out[2:]
        elif ASSIGN.match(out[0].raw) or head == "env":
            assigned = True
            out.pop(0)
        else:
            break
    return prefix, out, assigned


def assignments(tokens: list[Word]) -> dict[str, str | None]:
    """`NAME=value` words of a part that only assigns (`f=/tmp/x`, `export F=x`): the literal
    value, `~` expanded as bash does in an assignment, or None where it is computed."""
    found = {}
    for w in tokens:
        if w.value == "export":
            continue
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", w.raw, re.S)
        if not m:
            return {}
        raw = m.group(2)
        value = dequote(raw)
        if re.search(r"[$`]", raw) or (value.startswith("~") and not raw.startswith("~")):
            found[m.group(1)] = None
        else:
            found[m.group(1)] = os.path.expanduser(value) if raw.startswith("~") else value
    return found


def fill(word: Word, known: dict[str, str]) -> Word:
    """`$f`, `"$f"`, `${f}` for a variable assigned a literal earlier: the value instead."""
    m = re.fullmatch(r'"?\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"?', word.raw)
    return quote(known[m.group(1)]) if m and m.group(1) in known else word


# --- what the sandbox excludes -----------------------------------------------------------------

def claude_settings_path() -> str:
    folder = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"),
                                                                 ".claude")
    return os.path.join(folder, "settings.json")


def excluded_patterns() -> list[str]:
    """The user's `excludedCommands`, or [] when the sandbox is not enabled in their settings."""
    try:
        with open(claude_settings_path(), encoding="utf-8") as handle:
            sandbox = json.load(handle).get("sandbox", {})
        if sandbox.get("enabled") is not True:
            return []
        entries = sandbox.get("excludedCommands", [])
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, str) and e.strip()]


def listed_scripts() -> list[str]:
    """Absolute path patterns from the user's `sandbox-scripts` file (see the header)."""
    folder = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    try:
        with open(os.path.join(folder, "agentic-github-flow", "sandbox-scripts"),
                  encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    found = []
    for line in lines:
        line = os.path.expanduser(line.strip())
        if line and not line.startswith("#") and os.path.isabs(line) and "\0" not in line:
            found.append(os.path.normpath(line))
    return found


def pattern_regex(pattern: str, strict: bool) -> re.Pattern | None:
    """The client's rule (2.1.317, `sWe`/`uY`): `X:*` is a prefix; an unescaped `*` is any
    characters; a single trailing ` *` also matches no arguments; blanks are normalised.
    `strict`: a `*` before the last character may not span a quote or a blank."""
    p = re.sub(r"[ \t]+", " ", pattern.strip())
    if p.endswith(":*"):
        return re.compile(re.escape(p[:-2]) + r"( .*)?", re.S)
    out, stars, i = [], 0, 0
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p) and p[i + 1] in "*\\":
            out.append(re.escape(p[i + 1]))
            i += 2
            continue
        if c == "*":
            stars += 1
            out.append(".*" if (not strict or i == len(p) - 1) else "[^\"'\\s$`()\\\\;&|<>]*")
        else:
            out.append(re.escape(c))
        i += 1
    regex = "".join(out)
    if stars == 1 and regex.endswith(re.escape(" ") + ".*"):
        regex = regex[:-len(re.escape(" ") + ".*")] + "( .*)?"
    return re.compile(regex, re.S)


def matches(text: str, patterns: list[str], strict: bool = False) -> bool:
    text = re.sub(r"[ \t]+", " ", text.strip())
    return any(pattern_regex(p, strict).fullmatch(text) for p in patterns)


# --- rewriting one network command -------------------------------------------------------------

def git_out(directory: str, *args: str) -> str:
    try:
        return subprocess.run(["git", "-C", directory, *args], capture_output=True, text=True,
                              timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def github_repo(url: str) -> str | None:
    """`owner/name` of a github.com remote URL; None for another host or a local path."""
    m = re.fullmatch(r"(?:(?:https?|ssh|git)://(?:[^@/]+@)?github\.com(?::\d+)?/|"
                     r"(?:[^@/:]+@)?github\.com:)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?",
                     url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def local_url(url: str) -> bool:
    return url.startswith(("/", ".", "~", "file://")) or ":" not in url


def remote_urls(directory: str) -> dict[str, str]:
    urls = {}
    for line in git_out(directory, "remote", "-v").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            urls.setdefault(parts[0], parts[1])
    return urls


def folder_branch(directory: str, repo: str) -> str:
    """The folder's current branch, for a rewrite that names it, only where gh in the folder
    would mean that same branch of `repo`: every remote names `repo` (no fork beside it), and the
    branch tracks a branch of its own name, if any."""
    branch = git_out(directory, "branch", "--show-current")
    if not branch:
        raise Unsafe("no current branch")
    if {github_repo(u) for u in remote_urls(directory).values()} != {repo}:
        raise Unsafe("several remotes: gh would name the branch with its fork")
    merge = git_out(directory, "config", "--get", f"branch.{branch}.merge")
    if merge and merge != f"refs/heads/{branch}":
        raise Unsafe("the branch tracks another branch name")
    return branch


def gh_repo(directory: str) -> str | None:
    """The repository gh picks in `directory`, when that is certain: the remote marked
    `gh-resolved` (`gh repo set-default`), else the one github.com repository every remote names.
    None when GH_REPO or GH_HOST decide instead, when remotes disagree, or when one points to
    another host (gh may be signed in there)."""
    if os.environ.get("GH_REPO") or os.environ.get("GH_HOST"):
        return None
    urls = remote_urls(directory)
    resolved = git_out(directory, "config", "--get-regexp", r"^remote\..*\.gh-resolved$")
    for line in resolved.splitlines():
        key, _, value = line.partition(" ")
        name = key[len("remote."):-len(".gh-resolved")]
        if value == "base":
            return github_repo(urls.get(name, ""))
        return value if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) else None
    repos = set()
    for url in urls.values():
        repo = github_repo(url)
        if repo:
            repos.add(repo)
        elif not local_url(url):
            return None
    return repos.pop() if len(repos) == 1 else None


def remote_operand(value: str) -> bool:
    """`host:path`, `user@host:`, `[::1]:/x`, `rsync://...`: not a local path."""
    if value.startswith("rsync://"):
        return True
    head = value.split("/")[0]
    return ":" in head and not value.startswith((".", "/", "~"))


def operands(cmd: list[Word], value_opts: set[str], long_value: set[str] = frozenset()):
    """Yield (index, word, kind) for scp/rsync: kind is 'operand', 'value:<option>' or 'option'."""
    previous = None
    for at, w in enumerate(cmd[1:], 1):
        v = w.value
        if previous:
            yield at, w, "value:" + previous
            previous = None
        elif v.startswith("--"):
            name = v.split("=")[0]
            if "=" not in v and name in long_value:
                previous = name
            yield at, w, "option"
        elif v.startswith("-") and v != "-":
            letters = v[1:]
            if any(f"-{c}" in value_opts for c in letters[:-1]):
                raise Unsafe(f"option cluster {v}")
            if f"-{letters[-1:]}" in value_opts:
                previous = f"-{letters[-1]}"
            yield at, w, "option"
        else:
            yield at, w, "operand"


def classify(cmd: list[Word]) -> str | None:
    if not cmd:
        return None
    name = os.path.basename(cmd[0].value)
    if name in ("gh", "ssh"):
        return name
    if name in ("scp", "rsync"):
        opts = SCP_VALUE_OPTS if name == "scp" else RSYNC_VALUE_OPTS
        try:
            remote = any(kind == "operand" and remote_operand(w.value)
                         for _, w, kind in operands(cmd, opts, RSYNC_LONG_VALUE))
        except Unsafe:
            remote = True  # a network call we cannot rewrite: judged in rewrite()
        return name if remote else None
    if name == "git":
        i = 1
        while i < len(cmd) and cmd[i].value.startswith("-"):
            i += 2 if cmd[i].value in GIT_VALUE_OPTS else 1
        return "git" if i < len(cmd) and cmd[i].value in GIT_NETWORK else None
    if script_path(cmd):
        return "script"
    return None


def shell_script(path: str) -> bool:
    """Whether running the file directly runs bash or sh: its `#!` line names one of them, or it
    has none. A file that cannot be read counts as one (the call then fails as written too)."""
    try:
        with open(path, "rb") as handle:
            first = handle.readline(256).decode("utf-8", "replace")
    except OSError:
        return True
    if not first.startswith("#!"):
        return True
    words_ = first[2:].split()
    if words_ and os.path.basename(words_[0]) == "env":
        words_ = [w for w in words_[1:] if not w.startswith("-") and "=" not in w]
    return bool(words_) and os.path.basename(words_[0]) == "bash"


def script_faithful(cmd: list[Word], directory: str, cwd: str) -> bool:
    """Whether `bash "<absolute path>" ...` from `cwd` does what the call does from `directory`:
    the script runs under bash or sh either way, and the folder is the same or the user listed
    the script in `sandbox-scripts` as one that does not depend on its working folder."""
    at = 1 if os.path.basename(cmd[0].value) in SHELL_INTERPRETERS else 0
    if at and os.path.basename(cmd[0].value) != "bash":
        return False  # `sh x.sh` would become `bash x.sh`
    if ".." in cmd[at].value.split("/"):
        return False  # the shell resolves `..` through symlinks
    path = absolute(cmd[at].value, directory)
    if at == 0 and not shell_script(path):
        return False
    if os.path.realpath(directory) == os.path.realpath(cwd):
        return True
    for w in cmd[at + 1:]:  # arguments that name files in the folder would name others
        v = w.value
        if not v.startswith("-") and (("/" in v and relative_file(v)) or (
                relative_file(v) and os.path.exists(os.path.join(directory, v)))):
            return False
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in listed_scripts())


def script_forms(cmd: list[Word], directory: str) -> list[list[Word]]:
    """`bash "<absolute path>" ...`, and `bash <absolute path> ...` where the path needs no
    quotes: the forms an entry may be written in."""
    at = 1 if os.path.basename(cmd[0].value) in SHELL_INTERPRETERS else 0
    path = absolute(cmd[at].value, directory)
    forms = []
    if not re.search(r'["$`\\!]', path):
        forms.append([quote("bash"), Word(f'"{path}"', path)] + cmd[at + 1:])
    if quote(path).raw == path:
        forms.append([quote("bash"), Word(path, path)] + cmd[at + 1:])
    return forms


def script_path(cmd: list[Word]) -> Word | None:
    """The script word of a call by path (`tools/remote/wait.sh`, `"<dir>/bin/remote-ssh"`,
    directly or by bash/sh). Which scripts count is up to the settings: judge() keeps only those
    whose `bash "<absolute path>"` form matches an excluded entry."""
    at = 1 if os.path.basename(cmd[0].value) in ("bash", "sh") and len(cmd) > 1 else 0
    v = cmd[at].value
    return cmd[at] if ("/" in v and not v.startswith("-") and "$" not in cmd[at].raw
                       and not globbed(cmd[at])) else None


GH_VALUE_FLAGS = {"--json", "-q", "--jq", "-t", "--template", "-R", "--repo", "-b", "--body",
                  "-F", "--body-file", "-T", "--title", "-B", "--base", "-H", "--head", "-l",
                  "--label", "-a", "--assignee", "-m", "--milestone", "-p", "--project", "-r",
                  "--reviewer", "-L", "--limit", "-s", "--state", "-S", "--search", "-A",
                  "--author", "-i", "--interval", "-D", "--dir", "-n", "--notes",
                  "--notes-file", "--target", "--input", "-X", "--method", "-f", "--raw-field",
                  "--field", "--env-file", "-e", "--env", "-o", "--org", "-u", "--user", "-c",
                  "--color", "-w", "--workflow", "-j", "--job", "--ref", "--branch",
                  "--notes-start-tag", "--discussion-category", "--add-label", "--remove-label",
                  "--add-assignee", "--remove-assignee", "--add-reviewer", "--remove-reviewer",
                  "--add-project", "--remove-project", "--subject", "--match-head-commit",
                  "--author-email"}


def gh_flags_and_positionals(cmd: list[Word], start: int) -> tuple[list[Word], list[int]]:
    """The flag words and the indices of positional words from `start` on; the value after a
    flag that takes one (GH_VALUE_FLAGS) is neither."""
    flags, positionals, skip = [], [], False
    for i in range(start, len(cmd)):
        v = cmd[i].value
        if skip:
            skip = False
        elif v == "--":
            positionals += list(range(i + 1, len(cmd)))
            break
        elif v.startswith("-") and v != "-":
            flags.append(cmd[i])
            skip = "=" not in v and v in GH_VALUE_FLAGS
        else:
            positionals.append(i)
    return flags, positionals


def gh_flag_value(cmd: list[Word], *names: str) -> bool:
    """Whether a flag is given in any spelling: `-R x`, `-Rx`, `-R=x`, `--repo x`, `--repo=x`;
    a flag's value (`--title "-Rough"`) is not a flag."""
    for w in gh_flags_and_positionals(cmd, 1)[0]:
        v = w.value
        for name in names:
            if v == name or v.startswith(name + "="):
                return True
            if len(name) == 2 and not name.startswith("--") and v.startswith(name) and v[2:3] != "-":
                return True
    return False


def gh_files(cmd: list[Word], group: str | None, sub: str | None, directory: str) -> list[Word]:
    """File arguments made absolute: --body-file, --notes-file, --input, --dir (also -F for
    issue/pr/release bodies, -D for downloads), `-F key=@file` for api, release upload files."""
    file_flags = {"--body-file", "--notes-file", "--input", "--dir", "--env-file"}
    if group in ("issue", "pr", "release"):
        file_flags.add("-F")
    if group in ("run", "release"):
        file_flags.add("-D")
    if group in ("secret", "variable"):
        file_flags.add("-f")
    out, previous = [], None
    upload = group == "release" and sub in ("upload", "create")
    assets = set(gh_flags_and_positionals(cmd, 1)[1][3:]) if upload else set()  # after the tag
    for i, w in enumerate(cmd):
        v = w.value
        if previous:
            out.append(local_path(w, directory))
            previous = None
            continue
        name = v.split("=")[0]
        if v in file_flags:
            previous = v
        elif name in file_flags and "=" in v:
            w = attached_path(w, name + "=", v.split("=", 1)[1], directory)
        elif group in ("api", "workflow") and re.fullmatch(r"[^=]+=@.*", v) and cmd[i - 1].value in (
                "-F", "--field"):
            key, path = v.split("=@", 1)
            w = attached_path(w, key + "=@", path, directory)
        elif i in assets:  # release upload|create TAG files, `file#label`
            path, hashed, label = v.partition("#")
            if not hashed:
                w = local_path(w, directory)
            elif "$" in w.raw or "`" in w.raw or path.startswith("~"):
                raise Unsafe("a computed release file")
            elif not path.startswith("/"):
                w = quote(local_path(Word(path, path), directory).value + "#" + label)
        out.append(w)
    return out


def rewrite_gh(cmd: list[Word], directory: str, same: bool) -> list[Word]:
    if len(cmd) < 2:
        raise Unsafe("bare gh")
    if cmd[1].value.startswith("-"):
        if all(w.value in ("--version", "--help", "-h") for w in cmd[1:]):
            return cmd
        raise Unsafe("gh with a leading flag")
    group = cmd[1].value
    sub = cmd[2].value if len(cmd) > 2 and not cmd[2].value.startswith("-") else None
    if (group, sub) in GH_FOLDER_BOUND or group in ("extension", "codespace", "gist"):
        raise Unsafe("gh acts on the folder")
    if group == "pr" and sub == "create" and (any(
            w.value.startswith("--fill") for w in cmd) or gh_flag_value(cmd, "-f")):
        raise Unsafe("gh pr create --fill reads the folder's commits")
    if group in ("pr", "issue") and sub == "create" and gh_flag_value(
            cmd, "-T", "--template", "--recover"):
        raise Unsafe("a template or recovery file looked up in the folder")
    if group == "pr" and sub == "merge" and not same and gh_flag_value(cmd, "-d", "--delete-branch"):
        raise Unsafe("gh pr merge --delete-branch also deletes the folder's branch")
    if group == "issue" and sub == "develop" and gh_flag_value(cmd, "--checkout", "-c"):
        raise Unsafe("gh issue develop --checkout")
    if sub == "download" and group in ("run", "release") and not gh_flag_value(cmd, "-D", "--dir"):
        raise Unsafe("a download into the folder")
    for w in cmd:
        if substituted(w):
            prev = cmd[cmd.index(w) - 1].value
            m = re.fullmatch(r'"?\$\(cat\s+([^\s)$`]+)\)"?', w.raw)
            if not (m and prev in ("--body", "-b")):
                raise Unsafe("$(...) in a gh argument")
    out = []
    for i, w in enumerate(cmd):  # --body "$(cat f)" -> --body-file f
        m = re.fullmatch(r'"?\$\(cat\s+([^\s)$`]+)\)"?', w.raw)
        if m and out and out[-1].value in ("--body", "-b"):
            out[-1] = Word("--body-file", "--body-file")
            path = m.group(1)
            out.append(quote(os.path.expanduser(path) if path.startswith("~") else path))
        else:
            out.append(w)
    cmd = out
    if same:
        return cmd
    cmd = gh_files(cmd, group, sub, directory)
    if group in GH_FOLDER_FREE:
        return cmd
    repo = gh_repo(directory)
    if not repo:
        raise Unsafe("not certain which repository gh would pick in the folder")
    if group == "api":
        positional = None
        skip = False
        for i, w in enumerate(cmd[2:], 2):
            if skip:
                skip = False
            elif w.value in GH_API_VALUE_OPTS:
                skip = True
            elif not w.value.startswith("-"):
                positional = i
                break
        if positional is None:
            raise Unsafe("gh api without an endpoint")
        if any(re.search(r"\{(owner|repo|branch)\}", w.value) for i, w in enumerate(cmd)
               if i != positional):
            raise Unsafe("a placeholder outside the endpoint")
        endpoint = cmd[positional].raw
        if "{branch}" in endpoint:
            branch = git_out(directory, "branch", "--show-current")
            if not branch:
                raise Unsafe("no current branch")
            endpoint = endpoint.replace("{branch}", branch)
        owner, name = repo.split("/")
        endpoint = endpoint.replace("{owner}", owner).replace("{repo}", name)
        return cmd[:positional] + [Word(endpoint, dequote(endpoint))] + cmd[positional + 1:]
    if group == "repo":
        if sub not in GH_REPO_ARG:
            raise Unsafe("gh repo subcommand")
        at = 3
        if at < len(cmd) and not cmd[at].value.startswith("-"):
            return cmd  # the repository is named
        return cmd[:at] + [quote(repo)] + cmd[at:]
    if group not in GH_REPO_FLAG:
        raise Unsafe("unknown gh command")
    if gh_flag_value(cmd, "-R", "--repo"):
        return cmd
    at = 3 if sub else 2
    extra = []
    if group == "pr" and sub in GH_PR_SELECTOR and not gh_flags_and_positionals(cmd, at)[1]:
        if sub not in GH_PR_READ:
            raise Unsafe("a change to the pull request of the folder's branch")
        extra.append(quote(folder_branch(directory, repo)))
    extra += [quote("-R"), quote(repo)]
    if group == "pr" and sub == "create" and not gh_flag_value(cmd, "-H", "--head"):
        extra += [quote("--head"), quote(folder_branch(directory, repo))]
    return cmd[:at] + extra + cmd[at:]


def rewrite_copy(kind: str, cmd: list[Word], directory: str) -> list[Word]:
    value_opts = SCP_VALUE_OPTS if kind == "scp" else RSYNC_VALUE_OPTS
    out = list(cmd)
    for at, w, role in operands(cmd, value_opts, RSYNC_LONG_VALUE if kind == "rsync" else set()):
        v = w.value
        if kind == "rsync" and role == "option" and (
                v == "--relative" or (not v.startswith("--") and "R" in v[1:])):
            raise Unsafe("rsync --relative keeps the path as written")
        if kind == "rsync" and (role in ("value:-f", "value:--filter") or v.startswith(
                "--filter=")) and re.match(r"\s*(merge|dir-merge|[.:])", v.split("=", 1)[-1]
                                           if role == "option" else v):
            raise Unsafe("an rsync filter that reads a rules file")
        if role == "operand" and not remote_operand(v):
            out[at] = local_path(w, directory)
        elif role in ("value:-i", "value:-F") or role[6:] in RSYNC_LONG_FILE:
            out[at] = local_path(w, directory)
        elif role == "value:-o":
            if not ssh_option_faithful(v):
                raise Unsafe("an ssh option the rewrite cannot place")
        elif role == "value:-S" and kind == "scp":
            if "/" in v and relative_file(v):
                raise Unsafe("a relative ssh program")
        elif role in ("value:-e", "value:--rsh") and kind == "rsync":
            if not ssh_line_faithful(v):
                raise Unsafe("an rsync remote shell the rewrite cannot place")
        elif role == "option" and kind == "rsync" and v.startswith("--"):
            name = v.split("=")[0]
            if name == "--rsh" and "=" in v and not ssh_line_faithful(v.split("=", 1)[1]):
                raise Unsafe("an rsync remote shell the rewrite cannot place")
            if "=" in v and name in RSYNC_LONG_FILE:
                out[at] = attached_path(w, name + "=", v.split("=", 1)[1], directory)
            elif "=" not in v and name not in RSYNC_LONG_VALUE | RSYNC_LONG_FLAG:
                raise Unsafe(f"unknown rsync option {name}")
    return out


def ssh_file_value(option: str, value: str) -> bool:
    """Whether an ssh option's value is a file relative to the working folder."""
    return relative_file(value) and not (option == "-S" and value.lower() == "none")


def ssh_option_faithful(value: str) -> bool:
    """An ssh `-o` value that means the same from another folder."""
    m = re.match(r"\s*([A-Za-z0-9]+)\s*(?:=|\s)\s*(.*)", value, re.S)
    if not m:
        return False
    key, setting = m.group(1).lower(), m.group(2).strip().strip("\"'")
    if key in SSH_COMMAND_KEYS:
        return False
    if key in SSH_FILE_KEYS:
        return setting.startswith(("/", "~", "%d")) or setting.lower() == "none"
    return True


def ssh_options(cmd: list[Word]):
    """Yield (index, word, option, value word or None, attached value) over ssh's options, up to
    the destination; Unsafe for a value option without its value."""
    i = 1
    while i < len(cmd):
        w = cmd[i]
        v = w.value
        if not v.startswith("-") or v == "-":
            return
        letters, found = v[1:], False
        for k, c in enumerate(letters):
            option = "-" + c
            if option in SSH_VALUE_OPTS:
                attached = letters[k + 1:]
                if not attached and i + 1 >= len(cmd):
                    raise Unsafe("an ssh option without its value")
                yield i, w, option, None if attached else cmd[i + 1], attached
                i += 0 if attached else 1
                found = True
                break
        if not found:
            yield i, w, None, None, ""
        i += 1


def ssh_line_faithful(line: str) -> bool:
    """rsync's `-e` command: plain ssh whose options mean the same from another folder."""
    try:
        tokens = [Word(t, t) for t in shlex.split(line)]
    except ValueError:
        return False
    if not tokens or os.path.basename(tokens[0].value) != "ssh":
        return False
    try:
        options = list(ssh_options(tokens))
    except Unsafe:
        return False
    if len(options) != len(tokens) - 1 - sum(1 for o in options if o[3] is not None):
        return False  # words after the options: not a plain remote shell
    for _, _, option, value, attached in options:
        text = attached or (value.value if value else "")
        if option in SSH_FILE_OPTS and ssh_file_value(option, text):
            return False
        if option == "-o" and not ssh_option_faithful(text):
            return False
    return True


def rewrite_ssh(cmd: list[Word], directory: str) -> list[Word]:
    """ssh with its file options absolute; the destination and remote command as written."""
    out, end = [cmd[0]], 1
    for i, w, option, value, attached in ssh_options(cmd):
        out.append(w)
        end = i + 1
        text = attached or (value.value if value else "")
        if option == "-o" and not ssh_option_faithful(text):
            raise Unsafe("an ssh option the rewrite cannot place")
        if option in SSH_FILE_OPTS and ssh_file_value(option, text):
            if attached:
                raise Unsafe("a relative ssh file the rewrite cannot place")
            value = local_path(value, directory)
        if value is not None:
            out.append(value)
            end = i + 2
    if end + 1 < len(cmd) and cmd[end + 1].value.startswith("-"):
        raise Unsafe("ssh reads options after the destination too")
    return out + cmd[end:]


def rewrite(kind: str, cmd: list[Word], directory: str, cwd: str) -> list[Word]:
    """The command as a lone call that does the same from `cwd`; Unsafe when there is none."""
    same = os.path.realpath(directory) == os.path.realpath(cwd)
    if kind == "gh":
        return rewrite_gh(cmd, directory, same)
    if kind == "script":
        forms = script_forms(cmd, directory)
        if not forms:
            raise Unsafe("a script path that cannot be quoted plainly")
        return forms[0]
    if same:
        return cmd
    if kind in ("scp", "rsync"):
        return rewrite_copy(kind, cmd, directory)
    if kind == "ssh":
        return rewrite_ssh(cmd, directory)
    return [cmd[0], quote("-C"), quote(directory)] + cmd[1:]  # git: matches no entry (measured)


# --- the decision ------------------------------------------------------------------------------

def parse_part(part: dict) -> list[Word]:
    if part["heredoc"] and "<<" in part["text"]:
        return heredoc_part(part["text"])
    return words(part["text"])


CD_OPS = ("&&", ";", "\n")


def cd_target(tokens: list[str], directory: str) -> str:
    """The folder a literal `cd <dir>` moves to from `directory`; Unsafe for any other cd."""
    target = re.sub(r"^\$(HOME\b|\{HOME\})", lambda _: os.path.expanduser("~"),
                    tokens[1] if len(tokens) == 2 else "")
    if len(tokens) != 2 or target in ("-", "") or re.search(r"[$`*?\[]", target):
        raise Unsafe("a computed or relative-history cd")
    return absolute(target, directory)


def judge(command: str, cwd: str, patterns: list[str] | None = None) -> str | None:
    """The refusal reason for `command` run from `cwd`, or None when it passes."""
    patterns = excluded_patterns() if patterns is None else patterns
    if not patterns or len(command) > MAX_INPUT:
        return None
    try:
        parts = scan(gg.strip_heredocs(command)[0])
    except Unparsed:
        return None
    loose = loose_match(parts, patterns)
    if loose:
        return loose
    directory, i = cwd, 0
    while i < len(parts):
        try:
            tokens = [w.value for w in words(parts[i]["text"])]
        except Unparsed:
            tokens = []
        if not tokens or tokens[0] != "cd" or parts[i]["op"] not in CD_OPS:
            break
        try:
            directory = cd_target(tokens, directory)
        except Unsafe:
            return None
        i += 1
    if i == len(parts):
        return None
    had_cd, rest = i > 0, parts[i:]
    found, known, lone_all = [], {}, True
    try:
        for n, part in enumerate(rest):
            tokens = parse_part(part)
            if tokens and tokens[0].value in CONTROL:
                return None
            if tokens and tokens[0].value in ("cd", "pushd", "popd"):  # a later cd moves on
                if tokens[0].value != "cd" or part["op"] not in CD_OPS or (
                        n > 0 and rest[n - 1]["op"] not in CD_OPS):
                    raise Unsafe("a cd this hook cannot follow")
                directory = cd_target([w.value for w in tokens], directory)
                had_cd, lone_all = True, False
                continue
            conditional = part["op"] in ("||", "|", "&") or (
                n > 0 and rest[n - 1]["op"] in ("||", "|", "&"))
            for name, value in assignments(tokens).items():
                if value is None or conditional:
                    known.pop(name, None)
                else:
                    known[name] = value
            prefix, cmd, assigned = split_command(tokens)
            cmd = [fill(w, known) for w in cmd]
            kind = classify(cmd)
            script_form = None
            if kind == "script":
                fitting = [f for f in script_forms(cmd, directory)
                           if matches(" ".join(w.raw for w in f), patterns)]
                if fitting and script_faithful(cmd, directory, cwd):
                    script_form = fitting[0]
                else:
                    kind = None  # no excluded entry, or not the same from the session's folder
            piped_in = n > 0 and rest[n - 1]["op"] == "|"
            if not kind:
                lone_all = False
                continue
            same = os.path.realpath(directory) == os.path.realpath(cwd)
            if part["op"] == "&":
                raise Unsafe("a network command in the background")
            if not same and any(globbed(w) for w in cmd):
                raise Unsafe("a glob the shell would expand against another folder")
            if assigned or prefix or piped_in or part["infile"] or part["outfile"]:
                raise Unsafe("input, output to a file, an assignment or a wrapper "
                             "(`command`, `exec`, `timeout`: the client does not exclude them)")
            if part["heredoc"] and (kind != "gh" or "<<" not in part["text"]):
                raise Unsafe("a here-document feeds the command")
            if any(substituted(w) for w in cmd) and kind != "gh":
                raise Unsafe("$(...) in the command")
            filters = []
            k = n
            while rest[k]["op"] == "|" and k + 1 < len(rest):  # what its output goes through
                k += 1
                ftokens = words(rest[k]["text"])
                if not ftokens or ftokens[0].value not in DISPLAY_FILTERS or rest[k]["outfile"] \
                        or (ftokens[0].value == "sort" and any(
                            w.value.startswith("--output") or (
                                re.match(r"-[^-]", w.value) and "o" in w.value)
                            for w in ftokens[1:])):
                    raise Unsafe("output piped into a command, or a filter that writes a file")
                filters.append(rest[k])
            new = prefix + (script_form or rewrite(kind, cmd, directory, cwd))
            ok = matches(" ".join(w.raw for w in new[len(prefix):]), patterns)
            written_ok = (matches(" ".join(w.raw for w in cmd), patterns) and not filters
                          and not part["heredoc"] and not part["subst"])
            lone_all = lone_all and written_ok
            found.append((kind, new, ok, bool(filters), written_ok))
    except (Unsafe, Unparsed):
        return None
    if not found:
        return None
    if had_cd:
        if not any(ok for _, _, ok, _, _ in found):
            return None  # e.g. only git for another folder: no form of it is excluded
    else:  # without a cd only a script outside its excluded form is refused
        if not any(kind == "script" and ok and not (written_ok and lone_all)
                   for kind, _, ok, _, written_ok in found):
            return None
    return reason(found, had_cd, directory)


def loose_match(parts: list[dict], patterns: list[str]) -> str | None:
    """A part that matches an excluded entry only through `..` or a `*` spanning a quote."""
    patterns = [p for p in patterns if "*" in re.sub(r"\\\*", "", p).rstrip("*")]
    for part in parts:
        try:
            _, cmd, _ = split_command(words(part["text"]))
        except Unparsed:
            continue
        text = " ".join(w.raw for w in cmd)
        head = " ".join(w.raw for w in cmd[:2])  # where a path a `*` spans can stand
        dotted = bool(re.search(r"/\.\.?(/|\"|'|$)", head))
        strict = " ".join(w.raw for w in cmd).replace(head, re.sub(r"/\.\.?/", "/", head), 1)
        if cmd and matches(text, patterns) and (dotted or not matches(strict, patterns, strict=True)):
            return (f"Refused by the {REASON_MARKER}: this call matches an "
                    f"excluded command only loosely (through `..`, or a `*` of the entry "
                    f"spanning a quote or a space), so it would run outside the sandbox:\n"
                    f"    {text}\n"
                    f"Write the path plainly, without `..` and as the entry's single word; "
                    f"a call that does not match runs inside the sandbox.")
    return None


def reason(found: list, had_cd: bool, directory: str) -> str:
    lines = [f"Refused by the {REASON_MARKER}: "
             + ("a Bash call that starts with `cd` stays in the sandbox, where this network "
                "command fails." if had_cd else
                "this script call does not match its excluded entry, so it stays in the "
                "sandbox, where it cannot reach the network.")
             + " Run it as its own call; this form matches an entry of your "
               "`sandbox.excludedCommands`, so it runs outside the sandbox as configured:"]
    filtered, needs_value = False, False
    for kind, new, ok, filters, _ in found:
        line = "    " + " ".join(w.raw for w in new)
        if not ok:
            line += ("   [matches no excluded command (`git -C` and `--git-dir` never do), so "
                     "it runs inside the sandbox]")
        lines.append(line)
        filtered = filtered or filters
        needs_value = needs_value or any(
            re.search(r"\$\{?(?!(HOME|USER|TMPDIR|PATH|PWD)\b)[A-Za-z_]",
                      re.sub(r"'[^']*'", "", w.raw)) for w in new)
    lines.append("Put nothing else in that call: no `&&`, `cd`, pipe, file redirection, "
                 "here-document or `$(...)`; `2>&1` is fine. Run the other parts as separate "
                 "calls" + ("; they may keep their `cd`." if had_cd else "."))
    if filtered:
        lines.append("Its output went through a filter: read it whole, use gh's `--jq`, or "
                     "filter ssh output on the remote side (`ssh host 'cmd | head'`).")
    if needs_value:
        lines.append("A variable in it has no value in a new call: put the value in literally "
                     "(compute it in an earlier call).")
    if any(w.value == "<file>" for _, new, _, _, _ in found for w in new):
        lines.append("Write the body with the Write tool and pass its path as `--body-file`.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--check":
        if len(argv) < 3:
            print("usage: pre_tool_cd_network.py --check '<command>' [--cwd <dir>]")
            return 64
        cwd = argv[argv.index("--cwd") + 1] if "--cwd" in argv else os.getcwd()
        found = judge(argv[2], cwd)
        if found:
            print(found)
            return 2
        return 0
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        command = (data.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            return 0
        found = judge(command, data.get("cwd") or os.getcwd())
    except Exception:  # a fault in this guard never blocks work
        return 0
    if found:
        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                          "permissionDecision": "deny",
                                          "permissionDecisionReason": found}}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
