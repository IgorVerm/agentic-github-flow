# Audit #123, part 2: refusals, repeats and what a refused call costs

Measured 2026-11-22 with `audit/123/refusal_stats.py`, which imports the helpers of
`transcript_stats.py`. Window, input and privacy rule are the same as in `transcripts.md`:
2026-10-12 to 2026-11-22, 2,475 transcript files, aggregates only. Re-run:
`python3 audit/123/refusal_stats.py --until 2026-11-22 [--json]` (about 5 minutes).

**Units and definitions.** One *session* is one transcript: a main session or one subagent.
- A *network call* is a Bash call with a `gh` command, or with `git push|fetch|pull|ls-remote`, as one of its simple commands. Command substitutions count too.
- The commands are split quote-aware: `'…'`, `"…"`, `$(…)`, here-document bodies and comments are respected.
- *Form* of a network call:
  - `-C`: a git network command with `-C`, `--git-dir` or `--work-tree`;
  - `lone`: the whole call is that one simple command, with no `&&`, `;`, `|`, `$(…)` or here-document;
  - `chained`: everything else.
- *Escape*: `dangerouslyDisableSandbox: true`.
- *Blocked*: the tool_result's `permissionDecision.source == "hook"` with `decision: reject`, named by the guard's message.
- *Sandbox failure*: as in `transcripts.md` §5.
- *Context of a call*: input + cache-read + cache-creation tokens of the API response that issued it.

**The sandbox-network guard's first block** in the transcripts is 2026-11-21 15:24 UTC. All 102 of its blocks fall in the last 1.5 days of the window. The sandbox itself has been in use since W45: escapes start there.

## 1. Repetition after a refusal, per session

### Guards

| guard | sessions with a block | 1 block | 2 | 3+ | never repeated after the first block |
|---|---|---|---|---|---|
| sandbox-network guard | 88 (51 main, 37 subagents) | 75 | 12 | 1 | **75 (85 %)** |
| git guard | 105 (64 main, 41 subagents) | 79 | 17 | 9 | **79 (75 %)** |
| archive guard | 114 (all main) | 94 | 12 | 8 | **94 (82 %)** |

**What came after the first block, in the same session:**
- **Sandbox-network guard.** 1,208 later network calls in those 88 sessions:
  - (b) **lone network call, sandbox on: 897 (74 %)**;
  - (c) escaped the sandbox: 178 (15 %);
  - (a) blocked again: 14 (1.2 %);
  - chained or `-C` inside the sandbox and not blocked: 119 (10 %), of which 60 failed in the sandbox. The guard passes a call it cannot rewrite faithfully, for example `cd` into another folder.
- **Git guard.** 36 later blocks: only **4 had the same reason** as the first block, 32 had another reason. 4,861 later Bash calls passed the guard.
- **Archive guard.** 337 later archive_session calls:
  - 193 archived;
  - **57 blocked again**;
  - 43 rejected by the person;
  - 29 refused with "auto mode unavailable" (see §5);
  - 15 other failures.
  - All 114 sessions called `get_session` after their first block.

### Plain sandbox failures (no guard involved)

311 sessions had a network call fail inside the sandbox: 254 once, 38 twice, 19 three times or more. After the first such failure, the same sessions made 3,528 later network calls:

| next network calls | count | share |
|---|---|---|
| **sandbox off (escape)** | 2,380 | **67 %** |
| lone form, sandbox on | 819 | 23 % |
| chained or `-C` again in the sandbox | 323 (233 ran, 90 failed again) | 9 % |
| chained, blocked by a guard | 6 | 0.2 % |

**The lesson a session takes from a plain failure is mostly "switch the sandbox off"; the lesson from a guard refusal that names the lone form is mostly "use the lone form" (74 %).**

## 2. Is the mistake learned across sessions?

The first network call of each session. Only W45-W47 count, because before W45 there was no sandbox and "sandbox on" means nothing.

| first network call | W45 to the guard (670) | after the guard's first block (114) |
|---|---|---|
| (a) lone, sandbox on | 45 (7 %) | **29 (25 %)** |
| (b) chained or piped, sandbox on | 450 (67 %) | 72 (63 %) |
| (c) `git -C`, sandbox on | 4 (0.6 %) | 0 |
| (d) sandbox off pre-emptively | 171 (26 %) | 13 (11 %) |

After the guard, by unit:
- main sessions (55): lone 11, chained 43, sandbox off 1;
- subagents (59): lone 18, chained 29, sandbox off 12.

Over the whole window (1,501 sessions): chained 79 %, sandbox off 12 %, lone 7 %, `-C` 1 %.

**Not learned across sessions.** Every new chat and every subagent starts with the chained form, in about two thirds of cases, both before and after the guard. The guard's lesson stays inside the session that was refused. The 1.5 days after the guard are a small sample.

## 3. Shapes of the unsandboxed calls

