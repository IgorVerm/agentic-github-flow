#!/usr/bin/env python3
"""Hook that keeps an issue's question label true (#75; the rule: skills/issue-handover/method.md
§4, *Questions for the user*; wired by the plugin's hooks/hooks.json in Claude Code).

The question label (`question label` in HANDOFF.md §Issue chats settings, else `needs-user`)
shows that an issue's work waits on the user. A chat that asked only in its own window left the
issue looking idle (#75). This hook makes the label follow the question, where a tool call shows
one; it never writes the question or the answer to GitHub itself, so the words stay the chat's
and pass the personal-data guard on the chat's own `gh` command.

It acts only in a repository whose HANDOFF.md, as the default branch holds it, has
`## Issue chats settings`. Asking and answering also need an issue-chat worktree: the branch
`agent/<issue>-<name>`, or, in a linked worktree only, the folder `<issue>-<name>` (a worktree
tool that names branches its own way); `release/2025-01` or a checkout called `2024-site` is
none. Per event:

  PreToolUse AskUserQuestion, or       the issue lacks the label -> deny (exit 2), naming the
  mcp__ccd_turn__wrap_up with          command that posts the question and adds the label;
  `blocked: true` (the work stops      the label is there -> pass and note that this session
  until the user answers)              asked about that issue (a marker file per session)
  PostToolUse AskUserQuestion, or      this session asked about the issue -> remove the label
  UserPromptSubmit (the answer came    and tell the chat to record the answer on the issue;
  back, or the user typed it)          no marker -> nothing (a start brief, an unrelated
                                       message, another chat's question keep the label)
  PostToolUse Bash running             the pull request merged -> remove the label from the
  `merge_pr.py <n>`, `gh pr merge <n>` issues it closes in the same repository (-R, else
  or `gh issue close <n>`              origin's URL; not waiting for CLOSED, which GitHub sets
                                       seconds later); the issue CLOSED -> remove it there.
                                       `cd <dir> &&` in front and `-R/--repo` are followed.

The overview chat's standing issue (the label of the settings row `overview label`, default
`overview`; method §8) is exempt from the ask check: the overview's questions belong to the issues
they are about, which carry the label themselves, and its standing issue holds only state and
claims.

Known limits: two questions open on one issue at once lose the label at the first answer (the
chat adds it again); a question asked in plain text, and an issue closed on github.com or by a
command this hook does not parse, are not seen (cleanup-merged step 4 still removes the label at
the close). The Codex worker's turns run no hooks (`codex_worker.py`).

It never blocks for its own failures: no gh, no network, no repository -> pass silently, since a
question to the user must always be possible. Deny is exit 2 with the reason on stderr; notes
to the chat are JSON `additionalContext` on stdout.
The marker folder is the user's own: $CLAUDE_PLUGIN_DATA/question-markers, else
~/.cache/agentic-github-flow/question-markers, made 0700 and not used when it is a symlink or
another user's; markers open without following symlinks. Never the shared temp folder.
AGENTIC_GITHUB_FLOW_GH (a JSON list) replaces `gh`; AGENTIC_GITHUB_FLOW_QUESTION_STATE replaces
the marker folder.
Tests: python3 tests/question_label.py
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import stat

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)  # -I leaves the script's folder off sys.path
from next_issue import SECTION, SettingError, git, label_value, settings_text  # noqa: E402

ASK = "AskUserQuestion"
WRAP_UP = "mcp__ccd_turn__wrap_up"
DEFAULT_LABEL = "needs-user"
GH_TIMEOUT_S = 10  # hooks.json gives the hook 30 s
ISSUE_BRANCH = re.compile(r"^agent/(\d+)-")
ISSUE_DIR = re.compile(r"^(\d+)-[A-Za-z]")
REMOTE = re.compile(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")
CLOSERS = [
    ("pr", re.compile(r"(?:^|[\s/])merge_pr\.py\s+(\d+)\b")),
    ("pr", re.compile(r"\bgh\s+pr\s+merge\s+#?(\d+)\b")),
    ("issue", re.compile(r"\bgh\s+issue\s+close\s+#?(\d+)\b")),
]
LEADING_CD = re.compile(r"^\s*cd\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)\s*&&")
SEPARATOR = re.compile(r"&&|\|\||[;|\n]")
REPO_FLAG = re.compile(r"(?:^|\s)(?:-R|--repo)(?:\s+|=)([\w.-]+/[\w.-]+)(?=\s|$)")


class Unread(Exception):
    pass


def gh(args: list[str], cwd: str) -> str:
    raw = os.environ.get("AGENTIC_GITHUB_FLOW_GH")
    try:
        command = json.loads(raw) if raw else ["gh"]
    except ValueError:
        raise Unread("AGENTIC_GITHUB_FLOW_GH is no JSON list")
    try:
        p = subprocess.run(command + args, cwd=cwd, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=GH_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as e:
        raise Unread(str(e))
    if p.returncode:
        raise Unread((p.stderr or p.stdout).strip()[:200] or f"gh exit {p.returncode}")
    return p.stdout


def gh_json(args: list[str], cwd: str):
    try:
        return json.loads(gh(args, cwd) or "null")
    except ValueError as e:
        raise Unread(f"gh gave no JSON: {e}")


def settings(path: str) -> tuple[str, str] | None:
    """(top level, question label) where issue chats are switched on, else None."""
    if not path or not os.path.isdir(path):
        return None
    try:
        top, text = settings_text(path)
    except SettingError:
        return None
    if not text or not SECTION.search(text):
        return None
    return top, label_value(text, "question label", DEFAULT_LABEL)


def chat_issue(path: str) -> tuple[str, str, int] | None:
    """(top level, label, issue) for an issue-chat worktree, else None."""
    found = settings(path)
    if not found:
        return None
    top, label = found
    branch = git(path, "branch", "--show-current").stdout.strip()
    m = ISSUE_BRANCH.match(branch)
    if not m and linked_worktree(path):  # a worktree tool that names branches its own way
        m = ISSUE_DIR.match(os.path.basename(top))
    return (top, label, int(m.group(1))) if m else None


def linked_worktree(path: str) -> bool:
    """A linked worktree (its git dir differs from the common one), not a primary checkout."""
    p = git(path, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir")
    dirs = p.stdout.split()
    return p.returncode == 0 and len(dirs) == 2 and dirs[0] != dirs[1]


def own_repo(top: str, flag: str | None) -> str | None:
    """owner/name of the repository a command acts on: its -R flag, else origin's URL."""
    if flag:
        return flag.lower()
    m = REMOTE.search(git(top, "remote", "get-url", "origin").stdout.strip())
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def ref_repo(ref: dict) -> str:
    r = ref.get("repository") or {}
    return f"{(r.get('owner') or {}).get('login', '')}/{r.get('name', '')}".lower()


