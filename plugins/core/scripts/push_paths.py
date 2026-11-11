#!/usr/bin/env python3
"""Which outgoing commits change paths that leave only on the user's word: the push check of
templates/pre-push for a push that goes out without the user's yes.

Usage: python3 push_paths.py <repo> < object ids (one per line; the hook lists them)

The paths are the automatic merge's: merge_pr.py (beside this file) owns them, EXCLUDED and
the row `merge on the user's word` of HANDOFF.md's `## Landing settings` as the default branch
holds it, with its exception for a plugin manifest whose versions alone changed (MANIFESTS).
So CI workflows, hooks, permission settings (`.claude/settings*.json`), the installer and
`rules/core.md` still ask. Each commit is compared with its first parent, both sides of a rename
count; a merge (`--cc`) only with the paths it changes against every parent, so bringing the
default branch in is no change of its own. Annotated tags carry no paths and pass.

The pre-push hook runs this only when AGENTIC_GITHUB_FLOW_UNASKED_PUSH is set (not empty, not
`0`): the route that pushes without asking (#26) sets it, a push the user approved does not, so
the user's yes still covers such a change. Exit 0 none, 1 held (each printed as
`protected-path<TAB>path<TAB>commit`), 2 usage or git error. Reading is local.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from landing import SettingError, row, settings_text  # noqa: E402
from merge_pr import excluded, version_only  # noqa: E402

OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")


def git(repo: str, args: list, stdin: str = "") -> str:
    r = subprocess.run(["git", "-C", repo, *args], input=stdin, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("git: " + r.stderr.strip()[:200])
    return r.stdout


def held(repo: str, ids: list) -> list:
    """[(path, commit)] for the paths the outgoing commits change that leave on the user's word."""
    bad = [i for i in ids if not OBJECT_ID.fullmatch(i)]
    if bad:
        raise RuntimeError(f"not an object id: {bad[0][:80]!r}")
    commits = [line.split()[0] for line in git(
        repo, ["cat-file", "--batch-check=%(objectname) %(objecttype)"],
        "".join(i + "\n" for i in ids)).splitlines() if line.endswith(" commit")]
    if not commits:
        return []
    extra = [p for p in re.split(r"[,\s]+", row(settings_text(repo), "merge on the user's word")
                                 or "") if p]
    out = git(repo, ["-c", "core.quotePath=false", "-c", "diff.relative=false", "log",
                     "--no-walk=unsorted", "--stdin", "--cc", "--name-only", "--no-renames", "-z",
                     "--format=@@commit %H %P"], "".join(c + "\n" for c in commits))
    found, commit, parent = [], "", ""
    for field in out.split("\0"):  # paths unquoted; a newline may separate header and paths
        field = field[1:] if field.startswith("\n") else field
        if field.startswith("@@commit "):
            shas = field.split()[1:]
            commit, parent = shas[0], (shas[1] if len(shas) > 1 else "")
        elif field and commit and excluded(field, extra) and not (
                parent and version_only(repo, parent, commit, field)):
            found.append((field, commit[:12]))
    return found


def main(argv: list) -> int:
    if len(argv) != 1 or not os.path.isdir(argv[0]):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        ids = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]
        found = held(argv[0], ids)
    except (RuntimeError, SettingError, OSError) as e:
        print(f"push_paths: {e}", file=sys.stderr)
        return 2
    for path, commit in found:
        print(f"protected-path\t{path}\t{commit}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
