# Clarity and economy of the instruction text

Part of audit #123, phase 1. Base: `e27f84f` (worktree `agent/123-audit`), read 2026-11-22.
Read-only review of `rules/core.md`, `rules/codex.md` and the 14 skills with their reference files,
against `plugins/core/skills/repo-docs/skill-standard.md`, `AGENTS.md` and the rulings in
`DESIGN_DECISIONS.md`.

**How the numbers were made.** Bytes are `wc -c` of the files at the base. "Bytes after" is an
estimate (labelled so): the sum of the passages named in the findings that could be removed, moved
to a reference file read only on its branch, moved into a script's output or header, or moved to
`DESIGN_DECISIONS.md` or a design document that no session loads. Section sizes were cut at
headings and at bold lead-ins with a small Python script. Script output was measured by running
each script's `--help`, a deliberate bad argument, and, where it needs no GitHub, a real read-only
call (`landing.py --explain`, `chat_archivable.py --no-fetch`, `overlap_check.py --no-github`,
`remove_merged_worktree.py --sweep --dry-run --no-fetch`). **Not run:** every call that reads
GitHub (`next_issue.py`, `merge_pr.py`, `push_branch.py`, `review_verdict.py`,
`start_issue_chat.py`): `gh` cannot read its configuration inside this session's sandbox, so
their success and refusal output was read from the code, not measured.

