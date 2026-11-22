# Codex sources: what the worker's sandbox stands on

OpenAI's pages behind Codex's sandbox and approvals, which the worker's profile relies on
([SKILL.md](SKILL.md)). They were read on **2026-10-25** with plain fetches, for the
security plugin's sources, and moved here with the worker (#98). Re-read a source before
changing what rests on it, and update the date. `developers.openai.com/codex/…` moved to
`learn.chatgpt.com/docs/…`.

| Source | Version | Backs |
|---|---|---|
| [Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security) | n/d (Codex 0.114+) | Sandbox modes (`read-only`, `workspace-write`, `danger-full-access`), network off by default, `--yolo` not recommended; "treat web results as untrusted", cached web search against live-content injection; Codex Cloud strips secrets before the agent phase |
| [Sandboxing](https://learn.chatgpt.com/docs/sandboxing) | n/d | Seatbelt on macOS, bubblewrap on Linux; applies to spawned commands |
