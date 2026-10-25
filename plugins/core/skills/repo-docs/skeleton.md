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

## What to read for which work
| Work on | Read |
|---|---|
| <system> | `docs/design/<system>.md` |

## Standing permissions
None.
```

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

Newest first: `YYYY-MM-DD — <item> (#issue) — PR #n — merge <commit>`.
```

Also for a new repository, from the agentic-github-flow repository's `templates/` folder (the
installer keeps a copy in `~/.agentic-github-flow/templates/`): the secrets block for
`.gitignore` (`gitignore-secrets`) and the `pre-push` hook. On GitHub, a ruleset on `main` that
requires pull requests and the CI checks and blocks force-pushes; changing repository settings
is the owner's step, not an agent's.
A repository with a public website runs the `check-web-deploy` skill before its first deploy.
