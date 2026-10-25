# agentic-github-flow: current state

Checked on 2026-10-25.

## State

- Version 0.1.0 of all four plugins: core, security, web-deploy, guards. Not published yet.
- Maintainers: the author named in `NOTICE`.
- Lanes skills (requirements, open-issue, lane-handover, archive-finished-chats) are planned for
  a second release, after a pilot.

## Build, test, run

- Every offline test: `python3 tests/run_all.py` (`--require-all` in CI).
- One test: `python3 tests/<name>.py`.
- Live skill-choice probe (spends tokens): `python3 tests/skill_triggers.py --client claude`.
- Validate the manifests: `claude plugin validate --strict .` and on each `plugins/<name>`.
- Try the installer without touching your own setup: `python3 tests/installer.py` runs it in
  temporary home folders with stand-in clients; `--real` uses the installed `claude` and `codex`.

## What to read for which work

| Work on | Read |
|---|---|
| the always-loaded rules | `rules/core.md`, `AGENTS.md` §Rule budget |
| a skill | its `SKILL.md`, `tests/skills_format.py` |
| the installer | `tools/installer.py` (its docstring owns the behaviour), `tests/installer.py` |
| the guards | `plugins/guards/scripts/*.py` headers, `tests/git_guard.py`, `tests/personal_data_guard.py`, `tests/codex_policy.py` |

## Standing permissions

None.
