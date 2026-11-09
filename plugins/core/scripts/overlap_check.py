#!/usr/bin/env python3
"""Which unmerged work touches the same files?

Usage: python3 overlap_check.py [-C <checkout>] (--branch <name> | --paths <path>...)
                                [--issue <n>] [--days 14] [--base <ref>] [--no-github]

The ship-change skill runs it with the task branch (`--branch`) right before it proposes the
push; a chat that picks up an issue can run it with the paths the issue names (`--paths`, and
`--issue` the issue being picked). <base> is the default branch: `refs/remotes/origin/HEAD` as
last fetched (else origin/main, origin/master), or local main or master in a repository without
origin. "Unmerged" means not merged into <base>. It lists:

  - every local branch not merged into <base> whose diff against its merge base shares a path
    with the input (renames count on both sides), with its head, the issue its name or last
    commit subject names (for the candidate: its last commit that is not a merge), and how old
    its first unmerged and its newest commit are. A branch whose newest commit is older than
    --days is counted, not listed; a branch the candidate
    already contains is left out; a branch whose tip is the head of a pull request merged into
    <base> (a squash or rebase merge) is counted as merged. A branch of the same issue as
    --issue is reported as such: a second session on one issue;
  - every open pull request whose changed files share a path with the input, except the
    candidate's own and those whose head is a local branch judged above or contained in the
    candidate; a quiet branch's open pull request is still judged (GitHub lists the new
    path of a rename and at most 100 files of a pull request);
  - every open issue that is claimed (has an assignee) and whose body or comments name one of
    the input paths (the full path, or its file name when that is not a generic one such as
    __init__.py), except the --issue itself;
  - for each hit, the newest signed comment (starting with the robot sign) that contains
    "design note" or "design delta", else the newest signed comment, by its URL: read it.

It changes nothing and posts nothing: git reads, `gh issue list/view` and `gh pr list` only.
It does not fetch; fetch first for a current default branch. AGENTIC_GITHUB_FLOW_GH, a JSON
list, replaces the `gh` command (tests use it). Last line and exit code, for the caller:
  0  `none: ...`  no overlap (the GitHub part checked, or left out with --no-github)
  1  `overlaps: <n>`  hits listed above (the GitHub part checked, or left out with --no-github)
  2  `usage: ...` or `error: ...`  bad arguments, a git failure, a candidate without a merge
     base, or any unexpected failure; nothing was judged
  3  `unchecked: ...`  GitHub could not be read: pull requests and claims are unknown; any
     branch hits are listed above and count as for exit 1
"""
import argparse
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time

GENERIC = {
    "mod.rs", "lib.rs", "main.rs", "build.rs", "__init__.py", "README.md", "SKILL.md",
    "Cargo.toml", "package.json", "index.ts", "index.tsx", "index.js", "index.html",
    "settings.json", "config.toml", "Makefile",
}
NOTE = re.compile(r"design (note|delta)", re.I)
SIGN = "\N{ROBOT FACE}"
ISSUE_FIELDS = "number,title,url,assignees,body,comments"
PR_FIELDS = "number,title,url,headRefName,headRefOid,files,comments"


class Usage(Exception):
    pass


class GitHubError(Exception):
    pass


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)


