# OpenAI Codex, the Agent Skills standard and other sources: read 2026-11-22 (#123)

All pages below were fetched on 2026-11-22. Most `developers.openai.com/codex/...` URLs now
answer with a 308 redirect to `learn.chatgpt.com/docs/...` ("ChatGPT Learn"); the final URL is
recorded. The `openai/codex` repository's `docs/agents_md.md` and `docs/skills.md` are now one-line
stubs that link to those pages. None of the OpenAI doc pages carry a date. Model names in the
OpenAI pages read today: GPT-6.2 Astra and GPT-6.2 Sol (latest), GPT-6 Astra, GPT-6 Luna, GPT-5.6
Sol. Quotes are limited to one short sentence per source; everything else is paraphrase. Where a
statement is not from a page read today it is labelled "from memory, unverified" or
"search snippet only".

## Sources

| # | Title | Final URL | Date |
|---|---|---|---|
| CX-agentsmd | Custom instructions with AGENTS.md | https://learn.chatgpt.com/docs/agent-configuration/agents-md | undated, read 2026-11-22 |
| CX-skills | Build skills | https://learn.chatgpt.com/docs/build-skills (also `.md`) | undated, read 2026-11-22 |
| CX-plugins | Plugins | https://learn.chatgpt.com/docs/plugins | undated, read 2026-11-22 |
| CX-pkg | Package your plugin (Build plugins) | https://developers.openai.com/plugins/build/plugins | undated, read 2026-11-22 |
| CX-rules | Rules | https://learn.chatgpt.com/docs/agent-configuration/rules | undated ("experimental"), read 2026-11-22 |
| CX-hooks | Hooks | https://learn.chatgpt.com/docs/hooks | undated, read 2026-11-22 |
| CX-sec | Agent approvals & security | https://learn.chatgpt.com/docs/agent-approvals-security | undated, read 2026-11-22 |
| CX-sub | Subagents | https://learn.chatgpt.com/docs/agent-configuration/subagents | undated, read 2026-11-22 |
| CX-config | Configuration Reference | https://learn.chatgpt.com/docs/config-file/config-reference | undated, read 2026-11-22 |
| CX-bp | Best practices (Codex) | https://learn.chatgpt.com/docs/learn/best-practices | undated, read 2026-11-22 |
| CX-prompting | Prompting (Codex) | https://learn.chatgpt.com/docs/prompting | undated, read 2026-11-22 |
| OA-6.2 | Using GPT-6.2 (+ prompting best practices) | https://developers.openai.com/api/docs/guides/latest-model ; .../latest-model/gpt-6.2-astra.md | undated, read 2026-11-22 |
| OA-6 | Using GPT-6 (Astra) | https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra | undated, read 2026-11-22 |
| OA-5.6 | Prompting guidance for GPT-5.6 Sol | https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6.md | undated; press dates it 2026-07-09; read 2026-11-22 |
| OA-blog | Rethinking skills and prompts for GPT-6 Astra | https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra | undated (secondary coverage around Sep 2026), read 2026-11-22 |
| AS-spec | Agent Skills Specification | https://agentskills.io/specification | undated, read 2026-11-22 |
| AS-bp | Best practices for skill creators | https://agentskills.io/skill-creation/best-practices.md | undated, read 2026-11-22 |
| AS-desc | Optimizing skill descriptions | https://agentskills.io/skill-creation/optimizing-descriptions.md | undated, read 2026-11-22 |
| AS-eval | Evaluating skill output quality | https://agentskills.io/skill-creation/evaluating-skills.md | undated, read 2026-11-22 |
| AS-scripts | Using scripts in skills | https://agentskills.io/skill-creation/using-scripts.md | undated, read 2026-11-22 |
| AS-client | How to add skills support to your agent | https://agentskills.io/client-implementation/adding-skills-support.md | undated, read 2026-11-22 |
| AP | Agent Plugins (open plugin standard 1.0.0) | https://agent-plugins.org/ | undated, read 2026-11-22 |
| AGM | AGENTS.md (open format) | https://agents.md/ | undated, read 2026-11-22 |
| AAIF | Writing an effective AGENTS.md (S. Kearns) | https://aaif.io/blog/writing-an-effective-agents-md | 2026-08-13 |
| ETH | Gloaguen et al., Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents? (arXiv:2602.11988, ICLR 2026) | https://arxiv.org/abs/2602.11988 (html: /html/2602.11988) | v1 2026-02-12, v3 2026-09-29 |
| LUL | Lulla et al., On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents (arXiv:2601.20404) | https://arxiv.org/abs/2601.20404 | v1 2026-01-28, v2 2026-03-30 |
| IFS | Jaroslawicz et al., How Many Instructions Can LLMs Follow at Once? (arXiv:2507.11538, NeurIPS 2025) | https://arxiv.org/abs/2507.11538 | 2025-07-15 |
| ROT | Chroma, Context Rot | https://www.trychroma.com/research/context-rot | 2025-07-14 |
| GH-2500 | M. Nigh, How to write a great agents.md: lessons from over 2,500 repositories (GitHub blog) | https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/ | 2025-11-19, upd. 2025-11-25 |
| GH-cr | Copilot code review: new configurations and controls (changelog) | https://github.blog/changelog/2026-06-12-copilot-code-review-new-configurations-and-controls/ | 2026-06-12 |
| GH-skills | About agent skills (GitHub Copilot) | https://docs.github.com/en/copilot/concepts/agents/about-agent-skills | undated, read 2026-11-22 |
| CUR | Cursor: Rules | https://cursor.com/docs/context/rules | undated, read 2026-11-22 |
| GEM | Gemini CLI: Provide context with GEMINI.md files | https://geminicli.com/docs/cli/gemini-md/ | last updated 2026-06-18 |
| HL | Writing a good CLAUDE.md (HumanLayer) | https://www.humanlayer.dev/blog/writing-a-good-claude-md | 2025-11-25 |
| OSM | A. Osmani, Stop using /init for AGENTS.md | https://addyosmani.com/blog/agents-md/ | 2026-02-23 |
| CC-skills, CC-memory, CC-hooks, CC-plugref | Claude Code docs (skills, memory, hooks, plugins reference), read only for the comparison table; the Anthropic side is in `sources-anthropic.md` | https://code.claude.com/docs/en/{skills,memory,hooks,plugins-reference} | undated, read 2026-11-22 |

