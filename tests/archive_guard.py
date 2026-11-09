#!/usr/bin/env python3
"""Runs plugins/issue-chats/scripts/archive_guard.py on sample hook inputs and transcripts;
exit 1 on a mismatch.

    python3 tests/archive_guard.py

Builds a scratch git repository with a local bare origin, a clean worktree (HEAD in origin's
main), a dirty one and one with a commit that was never pushed, writes transcripts in Claude
Code's record shape (type, isSidechain, sessionId, message.content blocks) and checks the guard's
exit code per case: 0 pass, 2 deny. Every deny case is a way a chat could lose work, leave the
sidebar with work only on this machine, or archive the wrong chat if the guard let it through.
It also checks that the plugin's hooks.json wires the guard on archive_session, failing closed.
Offline.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

PLUGIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins",
                      "issue-chats")
HOOK = os.path.join(PLUGIN, "scripts", "archive_guard.py")
TOOL = "mcp__ccd_session_mgmt__archive_session"
GET = "mcp__ccd_session_mgmt__get_session"
SID = "11111111-2222-3333-4444-555555555555"  # this Claude Code session (hook input session_id)
APP = "local_aaaaaaaa-0000-0000-0000-000000000001"  # this chat's id in the app
OTHER = "local_bbbbbbbb-0000-0000-0000-000000000002"


ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")


def git(*args: str, cwd: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", *args], cwd=cwd,
                   check=True, capture_output=True, env=ENV)


def repo(tmp: str) -> tuple[str, str, str, str]:
    """A repository whose main is on origin, a clean worktree on main's HEAD, a dirty one, one
    with a commit that was never pushed, and a path that is gone."""
    main = os.path.join(tmp, "repo")
    origin = os.path.join(tmp, "origin.git")
    os.makedirs(main)
    git("init", "-q", "--bare", "-b", "main", origin, cwd=tmp)
    git("init", "-q", "-b", "main", cwd=main)
    git("remote", "add", "origin", origin, cwd=main)
    with open(os.path.join(main, "f"), "w") as fh:
        fh.write("x\n")
    git("add", "f", cwd=main)
    git("commit", "-q", "-m", "c", cwd=main)
    git("push", "-q", "origin", "main", cwd=main)
    git("fetch", "-q", "origin", cwd=main)
    git("remote", "set-head", "origin", "main", cwd=main)
    clean, dirty = os.path.join(tmp, "wt-clean"), os.path.join(tmp, "wt-dirty")
    git("worktree", "add", "-q", "-b", "agent/clean", clean, cwd=main)
    git("worktree", "add", "-q", "-b", "agent/dirty", dirty, cwd=main)
    with open(os.path.join(dirty, "unsaved.txt"), "w") as fh:
        fh.write("work\n")
    ahead = os.path.join(tmp, "wt-ahead")
    git("worktree", "add", "-q", "-b", "agent/ahead", ahead, cwd=main)
    git("commit", "-q", "--allow-empty", "-m", "not pushed", cwd=ahead)
    return clean, dirty, os.path.join(tmp, "wt-gone"), ahead


def use(uid: str, target: str, ts: str, side: bool = False, sess: str = SID) -> dict:
    return {"type": "assistant", "isSidechain": side, "sessionId": sess, "timestamp": ts,
            "message": {"content": [{"type": "tool_use", "id": uid, "name": GET,
                                     "input": {"session_id": target}}]}}


def res(uid: str, data, ts: str, side: bool = False, sess: str = SID, err: bool = False,
        rtype: str = "user") -> dict:
    body = data if isinstance(data, str) else json.dumps(data)
    return {"type": rtype, "isSidechain": side, "sessionId": sess, "timestamp": ts,
            "message": {"content": [{"type": "tool_result", "tool_use_id": uid, "is_error": err,
                                     "content": [{"type": "text", "text": body}]}]}}


def bash(uid: str, text: str, ts: str) -> list[dict]:
    """A Bash call whose output an agent controls, printing JSON that looks like get_session."""
    return [{"type": "assistant", "isSidechain": False, "sessionId": SID, "timestamp": ts,
             "message": {"content": [{"type": "tool_use", "id": uid, "name": "Bash",
                                      "input": {"command": "cat fake.json"}}]}},
            res(uid, text, ts)]


def run(tmp: str, name: str, records: list[dict], target, extra: dict | None = None,
        raw: str | None = None, sub: bool = False) -> int:
    d = os.path.join(tmp, name.replace(" ", "_").replace("/", "_"))
    os.makedirs(os.path.join(d, SID, "subagents"))
    tpath = os.path.join(d, SID, "subagents", "agent-x.jsonl") if sub else os.path.join(d, SID + ".jsonl")
    with open(tpath, "w") as fh:
        fh.writelines(json.dumps(r) + "\n" for r in records)
    event = {"session_id": SID, "transcript_path": tpath, "cwd": tmp, "tool_name": TOOL,
             "hook_event_name": "PreToolUse", "tool_input": {"session_id": target, "reason": "t"}}
    event.update(extra or {})
    stdin = raw if raw is not None else json.dumps(event)
    return subprocess.run([sys.executable, HOOK], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", env=ENV).returncode


def wiring() -> list[str]:
    """The plugin's hooks.json runs this guard before archive_session and denies on a crash."""
    with open(os.path.join(PLUGIN, "hooks", "hooks.json"), encoding="utf-8") as fh:
        entries = json.load(fh)["hooks"]["PreToolUse"]
    problems = []
    found = [e for e in entries if re.fullmatch(e.get("matcher", ""), TOOL)]
    if not found:
        problems.append("hooks.json: no PreToolUse entry matches " + TOOL)
    for entry in found:
        for hook in entry.get("hooks", []):
            command = hook.get("command", "")
            if "archive_guard.py" not in command or not command.rstrip().endswith("|| exit 2"):
                problems.append("hooks.json: the guard must run archive_guard.py and end in "
                                "`|| exit 2`: " + command)
    with open(os.path.join(PLUGIN, "scripts", "run-guard.sh"), encoding="utf-8") as fh:
        if not fh.read().rstrip().endswith("exit 2"):
            problems.append("run-guard.sh: without Python it must deny (exit 2)")
    return problems


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        clean, dirty, gone, ahead = repo(tmp)
        me = lambda wt=None: {"sessionId": APP, **({"worktreePath": wt} if wt else {})}  # noqa: E731
        other = lambda wt=None: {"sessionId": OTHER, **({"worktreePath": wt} if wt else {})}  # noqa: E731
        T1, T2 = "2026-10-24T10:00:00.000Z", "2026-10-24T11:00:00.000Z"
        cases = [
            # (name, records, target, extra, raw, sub, expected)
            ("garbage: not json", [], "self", None, "not json", False, 2),
            ("garbage: a list", [], "self", None, "[]", False, 2),
            ("garbage: tool_input not an object", [], "self", {"tool_input": "self"}, None, False, 2),
            ("garbage: no session_id", [], "", None, None, False, 2),
            ("garbage: no transcript_path", [], OTHER, {"transcript_path": None}, None, False, 2),
            ("another tool passes", [], "self", {"tool_name": "Bash"}, None, False, 0),
            ("other ok: clean, on GitHub", [use("a", OTHER, T1), res("a", other(clean), T1)], OTHER, None, None, False, 0),
            ("other ok: primary checkout", [use("a", OTHER, T1), res("a", other(), T1)], OTHER, None, None, False, 0),
            ("other ok: lookup by a subagent", [use("a", OTHER, T1, side=True), res("a", other(clean), T1, side=True)], OTHER, None, None, False, 0),
            ("other not-ok: dirty", [use("a", OTHER, T1), res("a", other(dirty), T1)], OTHER, None, None, False, 2),
            ("other not-ok: no lookup", [], OTHER, None, None, False, 2),
            ("other spoof: Bash output", bash("b", json.dumps(other()), T1), OTHER, None, None, False, 2),
            ("self ok: clean, on GitHub", [use("a", "self", T1), res("a", me(clean), T1)], "self", None, None, False, 0),
            ("self ok: primary checkout", [use("a", "self", T1), res("a", me(), T1)], "self", None, None, False, 0),
            ("self ok: worktree gone", [use("a", "self", T1), res("a", me(gone), T1)], "self", None, None, False, 0),
            ("self ok: newest result counts", [use("a", "self", T1), res("a", me(dirty), T1), use("b", "self", T2), res("b", me(clean), T2)], "self", None, None, False, 0),
            ("self not-ok: dirty", [use("a", "self", T1), res("a", me(dirty), T1)], "self", None, None, False, 2),
            ("self not-ok: a commit not on GitHub", [use("a", "self", T1), res("a", me(ahead), T1)], "self", None, None, False, 2),
            ("self not-ok: newest result dirty", [use("a", "self", T1), res("a", me(clean), T1), use("b", "self", T2), res("b", me(dirty), T2)], "self", None, None, False, 2),
            ("self not-ok: no lookup", [], "self", None, None, False, 2),
            ("self not-ok: error result", [use("a", "self", T1), res("a", me(clean), T1, err=True)], "self", None, None, False, 2),
            ("self not-ok: worktreePath not a string", [use("a", "self", T1), res("a", {"sessionId": APP, "worktreePath": 7}, T1)], "self", None, None, False, 2),
            ("self spoof: lookup of another session", [use("a", OTHER, T1), res("a", other(), T1)], "self", None, None, False, 2),
            ("self spoof: lookup by a subagent", [use("a", "self", T1, side=True), res("a", me(), T1, side=True)], "self", None, None, False, 2),
            ("self spoof: forked transcript", [use("a", "self", T1, sess="old"), res("a", me(), T1, sess="old")], "self", None, None, False, 2),
            ("self spoof: Bash output", bash("b", json.dumps(me()), T1), "self", None, None, False, 2),
            ("self spoof: api-request-blob copy", [use("a", "self", T1), res("a", me(), T1, rtype="api-request-blob")], "self", None, None, False, 2),
            ("self from a subagent: agent_id", [use("a", "self", T1), res("a", me(clean), T1)], "self", {"agent_id": "x"}, None, False, 2),
            ("self from a subagent: transcript", [use("a", "self", T1), res("a", me(clean), T1)], "self", None, None, True, 2),
        ]
        bad = 0
        for name, recs, target, extra, raw, sub, want in cases:
            got = run(tmp, name, recs, target, extra, raw, sub)
            ok = got == want
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} exit {got} (want {want})  {name}")
        for problem in wiring():
            bad += 1
            print("FAIL " + problem)
        print(f"{len(cases) - bad}/{len(cases)} cases as expected; hooks.json wiring checked")
        return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
