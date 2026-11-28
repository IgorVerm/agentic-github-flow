# Duplication and drift

Part of the audit of #123. Base: `e27f84f` (origin/main), measured 2026-11-22 in the worktree
`agent/123-audit`. Severity: **wrong** (a document says something the code or the repository
contradicts), **misleading** (true in part, or true only historically, and likely to steer an
agent wrong), **repeated** (a fact with more than one home; the copies agree today).

How it was measured:

- Every backticked path, script name and relative link in every tracked `.md` file was checked
  against `git ls-files` (throwaway script in `$TMPDIR`). All repository paths resolve; the
  unresolved ones are files of a user's project (`vercel.json`, `.mcp.json`, `ROADMAP.md`) or
  marked as history (`issue-handover/codex.md` "until #98", `plugins/issue-chats/scripts/codex_worker.py`
  "until #98").
- Every `--flag` written after a script name in a `.md` file was checked against that script's
  `--help` and source: none is missing. The flags of 18 scripts were listed by hand from
  `--help` and compared with what the skills tell agents to run: they agree.
- Top-level functions of `plugins/*/scripts/*.py` and `tools/installer.py` were compared by name
  and by AST body (throwaway script).
- Byte counts by `wc -c` on line ranges; section sizes by splitting on headings.
- `gh issue list` (open issues) read once; `python3 tests/run_all.py` run (result at the end).

Counts: 6 wrong, 12 misleading, 24 repeated facts or passages (A), 5 groups of duplicated code.

## A. Duplication

### A1. Facts restated in several documents (owner proposed in bold)