def overview_label(top: str) -> str:
    try:
        return label_value(settings_text(top)[1], "overview label", "overview")
    except SettingError:
        return "overview"


def labels_of(issue: int, cwd: str, repo: list[str] | None = None) -> list[str]:
    data = gh_json(["issue", "view", str(issue), "--json", "labels", *(repo or [])], cwd)
    return [x.get("name", "") for x in (data or {}).get("labels", [])]


def remove_label(issue: int, label: str, cwd: str, repo: list[str] | None = None) -> None:
    gh(["issue", "edit", str(issue), "--remove-label", label, *(repo or [])], cwd)


def state_dir(name: str = "question-markers",
              env: str = "AGENTIC_GITHUB_FLOW_QUESTION_STATE",
              plugin_data: bool = True) -> str | None:
    """The marker folder <name>, private to this user, or None when it cannot be trusted.

    Not the shared temp folder: on a multi-user host another user could make it first and read
    or redirect the markers. The plugin's data folder, else one under the user's home; made 0700,
    and refused when it is a symlink or another user's. context_limit.py uses it too, and with
    plugin_data=False (always under the home) for what a script outside the plugin's hooks writes
    for them, since only the hooks get CLAUDE_PLUGIN_DATA."""
    path = (os.environ.get(env)
            or (os.path.join(os.environ["CLAUDE_PLUGIN_DATA"], name)
                if plugin_data and os.environ.get("CLAUDE_PLUGIN_DATA") else None)
            or os.path.join(os.path.expanduser("~"), ".cache", "agentic-github-flow", name))
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        st = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        return None
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        return None
    return path


def marker(folder: str, session: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session or "unknown")
    return os.path.join(folder, safe + ".json")


def write_marker(session: str, content: dict) -> None:
    folder = state_dir()
    if not folder:
        return
    path = marker(folder, session)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(content, f)
    except OSError:
        pass


def take_marker(session: str) -> dict | None:
    """This session's marker, removed as it is read (a stale one goes too)."""
    folder = state_dir()
    if not folder:
        return None
    path = marker(folder, session)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, encoding="utf-8") as f:
            content = json.load(f)
    except (OSError, ValueError):
        return None
    finally:
        try:
            if os.path.lexists(path):
                os.remove(path)
        except OSError:
            pass
    return content if isinstance(content, dict) else None


def note(event: str, text: str) -> int:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
    return 0