Not fetched or not found: the Codex Rust source for skill name/description limits (raw path
404; `gh` unavailable in the sandbox). A search snippet claims older OpenAI docs limited `name` to
100 and `description` to 500 characters, single line; the current CX-skills page states no limit
(search snippet only, unverified). The arXiv PDF of ETH was not read; the HTML v3 was.

---

## (a) Always-loaded instruction files: size, content, caps

**Hard caps and loading (Codex)**
- Codex concatenates AGENTS.md from the Codex home (`~/.codex`, or `CODEX_HOME`) and then from the
  project root down to the working directory, at most one file per directory
  (`AGENTS.override.md` > `AGENTS.md` > names in `project_doc_fallback_filenames`); closer files
  come later and so win. Empty files are skipped. [CX-agentsmd]
- The combined size is capped by `project_doc_max_bytes`, default **32 KiB**; once reached,
  Codex stops adding files (truncation). The fix the docs give is to raise the cap or split into
  nested directories. [CX-agentsmd; CX-config lists the key without a default]
- The chain is built once per run (once per TUI session); there is no cache; changes need a
  restart. `codex --ask-for-approval never "Summarize the current instructions."` echoes what was
  loaded. [CX-agentsmd]
- `developer_instructions` (string) injects extra developer instructions; `model_instructions_file`
  replaces the built-in instructions. [CX-config]
- Implication for this repository (inference): the global Codex AGENTS.md the installer writes plus
  any project AGENTS.md share one 32 KiB budget; the core rules (~8 KB) leave room, but a project
  file above ~24 KB would truncate silently.

**Size and content recommendations**
- Codex: a short, accurate AGENTS.md beats a long one; include repo layout, how to run, build/test/
  lint commands, conventions and PR expectations, do-not rules, how to verify. Start with basics,
  add a rule only after repeated mistakes; when Codex makes the same mistake twice, ask for a
  retrospective and update the file. Move task-specific detail (planning, review, architecture)
  into separate Markdown files. Durable guidance goes in AGENTS.md, repeatable workflows in skills.
  No number given. [CX-bp]
- OpenAI on GPT-6 Astra: revisit each AGENTS.md instruction regularly; do not require reading
  several docs before every edit (point to a doc only where it applies, e.g. schema doc for schema
  changes); remove "run the tests" instructions (Astra tests on its own; such lines cause
  unnecessary testing); grant standing permission for safe local workflows. [OA-blog]
