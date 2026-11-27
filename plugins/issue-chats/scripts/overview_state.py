#!/usr/bin/env python3
"""The overview chat's state, read without its issue's thread (the method's §8, *The overview
chat*; skill issue-handover).

Usage: python3 overview_state.py [-C <checkout>] [-R <owner/repo>] [--issue <n>]

An overview chat keeps its state on a standing issue: the open issue with the overview label
(the settings row `overview label`, default `overview`) in the repository the row `overview
repository` names (default: the one <checkout> belongs to; another repository's when one
overview covers several). Read whole, such an issue floods a chat's context (Pax #223: 731
comments, 487,930 characters, measured 2026-11-27), so a chat never reads its thread: this tool
asks GitHub for the issue's newest 100 comments in one GraphQL call and prints only

  standing issue: <owner/repo>#<n> · <title>
  comments: <total>, rollover at 100
  rollover due                       (only from 100 comments on)
  claim (<time>): <the newest signed comment opening `claimed for chat`>
  state (<time>, <length> characters[, over the 1,500 the method allows]):
  <the newest signed comment opening `overview state:`>

each body cut at 4,000 characters, so what it prints stays bounded whatever the issue holds.
Signed: right after `🤖 <agent> (<role>):`, optionally in bold, as next_issue.py reads claims.
With --issue the label is not looked up. The settings are HANDOFF.md's `## Issue chats settings`
on the default branch as last fetched (next_issue.py owns how they are read); it does not fetch.

AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command (tests use it).
Exit 0 with the state; 1 no open standing issue, several, or no state comment among the newest
100 (the issue is overdue for its rollover, or the bootstrap of §8 has not posted one); 2 usage,
a bad setting or no default branch; 3 GitHub could not be read (inside the Claude Code sandbox gh
may be unreadable: run it outside the sandbox), nothing judged.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))  # -I leaves it off
from next_issue import (SettingError, Unread, gh, label_value, row_in,  # noqa: E402
                        settings_text)

ROLLOVER_AT = 100   # comments; the method's §8 owns the number
STATE_LIMIT = 1500  # characters a state comment may have (§8); longer is named, not refused
PRINT_CAP = 4000    # characters printed of any one comment
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SIGNED = r"\A\s*\N{ROBOT FACE}[^\n]*?\):\s*(?:\*\*)?"
STATE = re.compile(SIGNED + r"overview state:", re.I)
CLAIM = re.compile(SIGNED + r"claimed for chat\b", re.I)
QUERY = ("query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name)"
         "{issue(number:$number){number title state comments(last:%d){totalCount "
         "nodes{body createdAt}}}}}" % ROLLOVER_AT)


def repository(text: str | None, top: str, override: str | None) -> str:
    """owner/repo of the standing issue: -R, else the row `overview repository`, else origin's."""
    cell = override or row_in(text, "overview repository")
    if cell:
        value = cell.strip().strip("`").strip()
        if value.lower() not in ("", "here", "none") and \
                not value.lower().startswith("this repository"):
            if not REPO.fullmatch(value):
                raise SettingError(f"overview repository {cell!r} is not owner/repo")
            return value
    seen = gh(["repo", "view", "--json", "nameWithOwner"], top)
    name = seen.get("nameWithOwner") if isinstance(seen, dict) else None
    if not isinstance(name, str) or not REPO.fullmatch(name):
        raise Unread("gh repo view gave no nameWithOwner")
    return name


def standing_issue(repo: str, label: str, top: str) -> tuple[int | None, str]:
    """The one open issue with the overview label, or None and the reason."""
    found = gh(["issue", "list", "-R", repo, "--state", "open", "--label", label,
                "--limit", "10", "--json", "number,title"], top)
    if not isinstance(found, list):
        raise Unread("gh issue list gave no list")
    if not found:
        return None, (f"no open issue labelled {label!r} in {repo}: no overview runs there yet "
                      "(the bootstrap of the method's §8)")
    if len(found) > 1:
        numbers = ", ".join(f"#{i.get('number')}" for i in found)
        return None, (f"{len(found)} open issues labelled {label!r} in {repo} ({numbers}): a "
                      "rollover closes the old one; close all but the newest, or pass --issue")
    try:
        return int(found[0]["number"]), ""
    except (KeyError, TypeError, ValueError):
        raise Unread("gh issue list gave no issue number")


