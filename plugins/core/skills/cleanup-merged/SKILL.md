---
name: cleanup-merged
description: Remove a task's worktree and branches after its pull request was merged, and make sure its issue is closed. Use when the user says a pull request was merged, when asked to clean up merged work, old worktrees or leftover local branches, or to audit which worktrees and branches can go.
---

# Cleaning up after a merge

`<plugin>` below is the folder two levels above this skill's folder; the scripts are
[remove_merged_worktree.py](../../scripts/remove_merged_worktree.py) and
[delete_merged_branch.py](../../scripts/delete_merged_branch.py). Run everything from the
repository's primary checkout, not from inside the worktree that goes.

1. **Prove the merge.** `gh pr view <number or branch> --json state,mergedAt,mergeCommit,headRefName,headRefOid`
   must say `MERGED`. Not merged: stop and tell the user.
2. **Remove the worktree and the local branch:**
   `python3 <plugin>/scripts/remove_merged_worktree.py <worktree>`, or `--sweep` for every
   linked worktree of the repository, `--dry-run` to only report. It fetches, runs the checks
   below and then removes; what fails a check is kept and named. After the worktrees, a sweep
   also deletes local branches that nothing holds any more (below), printing for each
   `DELETED <branch> at <sha>`, the `git branch <branch> <sha>` that restores it, and
   `remote copy: origin/<branch>` when origin still has one.
3. **The remote branch,** and each `remote copy` the sweep named.
   `python3 <plugin>/scripts/delete_merged_branch.py <branch> --dry-run`
   says whether GitHub already deleted it and, if not, whether its tip on the remote is still
   the merged commit. Deleting it is a push, so ask the user first, like every other push. On a
   yes, run the same command without `--dry-run`: it deletes the branch only while its tip is
   still the merged pull request's head (or in the default branch), with a lease on that tip,
   so a commit someone pushed after the merge is never lost. A refusal: leave the branch and
   tell the user. The `pre-push` template allows the deletion on the same terms.
4. **The issue.** `gh issue view <n> --json state`. A closing keyword in the pull request closed
   it at the merge. Still open and fully resolved: close it with a signed comment naming the pull
   request and the merge commit. Resolved in part: comment what remains and leave it open.
   Put every branch the sweep printed as DELETED, name and head SHA, in a signed comment on
   that issue, whichever issue the branch belonged to: nothing else records them, and the SHA
   is the way back until git prunes the commit. A cleanup without an issue puts them on a new
   one.
5. **Report** what was removed and what was kept, with the reasons.

A worktree or branch the script keeps stays with its owner or the user: never remove a worktree
or delete a kept branch by hand, never delete ignored files on judgement. Work the user decided
to abandon is removed only with their words passed as `--approved "<their words>"`, which waives
the merged check alone and never deletes the branch; a later sweep takes that branch if it has
been merged.

## What the script checks

Per worktree, every check must hold; otherwise it is kept and named:

- **merged**: its branch tip is in the fetched default branch (a merge commit or fast-forward),
  or it is exactly the head commit of a pull request merged into the default branch (`gh pr list
  --head <branch> --state merged`, `baseRefName` the default branch), which covers squash and
  rebase merges; a pull request merged into another branch (stacked) does not count. A commit
  added after that head keeps it. In `--sweep`, a branch also needs commits of its own in its
  reflog, so a fresh worktree is never mistaken for merged; ancestry in the fetched default
  branch, or that merged pull request, is the proof, so a sweep needs no separate step 1.
- **clean**: `git status` is empty and no index entry hides local edits.
- **ignored files**: every ignored entry proves it can be regenerated (a symlink, `.DS_Store`,
  bytecode, a tagged cache with its tool's known layout, `node_modules` with a package-manager
  state file, or a pattern in the repository's tracked `.worktree-disposable`, each line
  `<pattern>  # <who approved> YYYY-MM-DD #<issue>`). Anything else keeps the worktree, because
  `git worktree remove` deletes ignored files without asking.
- **no stray commits**: every commit the worktree's own history records stays reachable from a
  ref that survives the removal. A commit made on a detached HEAD, or dropped by a reset, keeps
  the worktree: give it a branch and rerun. For a probe that must never be merged that is
  `git branch scratch/<issue>-<what> <sha>`, which a sweep deletes once the issue is closed;
  for work that must stay, a task branch.
- **unlocked, idle**: no worktree lock, and no other process has a file open inside (`lsof`; on
  Windows the removal itself refuses open files).

Then `git worktree remove` (never `--force`) and the local branch is deleted against the exact
commit that was proven merged. `git worktree prune` drops metadata of worktrees whose folder is
already gone. Undo a merge with `git revert` (a merge commit: `git revert -m 1 <merge>`), never
by rewriting `main`.

A sweep's branch passes run only when the default branch could be established and no removal
failed in that sweep (`--no-fetch` skips the merged pass); `--dry-run` reports them too:

- **scratch branches**: a local `scratch/<issue>-<what>` goes when GitHub reports its issue
  closed (`gh issue view <n> -R <origin>`) and no worktree has it checked out. It stays and is
  named when it has no issue number, the issue is open or cannot be read (without `gh` every
  scratch branch stays), or its reflog cannot show it was made for that issue: renamed from a
  name without the number (a renamed task branch would take its commits along), or a reflog
  that is missing or no longer unbroken from the branch's creation. Such a kept branch stays
  until the user decides.
- **merged branches**: every other local branch goes, whoever left it, when it is merged as
  above (without `gh`, a squash-merged one is only counted), no worktree holds it, and every
  commit in its reflog is in the default branch or that pull request's head. It stays and is
  named when a worktree holds it (one whose directory is gone: until `git worktree prune`),
  when its reflog holds a commit outside the default branch, and for `claude/*`, the Claude
  Code desktop app's session branches, which a resumed session checks out again. `main`,
  `master` and the default branch are never touched; a branch that is not merged is only
  counted.
