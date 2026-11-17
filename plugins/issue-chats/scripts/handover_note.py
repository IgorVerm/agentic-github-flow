"""The hand-over note: a chat that handed its unfinished issue over in place (#80).

start_issue_chat.py --handover writes it once the successor is open in the app, beside the chat
it hands over for, in the same worktree; archive_guard.py reads it. With it the guard lets that
old chat be archived although its commits are not on GitHub: the successor works on in the
worktree, and archiving a chat whose worktree the app did not make (no `worktreePath`, a worktree
of `new_worktree.py`) leaves that folder in place (measured 2026-11-17, #80). An archived chat
takes no message, so it cannot wake and work beside its successor.

One file per old session id (the CLI id and, when it differs, the app's `local_` id without the
prefix) in ~/.cache/agentic-github-flow/handovers, or AGENTIC_GITHUB_FLOW_HANDOVER_STATE (tests):
a fixed folder, because the script runs without CLAUDE_PLUGIN_DATA and the hook with it. The
folder is the user's own (0700, not a symlink, owned by the user); files open without following
symlinks.
"""
from __future__ import annotations

import json
import os
import re
import stat
import time


def folder() -> str | None:
    path = os.environ.get("AGENTIC_GITHUB_FLOW_HANDOVER_STATE") or os.path.join(
        os.path.expanduser("~"), ".cache", "agentic-github-flow", "handovers")
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


def plain(session: str) -> str:
    s = session[len("local_"):] if session.startswith("local_") else session
    return re.sub(r"[^A-Za-z0-9_.-]", "_", s)


def write(old_ids, worktree: str, successor: str, issue: int | None) -> list[str]:
    """Note that each of old_ids handed over to successor in worktree; the files written."""
    base = folder()
    if not base:
        return []
    note = {"worktree": os.path.realpath(worktree), "successor": successor, "issue": issue,
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    written = []
    for sid in {plain(s) for s in old_ids if s and len(plain(s)) >= 8}:
        path = os.path.join(base, sid + ".json")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
                         0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(note, f)
            written.append(path)
        except OSError:
            pass
    return written


def handed_over(session: str, worktree: str) -> dict | None:
    """The note for session (CLI or app id) whose worktree is worktree, else None."""
    base = folder()
    if not base or not session:
        return None
    path = os.path.join(base, plain(session) + ".json")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, encoding="utf-8") as f:
            note = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(note, dict) or note.get("worktree") != os.path.realpath(worktree):
        return None
    return note
