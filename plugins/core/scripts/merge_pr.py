#!/usr/bin/env python3
"""Merge an agent's own pull request, only where the repository switched automatic merging on and
every check holds.

Usage: python3 merge_pr.py <number> [--ready] [--method merge|squash] [--dry-run]
                           [-C <checkout>] [-R <owner>/<repo>] [--grant "<text>"]

Merging, and marking a draft ready, is the user's word for each pull request, unless the
repository switched automatic merging on (the core rules): a row `automatic merge` with the
value `on` in the `## Standing permissions` section of HANDOFF.md as the default branch holds
it, set by the user by hand (the maintainer's ruling of 2026-11-11, DESIGN_DECISIONS.md). An
overlay cannot switch it on: without the row this script refuses, whatever a grant says.
--grant is still accepted from older callers and only printed. The script fetches, then checks,
reading git and `gh` only, and merges only when all hold:

  switch    the row above, on the default branch;
  mode      landing.py (beside this file) decides pull request for the repository, and the pull
            request's base is the landing branch;
  state     open, not a draft, merge state CLEAN (GitHub's own rules and checks satisfied), and
            no review decision CHANGES_REQUESTED. With --ready a draft passes (merge state DRAFT
            or CLEAN) when every other condition holds: the script then marks it ready
            (`gh pr ready`), reads the pull request again until GitHub has computed its merge
            state, and merges only when it is CLEAN at the same head; otherwise it reports, and
            the pull request stays ready for the user;
  checks    every required check is on the head commit and SUCCESS (a skipped one is not; one
            GitHub ties to an app only as a check run), and no other check failed or is
            unfinished. Required: the checks GitHub requires on the landing branch (ruleset or
            branch protection, as far as readable) and the names, separated by `;`, in the row
            `required checks` of HANDOFF.md's `## Landing settings`; none named at all refuses,
            since "every platform" cannot be checked then;
  review    the newest signed review by the signed-in account (agents post under the user's
            account; a stranger's or a pending review never counts), with the role `review` or
            `reviewer` (`🤖 <agent> (review): Approved <sha>`), approves: it opens with
            `Approved` and the SHA. review_verdict.py (beside this file, posted by the
            review-change skill) owns that format; this script reads it through its verdict().
            That the reviewer did not write the change is its attestation. Only a pull request
            comment approves, and not once it was edited after posting (`includesCreatedEdit`;
            missing counts as edited): anyone signed in as the account can edit it, the
            author's session too. A GitHub review's body never approves, since gh does not
            report whether it was edited; it still blocks. A SHA prefix counts only where git
            resolves it to one commit that starts with it (a ref named like the prefix does
            not). <sha> is the head commit, or an earlier commit on the head's own line
            followed only by two-parent merges of the base branch whose tree is git's own merge
            result (no conflict resolved, nothing edited), so a merge of the default branch
            after the review needs only green checks again. A newer review of that account
            with state CHANGES_REQUESTED refuses, and so does the latest review of anyone with
            write access (owner, member, collaborator) that requests changes;
  overlap   the body holds the overlap check's result: a line starting with `Overlap` (the
            ship-change skill's step 5); what it says stays the reviewer's to judge;
  paths     no changed path (both sides of a rename; compared without case, since macOS and
            Windows do not tell case apart) is one that merges only on the user's word: EXCLUDED
            below (a plugin manifest whose versions alone changed excepted: MANIFESTS), and the
            patterns (comma-separated, `*` matches across `/`) of the row `merge on the user's
            word`; and the sections `## Standing permissions` and `## Landing settings` of
            HANDOFF.md (any case of its name), which hold the switch and these settings, are
            unchanged, as is every line that names either.

Then `gh pr merge <n> --match-head-commit <sha> --delete-branch --merge` (or --squash), so a
commit pushed after the checks makes GitHub refuse. Afterwards the cleanup-merged skill. A bare
`gh pr merge` stays an ask rule; this script is the one route around it. -R must name the same
repository as origin (it exists for a checkout whose origin is not on github.com, as in the
tests). AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command. Exit 0 merged (or, with
--dry-run, would merge), 1 refused with every reason printed, 2 usage error or unreadable state.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from landing import (PR, GITHUB_URL, SettingError, Unknown, decide, gh_command,  # noqa: E402
                     gh_json, row, settings_text)
from review_verdict import verdict  # noqa: E402

# Paths that merge only on the user's word: the always-loaded rules and a repository's own
# rules, this gate itself, guards, permission settings, hooks and plugin manifests (which can
# declare hooks), the installer, CI and repository configuration, deployment configuration.
EXCLUDED = (
    "rules/core.md", "AGENTS.md", "*/AGENTS.md", "AGENTS.override.md", "*/AGENTS.override.md",
    "CLAUDE.md", "*/CLAUDE.md",
    "*/merge_pr.py", "*/landing.py", "*/review_verdict.py", "*/push_branch.py", "*/push_paths.py",
    "plugins/guards/*", "*/settings.json", "*/settings.local.json", ".claude/*", ".codex/*",
    "*.claude-plugin/*", "*.codex-plugin/*", ".agents/*",  # but see MANIFESTS
    "hooks/*", "plugins/*/hooks/*", "hooks.json", "*/hooks.json", "templates/pre-push",
    ".githooks/*", ".husky/*", ".pre-commit-config.yaml", "lefthook.yml", "lefthook.yaml",
    "install.sh", "install.ps1", "tools/installer.py",
    ".github/*", ".gitlab-ci.yml", ".circleci/*",
    "vercel.json", "netlify.toml", "fly.toml", "render.yaml", "app.yaml", "Procfile",
    "Dockerfile", "*/Dockerfile", "docker-compose*.yml", "supabase/config.toml",
    ".vercel/*", "deploy/*", "infra/*", "terraform/*", "*.tf",
)
# Plugin manifests and marketplace files: a change of `version` alone (every plugin change
# raises it) passes; any other change, such as a hook a manifest declares, is held.
MANIFESTS = ("*.claude-plugin/*.json", "*.codex-plugin/*.json", ".agents/plugins/*.json")
GUARDED_SECTIONS = ("Standing permissions", "Landing settings")
SWITCH = "automatic merge"
READY_WAIT_S, READY_POLL_S = 60, 5
GUARDED_LINE = re.compile(r"standing permission|landing setting", re.I)
PASSED_RUNS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
OVERLAP = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?overlap", re.I | re.M)


def git(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", path, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def gh(command: list, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(command + list(args), stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def excluded(path: str, extra: list) -> bool:
    folded = path.casefold()
    return any(fnmatch.fnmatchcase(folded, p.casefold()) for p in EXCLUDED + tuple(extra))


def without_versions(value):
    if isinstance(value, dict):
        return {k: without_versions(v) for k, v in value.items() if k != "version"}
    if isinstance(value, list):
        return [without_versions(v) for v in value]
    return value


def version_only(path: str, before: str, after: str, name: str) -> bool:
    """Whether the manifest <name> changed between the two commits in its versions alone."""
    if not any(fnmatch.fnmatchcase(name.casefold(), p) for p in MANIFESTS):
        return False
    old, new = git(path, "show", f"{before}:{name}"), git(path, "show", f"{after}:{name}")
    if old.returncode or new.returncode:
        return False  # added or removed: held
    try:
        return without_versions(json.loads(old.stdout)) == without_versions(json.loads(new.stdout))
    except ValueError:
        return False


def section(text: str | None, title: str) -> str:
    m = re.search(r"^## %s[ \t]*$(.*?)(?=^## |\Z)" % re.escape(title), text or "", re.M | re.S)
    return m.group(1).strip() if m else ""


def switched_on(text: str | None) -> bool:
    """Whether HANDOFF.md's `## Standing permissions` has the row `automatic merge` set to `on`."""
    for line in section(text, GUARDED_SECTIONS[0]).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and len(cells) >= 2 and cells[0].lower() == SWITCH:
            return cells[1].replace("`", "").strip().lower() == "on"
    return False