- AGENTS.md format: setup/build commands, tests, code style, overview, security, PR/commit
  guidance; nearest file wins; explicit chat prompts override files; no size advice; used by
  60,000+ projects; OpenAI's main repo has 88 AGENTS.md files. [AGM]
- AAIF: no target length; per instruction ask whether knowing it would change what the agent
  does. Exclude what config files already say, generic advice, directory listings, copies of docs
  (point to them), rules a formatter/linter enforces, stale lines. Include exact commands with
  working directory, boundaries, tiered validation (while iterating / before finishing / full
  suite), canonical files to imitate. [AAIF]
- Claude Code (for comparison): target **under 200 lines** per CLAUDE.md; longer files reduce
  adherence; `@` imports do not reduce context cost; block-level HTML comments are stripped
  before injection (zero tokens). [CC-memory]
- Cursor: each rule under **500 lines**; split into composable rules; add a rule only when the
  agent repeats a mistake; do not document common tools (npm, git, pytest); use a linter instead
  of copying style guides. [CUR]
- GitHub (pattern analysis of 2,500+ files): cover commands, testing, project structure, code
  style, git workflow, boundaries; put commands early; one real snippet beats paragraphs;
  three-tier boundaries (always / ask first / never). Observational, success undefined. [GH-2500]
- HumanLayer: root file under 60 lines in their practice; "under 300 lines" as community
  consensus; claims frontier models follow ~150-200 instructions and that Claude Code's system
  prompt already holds ~50 (author's own count; rests on IFS). [HL]
- GitHub Copilot code review used to read only the first 4,000 characters of instruction files;
  that limit was removed on 2026-06-12. [GH-cr]
- Gemini CLI concatenates all GEMINI.md files and sends them with every prompt; AGENTS.md only via
  `context.fileName`; the page says Gemini CLI was replaced by Antigravity CLI on 2026-06-18. [GEM]

## (b) Skill descriptions and bodies

**Agent Skills specification (numbers exact)** [AS-spec]
- `name`: required, 1-64 chars, lowercase a-z, 0-9 and `-`, no leading/trailing hyphen, no `--`,
  must match the parent directory name.
- `description`: required, 1-1024 chars, non-empty; say what it does and when to use it, with
  keywords.
- `license`: optional, short. `compatibility`: optional, 1-500 chars, only if there are real
  environment requirements ("most skills do not need" it). `metadata`: optional string-to-string
  map, use unique key names. `allowed-tools`: optional, space-separated, experimental.
- Layout: `SKILL.md` plus optional `scripts/`, `references/`, `assets/`.
- Progressive disclosure: metadata **~100 tokens** per skill at startup; body **< 5,000 tokens**
  recommended, loaded on activation; resources on demand. Keep `SKILL.md` **under 500 lines**.
- File references relative to the skill root, **one level deep** from SKILL.md; avoid nested
  reference chains.
- Validation: `skills-ref validate ./my-skill` (frontmatter and naming).
- Client guide: catalog costs ~50-100 tokens per skill; clients should strip or keep frontmatter,
  wrap activated content in tags, **exempt skill content from compaction**, deduplicate repeated
  activations, gate project skills on folder trust, and load leniently (warn on name > 64 or
  name/dir mismatch; skip on missing description or unparseable YAML). Common unquoted-colon YAML
  in descriptions breaks strict parsers. `.agents/skills/` (project and user) is the emerging
  cross-client location; some clients also scan `.claude/skills/`. [AS-client]

**Writing descriptions** [AS-desc]
- Imperative ("Use this skill when..."), focused on user intent not implementation, err on the
  side of being pushy (list contexts where the user does not name the domain), a few sentences to
  a short paragraph; hard limit 1,024 characters.
- Agents tend to consult skills only for tasks beyond their own ability; a simple one-step request
  may not trigger even a perfect description.
- Codex: front-load the key use case and trigger words so matching survives shortening; concise
  descriptions with clear scope and boundaries. [CX-skills] Claude Code says the same (1,536-char
  cap per entry). [CC-skills]
- OpenAI on Astra: keep descriptions as short as possible but name the specific trigger (e.g.
  "adding or changing a migration", not "working with databases"). [OA-blog]

**Writing bodies** [AS-bp]
- Add what the agent lacks, omit what it knows; for every line ask whether the agent would get it
  wrong without it; if the agent does the whole task well without the skill, the skill adds
  nothing.
- Moderate detail: exhaustive skills hurt (the agent follows instructions that do not apply).
- Match prescriptiveness to fragility: freedom plus the why for flexible work; exact commands for
  fragile operations. Defaults, not menus. Procedures over one-off answers.
- Gotchas sections are the highest-value content; keep them in SKILL.md, not in a reference the
  agent may not know to open. Templates for output shape; checklists for multi-step work;
  validation loops; plan-validate-execute for destructive batch work.
- Say *when* to load each reference ("read X if the API returns non-200"), not "see references/".
- Explain the why rather than ALWAYS/NEVER; if pass rates plateau as rules are added, remove rules
  and see whether results hold. [AS-eval]
- OpenAI on Astra: for multi-workflow skills make SKILL.md a minimal router to supporting docs and
  scripts; remove rigid step-by-step recipes. [OA-blog]
- Codex: one job per skill; prefer instructions over scripts unless determinism or external tools
  are needed; imperative steps with explicit inputs and outputs. [CX-skills]

**Scripts** [AS-scripts]
- No interactive prompts (hard requirement); `--help` is the agent's interface doc, kept short;
  errors say what was wrong, what was expected, what to try; structured output on stdout,
  diagnostics on stderr; idempotent; `--dry-run` for destructive ops; distinct documented exit
  codes; predictable output size, because harnesses often truncate at roughly 10-30K characters.

## (c) Codex versus Claude Code: how things load

See the comparison table at the end. Key differences that matter for "write once for both":
- **Skill locations differ.** Codex scans `.agents/skills` from CWD up to the repo root,
  `$HOME/.agents/skills`, `/etc/codex/skills`, and bundled system skills; it does not list
  `.claude/skills`. Claude Code scans `.claude/skills` (personal, project, nested, plugin); its
  skills page does not list `.agents/skills`. GitHub Copilot scans `.github/skills`,
  `.claude/skills` and `.agents/skills`. [CX-skills; CC-skills; GH-skills]
- **Catalog budget differs.** Codex: at most 2% of the context window (8,000 characters if the
  window is unknown), `skills.max_context_tokens` up to 10,000; on overflow Codex shortens
  descriptions first, then omits skills with a warning. Claude Code: 1% of the context window
  (`skillListingBudgetFraction`, or `SLASH_COMMAND_TOOL_CHAR_BUDGET`), each entry capped at 1,536
  characters (`skillListingMaxDescChars`), overflow drops descriptions of the least-invoked
  skills first. [CX-skills; CX-config; CC-skills]
- **Implicit-invocation switch differs.** Codex: `policy.allow_implicit_invocation: false` in
  `agents/openai.yaml` (explicit `$skill` still works). Claude Code: `disable-model-invocation:
  true` in SKILL.md frontmatter. Claude Code's other frontmatter extensions (`when_to_use`,
  `context: fork`, `paths`, `hooks`, `model`, ...) are ignored elsewhere; unknown fields are
  silently ignored by Claude Code. [CX-skills; CC-skills]
