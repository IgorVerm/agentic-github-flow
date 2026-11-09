# agentic-github-flow: design decisions

Rulings of the maintainers named in `HANDOFF.md`, newest first, with their words. Detail lives on
the linked issue.

## Agents may merge their own pull request under a standing grant, 2026-11-09

**Decision (the maintainer):** "ja zo wil ik dat het werkt" (that is how I want it to work), on
the rule below; for what is excluded, "Not rules, guards, CI (recommended)".
**What:** in pull-request mode an agent merges its own pull request without a word for that pull
request only where a standing grant allows it: the repository's `HANDOFF.md` §Standing
permissions, or an overlay the user installed. It merges through
`plugins/core/scripts/merge_pr.py`, and only when all hold: pull-request mode; not a draft and
merge state CLEAN, no review requesting changes; every required check (the ruleset's or branch
protection's, and the `required checks` row) passed on the head, so every platform; the newest
signed review by the user's own account (agents post under it), role `review`, by an agent
that did not write the change, approves the head commit (or an earlier one followed only by
conflict-free merges of the base branch, which need green checks again and no new review); the
overlap check's result in the body; no path that merges only on the user's word.
**Excluded, merged only on the user's word:** `rules/core.md` and a repository's own rules
(`AGENTS.md`, `CLAUDE.md`), a personal or company overlay, the guards, permission settings,
hooks and plugin manifests beyond their versions, the installer, CI and `.github/`
configuration, deployment configuration, the merge gate itself (`merge_pr.py`, `landing.py`),
and the `HANDOFF.md` sections that hold the grant and these settings (§Standing permissions,
§Landing settings); a repository adds patterns in `## Landing settings`. Skills, scripts,
tests and documents may merge automatically. Paths compare without case.
**Why:** a green CI on three systems and an independent review are what the user's word checked
for; the excluded paths change what every later session may do, so they stay with the user.
**Where the grant lives:** this repository grants nothing (`HANDOFF.md`: Standing permissions:
None); the maintainer's grant is in a private overlay, so it never extends to other
contributors. A bare `gh pr merge` stays an ask rule in the guards.
**Binds:** `rules/core.md` §Git, `plugins/core/scripts/merge_pr.py`, `tests/merge_pr.py`,
`plugins/core/skills/ship-change/SKILL.md` steps 1, 4 and 7.
**Detail:** issue #13.

## Landing mode: local main or pull request, per repository, 2026-11-09

**Decision (the maintainer):** "er moet een automatische landing modus in de teams zitten, kies
tussen lokale main of pull requests op basis van industry standaarden" (an automatic landing
mode in the team edition, choosing local main or pull requests by industry practice). On the
open points: "Always worktree" (local-main mode also works on a branch in a worktree and lands by
a checked fast-forward, never directly on main) and "Reviewer lands" (a large or risky change is
reviewed and landed by an agent that did not write it). The `landing branch` setting stays.
**What:** `plugins/core/scripts/landing.py` decides at every landing (its header owns the rule);
`ship-change` and `cleanup-merged` follow both modes; this repository declares pull request.
**Binds:** `rules/core.md` §Git, `plugins/core/scripts/landing.py`, `promote_main.py`,
`plugins/core/skills/ship-change/`, `cleanup-merged`, the issue-chats plugin.
**Detail:** issue #13.
