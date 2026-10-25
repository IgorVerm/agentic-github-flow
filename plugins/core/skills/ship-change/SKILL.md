---
name: ship-change
description: Take finished work on a task branch to a pull request - pick the review route, run the checks, ask the user before the push, then push the branch and open the pull request. Use when work on a branch is done and ready for review, or when the user asks to push, publish or open a pull request.
---

# From a finished branch to a pull request

The user decides every push. This skill prepares everything first, so that the user's yes is
the last step. It never pushes `main`, never force-pushes and never merges.

Work starts on a branch in a worktree. `python3 <plugin>/scripts/new_worktree.py <task>`, run
from the repository's primary checkout, makes `../<repo>-worktrees/<task>` on a new branch
`agent/<task>` from the freshly fetched default branch. `<plugin>` is the folder two levels
above this skill's folder ([new_worktree.py](../../scripts/new_worktree.py)); a plain
`git worktree add -b agent/<task> ../<repo>-worktrees/<task> origin/main` does the same.

## 1. Pick the review route and say it on the issue

- **Small change:** one bounded, low-risk change with an obvious diff, simple checks and a simple
  rollback (copy, documentation, an isolated fix that keeps existing contracts). You check it.
- **Independent review:** anything larger or risky regardless of size: several components, a
  shared interface, a data migration, authentication, permissions, security, deployment,
  dependencies, agent rules. A context that did not write the change reviews it before the pull
  request is marked ready: `/code-review` in Claude Code, `/review` in Codex, run in a fresh
  session or subagent. A change touching authentication, permissions, secrets, dependencies or
  deployment also gets the `review-security` skill when it is installed. The repository's own
  required reviewers still review the pull request on GitHub.

One sentence on the issue is enough: the route and why.

## 2. Bring the default branch in

`git fetch origin`. If `origin/<default>` is not an ancestor of your branch
(`git merge-base --is-ancestor origin/<default> HEAD`), merge it: `git merge origin/<default>`.
Never rebase. Conflicts whose combined intent is unclear go to the user.

## 3. Checks

- Read the whole diff: `git diff origin/<default>...HEAD`.
- Run the checks the repository requires for this kind of change (`HANDOFF.md`, `AGENTS.md`,
  the CI workflow); a failing check is fixed, never weakened or skipped.
- `git status` shows nothing you meant to commit and did not.
- With the security plugin installed, its `scan_secrets.py` on the repository is clean, or every
  hit is explained.

## 4. Prepare the pull request

Write the title and body to a file outside the repository. The body starts with
`🤖 <agent> (<role>):` and holds what changed and why, how it was checked, what is not covered,
and `Closes #<n>` for the issue it finishes (a closing keyword is right here: the merge is the
verified publication). Draft or ready: draft while an independent review is still open.

## 5. Ask

One message to the user: the branch, how many commits, the checks and their results, the pull
request title, draft or ready. Wait for an explicit yes for this push. A yes for an earlier push
does not cover this one.

## 6. Push and open the pull request

On the yes:

1. `git push -u origin <your task branch>`: your own task branch only, never `main`, never with
   `--force` or `+`. A rejected push means stop: fetch, go back to step 2, ask again.
2. `gh pr create --base <default> --head <branch> --title "<title>" --body-file <file>`
   (`--draft` for a draft). Without `gh`, give the user the title, the body and the compare URL
   (`https://github.com/<owner>/<repo>/compare/<default>...<branch>`), and stop.
3. Report the pull request URL and the first CI result (`gh pr checks <n>`).

Review comments become new commits on the same branch; each new push asks again. Marking the
draft ready, merging and closing are the user's, per pull request. After the merge: the
`cleanup-merged` skill.