def on_ask(data: dict) -> int:
    tool, args = data.get("tool_name"), data.get("tool_input") or {}
    if tool == WRAP_UP and args.get("blocked") is not True:
        return 0
    if data.get("agent_id"):
        return 0  # a subagent's call; its chat asks, not it
    found = chat_issue(data.get("cwd") or "")
    if not found:
        return 0
    top, label, issue = found
    try:
        labels = labels_of(issue, top)
    except Unread:
        return 0
    if overview_label(top) in labels:
        return 0  # the overview's standing issue (method §8)
    if label not in labels:
        print(f"question label: this question makes the chat for issue #{issue} wait on the user, "
              f"but #{issue} does not carry `{label}`, so nobody looking at the issues can see "
              f"that. Put the question on the issue first, signed, and add the label in the same "
              f"step:\n  gh issue comment {issue} --body '<signature> <the question>' && "
              f"gh issue edit {issue} --add-label {shlex.quote(label)}\n(once per repository, if "
              f"the label is missing: gh label create {shlex.quote(label)}). Then ask again. "
              f"The rule: issue-handover method.md §4, Questions for the user.", file=sys.stderr)
        return 2
    write_marker(data.get("session_id", ""), {"issue": issue, "label": label, "top": top})
    return 0


def on_answer(data: dict, event: str) -> int:
    asked = take_marker(data.get("session_id", ""))
    if not asked:
        return 0
    issue, label, top = asked.get("issue"), asked.get("label"), asked.get("top")
    if not isinstance(issue, int) or not isinstance(label, str) or not label \
            or not isinstance(top, str) or not os.path.isdir(top):
        return 0
    try:
        if label in labels_of(issue, top):
            remove_label(issue, label, top)
        done = f"removed `{label}` from #{issue}"
    except Unread as e:
        done = f"could not remove `{label}` from #{issue} ({e}); remove it yourself"
    return note(event, f"question label: the user answered the question on #{issue}; {done}. "
                       f"Record the answer on #{issue} in a signed comment, in the user's words. "
                       f"If another question there is still open, name it in that comment and "
                       f"add `{label}` again.")


def on_bash(data: dict) -> int:
    command = (data.get("tool_input") or {}).get("command") or ""
    hits = []
    for kind, rx in CLOSERS:
        for m in rx.finditer(command):
            # -R/--repo counts only inside this command's own segment, so `grep -R src/lib`
            # elsewhere on the line is never read as a repository.
            segment = SEPARATOR.split(command[m.start():], maxsplit=1)[0]
            flag = REPO_FLAG.search(segment)
            hits.append((kind, int(m.group(1)), flag.group(1) if flag else None))
    if not hits:
        return 0
    where = data.get("cwd") or ""
    cd = LEADING_CD.match(command)
    if cd:
        target = os.path.expanduser(cd.group(1).strip("\"'"))
        where = target if os.path.isabs(target) else os.path.join(where, target)
    found = settings(where)
    if not found:
        return 0
    top, label = found
    removed, failed = [], []
    for kind, n, flag in hits:
        repo = ["-R", flag] if flag else []
        try:
            if kind == "pr":
                pr = gh_json(["pr", "view", str(n), "--json", "state,closingIssuesReferences",
                              *repo], top) or {}
                if pr.get("state") != "MERGED":
                    continue
                # Only this repository's issues: a reference to another repository's #n must
                # not take the label off this one's #n. Not waiting for CLOSED: GitHub closes
                # the referenced issues a few seconds after the merge (#70 read OPEN just after
                # PR #71 merged), and a merged pull request closes them.
                here = own_repo(top, flag)
                issues = [i.get("number") for i in pr.get("closingIssuesReferences") or []
                          if here and ref_repo(i) == here]
            else:
                st = gh_json(["issue", "view", str(n), "--json", "state", *repo], top) or {}
                issues = [n] if st.get("state") == "CLOSED" else []
            for i in issues:
                if isinstance(i, int) and label in labels_of(i, top, repo):
                    remove_label(i, label, top, repo)
                    removed.append(f"#{i}")
        except Unread as e:
            failed.append(f"{kind} {n}: {e}")
    if not removed and not failed:
        return 0
    parts = []
    if removed:
        parts.append(f"removed `{label}` from the closed {', '.join(removed)}")
    if failed:
        parts.append("could not check " + "; ".join(failed) + " (cleanup-merged step 4 removes it)")
    return note("PostToolUse", "question label: " + "; ".join(parts) + ".")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    event, tool = data.get("hook_event_name"), data.get("tool_name")
    if event == "PreToolUse" and tool in (ASK, WRAP_UP):
        return on_ask(data)
    if event == "PostToolUse" and tool == ASK:
        return on_answer(data, "PostToolUse")
    if event == "UserPromptSubmit":
        return on_answer(data, "UserPromptSubmit")
    if event == "PostToolUse" and tool == "Bash":
        return on_bash(data)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):  # UTF-8, also where Windows uses cp1252
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        sys.exit(main())
    except Exception as e:  # never stop a question or a command over the hook's own fault
        print(f"question label: hook failed, nothing done: {e}", file=sys.stderr)
        sys.exit(0)
