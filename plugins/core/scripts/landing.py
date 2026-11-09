#!/usr/bin/env python3
"""How does finished work land in this repository: on local main, or through a pull request?

Usage: python3 landing.py [-C <checkout>] [--branch]

The ship-change skill runs it at every landing and follows its last line; promote_main.py and the
issue chats ask it too. It prints one `check:` line per signal it read, then
`landing branch: <name>` and last `landing: pull request` or `landing: local main`. With
--branch it prints only the landing branch. First match wins:

  1. setting   HANDOFF.md, section `## Landing settings`, row `landing`: `pull request` gives
               pull request; `local main` gives local main unless the server is seen to
               require pull requests (3); when the server cannot be read (5) the setting holds,
               since a push the server rejects only stops there. `auto` or no row: go on. An
               unknown value gives pull request.
  2. no origin no remote `origin`: local main, there is no server to open a pull request on.
  3. server    the landing branch on GitHub has an active ruleset rule that forbids a direct
               push (PUSH_RULES, or a type not in HARMLESS_RULES), or legacy branch protection
               with required reviews, required status checks, push restrictions or a lock (an
               unreadable protection of a branch GitHub calls protected counts too): pull
               request. HTTP 403 "Upgrade to GitHub Pro ..." means the plan offers no
               protection, which is not "unknown".
  4. team      the owner is an Organization, the user cannot push, more than one collaborator
               can write, a CODEOWNERS file is on the landing branch, or someone else (not a bot)
               merged a pull request into it in the last 90 days: pull request.
  5. unknown   origin not on github.com, no gh, not signed in, a network or API error: pull
               request.
  6. otherwise one writer, a User owner, no protection, no team signal: local main.

The settings are read from HANDOFF.md as the default branch holds it, as last fetched
(`refs/remotes/origin/HEAD`, else origin/main or origin/master, else local main or master); a
change to them counts once it has landed. The landing branch is the row `landing branch`, else
the remote's default branch (`origin/HEAD`), else `main`. The scripts that count "merged" or
"landed" and the worktree tool read it through landing_branch() and landing_ref() here.
It does not fetch. AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command (tests use it).
A copy of this file lives in the issue-chats plugin (an installed plugin stands alone);
tests/landing.py keeps the two identical. Exit 0 with a decision, 2 for a usage error, a
checkout outside git, or an invalid `landing branch`.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys

PR, LOCAL = "pull request", "local main"
SECTION = re.compile(r"^## Landing settings[ \t]*$(.*?)(?=^## |\Z)", re.M | re.S)
# Ruleset rule types that make a direct push of a reviewed commit fail: it needs a pull request,
# a merge queue, checks or a deployment first, or updates are blocked outright.
PUSH_RULES = {"pull_request", "update", "required_status_checks", "merge_queue",
              "required_deployments", "workflows", "code_scanning"}
# Types a fast-forward push of reviewed commits passes: they forbid force pushes, deletion or
# creation, or constrain what a commit contains. Any type in neither set counts as PUSH_RULES.
HARMLESS_RULES = {"non_fast_forward", "deletion", "creation", "required_linear_history",
                  "required_signatures", "commit_message_pattern", "commit_author_email_pattern",
                  "committer_email_pattern", "branch_name_pattern", "tag_name_pattern",
                  "file_path_restriction", "max_file_path_length", "file_extension_restriction",
                  "max_file_size", "copilot_code_review"}
PLAN_LIMIT = "upgrade to github pro"
GITHUB_URL = re.compile(r"^(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:|"
                        r"ssh://git@github\.com(?::\d+)?/)([^/]+)/([^/]+?)(?:\.git)?/?$", re.I)
CODEOWNERS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")
RECENT_DAYS = 90
TIMEOUT_S = 20


class SettingError(Exception):
    pass


class Unknown(Exception):
    """GitHub could not be read: the decision falls to pull request (rule 5)."""


def git(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", path, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)


def out(path: str, *args: str) -> str | None:
    r = git(path, *args)
    return r.stdout.strip() if r.returncode == 0 else None


def verified(path: str, ref: str) -> bool:
    return bool(ref) and git(path, "rev-parse", "-q", "--verify",
                             ref + "^{commit}").returncode == 0


def settings_text(path: str) -> str | None:
    """HANDOFF.md as the default branch holds it, or None when there is none."""
    if out(path, "rev-parse", "--show-toplevel") is None:
        raise SettingError(f"{path} is not in a git repository")
    head = out(path, "symbolic-ref", "-q", "refs/remotes/origin/HEAD") or ""
    for ref in (head, "refs/remotes/origin/main", "refs/remotes/origin/master",
                "refs/heads/main", "refs/heads/master"):
        if verified(path, ref):
            return out(path, "show", f"{ref}:HANDOFF.md")
    return None


def row(text: str | None, name: str) -> str | None:
    """The value cell of the row <name> of `## Landing settings`, backticks removed, or None."""
    sec = SECTION.search(text or "")
    if not sec:
        return None
    for line in sec.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0].lower() == name:
            return cells[1].replace("`", "").strip() or None
    return None


def landing_setting(path: str = ".") -> str | None:
    """The row `landing branch` when it is set, else None; SettingError when it is no branch
    name. The other scripts call this and keep their own default without the row."""
    value = row(settings_text(path), "landing branch")
    if value and (value.startswith("-") or
                  git(path, "check-ref-format", "--branch", value).returncode != 0):
        raise SettingError(f"`landing branch` in HANDOFF.md is not a branch name: {value!r}")
    return value


def landing_branch(path: str = ".") -> str:
    """The branch work lands on: the setting, else origin's default branch, else main."""
    value = landing_setting(path)
    if value:
        return value
    head = out(path, "symbolic-ref", "-q", "refs/remotes/origin/HEAD") or ""
    if head.startswith("refs/remotes/origin/"):
        return head[len("refs/remotes/origin/"):]
    for name in ("main", "master"):
        if verified(path, "refs/remotes/origin/" + name) or verified(path, "refs/heads/" + name):
            return name
    return "main"


