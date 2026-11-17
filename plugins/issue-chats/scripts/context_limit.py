#!/usr/bin/env python3
"""Hook that enforces an issue chat's context limit (#77; the rule: skills/issue-handover/method.md
§1 `context limit` and §4; wired by the plugin's hooks/hooks.json through context-gate.sh).

Cost grows with context: every request re-reads the whole conversation. Chats did not keep to the
limit as a sentence (in pax_deorum 335 of 349 issue chats passed it, #77), and a chat does not see
its own context size. This hook reads it from the transcript and acts, in an issue-chat worktree
(question_label.chat_issue: branch `agent/<n>-…`, or a linked worktree's folder `<n>-…`) of a
repository whose HANDOFF.md has `## Issue chats settings`. Elsewhere it does nothing, and
context-gate.sh exits before Python starts unless the branch starts with `agent/<digit>`.

The limit L is the settings' `context limit` (tokens: `300000`, `300,000`, `300k`, `0.3M`),
default 300,000 (Igor, 2026-11-17, for every repository; DESIGN_DECISIONS.md owns the value and
its review date). The context is that of the newest API call in the transcript's tail: input plus
cache writes plus cache reads. The hook calls no model and costs no tokens; a note it adds costs a
few dozen. The settings are read once per session.

  PostToolUse, context >= L      note to the chat, again per further 25k: finish the step you
                                 are on and hand over, unless you judge you are close to a
                                 solution, then finish it first; at 2L the user decides.
                                 A subagent (agent_id): wrap up and report back now.
  PreToolUse, context >= 2L      main thread: refuse every tool but asking the user
  and no grant covering it       (AskUserQuestion, a blocked wrap_up), loading a skill, stopping
                                 a task, the desktop app's session and turn tools, ToolSearch,
                                 and Bash whose every command (split outside quotes, heredoc
                                 bodies set aside) is git, gh, a hand-over script of these
                                 plugins or a filter (tail, head, grep, wc, ...), with no command
                                 substitution but `$(cat <<…)`, no output redirection and no
                                 `git -c`; the session is marked stopped at that moment.
                                 A subagent: refuse every tool but its report (SubagentHandback,
                                 SendMessage), so it reports back.
  the user's answer while        a grant: the chat may work on until context + L/2, then it asks
  stopped                        again. The answer is the AskUserQuestion result (PostToolUse),
                                 or a message the user typed or clicked: a transcript record
                                 with `origin.kind` "human" newer than the stop. A notification,
                                 another session's or a subagent's message ("task-notification",
                                 "peer") grants nothing (measured in transcripts, 2026-11-17).
  context below L again          (compaction) notes, stop and grant are cleared.

It never blocks over its own failure (no transcript, unreadable state: pass). Deny is exit 2 with
the reason on stderr; notes are JSON `additionalContext` on stdout. State lives per session (and
subagent) in question_label.state_dir("context-limit"), the user's own folder.
AGENTIC_GITHUB_FLOW_CONTEXT_STATE replaces that folder (tests).
Tests: python3 tests/context_limit.py
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)  # -I leaves the script's folder off sys.path
from next_issue import row_in, settings_text  # noqa: E402
from question_label import chat_issue, state_dir  # noqa: E402

DEFAULT_LIMIT = 300_000
STEP = 25_000          # a further note per this much growth past the limit
TAIL = 512 * 1024      # bytes read from the transcript's end; once more at 8x when nothing is found
ASK = "AskUserQuestion"
ALWAYS = re.compile(r"^(AskUserQuestion|ToolSearch|Skill|TaskStop|mcp__ccd_turn__.*|"
                    r"mcp__ccd_session__.*|mcp__ccd_session_mgmt__.*|mcp__ccd_sidebar__.*)$")
SUBAGENT_ALWAYS = {"SubagentHandback", "SendMessage"}
SCRIPTS = (r"push_branch|overlap_check|start_issue_chat|next_issue|chat_archivable|landing|"
           r"merge_pr|merge_landing|promote_main|new_worktree|remove_merged_worktree|"
           r"delete_merged_branch|review_verdict|work_proof")
FIRST_WORDS = {"git", "gh", "cd", "tail", "head", "grep", "wc", "cut", "sort", "echo", "printf",
               "true"}
SCRIPT = re.compile(r"(?:^|/)(?:" + SCRIPTS + r")\.py$")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?=\n|$)", re.S)
CAT_HEREDOC = re.compile(r"\$\(\s*cat\s*<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*\)", re.S)
OPERATORS = {";", "&&", "||", "|", "&", "\n"}


def limit_for(top: str) -> int:
    try:
        _, text = settings_text(top)
    except Exception:
        return DEFAULT_LIMIT
    cell = (row_in(text, "context limit") or "").lower()
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k|m)?\b", cell)
    if not m:
        return DEFAULT_LIMIT
    n = float(m.group(1).replace(",", ""))
    n *= {"k": 1_000, "m": 1_000_000}.get(m.group(2) or "", 1)
    return int(n) if n >= 10_000 else DEFAULT_LIMIT


def transcript_of(data: dict) -> str | None:
    path = data.get("transcript_path") or ""
    agent = data.get("agent_id")
    if agent:
        stem = path[:-len(".jsonl")] if path.endswith(".jsonl") else path
        path = os.path.join(stem, "subagents", f"agent-{re.sub(r'[^A-Za-z0-9_-]', '', agent)}.jsonl")
    return path if path and os.path.isfile(path) else None


def tail_records(path: str, want):
    """Records of the transcript's tail, newest first, until want(record) returns a value."""
    size = os.path.getsize(path)
    for span in (TAIL, TAIL * 8):
        with open(path, "rb") as f:
            f.seek(max(0, size - span))
            lines = f.read().decode("utf-8", "replace").splitlines()
        for line in reversed(lines):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                got = want(r)
                if got is not None:
                    return got
        if span >= size:
            break
    return None