### `gh` chained or piped, with the sandbox off: 4,796 calls

Features overlap, so they do not sum to the total.

| feature | calls |
|---|---|
| `cd <path> &&` in front | 3,295 |
| `&&` / `;` with other (non-gh) commands | 3,266 |
| redirection (`2>&1`, `> /dev/null`, `> file`) | 2,694 |
| `$(…)` substitution | 1,658 |
| `&&` with another `gh` | 1,444 |
| pipe to `head`/`tail` | 1,421 |
| here-document | 1,067 |
| loop (`for`/`while`) | 877 |
| pipe to `grep` | 311 |
| pipe to `wc`/`sort`/`cut`/`uniq` | 120 |
| pipe to `sed`/`awk` | 76 |
| pipe to `python` | 9 |
| pipe to `jq` | 0 (agents already use `--jq`) |
| env-var prefix on gh | 3 |

Each call is assigned to the first class it fits:

| rewrite class | calls | share |
|---|---|---|
| faithful mechanical rewrite: drop `cd` (`gh -R`), drop `2>&1`; one gh and nothing else | 406 | 8 % |
| mechanical, but drops a display filter (`| head`, `| grep`, `| wc` …) | 544 | 11 % |
| needs restructuring: two or more gh, other commands, a loop, a substitution, or a here-document (→ `--body-file`) | 3,846 | **80 %** |

### `cd <path> && <network command>`, with the sandbox off: 3,795 calls

| network command | calls | `cd` into the session's own folder / another folder | more commands after it |
|---|---|---|---|
| gh | 3,136 | 2,131 / 1,005 | 2,683 |
| git fetch | 462 | git total: 230 / 347 | git total: 571 |
| git push | 76 | | |
| git ls-remote | 39 | | |
| cargo | 42 | 31 / 11 | 42 |
| ssh, scp, rsync | 32, 7, 1 | 24 / 16 | 38 |

Only **461 (12 %)** are `cd X && <one network command>` with nothing after it. These are mechanically rewritable: drop the `cd` when X is the session's folder, use `gh -R` for gh, or the lone git call from the own worktree (#122). The other 88 % chain more work after the network command, so they need two calls.

**Estimate.** About 10-20 % of the unsandboxed gh and `cd` calls have a faithful mechanical lone form. About 80 % need the model to split the call. A rewriting hook could fix the minority; the majority needs the model to change how it writes the call.

## 4. Where do chats copy the chained form from?

1,374 sessions started with a chained or `-C` network call (530 main, 844 subagents).

Earlier in the same session, the matching form appeared in a tool result, a skill body, an attachment or the first user message in only **43 sessions (3 %)**. Matched forms: `git -C <path> <network>`, `cd <path> && gh`, `cd <path> && git <network>`, `gh … |`, `gh … && gh`.

