# Starter documents for a new repository

`CLAUDE.md`:

```markdown
@AGENTS.md
```

`AGENTS.md`:

```markdown
# <Project>: rules of this repository

The general rules come from agentic-github-flow (installed per user). This file adds only what
is specific to this repository. Decisions here are made by: <the owner or the maintainers, by
GitHub handle>.

## Deviations from the general rules
None.

## Rules of this repository
- <an invariant every change must keep, with its reason>

Commands, current state and the reading route: `HANDOFF.md`.
```

`HANDOFF.md`:

```markdown
# <Project>: current state

Checked on YYYY-MM-DD.

## State
- <what exists and works, what is in progress and where (issue links), what is known broken>

## Build, test, run
<the commands; the checks a pull request must pass>

## Verification

| Setting | Value |
|---|---|
| `fast` | <the command for the cheap check; it takes the changed paths or selects by itself> |
| `full` | <the command for everything> |
| `drive` | <how to start the product and look at it, or the project skill or script that does; `none` with the reason> |
| `check paths` | <where checks live, as patterns> |
| `critical paths` | <the critical systems, as path patterns> |
| `verification gate` | `off` |
| `removed checks` | `maintainer` |

- `<critical path pattern>`: <what would be lost that cannot be taken back, or would stop the work, if it broke unnoticed>

## What to read for which work
| Work on | Read |
|---|---|
| <system> | `docs/design/<system>.md` |

## Standing permissions
None.
```

The `## Verification` section, read by the `verify` skill from the default branch:
- `critical paths` is written by an audit agent, one reason line per entry under the table, as
  an audit change (the `verify` skill's `writing-the-section.md`); the other rows change on the
  maintainer's word.
- `verification gate` is `off`, `observe` (report what would be refused) or `enforce` (refuse
  the unasked push and the automatic merge); `off` when the row is missing.
- `removed checks` names who approves a change that removes checks: `maintainer`, or
  `reviewer`, which the maintainer sets once the repository's first pruning pass has merged;
  even then the removal of a check that protects a critical path waits for the maintainer.
  `maintainer` when the row is missing.

`ROADMAP.md`:

```markdown
# <Project>: roadmap

Concrete work lives in GitHub issues on <owner>/<repo>. This file holds direction only.

## Direction
## Phases (milestone links) and dependencies
```

`DESIGN_DECISIONS.md`:

```markdown
# <Project>: design decisions

Rulings, newest first. Re-opening one needs the person who decided and a new entry.

## <decision>, YYYY-MM-DD
**Decision (<who>):** "<their words>" **Why:** … **Rejected:** … **Binds:** …
```

`archive_implementations.md`:

```markdown
# <Project>: what landed

Newest first: `YYYY-MM-DD — <item> (#issue) — PR #n — merge <commit>`, or in local-main mode
`YYYY-MM-DD — <item> (#issue) — landed <commit>`.
```

Also for a new repository, from the agentic-github-flow repository's `templates/` folder (the
installer keeps a copy in `~/.agentic-github-flow/templates/`): the secrets block for
`.gitignore` (`gitignore-secrets`) and the `pre-push` hook, which runs the secret scan and the
personal-data check from that clone on every push. On GitHub, a ruleset on `main` that
requires pull requests and the CI checks and blocks force-pushes; changing repository settings
is the owner's step, not an agent's.
A repository with a public website runs the `check-web-deploy` skill before its first deploy.
