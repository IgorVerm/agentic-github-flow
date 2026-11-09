---
name: requirements
description: Run a requirements chat - interview the user about new work, write the specification on a parent GitHub issue and open one ready sub-issue (agent-ready) per session-sized package for agents to pick up. Use when the user asks for a requirements chat, for issues labelled needs-spec, or to turn new work into ready issues. For a single build without issues, spec-first.
---

# Requirements: specify new work and open ready issues

How to interview is `spec-first` steps 1 and 2; how to search for a duplicate, write an issue
and which labels it gets is `open-issue`; neither is repeated here. This skill owns the
definition of ready below. The ready and requirements labels are the ones `open-issue` names
(`agent-ready` and `needs-spec` unless the repository's `HANDOFF.md` section
`## Issue chats settings` names others). Where the optional `agentic-github-flow-issue-chats`
plugin runs, issue chats pick the packages up; without it, whoever takes the issue does.

**The chat.** One topic per chat: what the user named, or one open issue with the requirements
label. It builds nothing.

**Where issue chats run** (the issue-chats plugin is installed, the repository's `HANDOFF.md`
has `## Issue chats settings`, and the desktop app's session tools are present), the chat keeps
an issue chat's lifecycle; the title form and the settings are owned by that plugin's
`issue-handover` skill, `method.md` §2 and §1. Its first steps: set its title with
`set_session_title` on `"self"`, `<title prefix>Requirements · #<n> · <topic>` when it started
from issue `<n>`, otherwise `<title prefix>Requirements · new · <topic>`; file itself under the
settings' sidebar section (`list_sections`, `create_section` only if it is missing,
`move_sessions` with `["self"]`); and work from the start in a worktree of its own, made with
the settings' worktree tool for `requirements-<short topic>`, never in the primary checkout, so
any file change below is made there. It renames itself at step 5 and archives itself at step 6.
Elsewhere (without that plugin or section, outside the desktop app, in Codex) these steps do
not apply and the chat ends with its report.

**The issues hold the work.** The specification and the packages live on GitHub: the parent
issue and its sub-issues. The chat changes a file in the repository only where an issue cannot
own the fact: the user's rulings in `DESIGN_DECISIONS.md` (or where the repository keeps its
decisions), a design document only when the design outlives the work, a short pointer from an
existing document to the issue. Such edits stay minimal, are made on a branch in a worktree of
their own and go to a pull request by the `ship-change` skill, with the user's yes before the
push.

1. **Read before asking.** Read the code of the area, the open issues (overlapping ones and the
   requirements label's queue), the repository's decisions and the design sections that bear
   on it; a subagent per narrow question keeps this out of your context. A question the
   repository answers is not put to the user; a conflict with an earlier ruling is named to
   the user as one, because re-opening it is theirs.
2. **Interview in rounds** (`spec-first` step 2) until nothing material is open. Claude Code:
   its question tool, at most four questions a round, each multiple choice with the
   recommended option first and its reason. Codex: plain questions, in plan mode (`/plan`).
   Ask the hard parts: behaviour, edge cases, trade-offs, what must not change, how done is
   seen. What is immaterial becomes a stated assumption.
3. **Draft the specification and the split,** nothing on GitHub yet:
   - **the parent:** the goal in the user's words, quoted; context; scope and out of scope; the
     end-to-end check that proves the whole; the decisions with the user's words; the packages
     in order. It stands on its own: someone who reads only it and the sections it names can
     build;
   - **the packages:** one per session-sized piece, each meeting the definition of ready, with
     at most one area label, and `after #n` for what it waits on. Work that fits one package is
     one issue, with no parent;
   - **the rulings:** each decision of the user's in this chat, with their words, as an entry
     for the repository's decisions.
4. **The user confirms.** Show the package list: title, area, check and order of each, and the
   rulings to record. The confirmation is the approved scope; a change goes round step 3 again.
5. **Create.** The parent first, then each package with `gh issue create --parent <parent>`
   when `gh issue create --help` lists that flag; otherwise name the parent in the body and
   tell the user. Where issue chats run, rename this chat to
   `<title prefix>Requirements · #<parent> · <topic>` as soon as the parent exists. Bodies
   start `🤖 <agent> (requirements):`. Labels: each package the ready label (and its area
   label); the parent the ready label with `after #n` for each package,
   so whoever picks it up runs its end-to-end check and closes it once its packages are merged
   and the check passed; other labels as the repository's documents say. An issue that carried
   the requirements label: comment the specification on it, remove that label, add the ready
   label (or make it the parent). Record the rulings by the route above. Finally a comment on
   the parent listing its packages.
6. **Report and end.** Tell the user, in their language: the parent, each package with its
   area, the rulings' branch or pull request, what waits for them (a push, a review). Start no
   build, no successor and no issue chat: the packages wait for whoever picks them up (a
   `priority: high` one: `open-issue` step 4). Where issue chats run, then run the worktree
   check on this chat's worktree (the issue-chats plugin's `scripts/chat_archivable.py
   <worktree>`) and on `ok` archive this chat (`archive_session` with `"self"` and a short
   `reason`), telling the user first; on `keep:` stop with that reason. A rulings branch that
   waits for the push keeps the chat; after the user's yes and the push it archives the same
   way.

## Definition of ready

An issue of new work gets the ready label only when all of these hold; until then it carries the
requirements label and no ready label. A defect or follow-up written by `open-issue` (its steps
2 and 3) is ready as written.

- **Goal, Context, Constraints, Done when** as sections of the body.
- **An acceptance check:** a command, or a concrete observation someone can make.
- **Sections to read:** named sections of documents and the code paths it will touch, not whole
  documents (the overlap check reads the paths).
- **Out of scope,** stated.
- **Dependencies:** `after #n` for each issue it waits on, or none.
- **Fits one package:** one session's context, one coherent diff, one pull request.
- **No open question the first step needs.** A later question may stay open, on the issue.
- **What the repository's own documents add** to this definition.

## Stays the user's

Confirming each specification and split; every ruling; re-opening a decision; cancelling work;
any push.
