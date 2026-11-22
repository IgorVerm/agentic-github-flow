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
default 300,000 (the maintainer, 2026-11-17, for every repository; DESIGN_DECISIONS.md owns
the values and their review date). A label may have its own limit (#82, the maintainer
2026-11-22: `work: model` and `work: animation` get 600k):
`` `300k`; label `work: model`: `600k` ``. A chat whose issue
carries such a label gets the largest of them; every other chat the count before the first
label. The context is that of the newest API call in the transcript's tail: input plus cache
writes plus cache reads. The hook calls no model and costs no tokens; a note it adds costs a few
dozen.

Where the values come from, per tool call without a network call:
  the settings   HANDOFF.md of origin's default branch, or of the local branch of that name when
                 it is ahead (a setting landed on local main, not pushed yet). One git call per
                 tool call compares both tips with the last read; HANDOFF.md is read again only
                 after one moved, so a changed setting counts in a running session too.
  the labels     only where the settings name a label: once per session, from the record that
                 start_issue_chat.py writes for the worktree and issue before the chat starts (a
                 hand-over writes it anew). A chat started some other way has none; the hook
                 then reads the labels once with `gh issue view` and records them for later
                 sessions in that worktree. No answer: the default. A label added after the start
                 counts once start_issue_chat.py writes the record anew (a hand-over, a new
                 start); a record the hook wrote stays until then.
Cost: the hook runs at PreToolUse and PostToolUse, so a tool call pays two git calls.
The records live in ~/.cache/agentic-github-flow/context-limits (AGENTIC_GITHUB_FLOW_LIMIT_RECORDS
replaces it), outside CLAUDE_PLUGIN_DATA, which start_issue_chat.py does not get.

The decision point D is twice the limit, at most 900k (the maintainer, 2026-11-22: "optie 1,
plafond op 900k"): 600k for a 300k chat, 900k for a 600k chat, below the automatic compaction
at about 967k-977k that would otherwise come first (a limit above 900k is its own decision point).

  PostToolUse, context >= L      note to the chat, again per further 25k: finish the step you
                                 are on and hand over, unless you judge you are close to a
                                 solution, then finish it first; at D the user decides.
                                 A subagent (agent_id): wrap up and report back now.
  PreToolUse, context >= D       main thread: refuse every tool but asking the user
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
AGENTIC_GITHUB_FLOW_CONTEXT_STATE replaces that folder (tests), AGENTIC_GITHUB_FLOW_GH (a JSON
list) the `gh` command.
Tests: python3 tests/context_limit.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)  # -I leaves the script's folder off sys.path
from next_issue import row_in  # noqa: E402
from question_label import chat_issue, state_dir  # noqa: E402

DEFAULT_LIMIT = 300_000
CEILING = 900_000      # the decision point: twice the limit, at most this (#82)
RECORDS_ENV = "AGENTIC_GITHUB_FLOW_LIMIT_RECORDS"
# `label `a`: `600k`` or `labels `a`, `b`: `600k``: the labels, then the colon and the count.
LABEL_LIMIT = re.compile(r"labels?\s+((?:`[^`]+`[\s,]*(?:and\s+|or\s+)?)+?)\s*:\s*`?([^`;|]*)`?",
                         re.I)
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


def decision_point(lim: int) -> int:
    """Where the user decides whether a chat works on: twice the limit, at most CEILING, which
    stays below Claude Code's automatic compaction (about 967k-977k with a 1M window, measured
    2026-11-22), so a 600k chat reaches it."""
    return min(2 * lim, max(CEILING, lim))


def tokens(text: str) -> int | None:
    """The first token count in text (`300000`, `300,000`, `300k`, `0.3M`), None below 10,000."""
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k|m)?\b", text.lower())
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    n *= {"k": 1_000, "m": 1_000_000}.get(m.group(2) or "", 1)
    return int(n) if n >= 10_000 else None


def limits_in(cell: str | None) -> tuple[int, dict[str, int]]:
    """The `context limit` cell: the default and the limit per label, from the form
    `` `300k`; label `work: model`: `600k` `` (the default is the count before the first label)."""
    cell = cell or ""
    per = {}
    for m in LABEL_LIMIT.finditer(cell):
        n = tokens(m.group(2))
        if n:
            for name in re.findall(r"`([^`]+)`", m.group(1)):
                per[name.strip().lower()] = n
    first = re.search(r"\blabels?\b", cell, re.I)  # also where a label entry is malformed
    return tokens(cell[:first.start()] if first else cell) or DEFAULT_LIMIT, per


def limit_of(default: int, per: dict[str, int], labels) -> int:
    """The chat's limit: the largest of its issue's labels that have one, else the default."""
    hits = [per[str(name).lower()] for name in labels or () if str(name).lower() in per]
    return max(hits) if hits else default


