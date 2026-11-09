#!/usr/bin/env python3
"""Start an issue chat in the background and open it in the Claude Code desktop app.

Usage: python3 start_issue_chat.py <worktree> <chat title> --model <model> [--effort <level>]
                                   [--prefix <repository prefix>] [--handover]

The route of skill issue-handover, *Start the next chat* (why and what was measured: the
method's *The next chat starts in the background*), as one tool so that a single narrow allow
rule covers it instead of allow rules on `claude --bg *`, which would also admit
`--dangerously-skip-permissions`, `--settings` or any prompt. It refuses before starting
anything unless: the platform is macOS or Linux (it needs `script`); the terminal CLI is logged
in; <worktree> is a clean linked git worktree (never a primary checkout) in which no active
session works (so never the starting chat's own worktree, where the app later refuses the
brief); no other active session carries <chat title>; title, model and effort are plain values;
the title has the fixed form that names the chat's GitHub issue: `<prefix>#<issue> · <topic>`,
`<prefix>Requirements · #<issue> · <topic>` or `<prefix>Requirements · new · <topic>` (the
prefix is the repository's optional setting, empty by default, e.g. `--prefix "Web · "`); and
that issue, read with `gh issue view` in <worktree>, is open and has no assignee (the claim:
another chat already works on it), unless --handover says the claim is the calling chat's own
and it hands the issue over before its branch is ready (context limit, two failed corrections):
then the issue's newest claim comment (signed, opening with `claimed for chat`) must name the
calling chat, by its session id (`CLAUDE_CODE_SESSION_ID`, or `CLAUDE_CODE_HOST_SESSION_ID` as
`local_<id>`) or by the full path of the worktree its working directory is in, so the flag
cannot take over another chat's claim. Then it runs
`claude --bg --name <title> --model <model> --effort <level> <ready prompt>` in <worktree>,
waits up to 120 s until `claude agents --json --cwd <worktree>` lists that one session idle,
runs `claude stop <short id>`, and opens it with `claude --desktop --resume <sessionId>` under
`script` (the desktop switch refuses without a terminal; `script -q /dev/null` on macOS, the
measured form; `script -q -c` on Linux, not measured). It claims nothing: the caller assigns
the issue right after exit 0. --effort left out: this chat's own effort (`CLAUDE_EFFORT`), else
the user's default. AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command (tests).

Last line and exit code, for the caller:
  0  `ok local_<sessionId>`: open in the app; hand it the brief with `send_message` to that id.
  1  `fail: ...`: nothing runs and nothing was opened in the app (a background session that
     started was stopped; its conversation stays on disk). Never `claude rm`, which deletes a
     session's worktree.
  2  `unsure: ...`: it may be open in the app or still running, with `local_<sessionId>` or the
     short id when known; the caller checks `list_sessions` and `claude agents --json --cwd
     <worktree>` before anything else. Any failure after `claude --bg` ran ends here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

READY = "Reply with exactly one line: ready. Use no tools."
EFFORTS = ("low", "medium", "high", "xhigh", "max")
WAIT_IDLE_S = 120
TITLE = r"(?:Requirements · )?#([1-9][0-9]*) · \S.*|Requirements · new · \S.*"
# A claim comment: the signature, then the opening the skill issue-handover gives it (the same
# marker next_issue.py reads), optionally in bold.
CLAIM = re.compile(r"\A\s*\N{ROBOT FACE}[^\n]*?\):\s*(?:\*\*)?claimed for chat\b", re.I)


def title_issue(title: str, prefix: str) -> tuple[bool, int | None]:
    """Whether the title has the fixed form after the repository's prefix, and its issue."""
    m = re.fullmatch(re.escape(prefix) + "(?:" + TITLE + ")", title)
    if not m:
        return False, None
    return True, int(m.group(1)) if m.group(1) else None


class Fail(Exception):
    pass


def run(cmd: list[str], cwd: str | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout)


def git(wt: str, *args: str) -> str:
    p = run(["git", "-C", wt, *args])
    if p.returncode != 0:
        raise Fail(f"git {' '.join(args)} in {wt}: {p.stderr.strip()}")
    return p.stdout.strip()


def gh_command() -> list[str] | None:
    raw = os.environ.get("AGENTIC_GITHUB_FLOW_GH")
    if raw:
        try:
            command = json.loads(raw)
        except ValueError:
            return None
        return command if isinstance(command, list) and command else None
    found = shutil.which("gh")
    return [found] if found else None


