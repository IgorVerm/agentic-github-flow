#!/usr/bin/env python3
"""Which ready issue does a chain pick next? (skill issue-handover, *Pick the next issue*; the
method's settings section, *Spreading over areas*.)

Usage: python3 next_issue.py [-C <checkout>] [--area <label>] [--no-spread]

Prints the ready issues of the repository that <checkout> (default: the current directory)
belongs to, one `#<number> <title>` per line, in the order a chain picks them; the first line is
the pick unless the chat skips it (an open `after #n`, an overlap, open requirements). Ready:
open, the ready label, unassigned, without the requirements label (`agent-ready` and
`needs-spec`, the defaults the open-issue skill states, unless the settings rows `ready label`
and `requirements label` name others). The settings are the section `## Issue chats settings`
of `HANDOFF.md` on the default branch as last fetched (`refs/remotes/origin/HEAD`, else
origin/main, origin/master, else local main or master): a change to them counts once merged.
It does not fetch; fetch first.

The order: `priority: critical`, then `priority: high`, then the rest, oldest first. When the row
`spread over areas` says yes, the rest goes first from the areas no running chain works in yet:
an area is taken when an open issue with its label is assigned (the claim) and its newest claim
or hand-off comment, right after the signature `🤖 <agent> (<role>):`, is a claim (`claimed for
chat`), not `ready to push:` or `pull request opened:`. A chat whose branch waits for the push,
or whose pull request waits for review, no longer works in the area; its issue stays assigned
until the merge closes it. Critical and high stay first even in a taken area; an issue counts as
in a free area when it has one of the spread-over area labels and none of them is taken; then all
others, oldest first, so with every area taken the order is the normal one. An area without
ready work is simply absent. With `--area` (a chain limited to one area), `--no-spread`, or the
setting off, the order is the normal one. The taken and free areas go to stderr in one line.

AGENTIC_GITHUB_FLOW_GH, a JSON list, replaces the `gh` command (tests use it).
Exit 0 with the list (empty when nothing is ready); 2 usage, a bad setting or no default branch;
3 GitHub could not be read, or a list reached the cap of 1000: nothing was judged.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

LIMIT = "1000"
TICKED = re.compile(r"`([^`]+)`")
SECTION = re.compile(r"^## Issue chats settings[ \t]*$(.*?)(?=^## |\Z)", re.M | re.S)
# A claim or hand-off comment: the signature, then the fixed opening the skill issue-handover
# gives it (claim, ready to push, pull request opened), optionally in bold.
MARK = re.compile(r"\A\s*\N{ROBOT FACE}[^\n]*?\):\s*(?:\*\*)?"
                  r"(claimed for chat\b|ready to push:|pull request opened:)", re.IGNORECASE)


class Unread(Exception):
    pass


class SettingError(Exception):
    pass


def git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)


def settings_text(path: str) -> tuple[str, str | None]:
    """The checkout's top level and HANDOFF.md as the default branch holds it (None: no file)."""
    top = git(path, "rev-parse", "--show-toplevel")
    if top.returncode:
        raise SettingError(f"{path} is not in a git repository: {top.stderr.strip()}")
    head = git(path, "symbolic-ref", "-q", "refs/remotes/origin/HEAD").stdout.strip()
    for ref in (head, "refs/remotes/origin/main", "refs/remotes/origin/master",
                "refs/heads/main", "refs/heads/master"):
        if ref and git(path, "rev-parse", "-q", "--verify", ref + "^{commit}").returncode == 0:
            shown = git(path, "show", f"{ref}:HANDOFF.md")
            return top.stdout.strip(), shown.stdout if shown.returncode == 0 else None
    raise SettingError("no default branch found (origin/HEAD, origin/main, origin/master, or "
                       "local main or master): fetch first")


def row_in(text: str | None, name: str) -> str | None:
    """The raw value cell of the row <name> of the settings section, or None when absent."""
    sec = SECTION.search(text or "")
    if not sec:
        return None
    for line in sec.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0].lower() == name:
            return cells[1]
    return None


def label_value(text: str | None, name: str, default: str) -> str:
    """A one-label row (`ready label`, `requirements label`): its first `label`, else default."""
    cell = row_in(text, name)
    if not cell:
        return default
    ticked = TICKED.findall(cell)
    return (ticked[0] if ticked else cell).strip() or default


def spread_areas(text: str | None) -> list[str] | None:
    """The labels a pick spreads over, or None when `spread over areas` is absent or no.

    The value starts with yes or no; the labels in backticks after it, up to the first `;` (the
    rest is a comment), are the areas. Yes without labels spreads over the labels in backticks
    of the row `area labels`."""
    cell = row_in(text, "spread over areas")
    if cell is None:
        return None
    word = cell.replace("`", " ").split()
    head = word[0].lower().rstrip(":,;") if word else ""
    if head not in ("yes", "no"):
        raise SettingError(f"spread over areas {cell!r} does not start with yes or no")
    if head == "no":
        return None
    areas = [t.strip() for t in TICKED.findall(cell.split(";")[0])
             if t.strip().lower() not in ("yes", "no")]
    if not areas:
        areas = [t.strip() for t in TICKED.findall(row_in(text, "area labels") or "")]
    if not areas:
        raise SettingError("spread over areas is yes but names no area labels, "
                           "and the row `area labels` names none in backticks")
    return areas


