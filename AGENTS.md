# agentic-github-flow: rules for maintaining this repository

This file is for agents and people changing this repository. The rules every user's sessions
load are `rules/core.md`, not this file. Decisions here are made by the maintainers listed in
`HANDOFF.md`.

## Deviations from the core rules

None. The core rules apply here too, through the maintainer's own install.

## Rules of this repository

- **Rule budget.** `rules/core.md` loads in every session of every user, so it stays under
  8,000 bytes (`wc -c`) and a rule is added only after the same mistake happened twice. A rule
  that must hold every time without exception becomes a hook or a permission rule in the guards
  plugin, because a sentence is advice the model weighs, not a guarantee. The skills have a
  budget too: `tests/skills_format.py` owns the bytes of each skill body and of all
  descriptions together, and a change that grows one raises its number in the same change.
- **Codex only where Codex is chosen** (#98, `DESIGN_DECISIONS.md`). No skill outside the codex
  plugin and not `rules/core.md` names Codex: Codex's side of a shared skill goes into
  `rules/codex.md` (inlined into the Codex block only, under 2,000 bytes), and Codex-only
  procedures and scripts into `plugins/codex/`, which the installer adds only with Codex in the
  plan. A seam in a shared skill stays client-neutral. `tests/skills_format.py` checks it.
- **Skills are written once** for both clients: `plugins/<plugin>/skills/<name>/SKILL.md`,
  inside what both accept (`tests/skills_format.py`). Writing or changing one follows the Agent
  Skills standard: `plugins/core/skills/repo-docs/skill-standard.md`, with Codex's additions in
  `rules/codex.md`. Scripts a skill runs live
  in its plugin's `scripts/` folder, because an installed plugin is copied without the rest of
  the repository.
- **Plugin names never change** once published. When any file of a plugin changes, raise its
  version with `python3 tools/bump_version.py <plugin> [patch|minor|major]`, or installed copies
  keep the old files (both clients cache plugins per version; measured 2026-10-25). The version
  lives in three places: both manifests and the plugin's entry in
  `.claude-plugin/marketplace.json`. `tests/repo_checks.py` checks the three agree and, against
  the default branch, that a changed plugin has a new version.
- **Attribution only where it belongs.** The author named in `NOTICE` appears in `README.md`,
  `NOTICE` and the manifests' `author`, `homepage`, `owner` and `developerName`, and nowhere
  else: not in `rules/`, not in a skill. No sales copy, pricing or call to action anywhere.
- **No personal or company data.** No e-mail address other than no-reply or example domains, no
  absolute home path, no employer or client names, no secrets: `tests/repo_checks.py` scans for
  the first two and `scan_secrets.py` for the last.
- **One owner per fact.** A plugin is installed on its own, so a few files and blocks of code
  live twice on purpose: `COPIES` in `tools/sync_copies.py` lists each owner and its copy.
  Edit the owner, then run `python3 tools/sync_copies.py`, which writes the copies;
  `tests/repo_checks.py` fails while one differs. The ask and deny lists are owned by
  `plugins/guards/policy/claude-permissions.json`, the Codex rules by
  `plugins/guards/policy/git-safety.rules`.

## Test gate

`python3 tests/run_all.py` runs every offline test; CI runs it on Linux, macOS and Windows with
`--require-all`, where a test that would skip for a missing `claude` or `codex` command fails
instead. After changing a skill's description, `python3 tests/skill_triggers.py` (live, spends
tokens) asks a client which skill it would pick for two requests per skill.