def required_checks(command: list, repo: str, branch: str, named: list) -> set:
    """The check names required on <branch>: the ruleset's and branch protection's, as far as
    readable, and the names HANDOFF.md lists. A name GitHub ties to an app (integration_id) is
    returned as "app:<name>": only a check run, not a status anyone can post, satisfies it."""
    required = set(named)
    try:
        status, rules = gh_json(command, "api", f"repos/{repo}/rules/branches/{branch}")
        for rule in rules if status == 200 and isinstance(rules, list) else []:
            if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
                for c in (rule.get("parameters") or {}).get("required_status_checks") or []:
                    required.add(("app:" if c.get("integration_id") else "")
                                 + str(c.get("context")))
        status, prot = gh_json(command, "api",
                               f"repos/{repo}/branches/{branch}/protection/required_status_checks")
        if status == 200 and isinstance(prot, dict):
            required |= {str(c) for c in prot.get("contexts") or []}
            required |= {("app:" if c.get("app_id") else "") + str(c.get("context"))
                         for c in prot.get("checks") or []}
    except Unknown:
        pass
    return {r for r in required if r and not r.endswith("None")}


def check_reasons(rollup, required: set) -> list:
    """The reasons the checks do not pass; empty when they do."""
    if not required:
        return ["no required checks are named (a ruleset or branch protection on the landing "
                "branch, or the row `required checks` in Landing settings)"]
    bad, passed, runs = [], set(), set()
    for c in rollup or []:
        name = str(c.get("name") or c.get("context") or "?")
        if c.get("__typename") == "StatusContext" or ("state" in c and "conclusion" not in c):
            state = str(c.get("state")).upper()
            if state == "SUCCESS":
                passed.add(name)
            else:
                bad.append(f"status {name}: {state}")
        elif str(c.get("status")).upper() != "COMPLETED":
            bad.append(f"check {name}: {c.get('status')}")
        else:
            conclusion = str(c.get("conclusion")).upper()
            if conclusion == "SUCCESS":
                passed.add(name)
                runs.add(name)
            elif conclusion not in PASSED_RUNS:
                bad.append(f"check {name}: {conclusion}")
    missing = sorted(r for r in required if (r[4:] not in runs if r.startswith("app:")
                                             else r not in passed))
    if missing:
        bad.append("required checks not passed on the head: " + ", ".join(missing))
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