def rank(issue: dict) -> int:
    names = {lab["name"] for lab in issue.get("labels", [])}
    return 0 if "priority: critical" in names else 1 if "priority: high" in names else 2


def normal_order(ready: list[dict]) -> list[dict]:
    """Critical, high, the rest; oldest first within each."""
    return sorted(ready, key=lambda i: (rank(i), i["number"]))


def handed_off(comments: list[dict]) -> bool:
    """Whether the newest claim or hand-off comment (oldest first in <comments>) is a hand-off:
    the branch is ready to push or its pull request is open, so no chat works there now."""
    last = None
    for c in comments:
        m = MARK.match(c.get("body") or "")
        if m:
            last = m.group(1).lower()
    return last is not None and not last.startswith("claimed")


def taken_areas(open_issues: list[dict], areas: list[str], cwd: str) -> set[str]:
    """The areas in which an open issue is assigned and not handed off: a chain works there."""
    taken = set()
    for issue in open_issues:
        mine = {lab["name"] for lab in issue.get("labels", [])} & set(areas)
        if not issue.get("assignees") or not mine or mine <= taken:
            continue
        comments = gh(["issue", "view", str(issue["number"]), "--json", "comments"], cwd)
        if not handed_off(comments.get("comments", []) if isinstance(comments, dict) else []):
            taken |= mine
    return taken


def spread_order(ready: list[dict], areas: list[str], taken: set[str]) -> list[dict]:
    """Critical and high first; then the rest in a free area; then all others."""
    def in_free_area(issue: dict) -> bool:
        mine = {lab["name"] for lab in issue.get("labels", [])} & set(areas)
        return bool(mine) and not (mine & taken)
    return sorted(ready, key=lambda i: (rank(i), 0 if rank(i) < 2 or in_free_area(i) else 1,
                                        i["number"]))


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


def gh(args: list[str], cwd: str):
    command = gh_command()
    if not command:
        raise Unread("gh is not installed")
    try:
        p = subprocess.run(command + args, cwd=cwd, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        raise Unread(str(e))
    if p.returncode:
        raise Unread((p.stderr or p.stdout).strip()[:200] or f"gh exit {p.returncode}")
    try:
        return json.loads(p.stdout or "[]")
    except ValueError as e:
        raise Unread(f"gh gave no JSON: {e}")


def search_label(label: str) -> str:
    return f'"{label}"' if re.search(r"[\s\"]", label) else label


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):  # a title the console code page lacks is no crash
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="next_issue.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("-C", dest="path", default=".", help="a checkout of the repository")
    ap.add_argument("--area", help="only issues with this area label (a chain limited to it)")
    ap.add_argument("--no-spread", action="store_true", help="the normal order, setting or not")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2
    try:
        top, text = settings_text(a.path)
        ready_label = label_value(text, "ready label", "agent-ready")
        spec_label = label_value(text, "requirements label", "needs-spec")
        areas = None if a.area or a.no_spread else spread_areas(text)
    except SettingError as e:
        print(f"next_issue: {e}", file=sys.stderr)
        return 2
    args = ["issue", "list", "--state", "open", "--label", ready_label,
            "--search", f"no:assignee -label:{search_label(spec_label)}",
            "--limit", LIMIT, "--json", "number,title,labels"]
    if a.area:
        args += ["--label", a.area]
    try:
        ready = gh(args, top)
        if not isinstance(ready, list):
            raise Unread("gh issue list gave no list")
        if len(ready) >= int(LIMIT):
            raise Unread(f"{LIMIT} or more ready issues: the list may be cut, the order unsure")
        if areas is None:
            order = normal_order(ready)
        else:
            open_issues = gh(["issue", "list", "--state", "open", "--assignee", "*",
                              "--limit", LIMIT, "--json", "number,labels,assignees"], top)
            if not isinstance(open_issues, list):
                raise Unread("gh issue list gave no list")
            if len(open_issues) >= int(LIMIT):
                raise Unread(f"{LIMIT} or more assigned issues: the list may be cut, "
                             "the taken areas unsure")
            taken = taken_areas(open_issues, areas, top)
            order = spread_order(ready, areas, taken)
            free = [x for x in areas if x not in taken and any(
                x in {lab["name"] for lab in i.get("labels", [])} for i in ready)]
            print(f"spread over areas: taken {', '.join(x for x in areas if x in taken) or '-'};"
                  f" free with ready work {', '.join(free) or '-'}", file=sys.stderr)
    except Unread as e:
        print(f"next_issue: GitHub was not read: {e}", file=sys.stderr)
        return 3
    for issue in order:
        print(f"#{issue['number']} {issue['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