def agents(cwd: str | None = None) -> list[dict]:
    cmd = ["claude", "agents", "--json"] + (["--cwd", cwd] if cwd else [])
    p = run(cmd)
    if p.returncode != 0:
        raise Fail(f"claude agents --json: {p.stderr.strip() or p.returncode}")
    try:
        rows = json.loads(p.stdout)
    except ValueError:
        raise Fail("claude agents --json printed no JSON")
    if not isinstance(rows, list):
        raise Fail("claude agents --json printed no list")
    return rows


def real(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def preflight(wt: str, title: str, model: str, effort: str | None, prefix: str = "",
              handover: bool = False) -> None:
    if sys.platform not in ("darwin", "linux"):
        raise Fail(f"no form of `script` known for {sys.platform}: give the user the brief")
    if not shutil.which("script"):
        raise Fail("the `script` command is not on PATH")
    if not shutil.which("claude"):
        raise Fail("the claude CLI is not on PATH")
    if not title.strip() or title.startswith("-") or "\n" in title or len(title) > 200:
        raise Fail("the chat title must be one plain line")
    if "#" in prefix or "\n" in prefix or len(prefix) > 60:
        raise Fail(f"not a plain repository prefix: {prefix!r}")
    form_ok, issue = title_issue(title, prefix)
    if not form_ok:
        raise Fail(f"the chat title {title!r} lacks the form {prefix}#<issue> · <topic> "
                   "(the method's title form; a repository prefix goes in --prefix)")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\[\]-]*", model):
        raise Fail(f"not a plain model id: {model!r}")
    if effort is not None and effort not in EFFORTS:
        raise Fail(f"effort must be one of {', '.join(EFFORTS)}")
    p = run(["claude", "auth", "status"])
    try:
        logged_in = json.loads(p.stdout).get("loggedIn") is True
    except (ValueError, AttributeError):
        logged_in = False
    if not logged_in:
        raise Fail("the claude CLI is not logged in (claude auth login)")
    if not os.path.isdir(wt):
        raise Fail(f"no such directory: {wt}")
    if real(git(wt, "rev-parse", "--show-toplevel")) != wt:
        raise Fail(f"{wt} is not the top of a git worktree")
    gd = real(os.path.join(wt, git(wt, "rev-parse", "--git-dir")))
    common = real(os.path.join(wt, git(wt, "rev-parse", "--git-common-dir")))
    if gd == common:
        raise Fail(f"{wt} is a primary checkout, not a linked worktree")
    if git(wt, "status", "--porcelain"):
        raise Fail(f"{wt} has changes: the next chat needs a fresh worktree")
    if issue is not None:
        unclaimed(wt, issue, handover)
    me = os.environ.get("CLAUDE_CODE_SESSION_ID")
    for row in agents():
        cwd = real(str(row.get("cwd") or "/nonexistent"))
        if cwd == wt or cwd.startswith(wt + os.sep):
            raise Fail(f"session {row.get('sessionId')} already works in {wt}")
        if row.get("name") == title and row.get("sessionId") != me:
            raise Fail(f"session {row.get('sessionId')} already carries the title {title!r}")


def unclaimed(wt: str, issue: int, handover: bool = False) -> None:
    """The issue is open and nobody claimed it (no assignee), read in the worktree's repository;
    with handover, the caller's own claim may stand."""
    command = gh_command()
    if not command:
        raise Fail("gh is not on PATH: the claim on the issue cannot be checked")
    fields = "state,assignees,comments" if handover else "state,assignees"
    p = run(command + ["issue", "view", str(issue), "--json", fields], cwd=wt)
    try:
        data = json.loads(p.stdout) if p.returncode == 0 else None
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise Fail(f"gh issue view {issue}: {(p.stderr or p.stdout).strip()[:200] or 'no answer'}")
    if data.get("state") != "OPEN":
        raise Fail(f"issue #{issue} is {str(data.get('state')).lower()}, not open")
    if not data.get("assignees"):
        return
    if handover:
        own_claim(issue, data.get("comments"))
        return
    who = ", ".join(str(a.get("login")) for a in data["assignees"] if isinstance(a, dict))
    raise Fail(f"issue #{issue} is already claimed (assigned to {who}): another chat works on it")


