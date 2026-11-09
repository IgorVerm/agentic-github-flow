#!/usr/bin/env python3
"""May a finished chat be archived? The worktree check of the issue-chats method.

Usage: python3 chat_archivable.py <worktree path> [--landed] [--no-fetch]

Archiving a chat in the Claude Code desktop app removes the worktree the app made for it, and a
chat whose work is only on this machine must not leave the sidebar, so the answer is "ok" only
when nothing in the worktree can be lost and every commit of it is on GitHub, or, in local-main
mode, on the local landing branch:

  ok        the worktree is gone already; or it is the top of its own git worktree and clean (no
            tracked change, no untracked file in any directory whatever status.showUntrackedFiles
            says, no change in a submodule, no file hidden from status by assume-unchanged or,
            outside a sparse checkout, skip-worktree, no git operation in progress; ignored
            files are build output), and its HEAD is in a remote-tracking branch of origin
            after a fetch: the default branch (`refs/remotes/origin/HEAD`, else origin/main,
            origin/master), the landing branch HANDOFF.md names, or the branch's own
            `origin/<branch>` (pushed by ship-change)
  ok        in local-main mode (landing.py beside this file, asked only then): clean as above,
            and its HEAD is in the local landing branch, where the landing put it
  ok        a chat that handed its issue over (#14): clean as above, and its HEAD in another
            branch of origin (a successor's pushed branch, which started from this chat's head)
            that GitHub still has with HEAD in it (`git ls-remote`: the fetch does not prune, so
            a tracking ref alone may name a branch deleted unmerged). A successor's branch only
            on this machine does not count
  every ok but "worktree gone" also needs the reflog proof of a linked worktree: no commit that
            only its own history holds (its HEAD reflog, ORIG_HEAD, its branch's reflog with the
            branch counted as deleted, per-worktree refs: stranded_commits of work_proof.py
            beside this file), which archiving would make unreachable. Such a commit counts as
            kept when any ref that survives the archive reaches it: a branch of origin, or a
            local branch or tag (a `scratch/<issue>-<what>` branch for a probe), the same proof
            cleanup-merged uses before it removes a worktree
  keep: ... the reason, one line (not a worktree of its own, for example a folder whose .git
            link is missing inside another checkout; changes, untracked or hidden files, a git
            operation in progress, no remote origin, commits that are not on GitHub); the chat
            stays

--landed (a side chat, #18: started by another chat with start_session and not detached) asks
more: the work has landed, not only been pushed. Ok only when clean and HEAD is in origin's
default or landing branch, or on the local landing branch in local-main mode, or is exactly the
head of a pull request of origin merged into the landing branch (a squash or rebase merge; read
with gh). The branch's own origin/<branch> and a successor's branch do not count, so a side
chat whose pull request is open stays where a follow-up can reach it.

It fetches origin first (no prune, so a branch GitHub deleted after its merge still counts as
pushed); when the fetch fails it judges on the remote-tracking refs as last fetched, which only
a fetch or a push can write, and says so. --no-fetch skips the fetch. A HEAD that only a squash
merge brought into the default branch counts once its own branch was pushed; a probe branch that
was never pushed keeps its chat. Called by the skills issue-handover and archive-finished-chats
and by archive_guard.py. It changes nothing but origin's remote-tracking refs. Exit 0 for ok,
1 for keep, 2 for usage. AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import landing  # noqa: E402  (beside this file: the landing mode and branch)
import work_proof  # noqa: E402  (beside this file: the reflog proof, merged pull requests)

OPERATIONS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply",
              "BISECT_LOG")
FETCH_TIMEOUT_S = 25  # archive_guard.py waits at most 40 s for the whole check
GH_TIMEOUT_S = 6  # per GitHub call of the landing-mode check, which runs only for local landings
LS_REMOTE_TIMEOUT_S = 6  # per successor branch asked of GitHub


def git(wt: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", wt, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=timeout, env=env)


def out(wt: str, *args: str) -> str | None:
    p = git(wt, *args)
    return p.stdout.strip() if p.returncode == 0 else None


def hidden_paths(wt: str) -> list[str] | None:
    """Tracked paths whose changes git status does not show: assume-unchanged (a lowercase tag
    in `git ls-files -v`) always, skip-worktree (`S`) unless the worktree is a sparse checkout,
    where that bit is how the excluded paths are marked."""
    p = git(wt, "ls-files", "-v", "-z")
    if p.returncode != 0:
        return None
    sparse = (out(wt, "config", "--bool", "core.sparseCheckout") or "") == "true"
    hidden = []
    for entry in p.stdout.split("\0"):
        if len(entry) < 3:
            continue
        tag, path = entry[0], entry[2:]
        if tag.islower() or (tag == "S" and not sparse):
            hidden.append(path)
    return hidden


def landed_locally(wt: str, head: str) -> str | None:
    """The ok line when HEAD is in the local landing branch and the repository lands on local
    main (landing.py beside this file decides); else None. Asked only when GitHub does not hold
    HEAD, so the GitHub calls run only for a chat whose work landed locally."""
    landing.TIMEOUT_S = GH_TIMEOUT_S
    try:
        branch = landing.landing_branch(wt)
    except landing.SettingError:
        return None
    ref = f"refs/heads/{branch}"
    if not out(wt, "rev-parse", "-q", "--verify", ref + "^{commit}") or \
            git(wt, "merge-base", "--is-ancestor", head, ref).returncode != 0:
        return None
    try:
        mode, _, checks = landing.decide(wt)
    except landing.SettingError:
        return None
    if mode != landing.LOCAL:
        return None
    return f"ok (clean, HEAD {head[:8]} landed on local {branch}; local-main mode)"


def strays(wt: str, merged_head: str | None = None) -> str | None:
    """Why archiving would lose a commit that only this worktree's own history holds (its HEAD
    reflog, ORIG_HEAD, its branch's reflog with the branch counted as deleted, per-worktree
    refs: stranded_commits of work_proof.py); None when nothing would be lost. A primary
    checkout, which archiving never removes, has nothing to lose this way. `merged_head` is the
    head of a merged pull request, which GitHub keeps after deleting its branch."""
    trees = work_proof.worktrees(wt)
    here = os.path.realpath(wt)
    if trees and trees[0]["path"] == here:
        return None
    me = next((t for t in trees[1:] if t["path"] == here), None)
    if me is None:
        return f"{wt} is not in `git worktree list`, so its reflogs cannot be read"
    return work_proof.stranded_commits(trees[0]["path"], me, branch_goes=True,
                                       merged_head=merged_head)


def held_by_successor(wt: str, head: str, seen: list[str]) -> tuple[str | None, str | None]:
    """(the ok line, None) when another branch of origin holds HEAD and GitHub still has that
    branch with HEAD in it; (None, the reason) when a tracking ref holds HEAD but GitHub does not
    confirm it; (None, None) when no other branch of origin holds HEAD. The fetch does not
    prune, so a tracking ref alone may name a branch GitHub deleted unmerged: `git ls-remote`
    asks GitHub for the branch's current tip."""
    p = git(wt, "for-each-ref", "--contains", head, "--format=%(refname)", "refs/remotes/origin/")
    if p.returncode:
        return None, None
    holders = sorted(r for r in p.stdout.split()
                     if r not in seen and r != "refs/remotes/origin/HEAD")
    problem = None
    for ref in holders:
        name = ref[len("refs/remotes/origin/"):]
        try:
            remote = git(wt, "ls-remote", "origin", f"refs/heads/{name}",
                         timeout=LS_REMOTE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return None, (f"origin/{name} holds HEAD, but GitHub did not answer within "
                          f"{LS_REMOTE_TIMEOUT_S} s")
        if remote.returncode:
            return None, (f"origin/{name} holds HEAD, but GitHub could not be asked: "
                          f"{remote.stderr.strip()[:120]}")
        tip = remote.stdout.split()[0] if remote.stdout.split() else None
        if tip and git(wt, "merge-base", "--is-ancestor", head, tip).returncode == 0:
            return (f"ok (clean, HEAD {head[:8]} held by origin/{name}, a successor's pushed "
                    "branch"), None
        problem = problem or f"origin/{name} holds HEAD as last fetched, but GitHub no longer does"
    return None, problem


def merged_into_landing(wt: str, head: str, branch: str | None) -> tuple[str | None, str]:
    """(pull request number, problem): a pull request of origin merged into the landing branch
    whose head is exactly HEAD (squash and rebase merges leave no ancestry)."""
    if not branch:
        return None, "a detached HEAD has no pull request"
    try:
        base = landing.landing_setting(wt)
    except landing.SettingError as e:
        return None, str(e)
    if not base:
        default = out(wt, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD") or ""
        if default.startswith("origin/"):
            base = default.split("/", 1)[1]
        else:
            base = next((b for b in ("main", "master") if out(
                wt, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{b}^{{commit}}")), "main")
    number, problem = work_proof.merged_pull_request(wt, branch, head, base, timeout=GH_TIMEOUT_S)
    return number, problem or f"no pull request of {branch} with head {head[:8]} merged into {base}"


GONE = "ok (worktree gone)"


def verdict(wt: str, fetch: bool = True, landed: bool = False) -> tuple[int, str]:
    """The answer, with the reflog proof (strays) run before every ok of an existing worktree."""
    code, line, merged_head = where_held(wt, fetch, landed)
    if code == 0 and line != GONE:
        stray = strays(wt, merged_head)
        if stray:
            return 1, f"keep: {line[len('ok ('):].rstrip(')')}, but {stray}"
    return code, line


def where_held(wt: str, fetch: bool, landed: bool) -> tuple[int, str, str | None]:
    """(exit code, line, the head of the merged pull request the ok rests on, or None)."""
    code, line = held(wt, fetch, landed)
    merged = line.startswith("ok") and "is the head of pull request #" in line
    return code, line, (out(wt, "rev-parse", "--verify", "HEAD") if merged else None)


def held(wt: str, fetch: bool, landed: bool) -> tuple[int, str]:
    if not os.path.lexists(wt):
        return 0, GONE
    gd = out(wt, "rev-parse", "--absolute-git-dir")
    if not gd:
        return 1, f"keep: {wt} is not a git worktree"
    top = out(wt, "rev-parse", "--show-toplevel")
    if not top or os.path.realpath(top) != os.path.realpath(wt):
        return 1, (f"keep: {wt} is not the top of its own git worktree (it lies inside "
                   f"{top or 'another checkout'}; is its .git link missing?)")
    for op in OPERATIONS:
        if os.path.exists(os.path.join(gd, op)):
            return 1, f"keep: a git operation is in progress ({op})"
    st = git(wt, "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none")
    if st.returncode != 0:
        return 1, f"keep: git status failed: {st.stderr.strip()[:200]}"
    lines = [x for x in st.stdout.splitlines() if x.strip()]
    if lines:
        return 1, f"keep: {len(lines)} changed or untracked path(s), e.g. {lines[0][3:]}"
    hidden = hidden_paths(wt)
    if hidden is None:
        return 1, "keep: git ls-files -v failed"
    if hidden:
        return 1, (f"keep: {len(hidden)} path(s) hidden from git status (assume-unchanged or "
                   f"skip-worktree), e.g. {hidden[0]}")
    head = out(wt, "rev-parse", "--verify", "HEAD")
    if not head:
        return 1, "keep: HEAD does not resolve"
    if "origin" not in (out(wt, "remote") or "").split():
        local = landed_locally(wt, head)
        if local:
            return 0, local
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
    try:
        setting = landing.landing_setting(wt)
    except landing.SettingError as e:
        return 1, f"keep: {e}"
    candidates = []
    if not (landed and setting):  # --landed: the landing branch HANDOFF.md names, when it does
        default = out(wt, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
        candidates += [default] if default else []
        candidates += ["refs/remotes/origin/main", "refs/remotes/origin/master"]
    candidates += [f"refs/remotes/origin/{setting}"] if setting else []
    branch = out(wt, "symbolic-ref", "-q", "--short", "HEAD")
    if branch and not landed:
        candidates.append(f"refs/remotes/origin/{branch}")
    seen = []
    for ref in candidates:
        if ref in seen or not out(wt, "rev-parse", "-q", "--verify", ref + "^{commit}"):
            continue
        seen.append(ref)
        if git(wt, "merge-base", "--is-ancestor", head, ref).returncode == 0:
            short = ref[len("refs/remotes/"):]
            return 0, f"ok (clean, HEAD {head[:8]} in {short}{note})"
    local = landed_locally(wt, head)
    if local:
        return 0, local
    if landed:
        try:
            number, problem = merged_into_landing(wt, head, branch)
        except (OSError, subprocess.SubprocessError) as e:
            number, problem = None, f"gh failed: {e}"
        if number:
            return 0, f"ok (clean, HEAD {head[:8]} is the head of pull request #{number} merged{note})"
        names = " or ".join(r[len("refs/remotes/"):] for r in seen) or "no landing branch of origin"
        return 1, (f"keep: not landed: HEAD {head[:8]} is not in {names}, and {problem}{note}")
    ok, stray = held_by_successor(wt, head, seen)
    if ok:
        return 0, ok + note + ")"
    if not seen:
        return 1, ("keep: no remote-tracking branch to compare with (origin/HEAD, origin/main, "
                   f"origin/master{', origin/' + branch if branch else ''}){note}")
    own = f"refs/remotes/origin/{branch}" if branch else None
    base = own if own in seen else seen[0]
    count = out(wt, "rev-list", "--count", f"{base}..{head}") or "?"
    names = " or ".join(r[len("refs/remotes/"):] for r in seen)
    return 1, (f"keep: {count} commit(s) of {branch or 'the detached HEAD'} are not on GitHub "
               f"(not in {names}){'; ' + stray if stray else ''}{note}")


def main(argv: list[str]) -> int:
    args = [a for a in argv if a not in ("--no-fetch", "--landed")]
    if len(args) != 1 or args[0].startswith("-"):
        print("usage: chat_archivable.py <worktree path> [--landed] [--no-fetch]",
              file=sys.stderr)
        return 2
    try:
        code, line = verdict(args[0], fetch="--no-fetch" not in argv, landed="--landed" in argv)
    except (OSError, subprocess.SubprocessError) as e:
        code, line = 1, f"keep: the check did not run ({e})"
    print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
