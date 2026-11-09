#!/usr/bin/env python3
"""Land a checked candidate on the primary checkout's landing branch, guarded (local-main mode).

Usage: python3 promote_main.py [-C <path>] [--no-fetch] [--remote <name>] <candidate>

The ship-change skill runs it in local-main mode ([local-main.md](../skills/ship-change/local-main.md)).
Run it from any checkout of the repository, the primary or a linked worktree, or name one with
-C <path>. The candidate is resolved there; then it finds the primary checkout (the worktree of
`git rev-parse --git-common-dir`, which must be on the landing branch) and runs every step there.
The landing branch and the mode come from landing.py: the row `landing branch` of HANDOFF.md's
`## Landing settings`, else origin's default branch; "main" below means that branch. It stops at
the first check that fails, changing nothing:

  0. landing.py decides local main for this repository; in pull-request mode it refuses, because
     the work lands through a pull request.
  1. HEAD is the branch main, no git operation is in progress, the index matches HEAD, and no
     index entry hides local edits (assume-unchanged, skip-worktree, sparse checkout).
  2. main is an ancestor of the candidate (a fast-forward), and the remote's main, fetched now,
     is in the candidate too (skip with --no-fetch only in a repository without a remote, or
     when fetching failed and the user made the exception).
  3. Every local modification, deletion, untracked and ignored path of the primary checkout is
     inventoried and compared with the FULL main-to-candidate tree diff, both sides of every
     rename and every directory prefix in both directions included, case-folded where
     core.ignorecase is on. Any overlap stops the landing: nothing is stashed, moved or deleted.
  4. The preserved paths' type, mode and content hash are recorded (contents are never printed;
     an ignored directory by its presence only). The hooks this merge runs are listed.
  5. `git merge --ff-only --no-autostash --no-overwrite-ignore <candidate>`; a refusal stops.
  6. HEAD equals the candidate, the index matches it, every preserved path is unchanged and no
     new local path appeared.

It does not replace the route's review, checks and evidence or reading the listed hooks: those
stay the agent's job. It needs no lock or claim: it is the compare-and-swap of the landing (of
two fast-forwards at once git lets one through), so a refusal because main moved means: merge
main into the candidate and run it again. Exit 0 landed (or nothing to do), 1 refused or failed
(the reason is printed), 2 usage.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from landing import LOCAL, SettingError, decide  # noqa: E402  (owner of the settings)


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"promote: git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def refuse(msg: str) -> None:
    print(f"promote: REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(1)


def z(out: str) -> list[str]:
    return [p for p in out.split("\0") if p]


def state_of(path: str) -> str:
    """Type, mode and content hash of a path, without its contents."""
    if os.path.islink(path):
        return "link:" + os.readlink(path)
    if not os.path.lexists(path):
        return "absent"
    if os.path.isdir(path):
        return "dir"
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"file:{oct(st.st_mode & 0o777)}:{h.hexdigest()}"


def local_paths() -> set[str]:
    """Local modifications/deletions against HEAD, untracked paths and ignored paths."""
    s = set(z(git("diff", "--name-only", "-z", "HEAD")))
    s |= set(z(git("ls-files", "-z", "--others", "--exclude-standard")))
    s |= set(z(git("ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory")))
    return s


def ancestors(p: str) -> set[str]:
    segs = p.split("/")
    return {"/".join(segs[:k]) for k in range(1, len(segs))}


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(line_buffering=True)  # keep progress and refusals in order
    fetch, remote, where, rest = True, "origin", ".", []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--no-fetch":
            fetch = False
        elif a == "--remote":
            i += 1
            remote = argv[i] if i < len(argv) else ""
        elif a == "-C":
            i += 1
            where = argv[i] if i < len(argv) else ""
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            rest.append(a)
        i += 1
    if len(rest) != 1 or not remote or not where:
        print(__doc__, file=sys.stderr)
        return 2

    try:
        os.chdir(where)
    except OSError as e:
        refuse(f"cannot enter {where}: {e.strerror}")
    # The candidate is resolved in the calling checkout (HEAD there is the caller's HEAD).
    cand = git("rev-parse", "--verify", rest[0] + "^{commit}").strip()
    # The primary checkout is the worktree that owns the common git directory: the calling
    # checkout itself when its git directory is the common one (also a --separate-git-dir
    # checkout, whose git directory lies elsewhere), otherwise the common directory's parent.
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    own = git("rev-parse", "--path-format=absolute", "--git-dir").strip()
    top = git("rev-parse", "--show-toplevel", check=False).strip()
    if os.path.realpath(own) == os.path.realpath(common) and top:
        primary = top
    else:
        primary = os.path.dirname(common)
        if os.path.basename(common) != ".git" or not os.path.isdir(primary):
            refuse(f"cannot locate the primary checkout from the common git directory {common}")
    os.chdir(primary)
    if (os.path.realpath(git("rev-parse", "--show-toplevel").strip()) != os.path.realpath(primary)
            or os.path.realpath(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
            != os.path.realpath(common)):
        refuse(f"{primary} is not the primary checkout of {common}")
    try:
        mode, lb, checks = decide(primary)
    except SettingError as e:
        refuse(str(e))
    print(f"promote: primary checkout {primary}")
    if mode != LOCAL:
        refuse("this repository lands through pull requests (landing.py: "
               + "; ".join(checks[-2:]) + "): use ship-change's pull-request steps")
    print(f"promote: landing mode local main ({checks[-1]})")

    # 1. the landing branch checked out, nothing in progress, index == HEAD, nothing hidden.
    if git("symbolic-ref", "-q", "HEAD", check=False).strip() != f"refs/heads/{lb}":
        refuse(f"the primary checkout {primary} is not on {lb}")
    gitdir = git("rev-parse", "--git-dir").strip()
    for op in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD", "rebase-merge",
               "rebase-apply", "BISECT_LOG"):
        if os.path.exists(os.path.join(gitdir, op)):
            refuse(f"a git operation is in progress ({op})")
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
        refuse(f"the index has staged changes: it must match {lb}")
    if git("ls-files", "-u"):
        refuse("the index has unresolved entries")
    hidden = [l[2:] for l in git("ls-files", "-v").splitlines() if l[:1].islower() or l[:1] == "S"]
    if hidden:
        refuse(f"{len(hidden)} index entries hide local edits (assume-unchanged/skip-worktree), e.g. {hidden[0]}")
    if git("config", "--bool", "core.sparseCheckout", check=False).strip() == "true":
        refuse("sparse checkout is on: the inventory cannot be trusted")
    base = git("rev-parse", "HEAD").strip()

    # 2. fast-forward, and the remote's landing branch is in the candidate.
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, cand]).returncode != 0:
        refuse(f"{lb} {base[:10]} is not an ancestor of {cand[:10]}: merge {lb} into the candidate first")
    if fetch:
        if remote not in git("remote").split():
            refuse(f"there is no remote '{remote}': a repository without a remote uses --no-fetch")
        if subprocess.run(["git", "fetch", "-q", remote]).returncode != 0:
            refuse(f"fetching {remote} failed: promotion waits for a fresh check (or --no-fetch on the user's exception)")
        r = git("rev-parse", "-q", "--verify", f"refs/remotes/{remote}/{lb}", check=False).strip()
        if not r:
            if git("ls-remote", "--heads", remote, f"refs/heads/{lb}").strip():
                refuse(f"{remote} has a {lb}, but the fetch did not update refs/remotes/{remote}/{lb}: "
                       "fetch it and retry")
            print(f"promote: {remote} has no {lb} branch; no remote commit to include")
        elif subprocess.run(["git", "merge-base", "--is-ancestor", r, cand]).returncode != 0:
            refuse(f"{remote}/{lb} {r[:10]} is not in the candidate: merge it into the candidate first")
        else:
            print(f"promote: {remote}/{lb} {r[:10]} is in the candidate")
    else:
        print("promote: remote not checked (--no-fetch)")
    if base == cand:
        print(f"promote: {lb} is already {cand[:10]}; nothing to do")
        return 0

    # 3. inventory of preserved paths against the full tree diff.
    changed = set()
    parts = z(git("diff", "--name-status", "-z", "--find-renames", base, cand))
    j = 0
    while j < len(parts):
        status = parts[j]; j += 1
        n = 2 if status[:1] in ("R", "C") else 1
        changed.update(parts[j:j + n]); j += n
    # On a case-insensitive file system Foo.txt and foo.txt are one path.
    icase = git("config", "--bool", "core.ignorecase", check=False).strip() == "true"
    fold = (lambda s: s.casefold()) if icase else (lambda s: s)
    changed_f = {fold(c) for c in changed}
    prefixes_f = set().union(*(ancestors(c) for c in changed_f)) if changed_f else set()
    preserved = local_paths()
    overlap = []
    for p in sorted(preserved):
        q = fold(p.rstrip("/"))
        # the path itself changes, a changed path lies below it, or a changed path is a
        # file/directory where one of its parent directories stands.
        if q in changed_f or q in prefixes_f or ancestors(q) & changed_f:
            overlap.append(p.rstrip("/"))
    if overlap:
        refuse(f"{len(overlap)} local path(s) overlap the change, e.g. {overlap[:5]}: nothing is moved for you")

    # 4. record the preserved paths (ignored directories by their presence only).
    before = {p: state_of(p.rstrip("/")) for p in preserved}
    print(f"promote: {lb} {base[:10]} -> {cand[:10]}, {len(changed)} paths change, "
          f"{len(preserved)} local paths preserved, no overlap")
    hooks_dir = git("rev-parse", "--git-path", "hooks").strip()
    hooks = [h for h in ("reference-transaction", "post-index-change", "post-merge")
             if os.access(os.path.join(hooks_dir, h), os.X_OK)]
    if hooks:
        print(f"promote: hooks that run on this merge: {', '.join(hooks)} (in {hooks_dir}); "
              "they are not disabled, step 6 checks their effect on preserved paths")

    # 5. the fast-forward itself.
    r = subprocess.run(["git", "merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore", cand],
                       capture_output=True, text=True)
    if r.returncode != 0:
        refuse(f"git refused the fast-forward: {r.stderr.strip() or r.stdout.strip()} (do not retry with weaker flags)")

    # 6. verify.
    head = git("rev-parse", "HEAD").strip()
    problems = []
    if head != cand:
        problems.append(f"HEAD is {head[:10]}, not {cand[:10]}")
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
        problems.append("the index does not match the candidate")
    after = {p: state_of(p.rstrip("/")) for p in preserved}
    moved = [p for p in preserved if before[p] != after[p]]
    if moved:
        problems.append(f"{len(moved)} preserved path(s) changed, e.g. {moved[:5]}")
    dirs = [p for p in preserved if p.endswith("/")]

    def covered(p: str) -> bool:
        # an ignore rule changed by the candidate may list a directory's files or the directory
        return (p in preserved or any(p.startswith(d) for d in dirs)
                or (p.endswith("/") and any(q.startswith(p) for q in preserved)))

    new = sorted(p for p in local_paths() if not covered(p))
    if new:
        problems.append(f"{len(new)} new local path(s) appeared, e.g. {new[:5]}")
    if problems:
        print("promote: PROMOTED BUT VERIFY FAILED: " + "; ".join(problems)
              + ". Stop and report; do not reset or restore anything.", file=sys.stderr)
        return 1
    print(f"promote: {lb} is now {cand[:10]}; index matches; {len(preserved)} preserved paths unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