def context_now(path: str, sidechain: bool) -> int | None:
    """The context of the newest API call in the transcript."""
    def want(r):
        m = r.get("message")
        if r.get("type") != "assistant" or not isinstance(m, dict) or "usage" not in m:
            return None
        if bool(r.get("isSidechain")) != sidechain:
            return None
        u = m.get("usage") or {}
        return ((u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                + (u.get("cache_read_input_tokens") or 0))
    return tail_records(path, want)


def human_answer_since(path: str, since: str) -> bool:
    """Whether the user typed or clicked a message after `since` (ISO time)."""
    def want(r):
        ts = r.get("timestamp") or ""
        if ts and ts <= since:
            return False  # older than the stop: stop looking
        origin = r.get("origin")
        if r.get("type") == "user" and isinstance(origin, dict) and origin.get("kind") == "human":
            return True
        return None
    return tail_records(path, want) is True


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def state_path(data: dict) -> str | None:
    folder = state_dir("context-limit", "AGENTIC_GITHUB_FLOW_CONTEXT_STATE")
    if not folder:
        return None
    key = (data.get("session_id") or "unknown") + ("." + data["agent_id"] if data.get("agent_id") else "")
    return os.path.join(folder, re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".json")


def load(path: str | None) -> dict:
    if not path:
        return {}
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(path: str | None, state: dict) -> None:
    if not path:
        return
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


def note(event: str, text: str) -> int:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))
    return 0


def k(n: int) -> str:
    return f"{round(n / 1000)}k"


def handover_bash(command: str) -> bool:
    """Every command is git, gh, a hand-over script or a filter, and nothing runs hidden code."""
    text = CAT_HEREDOC.sub("BODY", command)  # gh issue comment --body "$(cat <<'EOF' … EOF)"
    text = HEREDOC.sub("<<BODY", text)       # a heredoc's body is data, not commands
    text = re.sub(r"\d?>&\d|\d?>\s*/dev/null", " ", text)  # 2>&1, >/dev/null write nothing
    unquoted = re.sub(r"'[^']*'", "''", text)  # single quotes: nothing in them runs
    if "$(" in unquoted or "`" in unquoted or re.search(r"(?:^|\s)git\s+(?:-\S+\s+)*-c\b", unquoted):
        return False
    try:
        lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|<>\n")
        lexer.whitespace = " \t\r"   # a newline separates commands
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    commands, current = [], []
    for tok in tokens:
        if tok and set(tok) <= set(";&|\n"):
            if current:
                commands.append(current)
            current = []
        elif tok and set(tok) <= set("<>") and tok != "<<":
            return False  # output redirection writes files
        else:
            current.append(tok)
    if current:
        commands.append(current)
    if not commands:
        return False
    for cmd in commands:
        first = cmd[0]
        if first in FIRST_WORDS:
            continue
        if re.fullmatch(r"(?:\S*/)?python3?", first):
            script = next((t for t in cmd[1:] if not t.startswith("-")), "")
            if SCRIPT.search(script):
                continue
        return False
    return True


