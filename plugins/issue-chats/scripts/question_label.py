#!/usr/bin/env python3
"""Hook that keeps an issue's question label true (#75; the rule: skills/issue-handover/method.md
§4, *Questions for the user*; wired by the plugin's hooks/hooks.json in Claude Code).

The question label (`question label` in HANDOFF.md §Issue chats settings, else `needs-user`)
shows that an issue's work waits on the user. A chat that asked only in its own window left the
issue looking idle (#75). This hook makes the label follow the question, where a tool call shows
one; it never writes the question or the answer to GitHub itself, so the words stay the chat's
and pass the personal-data guard on the chat's own `gh` command.

It acts only in a repository whose HANDOFF.md, as the default branch holds it, has
`## Issue chats settings`. Asking and answering also need an issue-chat worktree: a branch or
worktree folder named `<issue>-<name>` (`agent/<issue>-<name>`). Per event:

  PreToolUse AskUserQuestion, or       the issue lacks the label -> deny (exit 2), naming the
  mcp__ccd_turn__wrap_up with          command that posts the question and adds the label;
  `blocked: true` (the work stops      the label is there -> pass and note that this session
  until the user answers)              asked about that issue (a marker file per session)
  PostToolUse AskUserQuestion, or      this session asked about the issue -> remove the label
  UserPromptSubmit (the answer came    and tell the chat to record the answer on the issue;
  back, or the user typed it)          no marker -> nothing (a start brief, an unrelated
                                       message, another chat's question keep the label)
  PostToolUse Bash running             the pull request merged -> remove the label from the
  `merge_pr.py <n>`, `gh pr merge <n>` issues it closes; the issue closed -> remove it there.
  or `gh issue close <n>`              `cd <dir> &&` in front and `-R/--repo` are followed.

Known limits: two questions open on one issue at once lose the label at the first answer (the
chat adds it again); a question asked in plain text, and an issue closed on github.com or by a
command this hook does not parse, are not seen (cleanup-merged step 4 still removes the label at
the close). Codex runs no such hooks.

It never blocks for its own failures: no gh, no network, no repository -> pass silently, since a
question to the user must always be possible. Deny is exit 2 with the reason on stderr; notes
to the chat are JSON `additionalContext` on stdout.
AGENTIC_GITHUB_FLOW_GH (a JSON list) replaces `gh`; AGENTIC_GITHUB_FLOW_QUESTION_STATE replaces
the marker folder (default: <temp>/agentic-github-flow-questions).
Tests: python3 tests/question_label.py
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)  # -I leaves the script's folder off sys.path
from next_issue import SECTION, SettingError, git, label_value, settings_text  # noqa: E402

ASK = "AskUserQuestion"
WRAP_UP = "mcp__ccd_turn__wrap_up"
DEFAULT_LABEL = "needs-user"
GH_TIMEOUT_S = 10  # hooks.json gives the hook 30 s
ISSUE_DIR = re.compile(r"^(?:[^/]+/)*(\d+)-")
CLOSERS = [
    ("pr", re.compile(r"(?:^|[\s/])merge_pr\.py\s+(\d+)\b")),
    ("pr", re.compile(r"\bgh\s+pr\s+merge\s+#?(\d+)\b")),
    ("issue", re.compile(r"\bgh\s+issue\s+close\s+#?(\d+)\b")),
]
LEADING_CD = re.compile(r"^\s*cd\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)\s*&&")
REPO_FLAG = re.compile(r"(?:-R|--repo)[\s=]+([\w.-]+/[\w.-]+)")


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
    m = ISSUE_DIR.match(branch) or ISSUE_DIR.match(os.path.basename(top))
    return (top, label, int(m.group(1))) if m else None


def labels_of(issue: int, cwd: str, repo: list[str] | None = None) -> list[str]:
    data = gh_json(["issue", "view", str(issue), "--json", "labels", *(repo or [])], cwd)
    return [x.get("name", "") for x in (data or {}).get("labels", [])]


def remove_label(issue: int, label: str, cwd: str, repo: list[str] | None = None) -> None:
    gh(["issue", "edit", str(issue), "--remove-label", label, *(repo or [])], cwd)


def state_dir() -> str:
    return os.environ.get("AGENTIC_GITHUB_FLOW_QUESTION_STATE") or os.path.join(
        tempfile.gettempdir(), "agentic-github-flow-questions")


def marker(session: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session or "unknown")
    return os.path.join(state_dir(), safe + ".json")


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
        present = label in labels_of(issue, top)
    except Unread:
        return 0
    if not present:
        print(f"question label: this question makes the chat for issue #{issue} wait on the user, "
              f"but #{issue} does not carry `{label}`, so nobody looking at the issues can see "
              f"that. Put the question on the issue first, signed, and add the label in the same "
              f"step:\n  gh issue comment {issue} --body '<signature> <the question>' && "
              f"gh issue edit {issue} --add-label {shlex.quote(label)}\n(once per repository, if "
              f"the label is missing: gh label create {shlex.quote(label)}). Then ask again. "
              f"The rule: issue-handover method.md §4, Questions for the user.", file=sys.stderr)
        return 2
    try:
        os.makedirs(state_dir(), exist_ok=True)
        with open(marker(data.get("session_id", "")), "w", encoding="utf-8") as f:
            json.dump({"issue": issue, "label": label, "top": top}, f)
    except OSError:
        pass
    return 0


def on_answer(data: dict, event: str) -> int:
    path = marker(data.get("session_id", ""))
    try:
        with open(path, encoding="utf-8") as f:
            asked = json.load(f)
    except (OSError, ValueError):
        return 0
    issue, label, top = asked.get("issue"), asked.get("label"), asked.get("top")
    if not isinstance(issue, int) or not label or not top or not os.path.isdir(top):
        return 0
    try:
        os.remove(path)
    except OSError:
        pass
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
    hits = [(kind, int(m.group(1))) for kind, rx in CLOSERS for m in rx.finditer(command)]
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
    repo_m = REPO_FLAG.search(command)
    repo = ["-R", repo_m.group(1)] if repo_m else []
    removed, failed = [], []
    for kind, n in hits:
        try:
            if kind == "pr":
                pr = gh_json(["pr", "view", str(n), "--json", "state,closingIssuesReferences",
                              *repo], top) or {}
                if pr.get("state") != "MERGED":
                    continue
                issues = [i.get("number") for i in pr.get("closingIssuesReferences") or []]
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
    try:
        sys.exit(main())
    except Exception as e:  # never stop a question or a command over the hook's own fault
        print(f"question label: hook failed, nothing done: {e}", file=sys.stderr)
        sys.exit(0)
