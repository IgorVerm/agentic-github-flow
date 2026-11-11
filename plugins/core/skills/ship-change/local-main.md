# Local-main mode: landing on the landing branch, then pushing it

Read with [SKILL.md](SKILL.md); `<landing>` and `<plugin>` are as defined there. Landing means
the commit is on the local landing branch of the primary checkout. Pushing that branch is a
separate step and needs the user's word (§5). Nothing is rebased, squashed or forced to make a
landing work. Commits name the issue as `(#n)` without a closing keyword: the issue is closed
after the push is verified, by the `cleanup-merged` skill.

Between pushes the local landing branch is ahead of origin's: `new_worktree.py` and the overlap
check start from it then, and SKILL step 2 merges it in. A repository without a remote has
nothing to fetch or push; `promote_main.py` says so and lands all the same.

Land from a worktree, not from a session whose working directory is the primary checkout: when
the landing branch changed `.claude/` or `.mcp.json`, the sandbox keeps that session from
writing them there, and `merge_landing.py` refuses to freeze them in a primary checkout, where
they would stay behind for good.

## 1. Small change: the author lands it

After SKILL steps 1 to 3 and 5, from your worktree:
`python3 <plugin>/scripts/promote_main.py <commit>` ([promote_main.py](../../scripts/promote_main.py)).
It asks `landing.py` again and refuses unless the mode is local main, then checks the primary
checkout and fast-forwards its landing branch to exactly that commit (its header lists every
check). It is the compare-and-swap of the landing: nobody claims or releases a slot, and of two
landings at once git lets one through.

- Refused because `<landing>` or `origin/<landing>` is not in the candidate: merge it into your
  branch (SKILL step 2), re-check per §3, run it again.
- Any other refusal, or git's: stop and report. Never retry with weaker flags, and never stash,
  move or delete another session's files in the primary checkout to make it pass. If your client
  may not reach the primary checkout, hand the landing to an agent that may.

Then one signed comment on the issue, and in the same landing, when the repository keeps
`archive_implementations.md`, its line `YYYY-MM-DD — <item> (#n) — landed <commit>`:
`🤖 <agent> (<role>): Landed on local <landing> at <sha>: <what>; checks: <what ran, result>; overlap: <result>; efficient design: <result>` (SKILL step 4).
The issue stays open, assigned to you, until the push.

## 2. Independent review: the reviewer lands it

1. **The author** hands over a clean branch at an exact commit S, with what was checked, what
   is not covered and the `Efficient design:` line (SKILL step 4) on the issue, and stops
   writing to it.
2. **The reviewer,** a fresh session or subagent that did not write the change, reviews the diff
   and the evidence of S with the `review-change` skill. What affects correctness or the stated
   requirements goes back to the author; a new author commit needs a new review.
3. **It lands S.** `git fetch origin` first. When the local `<landing>` and the fetched
   `origin/<landing>` are both in S: the overlap check (SKILL step 5) on S's branch, then
   `promote_main.py <S>`. Otherwise it builds away from the landing branch:
   `python3 <plugin>/scripts/new_worktree.py <n>-integrate --branch integrate/<n> --base <landing>`,
   there `python3 <plugin>/scripts/merge_landing.py origin/<landing>` when the local `<landing>`
   lacks it, then `python3 <plugin>/scripts/merge_landing.py --no-ff <S>` (SKILL step 2 says
   why not a bare `git merge`). Conflicts whose combined intent is unclear go back to the
   author or the user. A merge commit commits the whole reviewed merge index: stage the resolved
   paths by name, read the complete staged diff, then commit without paths. The full gate runs on
   that result M, then the overlap check, then `promote_main.py <M>`. Its refusals are handled
   as in §1: a moved landing branch is merged into the integration branch and checked per §3.
4. **It records** on the issue: the landing branch's commit before, S, the landed commit, the
   reviewer, which commit each check covered, and the `Efficient design:` line as checked.

## 3. When the landing branch moved: reusing evidence

After merging a newer landing branch into a checked candidate, read the whole delta from the
checked commit to the new one, deletions and both sides of renames included:

- documents no gate or build consumes: their document checks are enough;
- code or inputs of a gate: the repository's declared fast landing gate, else its mandatory gate;
- your own fixes, a behavioural conflict resolution or a changed S: a new review and the full
  gate.

Record the reason any earlier result was reused. Another move of the landing branch needs
another such step.

## 4. What a landing leaves

A landed commit is "landed, awaiting push": never call it pushed or published. Report unpushed
landings, branches and worktrees at the end of a session. Failed or abandoned work stays on its
branch until the user decides; a correction after a landing is a new change or `git revert`.

## 5. Push the landing branch, on the user's word

1. `git fetch origin`. `origin/<landing>` must be an ancestor of the local `<landing>`
   (`git merge-base --is-ancestor origin/<landing> <landing>`). If not, someone else pushed:
   stop, bring their commits in through a task branch (SKILL step 2) and land again; never force.
2. Run `landing.py` again. If the mode is now pull request (a protection or a collaborator was
   added since), the push would be wrong or rejected: stop and tell the user. The landed commits
   then go out through a pull request from a branch at `<landing>`'s tip.
3. Tell the user what goes out (`git log --oneline origin/<landing>..<landing>`: the commits,
   their issues, the checks) and wait for an explicit yes for this push.
4. `git push origin <landing>`, never with `--force` or `+`, and without `-u`. A rejected push
   means stop and go back to 1.
5. Verify: `git ls-remote origin refs/heads/<landing>` equals `git rev-parse <landing>`.
6. The `cleanup-merged` skill: the sweep of landed worktrees and branches, the landed remote task
   branches, and closing each landed issue with its landing commit.
7. Report the pushed commit and what the cleanup removed and kept.

## 6. Undo a landing

With `git revert`, reading the actual history: an ordinary commit takes an ordinary revert; for
an independent landing, revert any later follow-up commits newest first, then
`git revert -m 1 <merge commit>`. Never move or rewrite the landing branch.
