# agentic-github-flow: current state

Checked on 2026-11-11 (v2, the landing modes of #13, the sandbox-network guard of #20, the pre-push checks of #40, the reviewer skill of #39, issue chats switched on by #51, the unasked push and the per-repository merge switch of #26).

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
  - guards: a delete guard for Claude Code (asks, never denies); Codex prompt rules for deletes;
    Codex rules files installed as copies, because Codex skips a symlinked rules file; the
    personal-data guard's settings `exempt-dirs` and `local-mcp`, and its Codex hook installed by
    `--guards` (#15); the opt-in sandbox-network guard for Claude Code (`--guards sandbox`,
    #20), wired by the installer in `~/.claude/settings.json`, not by the plugin's hooks.
  - issue-chats (new, opt-in): one issue per chat, hand-over to the next ready issue, archiving
    only once a chat's work is on GitHub (also when a successor's pushed branch holds it); a
    side chat started with `start_session` only once its work landed or its pull request merged. The method: `plugins/issue-chats/skills/issue-handover/method.md`.
    The automatic start of the next chat needs the Claude Code CLI and desktop app (measured on
    macOS only); Codex uses its own thread tools; elsewhere the chat hands over a brief to paste.
- Efficient design (#37): the core skill `efficient-design` is a checklist at design and review
  (work per frame, request or job run grows with what changed, not with all data), and the core
  rule *Work grows with what changed* has the author write an `Efficient design:` line in the
  pull request body or landing comment and the reviewer check it.
- Landing modes (#13): finished work lands through a pull request or on local main, detected
  per repository at every landing by `plugins/core/scripts/landing.py` (its header owns the
  rule; a copy in the issue-chats plugin). Local main lands with `promote_main.py` and pushes
  the landing branch on the user's word (`plugins/core/skills/ship-change/local-main.md`). The
  setting `## Landing settings` can fix the mode and name a landing branch; the worktree,
  overlap and cleanup scripts and `templates/pre-push` follow that branch.
- Frozen .claude (#50, `DESIGN_DECISIONS.md`): the landing branch is merged in with
  `plugins/core/scripts/merge_landing.py`, which commits the ordinary merge inside the Claude
  Code sandbox and keeps the worktree's `.claude/` and `.mcp.json` on disk as the chat started
  with them; the cleanup and archive checks accept those paths while they match its manifest.
  Not measured yet in a real issue chat whose landing branch changed `.claude/`.
- Automatic merging (#13, narrowed by #26, `DESIGN_DECISIONS.md`): off by default, switched on per
  repository by the row `automatic merge` | `on` in `HANDOFF.md` §Landing settings, next to the
  landing mode (`landing.py` owns it, `--explain` reports it); an overlay cannot switch it on. There
  `merge_pr.py --ready` marks an agent's own draft ready and merges it when its checks, review,
  overlap line and paths allow it. It is off here (Landing settings below). The review it needs
  comes from the core skill `review-change` (#39), whose `review_verdict.py` writes the verdict
  comment and owns its format; `merge_pr.py` parses it through the same module.
- Unasked push (#26): under a standing grant (`HANDOFF.md` §Standing permissions or an overlay)
  an agent pushes its own task branch in pull-request mode and opens its pull request through
  `plugins/core/scripts/push_branch.py`, which refuses without the pre-push hook, for a
  protected path or without the overlap line, and pushes with `AGENTIC_GITHUB_FLOW_UNASKED_PUSH`
  set. After the pull request is open, `ship-change` step 8 runs the CI monitor, the
  independent review, the fixes and the merge; an issue chat stays until the merge and its
  cleanup (`issue-handover` step 7).
- The pre-push hook (#40): besides force pushes, tag moves and unmerged deletions,
  `templates/pre-push` refuses every push whose outgoing commits carry a secret
  (`scan_secrets.py --commits`) or personal data (`pre_tool_personal_data.py --commits`), run
  from the installed clone `~/.agentic-github-flow`, failing closed. Both skip the content of
  a file that is binary in a commit and no UTF-16 text (#55: `.glb` model data read as
  addresses); its name is still judged. Its protected-path check
  (`plugins/core/scripts/push_paths.py`, the paths of `merge_pr.py`) runs only when
  `AGENTIC_GITHUB_FLOW_UNASKED_PUSH` is set: `push_branch.py` sets it for its own push. This
  repository's tests build their planted tokens and addresses by concatenation, or the hook refuses
  the push that carries them.
- Worktree clones (#19, `DESIGN_DECISIONS.md`): on macOS `new_worktree.py` makes the tracked
  files APFS clones of the primary checkout's by default, checked by git to equal a plain
  `git worktree add`; `--no-clones` or `AGENTIC_GITHUB_FLOW_CLONES=0` turns it off. Elsewhere
  nothing changes. `clone_dedupe_worktree.py` turns an existing worktree's files into clones.
  Measured 2026-11-11 with 512 MiB of tracked files: `df` 507.8 MiB
  for a plain worktree, 0.0 MiB with clones.
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
| the guards | `plugins/guards/scripts/*.py` headers, `plugins/guards/policy/*.rules`, `tests/git_guard.py`, `tests/delete_guard.py` (cases in `tests/delete_guard_cases.py`; `tests/delete_guard_differential.py` checks it never asks less than before issue 4), `tests/personal_data_guard.py`, `tests/sandbox_network_guard.py` (with `--guards sandbox` in `tools/installer.py`), `tests/codex_policy.py` |
| automatic merging and the unasked push | `plugins/core/scripts/merge_pr.py`, `push_branch.py` and `review_verdict.py` headers, `plugins/core/skills/ship-change/SKILL.md` steps 6 to 8, `plugins/core/skills/review-change/SKILL.md`, `DESIGN_DECISIONS.md`, `tests/merge_pr.py`, `tests/push_branch.py`, `tests/review_verdict.py` |
| landing modes | `plugins/core/scripts/landing.py` and `promote_main.py` headers, `plugins/core/skills/ship-change/` (`SKILL.md`, `local-main.md`), `tests/landing.py`, `tests/promote_main.py` |
| worktrees and cleanup | `plugins/core/scripts/*.py` headers, `plugins/core/skills/cleanup-merged/SKILL.md`, `tests/worktree_tools.py`, `tests/new_worktree.py`, `tests/overlap_check.py` |
| merging the landing branch in the sandbox | `plugins/core/scripts/merge_landing.py` header, `frozen_unexplained` in `plugins/core/scripts/work_proof.py`, `plugins/core/skills/ship-change/SKILL.md` step 2, `DESIGN_DECISIONS.md`, `tests/merge_landing.py` |
| the security scanners | `plugins/security/scripts/*.py` headers, `plugins/security/skills/review-security/sources.md`, `tests/scan_secrets.py`, `tests/audit_dependencies.py` |
| the pre-push hook | `templates/pre-push` header, `plugins/core/scripts/push_paths.py`, the push check in `plugins/guards/scripts/pre_tool_personal_data.py`, `tests/pre_push_checks.py`, its older refusals in `tests/worktree_tools.py` (`PrePushTests`) |
| issue chats | `plugins/issue-chats/skills/issue-handover/method.md`, `plugins/issue-chats/scripts/*.py` headers, `tests/next_issue.py`, `tests/start_issue_chat.py`, `tests/chat_archivable.py`, `tests/archive_guard.py` |

## Landing settings

This repository is the team edition others install, and its changes are reviewed as pull
requests, whatever the detection would say about its one writer.

| Setting | Value |
|---|---|
| landing | `pull request` |

## Issue chats settings

The method: the `issue-handover` skill's method file (agentic-github-flow-issue-chats plugin). This
section switches on its standing permission in this repository: picking and claiming the next ready
issue, starting its chat, and archiving chats that pass the worktree check. Pushes, merges and
ready-marking follow the `ship-change` skill: the user's word, unless a standing grant or the
`automatic merge` row of §Landing settings says otherwise. Switched on by Igor, 2026-11-11: "zet de
knop aan" (#51).

| Setting | Value |
|---|---|
| model and effort | `claude-opus-5-5`, `high` |
| ready label | `agent-ready` |
| area labels | none |
| spread over areas | `no` |
| sidebar section | `agentic-github-flow` |

## Standing permissions

None beyond §Issue chats settings.