def newest(nodes: list[dict], mark: re.Pattern) -> dict | None:
    for node in reversed(nodes):
        if isinstance(node, dict) and mark.match(str(node.get("body") or "")):
            return node
    return None


def cut(body: str) -> str:
    body = body.strip()
    if len(body) <= PRINT_CAP:
        return body
    return body[:PRINT_CAP] + f"\n[cut at {PRINT_CAP} of {len(body)} characters]"


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="overview_state.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("-C", dest="path", default=".", help="a checkout of the repository")
    ap.add_argument("-R", dest="repo", help="owner/repo of the standing issue")
    ap.add_argument("--issue", type=int, help="the standing issue's number")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2
    try:
        top, text = settings_text(a.path)
        label = label_value(text, "overview label", "overview")
        if a.repo and not REPO.fullmatch(a.repo):
            raise SettingError(f"-R {a.repo!r} is not owner/repo")
    except SettingError as e:
        print(f"overview_state: {e}", file=sys.stderr)
        return 2
    try:
        repo = repository(text, top, a.repo)
        number = a.issue
        if number is None:
            number, why = standing_issue(repo, label, top)
            if number is None:
                print(f"overview_state: {why}", file=sys.stderr)
                return 1
        owner, name = repo.split("/")
        try:
            data = gh(["api", "graphql", "-f", f"query={QUERY}", "-f", f"owner={owner}",
                       "-f", f"name={name}", "-F", f"number={number}"], top)
        except Unread as e:
            if "Could not resolve to an Issue" not in str(e):
                raise
            data = None
        issue = (((data or {}).get("data") or {}).get("repository") or {}).get("issue") \
            if isinstance(data, dict) else None
        if data is None or (isinstance(data, dict) and isinstance(data.get("data"), dict)
                            and not issue):
            print(f"overview_state: no issue #{number} in {repo}", file=sys.stderr)
            return 1
        if not isinstance(issue, dict):
            raise Unread("gh api graphql gave no issue")
    except SettingError as e:
        print(f"overview_state: {e}", file=sys.stderr)
        return 2
    except Unread as e:
        print(f"overview_state: GitHub was not read: {e}", file=sys.stderr)
        return 3
    comments = issue.get("comments") or {}
    total = int(comments.get("totalCount") or 0)
    nodes = [n for n in comments.get("nodes") or [] if isinstance(n, dict)]
    print(f"standing issue: {repo}#{issue.get('number')} · {issue.get('title')}")
    if str(issue.get("state")).upper() != "OPEN":
        print(f"overview_state: #{number} is {str(issue.get('state')).lower()}: the rollover "
              "names its successor in its last comments", file=sys.stderr)
        return 1
    print(f"comments: {total}, rollover at {ROLLOVER_AT}")
    if total >= ROLLOVER_AT:
        print("rollover due")
    claim = newest(nodes, CLAIM)
    print(f"claim ({claim.get('createdAt')}): {cut(str(claim['body']))}" if claim
          else f"claim: none among the newest {ROLLOVER_AT} comments")
    state = newest(nodes, STATE)
    if not state:
        print(f"overview_state: no signed `overview state:` comment among the newest "
              f"{len(nodes)} comments of #{number}", file=sys.stderr)
        return 1
    body = str(state["body"])
    over = f", over the {STATE_LIMIT:,} the method allows" if len(body) > STATE_LIMIT else ""
    print(f"state ({state.get('createdAt')}, {len(body):,} characters{over}):")
    print(cut(body))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