def git_out(top: str, *args: str) -> str | None:
    """git's output as UTF-8 (HANDOFF.md, also where the locale is cp1252), None on any failure:
    the settings then fall back to the default, never to no limit."""
    try:
        p = subprocess.run(["git", "-C", top, *args], stdin=subprocess.DEVNULL,
                           capture_output=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def settings_refs(top: str) -> list[str]:
    """Pairs of origin's default branch and the local branch of the same name: origin/HEAD's
    target, else main, then master (next_issue.settings_text tries the four in another order,
    which differs only where origin lacks main but has master and local main exists)."""
    head = (git_out(top, "symbolic-ref", "-q", "refs/remotes/origin/HEAD") or "").strip()
    if head.startswith("refs/remotes/origin/"):
        return [head, "refs/heads/" + head[len("refs/remotes/origin/"):]]
    return ["refs/remotes/origin/main", "refs/heads/main", "refs/remotes/origin/master",
            "refs/heads/master"]


def settings_now(top: str, state: dict) -> tuple[int, dict[str, int]]:
    """The settings' limits, read again whenever origin's default branch or its local twin moved:
    one git call per tool call, a read of HANDOFF.md only after a move. The local branch counts
    when it is ahead of origin's (a setting landed on local main, not pushed yet), else origin's."""
    refs = state.get("refs")
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
        refs = state["refs"] = settings_refs(top)
    listed = git_out(top, "for-each-ref", "--format=%(refname) %(objectname)", *refs)
    if listed is None and isinstance(state.get("limits"), list):  # git failed: keep the last read
        default, per = state["limits"]
        return int(default), {str(k): int(v) for k, v in per.items()}
    tips = {}
    for line in (listed or "").splitlines():
        name, _, sha = line.partition(" ")
        if name in refs:
            tips[name] = sha
    key = " ".join(f"{r}={tips.get(r, '')}" for r in refs)
    if key == state.get("settings_key") and isinstance(state.get("limits"), list):
        default, per = state["limits"]
        return int(default), {str(k): int(v) for k, v in per.items()}
    ref = None
    for remote, local in zip(refs[::2], refs[1::2]):
        if remote in tips and local in tips and tips[local] != tips[remote] and \
                git_out(top, "merge-base", "--is-ancestor", remote, local) is not None:
            ref = local
        else:
            ref = remote if remote in tips else local if local in tips else None
        if ref:
            break
    text = git_out(top, "show", f"{ref}:HANDOFF.md") if ref else None
    default, per = limits_in(row_in(text, "context limit"))
    state["settings_key"], state["limits"] = key, [default, per]
    return default, per


def record_path(top: str, issue: int) -> str | None:
    folder = state_dir("context-limits", RECORDS_ENV, plugin_data=False)
    if not folder:
        return None
    where = hashlib.sha256(os.path.realpath(top).encode("utf-8")).hexdigest()[:16]
    return os.path.join(folder, f"{where}-{int(issue)}.json")


def record_labels(top: str, issue: int, labels, source: str) -> None:
    """Note the issue's labels for the chats in this worktree (start_issue_chat.py, or this hook
    once); the hook reads them, so it needs no network per tool call."""
    names = sorted({str(n) for n in labels or () if str(n).strip()})
    save(record_path(top, issue), {"worktree": os.path.realpath(top), "issue": int(issue),
                                   "labels": names, "source": source, "time": now_iso()})


def recorded_labels(top: str, issue: int) -> list[str] | None:
    rec = load(record_path(top, issue))
    if rec.get("worktree") != os.path.realpath(top) or rec.get("issue") != issue or \
            not isinstance(rec.get("labels"), list):
        return None
    return [str(n) for n in rec["labels"]]


def labels_from_github(top: str, issue: int) -> list[str] | None:
    """A chat started without start_issue_chat.py: its issue's labels, read once per session."""
    raw = os.environ.get("AGENTIC_GITHUB_FLOW_GH")
    try:
        command = json.loads(raw) if raw else [shutil.which("gh") or "gh"]
        p = subprocess.run(command + ["issue", "view", str(issue), "--json", "labels"], cwd=top,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
        data = json.loads(p.stdout) if p.returncode == 0 else None
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("labels"), list):
        return None
    return [str(lb.get("name")) for lb in data["labels"] if isinstance(lb, dict) and lb.get("name")]


def chat_limit(top: str, issue: int, state: dict) -> int:
    default, per = settings_now(top, state)
    if per and not isinstance(state.get("labels"), list):  # labels matter: resolved once
        labels = recorded_labels(top, issue)
        if labels is None:
            labels = labels_from_github(top, issue)
            if labels is not None:
                record_labels(top, issue, labels, "hook")
        state["labels"] = labels or []
    return limit_of(default, per, state.get("labels"))


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
    if "issue" not in state or "top" not in state:  # once per session (and for older state)
        found = chat_issue(data.get("cwd") or "")
        state["issue"] = found[2] if found else None
        state["top"] = found[0] if found else None
        save(spath, state)
    issue, top = state.get("issue"), state.get("top")
    if not isinstance(issue, int) or not isinstance(top, str):
        return 0
    before = json.dumps(state, sort_keys=True)
    lim = state["limit"] = chat_limit(top, issue, state)
    if json.dumps(state, sort_keys=True) != before:
        save(spath, state)
    sub = bool(data.get("agent_id"))
    ctx = context_now(transcript, sidechain=sub)
    if ctx is None and sub:
        ctx = context_now(transcript, sidechain=False)
    if ctx is None:
        return 0
    hard = decision_point(lim)

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
            print(f"context limit: this subagent's context is {k(ctx)}, past the point "
                  f"where it must stop ({k(hard)}). Stop and report what you found and did to the chat that started "
                  f"you; no other tool runs.", file=sys.stderr)
            return 2
        print(f"context limit: the chat for issue #{issue} is at {k(ctx)} context, past the "
              f"decision point ({k(hard)}). From here the user decides whether this chat works on. Ask the "
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
                                   f"at the decision point. Follow that answer: to hand over, or to "
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
