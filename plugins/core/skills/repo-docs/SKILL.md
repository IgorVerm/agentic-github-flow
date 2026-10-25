---
name: repo-docs
description: Layout and upkeep of a repository's agent documents (AGENTS.md, HANDOFF.md, ROADMAP.md, DESIGN_DECISIONS.md, archive, design docs). Use when setting up a new repository, when deciding where a piece of information belongs, or when slimming or restructuring these documents.
---

# A repository's documents

Every line of documentation answers one question, and the question decides the file. Each fact
has one home; everything else links to it.

| File | Answers | Holds | Keep it |
|---|---|---|---|
| `AGENTS.md` | What must every agent here always respect? | Only this repository's own rules: its invariants, its deliberate deviations from the general rules (named as such), where outside content enters. `CLAUDE.md` is the one line `@AGENTS.md`. | Short: under 100 lines. Both clients load it in every session. |
| `HANDOFF.md` | What is true now, and how do I build, test and run? | Current state with the date it was checked, the commands, a routing table ("for this kind of work, read that document"), standing permissions. | Under 200 lines. Rewritten, never appended to. |
| GitHub issues | What is not done? | Every piece of concrete work, with its status. | The only queue. |
| `ROADMAP.md` | Where is this going? | Direction, phases, dependencies, links to milestones. | No task list, no finished items. |
| `DESIGN_DECISIONS.md` | What did the decision-makers decide, and why? | One entry per ruling: the decision in their words, why, what was rejected, what it binds. Newest first. | Re-opening one needs the person who decided. |
| `archive_implementations.md` | What landed? | One line per merge: date, item, issue, pull request, merge commit. | Not required reading. |
| `docs/design/<system>.md` | How does this system work, and why this way? | The design of record per system: mechanism and rationale in the present tense. | Read when working on that system. |
| `docs/archive/` | What used to be true? | Superseded documents, each naming its replacement. | Never on a reading route. |

Who decides is named in `AGENTS.md`: the user who owns the repository, or its maintainers.
Rules that apply to one part of the code go in an `AGENTS.md` inside that directory (with a
one-line `CLAUDE.md` importing it), so both clients load them only when working there.
A procedure with several steps becomes a skill in `.agents/skills/<name>/SKILL.md`, with
`.claude/skills/<name>` as a symlink to it, so both clients load it on demand.

## What goes where

- Something changed in the present state: rewrite the line in `HANDOFF.md`. Delete what stopped
  being true.
- Work found or finished: the issue. Never a checklist in a document.
- A ruling on architecture, method, scope or a deferral: `DESIGN_DECISIONS.md`, dated, in the
  words of the person who decided.
- A lasting fact about how a system works: its design document. Describe the mechanism, not the
  history of building it.
- A measurement: name the command that produces it instead of copying the number.
- A log of what happened in a session or a run: nowhere. Git, the pull request and the issue
  already have it.
- A document was superseded: move it to `docs/archive/` with a line naming its replacement.

## Checks before a change is merged

- No document describes a state the change made untrue.
- `HANDOFF.md` has no dated journal, no open-task list and no commit hashes other than a
  current baseline; its "checked on" date matches its content.
- A standing permission whose scope ended is deleted.
- Names that can be searched (symbols, headings) instead of line numbers.

A new repository starts from [skeleton.md](skeleton.md).
