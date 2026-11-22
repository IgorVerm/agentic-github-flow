# Anthropic best practices: primary sources read 2026-11-22 (#123)

All pages below were fetched on 2026-11-22. Claude Code docs were read as raw Markdown
(`<page>.md`) from code.claude.com; platform docs from platform.claude.com; engineering posts
through anthropic.com. Old docs.anthropic.com / docs.claude.com links now redirect to these hosts,
and the old engineering post "Claude Code: best practices for agentic coding"
(`anthropic.com/engineering/claude-code-best-practices`) now returns a 308 redirect to the docs
page `code.claude.com/docs/en/best-practices`. Engineering posts moved from `/engineering/<slug>`
to `/research/<slug>`. The Claude Code docs pages carry no date; they mention versions up to
v2.1.314, so they are current as of the read date. Quotes are limited to one short sentence per
source; everything else is paraphrase.

## Sources

| # | Title | Final URL | Date |
|---|---|---|---|
| CC-skills | Extend Claude with skills | https://code.claude.com/docs/en/skills | undated, read 2026-11-22 |
| CC-memory | How Claude remembers your project | https://code.claude.com/docs/en/memory | undated, read 2026-11-22 |
| CC-bp | Best practices for Claude Code (successor of the 2025 engineering post) | https://code.claude.com/docs/en/best-practices | undated, read 2026-11-22 |
| CC-hooks | Hooks reference | https://code.claude.com/docs/en/hooks | undated, read 2026-11-22 |
| CC-hooks-guide | Automate actions with hooks | https://code.claude.com/docs/en/hooks-guide | undated, read 2026-11-22 |
| CC-subagents | Create custom subagents | https://code.claude.com/docs/en/sub-agents | undated, read 2026-11-22 |
| CC-agents | Run agents in parallel | https://code.claude.com/docs/en/agents | undated, read 2026-11-22 |
| CC-features | Extend Claude Code (features overview, context cost by feature) | https://code.claude.com/docs/en/features-overview | undated, read 2026-11-22 |
| CC-costs | Manage costs effectively | https://code.claude.com/docs/en/costs | undated, read 2026-11-22 |
| CC-ctx | Explore the context window | https://code.claude.com/docs/en/context-window | undated, read 2026-11-22 |
| CC-cache | How Claude Code uses prompt caching | https://code.claude.com/docs/en/prompt-caching | undated, read 2026-11-22 |
| CC-model | Model configuration (auto-compact thresholds) | https://code.claude.com/docs/en/model-config | undated, read 2026-11-22 |
| CC-perms | Configure permissions | https://code.claude.com/docs/en/permissions | undated, read 2026-11-22 |
| CC-sandbox | Configure the sandboxed Bash tool | https://code.claude.com/docs/en/sandboxing | undated, read 2026-11-22 |
| CC-pl-overview | Plugins overview | https://code.claude.com/docs/en/plugins/overview | undated, read 2026-11-22 |
| CC-pl-components | Add components to a plugin | https://code.claude.com/docs/en/plugins/components | undated, read 2026-11-22 |
| CC-pl-loading | Plugin loading reference (versions, cache) | https://code.claude.com/docs/en/plugins/loading | undated, read 2026-11-22 |
| CC-pl-publish | Publish and distribute a plugin | https://code.claude.com/docs/en/plugins/publish | undated, read 2026-11-22 |
| CC-pl-measure | Measure plugin cost and usage | https://code.claude.com/docs/en/plugins/measure | undated, read 2026-11-22 |
| CC-pl-evals | Test plugins with evals | https://code.claude.com/docs/en/plugin-evals | undated, read 2026-11-22 |
| SDK-skills / SDK-subagents | Agent SDK: Extend agents with skills; Subagents in the SDK | https://code.claude.com/docs/en/agent-sdk/skills , https://code.claude.com/docs/en/agent-sdk/subagents | undated, read 2026-11-22 |
| P-skills-overview | Agent Skills overview | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview | undated, read 2026-11-22 |
| P-skills-bp | Skill authoring best practices | https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices | undated, read 2026-11-22 |
| P-prompting | Prompting best practices (current models) | https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices | undated, read 2026-11-22 |
| P-fable52 | Prompting Claude Fable 5.2 | https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2 | undated, read 2026-11-22 |
| P-opus55 | Prompting Claude Opus 5.5 | https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5 | undated, read 2026-11-22 |
| P-cache | Prompt caching (API) | https://platform.claude.com/docs/en/build-with-claude/prompt-caching | undated, read 2026-11-22 |
| AS-spec | Agent Skills specification (open standard) | https://agentskills.io/specification | undated, read 2026-11-22 |
| E-ctx | Effective context engineering for AI agents | https://www.anthropic.com/research/effective-context-engineering-for-ai-agents | 2025-09-29 |
| E-skills | Equipping agents for the real world with Agent Skills | https://www.anthropic.com/research/equipping-agents-for-the-real-world-with-agent-skills | 2025-10-16 (update 2025-12-18: open standard) |
| E-tools | Writing effective tools for agents, with agents | https://www.anthropic.com/research/writing-tools-for-agents | 2025-09-11 |
| E-bea | Building effective agents | https://www.anthropic.com/research/building-effective-agents | 2024-12-19 |
| E-multi | How we built our multi-agent research system | https://www.anthropic.com/research/multi-agent-research-system | 2025-06-13 |
| E-harness1 | Effective harnesses for long-running agents | https://www.anthropic.com/research/effective-harnesses-for-long-running-agents | 2025-11-26 |
| E-advtools | Introducing advanced tool use on the Claude Developer Platform | https://www.anthropic.com/research/advanced-tool-use | 2025-11-24 |
| E-evals | Demystifying evals for AI agents | https://www.anthropic.com/research/demystifying-evals-for-ai-agents | 2026-01-09 |
| E-harness2 | Harness design for long-running application development | https://www.anthropic.com/research/harness-design-long-running-apps | 2026-03-24 |
| E-postmortem | An update on recent Claude Code quality reports | https://www.anthropic.com/research/april-23-postmortem | 2026-04-23 |
| E-contain | How we contain Claude across products | https://www.anthropic.com/research/how-we-contain-claude | 2026-05-25 |
| E-memory | The components of agent memory | https://www.anthropic.com/research/components-of-agent-memory | 2026-11-06 |

