#!/usr/bin/env python3
"""May a finished chat be archived? The worktree check of the issue-chats method.

Usage: python3 chat_archivable.py <worktree path> [--no-fetch]

Archiving a chat in the Claude Code desktop app removes the worktree the app made for it, and a
chat whose work is only on this machine must not leave the sidebar, so the answer is "ok" only
when nothing in the worktree can be lost and every commit of it is on GitHub:

  ok        the worktree is gone already; or it is clean (no tracked change, no untracked file,
            no git operation in progress; ignored files are build output) and its HEAD is in a
            remote-tracking branch of origin after a fetch: the default branch
            (`refs/remotes/origin/HEAD`, else origin/main, origin/master) or the branch's own
            `origin/<branch>` (pushed by the ship-change skill)
  keep: ... the reason, one line (changes, untracked files, a git operation in progress, no
            remote origin, commits that are not on GitHub); the chat stays

It fetches origin first (no prune, so a branch GitHub deleted after its merge still counts as
pushed); when the fetch fails it judges on the remote-tracking refs as last fetched, which only
a fetch or a push can write, and says so. --no-fetch skips the fetch. A HEAD that only a squash
merge brought into the default branch counts once its own branch was pushed; a probe branch that
was never pushed keeps its chat. Called by the skills issue-handover and archive-finished-chats
and by archive_guard.py. It changes nothing but origin's remote-tracking refs. Exit 0 for ok,
1 for keep, 2 for usage.
"""
from __future__ import annotations

import os
import subprocess
import sys

OPERATIONS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply",
              "BISECT_LOG")
FETCH_TIMEOUT_S = 30


def git(wt: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", wt, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout, env=env)


def out(wt: str, *args: str) -> str | None:
    p = git(wt, *args)
    return p.stdout.strip() if p.returncode == 0 else None


def verdict(wt: str, fetch: bool = True) -> tuple[int, str]:
    if not os.path.lexists(wt):
        return 0, "ok (worktree gone)"
    gd = out(wt, "rev-parse", "--absolute-git-dir")
    if not gd:
        return 1, f"keep: {wt} is not a git worktree"
    for op in OPERATIONS:
        if os.path.exists(os.path.join(gd, op)):
            return 1, f"keep: a git operation is in progress ({op})"
    st = git(wt, "status", "--porcelain")
    if st.returncode != 0:
        return 1, f"keep: git status failed: {st.stderr.strip()[:200]}"
    lines = [x for x in st.stdout.splitlines() if x.strip()]
    if lines:
        return 1, f"keep: {len(lines)} changed or untracked path(s), e.g. {lines[0][3:]}"
    if "origin" not in (out(wt, "remote") or "").split():
        return 1, "keep: no remote origin, so nothing of this worktree is on GitHub"
    note = ""
    if fetch:
        try:
            f = git(wt, "fetch", "--quiet", "--no-tags", "origin", timeout=FETCH_TIMEOUT_S)
            failed = f.stderr.strip()[:120] if f.returncode else ""
        except subprocess.TimeoutExpired:
            failed = f"timed out after {FETCH_TIMEOUT_S} s"
        if failed:
            note = f"; fetch failed ({failed}): refs as last fetched"
    head = out(wt, "rev-parse", "--verify", "HEAD")
    if not head:
        return 1, "keep: HEAD does not resolve"
    candidates = []
    default = out(wt, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    candidates += [default] if default else []
    candidates += ["refs/remotes/origin/main", "refs/remotes/origin/master"]
    branch = out(wt, "symbolic-ref", "-q", "--short", "HEAD")
    if branch:
        candidates.append(f"refs/remotes/origin/{branch}")
    seen = []
    for ref in candidates:
        if ref in seen or not out(wt, "rev-parse", "-q", "--verify", ref + "^{commit}"):
            continue
        seen.append(ref)
        if git(wt, "merge-base", "--is-ancestor", head, ref).returncode == 0:
            short = ref[len("refs/remotes/"):]
            return 0, f"ok (clean, HEAD {head[:8]} in {short}{note})"
    if not seen:
        return 1, ("keep: no remote-tracking branch to compare with (origin/HEAD, origin/main, "
                   f"origin/master{', origin/' + branch if branch else ''}){note}")
    own = f"refs/remotes/origin/{branch}" if branch else None
    base = own if own in seen else seen[0]
    count = out(wt, "rev-list", "--count", f"{base}..{head}") or "?"
    names = " or ".join(r[len("refs/remotes/"):] for r in seen)
    return 1, (f"keep: {count} commit(s) of {branch or 'the detached HEAD'} are not on GitHub "
               f"(not in {names}){note}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--no-fetch"]
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: chat_archivable.py <worktree path> [--no-fetch]", file=sys.stderr)
        return 2
    try:
        code, line = verdict(args[0], fetch="--no-fetch" not in argv)
    except (OSError, subprocess.SubprocessError) as e:
        code, line = 1, f"keep: the check did not run ({e})"
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
