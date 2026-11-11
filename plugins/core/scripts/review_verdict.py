#!/usr/bin/env python3
"""Write, post and read the review verdict on a pull request: the one owner of its format.

Usage: python3 review_verdict.py head <n>
       python3 review_verdict.py approve <n> --sha <sha> --agent "<agent>" [--note "<text>"]
       python3 review_verdict.py findings <n> --sha <sha> --agent "<agent>" --body-file <file|->
       python3 review_verdict.py check --body-file <file|->
       each with [--dry-run] [-C <checkout>] [-R <owner>/<repo>]

The review-change skill runs it in the reviewing session; merge_pr.py (beside this file) reads
review comments through verdict() here, so the comment the reviewer posts and the comment the
merge accepts cannot drift apart. The format, as GitHub stores the comment body:

  approval  🤖 <agent> (review): Approved <40-hex head SHA>
            [blank line, then a note]
  findings  🤖 <agent> (review): Findings at <40-hex head SHA>
            <blank line, then the findings>

verdict() accepts what merge_pr.py has always accepted, so reviews posted before this script
stay valid: the signature `🤖 <agent> (<role>):` with the role `review` or `reviewer`, then text
opening with `Approved` and 7 to 40 hex digits (in backticks or bold, with a colon, allowed).
This script writes only the strict form above: the full SHA, never a prefix.

  head      prints the pull request's head SHA. Run it before the review: that is the commit
            to review.
  approve   posts the approval of --sha. Refused (exit 1) unless --sha is the full head SHA of
            the open pull request at the moment of posting; after posting it reads the head
            again and exits 1 if it moved meanwhile (the approval then covers --sha only, and
            merge_pr.py treats it so).
  findings  posts the findings from --body-file (`-` reads stdin) for --sha, which must be the
            head too. A findings comment never approves, whatever its text says.
  check     reads a comment body and prints `approves <sha>` (exit 0) or why it does not
            (exit 1): what merge_pr.py will make of it.

--dry-run prints the comment body on stdout, exactly as it would be posted, and posts nothing
(it still checks the head). -R must name the same repository as origin; without it, origin on
github.com. AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command (tests use it). Exit
0 posted (or printed), 1 refused with the reason on stderr, 2 usage error or unreadable state.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from landing import GITHUB_URL, gh_command  # noqa: E402

ROBOT = "\N{ROBOT FACE}"
ROLE = "review"
REVIEW_ROLES = {"review", "reviewer"}
SIGNED = re.compile(r"\A\s*\N{ROBOT FACE}\s*[^\n(]*\(([^)\n]*)\):\s*(?:\*\*)?(.*)", re.S)
APPROVED = re.compile(r"\Aapproved(?:\*\*)?\s*:?\s*`?([0-9a-f]{7,40})`?(?=[\s.,;:)]|$)", re.I)
FULL_SHA = re.compile(r"\A[0-9a-f]{40}\Z")
AGENT = re.compile(r"\A[^\n()]{1,60}\Z")


def verdict(body: str | None) -> tuple | None:
    """None when <body> is not a comment signed with a review role; else (the approved SHA or
    prefix, lower case, or None when it does not approve; the text after the signature)."""
    m = SIGNED.match(body or "")
    if not m or m.group(1).strip().lower() not in REVIEW_ROLES:
        return None
    text = m.group(2).strip()
    a = APPROVED.match(text)
    return (a.group(1).lower() if a else None), text


def approved_sha(body: str | None) -> str | None:
    v = verdict(body)
    return v[0] if v else None


def _signature(agent: str, sha: str) -> str:
    agent = (agent or "").strip()
    if not AGENT.match(agent):
        raise ValueError(f"agent {agent!r}: 1 to 60 characters, no parenthesis, one line")
    if not FULL_SHA.match(sha or ""):
        raise ValueError(f"sha {sha!r}: the full 40-character commit SHA, lower case")
    return f"{ROBOT} {agent} ({ROLE}): "


def approval(agent: str, sha: str, note: str = "") -> str:
    body = _signature(agent, sha) + f"Approved {sha}\n"
    note = (note or "").strip()
    return body + (f"\n{note}\n" if note else "")


def findings(agent: str, sha: str, text: str) -> str:
    head = _signature(agent, sha)
    text = (text or "").strip()
    if not text:
        raise ValueError("no findings given: an empty findings comment says nothing")
    return head + f"Findings at {sha}\n\n{text}\n"


def git(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", path, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def gh(command: list, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command + list(args), input=stdin,
                          stdin=None if stdin is not None else subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=120)


def view(command: list, repo: str, number: str) -> dict | None:
    r = gh(command, "pr", "view", number, "-R", repo, "--json", "number,state,headRefOid")
    try:
        pr = json.loads(r.stdout) if r.returncode == 0 else None
    except ValueError:
        pr = None
    if not isinstance(pr, dict) or not FULL_SHA.match(str(pr.get("headRefOid") or "").lower()):
        print(f"review_verdict: cannot read pull request {number}: {r.stderr.strip()[:200]}",
              file=sys.stderr)
        return None
    return pr


def read_body(path: str) -> str | None:
    try:
        if path == "-":
            return sys.stdin.read()
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print(f"review_verdict: cannot read {path}: {e}", file=sys.stderr)
        return None


def usage() -> int:
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


def main(argv: list) -> int:
    try:
        sys.stdout.reconfigure(errors="replace", newline="\n")
        sys.stderr.reconfigure(errors="replace")
    except AttributeError:
        pass
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    opts = {"--sha": None, "--agent": None, "--note": "", "--body-file": None, "-C": ".",
            "-R": None}
    words, dry, i = [], False, 0
    while i < len(argv):
        a = argv[i]
        if a in opts:
            if i + 1 >= len(argv):
                return usage()
            opts[a] = argv[i + 1]
            i += 2
            continue
        if a == "--dry-run":
            dry = True
        elif a.startswith("-") and a != "-":
            return usage()
        else:
            words.append(a)
        i += 1
    action = words[0] if words else None

    if action == "check":
        if len(words) != 1 or opts["--body-file"] is None:
            return usage()
        body = read_body(opts["--body-file"])
        if body is None:
            return 2
        v = verdict(body)
        if v is None:
            print("not a signed review: it must open with `🤖 <agent> (review):`")
            return 1
        if v[0] is None:
            print(f"does not approve: {v[1][:80]!r}")
            return 1
        print(f"approves {v[0]}")
        return 0

    if action not in ("head", "approve", "findings") or len(words) != 2 \
            or not words[1].isdigit():
        return usage()
    number = words[1]
    text = None
    if action != "head":
        if not opts["--sha"] or not opts["--agent"]:
            return usage()
        if action == "findings":
            if opts["--body-file"] is None:
                return usage()
            text = read_body(opts["--body-file"])
            if text is None:
                return 2
        try:
            body = (approval(opts["--agent"], opts["--sha"], opts["--note"]) if action == "approve"
                    else findings(opts["--agent"], opts["--sha"], text))
        except ValueError as e:
            print(f"review_verdict: {e}", file=sys.stderr)
            return 2

    command = gh_command()
    path, repo = opts["-C"], opts["-R"]
    m = GITHUB_URL.match(git(path, "remote", "get-url", "origin").stdout.strip())
    origin_repo = f"{m.group(1)}/{m.group(2)}" if m else None
    if repo and origin_repo and repo.lower() != origin_repo.lower():
        print(f"review_verdict: -R {repo} is not origin's repository {origin_repo}",
              file=sys.stderr)
        return 2
    repo = repo or origin_repo
    if command is None or not repo:
        print("review_verdict: needs gh, and an origin on github.com or -R <owner>/<repo>",
              file=sys.stderr)
        return 2

    pr = view(command, repo, number)
    if pr is None:
        return 2
    head = str(pr["headRefOid"]).lower()
    if action == "head":
        print(head)
        return 0
    sha = opts["--sha"]
    if pr.get("state") != "OPEN":
        print(f"review_verdict: #{number} is {pr.get('state')}, not open: nothing to review",
              file=sys.stderr)
        return 1
    if sha != head:
        print(f"review_verdict: the head of #{number} is {head}, not {sha}: review the commits "
              f"since then and post for the head", file=sys.stderr)
        return 1
    if dry:
        sys.stdout.write(body)
        return 0
    r = gh(command, "pr", "comment", number, "-R", repo, "--body-file", "-", stdin=body)
    if r.returncode != 0:
        print(f"review_verdict: posting failed: {(r.stderr or r.stdout).strip()[:300]}",
              file=sys.stderr)
        return 2
    print(f"review_verdict: posted the {action} of {sha[:10]} on #{number}: "
          f"{r.stdout.strip()[:200]}")
    after = view(command, repo, number)
    if after is None:
        return 2
    if str(after["headRefOid"]).lower() != sha:
        print(f"review_verdict: the head of #{number} moved to {after['headRefOid']} while "
              f"posting: the comment covers {sha[:10]} only; review the new commits",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