Not read in full (listed on the engineering index, judged off-topic or covered elsewhere):
"Beyond permission prompts" (2025-10-20, its 84 % figure is repeated in E-contain), "Code execution
with MCP" (2025-11-04), "How we built Claude Code auto mode" (2026-03-25), "Scaling Managed Agents"
(2026-04-08), "Redesigning source control" (2026-10-13), "Building strong safety evaluations"
(2026-11-13). The index page said 29 posts exist but showed 24.

---

## (a) Always loaded versus loaded on demand; sizes and budgets

**What loads at session start (CC-ctx, CC-features).** CLAUDE.md (or AGENTS.md), auto memory,
MCP tool names, skill descriptions, output style and environment info load before the first prompt
and are sent with every request. CC-features rates CLAUDE.md "every request", skills "low
(descriptions every request)", hooks "zero, unless hook returns additional context", subagents
"isolated from main session". CC-ctx gives an illustrative startup of ~7,850 tokens (system prompt
4,200; project CLAUDE.md 1,800; skill descriptions 450; MEMORY.md 680; user CLAUDE.md 320).

**CLAUDE.md size.**
- Target under **200 lines per CLAUDE.md file**; longer files consume more context and reduce
  adherence (CC-memory "Write effective instructions"; repeated in CC-features, CC-costs, CC-bp).
- `@path` imports organise but **do not reduce context**: imported files load with the importer;
  max import depth **four hops** (CC-memory).
- Claude Code **skips a file over 4 MiB**; it warns at startup and in `/status` when a file is over
  the recommended length, and when files within that length together pass a combined limit (number
  not stated) (CC-memory "My CLAUDE.md is too large").
- **On-demand** files (subdirectory CLAUDE.md, rules in a subdirectory, path-scoped rules) are cut
  to a per-file limit: **40,000 characters** with a 200K window; **200,000** on Opus 4.6 / Sonnet
  4.6 1M and **150,000** on later 1M models. Claude gets only the start plus a note to Read the rest.
  Applies since v2.1.309 (CC-memory "Claude ignores the end of my subdirectory CLAUDE.md").
- Block-level **HTML comments are stripped** before injection, so maintainer notes cost no tokens
  (CC-memory).
- What belongs in CLAUDE.md: only what Claude cannot work out from the code: exact test /
  typecheck / lint commands, misleading places in the code, decisions not in the repo, anything
  corrected twice. Do not describe architecture or layout (CC-bp "Keep CLAUDE.md short" and
  "What you can stop doing"). `/doctor` proposes cuts; `/doctor prompt-audit` (v2.1.283+) flags
  instructions written for older models, dead references and contradictions (CC-memory).
- Add to CLAUDE.md when Claude makes the same mistake a second time, a review catches something,
  or you repeat a correction (CC-memory "When to add").
