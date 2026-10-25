# Templates

| File | Use |
|---|---|
| `company-overlay/AGENTS.md` | Starting point for a company's private overlay repository: the AI policy pointer, the data classes, the GitHub organisation's specifics. |
| `gitignore-secrets` | The secrets block for every repository's `.gitignore` (and the global `~/.config/git/ignore`). The security plugin's secret scanner reads a byte-identical copy of it (`plugins/security/scripts/gitignore-secrets`); `tests/repo_checks.py` keeps the two the same. |
| `pre-push` | A per-repository hook that refuses force-pushes, tag moves and deletions other than merged task branches. |

The starter documents for a new repository (`AGENTS.md`, `HANDOFF.md` and the rest) are owned by
the `repo-docs` skill: `plugins/core/skills/repo-docs/skeleton.md`.