- **Explicit invocation:** Codex `$name` or `/skills`; Claude Code `/name` (plugin skills
  `/plugin:name`). [CX-skills; CC-skills]
- **Plugins.** Codex prefers a portable root `plugin.json` (Agent Plugins schema 1.0.0, whose
  steering committee lists Amazon, Cursor, Microsoft, OpenAI, Vercel) and still accepts
  `.codex-plugin/plugin.json`; the `@plugin-creator` scaffold writes only the latter. Codex
  marketplaces live at `.agents/plugins/marketplace.json`, `~/.agents/plugins/marketplace.json`,
  and "legacy-compatible" `.claude-plugin/marketplace.json`. Installed copies are cached at
  `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/` (`local` for local plugins); refresh
  with `codex plugin marketplace upgrade`. Claude Code reads only `.claude-plugin/plugin.json`
  (optional), `version` pins users until it changes, and a `CLAUDE.md` at the plugin root is not
  loaded. [CX-pkg; AP; CC-plugref]
- **AGENTS.md.** Codex reads AGENTS.md natively, 32 KiB cap. Claude Code now reads AGENTS.md
  itself (v2.1.277+) but by default only when there is no CLAUDE.md/CLAUDE.local.md in the working
  directory or above; with a CLAUDE.md, it must `@AGENTS.md`-import it or set
  `claude-md-and-agents-md`. [CX-agentsmd; CC-memory]
