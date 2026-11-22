# Audit #123: context cost by when it loads

Measured on `agent/123-audit` at `e27f84f` (= `origin/main`), 2026-11-22. Every number below comes
from `python3 audit/123/measure_context.py`, run from the repository root (its full output is
the appendix), unless a line names another source. `tiktoken` is not installed here, so tokens
are **estimated as bytes / 4** (English prose); treat every token count as an estimate.

## Method and assumptions

- **Rules blocks:** the script imports `tools/installer.py` and calls `claude_block([])` and
  `codex_block([])`, so the blocks are exactly what the installer writes (no overlay).
  Claude Code imports `rules/core.md` with `@`; Codex gets `core.md` + `codex.md` inlined.
  The block's HTML-comment markers are not shown to the model: in this session's own context the
  installed `~/.claude/CLAUDE.md` appears with only its `@` lines (observed, not documented).
- **Skill listing:** Claude's form is `- <plugin>:<name>: <description>`, as this session's own
  skill listing shows; `compatibility` is not listed there. Codex lists name, description and a
  path per skill; the path is not measured.
- **Subagents pay the always-loaded part too:** this measuring subagent received the user's
  `CLAUDE.md` chain (with `rules/core.md`) and the full skill listing in its own context
  (observed). So class 1 is paid once per session *and once per subagent*.
- **Reference files:** "always" or "conditional" is a judgement from the wording of the
  instruction at the cited `file:line` (table in §2 of the appendix).
- **Rare branches:** the line ranges in `RARE` inside the script are a judgement; the script
  measures their bytes.
- **The repository's installed copy may differ:** the clone in `~/.agentic-github-flow` on this
  machine has an older `rules/core.md` (`cmp` differs at line 3). Numbers are for the repository.

## 1. Always (every session, every subagent)

| part | Claude Code | Codex |
|---|---|---|
| rules | `core.md` 7,969 B + import line 38 B = 8,007 B (~2.0k tokens) | inlined block 9,303 B (~2.3k tokens): core 7,969 + `codex.md` 1,151 + markers; 28.4 % of Codex's 32 KiB AGENTS.md budget |
| skill listing, all plugins | 14 skills, 6,282 B (~1.6k tokens) | 5,836 B name + description, plus a path per skill |
| hooks | 0 B: no SessionStart hook; no hook prints on the normal path | Codex gets the guards as `.rules` files, not plugin hooks |
| **total, all plugins** | **14,289 B (~3.6k tokens)** | **~15.1 kB + paths** |

