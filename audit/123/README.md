# Audit #123: working notes

Phase 1 of issue #123: an audit of the whole repository and a refactor plan. No refactor
commits before the maintainer approves the plan.

## When phase 1 is done

- End state: the plan is posted as a comment on #123 with measurements, cited sources, ranked
  proposals and the split into sub-issues; the issue carries the label `needs-user`; the
  overview chat is told.
- Proof: `gh issue view 123 -R IgorVerm/agentic-github-flow --json labels,comments`.
- Stop and report instead when: a measurement cannot be made with what this session may read,
  or two corrections of the same problem failed.

## Files here

| File | Holds |
|---|---|
| `context-cost.md` | bytes and estimated tokens by when they load |
| `duplication-drift.md` | facts with more than one owner, documents that contradict the code |
| `transcripts.md` | friction and unused parts, counted from session transcripts (counts only) |
| `clarity-skills.md` | each skill against the skill standard |
| `tooling.md` | installer, docs for the person, scripts, tests and CI |
| `sources-anthropic.md` | best practices: Anthropic |
| `sources-openai-skills.md` | best practices: OpenAI Codex, agentskills.io, others |
| `PLAN.md` | the plan as posted on #123 |

Base: `origin/main` at `e27f84f`, measured 2026-11-22.
