#!/usr/bin/env python3
"""Push an agent's own task branch without asking, and open its pull request, where a standing
grant allows it and every check holds.

Usage: python3 push_branch.py --grant "<where the grant is written>"
                              [--title "<title>" --body-file <file> [--draft]]
                              [--dry-run] [-C <checkout>] [-R <owner>/<repo>]

Every push is the user's word (the core rules), except the push of an agent's own task branch in
pull-request mode where a standing grant allows it: the repository's HANDOFF.md §Standing
permissions or an overlay the user installed. In pull-request mode a task branch enters the
default branch only through a merge, so its push publishes but integrates nothing; what a push
cannot take back (a secret, personal data) and what changes what later sessions may do (CI
workflows, hooks, permission settings, the installer, the rules) is checked first. This script is
how an agent uses such a grant: --grant names where it is written, and is printed with the
result. It pushes the branch checked out in <checkout> only when all hold:

  ref       a branch is checked out, and it is not main, master, the remote's default branch or
            the landing branch; origin's copy of it, if any, is in HEAD (a fast-forward: no
            force, no deletion, no tag);
  mode      landing.py (beside this file) decides pull request for the repository; in local-main
            mode the push of the landing branch is the integration and stays the user's word;
  hook      the agentic-github-flow pre-push hook (templates/pre-push) is installed where git runs
            it (core.hooksPath, else the repository's hooks folder), so the secret scan and the
            personal-data check run on every outgoing commit and fail closed;
  paths     no outgoing commit (HEAD, not in origin's branches as fetched) changes a path that
            leaves only on the user's word: push_paths.py (beside this file, the paths of
            merge_pr.py) decides, here and again in the hook, which this script runs with
            AGENTIC_GITHUB_FLOW_UNASKED_PUSH=1;
  overlap   the pull request body holds the overlap check's result, a line starting with
            `Overlap` (the ship-change skill's step 5): the open pull request's body, or, when
            none is open for the branch, --body-file, which then needs --title as well.

Then `git push origin refs/heads/<branch>:refs/heads/<branch>` (no -u, never --no-verify), and,
when no pull request is open for the branch, `gh pr create --base <landing> --head <branch>
--title <title> --body-file <file>` (--draft passed on). A refusal by the hook is a refusal of
this script. A bare `git push` stays an ask rule in the guards; this script is the one route
around it. -R must name the same repository as origin (it exists for a checkout whose origin is
not on github.com, as in the tests). AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh`
command. Exit 0 pushed (and the pull request open; with --dry-run, would push), 1 refused with
every reason printed (ask the user), 2 usage error or unreadable state.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from landing import PR, GITHUB_URL, SettingError, decide, gh_command  # noqa: E402
from merge_pr import OVERLAP  # noqa: E402
from push_paths import held  # noqa: E402

HOOK_MARKS = ("agentic-github-flow pre-push hook", "AGENTIC_GITHUB_FLOW_UNASKED_PUSH")


def git(path: str, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", path, *args], stdin=subprocess.DEVNULL, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def gh(command: list, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(command + list(args), stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def hook_reason(path: str, top: str) -> str | None:
    """None when git runs the agentic-github-flow pre-push hook in <path>; else the reason."""
    hooks = git(path, "config", "core.hooksPath").stdout.strip()
    if hooks:
        hooks = os.path.join(top, os.path.expanduser(hooks))
    else:
        hooks = git(path, "rev-parse", "--git-path", "hooks").stdout.strip()
        hooks = hooks if os.path.isabs(hooks) else os.path.join(path, hooks)
    hook = os.path.join(hooks, "pre-push")
    try:
        with open(hook, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return f"no pre-push hook at {hook}: install templates/pre-push first"
    if not all(m in text for m in HOOK_MARKS):
        return f"{hook} is not the agentic-github-flow pre-push hook with the protected-path check"
    if os.name != "nt" and not os.access(hook, os.X_OK):
        return f"{hook} is not executable, so git skips it"
    return None


def open_pr(command: list, repo: str, branch: str) -> tuple:
    """(the open pull request of <branch> as a dict, or None; an error text or None)."""
    r = gh(command, "pr", "list", "-R", repo, "--head", branch, "--state", "open", "--json",
           "number,url,body,baseRefName")
    try:
        found = json.loads(r.stdout) if r.returncode == 0 else None
    except ValueError:
        found = None
    if not isinstance(found, list):
        return None, f"cannot list the pull requests of {branch}: {r.stderr.strip()[:200]}"
    return (found[0] if found and isinstance(found[0], dict) else None), None


def main(argv: list) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except AttributeError:
        pass
    grant, title, body_file, draft, dry, path, repo, i = "", "", "", False, False, ".", None, 0
    while i < len(argv):
        a = argv[i]
        if a in ("--grant", "--title", "--body-file", "-C", "-R") and i + 1 < len(argv) \
                and not argv[i + 1].startswith("-"):
            value = argv[i + 1]
            if a == "--grant":
                grant = value
            elif a == "--title":
                title = value
            elif a == "--body-file":
                body_file = value
            elif a == "-R":
                repo = value
            else:
                path = value
            i += 2
            continue
        if a == "--dry-run":
            dry = True
        elif a == "--draft":
            draft = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(__doc__, file=sys.stderr)
            return 2
        i += 1
    if not grant.strip() or bool(title) != bool(body_file):
        print("push_branch: usage: push_branch.py --grant \"<where the grant is written>\" "
              "[--title \"<title>\" --body-file <file> [--draft]] [--dry-run]", file=sys.stderr)
        return 2
    body = ""
    if body_file:
        try:
            with open(body_file, encoding="utf-8") as f:
                body = f.read()
        except OSError as e:
            print(f"push_branch: cannot read {body_file}: {e}", file=sys.stderr)
            return 2

    top = git(path, "rev-parse", "--show-toplevel").stdout.strip()
    command = gh_command()
    m = GITHUB_URL.match(git(path, "remote", "get-url", "origin").stdout.strip())
    origin_repo = f"{m.group(1)}/{m.group(2)}" if m else None
    if repo and origin_repo and repo.lower() != origin_repo.lower():
        print(f"push_branch: -R {repo} is not origin's repository {origin_repo}", file=sys.stderr)
        return 2
    repo = repo or origin_repo
    if not top or command is None or not repo:
        print("push_branch: needs a git checkout, gh, and an origin on github.com or "
              "-R <owner>/<repo>", file=sys.stderr)
        return 2
    fetched = git(path, "fetch", "--quiet", "origin")
    if fetched.returncode != 0:
        print(f"push_branch: cannot fetch origin: {fetched.stderr.strip()[:200]}", file=sys.stderr)
        return 2
    try:
        mode, landing, _ = decide(path)
    except SettingError as e:
        print(f"push_branch: {e}", file=sys.stderr)
        return 2

    reasons = []
    branch = git(path, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    head = git(path, "rev-parse", "-q", "--verify", "HEAD^{commit}").stdout.strip()
    default = git(path, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").stdout
    default = default.strip()[len("origin/"):] if default.strip() else ""
    if not branch or not head:
        reasons.append("no branch is checked out (a detached HEAD or no commit)")
    elif branch.casefold() in {b.casefold() for b in ("main", "master", default, landing) if b}:
        reasons.append(f"{branch} is the default or landing branch, not a task branch")
    if mode != PR:
        reasons.append(f"the repository lands on {mode}, not through pull requests: the push of "
                       "the landing branch is the user's word")
    remote_tip = git(path, "rev-parse", "-q", "--verify",
                     f"refs/remotes/origin/{branch}^{{commit}}").stdout.strip() if branch else ""
    if remote_tip and head and git(path, "merge-base", "--is-ancestor", remote_tip,
                                   head).returncode != 0:
        reasons.append(f"origin/{branch} has commits HEAD lacks: merge it, never force")
    why = hook_reason(path, top)
    if why:
        reasons.append(why)
    if head:
        outgoing = git(path, "rev-list", head, "--not", "--remotes=origin")
        if outgoing.returncode != 0:
            reasons.append("cannot list the outgoing commits")
        else:
            try:
                found = held(top, outgoing.stdout.split())
            except (RuntimeError, SettingError, OSError) as e:
                found = []
                reasons.append(f"the protected-path check could not run: {e}")
            if found:
                reasons.append("paths that leave only on the user's word: " + ", ".join(
                    sorted({f"{p} ({c})" for p, c in found})[:8]))
    pr, error = open_pr(command, repo, branch) if branch else (None, None)
    if error:
        print(f"push_branch: {error}", file=sys.stderr)
        return 2
    if pr:
        if not OVERLAP.search(str(pr.get("body") or "")):
            reasons.append(f"pull request #{pr.get('number')} has no overlap check result in its "
                           "body (a line starting with `Overlap`)")
    elif not body_file:
        reasons.append("no pull request is open for the branch: pass --title and --body-file")
    elif not OVERLAP.search(body):
        reasons.append(f"{body_file} has no overlap check result (a line starting with `Overlap`)")

    print(f"push_branch: {branch or '(no branch)'} at {head[:10]} to {repo}, mode {mode}, "
          f"grant: {grant.strip()}")
    if reasons:
        for reason in reasons:
            print(f"push_branch: REFUSED: {reason}")
        return 1
    after = f"pull request #{pr.get('number')}" if pr else \
        f"open a {'draft ' if draft else ''}pull request into {landing}"
    if dry:
        print(f"push_branch: would push {branch} and {after}")
        return 0
    env = dict(os.environ, AGENTIC_GITHUB_FLOW_UNASKED_PUSH="1")
    pushed = git(path, "push", "origin", f"refs/heads/{branch}:refs/heads/{branch}", env=env)
    if pushed.returncode != 0:
        print("push_branch: REFUSED by the push (ask the user):")
        print("\n".join("  " + line for line in (pushed.stderr or pushed.stdout).strip()
                        .splitlines()[:30]))
        return 1
    if pr:
        print(f"push_branch: pushed {branch} at {head[:10]}; pull request #{pr.get('number')} "
              f"{pr.get('url') or ''}".rstrip())
        return 0
    args = ["pr", "create", "-R", repo, "--base", landing, "--head", branch, "--title", title,
            "--body-file", body_file] + (["--draft"] if draft else [])
    made = gh(command, *args)
    if made.returncode != 0:
        print(f"push_branch: pushed {branch} at {head[:10]}, but the pull request was not opened: "
              f"{(made.stderr or made.stdout).strip()[:300]}")
        return 1
    print(f"push_branch: pushed {branch} at {head[:10]}; opened {made.stdout.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