def allowed_when_stopped(tool: str, args: dict, sub: bool) -> bool:
    if sub:
        return tool in SUBAGENT_ALWAYS
    if ALWAYS.match(tool or ""):
        return True
    return tool == "Bash" and handover_bash(args.get("command") or "")


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(data, dict):
        return 0
    event, tool = data.get("hook_event_name"), data.get("tool_name") or ""
    args = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    transcript = transcript_of(data)
    if not transcript:
        return 0
    spath = state_path(data)
    state = load(spath)
    if "issue" not in state:  # resolved once per session: the settings and the issue
        found = chat_issue(data.get("cwd") or "")
        state["issue"] = found[2] if found else None
        state["limit"] = limit_for(found[0]) if found else None
        save(spath, state)
    issue, lim = state.get("issue"), state.get("limit")
    if not isinstance(issue, int) or not isinstance(lim, int):
        return 0
    sub = bool(data.get("agent_id"))
    ctx = context_now(transcript, sidechain=sub)
    if ctx is None and sub:
        ctx = context_now(transcript, sidechain=False)
    if ctx is None:
        return 0
    hard = 2 * lim

    if ctx < lim and any(key in state for key in ("noted", "stopped_at", "stopped_time", "granted_until")):
        for key in ("noted", "stopped_at", "stopped_time", "granted_until"):
            state.pop(key, None)  # compacted or cleared below the limit
        save(spath, state)

    if event == "PreToolUse":
        if ctx < hard or ctx < state.get("granted_until", 0):
            return 0
        if not sub and state.get("stopped_time") and human_answer_since(transcript, state["stopped_time"]):
            state["granted_until"] = ctx + lim // 2
            state["grant_note"] = True
            for key in ("stopped_at", "stopped_time"):
                state.pop(key, None)
            save(spath, state)
            return 0
        if not state.get("stopped_time"):
            state["stopped_at"], state["stopped_time"] = ctx, now_iso()
            save(spath, state)
        if allowed_when_stopped(tool, args, sub):
            return 0
        if sub:
            print(f"context limit: this subagent's context is {k(ctx)}, past twice the limit "
                  f"({k(hard)}). Stop and report what you found and did to the chat that started "
                  f"you; no other tool runs.", file=sys.stderr)
            return 2
        print(f"context limit: the chat for issue #{issue} is at {k(ctx)} context, past twice the "
              f"limit ({k(hard)}). From here the user decides whether this chat works on. Ask the "
              f"user now, with AskUserQuestion or wrap_up with blocked: true (the question goes on "
              f"#{issue} with the question label first), whether to continue or hand over. Until "
              f"the user answers, only asking, skills, the session tools, and git, gh and the "
              f"hand-over scripts run. The rule: issue-handover method.md §4.", file=sys.stderr)
        return 2

    if event != "PostToolUse":
        return 0
    if tool == ASK and not sub and state.get("stopped_time"):
        state["granted_until"] = ctx + lim // 2
        state["grant_note"] = True
        for key in ("stopped_at", "stopped_time"):
            state.pop(key, None)
        save(spath, state)
    if state.pop("grant_note", None):
        save(spath, state)
        return note("PostToolUse", f"context limit: the user answered while this chat was stopped "
                                   f"at twice the limit. Follow that answer: to hand over, or to "
                                   f"work on; working on is allowed until "
                                   f"{k(state['granted_until'])}, then ask again.")
    if ctx < lim or ctx < state.get("noted", 0) + STEP:
        return 0
    state["noted"] = ctx
    save(spath, state)
    if sub:
        return note("PostToolUse", f"context limit: this subagent's context is {k(ctx)}, past the "
                                   f"limit ({k(lim)}). Wrap up and report back now; at {k(hard)} "
                                   f"its tools stop.")
    return note("PostToolUse", f"context limit: the chat for issue #{issue} is at {k(ctx)} context, "
                               f"past the limit ({k(lim)}); every further call re-reads it. Finish "
                               f"the step you are on and hand over (issue-handover), unless you "
                               f"judge you are close to a solution: then finish that first. At "
                               f"{k(hard)} the user decides whether this chat works on.")


if __name__ == "__main__":
    for stream in (sys.stdin, sys.stdout, sys.stderr):  # UTF-8, also where Windows uses cp1252
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    try:
        sys.exit(main())
    except Exception as e:  # never stop work over the hook's own fault
        print(f"context limit: hook failed, nothing done: {e}", file=sys.stderr)
        sys.exit(0)