**Rulings respected.** No proposal below removes the core rule *Work grows with what changed*
(ruling 2026-11-11, "Skill + regel"), adds a core bullet for the question label (ruling
2026-11-17, "No bullet in rules/core.md"), or brings Codex text into a file a Claude-only install
loads (ruling 2026-11-22, #98). Every proposal for `rules/core.md` needs the maintainer's word.
Where a proposal touches a file a ruling's **Binds** line names, that line has to move with it.

## Summary table

| Skill (files) | Bytes now | Bytes after (estimate) | Main defect |
|---|---|---|---|
| issue-handover (`SKILL.md` + `method.md`) | 19,879 + 38,722 | about 9,000 SKILL + reference files read by moment (below) | one method file mixes start, hand-over, rare branches, adoption and rationale; read whole at every chat start |
| ship-change (`SKILL.md` + `local-main.md`) | 13,822 + 6,951 | about 9,800 + 5,500 | repository setup, sandbox rationale and rare conflict recipes inside the per-landing path; restated push permission |
| cleanup-merged | 8,170 | about 4,600 | *What the script checks* (3.5 KB) restates the script's 11 KB header |
| requirements | 7,601 | about 6,000 | restates issue-chat title, sidebar, worktree and archive steps owned by issue-handover |
| review-change | 6,162 | about 5,200 | stale "standing grant merges" sentence; manual fetch-and-compare a script could do |
| open-issue | 3,335 | about 3,100 | none material |
| spec-first | 1,510 | about 1,350 | one motivational sentence |
| repo-docs (+ `skill-standard.md`, `skeleton.md`) | 3,799 + 5,187 + 2,226 | unchanged | none material |
| efficient-design | 4,148 | about 3,900 | none material |
| archive-finished-chats | 6,843 | about 4,500 | one 990-byte sentence defines the worktree check; step 3 stacks five conditions |
| review-security (`SKILL.md`, `checklist.md`, `sources.md`) | 6,192 + 21,156 + 37,549 | about 4,500 + 16,100 loaded (stack notes per stack) + sources maintainer-only | step 3 is 2.8 KB of branches; base-branch comparison done by hand |
| check-web-deploy (10 files) | 5,792 SKILL, 64,266 all | about 5,500 SKILL | in good shape; references one level deep |
| codex-worker (+ `sources.md`) | 9,505 + 988 | about 6,000 | restates the worker's and the import's refusal lists; limits section is rationale |
| codex-issue-chats | 7,927 | about 4,500 + 3,400 reference | rare integrator route (3.4 KB) in the always-read body |
| `rules/core.md` | 7,969 | about 6,600 to 6,900 (needs the maintainer's word) | command lists the guards enforce; a few restated pointers |
| `rules/codex.md` | 1,151 | unchanged | none |

## Standard compliance, all skills

| Check | Result |
|---|---|
| `name` equal to the folder, frontmatter one line per value | all 14 pass (`tests/skills_format.py`) |
| Description 40-500 characters | all pass; `issue-handover` is at 499, `archive-finished-chats` 477, `check-web-deploy` 472, `ship-change` 465 |
| Description says what and when | all have a *Use when*. Four describe the procedure step by step instead of what the skill is for (issue-handover, ship-change, archive-finished-chats, codex-issue-chats): about 150-200 characters each could go without losing a trigger |
| Voice | descriptions open with an imperative verb ("Pick and claim", "Remove", "Land"), not the third person Anthropic's best practices name ("Processes Excel files"). Not wrong under the agentskills.io specification; consistent across the set |
| Body under 5,000 tokens (characters / 4) | all pass; `issue-handover` body is about 4,760 tokens, 5% under the limit, so any addition there fails the test |
| `SKILL.md` under 500 lines | all pass (largest 240) |
| References one level deep | pass by the repository's own definition. One cross-skill link: `archive-finished-chats/SKILL.md:10` links `../issue-handover/method.md`, outside its own folder; it works because the plugin installs both, but the skill is not self-contained |
| ALL-CAPS or alarm wording | none found; emphasis is bold lead-ins, calm |
| Lines over 110 characters (sign of a sentence inserted without rewrapping, often where flow breaks) | `issue-handover/SKILL.md:88` (156), `:158` (154), `:127`; `local-main.md:37` (158); `archive-finished-chats/SKILL.md:55`; `review-security/SKILL.md:34`, `:56`; `ship-change/SKILL.md:126`, `:150`; `cleanup-merged/SKILL.md:15` |

## Facts restated across files (economy, cross-cutting)

Measured with `grep -i` over `rules/core.md` and every skill file:

| Fact | Occurrences | Files | Owner it should point to |
|---|---|---|---|
| push and merge permission ("standing grant", "automatic merg", "user's yes") | 40 | 5-6 | `rules/core.md` §Git for the rule, `ship-change` steps 6-8 for the procedure |
| "signed comment" | 19 | 9 | `rules/core.md` §Work and documents |
| the worktree check and what `ok` means | 14 | 4 | `chat_archivable.py` header |
| `get_session "self"` before an archive | 11 | 4 | one archive section in issue-handover |
| at most five chains | 6 | 2 | `method.md` §1 |
| "`<plugin>` is the folder two levels above this skill's folder" | 6 | 6 | needed per skill (a skill loads alone); keep |

## Conflicts found (instructions that disagree)

1. **Who lets `merge_pr.py` merge.** `review-change/SKILL.md:10-11` "Under a standing grant
   `merge_pr.py` merges on it" and `issue-handover/method.md:363-364` "by `merge_pr.py` where a
   standing grant allows it" describe the rule of 2026-11-09, which the ruling of 2026-11-11
   narrowed: only the repository's `automatic merge` row switches merging on
   (`ship-change/SKILL.md:200-207` has it right). Fix the two sentences; no ruling changes.
2. **Is the review subagent always run after the pull request opens?** The ruling of
   2026-11-11 (*What*) and `issue-handover/SKILL.md:193-195`, `method.md:206` say yes;
   `ship-change/SKILL.md:191-192` says "on the small-change route without automatic merging,
   your own check of step 3 stands". An agent following ship-change alone skips what the ruling
   and issue-handover require. Resolve toward the ruling, or ask the maintainer.
3. **Foreground or background for long runs.** `method.md:151-152` and `:327-333`: a chat
   waits for long runs in the foreground, never ending its turn for a notification.
   `codex-worker/SKILL.md:43-44` runs a Codex turn "in the background, since a turn may run
   long"; `review-security/SKILL.md:25-26` runs `--history` "in the background". Say in each
   whether the chat then waits in the same turn (blocking wait) or may end the turn.
4. **Stop or keep runs before the hand-over.** `issue-handover/SKILL.md:68` "Stop or finish your
   runs and agents" versus `:55-59` "One that outlasts the turn (a remote gate, a capture) is a
   run the work still needs: never stop it". Step 1 should point to *End your own live work*.
5. **What a claim is.** `ship-change/SKILL.md:71-74`: assigning the issue "is the claim the
   overlap check of step 5 reads", said at landing time. `method.md:396-400` and
   `issue-handover/SKILL.md:139-142`: the claim is the assignee plus a signed comment naming
   chat, branch and worktree, made at the start. Move the ship-change sentence to the start of
   work (or drop it and point to `open-issue`/`issue-handover`), and use one definition.
6. **"The default branch" redefined.** `cleanup-merged/SKILL.md:11-13` lets "the default branch"
   mean the landing branch; `ship-change` calls the same thing `<landing>`. Use `<landing>`
   throughout.
7. **Closing keywords.** `rules/core.md:79` "never a closing keyword" (commit subject) and
   `:101-102` "A pull request body may close its issue with a closing keyword" are both right
   but read as a contradiction at a glance. One sentence: close an issue only from a pull
   request body (`Closes #n`), never from a commit.

## Script output and help as context

| Script | Success output | Refusal or bad call | Finding |
|---|---|---|---|
| `landing.py --explain` | 102 bytes, 4 lines (measured) | n/a | good; `--help` prints its 4.6 KB header |
| `chat_archivable.py` | 1 line (`keep: 1 changed or untracked path(s), e.g. …`, measured) | `--help` is treated as an error (usage line, exit 2) | good output; help gives no exit codes |
| `overlap_check.py` | 1 line per hit (measured `none: …`) | `--help` lists options without meaning; exit codes only in `ship-change/SKILL.md:131-139` | move exit codes into `--help`, shorten the skill |
| `remove_merged_worktree.py --sweep --dry-run --no-fetch` | 808 bytes for 3 worktrees (measured) | `KEPT <path>: <reasons>` | good, actionable |
| `start_issue_chat.py` | one line `ok local_<id>` / `fail: …` / `unsure: …` (code) | same | good; the skill still restates its refusal list (`issue-handover/SKILL.md:129-134`) |
| `merge_pr.py` | 2-3 lines (code) | **any unknown argument prints the whole 5.2 KB module docstring to stderr** (`merge_pr.py:347-349`, measured 5,238 bytes) | print the usage line and "see --help" |
| `push_branch.py` | 2-3 lines (code) | **unknown argument prints the 4.7 KB docstring** (`push_branch.py:204-206`) | same |
| `promote_main.py` | about 8 lines (code) | **wrong argument count prints the 2.7 KB docstring** (`promote_main.py:114-116`, measured 2,725 bytes) | same |
| `new_worktree.py` | 1-3 lines (code) | **wrong argument count prints the 3.0 KB docstring** (`new_worktree.py:284-286`, `:303-305`) | same |
| `merge_landing.py` | short (code) | the `.claude/` conflict refusal says "as the ship-change skill says in step 2" (`merge_landing.py:514-516`) instead of printing the integrate commands | print the exact commands; then `ship-change/SKILL.md:95-100` can go |
| `review_verdict.py` | short (code) | usage 357 bytes | good |
| `codex_worker.py` | `json.dumps(report, indent=2)` with job, events path, tools, setup (withheld list capped at 50), and `last_message` unbounded; `stderr_tail` 2,000 characters on failure (`codex_worker.py:1051-1081`) | refusal one line | the skill tells the chat to read only `status` and `last_message`, but the whole JSON enters the context; print a compact line by default and the full report with `--json` |
| `audit_dependencies.py`, `scan_secrets.py` | not run (network, long) | `--help` 6.2 KB and 3.6 KB | help is the header; acceptable since rarely called with `--help` |

The pattern to fix once: four scripts answer a mistyped flag with their whole header. An agent
that mistypes a flag on a 5 KB-header script pays about 1,300 tokens and then has to find the
error in it.

## Procedure that could become code

| Where | Manual procedure now | Proposal |
|---|---|---|
| `ship-change/SKILL.md:78-80` | `git merge-base --is-ancestor origin/<landing> HEAD`, then `merge_landing.py` | drop the ancestor test: `merge_landing.py` already prints "nothing to merge: … is in HEAD already" (`merge_landing.py:489`) |
| `issue-handover/SKILL.md:74-76`, `:139-142`, `:191-192`, `:204`; `local-main.md:37`; `codex-issue-chats/SKILL.md:65` | agents type comment openings that scripts parse (`claimed for chat "<title>" (local_<id>), branch …, worktree …`, `ready to push:`, `pull request opened: #`, `landed on local <branch> at`, `merged: #… at …`, `integrator accepted <S>:`): `next_issue.py`, `overlap_check.py` and `start_issue_chat.py --handover` read them | one `state_comment.py <kind> <issue> …` that writes the signed opening exactly, as `review_verdict.py` does for verdicts; or let `start_issue_chat.py` post the claim after `ok` |
| `issue-handover/SKILL.md:99-108` | after `next_issue.py`: skip issues whose `after #n` is open (`gh issue view` per dependency), then run the overlap check and judge stale branches and second chats | `next_issue.py --check` that drops open `after #n` and runs `overlap_check.py --paths … --issue …` for the first candidate, printing the pick and its hit lines |
| `issue-handover/SKILL.md:163-174` | after exit 2 or an undelivered brief: `list_sessions`, `archive_session`, or `claude agents --json --cwd` must print `[]` | `start_issue_chat.py` on exit 2 already knows the session id; it can print `half-made: <id>` or `half-made: none` from `claude agents --json --cwd` |
| `review-change/SKILL.md:25-29` | fetch base, fetch `refs/pull/<n>/head`, compare `FETCH_HEAD` with the printed SHA, retry | `review_verdict.py head <n> --fetch` does both fetches and the comparison |
| `review-security/SKILL.md:51-57` | list base lockfiles, `git archive`, `tar -xf`, run the audit there with `--no-npm`, compare advisory id and package by hand | `audit_dependencies.py --base <ref>` exports and compares itself and prints only what the change adds |
| `local-main.md:85-96` | push of the landing branch: fetch, ancestor test, `landing.py` again, `git log`, push, `ls-remote` verify | `push_landing.py --dry-run` (checks and the log) and `push_landing.py` on the user's yes, like `promote_main.py` |
| `archive-finished-chats/SKILL.md:40-69` | list sessions, parse titles, find the newest chat per issue, walk descendants by `startedBy`/`parentSessionId`, pick `worktreePath` or `originCwd` | a script that takes the JSON of `list_sessions` and `get_session` on stdin and prints `archive <id> <reason>` / `keep <id> <reason>`; the session tools stay the agent's |

## Per skill

### issue-handover

| | |
|---|---|
| Files | `SKILL.md` 19,879 (body about 4,760 tokens), `method.md` 38,722 |
| Read when | `SKILL.md` at every hand-over; the start brief sends every new chat to "this skill and method.md §4 step 1" (`SKILL.md:153-155`), so a start reads both: 58.6 KB, plus `archive-finished-chats` 6.8 KB = 65.4 KB |
| Description | 499 characters, a procedure list; could be about 300 |
| After (estimate) | `SKILL.md` about 9,000; method split by moment (§7 below) |

Economy (bytes removable or movable, estimates):

- `method.md:1-35` overview, "This file owns", modes (2.8 KB): restates `SKILL.md` and
  `ship-change`; keep two sentences, move the rest to a design document.
- `method.md:122-163` §3 (3.5 KB): principles with citations of Anthropic's best-practices page
  (*Keep cost and context down*, *Give Claude a way to verify*); rationale, read by nobody at
  run time. Items 1 (context limit), 9 and 10 (work in flight, review comments) are operative and
  stay in a short reference.
- `method.md:214-238` *Why that order* and the live-work and successor paragraphs (about 2 KB):
  rationale for `DESIGN_DECISIONS.md` or a design document.
- `method.md:280-308` *The next chat starts in the background* (2.2 KB): measurements of CLI
  2.1.292; the operative part is "`start_issue_chat.py` does it". Move to a design document.
- `method.md:448-468` §7 machine setup (about 1.7 KB) restates `docs/install.md` §Issue chats
  without a click (two owners of the allow-rule form).
- `method.md:76-87` *Spreading over areas* (1.1 KB): `next_issue.py` "owns the order"
  (`:86`); keep one sentence.
- `SKILL.md:232-240` (0.8 KB) and `method.md:240-278` (3.0 KB) both describe the hand-over
  before the branch is ready, with different detail: one owner.
- `SKILL.md:25-34` (0.9 KB) and `method.md:20-27`, `:43-49`, `:318-320` restate the push and
  merge rule of `rules/core.md` §Git and `ship-change` steps 6-8.
- `SKILL.md:129-138` (about 0.8 KB) restates `start_issue_chat.py`'s refusal list; the tool
  prints the reason.
- `method.md:334-346` and `:130-136` restate what the `question_label.py` and `context_limit.py`
  hooks do (about 1 KB); "its header owns the details" is already there, so the description can
  shrink to one sentence each.
- "At most five chains" appears at `method.md:7`, `:72`, `:151`, `:485`, `SKILL.md:222`.

Clarity defects (worst first):

1. `SKILL.md:36-47` *Never archive this chat*: one sentence of about 1 KB with six stacked
   conditions, nested parentheses and mode exceptions. Rewrite as a bullet list of keep
   conditions, each one line, with the script that decides it.
2. `SKILL.md:72-92` step 2 does three things by mode (ready to push, pushed under a grant,
   landed on local main), each condition stated after the default action ("**Under a standing
   grant** … push now instead", "**In local-main mode** land the work instead"), then appends
   the comment-edit rule and the whole question-label policy (`:88-92`, a 156-character inserted
   line). Use a three-row table: mode, action, comment opening; move the question rule to the
   start reference.
3. `SKILL.md:163-180` *The fallback*: exit 1, exit 2, undelivered, in place, outside a
   hand-over, no session tools, each with its own action, in one paragraph. A decision table
   (situation, check, action) is shorter and safer.
4. `SKILL.md:68` conflicts with `:55-59` (conflict 4 above).
5. `SKILL.md:146-161` the start brief is described in prose with (a)(b)(c) and an inserted
   154-character line; the brief is deterministic text. Give a literal template with
   placeholders, or have `start_issue_chat.py` print it.
6. `method.md:64` the `context limit` row is a 400-character table cell with an embedded
   example; keep the value form there and point to the hook header for the rest.
7. `method.md:363-364` stale merge permission (conflict 1).

Procedure to code: the state comments, the pick with dependencies and overlap, the half-made
check (table above).

### ship-change (`SKILL.md`, `local-main.md`)

| | |
|---|---|
| Files | `SKILL.md` 13,822 (8 steps), `local-main.md` 6,951 |
| Read when | every landing; `local-main.md` only in local-main mode (good) |
| Description | 465 characters, procedure list |
| After (estimate) | about 9,800 + 5,500 |

Economy:

- `SKILL.md:14-20` how a worktree is made (0.65 KB): the skill is loaded when work is done;
  the integration worktree needs one line. Point to `new_worktree.py`.
- `SKILL.md:38-53` the `## Landing settings` template and value rules (1.1 KB): repository
  setup, needed once per repository; `landing.py`'s header owns the rule. Move to a reference
  or to `landing.py --help`; keep one line.
- `SKILL.md:81-91` sandbox rationale ("The cost: a running chat keeps the `.claude/` it started
  with", #108 leftovers; about 0.5 KB) is the text of the ruling of 2026-11-11 (option D).
- `SKILL.md:93-100` the `.claude/` conflict recipe (0.7 KB): rare branch; have
  `merge_landing.py` print the commands in its refusal.
- `SKILL.md:8-12` restates the push rule of `rules/core.md` and step 6.
- `SKILL.md:150-152` and `:164-168` restate what `push_branch.py` checks and prints.
- `SKILL.md:204-207` lists the paths that merge only on the user's word; `merge_pr.py` prints
  the refusal with the path.
- `local-main.md:85-99` the push of the landing branch (1.2 KB) as a script (table above).

Clarity defects:

1. `SKILL.md:189-192` review exception (conflict 2).
2. `SKILL.md:71-74` claim at landing time (conflict 5): a start-of-work instruction in the
   landing skill, after the action it should precede.
3. `SKILL.md:78-91` step 2: an ancestor test the tool makes needless, then a 12-line paragraph
   mixing the procedure, its rationale and the local-main variant ("In local-main mode do the
   same with the local `<landing>`", `:86`). Lead with the one command, then a two-row list
   for the modes.
4. `local-main.md:48-60` §2 step 3: one paragraph with two routes (both in S / not), plain
   merges versus `merge_landing.py` depending on who reviews, a staging rule and the gate
   order. A numbered sub-list per route.
5. `SKILL.md:146-152` *A standing grant* runs 7 lines with a 127-character line; the reader has
   to find "Then go on with step 7 without asking" in the middle. Lead with the action.

### cleanup-merged

| | |
|---|---|
| File | `SKILL.md` 8,170 |
| After (estimate) | about 4,600 |

- `SKILL.md:61-108` *What the script checks* (3,555 bytes) restates the header of
  `remove_merged_worktree.py` (11 KB docstring, same checks: merged, clean, ignored files, no
  stray commits, idle; scratch and merged branch passes). The script prints `KEPT <path>:
  <reasons>` (measured), so the agent needs only the rule "never remove by hand what it kept"
  (`:55-59`, which stays). Two owners of one fact.
- `SKILL.md:11-13` redefines "the default branch" (conflict 6).
- `SKILL.md:40-51` step 4 packs closing, partial resolution, recording DELETED branches and the
  question label into one step; split into three short items.
- Scripts do the deterministic work here already; the prose is the only excess.

### requirements

| | |
|---|---|
| File | `SKILL.md` 7,601 |
| After (estimate) | about 6,000 |

- `SKILL.md:18-30` (1.1 KB) restates the start brief's (a)(b)(c) of
  `issue-handover/SKILL.md:146-152` and the title form of `method.md` §2. Point to one
  "first steps of a chat" section in issue-handover's start reference.
- `SKILL.md:74-84` step 6's archive sequence (1.0 KB) restates `issue-handover` step 7.4 and
  *Never archive*; point to it.
- `SKILL.md:45-47` "Claude Code: its question tool, at most four questions a round … Another
  client: its own way to ask" is client text in a shared skill; it is client-neutral enough and
  `rules/codex.md:9-10` owns Codex's side, so it stays.
- Steps and the definition of ready are clear; *Stays the user's* is a useful closing list.

### review-change

| | |
|---|---|
| File | `SKILL.md` 6,162 |
| After (estimate) | about 5,200 |

- `SKILL.md:10-11` stale (conflict 1).
- `SKILL.md:25-29` fetch and compare by hand (table above).
- `SKILL.md:71-81` exit codes: keep, but each could be one line if `review_verdict.py` printed
  the next action itself (it already names "The head is …, not …").
- `SKILL.md:90-101` *Gotchas* is the right form and worth keeping.

### open-issue, spec-first, repo-docs, efficient-design

- **open-issue** (3,335): clear numbered steps. `SKILL.md:31-40` step 3 has the priority rules
  in prose; a three-row table (critical, high, low) would be shorter. About 0.2 KB.
- **spec-first** (1,510): `SKILL.md:8` "Time spent making the specification precise pays back
  more than time spent watching the build" tells a capable model nothing it acts on.
- **repo-docs** (3,799): a table and short rules; good. `skill-standard.md:59` is a 133-character
  line; `skill-standard.md` is maintainer reference, read only when writing a skill.
- **efficient-design** (4,148): a checklist with examples; good. `§At review` repeats the core
  rule's consequence (`:70-72`), harmless.

### archive-finished-chats

| | |
|---|---|
| File | `SKILL.md` 6,843 |
| Read when | at the start of every issue chat (housekeeping, `method.md:183`) |
| After (estimate) | about 4,500 |

1. `SKILL.md:20-31` defines the worktree check in one 990-byte sentence that restates the
   `chat_archivable.py` header (`ok` cases, reflog proof, `--landed`). Replace by "the script
   prints `ok` or `keep: <reason>`; archive only on `ok`" plus the `--landed` rule.
2. `SKILL.md:54-69` step 3 stacks: which worktree to check (`worktreePath`, else `originCwd`,
   else `cwd`, only when linked), the never-archive-with-descendants rule, the app-made worktree
   shared with another chat, and #80's tool-made worktree. Split into "which worktree" and
   "keep when" lists.
3. `SKILL.md:9-18` intro holds the standing permission, the no-section case, reversibility, the
   title forms and the outside-the-app case in one paragraph; the outside-the-app case is also
   in the `compatibility` field.
4. `SKILL.md:10` cross-skill link into `issue-handover/method.md` (§1, §2, §4, §6): after a split
   (§7 below) it can link the one reference it needs.
5. Candidate selection is deterministic and could be a script over the session tools' JSON
   (table above).

### review-security (`SKILL.md`, `checklist.md`, `sources.md`)

| | |
|---|---|
| Files | `SKILL.md` 6,192, `checklist.md` 21,156 (areas 12.4 KB, stack notes 5.1 KB, severity, report and focus 3.7 KB), `sources.md` 37,549 |
| Read when | `SKILL.md` and `checklist.md` at every security review; `sources.md` only when changing a check (`SKILL.md:15-16`) and for the osv-scanner install |
| After (estimate) | `SKILL.md` about 4,500; `checklist.md` loaded about 16 KB (stack notes per stack); `sources.md` maintainer-only |

1. `SKILL.md:28-57` step 3 is 2.8 KB: the audit, its network destinations and the ask,
   thresholds, `--upgrades`, unaudited requirements, osv-scanner as second opinion,
   `--reachability` with its own ask, and the base comparison by `git archive`. Split into
   "run" (3 lines), "ask first" (one list of destinations per flag), and move the base
   comparison into the script (`--base`).
2. `checklist.md:169-228` stack notes (5.1 KB): read whole although "only where the repository
   uses the stack". One reference file per stack, or a heading per stack the agent reads alone.
3. `sources.md:158-195` *Installing osv-scanner* (2.5 KB) is a procedure for the person, not
   the reviewer; it belongs in `docs/install.md`. The rest of `sources.md` is maintainer
   reference: fine where it is, as long as no step tells a reviewer to read it.
4. `SKILL.md:8-12` repeats the core secret rule ("the secret is revoked first") — acceptable as
   the skill's stop condition.

### check-web-deploy

| | |
|---|---|
| Files | `SKILL.md` 5,792 + nine references, 64,266 in all |
| After (estimate) | about 5,500 |

The best-structured skill in the set: a numbered route, one reference per area, every reference
linked from `SKILL.md`, a dashboard template, a verdict rule. Small points: each reference opens
with a sources paragraph (`vercel.md:3-7`, `dashboard.md:3-13`) that a reviewer does not act on;
`google-auth.md` and the Google Cloud files are "not yet exercised in a live project"
(`SKILL.md:25-26`), which the agent should say in its verdict; the skill does not say that.

### codex-worker (Codex plugin, loaded only with Codex in the plan)

| | |
|---|---|
| Files | `SKILL.md` 9,505, `sources.md` 988 |
| After (estimate) | about 6,000 |

1. `SKILL.md:43-61` step 3 (1.7 KB) lists the worker's sandbox and read deny list, which
   `codex_worker.py`'s header owns (the skill says so at `:47`); keep the command, the time limit
   and the effort rule.
2. `SKILL.md:72-82` step 6 restates `codex_import.py`'s refusal list; the import prints its
   reason.
3. `SKILL.md:103-119` *What the route does not give* (1.4 KB) is limits and a disk measurement
   for the person deciding to use the route: `docs/install.md` *Codex as the worker* or the
   ruling of 2026-11-20.
4. `SKILL.md:43-44` background versus the method's foreground rule (conflict 3).
5. `SKILL.md:57-58` "the chat reads `status` and `last_message`, nothing else: a few hundred
   tokens per turn" — the whole indented JSON report still enters the context
   (`codex_worker.py:1081`).

### codex-issue-chats (Codex plugin)

| | |
|---|---|
| File | `SKILL.md` 7,927 |
| After (estimate) | about 4,500, plus a 3.4 KB reference for the integrator |

1. `SKILL.md:41-79` *Start the integrator* (3,375 bytes) applies only on the independent
   local-main route; a reference file read on that branch. The ruling of 2026-11-18 binds the
   behaviour, not its place: its **Binds** line names this skill's *Start the integrator*, so
   the line moves with it.
2. `SKILL.md:9-21` restates the issue-handover lifecycle in one 13-line sentence chain; keep
   "this skill replaces only these calls" and the list of them.
3. `SKILL.md:50-61` the integrator brief is a 12-line sentence with nested requirements; a
   literal template.

## 6. `rules/core.md` (needs the maintainer's word for every item)

7,969 bytes, 31 under the budget of 8,000. The guards that enforce parts of it are opt-in
(`install.sh --guards`, `docs/install.md:53`): a user without them has only the sentence, so no
rule can become a bare pointer to a guard. What can shrink is the list of spellings the guard
prints on refusal anyway.

| Line | Now | Proposal | Bytes saved (estimate) |
|---|---|---|---|
| `:36-37` | spec-first and requirements pointer | the skills' descriptions trigger on the same requests; drop, or keep only "large work with open requirements starts with a specification" | 60-150 |
| `:60` | "Agents have destroyed hours of uncommitted work …" | rationale; move to `DESIGN_DECISIONS.md` (it does help a model weigh the rule, so optional) | 90 |
| `:62-68` | the never-list with command spellings in parentheses | keep the categories; drop the parenthesised spellings that `pre_tool_git_guard.py` and `claude-permissions.json` name on refusal (`reset --hard`, `filter-repo`, `restore`, `checkout -- <path>`, `clean`, `stash drop`, `branch -D`) | about 180 |
| `:72-74` | trash, not `rm -rf`; literal paths | one sentence; the delete guard asks and names the safe form | about 60 |
| `:77-80` | staging by path, never `add -A`, `add .`, `add -f`, `commit -a`; trailer | keep "stage by explicit path"; the guard refuses each listed form; the client adds the trailer itself | about 100 |
| `:85-86` | cleanup after the merge | restated by `ship-change` step 8.6 and `local-main.md` §5.6, and the `cleanup-merged` description triggers on it | 130 |
| `:90-96` | personal data, 560 bytes | tighten to the rule, the scope and the exception; the personal-data guard names what matched | about 200 |
| `:18-21` | "Do the task … make routine judgement calls … say so in a sentence" | tighten wording | about 100 |
| `:79` + `:101-102` | closing keyword stated twice in two sections | one sentence in §Git (conflict 7) | about 60 |

**Estimate:** about 6,600 to 6,900 bytes without losing a rule (labelled estimate; the sum of the
rows, with wording tightened elsewhere).

**Procedure in core that belongs in a skill:** `:77-80` (commit message form) and `:81-84`
(which script pushes and merges) are procedure; both are also in `ship-change`. The rule part
("ask before every push unless a standing grant covers your own task branch; merge only on the
user's word or where the repository switched automatic merging on") must stay in core; the
script names can live in `ship-change` alone. The ruling of 2026-11-11 binds `rules/core.md`
§Git, so this needs the maintainer.

**Vague lines:** `:40` "long or unattended work" (no threshold); `:44-45` "when one is cheap"
(acceptable); `:51` "the layer where it lives" (clear enough with the review rule behind it).

**Already right:** no ALL-CAPS, short bold rule heads, the ask-first list as a list.

`rules/codex.md` (1,151 bytes, budget 2,000): a mapping list, clear; no finding.

## 7. The issue-chat method, by moment of use

**Now.** The start brief sends every new chat to `issue-handover` and `method.md` §4 step 1
(`SKILL.md:153-155`), and `method.md:183` to `archive-finished-chats`; the Read tool returns
`method.md` whole (496 lines). What each moment needs, measured by section:

| `method.md` section | Bytes | Needed at |
|---|---|---|
| top, overview and modes (`:1-35`) | 2,759 | nobody at run time (design) |
| §1 settings table, defaults (`:37-75`) | about 3,900 | start (start reading, extras, sidebar) and hand-over (model, worktree tool, prefix) |
| §1 spreading over areas, template (`:76-107`) | about 1,800 | `next_issue.py` (owner); template only at adoption |
| §2 title form | 865 | hand-over (the tool refuses a wrong title) |
| §3 principles | 3,537 | items 1, 9, 10 operative and rare; rest design |
| §4 items 1-4 (`:165-212`) | about 3,300 | item 1 at start; items 2-4 restate `SKILL.md` |
| §4 why that order, successor (`:214-238`) | about 2,300 | design |
| §4 hand-over before ready | 2,989 | rare (context limit, two failed corrections) |
| §4 background start | 2,172 | design (measurements) |
| §4 unattended rules | 3,411 | start and during work |
| §4 side chats | 2,578 | side chats and their parents only |
| §5 sharing | 2,300 | design note at start when overlap; rest restates SKILL step 3 and ship-change step 5 |
| §6 session tools | 3,531 | only when a tool misbehaves |
| §7 adoption | 3,242 | once per machine and repository (person), duplicates `docs/install.md` |

**Proposed split** (file names illustrative; seams stay client-neutral per the ruling of
2026-11-22, and the **Binds** lines of the rulings of 2026-11-17, 2026-11-22 (#82), 2026-11-11
and 2026-11-22 (#98) that name `method.md` §1, §4, §6 move with the text):

| File | Holds | Read at | Bytes (estimate) |
|---|---|---|---|
| `SKILL.md` | the hand-over steps 1-7 as lists and tables, never-archive as a list, mode table | every hand-over | about 9,000 |
| `start.md` | §4 item 1, the start brief template, the unattended rules that apply during work, the design note, questions for the user | every chat start | about 3,500 |
| `settings.md` | §1 table with defaults, §2 title form, five chains | start and hand-over | about 3,000 |
| `early-handover.md` | hand-over before the branch is ready (in place, with `worktreePath`, idle chat, refused archive) | that branch | about 3,000 |
| `fallbacks.md` | start-tool and claim failures as a decision table, the card fallback, §6's uncertain items | on a failure | about 3,500 |
| `side-chats.md` | §4 *Side chats* | a side chat or its parent | about 2,000 |
| `session-tools.md` | §6 table | when a tool misbehaves | about 3,500 |
| `docs/design/issue-chats.md` (not a skill file) | overview, §3 principles and citations, *why that order*, background-start measurements | never at run time | about 8,000 |
| `docs/install.md` §Issue chats | §7 adoption (merged with what install.md already has) | once, by the person | about 2,000 added |

**Bytes read per moment, before and after (estimates; "before" assumes the whole method is
read, as the brief asks):**

| Moment | Before | After |
|---|---|---|
| Chat start (issue-handover, method, archive-finished-chats) | 19.9 + 38.7 + 6.8 = 65.4 KB | 9.0 + 3.5 + 3.0 + 4.5 = 20.0 KB |
| Hand-over, pull-request mode (issue-handover, settings, ship-change) | 19.9 + 13.8 = 33.7 KB, 72.4 KB if the method is read again | 9.0 + 3.0 + 9.8 = 21.8 KB |
| Hand-over, local-main mode | add `local-main.md` 7.0: 40.7 to 79.4 KB | add 5.5: 27.3 KB |
| Hand-over before the branch is ready | 58.6 KB | 9.0 + 3.0 + 3.0 = 15.0 KB |
| A start or claim failure | 58.6 KB | 9.0 + 3.5 = 12.5 KB (+3.5 for session tools) |
| A side chat ending | brief sentence; up to 38.7 KB if it opens the method | brief sentence + 2.0 KB |
| Adoption in a repository | 38.7 KB + `docs/install.md` | `docs/install.md` alone |

The largest single saving is the chat start: about 45 KB per issue chat. With context cost
growing with every later request (the method's own reasoning, `method.md:128-129`), those bytes
are paid again on each call of the chat until compaction.

## Out of scope, noted in passing

- `plugins/issue-chats/scripts/context_limit.py` header names the maintainer by first name
  in two rulings' citations; `AGENTS.md` *Attribution only where it belongs* may cover script
  headers. For `duplication-drift.md` or `tooling.md` to judge.