- Multi-step procedures, or content for one part of the codebase, go to a **skill** or a
  **path-scoped rule** instead (CC-memory, CC-bp, CC-costs "Move instructions from CLAUDE.md to
  skills").

**AGENTS.md (new in 2026).** Claude Code now reads `AGENTS.md` natively (v2.1.277+) but by default
**only when no CLAUDE.md / .claude/CLAUDE.md / CLAUDE.local.md exists** in the working directory or
above. A `CLAUDE.md` with `@AGENTS.md` never reads it twice. A setting `instructionFiles`
(`claude-md-or-agents-md` default, `claude-md-and-agents-md`, `claude-md`, `managed-only`) sits under
`pluginConfigs["cc-plugin-agents-md@builtin"]` in user or managed settings only. A SessionStart hook
that prints AGENTS.md should be removed: it adds a second copy (CC-memory "AGENTS.md").
`~/.claude/CLAUDE.md` does not count for that check and keeps loading alongside AGENTS.md.

**Rules (`.claude/rules/`).** Unscoped rules load every session like CLAUDE.md. `paths:` is the
only frontmatter field read; a path-scoped rule loads when Claude Reads/Writes/Edits a matching file
(or `cat`/`head` of one file). Brace expansion budget 1,000 patterns / 4 MiB per rule. Path-scoped
rules and nested CLAUDE.md are summarised away by compaction and reload only on the next match
(CC-memory, CC-ctx).

**Auto memory.** First **200 lines or 25 KB** of `MEMORY.md` load at start (CC-memory; confirmed
in E-memory). Not loaded into non-fork subagents.

**Skills (Claude Code).**
- Listing budget for names + descriptions: **1 % of the model's context window** (characters);
  every name is always listed, but when over budget descriptions are dropped starting with the
  least-invoked skills. Raise with `skillListingBudgetFraction` (e.g. 0.02) or
  `SLASH_COMMAND_TOOL_CHAR_BUDGET`; collapse entries with `skillOverrides: "name-only"`
  (CC-skills "Skill descriptions are cut short").
- Per-entry cap: `description` + `when_to_use` truncated at **1,536 characters** in the listing
  (configurable `skillListingMaxDescChars`) (CC-skills frontmatter table).
- `disable-model-invocation: true` removes the description from context entirely (zero cost until
  invoked) (CC-skills, CC-features).
- Body: keep `SKILL.md` **under 500 lines** (CC-skills, P-skills-bp, AS-spec); AS-spec and
  P-skills-overview add **< 5,000 tokens** recommended for the body and **~100 tokens** of metadata
  per skill.
- Once invoked, the rendered body **stays in the conversation for the rest of the session**; every
  line is a recurring token cost; "state what to do rather than narrating how or why" (CC-skills
  "Types of skill content"). Re-invoking identical content adds only an "already loaded" note.
- `/skill-doctor` (v2.1.252+) reports each skill's context cost and flags never-invoked skills
  (CC-skills, CC-pl-measure).

**Plugins.** `claude plugin details <name>` prints the plugin's **always-on** tokens (names +
descriptions + `when_to_use` of skills, agents, commands) and on-invoke cost per component; hooks
are "harness-only — no model context cost". In the official marketplace, an always-on figure of
**2,000 tokens or more** is shown highlighted to users before install. To lower it: shorten
descriptions, split the plugin (CC-pl-measure).

**MCP.** Tool search is on by default; only tool names and server instructions load. CLI tools
(`gh`, `aws` ...) remain more context-efficient than MCP servers (CC-costs, CC-features). API-level
numbers: tool search cut up-front definitions from ~77K to ~8.7K tokens (85 %); defer when
definitions exceed ~10K tokens or 10+ tools; keep the 3–5 most used tools loaded (E-advtools).

**Hook output.** `additionalContext`, `systemMessage`, `initialUserMessage` and plain stdout are
capped at **10,000 characters**; beyond that Claude gets a file path plus a 2,000-character preview
and is not asked to read the file (CC-hooks "JSON output", "Add context for Claude"). For
unchanging instructions prefer CLAUDE.md over a hook (CC-hooks).

**General principle.** Find the smallest set of high-signal tokens; context rot degrades recall
gradually as tokens grow; prefer just-in-time retrieval via lightweight references (paths, queries)
with a hybrid of a few up-front files such as CLAUDE.md (E-ctx). Keep the always-loaded memory layer
small, a wrong note is carried into every session; use a short index as the loaded header (E-memory).

## (b) Writing skill descriptions and bodies

**Description.**
- Say what the skill does **and** when to use it, with keywords users would say (CC-skills
  "Skill not triggering", P-skills-bp, AS-spec).
