---
name: review-change
description: Review another agent's pull request or branch as the independent reviewer - confirm this session did not write it, run the client's code review and review-security where it applies, check the Efficient design line, and post the verdict for the exact head commit with the script whose format merge_pr.py accepts. Use when asked to review a pull request by its number, or another agent's branch or change before it lands.
---

# Reviewing another agent's change

You are the context that did not write the change, which the review route of the `ship-change`
skill asks for. You find and report: you do not fix the change unless asked, never push to its
branch, never merge it. Your verdict names one commit. Under a standing grant `merge_pr.py`
merges on it, so the comment is written and posted by
[review_verdict.py](../../scripts/review_verdict.py) (its header owns the format), never by
hand. `<plugin>` below is the folder two levels above this skill's folder; `<n>` is the pull
request's number.

## 1. Did this session write it?

If this session wrote or edited any commit of the change, or planned it with the author, stop
and tell the user: the review needs a fresh session, or a subagent given only the pull request
number and the issue, without the author's reasoning. Every agent posts under the same account,
so nothing on GitHub can tell; your word in the verdict is the attestation.

## 2. Pin the commit you review

`python3 <plugin>/scripts/review_verdict.py head <n>` prints the head SHA: `<sha>` below. That
commit, and nothing pushed after it, is what you review and what the verdict names. Fetch it:
`git fetch origin refs/pull/<n>/head`, and check that `git rev-parse FETCH_HEAD` prints `<sha>`.

## 3. Read the context

The pull request body, the issue it closes, the repository's `AGENTS.md` and `HANDOFF.md` (what
the repository already enforces, so you judge the change against it), and the whole diff:
`git diff origin/<base>...<sha>`, `<base>` the pull request's base branch.

## 4. Review

- **Code review:** Claude Code `/code-review <n>`; Codex `/review` with custom instructions to
  review `git diff origin/<base>...<sha>`. Read what it reports against the diff yourself: a
  finding you cannot confirm is dropped or marked uncertain, and what it missed is still yours.
- **Security:** when the change touches authentication, permissions, secrets or environment
  configuration, dependencies or deployment, the `review-security` skill too. Not installed:
  say so in the verdict.
- **Efficient design:** check the body's `Efficient design:` line against the diff (the
  `efficient-design` skill, §At review). A missing or wrong line, or work growing with all data
  where what changed would do and no bound is stated, is a finding.
- **Overlap:** the body's `Overlap` line (the `ship-change` skill's step 5). A conflict it names
  that the change does not settle is a finding.
- **Tests:** the checks the repository requires for this kind of change ran and pass (the
  pull request's CI, or run them). A weakened test or gate is a finding.

A finding is a defect the change must fix before it lands: file and line, what goes wrong in
which case, and the fix it needs. Advice that need not block goes into the approval's note. An
open question you cannot settle from the code is a finding, not an approval.

## 5. Post the verdict

`<agent>` is the name you sign comments with (`Claude Code`, `Codex`), without parentheses.

- **No finding:** `python3 <plugin>/scripts/review_verdict.py approve <n> --sha <sha> --agent
  "<agent>" --note "<what you checked, review-security yes or no, the Efficient design line,
  advice>"`.
- **Findings:** write them to a file outside the repository, one numbered item each, then
  `python3 <plugin>/scripts/review_verdict.py findings <n> --sha <sha> --agent "<agent>"
  --body-file <file>`.

`--dry-run` shows the comment without posting. What the exit codes mean:

- 0: posted. Report the verdict, `<sha>` and the comment's URL to whoever asked.
- 1, *the head is …, not …*: the author pushed during the review. Go back to step 2; only the
  commits since `<sha>` need reading. Nothing was posted.
- 1, *moved while posting*: the comment was posted and covers `<sha>` only. Review the new
  commits and post again for the new head.
- 2: a usage error or GitHub not read; nothing was posted. Fix the call and run it again.

## A branch without a pull request

In local-main mode there is no pull request and no script to run: the author hands over an
exact commit S on the issue. Run steps 1, 3 and 4 on S (`git diff <landing>...S`); post the
findings on the issue, signed `🤖 <agent> (review):` and naming S, or land S yourself as §2 of
the `ship-change` skill's `local-main.md` says.

## Gotchas

- An approval covers `<sha>` only. After a new commit of the author, `merge_pr.py` refuses
  until a new review approves the head; only conflict-free merges of the base may follow an
  approval.
- Never edit a verdict comment; post a new one. `merge_pr.py` counts the newest signed verdict
  of the account, and an edited one never approves.
- A request for changes on GitHub by someone with write access still blocks the merge after
  your approval; it is theirs to withdraw.
