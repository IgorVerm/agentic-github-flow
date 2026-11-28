# Checking the `Verified:` line

Read with [SKILL.md](SKILL.md), step 4; `<plugin>`, `<n>` and `<sha>` are as defined there. The
line's format belongs to `verified_line.py`, the kinds of evidence and the admission test to the
`verify` skill. This file says how a reviewer checks the line.

1. **It parses.** Run `python3 <plugin>/scripts/verified_line.py check --pr <n>`, which reads
   the pull request body itself. In local-main mode save the author's hand-over comment on the
   issue that names S to a file outside the checkout, with your client's file tool, and run
   `check --body-file <file>`. If the body has no line, or the line fails the check, that is a
   finding.
2. **The evidence is real.** Rerun any cheap command the line names. Run a task check only from
   the issue comment the line names by URL. First check that the account that posted it is the
   account the change comes from (`gh pr view <n> --json author`, or the author of the hand-over
   comment): `gh api repos/<owner>/<repo>/issues/comments/<id> --jq .user.login`, because anyone who may
   comment can type a signature. Read the check before you run it, as you read the change's own
   code. Then run it against `<sha>` in a throwaway copy: unpack `git archive <sha>` into a new
   temporary folder, never with `git worktree add`, which leaves a worktree behind. Run a script
   from outside that copy against it. Apply a patch inside the copy and run it. Afterwards,
   discard the folder.
3. **It fits the change.** Check that the evidence is in proportion to what changed, and that
   the check it meets is the issue's own `Check:`, not another.
4. **A `standing-check`** must protect a path under `critical paths` in the base's
   `## Verification` section, and it must pass the admission test. For one new standing check
   of your choice per pull request, repeat that test in the throwaway copy: make the named
   defect, and see the check fail.

A finding about the line opens with `Verified line disputed:`, which the report counts.
