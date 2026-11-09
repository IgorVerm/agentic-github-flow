#!/usr/bin/env python3
"""Merge an agent's own pull request, only where a standing grant allows it and every check holds.

Usage: python3 merge_pr.py <number> --grant "<where the grant is written>" [--method merge|squash]
                           [--dry-run] [-C <checkout>] [-R <owner>/<repo>]

Merging is the user's word for each pull request, unless the repository's `HANDOFF.md`
§Standing permissions, or an overlay the user installed, grants automatic merging (the core
rules). This script is how an agent uses such a grant: --grant names where it is written, and is
printed with the result. It checks, reading git and `gh` only, and merges only when all hold:

  mode      landing.py (beside this file) decides pull request for the repository, and the pull
            request's base is the landing branch;
  state     open, not a draft, merge state CLEAN (GitHub's own rules and checks satisfied);
  checks    the pull request has checks and every one finished successfully (a check run
            SUCCESS, NEUTRAL or SKIPPED; a status SUCCESS): on every platform the CI runs;
  review    the newest signed review comment (`🤖 <agent> (<role with "review">): ...`, a
            comment or a review body) opens with `Approved <sha>` and was written by an agent
            that did not write the change (the reviewer's attestation). <sha> is the head
            commit, or an earlier commit followed only by merges of the base branch that git
            resolves without conflict (the merge commit's tree is git's own merge result), so a
            merge of the default branch after the review needs only green checks again;
  overlap   the body holds the overlap check's result: a line starting with `Overlap` (the
            ship-change skill's step 5);
  paths     no changed path (both sides of a rename) is one that merges only on the user's
            word: EXCLUDED below, and the patterns (comma-separated, `*` matches across `/`) of
            the row `merge on the user's word` in HANDOFF.md's `## Landing settings`.

Then `gh pr merge <n> --match-head-commit <sha> --delete-branch --merge` (or --squash), so a
commit pushed after the checks makes GitHub refuse. Afterwards the cleanup-merged skill. A bare
`gh pr merge` stays an ask rule; this script is the one route around it. AGENTIC_GITHUB_FLOW_GH,
a JSON list, replaces the `gh` command (tests use it). Exit 0 merged (or, with --dry-run, would
merge), 1 refused with every reason printed, 2 usage error or unreadable state.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from landing import (PR, GITHUB_URL, SettingError, decide, gh_command, row,  # noqa: E402
                     settings_text)

# Paths that merge only on the user's word: the always-loaded rules and a repository's own
# rules, guards, permission settings, hooks, the installer, CI and deployment configuration.
EXCLUDED = (
    "rules/core.md", "AGENTS.md", "*/AGENTS.md", "AGENTS.override.md", "*/AGENTS.override.md",
    "CLAUDE.md", "*/CLAUDE.md",
    "plugins/guards/*", "*/settings.json", "*/settings.local.json", ".claude/*", ".codex/*",
    "hooks/*", "*/hooks/*", "*/hooks.json", "templates/pre-push", ".githooks/*", ".husky/*",
    "install.sh", "install.ps1", "tools/installer.py",
    ".github/workflows/*", ".github/actions/*", ".gitlab-ci.yml", ".circleci/*",
    "vercel.json", "netlify.toml", "fly.toml", "render.yaml", "app.yaml", "Procfile",
    "Dockerfile", "*/Dockerfile", "docker-compose*.yml", "supabase/config.toml",
    ".vercel/*", "deploy/*", "infra/*", "terraform/*", "*.tf",
)
PASSED_RUNS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
SIGNED = re.compile(r"\A\s*\N{ROBOT FACE}\s*[^\n(]*\(([^)\n]*)\):\s*(?:\*\*)?(.*)", re.S)
APPROVED = re.compile(r"\Aapproved\b[^0-9a-f\n]*`?([0-9a-f]{7,40})\b", re.I)
OVERLAP = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?overlap", re.I | re.M)


def git(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", path, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def gh(command: list, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(command + list(args), stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def excluded(path: str, extra: list) -> bool:
    return any(fnmatch.fnmatchcase(path, p) for p in EXCLUDED + tuple(extra))


def check_runs(rollup) -> list:
    """The reasons the checks do not all pass; empty when they do."""
    if not rollup:
        return ["no checks ran on the head commit"]
    bad = []
    for c in rollup:
        name = c.get("name") or c.get("context") or "?"
        if c.get("__typename") == "StatusContext" or "state" in c and "conclusion" not in c:
            if str(c.get("state")).upper() != "SUCCESS":
                bad.append(f"status {name}: {c.get('state')}")
        elif str(c.get("status")).upper() != "COMPLETED":
            bad.append(f"check {name}: {c.get('status')}")
        elif str(c.get("conclusion")).upper() not in PASSED_RUNS:
            bad.append(f"check {name}: {c.get('conclusion')}")
    return bad


def clean_base_merges(path: str, reviewed: str, head: str, base_ref: str) -> str | None:
    """None when every commit after <reviewed> up to <head> is a merge of the base branch that
    git resolves without conflict; else the reason."""
    if git(path, "merge-base", "--is-ancestor", reviewed, head).returncode != 0:
        return f"the reviewed commit {reviewed[:10]} is not in the head"
    chain = git(path, "rev-list", "--first-parent", head).stdout.split()
    if reviewed not in chain:
        return f"the reviewed commit {reviewed[:10]} is not on the head's own line of commits"
    commits = git(path, "rev-list", "--first-parent", "--parents",
                  f"{reviewed}..{head}").stdout.split("\n")
    for line in filter(None, commits):
        sha, *parents = line.split()
        if len(parents) != 2:
            return f"{sha[:10]} after the review is not a merge of the base branch"
        if git(path, "merge-base", "--is-ancestor", parents[1], base_ref).returncode != 0:
            return f"{sha[:10]} after the review merges something other than the base branch"
        tree = git(path, "merge-tree", "--write-tree", parents[0], parents[1])
        own = git(path, "rev-parse", f"{sha}^{{tree}}").stdout.strip()
        if tree.returncode != 0 or tree.stdout.split("\n")[0].strip() != own:
            return f"{sha[:10]} after the review is a merge with a conflict or an edit"
    return None


def review_reason(path: str, texts: list, head: str, base_ref: str) -> tuple:
    """(reason or None, what was found). <texts> are comment and review bodies, oldest first."""
    reviews = []
    for body in texts:
        m = SIGNED.match(body or "")
        if m and "review" in m.group(1).lower():
            reviews.append(m.group(2).strip())
    if not reviews:
        return "no signed review comment (`🤖 <agent> (review): Approved <sha>`)", ""
    newest = reviews[-1]
    m = APPROVED.match(newest)
    if not m:
        return f"the newest signed review does not approve: {newest[:80]!r}", ""
    token = m.group(1).lower()
    if head.startswith(token):
        return None, f"approved at the head {head[:10]}"
    resolved = git(path, "rev-parse", "-q", "--verify", token + "^{commit}").stdout.strip()
    if not resolved:
        return f"the approved commit {token} is not in this repository", ""
    why = clean_base_merges(path, resolved, head, base_ref)
    if why:
        return f"approved {resolved[:10]}, but {why}: review the head again", ""
    return None, f"approved {resolved[:10]}; since then only conflict-free merges of the base"


def main(argv: list) -> int:
    number, grant, method, dry, path, repo, i = None, None, "merge", False, ".", None, 0
    while i < len(argv):
        a = argv[i]
        if a in ("--grant", "--method", "-C", "-R") and i + 1 < len(argv):
            value = argv[i + 1]
            if a == "--grant":
                grant = value
            elif a == "--method":
                method = value
            elif a == "-R":
                repo = value
            else:
                path = value
            i += 2
            continue
        if a == "--dry-run":
            dry = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a.isdigit() and number is None:
            number = a
        else:
            print(__doc__, file=sys.stderr)
            return 2
        i += 1
    if number is None or not (grant or "").strip() or method not in ("merge", "squash"):
        print("merge_pr: usage: merge_pr.py <number> --grant \"<where the grant is written>\" "
              "[--method merge|squash] [--dry-run]", file=sys.stderr)
        return 2

    command = gh_command()
    m = GITHUB_URL.match(git(path, "remote", "get-url", "origin").stdout.strip())
    repo = repo or (f"{m.group(1)}/{m.group(2)}" if m else None)
    if command is None or not repo:
        print("merge_pr: needs gh, and an origin on github.com or -R <owner>/<repo>",
              file=sys.stderr)
        return 2
    reasons = []
    try:
        mode, landing, checks = decide(path)
        extra = [p for p in re.split(r"[,\s]+", row(settings_text(path),
                                                       "merge on the user's word") or "") if p]
    except SettingError as e:
        print(f"merge_pr: {e}", file=sys.stderr)
        return 2
    if mode != PR:
        reasons.append(f"the repository lands on {mode}, not through pull requests")

    fields = ("number,state,isDraft,mergeStateStatus,headRefOid,baseRefName,body,comments,"
              "reviews,statusCheckRollup")
    r = gh(command, "pr", "view", number, "-R", repo, "--json", fields)
    try:
        pr = json.loads(r.stdout) if r.returncode == 0 else None
    except ValueError:
        pr = None
    if not isinstance(pr, dict):
        print(f"merge_pr: cannot read pull request {number}: {r.stderr.strip()[:200]}",
              file=sys.stderr)
        return 2
    head, base = str(pr.get("headRefOid") or ""), str(pr.get("baseRefName") or "")
    if pr.get("state") != "OPEN":
        reasons.append(f"state {pr.get('state')}")
    if pr.get("isDraft"):
        reasons.append("a draft")
    if pr.get("mergeStateStatus") != "CLEAN":
        reasons.append(f"merge state {pr.get('mergeStateStatus')}, not CLEAN")
    if base != landing:
        reasons.append(f"its base is {base}, not the landing branch {landing}")
    reasons += check_runs(pr.get("statusCheckRollup"))
    if not OVERLAP.search(pr.get("body") or ""):
        reasons.append("the body has no overlap check result (a line starting with `Overlap`)")

    fetched = git(path, "fetch", "--quiet", "origin", f"refs/pull/{number}/head",
                  f"+refs/heads/{landing}:refs/remotes/origin/{landing}")
    if fetched.returncode != 0 or git(path, "rev-parse", "-q", "--verify",
                                      head + "^{commit}").returncode != 0:
        print(f"merge_pr: cannot fetch the head {head[:10]}: {fetched.stderr.strip()[:200]}",
              file=sys.stderr)
        return 2
    base_ref = f"refs/remotes/origin/{landing}"
    # comments and reviews, oldest first by their time (ISO 8601 strings sort by time)
    dated = sorted((str((c or {}).get("createdAt") or (c or {}).get("submittedAt") or ""),
                    (c or {}).get("body") or "") for c in
                   (pr.get("comments") or []) + (pr.get("reviews") or []))
    texts = [b for _, b in dated]
    why, found = review_reason(path, texts, head, base_ref)
    if why:
        reasons.append(why)

    merge_base = git(path, "merge-base", base_ref, head).stdout.strip()
    names = git(path, "diff", "--name-status", "-z", "--find-renames", merge_base, head)
    if not merge_base or names.returncode != 0:
        reasons.append("cannot list the changed paths")
    else:
        parts = [p for p in names.stdout.split("\0") if p]
        changed, j = [], 0
        while j < len(parts):
            n = 2 if parts[j][:1] in ("R", "C") else 1
            changed += parts[j + 1:j + 1 + n]
            j += 1 + n
        held = sorted({p for p in changed if excluded(p, extra)})
        if held:
            reasons.append("paths that merge only on the user's word: " + ", ".join(held[:8]))

    print(f"merge_pr: #{number} in {repo}, head {head[:10]}, grant: {grant.strip()}")
    print(f"merge_pr: mode {mode}; {found or 'no approved review'}")
    if reasons:
        for reason in reasons:
            print(f"merge_pr: REFUSED: {reason}")
        return 1
    if dry:
        print(f"merge_pr: would merge #{number} at {head[:10]} (--{method})")
        return 0
    r = gh(command, "pr", "merge", number, "-R", repo, f"--{method}", "--match-head-commit",
           head, "--delete-branch")
    if r.returncode != 0:
        print(f"merge_pr: REFUSED by GitHub: {(r.stderr or r.stdout).strip()[:300]}")
        return 1
    print(f"merge_pr: merged #{number} at {head[:10]}; next: the cleanup-merged skill")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