- **Hooks exist in both and share most event and field names** (see (d)), but Codex does not
  support `permissionDecision: "ask"` in PreToolUse (reported as a failure and the tool call
  continues), skips `prompt` and `agent` handlers, and requires a hash-based trust review for every
  non-managed hook, including after a plugin script changes. [CX-hooks]
- **Command policy.** Codex has `.rules` files (Starlark `prefix_rule`); Claude Code has
  permission allow/ask/deny lists in settings. [CX-rules; CC docs in sources-anthropic.md]
- **Protected paths.** Under Codex `workspace-write`, `.git`, `.agents`, `.codex` (and `.aws`) are
  read-only inside writable roots, so an agent cannot edit repo skills or Codex config without
  escalation. [CX-sec]

## (d) Enforcement by policy or hook versus prose

- Codex rules: `prefix_rule(pattern=[...], decision="allow"|"prompt"|"forbidden",
  justification=..., match=[...], not_match=[...])` in `rules/*.rules` next to each config layer
  (`~/.codex/rules/`, trusted `<repo>/.codex/rules/`); strictest match wins
  (forbidden > prompt > allow); `match`/`not_match` examples are validated at load; test with
  `codex execpolicy check --pretty --rules <file> -- <cmd>`. Shell wrappers (`bash -lc` etc.) are
  split into commands only for plain chains (`&&`, `||`, `;`, `|`); with redirection,
  substitution, variables, globs or control flow the whole script is one invocation. Admins can
  enforce rules via `requirements.toml`. Marked experimental. [CX-rules]
- `allow` in a Codex rule means "runs outside the sandbox without prompting", not just "no
  prompt". [CX-rules]
- Codex hooks: 14 events (PreToolUse, PermissionRequest, PostToolUse, PreCompact, PostCompact,
  UserPromptSubmit, SubagentStop, Stop, PreModelRequest, PostModelRequest, Interrupt,
  SessionStart, SubagentStart, SessionEnd); on by default (`[features] hooks = false` turns off;
  `codex_hooks` deprecated alias). Config in `hooks.json` at system, `$CODEX_HOME`, trusted
  `.codex/`, plugin `hooks/hooks.json` or manifest `hooks`, or inline `[hooks]` in config.toml.
  Block a tool with exit 2 or `hookSpecificOutput.permissionDecision: "deny"`. Default timeout
  600 s. Up to 8 async hooks per session. Model-visible hook output is capped at roughly 2,500
  tokens by default (`additionalContextLimit`), overflow saved to a temp file. Hooks cover Bash,
  `exec_command`, `apply_patch` (matchable as `Edit`/`Write`), MCP and local tools (`spawn_agent`
  matches `Agent`), not hosted tools such as WebSearch. [CX-hooks]
- Codex hooks fail open: a PreToolUse error, timeout or malformed response can let the tool run;
  the docs call tool hooks "a useful guardrail, not a complete enforcement boundary". [CX-hooks]
- Claude Code: CLAUDE.md is context, not enforced configuration; to block an action regardless of
  the model, use a PreToolUse hook; a rule a skill must hold every time belongs in a hook.
  [CC-memory; CC-skills] Claude Code PreToolUse supports `allow|deny|ask|defer`; a timed-out
  PreToolUse hook does not block unless `"onFailure": "block"`. additionalContext cap 10,000
  characters. [CC-hooks]
- OpenAI prompting: write ALWAYS/NEVER/must only for true invariants (safety, required fields);
  for judgment calls write decision rules. State which actions are authorised; do not repeat "ask
  first" for safe actions. [OA-5.6]
- AAIF and Cursor: leave what a formatter or linter enforces to the tool. HumanLayer: run
  formatters/linters from a Stop hook rather than writing style rules. [AAIF; CUR; HL]

## (e) Subagents and context isolation

- Codex: built-in `default`, `worker`, `explorer`; custom agents as TOML in `~/.codex/agents/` or
  `.codex/agents/` with required `name`, `description`, `developer_instructions`; optional model,
  effort, feature reductions, `skills.include_instructions = false`. Agent files cannot override
  `sandbox_mode`, `approval_policy`, `model_provider`, `mcp_servers` (inherited). `[agents]`:
  `enabled` (true), `max_concurrent_threads_per_session` (Codex chooses), default subagent model
  and effort. No depth limit documented. Subagents return summaries; the page does not state
  separate context windows. They cost more tokens; use for read-heavy, bounded, parallel work; be
  careful with parallel writes. Codex delegates when asked or when AGENTS.md or a skill asks for
  it. [CX-sub]