def git(cwd, *args):
    p = run(["git", *args], cwd)
    if p.returncode != 0:
        raise Usage(f"error: git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def verified(cwd, ref):
    return run(["git", "rev-parse", "-q", "--verify", ref + "^{commit}"], cwd).returncode == 0


def default_base(cwd):
    """The default branch as a full ref, the way the other scripts of this plugin read it."""
    remotes = git(cwd, "remote").split()
    if "origin" in remotes:
        head = run(["git", "symbolic-ref", "-q", "refs/remotes/origin/HEAD"], cwd).stdout.strip()
        candidates = [head, "refs/remotes/origin/main", "refs/remotes/origin/master"]
    else:
        candidates = ["refs/heads/main", "refs/heads/master"]
    for ref in candidates:
        if ref and verified(cwd, ref):
            return ref
    raise Usage("error: no default branch found (origin/HEAD, origin/main, origin/master, "
                "or local main or master); fetch, or name it with --base")


def branch_name(ref):
    """The branch name GitHub knows a base ref by: refs/remotes/origin/main -> main."""
    for prefix in ("refs/remotes/origin/", "refs/heads/", "origin/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref


def changed(cwd, base, ref, strict=False):
    """Paths a branch changes against its merge base with base, both sides of a rename.
    No merge base: no paths, or with strict (the candidate) an error, since nothing is judged."""
    mb = run(["git", "merge-base", base, ref], cwd).stdout.split()
    if not mb:
        if strict:
            raise Usage(f"error: {ref} has no merge base with {base}; nothing was judged")
        return set()
    out = git(cwd, "diff", "--no-renames", "--name-only", "-z", mb[0], ref)
    return {p for p in out.split("\0") if p}


def issue_of(name, subject):
    m = re.search(r"(?:^|[/-])(\d{1,6})(?:-|$)", name) or re.search(r"\(#(\d+)\)\s*$", subject)
    return int(m.group(1)) if m else None


def ago(ts):
    days = (time.time() - ts) / 86400
    return f"{days:.0f}d" if days >= 1 else f"{days * 24:.0f}h"


def mentions(text, path):
    if re.search(r"(?<![\w.-])" + re.escape(path) + r"(?![\w-])", text):
        return True
    name = os.path.basename(path)
    if name == path or name in GENERIC:
        return False
    return re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", text) is not None


def contains(cwd, ancestor, descendant):
    return run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd).returncode == 0


def local_branches(cwd, base, paths, candidate, cand_sha, issue, days):
    """(hits, judged tips, stale count): local branches not merged into base."""
    cutoff = time.time() - days * 86400
    rows = git(cwd, "for-each-ref", "--no-merged", base, "--format",
               "%(refname:short)%00%(objectname)%00%(committerdate:unix)%00%(subject)",
               "refs/heads/").splitlines()
    hits, tips, stale = [], set(), 0
    for row in rows:
        name, sha, when, subject = (row.split("\0") + ["", "", "0", ""])[:4]
        if name == candidate or sha == cand_sha:
            continue
        if cand_sha and contains(cwd, sha, cand_sha):
            tips.add(sha)
            continue
        if int(when or 0) < cutoff:  # its open pull request, if any, is still judged
            stale += 1
            continue
        tips.add(sha)
        n = issue_of(name, subject)
        if issue is not None and n == issue:
            hits.append({"kind": "same", "name": name, "sha": sha, "issue": n,
                         "when": int(when)})
            continue
        shared = sorted(paths & changed(cwd, base, sha))
        if shared:
            first = git(cwd, "log", "--format=%ct", "--reverse", f"{base}..{sha}").split()
            hits.append({"kind": "branch", "name": name, "sha": sha, "issue": n,
                         "when": int(when), "first": int(first[0]) if first else None,
                         "shared": shared})
    return hits, tips, stale


def gh_command():
    raw = os.environ.get("AGENTIC_GITHUB_FLOW_GH")
    if raw:
        try:
            command = json.loads(raw)
        except ValueError:
            return None
        return command if isinstance(command, list) and command else None
    found = shutil.which("gh")
    return [found] if found else None


def gh(cwd, *args):
    command = gh_command()
    if not command:
        raise GitHubError("gh is not installed")
    try:
        p = run(command + list(args), cwd)
    except (OSError, subprocess.SubprocessError) as error:
        raise GitHubError(f"gh failed: {error}")
    if p.returncode != 0:
        raise GitHubError((p.stderr or p.stdout).strip()[:200] or f"gh exit {p.returncode}")
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise GitHubError(f"gh {' '.join(args[:2])} gave no JSON")


def merged_pull(cwd, name, sha, base_name):
    """The number of a pull request from `name` merged into base_name with head `sha`."""
    pulls = gh(cwd, "pr", "list", "--head", name, "--state", "merged", "--json",
               "number,headRefOid,baseRefName", "--limit", "50")
    for pull in pulls:
        if isinstance(pull, dict) and pull.get("headRefOid") == sha \
                and pull.get("baseRefName") == base_name:
            return pull.get("number")
    return None


def note_line(item):
    signed = [c for c in item.get("comments") or []
              if str(c.get("body", "")).lstrip().startswith(SIGN)]
    notes = [c for c in signed if NOTE.search(str(c.get("body", "")))]
    if notes:
        return f"  note: {notes[-1].get('url', '?')}"
    if signed:
        return f"  no design note; newest signed comment: {signed[-1].get('url', '?')}"
    return f"  no signed comment: {item.get('url', '?')}"


def branch_lines(hit):
    if hit["kind"] == "same":
        return [f"same issue: branch {hit['name']} (#{hit['issue']}) head {hit['sha'][:8]} "
                f"already works on #{hit['issue']}, last commit {ago(hit['when'])} ago: "
                "a second session on one issue"]
    n = hit["issue"]
    first = ago(hit["first"]) if hit["first"] else "?"
    return [f"overlap: branch {hit['name']}" + (f" (#{n})" if n else "") +
            f" head {hit['sha'][:8]}, unmerged since {first}, last commit {ago(hit['when'])} "
            f"ago: {', '.join(hit['shared'])}",
            f"  #{n}" if n else "  (no issue in its name or subject)"]


def main(argv):
    try:
        return check(argv)
    except Exception as error:  # an unexpected failure must never read as exit 1 (overlaps)
        print(f"error: {type(error).__name__}: {error}; nothing was judged")
        return 2


def check(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("-C", dest="cwd", default=".")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--branch")
    g.add_argument("--paths", nargs="+")
    ap.add_argument("--issue", type=int)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--base")
    ap.add_argument("--no-github", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            return 0
        print("usage: see the header of overlap_check.py")
        return 2
    cwd = os.path.abspath(os.path.expanduser(a.cwd))
    try:
        base = a.base or default_base(cwd)
        if not verified(cwd, base):
            raise Usage(f"error: base {base} is not a commit here")
        cand_sha = None
        if a.branch:
            cand_sha = git(cwd, "rev-parse", "--verify", a.branch + "^{commit}").strip()
            paths = changed(cwd, base, a.branch, strict=True)
            issue = a.issue if a.issue is not None else issue_of(  # past ship-change's merge
                a.branch, git(cwd, "log", "-1", "--no-merges", "--format=%s", a.branch).strip())
        else:
            paths = {posixpath.normpath(p.replace("\\", "/")).strip("/") for p in a.paths}
            issue = a.issue
        hits, tips, stale = local_branches(cwd, base, paths, a.branch, cand_sha, issue, a.days)
    except Usage as e:
        print(e)
        return 2
    except subprocess.TimeoutExpired as e:
        print(f"error: {' '.join(str(c) for c in e.cmd[:3])} timed out; nothing was judged")
        return 2

    base_name = branch_name(base)
    lines, count, unchecked, merged = [], 0, None, []
    issues, pulls = {}, []
    if not a.no_github:
        try:
            kept, gone = [], []
            for hit in hits:
                n = merged_pull(cwd, hit["name"], hit["sha"], base_name)
                if n is None:
                    kept.append(hit)
                else:
                    gone.append(f"{hit['name']} (pull request #{n})")
            hits, merged = kept, gone  # together, so a failure halfway changes neither
            pulls = gh(cwd, "pr", "list", "--state", "open", "--limit", "200", "--json",
                       PR_FIELDS)
            issues = {i["number"]: i for i in gh(
                cwd, "issue", "list", "--state", "open", "--assignee", "*", "--limit", "500",
                "--json", ISSUE_FIELDS)}
        except (GitHubError, subprocess.TimeoutExpired) as e:
            unchecked, pulls, issues = str(e), [], {}

    for hit in hits:
        lines.extend(branch_lines(hit))
        count += 1
    for pull in pulls:
        head, sha = pull.get("headRefName") or "", pull.get("headRefOid") or ""
        if head == a.branch or sha == cand_sha or sha in tips:
            continue
        if cand_sha and sha and contains(cwd, sha, cand_sha):
            continue
        n = issue_of(head, str(pull.get("title") or ""))
        if issue is not None and n == issue:
            lines.append(f"same issue: pull request #{pull.get('number')} ({head}) already "
                         f"works on #{issue}: a second session on one issue")
            lines.append(note_line(pull))
            count += 1
            continue
        files = {str(f.get("path") or "") for f in pull.get("files") or []
                 if isinstance(f, dict)}
        shared = sorted(paths & files)
        if not shared:
            continue
        lines.append(f"overlap: pull request #{pull.get('number')} ({head})"
                     + (f" (#{n})" if n else "")
                     + f" {str(pull.get('title'))[:70]!r}: {', '.join(shared)}")
        lines.append(f"  #{n}" if n else note_line(pull))
        count += 1
    if unchecked is None and not a.no_github:
        for i, line in enumerate(lines):  # a branch's or pull request's issue: its note
            m = re.fullmatch(r"  #(\d+)", line)
            if not m:
                continue
            n = int(m.group(1))
            if n not in issues:
                try:
                    issues[n] = gh(cwd, "issue", "view", str(n), "--json", ISSUE_FIELDS)
                except (GitHubError, subprocess.TimeoutExpired):
                    lines[i] = f"  #{n}: not readable on GitHub"
                    continue
            lines[i] = note_line(issues[n])
        for n, iss in sorted(issues.items()):
            if n == issue or not iss.get("assignees"):
                continue
            text = "\n".join([str(iss.get("body") or "")] +
                             [str(c.get("body") or "") for c in iss.get("comments") or []])
            shared = sorted(p for p in paths if mentions(text, p))
            if not shared:
                continue
            lines.append(f"overlap: issue #{n} (claimed) {str(iss.get('title'))[:70]!r}: "
                         f"{', '.join(shared)}")
            lines.append(note_line(iss))
            count += 1

    for line in lines:
        print(line)
    if merged:
        print(f"merged: {len(merged)} branch(es) merged by pull request, not counted: "
              + ", ".join(merged))
    if stale:
        print(f"skipped: {stale} unmerged branch(es) with no commit in the last {a.days} days")
    if unchecked is not None:
        if count:
            print(f"overlaps: {count} branch(es)")
        print("unchecked: GitHub was not read, so open pull requests, claimed issues and "
              f"squash merges are unknown ({unchecked})")
        return 3
    if count:
        print(f"overlaps: {count}")
        return 1
    print(f"none: no unmerged branch, open pull request or claimed issue shares a path with "
          f"{len(paths)} path(s)")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