MEMBERS = {"OWNER", "MEMBER", "COLLABORATOR"}


def changes_requested(pr: dict) -> list:
    """The people with write access (owner, member, collaborator) whose latest submitted review
    requests changes."""
    latest = {}
    for r in sorted(pr.get("reviews") or [], key=lambda r: str((r or {}).get("submittedAt"))):
        state = str((r or {}).get("state") or "").upper()
        who = str(((r or {}).get("author") or {}).get("login") or "")
        if state in ("PENDING", "COMMENTED", "") or not (r or {}).get("submittedAt") or not who:
            continue
        if str((r or {}).get("authorAssociation") or "").upper() in MEMBERS:
            latest[who] = state
    return sorted(w for w, s in latest.items() if s == "CHANGES_REQUESTED")


def review_reason(path: str, pr: dict, login: str, head: str, base_ref: str) -> tuple:
    """(reason or None, what was found), from the comments and submitted reviews of <login>."""
    events = []  # (time, kind, state, body, edited)
    for c in pr.get("comments") or []:
        if ((c or {}).get("author") or {}).get("login", "").lower() == login.lower():
            events.append((str(c.get("createdAt") or ""), "comment", "", c.get("body") or "",
                           c.get("includesCreatedEdit") is not False))
    for r in pr.get("reviews") or []:
        state = str((r or {}).get("state") or "").upper()
        if state == "PENDING" or not (r or {}).get("submittedAt"):
            continue
        if ((r or {}).get("author") or {}).get("login", "").lower() == login.lower():
            events.append((str(r.get("submittedAt")), "review", state, r.get("body") or "",
                           True))  # gh does not fetch includesCreatedEdit for reviews
    events.sort(key=lambda e: e[0])  # ISO 8601 strings sort by time
    verdicts = []  # (time, approved sha or None, text)
    for when, kind, state, body, edited in events:
        signed = verdict(body)
        if kind == "review" and state == "CHANGES_REQUESTED":
            verdicts.append((when, None, "changes requested"))
        elif signed and kind == "review":
            verdicts.append((when, None, "a GitHub review, which never approves: post the "
                             "approval as a comment (the review-change skill)"))
        elif signed and edited:
            verdicts.append((when, None, "edited after it was posted; post a new review"))
        elif signed:
            verdicts.append((when, *signed))
    if not verdicts:
        return ("no signed review by this account (`🤖 <agent> (review): Approved <sha>`)", "")
    _, token, text = verdicts[-1]
    if not token:
        return f"the newest review does not approve: {text[:80]!r}", ""
    resolved = head if token == head else \
        git(path, "rev-parse", "-q", "--verify", token + "^{commit}").stdout.strip()
    if not resolved or not resolved.startswith(token):
        return f"the approved commit {token} is not in this repository (or not unique)", ""
    if resolved == head:
        return None, f"approved at the head {head[:10]}"
    why = clean_base_merges(path, resolved, head, base_ref)
    if why:
        return f"approved {resolved[:10]}, but {why}: review the head again", ""
    return None, f"approved {resolved[:10]}; since then only conflict-free merges of the base"


