---
name: open-issue
description: Open a GitHub issue that an agent can pick up - search for a duplicate, write a body with the first step, the check and the code paths, and label it ready (agent-ready), optionally with an area and priority label, or needs-spec when its requirements are open. Use whenever a new issue is opened - a defect the user reports, a defect seen in passing, a follow-up found during work, or new work the user asks for.
---

# Open an issue an agent can pick up

An issue is the work queue's unit: whoever takes it, a person or an agent, starts from its body
alone. The ready label says that the body is enough to start; an issue without it waits. Where
the optional `agentic-github-flow-issue-chats` plugin runs, issue chats pick their next task from
the open, unassigned issues with the ready label, so an issue without it is picked up by nobody.

**Labels.** The ready label is `agent-ready` and the requirements label `needs-spec`, unless the
repository's `HANDOFF.md` has a section `## Issue chats settings` whose rows `ready label` or
`requirements label` name others; read them there first. A label the repository does not have
yet: creating it (`gh label create`) changes the repository's settings on GitHub, so ask the
user first, and without a yes open the issue without that label and say so. The issue gets no
assignee here: an assignee is the claim of whoever works on it, and the overlap check
(`overlap_check.py` in this plugin's `scripts/`) reads assigned issues as work in progress.

1. **Search first:** `gh issue list --state open --search "<key words>"`. If an open issue
   covers it, comment there (with the user's words if they are new) instead of opening a
   second one.
2. **Write the issue.** The body starts with `🤖 <agent> (<role>):`, then: what happens (the
   reporter's own words, quoted, when the user reported it); what is known from the code or a
   measurement and what is not; the first step; the check that proves it fixed; the sections
   to read (named sections, not whole documents) and the code paths it will touch, which the
   overlap check reads; and `after #n` for each issue it waits on. Size test: it fits one
   session's context and one coherent diff, one pull request. If not, or if the first step
   needs an answer nobody has yet, its requirements are open (step 3).
3. **Labels:** the ready label; at most one area label when the repository uses area labels
   and one fits what must change (not where the symptom was seen); other labels as the
   repository's documents say; `priority: critical` for a Critical security finding (the
   severity table of the `review-security` skill, when installed), `priority: high` for a
   defect the user hit or one that blocks a milestone. Critical goes before high. New work
   whose requirements are open gets the requirements label and no ready label, its body names
   what is open, and the `requirements` skill specifies it. A defect stays ready even when its
   fix needs a question answered: that question goes on the issue, addressed to whoever
   decides.
4. **Say so if it cannot wait.** A `priority: critical` or `priority: high` issue: its number
   in your report to the user, who decides whether someone starts on it now.