| earlier source (sessions) | count |
|---|---|
| other command output | 24 |
| **start brief** (first user message: the coordinator's brief or the subagent prompt) | **16** |
| refusal text of this repository's guards: `pre_tool_git_guard.py` 2, `pre_tool_sandbox_network.py` 1 | 3 |
| file read (1 a repository `AGENTS.md`) | 4 |
| attachment, WebFetch | 2 |

None of this repository's rules (`rules/core.md`), skill bodies or script sources contain these forms. The one hit in source is the sandbox-network guard's own docstring, which explains the refused form. The user's overlay `AGENTS.md` and global `CLAUDE.md` contain none either.

**The chained form is the model's own default, not something copied.** The exception is the 16 briefs that hand it on to a subagent. The system prompt is not in the transcripts; the rule files that feed it were checked directly.

## 5. Hook-changed input and auto-mode refusals

The exact wordings, from the client:
- "…gave no verdict for <tool>: **a hook changed this call's input after auto mode reviewed it**, so the review does not cover what would run…";
- "…**another call in this response was changed after auto mode reviewed it**, or could not be confirmed unchanged, so this call's review no longer…".

| auto-mode denials (236) | count | calls |
|---|---|---|
| denied by the classifier (`automode-blocked`) | 117 | Bash with the sandbox on 41, Bash with the sandbox off 31, set_monitor 10, request_directory 8, other |
| no verdict: **a hook changed this call's input** | 52 | archive_session 35, stop_session 12, set_session_effort 3, unarchive_session 1, set_session_model 1 |
| no verdict: another call in the same response was changed | 13 | Bash 12 (6 with the sandbox off), SendMessage 1 |
| no verdict, other cause | 54 | Bash with the sandbox on 44, Edit 7, other |

**What came next.** 71 refusals cite a changed input. The next call of the same tool was:
- archive_session: changed and failed again 21, changed and succeeded 14;
- stop_session: 9 failed, 3 succeeded;
- Bash: identical retry succeeded 10, changed 5;
- other tools: 9.

**No hook of this repository returns `updatedInput`** (searched in `plugins/` and `tools/`). The hook that rewrites the session-management calls is installed elsewhere, so its cost sits outside this repository. The cost is still a lesson: a rewriting hook makes auto mode refuse the call it rewrote. That is a failed round trip of its own, and in 30 of 47 session-management cases it failed again.

Right after an escape (`dangerouslyDisableSandbox`), auto mode refused the call 39 times: 31 blocked, 6 for a changed call in the same response, 2 with no verdict.

## 6. Token cost per failed round trip

Each failed or refused call is costed at the context of the turn that issued it. That is the context the next turn re-reads, mostly as cache reads, to react to the failure.
- **Pricing assumption:** one extra round trip per failure, the whole context re-read once. At current list prices a cache read costs about a tenth of fresh input; only tokens are given here.
- Parallel calls in one response share a round trip, so this is an upper bound for them.

| class | calls | median context | total tokens re-read | W46 | W47 |
|---|---|---|---|---|---|
| sandbox failure (Bash) | 862 | 120k | **140.7M** | 78.9M | 51.1M |
| archive_session failure, not the guard | 179 | 291k | 56.5M | 29.2M | 24.5M |
| guard block: archive guard | 171 | 220k | 43.3M | 19.6M | 12.6M |
| guard block: git guard | 141 | 172k | 27.4M | 13.4M | 14.0M |
| guard block: sandbox-network guard | 102 | 90k | 13.6M | - | 13.6M |
| guard block: question label | 16 | 167k | 2.9M | - | 2.9M |
| guard block: context limit | 4 | 867k | 2.7M | - | 2.7M |
| guard block: other hooks (app) | 68 | 58k | 4.8M | 0.4M | - |
| denial: settings rule | 217 | 165k | 45.8M | 14.8M | 3.6M |
| denial: auto mode blocked / unavailable | 113 / 84 | 233k / 205k | 27.5M / 19.9M | 16.6M | 10.0M |
| denial: person rejected, interrupted, cancelled | 48 | | 12.9M | 6.1M | 1.5M |
| **subtotal: refusals and sandbox failures** | **2,005** | | **≈ 398M** | **≈ 179M** | **≈ 136M** |
| other Bash errors (includes designed non-zero exits such as grep without a match, overlap_check exit 1) | 2,603 | 159k | 524.7M | 171.2M | 69.8M |
| all failed or refused calls | 4,608 | 158k | 922.5M | 350.2M | 206.2M |

**Per call:** a guard refusal re-reads less than a plain sandbox failure.
- The sandbox-network guard is refused at a 90k median, because it fires early.
- A plain sandbox failure re-reads 120k.
- The archive and git guards re-read 172k-220k: they fire later in a chat.

The sandbox-network guard also removes the round trips that would follow a failure: after a refusal, 74 % of the next calls are lone forms; after a plain failure, 67 % are escapes.

## 7. The git guard's brace-expansion blocks

45 blocks with the reason "uses brace expansion". Each is classified by the context of the first brace the guard's own scan reacts to, using a reproduction of `brace_expansion()` and a quote- and here-document-aware scanner. No content is quoted.

| shape | segment the brace sits in | blocks |
|---|---|---|
| inside a here-document body | a program (python/jq/awk/node) | 15 |
| inside a here-document body | `cat`/`echo`/`printf` (writing a file or a body) | 12 |
| inside a here-document body | other command | 2 |
| inside a here-document body | git (`commit -F -`) | 1 |
| unquoted `{a,b}` / `{1..3}` expansion | another command in the call (`mkdir`, `ls`, `cp` …) | 10 |
| unquoted `{a,b}` / `{1..3}` expansion | **git** | **4** |
| unquoted expansion | a program | 1 |
| inside a single- or double-quoted string | - | 0 (the guard already skips quotes) |
| `${var}` | - | 0 as the trigger; present in 2 calls |
| `@{…}` (`stash@{n}`, `@{u}`) | - | 0 |

**Brace inside the git segment itself: 5 of 45 (11 %).** The other 40 are refused because:
- the guard scans here-document bodies for braces before it strips them (`judge()` calls `brace_expansion()` before `strip_heredocs()`);
- it accepts any `{a,b}` in the whole call once `git` appears anywhere in it.

This audit's own work met one: a classifier unit test fed through a Python here-document was refused live.

## Limits

- Sessions are transcripts. A main session and its subagents are separate units.
- "Later calls of the class" after a sandbox-network block counts all lone network calls of the session, not only those replacing the refused call.
- The `cd` target is compared with the entry's `cwd` after expanding `~`. A relative target counts as "another folder".
- The rewrite classes in §3 are mechanical judgements from the call's shape. Whether a dropped display filter is acceptable is the model's or the person's call.
- §6 assumes one round trip per failure. It does not count the output tokens of the failed call or of the reply to it.
