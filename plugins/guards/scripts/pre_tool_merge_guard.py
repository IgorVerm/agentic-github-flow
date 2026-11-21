#!/usr/bin/env python3
"""PreToolUse hook (Claude Code, Bash): refuse a bare `git merge <ref>` that the sandbox would
break, and name merge_landing.py (#108).

The Claude Code sandbox keeps a session from writing its own working directory's `.claude/` and
`.mcp.json` (#50). A plain `git merge` of a ref that changes them there dies half-way ("unable to
unlink old '.claude/…': Operation not permitted") and leaves the files that are new on the ref
behind as untracked files, which block every later merge and the hand-over's start tool. The core
plugin's `merge_landing.py` merges such a ref inside the sandbox. This hook refuses ("deny") the
bare merge before it writes anything when all of these hold:

1. the call runs inside the sandbox: not on native Windows (no sandbox there), the tool input
   has no `dangerouslyDisableSandbox`, `sandbox.enabled` is true in the Claude Code settings
   (user `$CLAUDE_CONFIG_DIR/settings.json` or `~/.claude/settings.json`, then the project's
   `.claude/settings.json` and `.claude/settings.local.json`, the later one winning), and not
   every part of the call matches an entry of `sandbox.excludedCommands` (matched as the opt-in
   sandbox-network guard matches them, `pre_tool_sandbox_network.matches`);
2. the merge runs in the session's own worktree: its top level is that of `CLAUDE_PROJECT_DIR`,
   else of the hook input's `cwd`. A plain merge in another worktree (an integration worktree,
   `local-main.md`) is not protected and passes;
3. `git merge-tree --write-tree HEAD <ref>` changes a path under `.claude/` or `.mcp.json`
   compared with HEAD, or conflicts there.

It reads `git merge` in the spellings the git guard's parser reads: `git -C <dir>`, a literal
`cd <dir> &&` before it, `env`/`timeout`-style wrappers and `sh -c '…'`; a merge without a ref
is judged for `@{upstream}`. It passes `--abort`, `--continue`, `--quit`, a ref git cannot resolve
(git then fails on its own), a computed `cd` or `-C`, `--git-dir`/`--work-tree`, and `git pull`,
whose merge target is known only after its fetch. It never answers "allow" or "ask", so it lets
nothing run that would not run without it; a fault in it, or a git call that fails or takes
longer than GIT_TIMEOUT seconds, lets the call pass. Work: one `rev-parse` per folder and one
`merge-tree` and `diff` per merged ref, which grow with what the ref changed.

Usage as a hook: reads JSON on stdin. For tests:
`pre_tool_merge_guard.py --check '<command>' [--cwd <dir>] [--project <dir>]` judges as if the
sandbox were on with no excluded commands; it prints the reason and exits 2, or exits 0.
Test: `python3 tests/merge_guard.py`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "pre_tool_sandbox_network", os.path.join(HERE, "pre_tool_sandbox_network.py"))
sn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sn)  # owner of the excludedCommands matching
gg = sn.gg  # pre_tool_git_guard: owner of the shell parsing

GIT_TIMEOUT = 5
MARKER = "merge guard"
WRAPPERS = {"env", "command", "builtin", "exec", "nohup", "time", "timeout", "nice", "noglob",
            "caffeinate", "stdbuf"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
MERGE_VALUE_OPTS = {"-m", "-F", "-s", "-X", "--file", "--strategy", "--strategy-option",
                    "--into-name", "--cleanup", "-S"}
STOP = {"--abort", "--continue", "--quit", "--skip"}
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")


def protected(path: str) -> bool:
    """As work_proof.protected in the core plugin (#50), which this plugin cannot import."""
    return path == ".mcp.json" or path.startswith(".claude/")


def git(directory: str, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", directory, *args], capture_output=True, text=True,
                              timeout=GIT_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None


def toplevel(directory: str) -> str | None:
    run = git(directory, "rev-parse", "--show-toplevel")
    if run is None or run.returncode:
        return None
    return os.path.normcase(os.path.realpath(run.stdout.strip()))


def literal_dir(value: str, directory: str | None) -> str | None:
    """`value` as a folder from `directory`; None when computed or unknown."""
    if directory is None or not value or re.search(r"[$`*?\[]", value) or value == "-":
        return None
    expanded = os.path.expanduser(value)
    return os.path.normpath(expanded if os.path.isabs(expanded)
                            else os.path.join(directory, expanded))


def git_merge(args: list[str], directory: str | None):
    """(folder, refs) for `git <args>` when it is a merge to judge, else None."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        opt = args[i]
        if opt == "-C" and i + 1 < len(args):
            directory = literal_dir(args[i + 1], directory)
            i += 2
        elif opt in ("--git-dir", "--work-tree") or opt.startswith(("--git-dir=", "--work-tree=")):
            return None
        elif opt in gg.GIT_VALUE_OPTS:
            i += 2
        else:
            i += 1
    if i >= len(args) or args[i] != "merge" or directory is None:
        return None
    rest, refs, j = args[i + 1:], [], 0
    while j < len(rest):
        a = rest[j]
        if a in STOP or a in ("-h", "--help"):
            return None
        if a == "--":
            refs.extend(rest[j + 1:])
            break
        if a in MERGE_VALUE_OPTS:
            j += 2
            continue
        if not a.startswith("-"):
            refs.append(a)
        j += 1
    return directory, refs or ["@{upstream}"]


def merges(text: str, directory: str | None, depth: int = 0):
    """Yield (folder, refs) for each `git merge` in a command run from `directory`."""
    if depth > 4:
        return
    text = gg.strip_heredocs(text.replace("\\\n", " "))[0]
    for tokens in gg.split_commands(text):
        while tokens and (ASSIGN.match(tokens[0]) or tokens[0] in gg.KEYWORDS):
            tokens = tokens[1:]
        while tokens and gg.base(tokens[0]) in WRAPPERS:
            tokens = tokens[1:]
            while tokens and (tokens[0].startswith("-") or ASSIGN.match(tokens[0])
                              or re.fullmatch(r"[0-9.]+[smhd]?", tokens[0])):
                tokens = tokens[1:]
        if not tokens:
            continue
        name = gg.base(tokens[0])
        if name == "cd":
            directory = literal_dir(tokens[1], directory) if len(tokens) == 2 else None
        elif name == "git":
            found = git_merge(tokens[1:], directory)
            if found:
                yield found
        elif name in SHELLS:
            for j, tok in enumerate(tokens[1:], 1):
                if re.fullmatch(r"-[a-z]*c[a-z]*", tok) and j + 1 < len(tokens):
                    yield from merges(tokens[j + 1], directory, depth + 1)
                    break


def touched(folder: str, ref: str) -> list[str] | None:
    """The protected paths merging `ref` into HEAD in `folder` changes or conflicts in; None
    when git cannot tell."""
    if (run := git(folder, "rev-parse", "-q", "--verify", ref + "^{commit}")) is None or \
            run.returncode:
        return None
    run = git(folder, "merge-tree", "--write-tree", "-z", "--name-only", "HEAD", ref)
    if run is None or run.returncode not in (0, 1) or not run.stdout:
        return None
    result, _, rest = run.stdout.partition("\0")
    conflicts = [p for p in rest.partition("\0\0")[0].split("\0") if p] if run.returncode else []
    diff = git(folder, "diff", "--name-only", "-z", "--no-renames", "HEAD", result, "--",
               ".claude", ".mcp.json")
    if diff is None or diff.returncode:
        return None
    return sorted({p for p in diff.stdout.split("\0") + conflicts if p and protected(p)})


def merge_landing_path() -> str:
    """merge_landing.py beside this plugin in a clone of the repository (the installer's
    layout), else its place by name: a client's plugin cache keeps several core versions."""
    candidate = os.path.join(HERE, "..", "..", "core", "scripts", "merge_landing.py")
    if os.path.isfile(candidate):
        return os.path.realpath(candidate)
    return "<core plugin>/scripts/merge_landing.py"


def judge(command: str, cwd: str, project: str | None) -> str | None:
    """The refusal for `command` run inside the sandbox from `cwd`, or None."""
    if "merge" not in command or not gg.may_run_git(command):
        return None
    own = toplevel(project or cwd)
    if own is None:
        return None
    tops: dict[str, str | None] = {}
    for folder, refs in merges(command, cwd):
        if folder not in tops:
            tops[folder] = toplevel(folder)
        if tops[folder] != own:
            continue
        for ref in refs:
            paths = touched(folder, ref)
            if paths:
                shown = ", ".join(paths[:5]) + (f" and {len(paths) - 5} more"
                                                if len(paths) > 5 else "")
                return (f"Refused by the {MARKER} (agentic-github-flow, #108): merging {ref} "
                        f"here changes {shown}, which the Claude Code sandbox keeps this session "
                        "from writing. A plain `git merge` would die half-way and leave the "
                        "ref's new files behind as untracked files. Merge it with:\n"
                        f"    python3 {shlex.quote(merge_landing_path())} {shlex.quote(ref)}\n"
                        "(the ship-change skill, step 2: it commits the merge and keeps "
                        ".claude/ and .mcp.json on disk as this chat started with them; "
                        "`merge_landing.py --abort` undoes a stopped one).")
    return None


def settings_files(project: str | None) -> list[str]:
    files = [sn.claude_settings_path()]
    if project:
        files += [os.path.join(project, ".claude", name)
                  for name in ("settings.json", "settings.local.json")]
    return files


def sandboxed(command: str, tool_input: dict, project: str | None) -> bool:
    """True when Claude Code would run this call inside its sandbox."""
    if os.name == "nt" or tool_input.get("dangerouslyDisableSandbox") is True:
        return False
    enabled, patterns = False, []
    for name in settings_files(project):
        try:
            with open(name, encoding="utf-8") as handle:
                sandbox = json.load(handle).get("sandbox")
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(sandbox, dict):
            continue
        if isinstance(sandbox.get("enabled"), bool):
            enabled = sandbox["enabled"]
        entries = sandbox.get("excludedCommands")
        if isinstance(entries, list):
            patterns += [e for e in entries if isinstance(e, str) and e.strip()]
    if not enabled:
        return False
    if not patterns:
        return True
    try:
        parts = [" ".join(tokens) for tokens in gg.split_commands(command)]
    except ValueError:
        return True
    return not (parts and all(sn.matches(part, patterns) for part in parts))


def main(argv: list[str]) -> int:
    if len(argv) > 2 and argv[1] == "--check":
        cwd = argv[argv.index("--cwd") + 1] if "--cwd" in argv else os.getcwd()
        project = argv[argv.index("--project") + 1] if "--project" in argv else None
        found = judge(argv[2], cwd, project)
        if found:
            print(found)
            return 2
        return 0
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or data.get("tool_name") != "Bash":
            return 0
        tool_input = data.get("tool_input") or {}
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        if not isinstance(command, str):
            return 0
        cwd = data.get("cwd") or os.getcwd()
        project = os.environ.get("CLAUDE_PROJECT_DIR") or None
        if not sandboxed(command, tool_input, project or cwd):
            return 0
        found = judge(command, cwd, project)
    except Exception:  # a fault in this guard never blocks work
        return 0
    if found:
        sys.stderr.write(found + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
