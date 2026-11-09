# agentic-github-flow: current state

Checked on 2026-11-09 (v2).

## State

- Five plugins: core, security, web-deploy, guards and issue-chats; each version lives in its
  manifests (`plugins/<name>/.claude-plugin/plugin.json`). Not published in a directory yet.
- Maintainers: the author named in `NOTICE`.
- v2 brought the team edition up to date with the personal rules repository it was built from;
  the item-by-item inventory and its verdicts are on issue #3.
  - core: `requirements` and `open-issue` for the issue queue, an overlap check in `ship-change`,
    a cleanup sweep of merged and scratch branches, the Agent Skills standard
    (`plugins/core/skills/repo-docs/skill-standard.md`) and its checks in `tests/skills_format.py`.
  - security: the dependency audit names what it cannot audit and can ask osv-scanner for a
    second opinion; review-security has due dates, acceptances and stack notes, and
    `sources.md` (sources, read dates, the osv-scanner pin).
  - web-deploy: mail-domain and EU privacy checks.
  - guards: not updated yet. The delete guard, Codex prompt rules for deletes and Codex rules
    installed as copies wait on the branch `agent/v2-guards`; its open review findings are on
    their own issue (named on #3).
  - issue-chats (new, opt-in): one issue per chat, hand-over to the next ready issue, archiving
    only once a chat's work is on GitHub. The method: `plugins/issue-chats/skills/issue-handover/method.md`.
    The automatic start of the next chat needs the Claude Code CLI and desktop app (measured on
    macOS only); Codex uses its own thread tools; elsewhere the chat hands over a brief to paste.
- Not run yet: the live skill-choice probe for the new and changed descriptions, an end-to-end
  issue-chat chain in the desktop app or in Codex.

## Build, test, run

- Every offline test: `python3 tests/run_all.py` (`--require-all` in CI).
- One test: `python3 tests/<name>.py`. `tests/start_issue_chat.py` needs a pseudo-terminal: in a
  sandbox without one it runs only its refusal cases and exits 77 (skipped); CI runs it whole.
- Live skill-choice probe (spends tokens): `python3 tests/skill_triggers.py --client claude`.
- Validate the manifests: `claude plugin validate --strict .` and on each `plugins/<name>`.
- Try the installer without touching your own setup: `python3 tests/installer.py` runs it in
  temporary home folders with stand-in clients; `--real` uses the installed `claude` and `codex`.

## What to read for which work

| Work on | Read |
|---|---|
| the always-loaded rules | `rules/core.md`, `AGENTS.md` §Rule budget |
| a skill | its `SKILL.md`, `plugins/core/skills/repo-docs/skill-standard.md`, `tests/skills_format.py` |
| the installer | `tools/installer.py` (its docstring owns the behaviour), `tests/installer.py` |
| the guards | `plugins/guards/scripts/*.py` headers, `plugins/guards/policy/*.rules`, `tests/git_guard.py`, `tests/personal_data_guard.py`, `tests/codex_policy.py` |
| worktrees and cleanup | `plugins/core/scripts/*.py` headers, `plugins/core/skills/cleanup-merged/SKILL.md`, `tests/worktree_tools.py`, `tests/new_worktree.py`, `tests/overlap_check.py` |
| the security scanners | `plugins/security/scripts/*.py` headers, `plugins/security/skills/review-security/sources.md`, `tests/scan_secrets.py`, `tests/audit_dependencies.py` |
| issue chats | `plugins/issue-chats/skills/issue-handover/method.md`, `plugins/issue-chats/scripts/*.py` headers, `tests/next_issue.py`, `tests/start_issue_chat.py`, `tests/chat_archivable.py`, `tests/archive_guard.py` |

## Standing permissions

None.
