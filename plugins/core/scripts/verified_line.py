#!/usr/bin/env python3
"""Read the `Verified:` line of a landing: the one owner of its format.

Usage: python3 verified_line.py check --body-file <file|->

The author writes the line in the pull request body, or in the landing comment in local-main
mode (the ship-change skill's step 4; the verify skill says which evidence to choose); the
reviewer checks it (the review-change skill's step 4). One line per landing, never per commit:

  Verified: <kind>: <evidence>[; <kind>: <evidence>]...

The line starts at the beginning of a line of the body, outside a fenced code block, and the
body holds exactly one. The kinds, in lower case:

  goal            the issue's check was run and met. A script or patch made for it is named by
                  the URL of its comment on the issue (task_checks() lists those URLs).
  tests           existing checks ran and passed.
  standing-check  a check added to those that run on every change, for a critical system; its
                  evidence reads `<test> fails when <defect>`.
  run             the product or tool was run and its behaviour observed.
  seen            a screenshot or rendered result was looked at.
  none            nothing to run; the evidence is the reason, and it stands alone.

Several kinds are joined by `;`. A `;` that is not followed by a kind and a colon stays part of
the evidence. Every kind needs evidence after its colon.

A reviewer who finds the line's evidence not real, not fitting the change, or proving another
check than the issue's says so in a findings item that opens with `Verified line disputed:`
(disputed() finds it in a review comment; the report counts those).

  check   prints each kind and its evidence, and the task-check URLs, and exits 0; exits 1
          with the reason when the body has no line, more than one, or one that does not
          parse; exits 2 on a usage error or a body that is not UTF-8.

Body files and stdin are read as UTF-8. Offline: it reads only the body it is given.
"""
from __future__ import annotations

import re
import sys

KINDS = ("goal", "tests", "standing-check", "run", "seen", "none")
PREFIX = "Verified:"
FENCE = re.compile(r"\A\s{0,3}(`{3,}|~{3,})")
_KIND_ALT = "|".join(re.escape(k) for k in KINDS)
ITEM = re.compile(rf"\A({_KIND_ALT})\s*:\s*(.*)\Z", re.S)
SPLIT = re.compile(rf"\s*;\s*(?=(?:{_KIND_ALT})\s*:)")
COMMENT_URL = re.compile(
    r"https://github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+#issuecomment-\d+")
DISPUTED = re.compile(r"^\s*(?:\d+[.)]\s*)?(?:\*\*)?Verified line disputed:", re.M)


def lines(body: str | None) -> list:
    """The `Verified:` lines of <body> outside fenced code blocks, without the prefix."""
    found, fence = [], None
    for line in (body or "").splitlines():
        m = FENCE.match(line)
        if m:
            mark = m.group(1)
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
            continue
        if fence is None and line.startswith(PREFIX):
            found.append(line[len(PREFIX):].strip())
    return found


def parse_line(text: str) -> list:
    """[(kind, evidence), ...] for the text after `Verified:`; ValueError with the reason."""
    text = (text or "").strip()
    if not text:
        raise ValueError("the line is empty: write `Verified: <kind>: <evidence>`")
    items = []
    for part in SPLIT.split(text):
        m = ITEM.match(part.strip())
        if not m:
            head = part.strip().split(":", 1)[0][:40]
            raise ValueError(f"{head!r} is not a kind: one of {', '.join(KINDS)}, then a colon")
        kind, evidence = m.group(1), m.group(2).strip()
        if not evidence:
            what = "a reason" if kind == "none" else "evidence"
            raise ValueError(f"`{kind}:` needs {what} after the colon")
        if kind == "standing-check" and " fails when " not in f" {evidence} ":
            raise ValueError("`standing-check:` reads `<test> fails when <defect>`")
        items.append((kind, evidence))
    if len(items) > 1 and any(k == "none" for k, _ in items):
        raise ValueError("`none` stands alone: nothing was run, so no other kind can be given")
    return items


def parse(body: str | None) -> list:
    """The one `Verified:` line of <body>, parsed; ValueError when it is missing, doubled or
    does not parse."""
    found = lines(body)
    if not found:
        raise ValueError("no `Verified:` line: one per landing, at the start of a line")
    if len(found) > 1:
        raise ValueError(f"{len(found)} `Verified:` lines: one per landing")
    return parse_line(found[0])


def task_checks(items: list) -> list:
    """The issue-comment URLs the `goal` items name: the task checks a reviewer runs."""
    return [u for k, e in items if k == "goal" for u in COMMENT_URL.findall(e)]


def disputed(review: str | None) -> bool:
    """Whether a review comment disputes the line it reviewed."""
    return bool(DISPUTED.search(review or ""))


def read_body(path: str) -> str | None:
    try:
        if path == "-":
            return sys.stdin.buffer.read().decode("utf-8-sig")
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"verified_line: cannot read {path} as UTF-8: {e}", file=sys.stderr)
        return None


def main(argv: list) -> int:
    try:
        sys.stdout.reconfigure(errors="replace", newline="\n")
        sys.stderr.reconfigure(errors="replace")
    except AttributeError:
        pass
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    if len(argv) != 3 or argv[0] != "check" or argv[1] != "--body-file":
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 2
    body = read_body(argv[2])
    if body is None:
        return 2
    try:
        items = parse(body)
    except ValueError as e:
        print(f"verified_line: {e}", file=sys.stderr)
        return 1
    for kind, evidence in items:
        print(f"{kind}: {evidence}")
    for url in task_checks(items):
        print(f"task check: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