- **Put the key use case first**, because of the 1,536-character truncation (CC-skills).
- Write in **third person** ("Processes Excel files..."); the description is injected into the
  system prompt and mixed point of view hurts discovery (P-skills-bp).
- Limits: AS-spec and P-skills-bp: `name` ≤ 64 chars, lowercase/digits/hyphens, must match the
  directory (AS-spec), no "anthropic"/"claude" (P-skills-bp); `description` ≤ **1,024 characters**,
  no XML tags. Claude Code itself accepts up to 1,536 (description + when_to_use) in its listing.
  **Discrepancy:** a skill meant to be portable (claude.ai upload, Skills API, other clients) must
  stay within 1,024; packaging fails hard on non-spec frontmatter keys such as `argument-hint`
  (CC-skills "Using skill frontmatter outside Claude Code").
- Vague or overlapping descriptions make Claude load the wrong skill or miss one (CC-features).
  Triggers too often: make it more specific or use `disable-model-invocation` (CC-skills).
- A shorter description can stop a skill from triggering; re-test triggering after trimming
  (CC-pl-measure).
- Names: gerund form preferred (`processing-pdfs`), avoid `helper`, `utils` (P-skills-bp).
  A plugin's name is permanent: renaming makes it a different plugin for every install
  (CC-pl-publish).

**Body.**
- "Claude is already very smart": add only context Claude does not have; ask of each paragraph
  whether it justifies its token cost (P-skills-bp "Concise is key"). CC-bp: the CLAUDE.md rule
  applies to skills too, only write down what Claude cannot find itself.
- **Degrees of freedom:** high freedom (text heuristics) where many approaches are valid; low
  freedom (exact commands/scripts) for fragile sequences ("narrow bridge" vs "open field")
  (P-skills-bp).
- **Progressive disclosure:** SKILL.md as a table of contents; reference files **one level deep**
  from SKILL.md (nested references get partially read with `head`); reference files over **100
  lines** get a table of contents at the top (P-skills-bp, AS-spec).
- Put the **most important instructions near the top** of SKILL.md: after compaction only the
  first **5,000 tokens** per skill are re-attached (CC-skills, CC-ctx).
