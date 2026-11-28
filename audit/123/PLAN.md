# Audit of the team edition: measurements and refactor plan (phase 1 of #123)

Base: `origin/main` at `e27f84f`, measured 2026-11-22. The evidence is in `audit/123/` on branch
`agent/123-audit`: one file per subject, with the two scripts that produced the numbers
(`measure_context.py`, `transcript_stats.py`). Token figures are bytes ÷ 4, an estimate; no
tokenizer was at hand. Nothing in the repository was refactored.

## The outcome in six lines

1. **This repository's text is a small part of a chat's context.** It puts 14.3 kB (about 3.6k
   tokens) into every session and every subagent, about 7% of the 52k tokens an issue chat holds
   at its first call. Per issue chat it adds about 55 kB of skill text on top.
2. **Trimming that text is worth doing and safe:** about a third less per issue chat (83 kB to
   56 kB), without losing a rule.
3. **The larger waste is round trips that fail,** and every one re-reads the whole context:
   962 sandbox failures, 499 hook blocks, 351 failed `archive_session` calls and 95 "errors"
   that are a script's normal answer, in six weeks.
4. **A quarter of all Bash calls run with the sandbox switched off** (16,235 calls; 28% in week
   46). 96% of them were switched off before anything failed, mostly a `gh` or a network
   command chained to something else. The person answered 666 prompts; about 207 of them were
   such a push or fetch.
5. **Six statements in the documents are wrong and twelve mislead;** two skills contradict a
   ruling of 2026-11-11.
6. **The repository has no guard against the text growing back,** and four files sit at the edge
   of a limit (`rules/core.md` 7,969 of 8,000 bytes; the `issue-handover` body 95% of the
   standard's 5,000 tokens; its description 499 of 500 characters; `method.md` 495 lines).

## 1. Measurements

### 1.1 Context cost by when it loads (`context-cost.md`)

| When | What | Bytes | Tokens (est.) |
|---|---|---:|---:|
| Always, Claude Code | `rules/core.md` and its import line | 8,007 | 2.0k |
| Always, Claude Code | 14 skill names and descriptions (core 3,304; issue-chats 1,086; codex 921; web-deploy 524; security 447) | 6,282 | 1.6k |
| Always, Codex | the inlined block (`core.md` + `codex.md`) and the listing | about 15,100 | 3.8k |
| Always | hooks at session start or per prompt | 0 | 0 |
| Per chat start | `archive-finished-chats` (261 invocations in the window) | 6,843 | 1.7k |
| Per hand-over | `issue-handover/SKILL.md` (217 invocations) | 19,879 | 5.0k |
| Per landing | `ship-change/SKILL.md` (70), `local-main.md` in local-main repositories | 13,822 + 6,951 | 3.5k + 1.7k |
| Per review | `review-change` (53), `review-security` + `checklist.md` (23) | 6,162; 6,192 + 21,156 | 1.5k; 6.8k |
| Per cleanup | `cleanup-merged` (26) | 8,170 | 2.0k |
| Rarely | `method.md`, read whole 22 times | 38,722 | 9.7k |
| Once per install | `docs/install.md` and the installer's docstring | 33,521 + about 5,000 | 9.6k |

- A text loaded early is carried on every later call of that chat. `archive-finished-chats`
  loads at the start of every issue chat, so each of its bytes costs more than a byte of
  `issue-handover`, which loads at the end.
- Against #82: the start cost holds over 421 issue chats (Opus 52.4k at call 1 and 83.9k at
  call 2; Fable 56.7k and 88.4k). The 31k that arrive at call 2 come from the desktop app, not
  from this repository.
- Against #98: no Codex line is left in what a Claude-only install loads. On a machine with
  both clients each client still lists one skill it cannot use (488 and 433 bytes).
- Issue chats elsewhere peak at a median of 312k tokens (n=434; 57% pass 300k); here at 229k
  (n=30). Subagents account for 47% of all output tokens.

### 1.2 Friction for the person (`transcripts.md`)

Window: 2026-10-12 to 2026-11-22, 718 main sessions and 1,234 subagent transcripts, 114,965
Bash calls. Counts and tool names only; no message text was read into the notes.

