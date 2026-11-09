---
name: ship-change
description: Land finished work from a task branch in the mode the repository uses - a pull request, or a guarded fast-forward onto local main - after detecting the mode, picking the review route, running the checks and asking the user before every push. Use when work on a branch is done and ready to land or for review, or when the user asks to push, land, publish or open a pull request.
---

# Landing a finished branch

The user decides every push. This skill prepares everything first, so that the user's yes is
the last step. It never force-pushes, and it marks a pull request ready, or merges it, only when
the user says so for that pull request.

Work starts on a branch in a worktree, in both modes. `python3 <plugin>/scripts/new_worktree.py <task>`,
run from the repository's primary checkout, makes `../<repo>-worktrees/<task>` on a new branch
`agent/<task>` from the freshly fetched landing branch. `<plugin>` is the folder two levels
above this skill's folder ([new_worktree.py](../../scripts/new_worktree.py)).

## 1. Detect the mode, pick the review route, say both on the issue

Run `python3 <plugin>/scripts/landing.py --explain` in your worktree ([landing.py](../../scripts/landing.py),
whose header owns the rule). Its last line is the mode, the line before it the landing branch
(`<landing>` below; the remote's default branch unless the repository names another):

- **pull request:** teams, a server that requires pull requests, and whenever it cannot tell.
  Steps 2 to 7 below.
- **local main:** one person with write access, no protection, no team signal (trunk-based
  development for a very small team). Steps 2, 3 and 5 below, then
  [local-main.md](local-main.md) in place of 4, 6 and 7.

Run it again at every landing, with `--explain` to see the signals it read, and never carry a
mode over from an earlier task. A repository fixes its mode in `HANDOFF.md`, merged like any
other change: `landing` is `pull request`, `local main` (which cannot overrule a server that
requires pull requests) or `auto` (detect); `landing branch`, left out, is the remote's default
branch. A value cell holds the value alone:

```markdown
## Landing settings

| Setting | Value |
|---|---|
| landing | `auto` |
| landing branch | `main` |
```

The review route, in both modes:

- **Small change:** one bounded, low-risk change with an obvious diff, simple checks and a simple
  rollback (copy, documentation, an isolated fix that keeps existing contracts). You check it.
- **Independent review:** anything larger or risky regardless of size: several components, a
  shared interface, a data migration, authentication, permissions, security, deployment,
  dependencies, agent rules. A context that did not write the change reviews it: `/code-review`
  in Claude Code, `/review` in Codex, run in a fresh session or subagent. In pull-request mode
  that happens before the pull request is marked ready, and the repository's own required
  reviewers still review it on GitHub; in local-main mode the reviewer also lands it. A change
  touching authentication, permissions, secrets, dependencies or deployment also gets the
  `review-security` skill when it is installed.

One sentence on the issue is enough: the mode with its reason, the route and why. When you start
work on an issue that has no assignee, assign it to the account you post under
(`gh issue edit <n> --add-assignee @me`) and say so on the issue: that is the claim the overlap
check of step 5 reads.

## 2. Bring the landing branch in

`git fetch origin`. If `origin/<landing>` is not an ancestor of your branch
(`git merge-base --is-ancestor origin/<landing> HEAD`), merge it: `git merge origin/<landing>`.
In local-main mode do the same with the local `<landing>`, which holds landings not pushed yet.
Without a remote, the local `<landing>` alone. Never rebase. Conflicts whose combined intent is
unclear go to the user.

## 3. Checks

- Read the whole diff: `git diff origin/<landing>...HEAD`.
- Run the checks the repository requires for this kind of change (`HANDOFF.md`, `AGENTS.md`,
  the CI workflow); a failing check is fixed, never weakened or skipped. In local-main mode no
  server runs them after you: every check the repository requires for this change type runs
  here.
- `git status` shows nothing you meant to commit and did not.
- With the security plugin installed, its `scan_secrets.py` on the repository is clean, or every
  hit is explained.

## 4. Prepare the pull request

Write the title and body to a file outside the repository. The body starts with
`🤖 <agent> (<role>):` and holds what changed and why, how it was checked, what is not covered,
and `Closes #<n>` for the issue it finishes (a closing keyword is right here: the merge is the
verified publication). Draft or ready: draft while an independent review is still open.

## 5. The overlap check

Other sessions may have unmerged work in the same files. Run
`python3 <plugin>/scripts/overlap_check.py --branch <your task branch> --issue <n>`
([overlap_check.py](../../scripts/overlap_check.py)), `<n>` the issue it works on. It only reads git and `gh`, compares
against the landing branch as fetched in step 2, and lists the local branches, open pull
requests and claimed (assigned) open issues that share a path with yours; `--no-github` in a
repository without a GitHub remote.

- Exit 0: nothing to do.
- Exit 1: for every hit that is older than your work or claimed, read the design note (or
  newest signed comment) it names, and add one line per hit to the pull request body of
  step 4, or in local-main mode to the landing comment: the two agree, or what the later one
  must change. A conflict of design goes to its authors or to the user, not into this landing.
- Exit 2: nothing was judged. Fix the call, or fetch, and run it again; never report it as
  no overlap.
- Exit 3 (GitHub not read; any branch hits it lists count as for exit 1): run it again; go on
  without the pull requests and claims only with that limitation stated in the body.

It does not block by itself: the merge on GitHub, or `promote_main.py` in local-main mode, is
where the branches meet.

## 6. Ask

One message to the user: the branch, how many commits, the checks and their results, the
overlap check's result, the pull request title, draft or ready. Wait for an explicit yes for
this push. A yes for an earlier push does not cover this one.

## 7. Push and open the pull request

On the yes:

1. `git push origin <your task branch>`: your own task branch only, never the landing branch,
   never with `--force` or `+` (and without `-u`, which writes upstream settings into the git
   configuration). A rejected push means stop: fetch, go back to step 2, ask again.
2. `gh pr create --base <landing> --head <branch> --title "<title>" --body-file <file>`
   (`--draft` for a draft). Without `gh`, give the user the title, the body and the compare URL
   (`https://github.com/<owner>/<repo>/compare/<landing>...<branch>`), and stop.
3. Report the pull request URL and the first CI result (`gh pr checks <n>`).

Review comments become new commits on the same branch; each new push asks again. Marking the
draft ready and merging happen only on the user's word for that pull request
(`gh pr ready <n>`, `gh pr merge <n>` with the method the repository uses). After the merge:
the `cleanup-merged` skill.
