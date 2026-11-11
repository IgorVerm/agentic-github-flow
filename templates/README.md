# Templates

| File | Use |
|---|---|
| `company-overlay/AGENTS.md` | Starting point for a company's private overlay repository: the AI policy pointer, the data classes, the GitHub organisation's specifics. |
| `gitignore-secrets` | The secrets block for every repository's `.gitignore` (and the global `~/.config/git/ignore`). The security plugin's secret scanner reads a byte-identical copy of it (`plugins/security/scripts/gitignore-secrets`); `tests/repo_checks.py` keeps the two the same. |
| `pre-push` | A per-repository hook that refuses force-pushes, tag moves and deletions other than merged task branches, and every push whose commits carry a secret or personal data (and, for a push without the user's yes, a change to a protected path). It runs the checks from the installed clone, `~/.agentic-github-flow`; its header owns the details. |

The starter documents for a new repository (`AGENTS.md`, `HANDOFF.md` and the rest) are owned by
the `repo-docs` skill: `plugins/core/skills/repo-docs/skeleton.md`.
