#!/usr/bin/env python3
"""PreToolUse guard for mcp__ccd_session_mgmt__archive_session (skills archive-finished-chats
and issue-handover; the method: skills/issue-handover/method.md of this plugin; wired by the
plugin's hooks/hooks.json, so it runs wherever the plugin is enabled in Claude Code).

Archiving a chat in the desktop app removes its worktree, so the chat may go only when
chat_archivable.py (beside this file) calls that worktree "ok": clean, and every commit on
GitHub. It works for any repository: it reads nothing of the repository but the worktree path
the app reports. It only ever denies; a pass leaves the call to the permission rules, so the
app still asks unless the user added an allow rule for archive_session.

The hook gets the target's session id, not its worktree, and nothing outside the app maps one to
the other. The app's own answer does: the skill calls get_session for the target, and its result
(sessionId, worktreePath) is in this session's transcript. The guard reads the newest such
result, written by the app as a tool result, never text the agent wrote, and then:

  no get_session result for that session      -> deny: call get_session first
  a result without worktreePath               -> pass: the chat ran in the primary checkout and
                                                 archiving removes no worktree
  worktreePath, chat_archivable.py says "ok"  -> pass (the permission rules decide)
  anything else, or the guard itself fails    -> deny, with the script's reason

"self" (an issue chat archiving itself at the end of issue-handover) is checked the same way, on
the calling chat's own worktree, taken from the newest get_session "self" result that:
  - the chat's main thread received (a transcript record with isSidechain false): a subagent's
    get_session "self" answers for the whole chat, and a subagent never archives its chat;
  - this Claude Code session received (the record's sessionId equals the hook's session_id):
    a forked or copied transcript carries another session's answer;
  - answered a tool_use whose input was exactly session_id "self".
The hook input's cwd is not used: a chat may cd into a task worktree, so cwd does not name the
worktree archiving removes. A call from inside a subagent (hook input with agent_id, or a
transcript_path under subagents/) is denied for "self".

Deny is exit 2 with the reason on stderr; pass is exit 0 without output, which leaves the call
to the permission rules. hooks.json runs this with `|| exit 2`, and run-guard.sh denies when it
finds no Python, so a crash denies too.
Tests: python3 tests/archive_guard.py
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

TOOL = "mcp__ccd_session_mgmt__archive_session"
GET = "mcp__ccd_session_mgmt__get_session"
CHECK = os.path.join(os.path.dirname(os.path.realpath(__file__)), "chat_archivable.py")


def deny(reason: str) -> int:
    print(f"archive guard: {reason}", file=sys.stderr)
    return 2


def transcripts(path: str) -> list[str]:
    """The session's transcript and its subagents' (a subagent may have made the lookup)."""
    files = [path]
    stem = path[:-len(".jsonl")] if path.endswith(".jsonl") else path
    files += sorted(glob.glob(os.path.join(stem, "subagents", "*.jsonl")))
    parts = path.split(os.sep)
    if "subagents" in parts:  # the hook runs in a subagent: add the main transcript and siblings
        i = len(parts) - 1 - parts[::-1].index("subagents")
        main_stem = os.sep.join(parts[:i])
        files.append(main_stem + ".jsonl")
        files += sorted(glob.glob(os.path.join(main_stem, "subagents", "*.jsonl")))
    seen, out = set(), []
    for f in files:
        if f not in seen and os.path.isfile(f):
            seen.add(f)
            out.append(f)
    return out


def lookups(path: str, target: str, session: str | None = None) -> list[tuple[str, dict]]:
    """Every get_session result about `target` in one transcript, as (timestamp, result).

    target "self": only calls made with session_id "self", by the main thread (not a sidechain)
    of the Claude Code session `session`; the result's own sessionId is the app's id."""
    own = target == "self"
    uses: set[str] = set()
    found = []
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return found
    with fh:
        for line in fh:
            if GET not in line and "tool_result" not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            if own and (rec.get("isSidechain") is not False or rec.get("sessionId") != session):
                continue
            msg = rec.get("message")
            content = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and block.get("name") == GET:
                    inp = block.get("input")
                    asked = inp.get("session_id") if isinstance(inp, dict) else None
                    if not own or (asked == "self" and rec.get("type") == "assistant"):
                        uses.add(block.get("id"))
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in uses:
                    if block.get("is_error"):
                        continue
                    body = block.get("content")
                    if isinstance(body, list):
                        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
                    try:
                        data = json.loads(body)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(data, dict) or not isinstance(data.get("sessionId"), str):
                        continue
                    if own and rec.get("type") != "user":
                        continue
                    if own or data.get("sessionId") == target:
                        found.append((str(rec.get("timestamp", "")), data))
    return found


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return deny("unreadable hook input")
    if not isinstance(event, dict):
        return deny("hook input is not an object")
    if event.get("tool_name") != TOOL:
        return 0
    tool_input = event.get("tool_input")
    target = tool_input.get("session_id") if isinstance(tool_input, dict) else None
    if not isinstance(target, str) or not target:
        return deny("no session_id in the archive call")
    tpath = event.get("transcript_path")
    if not isinstance(tpath, str) or not tpath:
        return deny("no transcript_path in the hook input")
    if target == "self":
        return archive_self(event, tpath)
    results = [r for f in transcripts(tpath) for r in lookups(f, target)]
    if not results:
        return deny(f"no get_session result for {target} in this session: call get_session "
                    f"{target} first (skill archive-finished-chats, step 3)")
    return check_worktree(max(results, key=lambda r: r[0])[1])


def archive_self(event: dict, tpath: str) -> int:
    """The calling chat archives itself: check its own worktree (see the module docstring)."""
    if event.get("agent_id") or "subagents" in tpath.split(os.sep):
        return deny('a subagent cannot archive its chat: archive "self" from the chat itself '
                    "(skill issue-handover, step 7)")
    session = event.get("session_id")
    if not isinstance(session, str) or not session:
        return deny("no session_id in the hook input")
    results = lookups(tpath, "self", session=session)
    if not results:
        return deny('no get_session "self" result in this chat: call get_session "self" first '
                    "(skill issue-handover, step 7)")
    return check_worktree(max(results, key=lambda r: r[0])[1])


def check_worktree(data: dict) -> int:
    """Pass when the session has no worktree of its own or chat_archivable.py calls it ok."""
    worktree = data.get("worktreePath")
    if not worktree:
        return 0
    if not isinstance(worktree, str):
        return deny("get_session gave a worktreePath that is not a path")
    try:
        r = subprocess.run([sys.executable, CHECK, worktree], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=50)
    except (OSError, subprocess.TimeoutExpired) as e:
        return deny(f"chat_archivable.py did not run: {e}")
    verdict = (r.stdout.strip().splitlines() or [""])[0]
    if r.returncode == 0 and verdict.startswith("ok"):
        return 0
    return deny(f"{worktree}: {verdict or r.stderr.strip() or 'no verdict'}")


if __name__ == "__main__":
    sys.exit(main())
