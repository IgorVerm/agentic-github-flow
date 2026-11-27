#!/usr/bin/env python3
"""Run a repository's fast or full check and keep a local record of it.

Usage: python3 verify.py [-C <checkout>] fast|full

The `verify` skill runs it while working and before every push. It reads the row `fast` or
`full` of the `## Verification` section of HANDOFF.md as the default branch holds it, as last
fetched (`refs/remotes/origin/HEAD`, else origin/main or origin/master, else local main or
master: the order of settings_text() in landing.py), never from the working tree or the branch,
so a change cannot rewrite the command it is judged by. It does not fetch.

The value cell holds the command in backticks; several code spans (`a`, `b`) are run one after
another, from the checkout's top folder, through the shell, stopping at the first that fails; a
cell without backticks is one command. `\\|` in the cell is a pipe. A missing section, a
missing row, or a row whose value is `none` is refused with exit 2 and nothing is run or
recorded: the `verify` skill's `writing-the-section.md` says how to write the section.

`fast` gets what changed, for its command to select by (the selection belongs to the command;
a path it does not know runs everything): VERIFY_BASE is the merge base of HEAD and the
default branch, and VERIFY_CHANGED names a file listing the changed paths one per line,
relative to the top folder, sorted: committed since VERIFY_BASE, staged, unstaged and untracked
but not ignored, deleted ones included. The file is removed after the run. A command that
ignores both selects by itself. `full` gets neither.

Every run appends one line to the record, `verify-record.tsv` in the git common directory
(shared by all worktrees of the repository, never committed; record_path() gives it), under a
header line starting with `#`. Tab-separated: the date (UTC, `YYYY-MM-DDTHH:MM:SSZ`), the
branch (`detached <sha>` without one), `fast` or `full`, the seconds, `passed` or `failed:
exit <n>: <the last line of output>` (`failed: interrupted` on Ctrl-C), and the command
(several joined by ` && `). Tabs and line breaks in a field become spaces. The record measures
how long the checks take and what they caught before a push; it decides nothing.

Output of the command passes through. Exit 0 when it passed, 1 when it failed, 130 when
interrupted, 2 for a usage error, a checkout outside git, or no command to run.
"""
from __future__ import annotations

import datetime
import os
import re
import subprocess
import sys
import tempfile
import time

SECTION = re.compile(r"^## Verification[ \t]*$(.*?)(?=^## |\Z)", re.M | re.S)
RECORD = "verify-record.tsv"
HEADER = "# date\tbranch\tcheck\tseconds\tresult\tcommand\n"
KINDS = ("fast", "full")
USAGE = "usage: verify.py [-C <checkout>] fast|full"


class Refused(Exception):
    """Nothing can be run: exit 2 with this message."""


def git(path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", path, *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def out(path: str, *args: str) -> str | None:
    r = git(path, *args)
    return r.stdout.strip() if r.returncode == 0 else None


def default_ref(path: str) -> str | None:
    """The default branch as last fetched; the order of landing.settings_text()."""
    head = out(path, "symbolic-ref", "-q", "refs/remotes/origin/HEAD") or ""
    for ref in (head, "refs/remotes/origin/main", "refs/remotes/origin/master",
                "refs/heads/main", "refs/heads/master"):
        if ref and git(path, "rev-parse", "-q", "--verify", ref + "^{commit}").returncode == 0:
            return ref
    return None


def cells(line: str) -> list:
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip()[1:])]


def commands(text: str | None, kind: str) -> list:
    """The commands of the row <kind> of `## Verification`; Refused when there are none."""
    sec = SECTION.search(text or "")
    if not sec:
        raise Refused("HANDOFF.md on the default branch has no `## Verification` section; "
                      "the verify skill's writing-the-section.md says how to write it")
    for line in sec.group(1).splitlines():
        if not line.strip().startswith("|"):
            continue
        row = cells(line)
        if len(row) >= 2 and row[0].replace("`", "").strip().lower() == kind:
            value = row[1]
            spans = [s.strip() for s in re.findall(r"`([^`]+)`", value) if s.strip()]
            found = spans or ([value] if value else [])
            if found and found[0].lower() not in ("none", "-"):
                return found
            break
    raise Refused(f"the `## Verification` section on the default branch has no command in "
                  f"its `{kind}` row")


def record_path(path: str = ".") -> str | None:
    common = out(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.join(common, RECORD) if common else None


def branch_name(path: str) -> str:
    name = out(path, "branch", "--show-current")
    if name:
        return name
    return "detached " + (out(path, "rev-parse", "--short", "HEAD") or "?")


def changed_paths(top: str, base: str) -> list:
    tracked = git(top, "diff", "--name-only", "-z", "--no-renames", base)
    untracked = git(top, "ls-files", "-z", "--others", "--exclude-standard")
    return sorted({p for r in (tracked, untracked) for p in r.stdout.split("\0") if p})


def flat(text: str) -> str:
    return re.sub(r"[\t\r\n]+", " ", text).strip()


def append_record(path: str, fields: list) -> None:
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        if new:
            f.write(HEADER)
        f.write("\t".join(flat(str(x)) for x in fields) + "\n")


def run(command: str, top: str, env: dict) -> tuple:
    """Run one command, its output passing through; (exit code, last line of output)."""
    last = ""
    proc = subprocess.Popen(command, shell=True, cwd=top, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if line.strip():
                last = line.strip()
        return proc.wait(), last
    except KeyboardInterrupt:
        proc.kill()
        proc.wait()
        raise


def main(argv: list) -> int:
    path = "."
    if len(argv) >= 2 and argv[0] == "-C":
        path, argv = argv[1], argv[2:]
    if len(argv) != 1 or argv[0] not in KINDS:
        print(USAGE, file=sys.stderr)
        return 2
    kind = argv[0]
    try:
        top = out(path, "rev-parse", "--show-toplevel")
        if top is None:
            raise Refused(f"{path} is not in a git repository")
        ref = default_ref(top)
        if ref is None:
            raise Refused("no default branch found (origin/HEAD, origin/main, origin/master, "
                          "main or master)")
        found = commands(out(top, "show", f"{ref}:HANDOFF.md"), kind)
    except Refused as e:
        print(f"verify.py: {e}", file=sys.stderr)
        return 2
    command = " && ".join(found)
    env = dict(os.environ)
    env.pop("VERIFY_CHANGED", None)
    env.pop("VERIFY_BASE", None)
    listing = None
    short = ref.replace("refs/remotes/", "").replace("refs/heads/", "")
    print(f"verify: {kind} from {short}:HANDOFF.md: {command}", flush=True)
    if kind == "fast":
        base = out(top, "merge-base", "HEAD", ref) or out(top, "rev-parse", ref)
        paths = changed_paths(top, base)
        fd, listing = tempfile.mkstemp(prefix="verify-changed-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(p + "\n" for p in paths))
        env["VERIFY_BASE"], env["VERIFY_CHANGED"] = base, listing
        print(f"verify: {len(paths)} changed paths since {base[:12]}", flush=True)
    started = time.monotonic()
    result, code = "passed", 0
    try:
        for one in found:
            status, last = run(one, top, env)
            if status != 0:
                result = f"failed: exit {status}" + (f": {last[:200]}" if last else "")
                code = 1
                break
    except KeyboardInterrupt:
        result, code = "failed: interrupted", 130
    finally:
        if listing:
            os.unlink(listing)
    seconds = time.monotonic() - started
    date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = record_path(top)
    append_record(record, [date, branch_name(top), kind, f"{seconds:.1f}", result, command])
    print(f"verify: {kind} {result} in {seconds:.1f}s (recorded in {record})", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
