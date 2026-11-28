# Audit #123: friction and use, measured from the maintainer's Claude Code transcripts

Measured 2026-11-22 with `audit/123/transcript_stats.py` (Python 3 stdlib, streaming; prints
aggregates only). Re-run: `python3 audit/123/transcript_stats.py --until 2026-11-22` (add `--json`
for the machine-readable form). Runtime about 40 s.

**Privacy.** Only counts, rates, tool names, this repository's skill and script names, guard
reason phrases (from the guards' own source) and command shapes are reported. A command shape
keeps the first word, the subcommand of `git`/`gh`/`cargo`/…, and this repository's script names;
every path becomes `<path>`, every other argument `<arg>`, a leading environment assignment
`VAR=<value>`. Projects other than this repository and its overlay are labels ("other project A",
the largest by transcript volume). `AskUserQuestion` headers are reduced to three classes.

## 1. Source, window and volume

| item | value |
|---|---|
| transcripts | `~/.claude/projects/*/` (all projects of the maintainer) |
| window | 2026-10-12 to 2026-11-22 (ISO weeks W42-W47); entries are filtered by their own `timestamp`, files by modification time |
| effective start | W42 holds only 6 sessions that *started* in it (older transcripts are pruned by Claude Code), so read W43-W47 as the full weeks |
| files read | 2,475 (main sessions and subagent transcripts) |
| entries parsed | 442,918 (`assistant`, `user`, `system`; plus `attachment` entries that carry a context-limit note) |
| main sessions | 718 (a main session = one `<session>.jsonl`) |
| subagent transcripts | 1,234 (`<session>/subagents/**/agent-*.jsonl`): **included** in tool, guard, sandbox and error counts; **excluded** from per-session context and start-cost numbers, reported separately for tokens |
| project groups | "repo" = this repository (30 main sessions) + its overlay `agent-rules` (103); "other" = 26 other projects (585, of which other project A 493) |

**Session kinds** (used throughout): *issue chat* = first `gitBranch` matches `agent/<digit>`;
*short probe* = at most 3 API calls (mostly `claude -p` probes and test runs: Haiku 59, Fable 5.1
50); *other session* = the rest. Entry points: 254 desktop, 464 CLI.

### Sessions per week (main sessions, by the week of their first entry)

| week | other issue chat | repo issue chat | other session | repo other session | short probe | total |
|---|---|---|---|---|---|---|
| W43 | 27 | 0 | 50 | 8 | 21 | 106 |
| W44 | 112 | 0 | 10 | 5 | 29 | 156 |
| W45 | 31 | 0 | 10 | 3 | 58 | 102 |
| W46 | 161 | 10 | 3 | 21 | 7 | 202 |
| W47 | 103 | 20 | 10 | 3 | 10 | 146 |

Subagent transcripts per week: W43 231, W44 278, W45 50, W46 386, W47 188.
Bash calls per week: W42 12,277, W43 18,780, W44 20,204, W45 7,598, W46 38,111, W47 17,995
(total 114,965; repo group 11,888, other 103,077).

### Tokens per session (deduplicated by API message id)

| kind | n | output median | output p90 | cache-read median | API calls median |
|---|---|---|---|---|---|
| other issue chat | 434 | 78k | 179k | 17.2M | 82.5 |
| repo issue chat | 30 | 53k | 122k | 13.7M | 84.5 |
| other session | 89 | 44k | 209k | 9.8M | 71 |
| repo other session | 40 | 108k | 367k | 24.7M | 115.5 |
| subagent transcript | 1,234 | 29k | 89k | 5.3M | 41.5 |

Subagents produced 52.7M output tokens against 58.7M in all main sessions together (47 % of all
output) and 13.6B of 32.0B cache-read tokens (43 %).

## 2. Skill use

Matcher: `Skill` tool_use `input.skill` (plugin prefix stripped, base name in this repository's
skill list); `/<skill>` slash commands (`<command-name>` in user turns: **0 found**); `Read` of
`…/skills/<skill>/<file>.md`. Invocations before W46 have no `agentic-github-flow-*` prefix: they
are the predecessor skills of the same names in the overlay repository (prefix `<none>`: W43 72,
W44 237, W45 58, W46 76; prefixed: W46 190, W47 165).

| skill (plugin) | Skill calls | repo group / other | W43 | W44 | W45 | W46 | W47 | SKILL.md / reference reads |
|---|---|---|---|---|---|---|---|---|
| archive-finished-chats (issue-chats) | 261 | 10 / 251 | 45 | 88 | 28 | 68 | 32 | 10 |
| issue-handover (issue-chats) | 217 | 7 / 210 | 0 | 91 | 24 | 82 | 20 | 20 / method.md 22 |
| open-issue (core) | 127 | 10 / 117 | 23 | 49 | 4 | 38 | 13 | 5 |
| ship-change (core) | 70 | 8 / 62 | - | - | - | 51 | 19 | 6 / local-main.md 9 |
| review-change (core) | 53 | 47 / 6 | - | - | - | 9 | 44 | 3 |
| cleanup-merged (core) | 26 | 20 / 6 | - | - | - | 9 | 17 | 6 |
| review-security (security) | 23 | 17 / 6 | - | 4 | - | 2 | 17 | 2 / checklist.md 4 |
| requirements (core) | 12 | 0 / 12 | - | 4 | 1 | 6 | 1 | 7 |
| spec-first (core) | 5 (W42: 1) | 3 / 2 | 3 | 1 | - | - | - | 3 |
| repo-docs (core) | 2 | 0 / 2 | - | - | 1 | 1 | - | 2 / skill-standard.md 2, skeleton.md 1 |
| efficient-design (core) | 2 | 0 / 2 | - | - | - | - | 2 | 0 |
| check-web-deploy (web-deploy) | 1 | 0 / 1 | 1 | - | - | - | - | 1 / supabase, vercel, google-auth 2 each, cloud-run, dashboard 1 |
| codex-worker (codex) | **0** | - | | | | | | 1 |
| codex-issue-chats (codex) | **0** | - | | | | | | 1 |

Never invoked: **codex-worker, codex-issue-chats** (both read once, during the #98 split). Reference
files never read in the window: review-security `sources.md`, check-web-deploy `cloud-sql.md`,
`iap.md`, `mail.md`, `privacy.md`. A stale reference was read twice: `issue-handover/codex.md`
(moved to the codex plugin by #98).

Other skills (not this repository's): 998 `Skill` calls, not broken down.

## 3. Script use

Matcher: a Bash command *runs* a script when the script's file name is a segment's command or the
first non-option argument of `python3`/`sh`/`bash`/`uv run`; every other mention (cat, grep,
sed, tests) is counted apart. Failure: the tool_result's `is_error`. Where it ran from: the path
in the command (installed plugin `~/.agentic-github-flow/…` or `~/.claude/plugins/…`; this
repository's checkout; the overlay repository's predecessor copy).

| script | runs | errors | error rate | repo / other group | predecessor / installed / checkout |
|---|---|---|---|---|---|
| overlap_check.py | 1,118 | 113 | 10.1 % | 86 / 1,032 | 735 / 354 / 27 |
| promote_main.py | 971 | 118 | 12.2 % | 53 / 918 | 594 / 365 / 11 |
| new_worktree.py | 941 | 13 | 1.4 % | 111 / 830 | 584 / 328 / 28 |
| start_issue_chat.py | 505 | 19 | 3.8 % | 64 / 441 | 219 / 248 / 35 |
| clone_dedupe_worktree.py | 375 | 4 | 1.1 % | 6 / 369 | 258 / 115 / 2 |
| next_issue.py | 307 | 8 | 2.6 % | 24 / 283 | 235 / 59 / 12 |
| review_verdict.py | 195 | 24 | 12.3 % | 195 / 0 | 0 / 181 / 14 |
| chat_archivable.py | 184 | 8 | 4.3 % | 40 / 144 | 0 / 155 / 29 |
| remove_merged_worktree.py | 152 | 9 | 5.9 % | 74 / 78 | 0 / 134 / 18 |
| merge_landing.py | 133 | 14 | 10.5 % | 47 / 86 | 0 / 91 / 42 |
| landing.py | 123 | 4 | 3.3 % | 51 / 72 | 0 / 90 / 33 |
| scan_secrets.py | 103 | 3 | 2.9 % | 79 / 24 | 26 / 40 / 37 |
| codex_worker.py | 98 | 9 | 9.2 % | 77 / 21 | 0 / 24 / 63 |
| push_branch.py | 81 | 3 | 3.7 % | 80 / 1 | 0 / 69 / 12 |
| audit_dependencies.py | 60 | 2 | 3.3 % | 38 / 22 | 51 / 1 / 8 |
| delete_merged_branch.py | 48 | 2 | 4.2 % | 48 / 0 | 0 / 44 / 4 |
| merge_pr.py | 45 | 2 | 4.4 % | 45 / 0 | 0 / 11 / 34 |
| codex_tools.py, codex_import.py, codex_job.py | 26, 14, 1 | 0, 5, 0 | | almost all repo | |
| guard and hook scripts run by hand (tests, `--check`) | 35 archive_guard, 16 context_limit, 14 question_label, 11 personal_data, 8 sandbox_network, 7 git_guard, 4 delete_guard, 4 merge_guard, 10 shell wrappers | | | repo | |

**Error classes** (exit code from `Exit code N`; "sandbox" = the result matched the sandbox
matcher of §5): overlap_check.py 95 of 113 are **exit 1 = "overlaps found"**, the script's
designed answer, which Claude Code shows as a failure; promote_main.py **61 sandbox** failures
and 49 other exit-1 refusals; review_verdict.py 16 sandbox, 2 permission; merge_landing.py 7 hook
blocks, 4 sandbox.

**Never run by an agent:** `handover_note.py`, `push_paths.py`, `work_proof.py`: all three are
libraries imported by other scripts (start_issue_chat/archive_guard; merge_pr/push_branch;
chat_archivable, context_limit, merge_landing, remove_merged_worktree, the merge guard). The
hook-only scripts (from `plugins/*/hooks/hooks.json`): `archive_guard.py`, `context-gate.sh`,
`pre_tool_delete_guard.py`, `pre_tool_git_guard.py`, `pre_tool_merge_guard.py`,
`pre_tool_personal_data.py`, `question_label.py`, `run-guard.sh`, `run-hook.sh`, `run-python.sh`;
`pre_tool_sandbox_network.py` and `context_limit.py` are hooks too (installer-wired and behind
`context-gate.sh`).

## 4. Hook and guard friction

Matcher: a tool_result whose entry carries `permissionDecision.source == "hook"`, named by the
guard's own message prefix in the result text ("Blocked by the git guard", "Refused by the
sandbox-network guard", "archive guard:", "question label: this question", "context limit:",
"Refused by the merge guard", …). The message alone also appears in test and `--check` output
(git guard 172, archive guard 206 mentions), so only hook-sourced results count as blocks.

| guard | blocks (hook reject) | tool | next Bash: same shape changed / other command / identical |
|---|---|---|---|
| archive guard | 171 | archive_session | (not Bash) |
| git guard | 138 | Bash | 53 / 85 / 0 |
| sandbox-network guard | 102 | Bash | 13 / 89 / 0 |
| question label | 16 | AskUserQuestion 14, wrap_up 2 | |
| context limit (hard stop) | 4 | Bash 3, Read 1 | |
| merge guard | 0 | | |
| delete guard, personal-data check | not derivable | they answer "ask": the prompt's reason is not stored in the transcript; their messages appear 25 and 21 times in any result, mostly tests | |
| other (app-internal: `update_plan` "Not shown" 64, SendMessage 2, other 2) | 68 | | |

**Reasons** (the guard's fixed phrase): git guard: *uses brace expansion, which the guard cannot
read safely* **43** (31 % of its blocks), *changes git configuration* 16 + *through the
environment* 14, *stages blindly or past the ignore list* 10, *discards uncommitted work
(checkout)* 9, *force-deletes or moves a branch* 7, *deletes untracked files* 6, *stages
everything (add .)* 6, *overwrites files from another commit* 4, *stages everything (commit -a)*
4, *overrides git configuration (-c core.hooksPath)* 4, *discards work (reset --hard)* 4,
*removes a worktree by hand* 4, 1 to 2 each for the rest. Archive guard: *no get_session result
for <session>* 95 + *no get_session "self" result in this chat* 68 = **163 of 171**: the call
order (get_session before archive) is the friction, not a dirty worktree. Sandbox-network guard:
all 102 are the `cd <dir> && <network command>` refusal.

A guard block was never followed by the identical command. After the git guard, 38 % of next
calls keep the same shape in a changed form (the "failed first attempt").

Context-limit notes (PostToolUse `additionalContext` mentioning the limit): 108, in 61 sessions
(52 other issue chats, 9 repo issue chats).

## 5. Sandbox friction

Matchers: *escape* = Bash `input.dangerouslyDisableSandbox == true`; *sandbox failure* = an error
result matching `Operation not permitted|sandbox|network denied|not in this command's
allowed_domains|Could not resolve host|ssh: connect to host|Connection refused`, or an entry with
non-empty `sandboxViolations` (418 entries, all `kind: network`); *escape after a failure* = an
escape whose previous one or two Bash calls in the same transcript had a sandbox failure.

| measure | count |
|---|---|
| escapes (dangerouslyDisableSandbox) | **16,235** = 14.1 % of all Bash calls; repo group 1,967 of 11,888 (16.5 %), other 14,268 of 103,077 (13.8 %) |
| escapes per week (sandbox in use from W45) | W45 967 (12.7 % of Bash), **W46 10,673 (28.0 %)**, **W47 4,594 (25.5 %)** |
| escapes at once (no sandbox failure just before) | 15,649 (96 %) |
| escapes right after a sandbox failure | 583 |
| identical command re-run with the sandbox flag flipped | 161 |
| sandbox failures | 962: repo group **401** (3.4 % of its Bash calls), other 561 (0.5 %) |
| Bash results with the `sandboxed` flag | 40,909 sandboxed, 60,425 not sandboxed (excluded commands and escapes), 13.6k without the flag |

**Failures by shape (top):** `cd <path> && git fetch && …` 160, `python3 <path>/promote_main.py`
**62**, `cd <path> && git status && …` 53, `cd <path> && python3 <path> && …` 49,
`cd <path> && gh issue view && …` 40, `cd <path> && git log && …` 36, `git -C <path> fetch` 15,
`gh issue comment && …` 15, `cd <path> && python3 <path>/new_worktree.py && …` 13.

**Escapes after a failure (top):** `cd <path> && gh issue view …` 73 + 37, `promote_main.py` **57**,
`cd <path> && git fetch && …` 53, `gh issue view && …` 35, `cat` 27, `new_worktree.py` 15.
`promote_main.py` also leads the consecutive identical re-runs (62).

**Escapes at once (top shapes):** a command that starts with a path (a project's own script):
`<path> && …` 1,570, `<path>` 1,341; `cd <path> && gh issue view && …` 891;
`cd <path> && python3 <arg>` 720; `cd <path> && <path> && …` 629; `cd <path> && git fetch && …` 364;
`gh issue view && …` 323; `promote_main.py` 219; `cd <path> && gh issue comment && …` 216.

### The classes of #122 and agent-rules#56 (whole window; a call counts once per class)

| class | calls | escaped at once | sandbox failures |
|---|---|---|---|
| `gh` chained with other commands | 12,372 | 4,807 | 263 |
| `cd <path> && <network command>` | 10,801 | 3,713 | 375 |
| `ssh` chained | 3,512 | 360 | 6 |
| `git fetch` chained | 1,551 | 523 | 209 |
| `gh` lone | 1,355 | 301 | 14 |
| `git -C <path> fetch / push / ls-remote / pull` | 195 / 92 / 49 / 4 = **340** | 50 / 35 / 22 / 0 | 21 / 7 / 0 / 0 |
| `git push` chained | 297 | 151 | 3 |
| lone `git push / fetch / ls-remote / clone` | 16 / 52 / 5 / 1 | 5 / 10 / 0 / 0 | 0 / 2 / 1 / 0 |
| `scp`, `rsync` chained | 466, 99 | 14, 2 | 0 |

Over 2026-11-19 to 11-22 the same matcher finds 89 `git -C` network calls (46 escaped at once,
21 sandbox failures) and 49 lone ones, against #122's 124 and 83 for "the last three days": same
order, lower, because #122's window and matcher differ (not reproduced exactly).

## 6. Permission prompts and denials

Matchers: an entry's `permissionDecision.source` is `user_temporary` (approved once),
`user_permanent` without a matched rule ("always allow"), or `user_reject`: a prompt the person
answered (AskUserQuestion excluded). `toolDenialKind` gives the denials.

| measure | count |
|---|---|
| permission prompts answered | **666**: 610 approved once (repo 181, other 429), 16 always-allow, 40 rejected (repo 25) |
| prompts by shape (top) | `cd <path> && git fetch && …` 79, `cd <path> && git push && …` 73, `git -C <path> push` 32, `cd <path> && python3 <arg>` 31, `cd <path> && git commit` 29, `cd <path> && git status && …` 18, `git push` 13, `gh pr merge` 12 + 8 |
| denials, all (`toolDenialKind`) | 1,113: by a hook 499, by a settings rule 179, rejected by the person 190 (150 `user-rejected` + 40 rejected prompts), auto mode unavailable 119, auto mode blocked 117, interrupted or cancelled 9 |
| rejected by the person | archive_session **110**, AskUserQuestion 12, rest single |
| auto-mode classifier rejections | 236 (archive_session 39, stop_session 16, Bash shapes ≤ 14 each) |
| settings-rule denials (not hooks), top shapes | `cd <path> && grep && …` 23, `cd <path> && python3 <arg>` 13, `VAR=<value> && rm && …` 10, `git commit` 5, `git -C <path> commit` 3 |

**archive_session** is the single most failing tool: 765 calls, **351 errors (46 %)**: archive
guard 171, rejected by the person 110, auto mode unavailable 35, other.

**AskUserQuestion:** 553 calls in 73 of 718 main sessions (10 %); 14 sessions asked 10 or more
times. 1,172 questions: 91 headers about landing or cleanup (push, merge, archive, clean up), 152
name an issue number, 929 other (project content). 26 AskUserQuestion results were errors (16
question-label guard blocks, 12 rejections).

## 7. Failed first attempts in general

| measure | count |
|---|---|
| Bash errors | 3,704 of 114,965 (3.2 %) |
| Bash call after a Bash error | identical retry 177, same shape changed 793, other command 2,682 |
| consecutive identical Bash commands (top) | `cd <path> && <path> && …` 65, `promote_main.py` 62, `until …` polling 33 + 10 |
| Edit | 3,571 calls, 77 errors (2.2 %): **not read first 51**, old_string not found 10, modified since read 6, other 10 |
| Write | 2,035 calls, 36 errors: not read first 11, modified since read 3, other 22 |
| Read | 12,674 calls, 81 errors |

**Bash errors by shape (top 30):** `cd <path> && gh issue view && …` 199, `cd <path> && sed && …` 188,
`cd <path> && grep && …` 186, `cd <path> && python3 <arg>` 155, `<path>` 133,
`cd <path> && cat && …` 104, `cd <path> && for && …` 97, `promote_main.py` 95, `ssh <arg> && …` 94,
`cd <path> && git status && …` 91, `overlap_check.py` 87, `sleep && …` 86,
`cd <path> && git fetch && …` 75, `cd <path> && git log && …` 68, `cat && …` 61,
`cd <path> && ls && …` 58, `gh issue view && …` 45, `cd <path> && git commit` 44,
`cd <path> && git rev-parse && …` 43, `cat` 43, `cd <path> && gh api <path> && …` 42,
`cd <path> && cat` 38, `ls && …` 37, `gh pr checks` 36, `<path> && …` 36,
`cd <path> && git diff && …` 34, `VAR=<value> && mkdir && …` 31, `sed && …` 29,
`VAR=<value> && cat && …` 26, `gh issue comment` 26. A `grep` without a match also counts here
(exit 1), so the grep and `gh pr checks` rows include designed non-zero exits.

## 8. Context, hand-overs and start cost

Matcher: context of an API call = `input_tokens + cache_read_input_tokens +
cache_creation_input_tokens` (the measure `context_limit.py` uses), once per message id; a
session's peak is its largest call; its model is the model of most of its calls.

### Peak context per main session

| kind | n | median | p90 | max | > 200k | > 300k |
|---|---|---|---|---|---|---|
| other issue chat | 434 | **312k** | 526k | 967k | 382 (88 %) | **246 (57 %)** |
| repo issue chat | 30 | 229k | 343k | 410k | 19 | 11 |
| other session | 89 | 195k | 671k | 967k | 43 | 25 |
| repo other session | 40 | 303k | 666k | 966k | 31 | 20 |

| model | n | median | p90 | max | > 300k | > 600k |
|---|---|---|---|---|---|---|
| Opus 5.5 | 472 | 286k | 449k | 967k | 211 | 24 |
| Fable 5.2 | 105 | 340k | 710k | 967k | 80 | 17 |
| Fable 5.1 | 70 | 41k | 329k | 962k | 11 | 3 |
| Haiku 5.5 | 66 | 48k | 50k | 96k | 0 | 0 |

**Compaction:** 36 automatic compactions (`compact_boundary`, trigger `auto`), in 25 main
sessions (10 other issue chats, 1 repo issue chat, 14 other sessions) and their subagents.

**Hand-overs:** the `issue-handover` skill was invoked 217 times, in 215 main sessions (208
other issue chats); `start_issue_chat.py` ran 505 times (19 errors); `handover_note.py` is only
imported; `context_limit.py` ran by hand 16 times (tests). Context-limit notes reached 61
sessions; its hard stop fired 4 times.

### Start cost (median context)

| kind, model | n | call 1 | call 2 | after the first 10 tool calls |
|---|---|---|---|---|
| other issue chat, Opus 5.5 | 322 | 52.4k | 83.9k | 106.2k (p90 121.7k) |
| repo issue chat, Opus 5.5 | 22 | 51.8k | 83.7k | 101.3k (p90 114.8k) |
| other issue chat, Fable 5.2 | 99 | 56.7k | 88.4k | 125.1k (p90 146.0k) |
| other session, Opus 5.5 | 84 | 77.5k | 78.9k | 100.4k |
| repo other session, Opus 5.5 | 36 | 78.7k | 81.6k | 100.2k |

**Against #82** (11 chats of 2026-11-15/17): #82 gave call 1 = 55k and call 2 = 86-87k for Opus,
57k / 87-89k for Fable 5.2. Over 421 issue chats the medians are 52-57k and 84-88k: the same
picture, and the **+31-32k at call 2** (the desktop app's tool list, skills and guidance arriving
with the brief) holds for every issue chat. A non-issue session starts at 77-79k in one step. The
first 10 tool calls add another 18-37k; Fable model chats read the most. #82's "first code" point
(121-154k for Opus) is not derivable from these aggregates.

## 9. Limits of these numbers

- Subagent transcripts are counted in tool, guard and sandbox numbers; they do not have their
  own session kind there.
- Hook decisions of the "ask" guards (delete guard, personal-data check) are not recorded with
  their reason, so their prompts cannot be attributed.
- Skills invoked before W46 are the overlay repository's predecessors with the same names.
- Command shapes split on `&&`, `||`, `;`, `|` without respecting quotes; shapes use the first
  non-comment line.
- No token cost of a failed attempt is measured here; #122 estimates one round trip of the
  chat's whole context per extra attempt.

## 10. What the numbers suggest

1. **Sandbox escapes are the largest friction source:** 25-28 % of all Bash calls in W46-W47 ran
   with `dangerouslyDisableSandbox`, 96 % of them pre-emptively. The classes behind them are `gh`
   in a chain (4,807 escapes) and `cd <path> && <network command>` (3,713). A rule plus the
   sandbox-network guard for lone `gh …` calls, and #122 for `git -C`, address the biggest share.
2. **`promote_main.py` fails inside the sandbox by design** (62 failures, 57 escapes right after,
   62 identical re-runs, 219 pre-emptive escapes): an `excludedCommands` entry for the installed
   script, or a line in its skill that it always runs outside, removes a failed attempt per landing.
3. **archive_session fails in 46 % of calls,** 163 of 171 guard blocks because `get_session` was
   not called first. Have `archive-finished-chats` call `get_session` itself in the same step, or
   let the guard read what it needs; 110 person rejections suggest an archive prompt the person does
   not want: check whether the ask rule is still needed with the guard in place.
4. **The git guard's brace-expansion refusal is 31 % of its blocks:** a candidate false positive
   to narrow (only when a brace expansion can reach a protected git form).
5. **`overlap_check.py` exit 1 ("overlaps found") is reported as an error** 95 times: exit 0 with
   the verdict on the last line would stop agents treating a normal answer as a failure.
6. **The 300k context limit triggers in most issue chats:** 57 % of other-project issue chats
   pass 300k and the median peak is 312k; start-up costs 84-88k at call 2 and 101-125k after ten
   tool calls. Trimming the +31k the app adds at call 2 (#82 option 3) returns about 10 % of the
   limit to every one of the 112-171 issue chats a week (W44, W46, W47).
7. **Prompts the person answers** are mostly pushes and fetches in a chain (≈ 200 of 666) and
   `git commit` after `cd` (29): lone calls that match the allow and exclude lists would avoid
   many of them.
8. **Never used:** the codex plugin's two skills (0 invocations) and five web-deploy and
   security reference files; `efficient-design`, `repo-docs` and `check-web-deploy` ran 1-2 times
   in five weeks. Keep them, but they do not justify their description budget in every session's
   skill list if that becomes tight.