| Friction | Count | Cause |
|---|---:|---|
| Bash calls with the sandbox off | 16,235 | `gh` chained or piped (4,807); `cd <path> && <network command>` (3,713); `git -C` network calls (340, the class of #122) |
| Sandbox failures | 962 | this repository's sessions fail 3.4% of their Bash calls, the others 0.5% |
| Prompts the person answered | 666 | about 207 are a push or fetch after `cd` or with `git -C` |
| Tool calls denied | 1,113 | hooks 499, the person 190, settings rules 179, auto mode 236 |
| `archive_session` failures | 351 of 765 (46%) | 163 are the archive guard's "`get_session` not called first"; 110 were rejected by the person |
| Git guard blocks | 138 | 31% are "brace expansion it cannot read", a likely false positive; a here-document whose body holds `{a,b}` is refused too (`pre_tool_git_guard.py:412-414`) |
| `promote_main.py` | 62 sandbox failures, 62 identical reruns | the script reaches GitHub and the first run is inside the sandbox |
| `overlap_check.py` | 95 "errors" | exit 1 means "overlaps found", its designed answer |
| Edit failures | 77 | 51 are "not read first" |

### 1.3 Duplication and drift (`duplication-drift.md`)

- **6 wrong, 12 misleading, 24 facts stated in more than one place, 5 groups of duplicated
  code.** Every path, link and documented flag resolves.
- Wrong: `HANDOFF.md:3` is dated 2026-11-11 and describes work up to 2026-11-22;
  `AGENTS.md:28-32` names four version places where there are three; `docs/install.md:105`
  says a rerun never removes a plugin; `repo-docs/SKILL.md:25` makes one client's folder
  layout the rule in a shared skill; `templates/company-overlay/AGENTS.md:30` says the
  dependency audit always contacts PyPI; the headers of `install.sh` and `install.ps1` (#93).
- Against a ruling: `review-change/SKILL.md:10` and `method.md:364` say a standing grant lets
  `merge_pr.py` merge; `ship-change/SKILL.md:191` lets a small change skip the review
  subagent, where `issue-handover/SKILL.md:193` always runs it (both: the ruling of
  2026-11-11).
- Misleading: the issue-chat skills treat an overlapping branch older than 7 days as a reason
  to pick another issue, while `overlap_check.py` lists only 14 days and never shows older.
- `issue-handover/SKILL.md` and `method.md` (58.6 kB together) restate each other: the
  lifecycle, the hand-over in place, the push and merge rule three times, the question label.
- Code: a `git()` wrapper is defined in 19 scripts with 5 behaviours; `gh_command()` has 6
  identical copies; three readers parse the `HANDOFF.md` settings, one in a different order.
  Three deliberate copies are missing from the list in `AGENTS.md`.

### 1.4 Clarity (`clarity-skills.md`)

The ten worst are listed there with `file:line`. Beside the two contradictions above: long
runs wait in the foreground in one skill and in the background in two others;
`issue-handover/SKILL.md:68` says to stop runs that lines 55-59 say never to stop; a claim
means two things (`ship-change:71-74`, `method.md:396-400`); `cleanup-merged:11-13` writes
"default branch" for the landing branch; `issue-handover/SKILL.md:36-47` is one sentence of
1 kB with six stacked conditions; four scripts print their whole header (up to 5.2 kB) for a
mistyped flag.

### 1.5 Tooling (`tooling.md`)

- **Hooks:** every Bash call starts Python 10 times (14 in an issue chat), about 455 ms of
  CPU (800 ms); the wrappers' version check is a second start per guard, 23 ms each. An Edit in
  an issue chat costs about 2 × 200 ms for the context gate.
- **Installer:** `--update` and `--uninstall` end with `done` and exit 0 after printing `FAIL`
  (`installer.py:297-299`, `331-340`). There is no status command. About 13 kB (38%) of
  `docs/install.md` matters only to Codex or Google Cloud users.
- **Tests:** 32 of 33 files pass, 1 skipped (no pseudo-terminal in the sandbox), in 13 min
  6 s, run one after another. Skips inside a file are invisible to `--require-all`.
- **Maintainers:** 28 of the last 100 commits edit the version files by hand; every pull
  request that touches a plugin changes the same version lines, so two of them conflict.
- **Unused:** no dead script or function. Never invoked in six weeks: `codex-worker` and
  `codex-issue-chats` (new); `efficient-design`, `repo-docs` and `check-web-deploy` once or
  twice. Never read: `review-security/sources.md` (37.5 kB, maintainers' material).

## 2. What the sources say

All read on 2026-11-22 by the research subagents; pages without a date are marked undated.
The full notes with 41 and 35 sources are in `sources-anthropic.md` and
`sources-openai-skills.md`. Three load-bearing claims (marked ✓) were fetched a second time.

| Recommendation | Source |
|---|---|
| ✓ The skill listing gets 1% of the context window; over it, the descriptions of the least-used skills are dropped; one entry is cut at 1,536 characters. So: the trigger first. | https://code.claude.com/docs/en/skills (undated) |
| ✓ After compaction only the first 5,000 tokens of an invoked skill come back, 25,000 in all. So: the critical rules at the top. A skill stays in context once invoked. | same |
| Body under 500 lines and 5,000 tokens; description at most 1,024 characters; references one level deep; a reference says when to load it. | https://agentskills.io/specification (undated); https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices (undated) |
| Cut what the agent would get right without it; keep the gotchas; defaults, not menus. | https://agentskills.io/skill-creation/best-practices.md (undated) |
| Scripts a skill runs: short `--help`, small structured output, documented exit codes, never interactive. | https://agentskills.io/skill-creation/using-scripts.md (undated) |
| A rule file under 200 lines; `@` imports save no context; what must hold every time belongs in a hook or permission rule, not in more emphasis. | https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/best-practices (undated) |
| Plain wording over emphasis; "never" is read as absolute and stacked cautions cause needless approval requests. | https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2 (undated) |
| Subagents cost extra tokens: for parallel work, noisy output and independent review, not to be smarter. A fresh subagent loads every rule file again. | https://code.claude.com/docs/en/sub-agents, https://code.claude.com/docs/en/best-practices (undated) |
| ✓ A manifest that pins `version` keeps users on the cached copy until the string changes; without `version` in manifest and marketplace entry, the commit SHA is the version. | https://code.claude.com/docs/en/plugins/loading (undated) |
| ✓ Codex stops adding instruction files at 32 KiB in total (`project_doc_max_bytes`). | https://learn.chatgpt.com/docs/agent-configuration/agents-md (undated) |
| Codex's skill listing gets 2% of the window; descriptions are shortened first. Codex hooks fail open and have no "ask". | https://learn.chatgpt.com/docs/build-skills, https://learn.chatgpt.com/docs/hooks (undated) |
| Lean prompts in a vendor's internal coding evals: +10–15% score, −41–66% tokens ("directional"). ALWAYS and NEVER only for true invariants; contradictions harm more than missing detail. | https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6.md (undated) |
| Trigger evals: about 20 queries, half of them near-misses that must not trigger, 3 runs each; output evals with and without the skill. | https://agentskills.io/skill-creation/optimizing-descriptions.md, https://agentskills.io/skill-creation/evaluating-skills.md (undated); https://code.claude.com/docs/en/plugin-evals (undated) |
| The one controlled study: context files added about 20% cost and no significant gain in success; files written by people +2.4 points, generated ones −0.5 to −2; tools named in the file were used reliably. Python tasks, older models. | Gloaguen et al., https://arxiv.org/abs/2602.11988 (v3, 2026-09-29) |
| A small loaded layer works better than a large one. | https://www.anthropic.com/research/components-of-agent-memory (2026-11-06); https://www.anthropic.com/research/effective-context-engineering-for-ai-agents (2025-09-29) |

How far this carries: the evidence agrees on short, hand-written files that hold only what an
agent cannot derive. No study tests rule files of this size against outcomes, so the savings
below are measured in bytes and counts, not in success rates.

## 3. Proposals, ranked by benefit against risk

Risk: low = text or an additive script with tests; medium = a script interface or a hook's
process layout; high = a guard's decisions. "User's word" = a path that merges only on the
maintainer's word (the ruling of 2026-11-09).

| # | What changes | Saving (measured, or marked est.) | What it might break | Ruling touched |
|---|---|---|---|---|
| P1 | **Correct the wrong and contradicting statements** (§1.3, §1.4): 6 wrong, the 2 against the 2026-11-11 ruling, the 7-against-14-days overlap window, the claim's two meanings, foreground against background runs. | 18 statements; no bytes. Removes misreadings at their source. | Nothing: text made true to the code. | None reversed; two skills brought back under the 2026-11-11 ruling. `AGENTS.md`: user's word. |
| P2 | **Archive without the failed call:** `archive-finished-chats` calls `get_session` before `archive_session` as one stated step; the 990-byte sentence becomes a table; body 6.8 to about 4.5 kB. | 163 guard blocks and up to 351 failed calls per six weeks; 2.3 kB at every chat start. | The sweep archives less or more if the table is wrong: covered by `tests/chat_archivable.py`. | None. Order with #67 and #30. |
| P3 | **Scripts answer briefly:** a mistyped flag prints one line and the usage, not the header (5.2 kB at `merge_pr.py`); `--help` is short; `next_issue.py` prints the one issue the skill uses; `promote_main.py` and `review_verdict.py` say in one line that they must run outside the sandbox, before doing work. | 3–6 kB per wrong call; 62 + 16 failed first runs. | A caller that parses the old output: checked by the tests. `merge_pr.py`: user's word. | None. |
| P4 | **`issue-handover` by moment of use:** `SKILL.md` keeps the hand-over steps (19.9 to about 9 kB); `method.md` splits into references read when their moment comes (start, settings, early hand-over, fallbacks, side chats, session tools); reasons and measurements move to a design document no session loads; the stacked sentences become tables. | 10.9 kB at each of 217 hand-overs; a whole-method read falls from 38.7 kB to 3–4 kB. Est. | A step lost in the move: a section-by-section map in the pull request, and the trigger probe. | The `Binds` lines of four rulings name `method.md` §1, §4, §6: updated, not reversed (**Q2**). Order with #104, #110. |
| P5 | **The other core skills lose their rare branches:** `ship-change` 13.8 to about 9.8 kB, `local-main.md` 7.0 to 5.5, `cleanup-merged` 8.2 to 4.6 (its *What the script checks* repeats the script's header), `review-change` 6.2 to 5.2, `requirements` 7.6 to 6.0. | About 10 kB per landed change. Est. | As P4. | None. After #83. |
| P6 | **A budget that only rises on purpose,** in `tests/skills_format.py`: bytes per skill body and the sum of all descriptions, set at today's size after each trim. | Keeps P4, P5 and P8. | A pull request that grows a skill must raise the number in the same change: intended. | Extends the rule budget of `AGENTS.md` to skills (**Q6**). |
| P7 | **The sandbox guard names the lone call for every chained network command,** after #122: `gh` in a chain or a pipe, `cd <dir> && git push`, and a call that switches the sandbox off although a lone form exists. | Up to 8,500 of the 16,235 unsandboxed calls and about 207 of the 666 prompts per six weeks. | A refusal where no faithful lone form exists: as in #122, pass when unsure. | **The guards' semantics (Q4).** After #122. User's word. |
| P8 | **Descriptions with the trigger first, in about 300 characters.** | 1.5 kB in every session and subagent; nothing is cut off when the listing is over its 1%. | A skill triggers less: measured before and after with `tests/skill_triggers.py`, which spends tokens. | None, but the probe costs (**Q3**). |
| P9 | **`rules/core.md` from 7,969 to about 6,700 bytes without losing a rule:** the command spellings the git guard prints anyway, two pointers to skills, a tighter personal-data line, one sentence for the closing-keyword pair. I write the diff; nothing lands without his word. | 1.2 kB in every session and subagent of every user; room under the budget again. | A rule read more weakly. The guards are opt-in, so no rule shrinks to a bare pointer. | **The core rules are his (Q1).** User's word. |
| P10 | **The git guard reads here-document bodies and plain braces without refusing.** | About 43 blocks per six weeks, and the here-document case. | A command the guard should refuse passes: each narrowed case gets a test, the differential test stays. | **The guards' semantics (Q4).** After #33 and #118. User's word. |
| P11 | **One Python start per hook:** drop the version check from `run-python.sh` and `run-hook.sh` (checked once at install instead); a cheaper context gate. | 90 ms of CPU per Bash call (115k calls in six weeks); up to 2 × 180 ms per Edit in an issue chat. | An unsupported Python fails later and less clearly: the installer's check names it. | Hooks: user's word. Semantics unchanged. |
| P12 | **`overlap_check.py` exits 0 when it found overlaps** and says so in its first line; exit 1 is left for failures. | 95 false "errors" per six weeks. | `push_branch.py` and the skills read the exit code: changed in the same pull request. | A script interface (**Q5**). |
| P13 | **Maintainers' tools:** `tools/bump_version.py` (three places, one command); `tools/sync_copies.py` owns the list of deliberate copies and writes them; `AGENTS.md` corrected to three places and five copies. | 28 of 100 commits no longer edit versions by hand; the "forgot one place" class is gone. | Nothing shipped changes. | The version rule stays (**Q7** asks about dropping `version`). |
| P14 | **Installer:** `--update` and `--uninstall` exit non-zero after a `FAIL`; `install.sh --status` prints what is installed and wired; `docs/install.md` moves its Codex and Google Cloud parts to files the installing agent reads only with those in the plan. | Two failures no longer reported as success; 13 kB off a Claude-only install. | The installer: user's word, tested in temporary homes. | In the line of the #98 ruling. With #47 and #93. |
| P15 | **Smaller skill trims:** `review-security` step 3 and stack notes per stack (5.1 kB), `sources.md` to maintainers' documents; the Codex skills' rare routes to references (9.5 to 6.0 and 7.9 to 4.5 kB). | 5–10 kB per security review; 7 kB per Codex chat. Est. | As P4. | None. After #121 and #115. |
| P16 | **Tests in parallel,** and skips inside a file counted by `--require-all`. | 13 minutes to about 4 (est.) per local run and per CI job. | Tests that share a temporary folder: found by running them. | None. |
| P17 | **Shared helpers per plugin** for `git`, `gh` and the settings reader (120 identical and about 190 near-identical lines). | Maintenance only. | Behaviour differs between the 5 `git()` variants: medium risk. | None. Last. |

**Not proposed.** Splitting the delete guard (2,057 lines, the lowest test ratio): high risk,
only after #118 and #122 and on its own decision. One dispatcher process for all guards: the
same. Removing the rarely used skills: they cost 100–900 bytes each in the listing and are
young. Custom subagent definitions that skip the rule files: the core rules must hold in
subagents too. The 31k the desktop app adds at call 2: not this repository's.

**What the whole plan is worth, honestly.** P2, P4, P5, P8 and P9 take about 27 kB (6.8k
tokens, est.) off an issue chat, 2–3% of its peak. P2, P3, P7, P10 and P12 remove on the order
of 1,500–2,500 failed or needless round trips per six weeks at this volume, each a re-read
of the whole context, and about a third of the prompts. The second group is the larger gain for
the person; the first keeps the text clear and under its limits.

## 4. Sub-issues, in order

Each is one session. Pull requests in the same plugin conflict on its version lines, so the
order goes by plugin, and work in flight goes first.

| Order | Sub-issue | Proposals | Plugin or path | Waits for |
|---|---|---|---|---|
| 1 | Maintainers' tools and the budget test | P13, P6 | `tools/`, `tests/`, `AGENTS.md` | nothing; first, so later ones bump with one command |
| 2 | True statements | P1 | core, issue-chats, `docs/`, `HANDOFF.md`, `templates/` | takes #93 and #74 along |
| 3 | Archive without the failed call | P2 | issue-chats | #67, #30 |
| 4 | `issue-handover` by moment of use | P4 | issue-chats | 3; #104, #110 |
| 5 | Scripts answer briefly; overlap exit code | P3, P12 | core | #83 |
| 6 | Core skills trimmed | P5 | core | 5 |
| 7 | Descriptions, with the trigger probe | P8 | all plugins | 4, 6 |
| 8 | `rules/core.md` tightened | P9 | `rules/` | the answer to Q1 |
| 9 | Hook starts | P11 | guards, issue-chats | #122 |
| 10 | Sandbox guard: every chained network command | P7 | guards | #122, 9 |
| 11 | Git guard: here-documents and braces | P10 | guards | #33, #118, 10 |
| 12 | Installer and the install guide | P14 | `tools/`, `docs/` | #47 |
| 13 | Security and Codex skills trimmed | P15 | security, codex | #121, #115 |
| 14 | Tests in parallel | P16 | `tests/`, CI | #102 |
| 15 | Shared helpers | P17 | core, issue-chats | all above |

`overlap_check.py` was not run for these: there are no branches yet. The table above comes
from the open issues and their paths; no pull request is open.

## 5. Questions for the maintainer

1. **Q1, `rules/core.md`.** May I propose a tightened core (about 6,700 bytes, no rule lost) as
   a diff for your word? Recommended: yes.
2. **Q2, the method's split.** The `Binds` lines of four rulings change to the new file names;
   the rulings stay. Agreed?
3. **Q3, descriptions.** About 300 characters with the trigger first, measured before and
   after with the live probe (it spends tokens, two requests per skill). Agreed?
4. **Q4, the guards.** Two changes to what a guard decides: the sandbox guard also refuses a
   chained `gh` or network command and an unneeded sandbox escape when a lone form exists
   (P7); the git guard stops refusing here-document bodies and plain braces (P10). Each
   with tests and your word on the merge. Agreed, one of them, or neither?
5. **Q5, `overlap_check.py`.** Exit 0 for "overlaps found"? Recommended: yes.
6. **Q6, the skill budget.** A test that fails when a skill body or the sum of the
   descriptions grows, until the number is raised in the same change. Agreed?
7. **Q7, versions.** Keep the version in three places with a bump script (recommended), or
   have a sub-issue measure in both clients whether leaving `version` out (the commit SHA
   becomes the version) removes the chore? The second reverses the rule in `AGENTS.md`.
8. **Q8, scope.** All fifteen, or a cut? The ten that matter most: 1–7, 9, 10, 12.

Limits of this audit: token figures are estimates; hook times come from one Mac inside the
sandbox; the installer was read and tested in temporary homes, never run for real; prompts
raised by the delete guard and the personal-data check cannot be counted from transcripts; the
content of the security checklist and of the web-deploy references was not reviewed.