- Codex best practices: offload exploration, tests, triage to subagents; keep the main agent on
  the core problem. [CX-bp]
- Agent Skills: run evals in clean contexts (subagents give this naturally); optional pattern of
  running a whole skill in a subagent. [AS-eval; AS-client]
- Final answers must stand alone and not carry shorthand from subagent instructions. [OA-6.2]

## (f) Long sessions, compaction, hand-over

- Codex compaction keys: `model_auto_compact_token_limit` (unset = model default),
  `model_auto_compact_token_limit_scope` (`total` | `body_after_prefix`),
  `model_post_turn_compact_threshold_percent` (0-100, off by default), `compact_prompt`,
  `experimental_compact_prompt_file`; `tool_output_token_limit` caps each stored tool output;
  per-MCP-tool `output_token_limit`; MCP input schemas compacted above 5,000 bytes by default.
  Hooks `PreCompact`/`PostCompact` exist. [CX-config; CX-hooks]
- Codex: one chat per coherent unit of work, fork only when work truly branches; `/compact` when
  long; `/resume`, `/fork`; PLANS.md or execution-plan templates for long multi-step work; `/plan`,
  `/goal`; schedule a task only after the workflow is reliable by hand. [CX-bp; CX-prompting]
- Codex AGENTS.md is read once per run; behaviour after compaction is not documented on the
  AGENTS.md page (not stated).
- Claude Code: project-root CLAUDE.md is re-read and re-injected after `/compact`; nested files
  and path rules reload on demand; invoked skills are re-attached with their first 5,000 tokens
  each, 25,000 tokens combined, most recent first, so put the most important skill instructions
  at the top. [CC-memory; CC-skills]
- Agent Skills client guide: protect skill content from compaction; deduplicate activations.
  [AS-client]
- OpenAI API guidance: keep the prefix stable (stable instructions first) for caching; editing
  earlier history can drop reasoning items and raise token use. [OA-6.2]

## (g) Instruction style for current models

- Outcome-first: destination, success criteria, required output, explicit stopping conditions;
  remove repeated rules, style/process lines and examples that do not change behaviour, process
  steps the model already does, unrelated tools. Keep safety, permission and evidence
  constraints, context-dependent tool routing, output shape, validation. [OA-5.6]
- Contradictions cause more instability than missing detail; review for conflicts. [OA-5.6]
  Claude Code: if two instructions contradict, Claude may pick one arbitrarily; `/doctor
  prompt-audit` finds conflicts and instructions written for older models. [CC-memory]
- Tool preambles: one or two sentences before the first tool call in multi-step work, then
  updates only at phase changes. [OA-5.6]
- Persistence: keep working when the next step is authorised and in scope; stop only for a
  significant scope change, a concrete blocker, a user-only decision, or an irreversible or
  destructive action; state reasonable reversible assumptions; verify every part of the request
  before finishing. [OA-6.2]
- GPT-6 Astra can be "more sensitive to instructions contained in skills" and AGENTS.md; unclear
  or conflicting skill guidance can make it pause and block early. OpenAI strongly recommends
  auditing skills and instruction files, states that explicit user instructions take precedence
  over a skill, and suggests asking the model to name and quote the SKILL.md line that made it
  pause. [OA-6]
- Instructions shared in a repository are read by other contributors' agents on other models;
  guidance tuned for older models may over-constrain newer ones. [OA-blog]
- Migration discipline: switch models first and run evals before changing prompts; remove
  scaffolding, then add targeted fixes only for measured regressions; change one group at a time.
  [OA-5.6]
- The newest models are more concise by default; revisit "be concise" instructions. [OA-6.2]

## (h) Evidence: does more context-file text help or hurt?