def mark_ready(command: list, repo: str, number: str, head: str) -> str | None:
    """Mark the draft ready and wait until GitHub has computed its merge state: None when it is
    CLEAN at <head>, else the reason."""
    r = gh(command, "pr", "ready", number, "-R", repo)
    if r.returncode != 0:
        return f"gh pr ready failed: {(r.stderr or r.stdout).strip()[:200]}"
    state, waited = "UNKNOWN", 0
    while True:
        r = gh(command, "pr", "view", number, "-R", repo, "--json",
               "isDraft,mergeStateStatus,headRefOid")
        try:
            now = json.loads(r.stdout) if r.returncode == 0 else {}
        except ValueError:
            now = {}
        if not isinstance(now, dict):
            now = {}
        if now.get("headRefOid") and now.get("headRefOid") != head:
            return f"the head moved to {str(now.get('headRefOid'))[:10]}"
        state = str(now.get("mergeStateStatus") or "UNKNOWN")
        if not now.get("isDraft") and state not in ("UNKNOWN", "DRAFT"):
            break
        if waited >= READY_WAIT_S:
            break
        time.sleep(READY_POLL_S)
        waited += READY_POLL_S
    return None if state == "CLEAN" else f"merge state {state}, not CLEAN"


def main(argv: list) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except AttributeError:
        pass
    number, grant, method, path, repo, i = None, "", "merge", ".", None, 0
    dry = ready = False
    while i < len(argv):
        a = argv[i]
        if a in ("--grant", "--method", "-C", "-R") and i + 1 < len(argv) \
                and not argv[i + 1].startswith("-"):
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
        elif a == "--ready":
            ready = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        elif a.isdigit() and number is None:
            number = a
        else:
            print(__doc__, file=sys.stderr)
            return 2
        i += 1
    if number is None or method not in ("merge", "squash"):
        print("merge_pr: usage: merge_pr.py <number> [--ready] [--method merge|squash] "
              "[--dry-run]", file=sys.stderr)
        return 2

    command = gh_command()
    m = GITHUB_URL.match(git(path, "remote", "get-url", "origin").stdout.strip())
    origin_repo = f"{m.group(1)}/{m.group(2)}" if m else None
    if repo and origin_repo and repo.lower() != origin_repo.lower():
        print(f"merge_pr: -R {repo} is not origin's repository {origin_repo}", file=sys.stderr)
        return 2
    repo = repo or origin_repo
    if command is None or not repo:
        print("merge_pr: needs gh, and an origin on github.com or -R <owner>/<repo>",
              file=sys.stderr)
        return 2

    fields = ("number,state,isDraft,mergeStateStatus,reviewDecision,headRefOid,baseRefName,"
              "body,comments,reviews,statusCheckRollup")
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

    fetched = git(path, "fetch", "--quiet", "origin", f"refs/pull/{number}/head")
    fetched_all = git(path, "fetch", "--quiet", "origin")
    if fetched.returncode != 0 or fetched_all.returncode != 0 or \
            git(path, "rev-parse", "-q", "--verify", head + "^{commit}").returncode != 0:
        print(f"merge_pr: cannot fetch the head {head[:10]}: "
              f"{(fetched.stderr + fetched_all.stderr).strip()[:200]}", file=sys.stderr)
        return 2
    try:
        mode, landing, _ = decide(path)
        text = settings_text(path)
    except SettingError as e:
        print(f"merge_pr: {e}", file=sys.stderr)
        return 2
    refreshed = git(path, "fetch", "--quiet", "origin",
                    f"+refs/heads/{landing}:refs/remotes/origin/{landing}")
    if refreshed.returncode != 0:
        print(f"merge_pr: cannot fetch the landing branch {landing}: "
              f"{refreshed.stderr.strip()[:200]}", file=sys.stderr)
        return 2
    split = lambda v: [p for p in re.split(r"[,\s]+", v or "") if p]  # noqa: E731
    extra = split(row(text, "merge on the user's word"))
    named = [p.strip() for p in (row(text, "required checks") or "").split(";") if p.strip()]

    reasons = []
    if not switched_on(text):
        reasons.append("automatic merging is not switched on in this repository: the user sets "
                       f"the row `{SWITCH}` | `on` in HANDOFF.md §Standing permissions by hand")
    if mode != PR:
        reasons.append(f"the repository lands on {mode}, not through pull requests")
    if pr.get("state") != "OPEN":
        reasons.append(f"state {pr.get('state')}")
    draft = bool(pr.get("isDraft"))
    if draft and not ready:
        reasons.append("a draft (--ready marks it ready when everything else holds)")
    if pr.get("mergeStateStatus") != "CLEAN" and not (
            draft and ready and pr.get("mergeStateStatus") == "DRAFT"):
        reasons.append(f"merge state {pr.get('mergeStateStatus')}, not CLEAN")
    if str(pr.get("reviewDecision") or "").upper() == "CHANGES_REQUESTED":
        reasons.append("a review requests changes")
    for who in changes_requested(pr):
        reasons.append(f"{who} requests changes")
    if base != landing:
        reasons.append(f"its base is {base}, not the landing branch {landing}")
    reasons += check_reasons(pr.get("statusCheckRollup"),
                             required_checks(command, repo, landing, named))
    if not OVERLAP.search(pr.get("body") or ""):
        reasons.append("the body has no overlap check result (a line starting with `Overlap`)")

    base_ref = f"refs/remotes/origin/{landing}"
    try:
        status, me = gh_json(command, "api", "user")
    except Unknown as e:
        status, me = 0, {"message": str(e)}
    login = me.get("login") if status == 200 and isinstance(me, dict) else None
    if not login:
        print("merge_pr: cannot read the signed-in account", file=sys.stderr)
        return 2
    why, found = review_reason(path, pr, login, head, base_ref)
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
        held = sorted({p for p in changed if excluded(p, extra)
                       and not version_only(path, merge_base, head, p)})
        if held:
            reasons.append("paths that merge only on the user's word: " + ", ".join(held[:8]))
        for name in sorted({p for p in changed if p.casefold() == "handoff.md"}):
            before = git(path, "show", f"{merge_base}:{name}").stdout
            after = git(path, "show", f"{head}:{name}").stdout
            diff = git(path, "diff", "-U0", merge_base, head, "--", name).stdout.splitlines()
            touched = [l for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---"))
                       and GUARDED_LINE.search(l)]
            if touched or any(section(before, t) != section(after, t) for t in GUARDED_SECTIONS):
                reasons.append(f"{name}: §Standing permissions, §Landing settings or a line "
                               "naming them changes: that merges only on the user's word")

    print(f"merge_pr: #{number} in {repo}, head {head[:10]}, switch: HANDOFF.md §Standing "
          f"permissions, {SWITCH}" + (f"; grant named: {grant.strip()}" if grant.strip() else ""))
    print(f"merge_pr: mode {mode}; {found or 'no approved review'}")
    if reasons:
        for reason in reasons:
            print(f"merge_pr: REFUSED: {reason}")
        return 1
    if dry:
        print(f"merge_pr: would {'mark ready and ' if draft else ''}merge #{number} at "
              f"{head[:10]} (--{method})")
        return 0
    if draft:
        why = mark_ready(command, repo, number, head)
        if why:
            print(f"merge_pr: REFUSED after marking #{number} ready: {why}; it stays ready for "
                  "the user")
            return 1
    r = gh(command, "pr", "merge", number, "-R", repo, f"--{method}", "--match-head-commit",
           head, "--delete-branch")
    if r.returncode != 0:
        after = gh(command, "pr", "view", number, "-R", repo, "--json", "state")
        if '"MERGED"' in after.stdout:
            print(f"merge_pr: merged #{number} at {head[:10]}, but GitHub reported: "
                  f"{(r.stderr or r.stdout).strip()[:200]} (the branch may still exist); next: "
                  "the cleanup-merged skill")
            return 0
        print(f"merge_pr: REFUSED by GitHub: {(r.stderr or r.stdout).strip()[:300]}")
        return 1
    print(f"merge_pr: merged #{number} at {head[:10]}; next: the cleanup-merged skill")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
