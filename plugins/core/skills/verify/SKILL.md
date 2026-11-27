---
name: verify
description: Prove a change met its goal - read the issue's check and the repository's Verification section, choose evidence in proportion, run the fast check, keep a task check on its issue, admit and prune standing checks. Use when starting an issue, before a push, when adding or removing a test, and when writing a Verification section.
---

# Verify a change against its goal

The yardstick comes from outside the change: the issue's `Check:` (its three kinds, and what the
agent does first and when the check is wrong: the `open-issue` skill) and the `## Verification`
section of `HANDOFF.md` (its rows: the `repo-docs` skill's skeleton). A check made for the
occasion confirms what its author already believed.

## Steps

1. **Read the issue's check and the section from the default branch**
   (`git show origin/<base>:HANDOFF.md`), so the change cannot rewrite what judges it.
2. **Choose the evidence in proportion:** the issue's own check first; then none for
   documentation, `fast` for most changes, `full` for a change under `critical paths`.
3. **Run `fast` while working and before every push** with
   `python3 <plugin>/scripts/verify.py fast` ([verify.py](../../scripts/verify.py)). Fix what
   fails; after two failed corrections of the same problem, stop and report.
4. **A check made for this issue goes on the issue** when it first fails, before the fix: a
   signed comment with the check in a code block and the command that runs it, and there it
   stays. It is a script that drives the product from outside, or, where it must be built with
   the code, a patch that adds it, never committed. It becomes a standing check only when it
   protects a critical system and passes the admission test.
5. **Write the `Verified:` line** in the pull request body, or the landing comment in
   local-main mode: `Verified: <kind>: <evidence>`, the kind `goal`, `tests`,
   `standing-check`, `run`, `seen`, or `none` with its reason; several joined by `;`. A check
   from step 4 is named by its comment's URL.

## Which checks are kept, in every repository

- **A task check** proves one issue's goal and lives on that issue, never in the repository.
- **A standing check** lives under `check paths`, runs in `fast` when the change touches what it
  protects and in `full` always, and exists only for a critical system.
- **The admission test.** A standing check protects a path under `critical paths` and fails on
  a plausible defect nothing else catches. Show it: name the defect as a change to the code (a
  condition inverted, a branch removed, a value read from the wrong place), make it, see the
  check fail, restore the code; for a bug fix, the check fails on the commit before the fix.
  The line records `standing-check: <test> fails when <defect>`. Refused: a check outside the
  critical systems, a test that restates the implementation, a test of someone else's code, a
  second test for a defect one already catches (it becomes a case of that one), a test in
  place of a judgment. No coverage target. A formatter, linter or type checker that `fast`
  names is a tool, neither admitted nor pruned; a lint check written here is a standing check.
- **The pruning rule.** A standing check stays while it protects a path under `critical paths`
  and a named defect still makes it fail; every other is removed, its reason in the commit.
  Having caught something once keeps no check; neither their number nor their seconds decide.
  The first pass comes when a repository adopts the section, later ones when the list of
  critical paths changes. Who approves a removal: the `removed checks` row.
- **A flaky check** is not skipped, given a sleep or retried until green: fix its cause, or
  delete it with the reason written down.
- **`critical paths`** is listed by an audit agent. An agent working on a change never edits it
  for that change; a part it finds missing goes on an issue for the next audit.

Writing a repository's section for the first time: [writing-the-section.md](writing-the-section.md).