| # | Fact | Where | Bytes of repeats | Owner | Copies agree? |
|---|---|---|---|---|---|
| 1 | The `## Landing settings` table and the meaning of `landing`, `landing branch`, `automatic merge` | `plugins/core/skills/ship-change/SKILL.md:38-53`, `docs/install.md:325-345`, `plugins/core/scripts/landing.py` header | 619 + 1,048 | **`landing.py` header**; ship-change keeps the table (agents need it), install.md points | yes |
| 2 | Automatic-merge conditions and the excluded paths | `docs/install.md:340-345`, `docs/guide.md:104-112`, `plugins/core/skills/ship-change/SKILL.md:201-207`, `DESIGN_DECISIONS.md:283-296`, `HANDOFF.md:78-85`, `plugins/core/scripts/merge_pr.py` (`EXCLUDED`) | ~2.9 KB | **`merge_pr.py` header and `EXCLUDED`** | yes |
| 3 | The push grant line `standing grant \| push_branch.py` and its conditions | `docs/install.md:346-352`, `plugins/core/skills/ship-change/SKILL.md:146-152`, `DESIGN_DECISIONS.md:214-220`, `HANDOFF.md:86-92`, `push_branch.py` header | 642 + 671 + ~1.3 KB | **`push_branch.py` header** | yes |
| 4 | The rule "push on the user's yes or under a grant; ready/merge on the user's word or `merge_pr.py` where switched on" | `plugins/issue-chats/skills/issue-handover/SKILL.md:25-34`, `method.md:20-27`, `method.md:43-49`, `method.md:318-320`, `HANDOFF.md:154-158`, `method.md:94-98` (settings template), `plugins/codex/skills/codex-issue-chats/SKILL.md:12-13` | 864 + 702 + 631 + 279 + ~900 | **`ship-change` steps 6-8**; issue chats need one sentence pointing there | yes |
| 5 | The pre-push hook's refusals | `HANDOFF.md:93-102`, `docs/install.md:320-323`, `templates/README.md:7`, `plugins/core/skills/repo-docs/skeleton.md:82-83` | 810 + 357 + ~300 + ~250 | **`templates/pre-push` header** | yes |
| 6 | Worktree clones on macOS (default, switches, measurement) | `HANDOFF.md:103-108`, `docs/install.md:299-313`, `DESIGN_DECISIONS.md:183-197`, `plugins/core/skills/ship-change/SKILL.md:18-20` | 484 + 773 + ~1 KB | **`new_worktree.py` header**; the ruling stays in DD | yes |
| 7 | Allow rules for unattended chains (`start_issue_chat.py`, `push_branch.py`, `merge_pr.py`, `archive_session`, never the cache path) | `docs/install.md:269-297`, `plugins/issue-chats/skills/issue-handover/method.md:456-468` | 1,642 + 1,174 | **`docs/install.md`** (the person sets them); method.md §7 one pointer | yes |
| 8 | Codex worker's read deny list | `docs/install.md:440-456`, `plugins/codex/skills/codex-worker/SKILL.md:46-53`, `DESIGN_DECISIONS.md:66-76`, `codex_worker.py` header | 1,480 + 752 | **`codex_worker.py` header** | yes |
| 9 | What `codex_import.py` refuses | `docs/install.md:481-493`, `plugins/codex/skills/codex-worker/SKILL.md:37-42` and `:72-82`, `codex_import.py` header | 1,130 + 966 + ~400 | **`codex_import.py` header**; the skill's step 2 needs the list for the prompt | yes |
| 10 | Context limit 300k / labels 600k / decision point 2x, at most 900k | `HANDOFF.md:38-41`, `DESIGN_DECISIONS.md:126-167` (two entries), `method.md:64` (§1 row), `method.md:129-136`, `context_limit.py:12-39`, start brief text | 334 + 744 + row | values: **DD**; mechanism: **`context_limit.py` header** | yes (300k, 600k, 900k everywhere) |
| 11 | The question label: default `needs-user`, when added and removed | `issue-handover/SKILL.md:88-92`, `method.md:58`, `method.md:334-346`, `cleanup-merged/SKILL.md:49-51`, `question_label.py:5,62`, `HANDOFF.md:35-37`, DD 2026-11-17 | 507 + 1,171 + ~600 | **method.md §1** (open issue #74 already) | yes |
| 12 | Issue-chat lifecycle (ready-to-push comment, ask, push, CI, merge, cleanup, archive) | `method.md:186-212` (§4 items 2-4) and `issue-handover/SKILL.md` steps 2, 6, 7 | 2,284 | **SKILL.md** for the steps; method.md the why | yes |
| 13 | Hand-over before the branch is ready | `issue-handover/SKILL.md:232-240`, `method.md:240-278` | 828 + 2,989 | **method.md** (SKILL already points) | yes |
| 14 | The commit form `git commit -m "…" -- <paths>`, `(#n)`, no `--amend` | `rules/core.md:77-80`, `issue-handover/SKILL.md:69-71`, `method.md:321-325`, `codex-worker/SKILL.md:38` | ~400 | **`rules/core.md`** | yes |
| 15 | The signature `🤖 <model> (<role>):` | `rules/core.md:103-105` (owner), `DESIGN_DECISIONS.md:89`, `open-issue:24`, `ship-change:116`, `local-main.md:37`, `requirements:67`, `review-change:61-62,87`, `review-security:68` | small | **`rules/core.md`** | role names differ: `review` (review-change, needed by `merge_pr.py`) vs `reviewer` (`review-security/SKILL.md:68`); no file owns the role vocabulary (misleading, low) |
| 16 | Ready/requirements labels `agent-ready`, `needs-spec` | `open-issue/SKILL.md:13` (owner), `requirements/SKILL.md:10-12`, `next_issue.py:10-11,230-231`, both skills' descriptions | small | **open-issue** | yes |
| 17 | Pick order (critical, high, rest, low; oldest first; spread) | `open-issue/SKILL.md:33-36`, `issue-handover/SKILL.md:95-98`, `method.md:76-87`, `next_issue.py` header | ~900 | **`next_issue.py` header** (method says so at :86) | yes |
| 18 | At most five chains | `method.md:7,72,485`, `issue-handover/SKILL.md:222` | small | **method.md §1** | yes |
| 19 | Push form: own branch, never `--force`/`+`, without `-u` | `ship-change/SKILL.md:172-174`, `local-main.md:94` | small | ship-change | yes |
| 20 | "landing mode unknown: rerun outside the sandbox" | `ship-change/SKILL.md:33-36` (owner), `local-main.md:29-30,88`, `issue-handover/SKILL.md:114-115`, `HANDOFF.md:62-64`, `landing.py` header | small | ship-change step 1 | yes |
| 21 | Opt-in parts described for the person | `docs/install.md:47-59` (step 2 list), `docs/install.md:92-101` (options table), `docs/guide.md:82-89`, the plugin descriptions | 1,001 + 692 + 1,507 | **guide.md** for the person; install.md lists options only | yes; the guards sentence is word for word in `install.md:53-54`, `guide.md:87` and the guards manifests (4x) |
| 22 | The requirements chat's issue-chat steps (title, section, worktree, archive) | `requirements/SKILL.md:18-30` and `:77-84`, `method.md` §2, §4, `archive-finished-chats` | 1,120 + ~700 | **issue-chats plugin** (requirements is a core skill restating issue-chats mechanics) | yes |
| 23 | Codex job cost measurement (pax_deorum, 13 GiB, 15.7 MiB) | `DESIGN_DECISIONS.md:69-70`, `codex-worker/SKILL.md:117-119` | ~250 | DD (a measurement in a skill against repo-docs' "name the command") | yes |
| 24 | The `<plugin>` is "the folder two levels above this skill's folder" preamble | ship-change, review-change, cleanup-merged, issue-handover, archive-finished-chats, codex-worker, review-security, check-web-deploy | ~80 each | none: each skill loads alone, so this repeat is the right cost | yes |

The audit network destinations of `audit_dependencies.py` are written three times and **disagree**
(see B6): `review-security/SKILL.md:30-34`, `check-web-deploy/SKILL.md:37-38`,
`templates/company-overlay/AGENTS.md:30-33`. Owner: **the script's header**.

### A2. Near-identical paragraphs across SKILL.md files

- `issue-handover/SKILL.md` and `method.md` repeat each other most: items 4, 12, 13 above, plus
  side chats (`SKILL.md:41-44` vs `method.md:353-385`) and the fallback (`SKILL.md:163-180` vs
  `method.md:349-351`). Together 58.6 KB, the largest pair in the repository; issue chats read
  both at the start. Proposal: SKILL.md the steps, method.md only the settings, the why and the
  measurements; drop every restated step from method.md §3-§4.
- `requirements/SKILL.md:18-30` restates what an issue chat does at start (title, sidebar,
  worktree) and `:77-84` the archive: core skill carrying issue-chats mechanics.
- `codex-issue-chats/SKILL.md:9-21` restates the lifecycle in one paragraph, then says "nothing
  here repeats them": small, acceptable.

### A3. Duplicated code

| What | Files | Size | Guard | Note |
|---|---|---|---|---|
| `landing.py` | `plugins/core/scripts/`, `plugins/issue-chats/scripts/` | 24,760 B, 492 lines, x2 | `tests/landing.py:577` byte equality | deliberate, documented in `AGENTS.md:41-42` |
| `work_proof.py` | same two folders | 11,783 B, 251 lines, x2 | `tests/chat_archivable.py:422` | deliberate, **not listed in `AGENTS.md` §One owner per fact** |
| `gitignore-secrets` | `templates/`, `plugins/security/scripts/` | 376 B x2 | `tests/repo_checks.py:186` | deliberate, documented |
| `utf16_text`, `skipped_binary`, `binary_blobs` | `security/scripts/scan_secrets.py:334-391`, `guards/scripts/pre_tool_personal_data.py:724-781` | 54 lines, identical bodies | behaviour only (`tests/pre_push_checks.py:456`) | deliberate ("installed apart"), not in AGENTS.md |
| `protected()` | `core/scripts/work_proof.py:190`, `guards/scripts/pre_tool_merge_guard.py:84` | 3-4 lines | `tests/merge_guard.py:227` | deliberate, not in AGENTS.md |
| `gh_command()` | `core/landing.py:226`, `core/work_proof.py:49`, `core/overlap_check.py:190`, `core/delete_merged_branch.py:30`, `issue-chats/next_issue.py:181`, `issue-chats/start_issue_chat.py:121` | 6 x 10 lines, identical | none | **avoidable**: `overlap_check.py` and `delete_merged_branch.py` already import `landing`; the issue-chats copy of `landing.py` sits beside the other two |
| HANDOFF.md settings reader | `landing.py:135` `settings_text`, `next_issue.py:69` `settings_text`, `context_limit.py:158-200` `settings_refs`/`settings_now` | 10-40 lines each | none | three readers of "HANDOFF.md as the default branch holds it"; `context_limit.py:160-161` documents that its ref order differs from `next_issue`'s, and it reads the local branch when ahead, the other two never do |
| Table-row parser | `landing.py:147` `row` (Landing settings), `next_issue.py:84` `row_in` (Issue chats settings) | ~12 lines each | none | same loop, a different section regex; one `row(text, section, name)` would do |
| `git()` wrapper | 19 scripts, 2-7 lines each | ~70 lines | none | trivial; not worth sharing across plugins |
| `default_base` / `default_branch` | `overlap_check.py:91`, `new_worktree.py:74`; `delete_merged_branch.py:42`, `push_branch.py:146` | 9-22 lines | none | similar intent, different bodies; `landing.py` owns the landing branch |
| `strip_heredocs`, `judge_command`, `shell_script` | `pre_tool_delete_guard.py`, `pre_tool_git_guard.py`, `pre_tool_sandbox_network.py` | 14-50 lines | none | same plugin, different bodies; a shared shell-parsing module inside `plugins/guards/scripts/` is possible without crossing plugins |

Cost of the deliberate copies: 36.9 KB stored twice; every change to `landing.py` or
`work_proof.py` is a copy by hand that a test catches after the fact. Lighter mechanisms, each
keeping "an installed plugin is copied without the rest of the repository":

1. **A sync tool instead of a hand copy:** `tools/sync_copies.py` writes the copies from the
   owner (one table of owner → copies, also for the binary classifier and `protected()`), and the
   existing tests become "run the tool, then `git diff --exit-code`". Bytes unchanged, the manual
   step gone, and AGENTS.md's list becomes that table (one owner for the list too).
2. **Import the sibling at run time** where the clone is the install (the guards plugin already
   does this for `merge_landing.py`, `pre_tool_merge_guard.py:268-274`): only safe where the
   plugin always runs from the clone. `docs/install.md:279` says Claude Code loads the skills
   from the clone, but a plugin installed from a directory (`docs/install.md:511-513`) runs from
   the cache without siblings, so this needs a fallback copy anyway. Not recommended alone.
3. **Merge issue-chats' scripts into core** would remove both copies, but changes what a
   core-only install carries: an architecture choice for the maintainer.

### A4. Manifest and marketplace metadata

| Field | Places per plugin | Agree? |
|---|---|---|
| `version` | `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `.claude-plugin/marketplace.json` entry: **three**, not four | yes (6 plugins) |
| `description` | both manifests, Codex `interface.shortDescription`, Claude marketplace entry: four | yes, word for word |
| `keywords`, `author`, `homepage`, `repository`, `license` | both manifests and the Claude marketplace entry: three | yes |

17.8 KB of JSON over 14 files. `.agents/plugins/marketplace.json` carries no version or
description at all, so `AGENTS.md:28-32` ("in both marketplace files ... the four places") is
**wrong**: the test (`tests/repo_checks.py:133-139`) compares three. The guards plugin has a
`.codex-plugin/plugin.json` (1,367 B) although `tests/repo_checks.py:145` keeps it out of the
Codex marketplace and Codex never installs it (`docs/install.md:402`): dead metadata the test
still requires (`repo_checks.py:133`). Lighter: let the marketplace entries hold only `name`
and `source` (and `version` if Claude Code needs it there) and have `repo_checks.py` derive the
rest from `plugin.json`; whether Claude Code's marketplace accepts entries without
`description` and `keywords` was not checked here.

## B. Drift

| # | Severity | Where | What | Fix |
|---|---|---|---|---|
| B1 | wrong | `HANDOFF.md:3` | "Checked on 2026-11-11", but the State describes #98 (merged 2026-11-22), #108 (2026-11-21), #116, #82 (2026-11-22). repo-docs' own check: the date matches the content (`repo-docs/SKILL.md:47`). | rewrite the line with the real date; drop the list of issues from it |
| B2 | wrong | `AGENTS.md:28-32` | version "in both manifests and in both marketplace files ... the four places agree": the Codex marketplace has no version; three places | "in both manifests and in `.claude-plugin/marketplace.json`" |
| B3 | wrong | `docs/install.md:105-106` | "A second plain run ... never removes a plugin" contradicts `install.md:401` and `tools/installer.py` docstring ("an install or --update without Codex in the plan removes it again") | add the exception or point to step 8 |
| B4 | wrong | `plugins/core/skills/repo-docs/SKILL.md:25-26` | a repository skill goes in `.agents/skills/<name>/SKILL.md` with `.claude/skills/<name>` a symlink: Codex's layout stated as the rule in a shared skill, while `skill-standard.md:57-59` (fixed in 8821002) says Claude Code reads `.claude/skills` and "that client's rules say which" folder is the link, and `rules/codex.md:14-16` owns the Codex side. A Claude-only user is told to build Codex's folder. | repo-docs: `.claude/skills/<name>/SKILL.md`, pointing to skill-standard.md for other clients |
| B5 | wrong | `install.sh:5-7`, `install.ps1:4-6` | option lists lack `issue-chats`, `--guards sandbox,gcloud`, `--codex`; "(README)" names the old entry point. Open issue #93 tracks it. | as #93 |
| B6 | wrong | `templates/company-overlay/AGENTS.md:30-33` vs `review-security/SKILL.md:30-34` | the overlay says the audit sends to "the PyPI registry" on every run; the script contacts pypi.org only in `latest()`, the `--upgrades` lookup (`audit_dependencies.py:45-46,371-377`), as review-security says. The overlay overstates (the safe direction) in the file a company signs off on. | one list in the script header; both point to it |
| B7 | misleading | `plugins/core/skills/review-change/SKILL.md:10-11` | "Under a standing grant `merge_pr.py` merges on it": since #26 automatic merging is the repository's `automatic merge` row, not a grant (`DESIGN_DECISIONS.md:210-214`) | "Where automatic merging is on" |
| B8 | misleading | `plugins/issue-chats/skills/issue-handover/method.md:364` | side chat merged "by `merge_pr.py` where a standing grant allows it": same stale term as B7 | same fix |
| B9 | misleading | `plugins/core/skills/repo-docs/skill-standard.md:49` | "Twelve skills at 1024 characters ... at 500, 6,000": there are 14 skills (12 without the codex plugin); at 500, 7,000 | state the count as "every skill" with the formula, or update |
| B10 | misleading | `AGENTS.md:39-44` | "One owner per fact" lists two deliberate copies; `work_proof.py` (twice), the binary classifier (scan_secrets / personal-data guard) and `protected()` (merge guard) are copies too; the Codex rules are owned by three files (`git-safety.rules`, `delete-guard.rules`, `gcloud.rules`), not one | one table of copies (A3 option 1) |
| B11 | misleading | `DESIGN_DECISIONS.md:3` vs `:146` | "newest first", but the 2026-11-22 entry *Model and animation chats* sits between two 2026-11-17 entries (placed by the one it narrows) | move it to the top, or state the order rule ("a narrowing entry follows its parent") |
| B12 | misleading | `issue-handover/SKILL.md:104-106`, `method.md:406-408` vs `overlap_check.py:268` | skills: an overlapping branch older than 7 days is a reason to pick another issue; the script's `--days` default 14 hides (counts, does not list) branches older than 14 days, so the 7-day rule only ever sees 7-14-day-old branches and a stale 30-day branch is invisible | pass `--days 7` in the skill, or state the 14-day cut |
| B13 | misleading | `plugins/issue-chats/.claude-plugin/plugin.json:4` (and Codex manifest, marketplace) | "archives itself once its work is on GitHub": since #26 a chat stays until its pull request is merged and cleaned up | "...sees its pull request through to the merge, then archives itself" |
| B14 | misleading | `plugins/core/.codex-plugin/plugin.json:23` | longDescription "an explicit yes before every push": not under a standing grant (#26) | "a yes before every push a standing grant does not cover" |
| B15 | misleading | `DESIGN_DECISIONS.md:299-302` | "this repository grants nothing ... the maintainer's grant is in a private overlay": automatic merging is on here now (`HANDOFF.md:150`); the entry is marked narrowed, but this sentence reads as current | mark "superseded by 2026-11-11" inline |
| B16 | misleading | `docs/install.md:19`, `install.sh:22` | "Python 3.8 or newer": every script parses with the 3.8 grammar and uses `from __future__ import annotations` where needed (checked by AST), but CI runs 3.12 only (`.github/workflows/ci.yml:24`), so 3.8 is unproven | a 3.8 job, or say "tested on 3.12" |
| B17 | misleading | `HANDOFF.md:7-8` | "each version lives in its manifests": also in the Claude marketplace entry | point to AGENTS.md's rule |
| B18 | misleading | `review-security/SKILL.md:68` vs `review-change/SKILL.md:87` | roles `reviewer` vs `review` (see A1 #15) | one vocabulary in `rules/core.md` or review_verdict.py |

Checked and true: `rules/core.md` 7,969 B (under 8,000, `tests/skills_format.py:17,37`; 31 B
headroom), `rules/codex.md` 1,151 B (under 2,000, `skills_format.py:32,130`), `AGENTS.md` 51
lines (under 100), `HANDOFF.md` 171 lines (under 200), six plugins, 14 skills, every skill in
`tests/skill_triggers.json` (14 of 14), every test named in `HANDOFF.md` exists,
`claude plugin validate --strict` exists, `tests/skill_triggers.py --client`,
`tests/installer.py --real`, `run_all.py --require-all` exist, exit codes of `push_branch.py`,
`merge_pr.py`, `review_verdict.py`, `overlap_check.py`, `landing.py`, `next_issue.py`,
`start_issue_chat.py` match what the skills say, the installer's statuses, exit codes, `--update`
/ `--uninstall` exclusions and `no client found` / `plugins not installed` lines match
`docs/install.md` steps 3, 6, 7, the four installer options tables are checked by
`repo_checks.py`, all context-limit numbers agree, label defaults agree with `next_issue.py` and
`question_label.py`.

## C. The documents' own weight

| Document | Bytes | Current state | History or restated design | Must an agent read it? |
|---|---|---|---|---|
| `HANDOFF.md` | 14,318 | Build/test (665), reading table (3,143), settings (1,224) | §State 9,011 B (63%): each bullet is a summary of a DD entry or a script header, with issue numbers, measurement dates and "measured live in ..." notes (e.g. :73-77, :107-108, :52) | yes, every change here; the State bullets could shrink to one line each with a pointer |
| `DESIGN_DECISIONS.md` | 24,688 | 15 rulings, all binding | Why-paragraphs carry review history (e.g. `:59-77` five reviews of #105, the three-review read-deny story, 4,060 B entry); two entries narrowed by later ones (2026-11-09 by 11-11; 11-17 by 11-22) kept whole | only the entry for the work at hand (repo-docs: decisions are read when relevant); an index (#66) and moving superseded text to an archive would cut what is read |
| `docs/install.md` | 33,521 | steps 1-7 | §8 Codex 8,995 B (27%), of which *Codex as the worker* 6,501 B restates `codex-worker` and `codex_worker.py`; the gcloud set-up walk-through 2,290 B is Google's procedure, not the installer's; *What the installer changes* restates the docstring the guide says owns it (`install.md:8-10`) | the installing agent reads all of steps 1-7 once per install; §8 only with Codex (already gated) |
| `docs/guide.md` | 10,700 | almost all current | little history; the daily-work bullets (:27-52) paraphrase `rules/core.md` for people, which is its purpose; the opt-in table repeats install.md step 2 | not by agents; it is for people |
| `method.md` (issue-chats) | 38,722 | settings §1 (5,008), title form, tools table | measured-version notes (`:282-301` CLI 2.1.292, "once failed ... measured again"), plus every step restated from SKILL.md (A2) | read at every issue chat's start (per DD 2026-11-22 *Why*); the largest always-read file of the opt-in parts |

Repeated between them: the clones, pre-push, push grant, automatic merge and context-limit facts
each appear in HANDOFF State, a DD entry and install.md or method.md (A1 #2, #3, #5, #6, #10).

Against the repo-docs layout (`plugins/core/skills/repo-docs/SKILL.md`):

- `HANDOFF.md` "checked on" date does not match the content (B1), and the State section is
  appended to rather than rewritten (bullets end in "(#108)", "Measured live ... (#75)").
- "A measurement: name the command that produces it instead of copying the number" (`:38`):
  `HANDOFF.md:107-108` (507.8 MiB / 0.0 MiB), `codex-worker/SKILL.md:118-119`, DD copies.
- No `docs/design/`: the design of record lives in script headers (named as owners in HANDOFF's
  reading table) and in method.md. That is a coherent choice for a scripts repository, but
  repo-docs does not name "a script's header" as a home, so HANDOFF and DD restate the headers.
  Either add that row to repo-docs' table or accept the restatements as the cost.
- No `ROADMAP.md`, no `archive_implementations.md`, no `docs/archive/`: optional in the layout.
- `AGENTS.md` follows the layout (51 lines, its deviations named, "None").
- Open issues already cover part of this: #65 (one owner per ruling, HANDOFF links instead of
  restating), #66 (decision index and archive rule), #74 (question-label default), #93
  (install script headers).

## Not checked

- Whether every sentence of `checklist.md`, `sources.md` (security) and the web-deploy reference
  files matches its sources; only their paths and links were checked.
- Whether Claude Code's marketplace accepts entries with only `name` and `source` (A4).
- The claims in `HANDOFF.md` State about live runs (pax_deorum merges, #61/#69): taken as written.
- Behaviour under Python 3.8 (no 3.8 interpreter here; only the grammar was checked).
- The tests' assertions themselves: only that the suite runs.

Test run: `python3 tests/run_all.py` in this worktree, inside Claude Code's sandbox: 32 of 33
passed, exit 0; `start_issue_chat.py` skipped (no pseudo-terminal: 41 refusal cases ok, 21 cases
that open a chat not run), as `HANDOFF.md:115-116` describes.