Per plugin (Claude listing bytes; rules are core's): core 3,304 (8 skills) + rules 8,007;
security 447; web-deploy 524; issue-chats 1,086; guards 0 (hooks only); codex 921.

- `rules/core.md` is 7,969 B against the repository's own budget of 8,000 (`AGENTS.md`):
  31 bytes of headroom.
- No description is over the repository's 500-character limit or the standard's 1,024; the
  longest is `issue-handover` at 499. Mean 417 characters.
- **Cross-client waste:** the codex plugin installs in both clients when Codex is in the plan
  (`tools/installer.py`, `keys.append('codex')` per client). Claude then lists
  `codex-issue-chats` (488 B, "Use in Codex ..."), which a Claude session never runs, and Codex
  lists `codex-worker` (433 B, "from a Claude Code issue chat"), which a Codex session never runs.
- **Hooks print only on a deny, an ask or a note.** `context-gate.sh` runs on every tool call but
  starts Python only on an `agent/<digit>` branch and prints nothing below the limit;
  `question_label.py` on UserPromptSubmit prints only after an answered question. Longest
  message literals: `question_label.py` 459 B, `context_limit.py` 440 B, `archive_guard.py`
  110 B (placeholders not counted). The guards answer with a JSON reason built from variables;
  not measured by this method.
- **Maintainers of this repository only:** `AGENTS.md` 3,454 B + `CLAUDE.md` 11 B
  (`@AGENTS.md`), ~0.9k tokens, every session in this repository.

## 2. Per skill run

No SKILL.md is over 500 lines or over 5,000 body tokens. `issue-handover` is at the edge:
240 lines, 19,052 body bytes = **4,763 estimated tokens (95 % of the 5,000 recommendation)**;
the whole file is 4,970. `method.md` (a reference file, not bound by the SKILL.md limit) has
**495 lines**, 38,722 B.

Typical run cost, SKILL.md plus the reference files it always sends the agent to:

| skill | SKILL.md B | always-read refs B | total B | ~tokens |
|---|---|---|---|---|
| issue-handover | 19,879 | 38,722 (method.md) | 58,601 | 14,650 |
| archive-finished-chats | 6,843 | 38,722 (method.md §1, §2, §4, §6) | 45,565 | 11,391 |
| check-web-deploy | 5,792 | 36,099 (dashboard, privacy, checklist) + route files 4-24 kB | 41,891+ | 10,473+ |
| review-security | 6,192 | 21,156 (checklist.md) | 27,348 | 6,837 |
| ship-change | 13,822 | 0 (local-main.md 6,951 in local-main mode) | 13,822 | 3,456 |
| codex-worker | 9,505 | 0 | 9,505 | 2,376 |
| cleanup-merged | 8,170 | 0 | 8,170 | 2,042 |
| codex-issue-chats | 7,927 | 0 | 7,927 | 1,982 |
| requirements | 7,601 | 0 (method.md when issue chats run) | 7,601 | 1,900 |
| review-change | 6,162 | 0 | 6,162 | 1,540 |
| efficient-design | 4,148 | 0 | 4,148 | 1,037 |
| repo-docs | 3,799 | 0 | 3,799 | 950 |
| open-issue | 3,335 | 0 | 3,335 | 834 |
| spec-first | 1,510 | 0 | 1,510 | 378 |

"method.md whole" assumes a plain file read, which reads the whole file unless an offset is
given; a chat may read less. `review-security/sources.md` (37,549 B) is a citation list, read
only for §Installing osv-scanner.

### Text a run needs every time versus rare branches (judgement)

| skill | movable share | sections |
|---|---|---|
| cleanup-merged | 44 % (3,555 B) | *What the script checks* (lines 61-108): the script's header owns it; needed only when a worktree is kept |
| codex-issue-chats | 43 % (3,375 B) | *Start the integrator* (41-79): local-main mode only |
| issue-handover | 27 % (5,384 B) | another client (9-12), probe branch (63-66), the start fallback (163-180), starting chains (220-223), card fallback (225-230), hand-over before ready (232-240), four local-main passages |
| archive-finished-chats | 24 % (1,613 B) | the worktree check in detail (20-31, the script owns it), step 0 for card-started chats (33-39) |
| codex-worker | 23 % (2,161 B) | the settings row (25-31, setup only), *What the route does not give* (103-122) |
| requirements | 15 % (1,121 B) | *Where issue chats run* (18-31) |
| review-security | 15 % (920 B) | osv-scanner second opinion, Rust reachability (41-50) |
| ship-change | 12 % (1,674 B) | mode unknown (33-36), fixing the mode in HANDOFF.md (38-53), merge conflicts (93-100) |
| review-change | 6 % (366 B) | a branch without a pull request (83-89) |

Sum across these skills: 20,169 B (~5.0k tokens). The small skills (spec-first, open-issue,
repo-docs, efficient-design, check-web-deploy as a router) have no meaningful rare branch.

`method.md` by section: §1 settings 5,008 B; §2 title 866; §3 one issue one chat 3,538;
**§4 lifecycle 16,795** (of which *A hand-over before the branch is ready* 2,990, *The next chat
starts in the background* 2,173, *Unattended up to the ask for the push* 3,412, *Side chats*
2,579); §5 sharing 2,301; §6 session tools 3,532; §7 adopting 3,243. **§4 step 1, the part a
starting chat is told to follow, is 1,348 B (lines 169-185): 3.5 % of the file.**

## 3. Per issue-chat start (Claude Code)

What a new issue chat is made to read, in order (`start_issue_chat.py`, the start brief of
`issue-handover/SKILL.md:146-161`, `method.md` §4 step 1):

| order | what | bytes |
|---|---|---|
| 0 | always: `core.md` + import line; skill listing (all plugins) | 8,007 + 6,282 |
| 1 | ready prompt (`start_issue_chat.py:87`) | 49 |
| 2 | the start brief (written by the handing chat) | variable |
| 3 | `issue-handover/SKILL.md` ("this skill and method.md §4 step 1 govern its start", `SKILL.md:153`) | 19,879 |
| 4 | `method.md` read whole (or only §4 step 1: 1,348) | 38,722 |
| 5 | the issue with comments; the settings' start reading | variable |
| 6 | `archive-finished-chats/SKILL.md` (housekeeping, `method.md` §4 step 1.4) | 6,843 |
| 7 | its tool output: `list_sessions` (limit 50), `chat_archivable.py` per chat | variable |

**Fixed repository text read at a start: 65,444 B (~16.4k tokens) with method.md whole;
28,070 B (~7.0k tokens) with §4 step 1 only. With the always-loaded part: 79,733 B (~19.9k
tokens).** The hand-over later needs `issue-handover` again (already in context unless
compacted) plus `ship-change` 13,822 B and `cleanup-merged` 8,170 B; the review runs in a
subagent with `review-change` 6,162 B plus its own always-loaded 14,289 B.

**Against #82** (measured on 11 pax_deorum transcripts, 2026-11-17, tokens ≈ chars / 3.5):
call 1 was 55k tokens in every chat (system prompt, tools, AGENTS.md, rules), call 2 86-87k
(+31k from the desktop app), first code at 121-154k for Opus chats. This repository's
always-loaded part is ~3.6k of the 55k (about 6.5 %); its fixed start reading (~16.4k
estimated with method.md whole) is roughly a quarter to a half of the 35-67k an Opus chat reads
between the brief and its first code. The rest is the app, the target repository's documents,
the issue and code. #82's option 2 ("lighter starts ... sections instead of whole files") applies
to this repository's own start reading too.

**Against #98:** its goal holds. `grep -i codex` over `rules/core.md`, every non-codex
SKILL.md and every reference file a non-codex skill points to finds **no line** (script section
"Codex text in what a Claude-only install loads"). #98 measured 4,431 B of Codex lines in
`method.md` and 930 B in `issue-handover/SKILL.md` on a9dae85; both are now 0. What remains is
the cross-client listing above (488 B in Claude, 433 B in Codex), only on machines with both
clients.

## 4. On demand

| file | bytes | ~tokens | who reads it |
|---|---|---|---|
| `docs/install.md` | 33,521 | 8,380 | the installing agent, once per install or update; 518 lines |
| `DESIGN_DECISIONS.md` | 24,688 | 6,172 | maintainers, when a ruling matters |
| `HANDOFF.md` | 14,318 | 3,580 | maintainers; read by section through its reading map |
| `docs/guide.md` | 10,700 | 2,675 | people |
| `templates/company-overlay/AGENTS.md` | 2,226 | 556 | an overlay built from it becomes always-loaded |
| `README.md`, `templates/README.md`, `NOTICE` | 2,483 | 621 | people |

**Script help.** Most scripts parse their arguments by hand and print the whole module docstring
for `--help` and, for most, on a usage error to stderr: `audit_dependencies.py` 6,247 B,
`merge_pr.py` 5,238, `push_branch.py` 4,658, `landing.py` 4,639, `scan_secrets.py` 3,608,
`new_worktree.py` 3,052, `review_verdict.py` 2,953, `promote_main.py` 2,725; the codex scripts
print a docstring paragraph on a usage error (`codex_tools.py` 7,245 B). The five argparse
scripts print 347-633 B. The skills also say "the script's header owns the details" for
`landing.py`, `new_worktree.py`, `push_branch.py`, `merge_pr.py`, so an agent that follows that
reads 3-5 kB per header. Hook scripts' docstrings (up to 11,560 B in `pre_tool_delete_guard.py`)
are never printed into a context.

**Script output on success** (read from the code): short and line-oriented. `landing.py
--explain` prints one `check:` line per signal plus three lines; `overlap_check.py` one line per
hit plus a count; `chat_archivable.py` one line. `next_issue.py` prints **every** ready issue
(`gh ... --limit 1000`), one line each, where the skill takes the first line: in a repository
with many ready issues that is the one unbounded success output.

## Ranking: cost × frequency

Frequency unit: one issue chat of an issue-chats user, which also runs one review subagent.
"Always" items count twice (the chat and its subagent).

| # | item | bytes | how often | bytes per chat |
|---|---|---|---|---|
| 1 | `method.md`, read whole at the start (and pointed to by archive-finished-chats) | 38,722 | once per chat | 38,722 |
| 2 | `issue-handover/SKILL.md` | 19,879 | once per chat (start; reused at hand-over) | 19,879 |
| 3 | `rules/core.md` + import | 8,007 | every session and subagent | 16,014 |
| 4 | `ship-change/SKILL.md` | 13,822 | once per task | 13,822 |
| 5 | skill listing (14 skills) | 6,282 | every session and subagent | 12,564 |
| 6 | `cleanup-merged/SKILL.md` | 8,170 | once per merge | 8,170 |
| 7 | `archive-finished-chats/SKILL.md` (+ list_sessions output) | 6,843+ | every chat start | 6,843+ |
| 8 | `review-change/SKILL.md` | 6,162 | once per pull request (subagent) | 6,162 |
| 9 | `review-security/checklist.md` | 21,156 | security-relevant changes (~1 in 3, guess) | ~7,000 |
| 10 | `AGENTS.md` (this repository's maintainers) | 3,454 | every session and subagent here | 6,908 |
| 11 | `local-main.md` | 6,951 | each landing in local-main repositories | 6,951 there, 0 elsewhere |
| 12 | `codex-worker/SKILL.md` | 9,505 | chats with the `codex worker` label | 9,505 there |
| 13 | `review-security/SKILL.md` | 6,192 | security-relevant changes | ~2,000 |
| 14 | `requirements/SKILL.md` (+ method.md when issue chats run) | 7,601 | per requirements chat | rare |
| 15 | `docs/install.md` | 33,521 | once per install or update | rare |

## Files over a limit

- None over a hard limit: every description is 221-499 characters (limit 500 here, 1,024 in the
  standard); every SKILL.md is under 500 lines and under 5,000 estimated body tokens.
- At the edge: `issue-handover/SKILL.md` 4,763 body tokens (95 % of 5,000); `rules/core.md`
  7,969 of 8,000 bytes; `issue-handover/description` 499 of 500; `method.md` 495 lines (a
  reference file; the standard's best practice keeps reference files focused and loaded only
  when needed); `docs/install.md` 518 lines (not a skill file).

## The five biggest savings (estimates)

1. **Start reading of an issue chat: send it to §4 step 1, not to the method and the skill.**
   A start needs ~1.3 kB of `method.md` and nothing of the hand-over procedure until the
   hand-over. A short start file (or a pointer to the exact section) in the brief saves up to
   **~37 kB per chat** (method.md whole minus §4 step 1), and moves the 19.9 kB SKILL.md from the
   start to the hand-over, so it is not carried through every turn of the work.
2. **Move rare branches out of SKILL.md bodies** into reference files read only on that branch:
   20.2 kB across nine skills; per issue chat (issue-handover, ship-change, cleanup-merged,
   archive-finished-chats, review-change) **~12.6 kB**.
3. **Split `method.md` (38.7 kB, 495 lines) by when it is needed:** setup (§1 settings and the
   template, §7 adopting: ~8.2 kB), the lifecycle (§4: 16.8 kB), background (§3, §5, §6:
   ~9.4 kB). Any skill that points to it then loads one part; **~20-30 kB** whenever the whole
   file would have been read (issue-handover, archive-finished-chats, requirements).
4. **`archive-finished-chats` at every chat start:** 6.8 kB of skill plus `list_sessions`
   output (up to 50 sessions) per chat. Running it at the hand-over only, or as one script that
   prints the verdicts, saves **~7 kB+ per chat**; trimming its script-owned detail saves 1.6 kB
   wherever it still runs.
5. **Always-loaded part, multiplied by sessions and subagents:** descriptions trimmed to ~300
   characters save 1,552 B; not listing the codex plugin's other-client skill saves 488 B
   (Claude) or 433 B (Codex): **~2 kB per session and per subagent**, ~4 kB per issue chat with
   one review subagent. Separately, splitting `review-security/checklist.md` (21.2 kB) by area
   would save an estimated 10-14 kB per security review.

## Appendix: output of `python3 audit/123/measure_context.py`

# Context cost by load class (measured at e27f84f; tokens: bytes / 4, an estimate for English prose)

## 1. Always: rules blocks

| item | bytes | lines | words | tokens |
|---|---|---|---|---|
| Claude: block lines in ~/.claude/CLAUDE.md (markers are HTML comments, not shown to the model) | 220 | 4 | 25 | 55 |
| Claude: the `@` import line(s) the model sees | 38 | 1 | 1 | 10 |
| Claude: rules/core.md, expanded from the import | 7,969 | 122 | 1,292 | 1,992 |
| Codex: the whole inlined block in ~/.codex/AGENTS.md (core.md + codex.md + markers) | 9,303 | 145 | 1,467 | 2,326 |
|   of which rules/codex.md | 1,151 | 19 | 151 | 288 |

rules/core.md budget (AGENTS.md: under 8,000 bytes): 7969 bytes. Codex block share of the 32 KiB AGENTS.md read limit: 28.4 %.

## 1. Always: skill listing (name + description per installed skill)

Claude line form `- <plugin>:<name>: <description>` as this session's own listing shows it; `compatibility` is not in the listing.

| plugin | skill | description chars | Claude listing bytes | compatibility chars (not listed) | tokens | limit |
|---|---|---|---|---|---|---|
| core | cleanup-merged | 387 | 431 | 0 | 108 | ok |
| core | efficient-design | 427 | 473 | 0 | 118 | ok |
| core | open-issue | 411 | 451 | 0 | 113 | ok |
| core | repo-docs | 272 | 311 | 0 | 78 | ok |
| core | requirements | 367 | 409 | 0 | 102 | ok |
| core | review-change | 419 | 462 | 0 | 116 | ok |
| core | ship-change | 465 | 506 | 0 | 126 | ok |
| core | spec-first | 221 | 261 | 0 | 65 | ok |
| security | review-security | 398 | 447 | 0 | 112 | ok |
| web-deploy | check-web-deploy | 472 | 524 | 0 | 131 | ok |
| issue-chats | archive-finished-chats | 477 | 536 | 137 | 134 | ok |
| issue-chats | issue-handover | 499 | 550 | 269 | 138 | ok |
| codex | codex-issue-chats | 440 | 488 | 193 | 122 | ok |
| codex | codex-worker | 390 | 433 | 155 | 108 | ok |

| plugin | skills | listing bytes | tokens |
|---|---|---|---|
| core | 8 | 3,304 | 826 |
| security | 1 | 447 | 112 |
| web-deploy | 1 | 524 | 131 |
| issue-chats | 2 | 1,086 | 272 |
| guards | 0 | 0 | 0 |
| codex | 2 | 921 | 230 |
| all | 14 | 6,282 | 1,571 |

## 1. Always: hooks

| plugin | event | matcher | script |
|---|---|---|---|
| guards | PreToolUse | Bash | run-python.sh → pre_tool_git_guard.py |
| guards | PreToolUse | Bash | run-python.sh → pre_tool_merge_guard.py |
| guards | PreToolUse | ^(Bash\|mcp__.*__run_in_terminal)$ | run-python.sh → pre_tool_delete_guard.py |
| guards | PreToolUse | ^(Bash\|WebFetch\|WebSearch\|Artifact\|ArtifactData\|ArtifactComments\|mcp__.*)$ | run-python.sh → pre_tool_personal_data.py |
| issue-chats | PreToolUse | ^mcp__ccd_session_mgmt__archive_session$ | run-guard.sh → archive_guard.py |
| issue-chats | PreToolUse | ^(AskUserQuestion\|mcp__ccd_turn__wrap_up)$ | run-hook.sh → question_label.py |
| issue-chats | PreToolUse | .* | context-gate.sh |
| issue-chats | PostToolUse | ^(AskUserQuestion\|Bash)$ | run-hook.sh → question_label.py |
| issue-chats | PostToolUse | .* | context-gate.sh |
| issue-chats | UserPromptSubmit | (every prompt) | run-hook.sh → question_label.py |

No SessionStart hook. Text reaches the context only when a hook denies, asks or adds a note; longest message literal per script (placeholders not counted):

| script | longest literal message bytes |
|---|---|
| plugins/issue-chats/scripts/context_limit.py | 440 |
| plugins/issue-chats/scripts/question_label.py | 459 |
| plugins/issue-chats/scripts/archive_guard.py | 110 |
| plugins/guards/scripts/pre_tool_git_guard.py | 0 |
| plugins/guards/scripts/pre_tool_merge_guard.py | 0 |

## 1. Always for maintainers of this repository only

| file | bytes | lines | words | tokens |
|---|---|---|---|---|
| AGENTS.md | 3,454 | 51 | 496 | 864 |
| CLAUDE.md | 11 | 1 | 1 | 3 |

## 1. Always: totals per plugin and client

| plugin | skill listing bytes | tokens (bytes/4) |
|---|---|---|
| core | 3,304 | 826 |
| security | 447 | 112 |
| web-deploy | 524 | 131 |
| issue-chats | 1,086 | 272 |
| guards | 0 | 0 |
| codex | 921 | 230 |

Claude, all plugins: rules 8,007 + listing 6,282 = 14,289 bytes (~3,572 tokens). Codex, all plugins but guards: rules 9,303 + name/description 5,836 bytes (plus a path per skill, not measured).

## 2. Per skill run: SKILL.md

| plugin | skill | file bytes | lines | words | tokens | body bytes | body tokens | over limit |
|---|---|---|---|---|---|---|---|---|
| issue-chats | issue-handover | 19,879 | 240 | 3,293 | 4,970 | 19,052 | 4,763 | ok |
| core | ship-change | 13,822 | 211 | 2,231 | 3,456 | 13,317 | 3,329 | ok |
| codex | codex-worker | 9,505 | 122 | 1,549 | 2,376 | 8,903 | 2,226 | ok |
| core | cleanup-merged | 8,170 | 108 | 1,307 | 2,042 | 7,740 | 1,935 | ok |
| codex | codex-issue-chats | 7,927 | 90 | 1,266 | 1,982 | 7,232 | 1,808 | ok |
| core | requirements | 7,601 | 105 | 1,232 | 1,900 | 7,193 | 1,798 | ok |
| issue-chats | archive-finished-chats | 6,843 | 81 | 1,085 | 1,711 | 6,162 | 1,540 | ok |
| security | review-security | 6,192 | 76 | 969 | 1,548 | 5,750 | 1,438 | ok |
| core | review-change | 6,162 | 101 | 1,012 | 1,540 | 5,701 | 1,425 | ok |
| web-deploy | check-web-deploy | 5,792 | 72 | 812 | 1,448 | 5,275 | 1,319 | ok |
| core | efficient-design | 4,148 | 72 | 720 | 1,037 | 3,676 | 919 | ok |
| core | repo-docs | 3,799 | 51 | 624 | 950 | 3,489 | 872 | ok |
| core | open-issue | 3,335 | 42 | 563 | 834 | 2,885 | 721 | ok |
| core | spec-first | 1,510 | 25 | 252 | 378 | 1,250 | 312 | ok |

## 2. Per skill run: reference files the SKILL.md sends the agent to

| skill | file | when | instruction at | bytes | lines | tokens |
|---|---|---|---|---|---|---|
| issue-handover | issue-handover/method.md | always (named as the method; the start brief makes every new chat read §4 step 1) | issue-handover/SKILL.md:14, :153 | 38,722 | 495 | 9,680 |
| archive-finished-chats | issue-handover/method.md | always (§1, §2, §4 Side chats, §6) | archive-finished-chats/SKILL.md:10 | 38,722 | 495 | 9,680 |
| ship-change | ship-change/local-main.md | conditional: local-main mode only | ship-change/SKILL.md:32 | 6,951 | 105 | 1,738 |
| cleanup-merged | ship-change/local-main.md | conditional: local-main mode only | cleanup-merged/SKILL.md:16 | 6,951 | 105 | 1,738 |
| review-change | ship-change/local-main.md | conditional: local-main mode only | review-change/SKILL.md:88 | 6,951 | 105 | 1,738 |
| codex-issue-chats | ship-change/local-main.md | conditional: local-main mode, §2 | codex-issue-chats/SKILL.md:42, :55 | 6,951 | 105 | 1,738 |
| requirements | issue-handover/method.md | conditional: where issue chats run (§1, §2) | requirements/SKILL.md:21 | 38,722 | 495 | 9,680 |
| repo-docs | repo-docs/skill-standard.md | conditional: writing or changing a skill | repo-docs/SKILL.md:27 | 5,187 | 61 | 1,297 |
| repo-docs | repo-docs/skeleton.md | conditional: a new repository | repo-docs/SKILL.md:51 | 2,226 | 86 | 556 |
| review-security | review-security/checklist.md | always (step 5: the checks, area by area) | review-security/SKILL.md:15, :63 | 21,156 | 289 | 5,289 |
| review-security | review-security/sources.md | conditional: §Installing osv-scanner; otherwise a citation | review-security/SKILL.md:16, :41 | 37,549 | 210 | 9,387 |
| check-web-deploy | check-web-deploy/dashboard.md | always (step 8) | check-web-deploy/SKILL.md:60 | 10,916 | 152 | 2,729 |
| check-web-deploy | check-web-deploy/privacy.md | always (step 6) | check-web-deploy/SKILL.md:56 | 4,027 | 51 | 1,007 |
| check-web-deploy | review-security/checklist.md | always (step 7: §Report, §Severity) | check-web-deploy/SKILL.md:59 | 21,156 | 289 | 5,289 |
| check-web-deploy | check-web-deploy/vercel.md | conditional: Vercel route | check-web-deploy/SKILL.md:51 | 6,888 | 91 | 1,722 |
| check-web-deploy | check-web-deploy/supabase.md | conditional: Vercel + Supabase route | check-web-deploy/SKILL.md:40 | 7,416 | 102 | 1,854 |
| check-web-deploy | check-web-deploy/google-auth.md | conditional: Google sign-in on | check-web-deploy/SKILL.md:46 | 5,085 | 72 | 1,271 |
| check-web-deploy | check-web-deploy/cloud-run.md | conditional: Google Cloud route | check-web-deploy/SKILL.md:54 | 6,429 | 94 | 1,607 |
| check-web-deploy | check-web-deploy/iap.md | conditional: Google Cloud route with IAP | check-web-deploy/SKILL.md:46 | 4,089 | 58 | 1,022 |
| check-web-deploy | check-web-deploy/cloud-sql.md | conditional: Cloud SQL | check-web-deploy/SKILL.md:43 | 4,197 | 62 | 1,049 |
| check-web-deploy | check-web-deploy/mail.md | conditional: the site sends mail | check-web-deploy/SKILL.md:49 | 2,476 | 41 | 619 |
| codex-worker | codex-worker/sources.md | conditional: a citation only | codex-worker/SKILL.md:122 | 988 | 12 | 247 |

### Typical run cost (SKILL.md + always-read references)

| skill | SKILL.md bytes | always-read refs bytes | total bytes | tokens (bytes/4) |
|---|---|---|---|---|
| issue-handover | 19,879 | 38,722 | 58,601 | 14,650 |
| archive-finished-chats | 6,843 | 38,722 | 45,565 | 11,391 |
| check-web-deploy | 5,792 | 36,099 | 41,891 | 10,473 |
| review-security | 6,192 | 21,156 | 27,348 | 6,837 |
| ship-change | 13,822 | 0 | 13,822 | 3,456 |
| codex-worker | 9,505 | 0 | 9,505 | 2,376 |
| cleanup-merged | 8,170 | 0 | 8,170 | 2,042 |
| codex-issue-chats | 7,927 | 0 | 7,927 | 1,982 |
| requirements | 7,601 | 0 | 7,601 | 1,900 |
| review-change | 6,162 | 0 | 6,162 | 1,540 |
| efficient-design | 4,148 | 0 | 4,148 | 1,037 |
| repo-docs | 3,799 | 0 | 3,799 | 950 |
| open-issue | 3,335 | 0 | 3,335 | 834 |
| spec-first | 1,510 | 0 | 1,510 | 378 |

### Rare branches inside SKILL.md bodies (judgement; bytes measured)

| file | lines | branch | bytes |
|---|---|---|---|
| issue-handover/SKILL.md | 9-12 | another client than Claude Code | 323 |
| issue-handover/SKILL.md | 63-66 | a probe that must not be merged | 349 |
| issue-handover/SKILL.md | 163-180 | the fallback (a failed start) | 1,625 |
| issue-handover/SKILL.md | 220-223 | starting chains (orchestrator only) | 358 |
| issue-handover/SKILL.md | 225-230 | the card fallback | 489 |
| issue-handover/SKILL.md | 232-240 | a hand-over before the branch is ready | 828 |
| issue-handover/SKILL.md | 31-34 | local-main mode (intro) | 294 |
| issue-handover/SKILL.md | 81-87 | local-main mode (step 2) | 623 |
| issue-handover/SKILL.md | 186-188 | local-main mode (step 6) | 228 |
| issue-handover/SKILL.md | 216-218 | local-main mode (step 7) | 267 |
| issue-handover/SKILL.md | sum | 27 % of 19,879 bytes | 5,384 |
| ship-change/SKILL.md | 33-36 | mode unknown | 349 |
| ship-change/SKILL.md | 38-53 | fixing the mode in HANDOFF.md (repository setup) | 619 |
| ship-change/SKILL.md | 93-100 | merge conflicts, inside and outside .claude/ | 706 |
| ship-change/SKILL.md | sum | 12 % of 13,822 bytes | 1,674 |
| cleanup-merged/SKILL.md | 61-108 | What the script checks (the script header owns it) | 3,555 |
| cleanup-merged/SKILL.md | sum | 44 % of 8,170 bytes | 3,555 |
| archive-finished-chats/SKILL.md | 20-31 | the worktree check in detail (the script owns it) | 993 |
| archive-finished-chats/SKILL.md | 33-39 | step 0, a chat a card started | 620 |
| archive-finished-chats/SKILL.md | sum | 24 % of 6,843 bytes | 1,613 |
| codex-issue-chats/SKILL.md | 41-79 | start the integrator (local-main mode only) | 3,375 |
| codex-issue-chats/SKILL.md | sum | 43 % of 7,927 bytes | 3,375 |
| codex-worker/SKILL.md | 25-31 | the settings row (repository setup) | 684 |
| codex-worker/SKILL.md | 103-122 | What the route does not give (background) | 1,477 |
| codex-worker/SKILL.md | sum | 23 % of 9,505 bytes | 2,161 |
| requirements/SKILL.md | 18-31 | where issue chats run | 1,121 |
| requirements/SKILL.md | sum | 15 % of 7,601 bytes | 1,121 |
| review-change/SKILL.md | 83-89 | a branch without a pull request (local-main mode) | 366 |
| review-change/SKILL.md | sum | 6 % of 6,162 bytes | 366 |
| review-security/SKILL.md | 41-50 | osv-scanner second opinion and Rust reachability | 920 |
| review-security/SKILL.md | sum | 15 % of 6,192 bytes | 920 |

### method.md by section

| section | bytes (### included in their ##) |
|---|---|
| ## 1. The settings section switches it on | 5,008 |
| ## Issue chats settings | 680 |
| ## 2. The chat title form | 866 |
| ## 3. One issue, one chat | 3,538 |
| ## 4. The chat lifecycle | 16,795 |
| ## 5. Sharing the repository | 2,301 |
| ## 6. The desktop app's session tools | 3,532 |
| ## 7. Adopting issue chats in a repository | 3,243 |
|   ### A hand-over before the branch is ready | 2,990 |
|   ### The next chat starts in the background | 2,173 |
|   ### Unattended up to the ask for the push | 3,412 |
|   ### Side chats | 2,579 |

method.md §4 step 1 (the chat start): lines 169-185, 1,348 bytes.

## 3. Per issue-chat start (Claude Code)

| order | what | instruction at | bytes |
|---|---|---|---|
| 0 | always: rules/core.md + import line (overlays not counted) | every session | 8,007 |
| 0 | always: skill listing, all six plugins | every session | 6,282 |
| 1 | ready prompt of start_issue_chat.py | start_issue_chat.py:87 | 49 |
| 2 | the start brief (written by the previous chat; not in the repository) | issue-handover/SKILL.md:146-161 | variable |
| 3 | issue-handover SKILL.md (the brief names the skill) | issue-handover/SKILL.md:153 | 19,879 |
| 4a | method.md, read whole | issue-handover/SKILL.md:14, :153 | 38,722 |
| 4b |   or only §4 step 1 | method.md §4 | 1,348 |
| 5 | the issue with its comments, settings start reading | method.md §4 step 1.1 | variable |
| 6 | archive-finished-chats SKILL.md (housekeeping) | method.md §4 step 1.4 | 6,843 |
| 7 | its tool output: list_sessions (limit 50), chat_archivable.py per chat | archive-finished-chats/SKILL.md:40, :54 | variable |

Repository files read at a chat start, beyond the always-loaded part: 65,444 bytes (~16,361 tokens) with method.md whole; 28,070 bytes (~7,018 tokens) with §4 step 1 only. With the always-loaded part: 79,733 bytes (~19,933 tokens).

## Codex text in what a Claude-only install loads (#98 check)

None.

## 4. On demand: documents

| file | bytes | lines | words | tokens |
|---|---|---|---|---|
| HANDOFF.md | 14,318 | 171 | 1,921 | 3,580 |
| DESIGN_DECISIONS.md | 24,688 | 319 | 3,754 | 6,172 |
| README.md | 1,319 | 30 | 188 | 330 |
| NOTICE | 146 | 3 | 17 | 36 |
| docs/install.md | 33,521 | 518 | 4,982 | 8,380 |
| docs/guide.md | 10,700 | 163 | 1,798 | 2,675 |
| templates/README.md | 1,018 | 10 | 141 | 254 |
| templates/company-overlay/AGENTS.md | 2,226 | 44 | 369 | 556 |
| audit/123/README.md | 1,311 | 28 | 210 | 328 |

## 4. On demand: script help (what `--help` or a usage error prints)

| script | file bytes | help bytes | source |
|---|---|---|---|
| plugins/guards/scripts/pre_tool_delete_guard.py | 93,578 | 11,560 | module docstring (no `--help`) |
| plugins/guards/scripts/pre_tool_sandbox_network.py | 63,936 | 7,883 | module docstring (no `--help`) |
| plugins/guards/scripts/pre_tool_personal_data.py | 49,337 | 7,387 | module docstring (no `--help`) |
| plugins/codex/scripts/codex_tools.py | 41,003 | 7,245 | module docstring (printed on a usage error) |
| plugins/security/scripts/audit_dependencies.py | 47,342 | 6,247 | module docstring (`--help` prints it) |
| plugins/issue-chats/scripts/context_limit.py | 25,055 | 5,400 | module docstring (no `--help`) |
| plugins/core/scripts/merge_pr.py | 26,588 | 5,238 | module docstring (`--help` prints it) |
| plugins/core/scripts/push_branch.py | 17,397 | 4,658 | module docstring (`--help` prints it) |
| plugins/core/scripts/landing.py | 24,760 | 4,639 | module docstring (`--help` prints it) |
| plugins/issue-chats/scripts/landing.py | 24,760 | 4,639 | module docstring (`--help` prints it) |
| plugins/issue-chats/scripts/chat_archivable.py | 17,638 | 4,205 | module docstring (no `--help`) |
| plugins/issue-chats/scripts/archive_guard.py | 13,027 | 4,063 | module docstring (no `--help`) |
| plugins/core/scripts/merge_landing.py | 27,769 | 3,621 | module docstring (no `--help`) |
| plugins/guards/scripts/pre_tool_merge_guard.py | 18,616 | 3,611 | module docstring (no `--help`) |
| plugins/security/scripts/scan_secrets.py | 27,816 | 3,608 | module docstring (`--help` prints it) |
| plugins/issue-chats/scripts/question_label.py | 15,893 | 3,222 | module docstring (no `--help`) |
| plugins/core/scripts/new_worktree.py | 18,818 | 3,052 | module docstring (`--help` prints it) |
| plugins/codex/scripts/codex_import.py | 12,297 | 2,968 | module docstring (printed on a usage error) |
| plugins/core/scripts/review_verdict.py | 11,423 | 2,953 | module docstring (`--help` prints it) |
| plugins/codex/scripts/codex_job.py | 14,395 | 2,878 | module docstring (printed on a usage error) |
| plugins/core/scripts/promote_main.py | 13,572 | 2,725 | module docstring (`--help` prints it) |
| plugins/guards/scripts/pre_tool_git_guard.py | 22,182 | 1,658 | module docstring (no `--help`) |
| plugins/core/scripts/push_paths.py | 3,968 | 1,239 | module docstring (printed on a usage error) |
| plugins/core/scripts/delete_merged_branch.py | 6,448 | 1,087 | module docstring (`--help` prints it) |
| plugins/core/scripts/work_proof.py | 11,783 | 1,074 | module docstring (no `--help`) |
| plugins/issue-chats/scripts/work_proof.py | 11,783 | 1,074 | module docstring (no `--help`) |
| plugins/issue-chats/scripts/handover_note.py | 3,263 | 1,020 | module docstring (no `--help`) |
| plugins/core/scripts/remove_merged_worktree.py | 52,162 | 633 | argparse `--help`, run |
| plugins/codex/scripts/codex_worker.py | 58,499 | 605 | argparse `--help`, run |
| plugins/issue-chats/scripts/next_issue.py | 12,380 | 430 | argparse `--help`, run |
| plugins/issue-chats/scripts/start_issue_chat.py | 22,289 | 415 | argparse `--help`, run |
| plugins/core/scripts/overlap_check.py | 17,157 | 414 | argparse `--help`, run |
| plugins/core/scripts/clone_dedupe_worktree.py | 9,340 | 347 | argparse `--help`, run |

