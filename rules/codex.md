## In Codex

The skills are written once for every client. Where one names a Claude Code tool, Codex uses:

- **A code review** (`review-change` step 4): `/review` with custom instructions to review
  `git diff origin/<base>...<sha>`.
- **A security review** (`review-security` step 4): `/review` with the focus text of its
  `checklist.md` §Focus for a client review.
- **Interview questions** (`requirements`, `spec-first`): plain questions, in plan mode
  (`/plan`).
- **The signature:** `Codex` with its model.
- **Issue chats:** the `codex-issue-chats` skill replaces the Claude-specific calls of
  `issue-handover`.
- **Writing a skill** (the `repo-docs` skill's standard): Codex reads a repository's skill at
  `.agents/skills/<name>/SKILL.md`; `.claude/skills/<name>` is a symlink to that folder for
  Claude Code. A skill only the user starts also sets `policy.allow_implicit_invocation: false`
  in its `agents/openai.yaml`. Codex's first skill list takes at most 2% of the context window,
  or 8,000 characters when the window is unknown, and shortens descriptions first
  (<https://learn.chatgpt.com/docs/build-skills>, read 2026-10-30).