- Write guidance that must hold for the whole task as a standing instruction ("Run the tests after
  every edit"), because the file is not re-read on later turns (CC-skills "Claude stops following a
  skill").
- Prefer bundled **scripts over generated code**: more reliable, code never enters context, only
  output does; say explicitly whether to run or read a script; scripts should handle errors
  themselves ("solve, don't defer") and justify constants (P-skills-bp, P-skills-overview,
  E-skills).
- Avoid time-sensitive text (use an "old patterns" section), use consistent terminology, give one
  default instead of many options, forward-slash paths (P-skills-bp).
- `context: fork` only for skills with an explicit task; the fork does not see the conversation
  (CC-skills). With `agent: Explore`, none of the CLAUDE.md files load.
- `allowed-tools` grants permission only for the invoking turn and restricts nothing
  (CC-skills); in AS-spec it is "experimental".
- Dynamic context injection `` !`cmd` `` runs before Claude sees the skill (CC-skills); a Claude
  Code-only feature.

## (c) Hooks and permission rules instead of prose

- CC-bp frames every instruction as non-deterministic (prompt, CLAUDE.md, skill) or deterministic
  (hook, deny rule, managed setting, sandbox in strict mode). Rule: if something must happen
  every time, make it a hook, deny rule or managed setting; CLAUDE.md is for guidelines Claude may
  judge inapplicable (CC-bp "Enforce the rules that can't have exceptions").
- "If you keep adding emphasis to a CLAUDE.md line and Claude still misses it", the line belongs in
  a hook; conversely, hooks for mere preferences should be deleted (CC-bp tip).
- **Keep the enforced set small.** Every hook and deny rule sometimes fires wrongly and needs
  maintenance; at forty of them most are probably preferences (CC-bp "Choose who a rule applies
  to").
- Real enforcement needs `command`, `http` or `mcp_tool` hooks; `prompt`/`agent` hooks ask another
  model and are not deterministic. `onFailure: "block"` blocks when the hook itself crashes or
  times out (CC-bp).
- Stop hook pattern: exit 2 with the reason on stderr; after **eight** consecutive blocked stops with
  no tool call Claude Code overrides (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`) (CC-bp).
- Permission evaluation order **deny → ask → allow**, first match wins, specificity irrelevant; a
  PreToolUse hook "allow" never bypasses deny or ask rules; a hook exiting 2 blocks even where an
  allow rule matches (CC-perms). PreToolUse decisions: allow / deny / ask / defer, precedence
  deny > defer > ask > allow (CC-hooks).
- Deny rules hold in every mode including auto and bypassPermissions; `Read` deny also catches
  `cat .env` but not a script opening the file; a WebFetch domain deny does not stop `curl` unless
  the sandbox is on. Rules match the command text, so a Bash deny/ask rule "isn't a security
  boundary around the program" (CC-bp, CC-perms). For OS-level limits turn on the sandbox; strict
  sandbox mode removes the unsandboxed retry (CC-bp, CC-sandbox).
- Auto mode is a classifier and can be wrong; "never" rules belong in deny rules or hooks (CC-bp).
  E-contain: auto mode blocks ~0.4 % of benign commands but lets ~17 % of overeager actions through;
  users approved ~93 % of prompts (approval fatigue); the sandbox cut prompts by 84 %; enforce with
  the harness, not instructions.
- Hook output enters context only on specific events (SessionStart, UserPromptSubmit,
  UserPromptExpansion, PostModelSwitch plain stdout; `additionalContext` on many events); Claude
  never sees stderr of an exit-0 hook. Write injected text **as facts, not imperative system
  commands**: out-of-band command framing can trigger prompt-injection defences and Claude then
  surfaces it instead of using it (CC-hooks "Add context for Claude").
- Timeouts: default **600 s** for command/http/mcp_tool, **30 s** on UserPromptSubmit (blocks every
  prompt), 30 s prompt hooks, 60 s agent hooks (CC-hooks). Matching hooks run in parallel
  (CC-hooks-guide). Hooks can also shrink context (PreToolUse rewrites `npm test` to `| tail -n
  100`) (CC-costs "Offload processing to hooks and skills").
- Project `.claude/settings.json` deny rules apply immediately; its allow rules and hooks wait for
  the workspace-trust dialog (CC-bp). E-contain warns that project-local config is untrusted.
- Plugins ship hooks in `hooks/hooks.json` (CC-pl-components). The plugin pages describe no
  component for permission allow/deny rules; those live in settings files. Plugin subagents ignore
  `hooks`, `mcpServers` and `permissionMode` frontmatter (CC-subagents).

## (d) Delegating to subagents to save context

- Subagents pay off for: parallel independent work, keeping long output (test runs, wide searches)
  out of the main conversation, an independent reviewer, fewer tools (CC-bp "Know what subagents
  cost").
- Costs: each subagent's tokens count against the same usage; a fresh one must gather context again
  and can be slower; same model, "not a smarter answer" (CC-bp). Ask for short summaries back; set
  `model: haiku` for simple jobs; restrict `tools: Read, Grep, Glob` for a reviewer (CC-bp,
  CC-costs).
- **"Use subagents to protect your context window" is now listed as outdated advice**: running out
  of context is rare with 1M windows; subagents remain good for parallelism, noisy output and review
  (CC-bp "What you can stop doing"). CC-costs and CC-ctx still recommend delegating verbose
  operations; these agree once read together.
- Use the main conversation for back-and-forth, shared multi-phase context, quick targeted changes,
  or when latency matters; subagents for verbose output, tool restrictions, self-contained work
  (CC-subagents "Choose between subagents and main conversation"). `/btw` for a question about
  what is already in context.
- What a non-fork subagent starts with: its own system prompt, the delegation message, **all
  CLAUDE.md levels** (except built-in Explore, Plan and web-fetch, or `omitClaudeMd: true`), git
  status, preloaded skills (`skills:` field, at most 32 names). It does not get the conversation,
  invoked skills, auto memory or output style. Restate a rule in the delegation prompt if it must
  reach the subagent (CC-subagents "What loads at startup").
- **Forks** inherit the full conversation, system prompt and tools and therefore **share the
  parent's prompt cache**; a fresh subagent builds its own cache and gets a 5-minute TTL even on a
  subscription (CC-subagents, CC-cache).
- Limits: nesting up to **3 layers** below main by default (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`);
  **20** concurrent subagents (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`) (CC-subagents).
- Brief a subagent with objective, output format, tool/source guidance and boundaries; scale effort
  (1 agent / 3–10 tool calls for simple facts; 2–4 subagents for comparisons; 10+ for complex
  research); multi-agent ≈ **15×** chat tokens, single agent ≈ 4×; poor fit for most coding tasks
  and tasks sharing context (E-multi). Subagents typically return 1,000–2,000-token summaries
  (E-ctx).
- Current models delegate on their own and may over-delegate: P-prompting "Subagent orchestration"
  gives a sample line limiting delegation to parallel/isolated work. P-fable52: standing
  instructions to delegate in system prompts, skills or agent files raise cost; review those lines
  first; a longer subagent-tool description stating what a subagent costs roughly halved the
  number of subagents at `high` effort.
- Agent teams use about **7×** the tokens of a standard session when teammates run in plan mode
  (CC-costs).

## (e) Hand-over, compaction and long sessions

- What survives compaction (CC-ctx): system prompt and output style; project-root CLAUDE.md and
  unscoped rules re-injected from disk; auto memory; skill descriptions rebuilt (v2.1.304+); plan
  file; up to **five** most recently modified files re-read (a file > 5,000 tokens comes back as a
  reference only); invoked skill bodies capped at **5,000 tokens each / 25,000 total**, oldest
  dropped first; hook-added context is summarised; SessionStart hooks with matcher `compact` run
  again. Path-scoped rules and nested CLAUDE.md are summarised away and reload only on demand; to
  make a rule survive, drop `paths:` or move it to root CLAUDE.md.
- Auto-compaction on native 1M models runs at about **967K tokens**; 200K-boundary models at 200K;
  `/autocompact 500k` sets an earlier point (CC-model, CC-ctx).
- Steering: `/clear` between unrelated tasks (costs nothing); `/compact <focus>` at natural breaks
  (it is itself a large request, worst after the cache expired); `/rewind` reuses an already cached
  prefix; after **two failed corrections**, `/clear` and write a better prompt (CC-bp "Steer the
  session", CC-cache).
- A "Compact instructions" section in CLAUDE.md steers summaries (CC-costs).
- Idle compaction: on the one-hour cache a session past ~200K tokens left idle is compacted shortly
  before the cache expires (CC-bp; `idleCompaction` setting, v2.1.290+).
- Unattended runs: before starting, answer five questions: what done looks like, how it checks its
  own work, what it may touch, what stops it (`--max-turns`, `--max-budget-usd`), who signs off
  (CC-bp "Let Claude run without you").
- Long-running harness patterns: initializer session; progress file; feature list in JSON (less
  likely to be overwritten than Markdown); one feature at a time; git commits; each session starts by
  reading pwd, git log, progress file and feature list, and running `init.sh` (E-harness1;
  P-prompting "Workflows across multiple context windows"). P-prompting: consider a fresh context
  window over compaction, because current models rediscover state from the filesystem well.
- Context resets vs compaction: resets need a hand-off artifact; resets were essential for Sonnet
  4.5 but dropped for Opus 4.5+ in favour of automatic compaction. Stress-test harness components
  as models improve and remove the ones no longer load-bearing (E-harness2).
- Memory hygiene (E-memory, 2026-11-06): keep the loaded layer small; do not record what the
  environment already shows (an agent with 413 files did worse than one with ~10); keep a current-
  goal file with next steps, mark confirmed vs unconfirmed facts, record rules with their evidence;
  tell the agent what memory is for rather than prescribing how; a fixed "record only failures" rule
  cut the benefit.
- Hand-over / final reports (P-fable52 "Make reports easy to follow"): write for a low-context
  reader who has not seen tool calls; key points first; plain words; no self-invented terms; the
  sample text recommends a Simplified Technical English style.

## (f) Instruction style for current models

- **No emphasis / ALL CAPS.** CC-bp "What you can stop doing": current models follow a plainly
  worded line; piling on emphasis mostly makes Claude over-apply the rule. P-prompting: soften
  aggressive language such as "CRITICAL: You MUST use this tool" to "Use this tool when...";
  instructions written to fix undertriggering now cause overtriggering. **Disagreement:**
  P-skills-bp's iteration example still mentions Claude suggesting stronger language such as
  "MUST filter"; the newer Claude Code and prompting pages advise against it.
- **Explain why.** Giving the reason lets Claude generalise (P-prompting "Add context to improve
  performance", the text-to-speech/ellipsis example).
- **Drop obsolete prompting.** "think hard/be thorough" (effort is the control; `ultrathink` still
  works per turn), "keep going / don't be lazy" (causes over-work), describing architecture in
  CLAUDE.md (CC-bp). Effort defaults to `medium` on Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5
  (CC-bp).
- **"Never" is absolute.** P-fable52: the model treats an instruction containing "never" as
  absolute; write "ask for approval before deleting files" instead of "never delete files" when you
  want it to keep responsibility; name the routine steps that need no approval; cautions
  accumulate in memory, notes and instruction files and cause unnecessary approval requests; delete
  cautions whose reason no longer holds and rewrite absolute rules with their scope and reason.
- **Hard style limits hurt.** P-fable52: a limit such as "one instruction per sentence, in 20 words
  or fewer" makes prose choppy. E-postmortem (2026-04-23): a Claude Code system-prompt line limiting
  text between tool calls to ≤ 25 words cost about 3 % on one eval for Opus 4.6/4.7 and was
  reverted; brevity instructions can trade off against intelligence and need per-model ablation.
- **Prompts written for earlier models** (standing delegation, token budgets shown to the model,
  "think less" lines) raised cost or no longer worked on Fable 5.2; test without them (P-fable52).
- Concrete, verifiable instructions ("Run `npm test` before committing") beat vague ones; organise
  under headers and bullets; contradictions make Claude pick arbitrarily (CC-memory). Right
  altitude: neither hard-coded if-else logic nor vague guidance; start minimal on the best model and
  add instructions for observed failures (E-ctx).
- Over-engineering: current Opus models may add files, abstractions or features; a sample
  "avoid over-engineering" block exists (P-prompting "Overeagerness").
- Opus 5.5 in unattended loops may end a turn with a progress report; treat a text-only end of turn
  as a report, keep a checklist, name the early stops to avoid; add such instructions at the start
  of the session, not midway (changing `system` invalidates earlier thinking blocks) (P-opus55).

## (g) Plugin packaging and versioning

- A plugin is a directory with `.claude-plugin/plugin.json` and components: skills, commands,
  agents, hooks (`hooks/hooks.json`), MCP servers (`.mcp.json`), LSP servers, executables, themes,
  output styles, channels, monitors, a hooks module ("mod"), `userConfig` values (CC-pl-overview,
  CC-pl-components).
- **Version resolution:** manifest `version` first, then the marketplace entry's `version`, else
  the source's commit SHA (12 chars). A pinned `version` keeps every user on the cached copy until
  the string changes: "either increment `version` on every release, or omit it" in a git-hosted
  marketplace (CC-pl-loading "How Claude Code computes the version", CC-pl-publish).
- Copied plugins live in `cache/<marketplace>/<plugin>/<version>/`; `${CLAUDE_PLUGIN_ROOT}`
  changes with every version, so durable files go in `${CLAUDE_PLUGIN_DATA}`; files outside the
  plugin directory (`../shared`) are not copied; old versions are removed **14 days** after an
  update (CC-pl-loading). Plugins from a local-path marketplace load in place, no version bump
  needed.
- Validate with `claude plugin validate --strict` (fails on warnings, e.g. missing `version`);
  refer to files as `${CLAUDE_PLUGIN_ROOT}/...` in hooks and MCP configs (CC-pl-publish).
- Plugin name is permanent; kebab-case (CC-pl-publish).
- Cost transparency: `claude plugin details` shows always-on tokens; ≥ 2,000 always-on tokens is
  highlighted in the official marketplace (CC-pl-measure). Plugin skills are not affected by
  `skillOverrides`; users manage them through `/plugin` (CC-skills).
- After a mid-session update, hooks/MCP/LSP keep the old path until `/reload-plugins` (CC-pl-loading).

## (h) Prompt-cache considerations

- The cache matches the request **prefix exactly**; any change recomputes everything after it; no
  per-file caching. Order: system prompt (core instructions + tool definitions) → project context
  (CLAUDE.md, auto memory, unscoped rules) → conversation (CC-cache).
- **Invalidates the cache:** switching model; changing effort (except Fable 5.1+, Opus 5.5,
  Sonnet 5.5, Haiku 5.5 on API key or subscription); fast mode; connecting/removing an MCP server
  (incl. plugins that provide one); denying a whole tool when tool search is off; compaction;
  dropping many images; upgrading Claude Code (first turn after restart) (CC-cache).
- **Keeps the cache:** editing files; editing root or user CLAUDE.md mid-session (read at start,
  reloaded only on `/clear`, `/compact` or restart); permission-mode changes (except `opusplan`);
  output style changes; invoking skills/commands (appended as messages; a skill whose frontmatter
  names a `model` is a model switch); enabling/disabling a plugin's skills, commands, agents, hooks,
  monitors or themes (appended); `/recap`; `/rewind`; spawning a subagent (CC-cache).
- **Cache scope is one machine and directory:** the system prompt embeds auto-memory paths and the
  conversation opens with cwd, platform, shell, OS version and the git-status snapshot. Parallel
  sessions in the same directory share a cache; sequential sessions share only if the git status
  snapshot matches; different worktrees build different prefixes (CC-cache "Cache scope").
- TTL: main conversation **1 hour** on a subscription within plan usage, otherwise **5 minutes**;
  subagents, workflows, forks' helpers and compaction **5 minutes**; settable with `promptCacheTtl`
  / `subagentPromptCacheTtl` (v2.1.242+) (CC-cache). API pricing: 5-minute cache write 1.25× base
  input, 1-hour write 2×, reads 0.1× (P-cache).
- Hook-injected text: `additionalContext` is inserted at the point where the hook fired, so it is
  appended, not a prefix change, within a session. SessionStart output sits at the start of the
  conversation; varying content there (timestamps, SHAs) makes each session's prefix unique (the
  docs do not state this cost explicitly; inference from the prefix rule). Mid-session hook text is
  replayed, not re-run, on resume (CC-hooks).
- Use `/usage` "Prompt cache (main)" (v2.1.251+) for hit ratio and likely miss cause; it flags long
  context or frequent cache misses once they pass 10 % of usage (CC-cache, CC-bp, CC-costs).
- E-postmortem: dropping reasoning blocks broke cache hits and drained usage limits faster; cache
  changes need checking for quality side effects.
- P-fable52 / P-prompting: with preserved thinking, editing the system prompt, tools or an earlier
  message between requests invalidates later thinking blocks (API-level; Claude Code handles this
  for its users).

## (i) Testing and evaluating skills

- Evaluation first: run Claude on representative tasks **without** the skill, document failures,
  build **three** scenarios, measure the baseline, write minimal instructions, iterate (P-skills-bp
  "Build evaluations first"; checklist: at least three evaluations, tested with Haiku, Sonnet and
  Opus). Claude A writes the skill, a fresh Claude B uses it; observe navigation (P-skills-bp).
- Measure **triggering** and **output quality** separately, each against a baseline run in a fresh
  session with the skill off (`skillOverrides: "off"`; for plugin skills use `claude plugin eval`)
  (CC-skills "Evaluate and iterate on a skill").
- `claude plugin eval` (v2.1.269+): each case runs **3 times** with and 3 times without the plugin
  (Δ = contribution); graders include regex, `tool_used: Skill`, rubric judged by a model; exits
  non-zero below `--threshold` for CI; `claude plugin eval init` drafts cases; every run is a real
  model call (CC-pl-evals). Common first finding: Δ ≈ 0 with `tool_used: Skill` failing → fix the
  description.
- skill-creator plugin: `evals/evals.json`, isolated subagent per case, benchmark of pass rate,
  time and tokens with vs without, blind A/B between versions, description tuning with
  should-trigger / should-not-trigger prompts; not interchangeable with plugin-eval files (CC-skills).
- General eval practice (E-evals, 2026-01-09): 20–50 tasks from real failures; balance should- and
  should-not-trigger cases; isolate trials; grade outcomes not paths; pass@k vs pass^k (75 % per
  trial ≈ 42 % for three in a row); capability evals graduate into regression suites; read
  transcripts.
- Tools: evaluation-driven development with realistic multi-step tasks and transcript reading
  (E-tools). Claude Code caps tool responses at 25,000 tokens by default (E-tools, 2025).

---

## Disagreements and recent changes noted

1. **Description length:** 1,024 chars (AS-spec, P-skills-bp, claude.ai/API packaging) vs 1,536
   chars listing cap in Claude Code (description + `when_to_use`).
2. **Emphasis:** P-skills-bp still shows "MUST filter" as a possible fix; CC-bp and P-prompting
   say emphasis causes over-application and should become a hook or be softened.
3. **Subagents for context:** CC-bp now lists "use subagents to protect your context window" as
   outdated; CC-costs / CC-ctx still advise delegating verbose operations. Consistent reading:
   delegate for noisy output and parallelism, not for "saving context" in general.
4. **Model choice:** CC-costs says Sonnet handles most coding and Opus is for complex work; CC-bp
   says the default Opus 5.5 handles most coding and Sonnet costs less on routine work.
5. **New in 2026 (versions named in the docs):** native AGENTS.md reading (v2.1.277), per-file
   size limit for on-demand instruction files (v2.1.309), `/doctor prompt-audit` (v2.1.283),
   `/skill-doctor` (v2.1.252), skill descriptions rebuilt after compaction (v2.1.304), the
   1 %-of-context listing budget with least-used-first dropping, `claude plugin details` cost
   projection, `claude plugin eval`, cache TTL settings (v2.1.242), idle compaction (v2.1.290),
   fork mode on by default with cache sharing, effort-level changes no longer breaking the cache on
   the newest models, the "What you can stop doing" table.