| Study | Design | Result | Strength / transfer |
|---|---|---|---|
| ETH (v3) | 4 agent/model pairs (Claude Code + Sonnet-4.5; Codex + GPT-5.2 and GPT-5.1 mini; Qwen Code + Qwen3-30b-coder); SWE-bench Lite 300 tasks/11 repos (LLM-generated files) and CTXbench 138 tasks/12 repos (developer files) | LLM-generated files: -0.5 pp (SWE-bench) and -2 pp (CTXbench) resolve rate, not significant; cost +20% / +23% (p < 0.001), +2.45 / +3.92 steps. Developer files: +2.4 pp, not significant; cost up to +19%, +3.34 steps. Dev beats LLM-generated by ~7% (p = 0.038). Agents follow tool mentions closely (`uv` 1.6 uses per task when named vs < 0.01). Overviews do not shorten navigation. LLM files help (+2.7%) only when other docs are removed. | Controlled, peer-reviewed (ICLR 2026 oral), Python only, models a generation old. Strongest evidence: context files cost ~20% more and add no significant success; keep only non-standard tooling/conventions. Earlier versions and secondary posts quote +4% / -3%; v3 numbers above supersede them. |
| LUL (v2) | 124 PRs, 10 repos, with/without AGENTS.md | Median runtime -28.64%, median output tokens -16.58%, completion "comparable" | Small, 5-page workshop paper, efficiency only (no correctness); associations. Supports a focused developer-written file helping orientation. |
| AAIF | 5 runs, 1 repo, 1 agent | 2/5 runs without the file reoriented or ran an unrequested production build; 0/5 with it | Anecdotal. |
| IFS | 20 models, 10-500 keyword-inclusion instructions | Best model 68% at 500 instructions; primacy bias peaking at 150-200 instructions | Synthetic task (keyword inclusion), not coding rules; supports "fewer instructions, important first". |
| ROT | 18 models, 194,480 calls | Performance degrades with input length even on simple tasks; distractors hurt more as length grows; LongMemEval focused prompt (~300 tokens) beats full (~113k) | Retrieval/QA, not instruction following; supports keeping irrelevant text out of context. |
| OA-5.6 | OpenAI internal coding-agent evals, leaner vs original heavier system prompts | Scores +10-15%, total tokens -41-66%, cost -33-67% | Vendor, unpublished method, "directional"; the most direct evidence that trimming prompts saves tokens without losing quality on current models. |
| GH-2500 | 2,500+ public agents.md files | Pattern list (commands, tests, structure, style, git, boundaries) | Observational, no outcome measure. |

## (i) Testing and evaluating skills and trigger descriptions

- Trigger evals [AS-desc]: ~**20 queries**, 8-10 should-trigger and 8-10 should-not; vary
  phrasing, explicitness, detail, complexity; negatives should be near-misses sharing keywords;
  run each **3 times**, trigger-rate threshold **0.5**; split **~60% train / ~40% validation**,
  fixed across iterations; revise from train failures only, generalise rather than add failed
  keywords; **~5 iterations** usually enough; pick the iteration with the best validation pass
  rate; confirm with **5-10 fresh queries**; stop runs early once the skill is (not) consulted.
  Example detection uses Claude Code JSON output for a `Skill` tool call.
- Output evals [AS-eval]: start with **2-3 test cases** in `evals/evals.json` (prompt, expected
  output, files); run each **with and without the skill** (or old version), each in a clean
  context; record `total_tokens` and `duration_ms`; add assertions after the first run; grade
  with evidence; prefer scripts for mechanical checks; blind A/B for versions; drop assertions
  that pass in both configurations; aggregate pass rate, time, tokens and their delta in
  `benchmark.json`; weigh quality gain against token cost.
- Codex: test prompts against the description to confirm triggering. [CX-skills] OpenAI's
  `$skill-creator` guidance was recently updated for common failure modes. [OA-blog]
- Claude Code: `skill-creator` plugin automates the loop; `claude plugin eval` with a
  `tool_used: Skill` grader measures trigger rate for plugin skills; `claude plugin validate`
  finds frontmatter that does not parse. [CC-skills]
- Codex rules have built-in tests (`match`/`not_match`, `codex execpolicy check`). [CX-rules]

---

## Codex versus Claude Code comparison (as documented 2026-11-22)