def own_claim(issue: int, comments) -> None:
    """--handover: the newest signed claim comment names this chat, by its session id or by
    the full path of the worktree it works in (never a folder name alone, which another
    repository's worktree may share)."""
    claims = [str(c.get("body") or "") for c in comments or [] if isinstance(c, dict)]
    claims = [b for b in claims if CLAIM.match(b)]
    if not claims:
        raise Fail(f"issue #{issue} is assigned but has no signed claim comment: --handover "
                   "hands over only this chat's own claim")
    newest = claims[-1]
    names = set()
    for var in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_HOST_SESSION_ID"):
        v = os.environ.get(var, "").strip()
        v = v[len("local_"):] if v.startswith("local_") else v
        if len(v) >= 8:
            names.add("(?:local_)?" + re.escape(v))
    p = run(["git", "rev-parse", "--show-toplevel"])
    if p.returncode == 0 and p.stdout.strip():
        top = p.stdout.strip()
        names.update({re.escape(top), re.escape(real(top))})
    if any(re.search(r"(?<![\w./-])" + n + r"(?![\w.-]|/[\w.-])", newest) for n in names):
        return
    raise Fail(f"the newest claim on issue #{issue} names another chat, not this one (session "
               "id or worktree): --handover hands over only this chat's own claim")


def start(wt: str, title: str, model: str, effort: str | None) -> tuple[int, str]:
    cmd = ["claude", "--bg", "--name", title, "--model", model]
    if effort:
        cmd += ["--effort", effort]
    p = run(cmd + [READY], cwd=wt)
    # From here on a session may run: any failure is `unsure`, never `nothing started`.
    m = re.search(r"backgrounded\s*·\s*(\S+)", p.stdout + p.stderr)
    if p.returncode != 0 or not m:
        try:
            running = agents(wt)
        except (Fail, subprocess.TimeoutExpired) as e:
            return 2, (f"unsure: claude --bg gave no short id ({(p.stderr or p.stdout).strip()[:200]})"
                       f" and the sessions in {wt} could not be listed: {e}")
        if running:
            return 2, f"unsure: claude --bg gave no short id but a session runs in {wt}"
        return 1, f"fail: claude --bg: {(p.stderr or p.stdout).strip()[:300]}"
    short = m.group(1)
    try:
        return after_start(wt, title, short)
    except (Fail, subprocess.TimeoutExpired) as e:
        try:
            s = run(["claude", "stop", short])
            state = "stopped" if s.returncode == 0 else "maybe still running"
        except (OSError, subprocess.TimeoutExpired):
            state = "maybe still running"
        return 2, f"unsure: {e}; background session {short} {state}; check list_sessions"


def after_start(wt: str, title: str, short: str) -> tuple[int, str]:
    def stop_and(code: int, msg: str) -> tuple[int, str]:
        s = run(["claude", "stop", short])
        if s.returncode != 0:
            return 2, f"unsure: {msg}; claude stop {short} failed too"
        return code, f"fail: {msg}; background session {short} stopped, not opened in the app"

    sid = None
    deadline = time.monotonic() + WAIT_IDLE_S
    while time.monotonic() < deadline:
        rows = agents(wt)
        if len(rows) > 1:
            return stop_and(1, f"{len(rows)} sessions run in {wt}")
        if rows and rows[0].get("name") == title and rows[0].get("status") == "idle":
            sid = str(rows[0].get("sessionId") or "")
            break
        time.sleep(2)
    if not sid or not re.fullmatch(r"[0-9a-f-]{36}", sid):
        return stop_and(1, f"the session did not turn idle within {WAIT_IDLE_S} s")
    s = run(["claude", "stop", short])
    if s.returncode != 0:
        return 2, f"unsure: claude stop {short}: {s.stderr.strip()}; local_{sid}"

    resume = ["claude", "--desktop", "--resume", sid]
    if sys.platform == "darwin":
        cmd = ["script", "-q", "/dev/null", *resume]
    else:
        cmd = ["script", "-q", "-c", shlex.join(resume), "/dev/null"]
    d = run(cmd, cwd=wt)
    if d.returncode != 0 or "Opening session" not in d.stdout + d.stderr:
        return 2, (f"unsure: the open in the app answered "
                   f"{(d.stdout + d.stderr).strip()[:200]!r}; local_{sid}")
    return 0, f"ok local_{sid}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("worktree")
    ap.add_argument("title")
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--handover", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            return 0
        print("fail: bad arguments; nothing started")
        return 1
    effort = a.effort or (os.environ.get("CLAUDE_EFFORT") or None)
    if effort is not None and effort not in EFFORTS and not a.effort:
        effort = None
    wt = real(a.worktree)
    try:
        preflight(wt, a.title, a.model, effort, a.prefix, a.handover)
        code, line = start(wt, a.title, a.model, effort)
    except Fail as e:
        code, line = 1, f"fail: {e}; nothing started"
    except subprocess.TimeoutExpired as e:
        code, line = 2, (f"unsure: {' '.join(map(str, e.cmd[:3]))} timed out; check "
                         f"claude agents --json --cwd {wt}")
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
