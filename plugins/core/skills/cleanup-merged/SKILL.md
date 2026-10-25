---
name: cleanup-merged
description: Remove a task's worktree and branches after its pull request was merged, and make sure its issue is closed. Use when the user says a pull request was merged, when asked to clean up merged work or old worktrees, or to audit which worktrees can go.
---

# Cleaning up after a merge

`<plugin>` below is the folder two levels above this skill's folder; the script is
[remove_merged_worktree.py](../../scripts/remove_merged_worktree.py). Run everything from the
repository's primary checkout, not from inside the worktree that goes.

1. **Prove the merge.** `gh pr view <number or branch> --json state,mergedAt,mergeCommit,headRefName,headRefOid`
   must say `MERGED`. Not merged: stop and tell the user.
2. **Remove the worktree and the local branch:**
   `python3 <plugin>/scripts/remove_merged_worktree.py <worktree>`, or `--sweep` for every
   linked worktree of the repository, `--dry-run` to only report. It fetches, runs the checks
   below and then removes; what fails a check is kept and named.
3. **The remote branch.** `git ls-remote --heads origin <branch>`. If GitHub did not delete it,
   `git push origin --delete <branch>`: the one push this skill makes without a separate yes,
   for a merged task branch only. The `pre-push` template allows it only for a non-default
   branch whose tip is in the default branch or is the head of a merged pull request.
4. **The issue.** `gh issue view <n> --json state`. A closing keyword in the pull request closed
   it at the merge. Still open and fully resolved: close it with a signed comment naming the pull
   request and the merge commit. Resolved in part: comment what remains and leave it open.
5. **Report** what was removed and what was kept, with the reasons.

A worktree the script keeps stays with its owner or the user: never remove a worktree by hand,
never delete ignored files on judgement. Work the user decided to abandon is removed only with
their words passed as `--approved "<their words>"`, which waives the merged check alone and
never deletes the branch.

## What the script checks

Per worktree, every check must hold; otherwise it is kept and named:

- **merged**: its branch tip is in the fetched default branch (a merge commit or fast-forward),
  or it is exactly the head commit of a merged pull request (`gh pr list --head <branch>
  --state merged`), which covers squash and rebase merges. A commit added after that head keeps
  it. In `--sweep`, a branch also needs commits of its own in its reflog, so a fresh worktree is
  never mistaken for merged.
- **clean**: `git status` is empty and no index entry hides local edits.
- **ignored files**: every ignored entry proves it can be regenerated (a symlink, `.DS_Store`,
  bytecode, a tagged cache with its tool's known layout, `node_modules` with a package-manager
  state file, or a pattern in the repository's tracked `.worktree-disposable`, each line
  `<pattern>  # <who approved> YYYY-MM-DD #<issue>`). Anything else keeps the worktree, because
  `git worktree remove` deletes ignored files without asking.
- **no stray commits**: every commit the worktree's own history records stays reachable from a
  ref that survives the removal.
- **unlocked, idle**: no worktree lock, and no other process has a file open inside (`lsof`; on
  Windows the removal itself refuses open files).

Then `git worktree remove` (never `--force`) and the local branch is deleted against the exact
commit that was proven merged. `git worktree prune` drops metadata of worktrees whose folder is
already gone. Undo a merge with `git revert` (a merge commit: `git revert -m 1 <merge>`), never
by rewriting `main`.