def landing_ref(path: str = ".", remote: str = "origin") -> str | None:
    """The ref "landed" counts against: <remote>/<landing branch> as last fetched, else the local
    landing branch in a repository without that remote-tracking branch; None when neither is."""
    branch = landing_branch(path)
    for ref in (f"refs/remotes/{remote}/{branch}", f"refs/heads/{branch}"):
        if verified(path, ref):
            return ref
    return None


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


def gh_json(gh: list[str], *args: str):
    """(status, JSON) of a gh call; status 200 on success, else the HTTP status gh reports (0
    when it reports none). Raises Unknown when gh cannot run or answers no JSON at all."""
    try:
        r = subprocess.run(gh + list(args), stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unknown(f"gh {' '.join(args[:2])}: {e}")
    try:
        body = json.loads(r.stdout) if r.stdout.strip() else None
    except ValueError:
        body = None
    if r.returncode == 0:
        if body is None:
            raise Unknown(f"gh {' '.join(args[:2])} answered no JSON")
        return 200, body
    m = re.search(r"\(HTTP (\d{3})\)", r.stderr)
    if not m and body is None:
        raise Unknown(f"gh {' '.join(args[:2])}: {r.stderr.strip()[:200] or 'failed'}")
    return (int(m.group(1)) if m else 0), body


def message(body) -> str:
    return str(body.get("message", "")) if isinstance(body, dict) else ""


def server_requires(gh, repo: str, branch: str, checks: list) -> bool:
    """Rule 3. True when GitHub would reject a direct push to the landing branch."""
    status, body = gh_json(gh, "api", f"repos/{repo}/rules/branches/{branch}")
    if status == 200 and isinstance(body, list):
        types = sorted({str(r.get("type")) for r in body if isinstance(r, dict)})
        forbidding = [t for t in types if t in PUSH_RULES or t not in HARMLESS_RULES]
        checks.append(f"rulesets on {branch}: {', '.join(types) or 'none'}"
                      + (f" ({', '.join(forbidding)} forbids a direct push)" if forbidding else ""))
        if forbidding:
            return True
    elif status == 403 and PLAN_LIMIT in message(body).lower():
        checks.append("rulesets: not available on this plan (HTTP 403): no protection possible")
    else:
        raise Unknown(f"rulesets: HTTP {status} {message(body)}".strip())

    status, body = gh_json(gh, "api", f"repos/{repo}/branches/{branch}/protection")
    if status == 200 and isinstance(body, dict):
        reasons = []
        if body.get("required_pull_request_reviews"):
            reasons.append("required reviews")
        checks_cfg = body.get("required_status_checks") or {}
        if checks_cfg.get("contexts") or checks_cfg.get("checks"):
            reasons.append("required status checks")
        if body.get("restrictions"):
            reasons.append("push restrictions")
        if (body.get("lock_branch") or {}).get("enabled"):
            reasons.append("locked branch")
        checks.append(f"branch protection on {branch}: " + (", ".join(reasons) or
                                                            "nothing that forbids a direct push"))
        return bool(reasons)
    if status == 403 and PLAN_LIMIT in message(body).lower():
        checks.append("branch protection: not available on this plan (HTTP 403): "
                      "no protection possible")
        return False
    if status == 404 and "not protected" in message(body).lower():
        checks.append(f"branch protection on {branch}: none")
        return False
    # Without admin rights the protection itself is unreadable; the branch still says whether
    # it is protected, and an unreadable protection counts as requiring.
    status2, body2 = gh_json(gh, "api", f"repos/{repo}/branches/{branch}")
    if status2 == 200 and isinstance(body2, dict):
        protected = bool(body2.get("protected"))
        checks.append(f"branch protection on {branch}: unreadable (HTTP {status}), "
                      + ("branch is protected" if protected else "branch is not protected"))
        return protected
    raise Unknown(f"branch protection: HTTP {status} {message(body)}; "
                  f"branch: HTTP {status2} {message(body2)}".strip())


def team_signal(gh, path: str, repo: str, branch: str, ref: str | None, checks: list) -> bool:
    """Rule 4. True when the repository is worked on by a team."""
    status, info = gh_json(gh, "api", f"repos/{repo}")
    if status != 200 or not isinstance(info, dict):
        raise Unknown(f"repository: HTTP {status} {message(info)}".strip())
    owner = str((info.get("owner") or {}).get("type", ""))
    checks.append(f"owner: {owner or 'unknown'}")
    if owner != "User":
        return True
    can_push = bool((info.get("permissions") or {}).get("push"))
    checks.append(f"your push permission: {'yes' if can_push else 'no'}")
    if not can_push:
        return True

    status, people = gh_json(gh, "api", f"repos/{repo}/collaborators?per_page=100")
    if status != 200 or not isinstance(people, list):
        raise Unknown(f"collaborators: HTTP {status} {message(people)}".strip())
    writers = sorted(str(p.get("login")) for p in people
                     if isinstance(p, dict) and (p.get("permissions") or {}).get("push"))
    checks.append(f"collaborators with write access: {len(writers)} ({', '.join(writers)})")
    if len(writers) > 1:
        return True

    found = [p for p in CODEOWNERS if ref and git(path, "cat-file", "-e", f"{ref}:{p}")
             .returncode == 0]
    checks.append(f"CODEOWNERS on {branch}: {', '.join(found) or 'none'}"
                  + ("" if ref else " (landing branch not fetched)"))
    if found:
        return True

    status, me = gh_json(gh, "api", "user")
    login = me.get("login") if status == 200 and isinstance(me, dict) else None
    if not login:
        raise Unknown(f"signed-in user: HTTP {status} {message(me)}".strip())
    status, pulls = gh_json(gh, "pr", "list", "-R", repo, "--state", "merged", "--base", branch,
                            "--limit", "50", "--json", "author,mergedAt")
    if status != 200 or not isinstance(pulls, list):
        raise Unknown(f"merged pull requests: HTTP {status} {message(pulls)}".strip())
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=RECENT_DAYS)
    others = set()
    for p in pulls:
        author = (p or {}).get("author") or {}
        who = str(author.get("login") or "")
        merged = str((p or {}).get("mergedAt") or "")
        try:
            when = datetime.datetime.fromisoformat(merged.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when >= since and who and who.lower() != login.lower() and not author.get("is_bot") \
                and not who.startswith("app/") and not who.endswith("[bot]"):
            others.add(who)
    checks.append(f"pull requests merged by others in {RECENT_DAYS} days: "
                  + (", ".join(sorted(others)) or "none"))
    return bool(others)


def decide(path: str = ".") -> tuple[str, str, list]:
    """(mode, landing branch, check lines). Raises SettingError for a usage problem."""
    text = settings_text(path)
    branch = landing_branch(path)
    checks: list = []
    setting = (row(text, "landing") or "auto").lower()
    checks.append(f"setting `landing`: {setting}" + ("" if row(text, "landing") else " (no row)"))
    if setting not in (PR, LOCAL, "auto"):
        checks.append(f"unknown value {setting!r}: the safe default")
        return PR, branch, checks
    if setting == PR:
        return PR, branch, checks

    url = out(path, "remote", "get-url", "origin")
    if not url:
        checks.append("remote origin: none, so no server to open a pull request on")
        return LOCAL, branch, checks
    m = GITHUB_URL.match(url)
    if not m:
        if setting == LOCAL:
            checks.append("remote origin: not on github.com, server not checked: the setting "
                          "holds, and a push the server rejects stops there")
            return LOCAL, branch, checks
        checks.append("remote origin: not on github.com: unknown, the safe default")
        return PR, branch, checks
    repo = f"{m.group(1)}/{m.group(2)}"
    checks.append(f"remote origin: github.com/{repo}")
    gh = gh_command()
    try:
        if gh is None:
            raise Unknown("gh is not installed")
        if server_requires(gh, repo, branch, checks):
            if setting == LOCAL:
                checks.append("the server requires pull requests, which overrules the setting")
            return PR, branch, checks
        if setting == LOCAL:
            return LOCAL, branch, checks
        ref = f"refs/remotes/origin/{branch}" if verified(path, f"refs/remotes/origin/{branch}") \
            else None
        if team_signal(gh, path, repo, branch, ref, checks):
            return PR, branch, checks
    except Unknown as e:
        if setting == LOCAL:
            checks.append(f"server not checked ({e}): the setting holds, and a push the server "
                          "rejects stops there")
            return LOCAL, branch, checks
        checks.append(f"unknown: {e}: the safe default")
        return PR, branch, checks
    return LOCAL, branch, checks


def main(argv: list) -> int:
    path, branch_only, i = ".", False, 0
    while i < len(argv):
        if argv[i] == "-C" and i + 1 < len(argv):
            path, i = argv[i + 1], i + 2
            continue
        if argv[i] == "--branch":
            branch_only = True
        elif argv[i] in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(__doc__, file=sys.stderr)
            return 2
        i += 1
    try:
        if branch_only:
            print(landing_branch(path))
            return 0
        mode, branch, checks = decide(path)
    except SettingError as e:
        print(f"landing: error: {e}", file=sys.stderr)
        return 2
    for line in checks:
        print(f"check: {line}")
    print(f"landing branch: {branch}")
    print(f"landing: {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
