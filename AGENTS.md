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
  plugin, because a sentence is advice the model weighs, not a guarantee.
- **Skills are written once** for both clients: `plugins/<plugin>/skills/<name>/SKILL.md`,
  inside what both accept (`tests/skills_format.py`). Scripts a skill runs live in its plugin's
  `scripts/` folder, because an installed plugin is copied without the rest of the repository.
- **Plugin names never change** once published. When any file of a plugin changes, raise its
  version in both manifests and in both marketplace files, or installed copies keep the old
  files (both clients cache plugins per version; measured 2026-10-25). `tests/repo_checks.py`
  checks the four places agree and, against the default branch, that a changed plugin has a new
  version.
- **Attribution only where it belongs.** The author named in `NOTICE` appears in `README.md`,
  `NOTICE` and the manifests' `author`, `homepage`, `owner` and `developerName`, and nowhere
  else: not in `rules/`, not in a skill. No sales copy, pricing or call to action anywhere.
- **No personal or company data.** No e-mail address other than no-reply or example domains, no
  absolute home path, no employer or client names, no secrets: `tests/repo_checks.py` scans for
  the first two and `scan_secrets.py` for the last.
- **One owner per fact.** `templates/gitignore-secrets` owns the secret file names; the copy in
  `plugins/security/scripts/` exists because the plugin is installed on its own, and the tests
  keep it identical. The ask and deny lists are owned by
  `plugins/guards/policy/claude-permissions.json`, the Codex rules by
  `plugins/guards/policy/git-safety.rules`.

## Test gate

`python3 tests/run_all.py` runs every offline test; CI runs it on Linux, macOS and Windows with
`--require-all`, where a test that would skip for a missing `claude` or `codex` command fails
instead. After changing a skill's description, `python3 tests/skill_triggers.py` (live, spends
tokens) asks a client which skill it would pick for two requests per skill.