| Aspect | Codex | Claude Code |
|---|---|---|
| Always-loaded file | `AGENTS.md` chain: `~/.codex` (or `CODEX_HOME`) then repo root down to CWD; one file per dir; `AGENTS.override.md` wins | `CLAUDE.md` (user, project, local, managed), `.claude/rules/*.md` without `paths`; AGENTS.md only if no CLAUDE.md (default), or via `@AGENTS.md` import |
| Size cap / guidance | Hard cap 32 KiB combined (`project_doc_max_bytes`), files beyond are dropped; "short, accurate" | No hard cap; target < 200 lines per file; imports up to 4 hops, no context saving |
| Subdirectory files | Only those between root and CWD at start; built once per run | Nested CLAUDE.md / AGENTS.md / path rules load on demand when files there are read |
| After compaction | Not documented | Root CLAUDE.md re-read from disk; skills re-attached (5k tokens each, 25k total) |
| Skill locations | `.agents/skills` (CWD up to repo root), `~/.agents/skills`, `/etc/codex/skills`, system; plugins | `.claude/skills` (project, nested on demand), `~/.claude/skills`, managed, plugins `skills/` |
| Skill frontmatter | `name`, `description` required; extras in `agents/openai.yaml` (`interface`, `policy.allow_implicit_invocation`, `dependencies.tools`) | Open-standard fields plus `when_to_use`, `disable-model-invocation`, `user-invocable`, `context: fork`, `agent`, `paths`, `hooks`, `model`, `effort`, `allowed-tools`, ...; unknown fields ignored |
| Name/description limits | None stated on current page (old limits 100/500 per search snippet, unverified); spec 64/1024 | Listing entry capped at 1,536 chars (description + when_to_use); spec 64/1024 |
| Catalog budget | 2% of context (8,000 chars fallback); `skills.max_context_tokens` <= 10,000; shortens descriptions, then omits skills | 1% of context (`skillListingBudgetFraction`); drops descriptions of least-used skills first; all names kept |
| Disable implicit use | `policy.allow_implicit_invocation: false` | `disable-model-invocation: true` |
| Disable a skill | `[[skills.config]]` `enabled = false` by `name` or `path` | `skillOverrides` (incl. `"name-only"`) |
| Explicit call | `$skill` or `/skills` | `/skill` (plugin: `/plugin:skill`) |
| Live reload | Detects skill file changes; restart if not seen | SKILL.md changes picked up; `/reload-skills`, `/reload-plugins` |
| Plugin manifest | Root `plugin.json` (Agent Plugins 1.0.0, preferred) or `.codex-plugin/plugin.json` (fallback; scaffold default) | `.claude-plugin/plugin.json` (optional) |
| Marketplace | `.agents/plugins/marketplace.json`, `~/.agents/plugins/marketplace.json`, legacy `.claude-plugin/marketplace.json` | `.claude-plugin/marketplace.json` |
| Plugin cache | `~/.codex/plugins/cache/<mkt>/<plugin>/<version>/`; `codex plugin marketplace upgrade` | Per version; `version` pins users until it changes; `${CLAUDE_PLUGIN_DATA}` survives updates |
| Plugin enable key | `[plugins."name@marketplace"] enabled` | `enabledPlugins`, `defaultEnabled` |
| Command policy | `.rules` (`prefix_rule`, allow/prompt/forbidden, strictest wins, inline tests, `codex execpolicy check`); experimental | settings `permissions` allow/ask/deny |
| Hooks | 14 events; `hooks.json` or `[hooks]`; on by default; trust review per hash for non-managed hooks; types `command`, `mcp_tool` (`prompt`/`agent` skipped); PreToolUse `ask` unsupported (fails open); ~2,500-token output cap; WebSearch not covered | ~33 events; settings files, plugin `hooks/hooks.json`, skill and agent frontmatter; types `command`, `http`, `mcp_tool`, `prompt`, `agent`; PreToolUse `allow/deny/ask/defer`; 10,000-char output cap |
| Sandbox / approvals | `read-only`, `workspace-write` (default "Auto" in VCS folders, with `on-request`), `danger-full-access`; policies `on-request`, `never`, `granular`; `untrusted` retired; network off by default; `.git`, `.agents`, `.codex` read-only | Permission modes + optional Bash sandbox (see sources-anthropic.md) |
| Subagents | `default`, `worker`, `explorer` + TOML agents in `.codex/agents/`; inherit sandbox/approvals; cannot override them | Markdown agents in `.claude/agents/`, plugin `agents/`; skill `context: fork` |
| Context keys | `model_auto_compact_token_limit`, `tool_output_token_limit`, `compact_prompt`, `skills.include_instructions` | auto-compact settings, `skillListingBudgetFraction`, `claudeMdExcludes` |
