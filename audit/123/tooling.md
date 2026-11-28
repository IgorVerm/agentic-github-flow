# Audit #123: tooling

What the person who installs and uses agentic-github-flow meets, and how maintainable the code
is: the installer and its documents, the scripts, the guards, the tests and CI, versioning, and
dead parts. Base: the worktree of `agent/123-audit` at `e27f84f` (origin/main), measured
2026-11-22 on macOS (Darwin 27.2, Python 3 from PATH), inside Claude Code's Bash sandbox.
"Measured" means a command below produced the number; "estimate" is labelled.

Read-only: nothing was installed, committed or posted. Scratch scripts lived in the session's
scratchpad (`$TMPDIR`), not in the repository.

## 1. Install experience

### The path in numbers

| Item | Count | Source |
|---|---:|---|
| Ways in | 2: ask an agent to follow `docs/install.md` (README), or `install.sh` / `install.ps1` | `README.md:13-18` |
| Shell commands the person runs | 1 (clone and `install.sh <options>`), done by the agent | `docs/install.md:74-84` |
| Requirement checks | 4 (git, Python 3.8+, a client, `gh auth status`) | `docs/install.md:16-21` |
| Decisions asked before install | 5 (machine type, overlays, opt-in parts with 6 options, clients, work identity) | `docs/install.md:36-70` |
| Installer flags | 10 public + 1 hidden (`--resume-update`) | `tools/installer.py:968-984` |
| Verify steps | 5 for Claude Code, 4 more for Codex; 2 need a fresh session the person starts by hand (`docs/install.md:158-164`), 1 needs `/hooks` trust in Codex by hand (`:417-418`) | `docs/install.md:152-170, 415-423` |
| Optional settings the person or agent edits by hand afterwards | about 14 machine-level (3 personal-data files, `sandbox.excludedCommands`, `sandbox-scripts`, 3 allow rules for the issue-chat scripts in 2 spellings each, the archive allow rule, `AGENTIC_GITHUB_FLOW_CLONES`, the Codex-worker allow rule and exclusion, 4 gcloud set-up steps) | `docs/install.md:172-313, 495-500` |
| Per-repository manual steps | 5 (copy `pre-push`, `.gitignore` block, `## Landing settings`, the push-grant line, `## Issue chats settings`) | `docs/install.md:315-355` |
| Bytes an installing agent reads | `docs/install.md` 33,521 + installer docstring 5,010 (named as the owner, `docs/install.md:8-10`) + optionally `docs/guide.md` 10,700; about 9.6k tokens at 4 bytes/token (estimate) before it runs anything | `wc -c`; `ast.get_docstring` |
| `install.py --help` output | 1,349 bytes | `python3 tools/installer.py --help \| wc -c` |

### Who reads `docs/install.md`

It is written for the installing agent (`docs/install.md:1-6`; `README.md:14`), and an agent
reads all 33.5 KB once per install or update question. Its sections by size
(`awk` over `^##` headings):

| Section | Bytes | Needed by |
|---|---:|---|
| 8. Codex as the worker | 6,501 | only Codex users of issue chats; restates the header of `codex_worker.py` (13.7 KB docstring), which owns it |
| 5. The Google Cloud guard | 4,017 | only `--guards gcloud`; 2.4 KB of it is a gcloud CLI how-to (`:237-267`) |
| 2. Ask the decisions | 2,980 | everyone |
| Per repository | 2,552 | everyone, later, per repository |
| 3. Clone and install | 2,306 | everyone |
| What the installer changes | 1,818 | everyone |
| What the installer changes for Codex | 1,738 | Codex only |
| Issue chats without a click | 1,643 | issue-chats only |
| other 11 sections | 8,000 or so | mixed |

About 12.9 KB (38 %) is conditional (Codex 9.0 KB, gcloud 4.0 KB) but loaded by every
installing agent, because it is one file. Step 8 says "Read this step only when Codex is set up"
(`docs/install.md:391`), which an agent can only follow after it has already read it.

### Findings

- **No status, doctor or dry-run command.** `tools/installer.py:965-984` has `--update` and
  `--uninstall` but nothing that prints what is installed (the record in `.state/install.json`)
  or checks it still holds (plugins listed, blocks present, hooks wired, Python found by the
  hook wrapper). Verification is manual and agent-driven (`docs/install.md:152-170`).
- **Failures reported as success.**
  - `--update`: a failed `claude plugin marketplace update` prints `FAIL` but is not added to
    `failures`, so the last line is `done` and the exit code 0 (`tools/installer.py:297-299`).
    Installed copies then stay on the old version without the summary saying so.
  - `--uninstall` always ends `done` and exits 0, even when a plugin or marketplace removal
    printed `FAIL` or the client command is gone (`tools/installer.py:331-340, 908-927`).
- **No partial removal.** A plain rerun only adds; dropping one plugin or the guards means
  `--uninstall` and a full reinstall (`docs/install.md:105-108`).
- **Stale shell headers.** `install.sh:2-6` and `install.ps1:2-6` call the clone-and-run line
  "The one command (README)", but README no longer has it (it tells the person to ask an agent,
  `README.md:15-17`), and the option list omits `--codex`, `issue-chats` in `--with` and the
  `--guards sandbox,gcloud` extras that `tools/installer.py:8-10` documents.
- **The hook wrapper can fail open silently.** `plugins/guards/scripts/run-python.sh:13-14`
  prints one stderr line and exits 0 when no Python 3.8+ is found: every guard is then off, and
  nothing in a verify step catches it except the scratch `git reset --hard` test, which the deny
  list also passes.
- **How a person learns what the plugins do:** `docs/guide.md` §Opt-in parts (a good 6-row
  table, `docs/guide.md:77-89`). It does not say what the guards cost per tool call (section 2
  below).
- **README** (1,319 bytes) orients in under a minute: what it is, how to install, where to read
  on. It does not list the six plugins in one line each; the guide does.

## 2. Scripts

### Size, comments, tests

33 Python files in `plugins/*/scripts/`, 17,392 lines, 836,274 bytes (two of them byte-identical
copies). Command: an `ast`/`tokenize` pass (`$TMPDIR/stats.py`): comment+doc % counts comment
lines and docstring lines over all lines; code lines exclude those and blank lines; test lines
are the test file(s) that exercise the script.

| Script | Lines | Bytes | Comment+doc % | Functions | Code lines | Test file(s) | Test lines | Test/code |
|---|---:|---:|---:|---:|---:|---|---:|---:|
| guards/pre_tool_delete_guard.py | 2057 | 93578 | 19 | 93 | 1476 | delete_guard, delete_guard_cases, delete_guard_differential | 624 | 0.42 |
| guards/pre_tool_sandbox_network.py | 1338 | 63936 | 17 | 53 | 985 | sandbox_network_guard | 507 | 0.51 |
| codex/codex_worker.py | 1199 | 58499 | 22 | 46 | 809 | codex_worker | 1067 | 1.32 |
| core/remove_merged_worktree.py | 975 | 52162 | 25 | 28 | 653 | worktree_tools (shared) | 1053 | (shared) |
| guards/pre_tool_personal_data.py | 1016 | 49337 | 20 | 48 | 699 | personal_data_guard, pre_push_checks (shared) | 415+ | 0.59+ |
| security/audit_dependencies.py | 966 | 47342 | 13 | 54 | 721 | audit_dependencies | 819 | 1.14 |
| codex/codex_tools.py | 843 | 41003 | 19 | 36 | 599 | codex_tools | 485 | 0.81 |
| security/scan_secrets.py | 589 | 27816 | 16 | 24 | 426 | scan_secrets | 268 | 0.63 |
| core/merge_landing.py | 561 | 27769 | 19 | 21 | 400 | merge_landing | 700 | 1.75 |
| core/merge_pr.py | 502 | 26588 | 18 | 13 | 366 | merge_pr | 477 | 1.30 |
| issue-chats/context_limit.py | 511 | 25055 | 22 | 27 | 335 | context_limit | 446 | 1.33 |
| core/landing.py (+ identical copy in issue-chats) | 492 | 24760 | 20 | 18 | 339 | landing | 582 | 1.72 |
| issue-chats/start_issue_chat.py | 442 | 22289 | 21 | 17 | 306 | start_issue_chat | 477 | 1.56 |
| guards/pre_tool_git_guard.py | 524 | 22182 | 11 | 18 | 419 | git_guard (+ differential) | 171+ | 0.41 |
| core/new_worktree.py | 374 | 18818 | 19 | 11 | 266 | new_worktree | 426 | 1.60 |
| guards/pre_tool_merge_guard.py | 389 | 18616 | 21 | 16 | 266 | merge_guard | 277 | 1.04 |
| issue-chats/chat_archivable.py | 334 | 17638 | 25 | 11 | 215 | chat_archivable | 431 | 2.00 |
| core/push_branch.py | 331 | 17397 | 21 | 7 | 234 | push_branch | 364 | 1.56 |
| core/overlap_check.py | 397 | 17157 | 14 | 18 | 290 | overlap_check | 328 | 1.13 |
| issue-chats/question_label.py | 362 | 15893 | 19 | 18 | 243 | question_label | 292 | 1.20 |
| codex/codex_job.py | 329 | 14395 | 17 | 12 | 230 | via codex_worker | - | - |
| core/promote_main.py | 269 | 13572 | 20 | 8 | 183 | promote_main | 198 | 1.08 |
| issue-chats/archive_guard.py | 254 | 13027 | 30 | 8 | 151 | archive_guard | 272 | 1.80 |
| issue-chats/next_issue.py | 272 | 12380 | 19 | 15 | 179 | next_issue | 293 | 1.64 |
| codex/codex_import.py | 251 | 12297 | 20 | 9 | 175 | via codex_worker | - | - |
| core/work_proof.py (+ identical copy in issue-chats) | 251 | 11783 | 23 | 13 | 163 | via chat_archivable, merge_landing | - | - |
| core/review_verdict.py | 274 | 11423 | 18 | 11 | 189 | review_verdict | 218 | 1.15 |
| core/clone_dedupe_worktree.py | 235 | 9340 | 20 | 12 | 154 | via new_worktree | - | - |
| core/delete_merged_branch.py | 147 | 6448 | 14 | 5 | 112 | via worktree_tools, landing | - | - |
| core/push_paths.py | 85 | 3968 | 27 | 3 | 48 | via pre_push_checks (env `AGENTIC_GITHUB_FLOW_UNASKED_PUSH`) | - | - |
| issue-chats/handover_note.py | 80 | 3263 | 21 | 4 | 52 | via archive_guard | - | - |

Module docstrings alone are 145,976 bytes across these files (largest: `codex_worker.py` 13,730,
`pre_tool_delete_guard.py` 11,558, `remove_merged_worktree.py` 11,021). They are the declared
owners of behaviour ("its header owns …"), and documents send agents to read them
(`docs/install.md:192-193, 210-211, 344-345, 352, 474`): each such read costs 2-3.5k tokens
(estimate, 4 bytes/token).

**Accumulated special cases.** `pre_tool_delete_guard.py` is a small shell interpreter: 93
functions, 45 top-level constants, a 150-line `lex`, option tables for `xargs`, `find` and others
(`plugins/guards/scripts/pre_tool_delete_guard.py:144` onward). `pre_tool_sandbox_network.py`
holds 30 constants and per-program rewrite logic (`rewrite_gh` 93 lines, `judge` 114, `scan`
106). Both have the lowest test/code ratios of the large scripts (0.42 and 0.51), while being
the ones where a false positive stops work.

### Copy-pasted helpers

Command: `$TMPDIR/dups.py` (an `ast` pass grouping functions by name and by identical body,
leaving out the two byte-identical files).

| Helper | Copies | Lines in total | Where |
|---|---:|---:|---|
| `git(...)` wrapper | 19 scripts | 74 | 12 in core alone (`landing.py:120`, `merge_landing.py:67`, `merge_pr.py:109`, `new_worktree.py:60`, `overlap_check.py:80`, `promote_main.py:49`, `push_branch.py:86`, `push_paths.py:34`, `review_verdict.py:105`, `work_proof.py:29`, `clone_dedupe_worktree.py:30`, `delete_merged_branch.py:26`) |
| `gh_command()` | 6, byte-identical bodies | 61 | `delete_merged_branch.py:30`, `landing.py:226`, `overlap_check.py:190`, `work_proof.py:49`, `next_issue.py:181`, `start_issue_chat.py:121` |
| `gh(...)` | 6 | 57 | `merge_pr.py:114`, `overlap_check.py:202`, `push_branch.py:91`, `review_verdict.py:110`, `next_issue.py:193`, `question_label.py:81` |
| HANDOFF.md settings readers (`settings_text`, `row`, `label_value`, `chat_limit`) | 13 scripts mention a settings section | - | `landing.py:135`, `next_issue.py:69`, plus readers in context_limit, question_label, push_paths, merge_pr |
| binary/UTF-16 diff reading (`binary_blobs`, `utf16_text`, `skipped_binary`) | 2, identical | 54 | `pre_tool_personal_data.py:724-745` and `scan_secrets.py:334-355` (different plugins: a deliberate twin, `pre_tool_personal_data.py` comment before `FIRST_FEW_BYTES`) |
| shell parsing (`strip_heredocs`, `judge_command`, `shell_script`) | 2-3 | 148 | git guard, delete guard, sandbox-network guard |
| Whole files | 2 byte-identical copies | 743 | `issue-chats/scripts/landing.py`, `issue-chats/scripts/work_proof.py` (36.5 KB) |

Identical bodies across scripts: 120 duplicate lines beyond the first copy. Same-named helpers
with small differences: about 190 lines. The 12 `git()` wrappers in core differ in behaviour,
not only in spelling: five return a `CompletedProcess`, three return stdout text, one bytes,
two raise on failure; only five pass `encoding='utf-8', errors='replace'` and `stdin=DEVNULL`
(`merge_landing.py:67` adds `--literal-pathspecs`). On Windows the others decode git output
with the locale code page.

**Is a shared module per plugin possible?** Yes, and the pattern is already in use:
`landing.py` is imported by 9 core scripts, `work_proof.py` by 3, `next_issue.py` by 2 in
issue-chats, and the guards load the git guard with `importlib` (grep of `^from|^import`). An
installed plugin is copied whole, so sharing inside a plugin is safe; across plugins the
repository already uses copy + identity test (`tests/chat_archivable.py:422` for
`work_proof.py`, `tests/landing.py` for `landing.py`). Folding `git`/`gh`/`gh_command` into
`landing.py` (core) and `next_issue.py` (issue-chats) removes about 150 lines and makes
encoding and stdin uniform; the risk is behaviour change in scripts that rely on their variant
(raising vs returning), so it needs the existing tests per script, not a sweep.

`AGENTS.md` §One owner per fact names the copies of `gitignore-secrets` and `landing.py` but not
`work_proof.py`, which is copied the same way.

### Hook latency

Command: `$TMPDIR/lat.py`: each hook started exactly as `hooks.json` starts it
(`sh run-python.sh <script>`), with a PreToolUse (or PostToolUse) JSON object on stdin
(`tool_name`, `tool_input.command`, `cwd`, `session_id`, `transcript_path`), 5 runs, median in
ms. The context gate was also run against this session's real 1.2 MB transcript (state redirected
to `$TMPDIR`, gh stubbed with `AGENTIC_GITHUB_FLOW_GH='["false"]'`).

| Hook (event, matcher) | `ls -la` | `git status` | `gh pr list` | `cd x && rm -rf build && git push` |
|---|---:|---:|---:|---:|
| git guard (Pre, `Bash`) | 62 | 64 | 62 | 53 |
| merge guard (Pre, `Bash`) | 72 | 68 | 68 | 79 |
| delete guard (Pre, `Bash`, `run_in_terminal`) | 81 | 102 | 112 | 90 |
| personal-data guard (Pre, `Bash`, web, Artifact, every `mcp__*`) | 121 | 109 | 107 | 148 |
| sandbox-network guard (Pre, `Bash`, opt-in, no wrapper) | 68 | 71 | 84 | 80 |
| question_label.py (Post `Bash`/`AskUserQuestion`, UserPromptSubmit) | 78 | 78 | 80 | 79 |
| context-gate.sh (Pre and Post, every tool), outside an issue-chat branch | 20 | | | |
| context-gate.sh in an `agent/<n>-…` branch, real 1.2 MB transcript | Pre 190-235 (first call 777), Post 160-180 (includes ~25 ms of the timing probe) | | | |

Baselines: `python3 -c pass` 24 ms; the version check `run-python.sh` and `run-hook.sh` run
before every guard (`python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))'`) 23 ms;
`git branch --show-current` 15 ms. The same guard started directly with `python3 -I` instead of
through the wrapper: git guard 36 ms (62 through the wrapper), delete guard 51 (81),
personal-data guard 58 (121).

Per tool call, with core + guards + issue-chats installed:

| Tool call | Processes started | Python starts | CPU time added (sum) | Wall time if hooks run in parallel |
|---|---:|---:|---:|---:|
| Bash, ordinary session | Pre 5, Post 2 | 10 | Pre ~355 ms + Post ~100 ms | Pre ~120-150 ms, Post ~80 ms |
| Bash, issue-chat branch | Pre 5, Post 2 | 14 | Pre ~550 ms + Post ~260 ms | Pre ~200-235 ms, Post ~180 ms |
| Bash with `--guards sandbox` | +1 Pre | +1 | +70-85 ms | unchanged (not the slowest) |
| Edit / Write / Read, ordinary session | 2 (context gate) | 0 | ~40 ms | ~20 ms each side |
| Edit / Write / Read, issue-chat branch | 2 | 4 | ~350-400 ms | ~180-235 ms each side |
| any `mcp__*` call | +1 Pre (personal-data) | +2 | ~120 ms | ~120 ms |
| each prompt the user sends | 1 (question_label) | 2 | ~78 ms | ~78 ms |

The parallel column assumes Claude Code runs the matching hooks of one event in parallel, as its
hooks documentation states; that was not measured here. The wrapper's version check is a second
Python start for every guard: about 23 ms × 4 = ~90 ms CPU per Bash call that buys nothing once
Python was found (measured above).

### What the guards print when they block

| Guard, input | Exit | Bytes into context |
|---|---:|---:|
| git guard, `git reset --hard` / `push --force` / `clean -fd` / `branch -D` | 2 | 268-273 |
| delete guard, `rm -rf ~/Documents` (ask) | 0 + JSON | 537 |
| delete guard, `rm -rf "$X"` (ask) | 0 + JSON | 576 |
| personal-data guard, `curl -d "to=<address>" https://example.org` (ask) | 0 + JSON | 325 |
| sandbox-network guard, `cd … && gh …` (seen in this session) | 2 | about 650 |
| context limit at the decision point | 2 | about 600 (`context_limit.py:466-472`) |

Small and actionable. Claude Code adds a line naming the plugin.

### Interface consistency

| Aspect | State |
|---|---|
| `--help` | 15 of 31 distinct scripts answer it; 9 print the module docstring (1,085-6,245 bytes: `audit_dependencies.py` 6,245, `merge_pr.py` 5,236, `push_branch.py` 4,656, `landing.py` 4,637), 6 print an argparse usage of 346-632 bytes. `merge_landing.py`, `work_proof.py`, `push_paths.py`, `codex_job.py`, `codex_import.py`, `codex_tools.py`, the issue-chats hooks and `pre_tool_personal_data.py` have no `--help`; the git, merge and sandbox-network guards read stdin and print nothing (command: `python3 -I <script> --help \| wc -c`, only on scripts whose source handles `--help` or uses argparse) |
| Argument parsing | 6 scripts use `argparse`, 25 parse `sys.argv` by hand |
| `--json` | only `audit_dependencies.py` offers it; the other `--json` strings in the scripts are gh's own flag |
| `--dry-run` | in 5 (merge_pr, push_branch, review_verdict, remove_merged_worktree, delete_merged_branch) |
| Exit codes | the installer and most scripts: 0 done, 1 failed, 2 usage, 3 refused (`tools/installer.py:65`); hooks: 2 block (git, merge, context limit) or 0 + JSON ask/deny (delete, personal-data, sandbox-network refuse with exit 2). Documented per script header, not in one place |
| Hook failure mode | guards and question/context hooks fail open (`run-python.sh:13-14`, `run-hook.sh`); the archive guard fails closed (`run-guard.sh`). Deliberate and documented |

## 3. Guards

### Enforced twice or more

| Rule (`rules/core.md` §Git) | Claude deny/ask list | git guard hook | Codex `.rules` | `templates/pre-push` |
|---|---|---|---|---|
| no force-push, no `--mirror`/`--prune`/`+ref` | deny | yes | forbidden | refuses non-fast-forward |
| no tag delete or move | deny | yes | forbidden | refuses tag moves |
| no `reset --hard`, rebase, filter-branch/repo, reflog expire, `gc --prune` | deny | yes | forbidden | - |
| no discarding work (`restore`, `checkout --`, `clean`, `stash drop`, `switch -f`) | deny | yes | forbidden | - |
| no `--no-verify`, `commit -n`, `core.hooksPath` | deny | yes | forbidden | (bypassed by it) |
| no git config changes | deny | yes (also `gh config`) | forbidden | - |
| no `worktree remove` by hand | deny | yes | forbidden | - |
| stage by path (`add -A`, `add .`, `add -f`, `commit -a`) | deny | yes | forbidden | - |
| ask before every push | ask (`git push*`, `git -C * push*`) | - | prompt | - |
| personal data off the machine | - | personal-data hook | personal-data hook (deny) | personal-data check |
| no secrets committed | `Read(.env…)` deny | - | - | secret scan |

The deny list (`plugins/guards/policy/claude-permissions.json`, 167 deny + 31 ask entries, plus 4 deny + 10 ask under `gcloud`) and
the git guard cover the same commands; the guard exists because prefix rules miss spellings
(`pre_tool_git_guard.py:4-9`). Almost every git entry is written twice, plain and as `git -C *`.
The double layer is cheap for Claude (rule matching costs nothing at run time) and keeps the
refusal when Python is missing.

### Core rules without enforcement

- "Work on a branch in a worktree, never directly on `main`": nothing refuses a commit on `main`.
- "Never commit a file over 50 MB": no size check in `pre-push`, `scan_secrets.py` or the guards
  (grep for `50 MB|50MB|50_000|MAX_FILE`: only the personal-data guard's 2 MB read limit).
- Commit subject ending in `(#n)`, the `Co-Authored-By` trailer, signed comments: unchecked
  (`review_verdict.py` checks only its own verdict format).
- "Ask before a push" in a repository without the per-repository `pre-push` copy rests on the
  ask rule alone; installing `pre-push` is a manual step per repository (`docs/install.md:320`).

### False positives seen in code, tests and this session

- **New, measured:** the git guard refuses a here-document written to a file with `cat` when
  its body holds a brace pair with a comma and the word `git` anywhere in the call, for example
  a Python dict literal and a `subprocess.run(['git', …])` line. The brace check runs on the
  whole text before here-document bodies are set aside: `pre_tool_git_guard.py:412-414`
  (`brace_expansion(text) and may_run_git(text)` before `strip_heredocs`). Reproduced with
  `--check` on `cat > f <<'EOF'` / `d={'a':1,'b':2}` / `x='git'` / `EOF` → exit 2 "uses brace
  expansion". It blocked this audit's first latency script. Not on #118 or #122.
- #118 lists merge-guard false refusals (item 5: `git merge @{u}` with an excluded
  `git merge:*`, `pre_tool_merge_guard.py` `sandboxed()` splitting on `{}`) and misses.
- #122 is the sandbox-network guard's `git -C <dir> push|fetch|pull` gap (a miss, not a false
  positive).
- Common delete commands pass the delete guard without a prompt (`rm -rf node_modules`,
  `rm -rf "$TMPDIR/x"`, `find . -name '*.pyc' -delete`, `rm -r dist build`, `git rm -r --cached`),
  measured with JSON on stdin.

### Open follow-ups (so proposals do not collide)

- #122 (open, claimed): `pre_tool_sandbox_network.py`, `tests/sandbox_network_guard.py`, guards
  version. Any refactor of that guard waits for it.
- #118 (open, low): `pre_tool_merge_guard.py` `git_merge()`, `merge_landing.py` `in_the_way`.
- #115 (open): `codex_worker.py` `lock()`, `sweep_jobs()`. Its body names
  `plugins/issue-chats/scripts/codex_worker.py`, which moved to `plugins/codex/scripts/` in #98:
  the paths in the issue are stale.

## 4. Tests and CI

### The offline suite on this machine

Command: `time python3 tests/run_all.py` in the worktree, inside Claude Code's sandbox.

**32 of 33 passed, 1 skipped, none failed; wall time 13 min 6 s** (`332.5 s user, 243.1 s
system, 73 % cpu, 13:05.79 total`). The run is serial; per-file times sum to the total.

| Slowest files | Seconds |
|---|---:|
| `worktree_tools.py` | 109.3 |
| `merge_pr.py` | 59.4 |
| `codex_worker.py` | 55.8 |
| `merge_landing.py` | 50.7 |
| `delete_guard_differential.py` | 49.6 |
| `delete_guard.py` | 48.9 |
| `chat_archivable.py` | 40.2 |
| `push_branch.py` | 39.3 |
| `landing.py` | 36.2 |
| `pre_push_checks.py` | 33.8 |

Skips on this machine (all caused by running inside Claude Code's sandbox, by their own
messages):

- `start_issue_chat.py` skipped as a file (exit 77): "`script` cannot open a terminal here, so 21
  case(s) that open the chat did not run; 41 refusal case(s) ok". CI with `--require-all` would
  fail on this, so CI must have a terminal for `script`.
- Partial skips inside files that reported `ok`: `new_worktree.py` (skipped=5),
  `merge_guard.py` (skipped=1), `codex_tools.py` ("offline only (sandbox-exec cannot run here)").
  `run_all.py` counts these as passed; `--require-all` does not see a skip inside a file.

Case counts the files report: git guard 136 blocked / 99 allowed; personal-data 33 asked / 25
passed (+ Codex 39 / 25); delete guard 252 asked / 91 passed; differential: 343 cases, 817
probes, 38,364 generated commands; sandbox-network 260 / 260; codex policy 187 / 187; archive
guard 55 / 55; plugin validate 12 / 12. `personal_data_guard.py` already prints a timing line
(python start 0.02 s, later hook calls median 0.09 s, max 0.18 s): the only latency measurement
in the suite, and it asserts nothing about it.

### Inventory

| Item | Count | Source |
|---|---:|---|
| Test files run by `run_all.py` | 33 | `tests/run_all.py:14-23` |
| Helpers and data, not run on their own | `delete_guard_cases.py`, `unknown_mode.py`, `skill_triggers.json`, `fixtures/` | grep |
| Live test, not in the gate | `skill_triggers.py` (spends tokens) | `tests/run_all.py:5-6` |
| `def test…` methods | 468 (some files are plain scripts with their own cases) | `grep -c "def test"` |
| Test lines | 13,480 | `wc -l tests/*.py` |
| Largest suites | `worktree_tools.py` 1,053 lines / 55 tests, `codex_worker.py` 1,067, `installer.py` 848 | `wc -l` |
| CI | one job, matrix ubuntu/macos/windows, Python 3.12, Node 22, installs `@anthropic-ai/claude-code@2.1.292` and `@openai/codex@0.164.0`, runs `run_all.py --require-all` | `.github/workflows/ci.yml` |
| CI wall time, last main push | ubuntu 5m52s, macOS 11m44s, Windows 15m34s | `gh run view 45049467515 --json jobs` |
| CI runs, last 10 | 6 success, 4 failure (all on `agent/116-codex-tools`) | `gh run list --limit 10` |

`run_all.py` runs the files one after another (`tests/run_all.py:29-36`); the files are
independent processes, so a parallel runner would cut wall time to roughly the slowest file
(estimate, not measured).

### Gaps

- No direct test for `run-python.sh`, `run-hook.sh` (the fail-open wrappers every hook goes
  through) or for hook wiring beyond `plugin_validate.py` (39 lines).
- `codex_job.py`, `codex_import.py`, `push_paths.py`, `handover_note.py`,
  `clone_dedupe_worktree.py`, `delete_merged_branch.py`, `work_proof.py` are tested only through
  their callers.
- The largest guard (`pre_tool_delete_guard.py`, 1,476 code lines) has the lowest test/code
  ratio (0.42), though `delete_guard_differential.py` adds a differential run against the git
  guard.
- No latency gate: only `personal_data_guard.py` prints a timing, and nothing fails when a
  guard grows from 60 to 600 ms.
- A skip inside a file (`unittest` skipped=N) passes `--require-all`; only a whole-file exit 77
  counts.
- The heredoc-brace false positive above has no case in `tests/git_guard.py`.

### Context budgets that exist, and what could be added

`tests/skills_format.py` already enforces: `rules/core.md` < 8,000 bytes (`:17, 37-38`),
`rules/codex.md` < 2,000 bytes (`:32, 130-131`), each description 40-500 characters
(`:82-83`), each `SKILL.md` < 500 lines (`:90`) and its body < 5,000 tokens at
`CHARS_PER_TOKEN` (`:93-95`). These are the Agent Skills standard's ceilings, not this
repository's actual sizes, so a skill can grow several-fold before a test fails.

Possible additions (each a few lines in `skills_format.py`):

1. the sum of all skill descriptions (they load in every session) under a byte budget;
2. a per-skill byte budget set a little above today's size, raised deliberately in the same
   change that grows it (a ratchet), so growth is a visible diff;
3. a budget for each reference file a skill links to;
4. a budget for `docs/install.md` (read in full by every installing agent);
5. a ceiling on what a hook prints when it blocks (today 270-650 bytes).

## 5. Versioning friction

- The rule says four places (`AGENTS.md` §Rules: "both manifests and in both marketplace
  files"), but only three hold a version: `.agents/plugins/marketplace.json` has no `version`
  key (`grep -c version` → 0), and `tests/repo_checks.py:133-139` checks the two manifests and
  `.claude-plugin/marketplace.json`. `AGENTS.md` and #122's path list differ from the code.
- No bump script (no file under `tools/` or a plugin's `scripts/` writes versions; grep for
  `bump`). `tests/repo_checks.py:151-161` fails a changed plugin whose version did not move and
  says so, but leaves the edit to the agent.
- Over the last 100 non-merge commits (2026-11-17 to 2026-11-22): 87 touched `plugins/`, 28
  touched a manifest or marketplace file, 103 file edits in total (`git log -100 --no-merges
  --name-only`). That is three or four hand edits of a JSON version per landing, and a source of
  merge conflicts when two branches bump the same plugin.

## 6. Dead and stale parts

- **Functions never called:** none found by a name-count pass over `plugins/*/scripts`,
  `tools/` and `tests/` (a name that appears only at its `def`). Rough: dynamic calls and
  same-named functions elsewhere can hide one.
- **Scripts no skill, hook, test or doc names:** none. `push_paths.py` is named by
  `templates/pre-push` and `HANDOFF.md`; `handover_note.py` and `work_proof.py` are imported.
- **Templates:** none is installed by the installer; all four (`pre-push`, `gitignore-secrets`,
  `company-overlay/AGENTS.md`, `README.md`) are named in `docs/install.md` for manual use.
- **Stale text:**
  - `install.sh:2-6`, `install.ps1:2-6`: "The one command (README)" and an incomplete option
    list (section 1).
  - `AGENTS.md`: "both marketplace files" carry a version (only one does); its §One owner per
    fact omits the `work_proof.py` copy.
  - #115 names the old path of `codex_worker.py`.
- **Name of the maintainer in shipped scripts:** "Igor" appears in `context_limit.py` (4),
  `codex_worker.py` (4), `codex_tools.py`, `new_worktree.py`, `pre_tool_personal_data.py` (1
  each) as the source of a ruling (`grep -rc Igor plugins`). `AGENTS.md` keeps the author to
  README, NOTICE and the manifests; `tests/repo_checks.py` checks only `rules/` and skills for
  the author name (MAI-Tech), so it does not see this. For the duplication audit to judge.

## 7. Proposals, ranked by benefit against risk

| # | Proposal | Benefit | Risk |
|---:|---|---|---|
| 1 | Drop the Python version check from `run-python.sh` and `run-hook.sh`: `exec python3 -I` when `command -v python3` succeeds, and let each script check `sys.version_info` itself on start (an exit other than 2 already fails open in a PreToolUse hook) | ~90 ms CPU per Bash call (4 × 23 ms), ~23 ms wall per hook | low: one shell line per wrapper; Windows `py -3` path unchanged |
| 2 | Fix the heredoc false positive: run `brace_expansion` after `strip_heredocs` in `pre_tool_git_guard.py:412-414`, with a test case | removes a block that costs a retry round trip (a full context re-read) | low; guards version bump; coordinate with #122 (same plugin) |
| 3 | Count failed `marketplace update` and uninstall steps as failures (`tools/installer.py:297-299, 331-340, 925`) | `--update`/`--uninstall` stop saying `done` when they did not | low |
| 4 | `tools/bump_version.py <plugin> [patch|minor]` that edits the three places, and correct `AGENTS.md` to three | removes 3-4 hand edits per landing (28 of the last 100 commits) | low |
| 5 | Split `docs/install.md`: the common path (~20 KB) and `install-codex.md` / the gcloud set-up beside it, or point the Codex-worker section to `codex_worker.py`'s header instead of restating it | ~13 KB (~3k tokens, estimate) less for every Claude-only install | low; links and `repo_checks.py` option scan need updating |
| 6 | An `install.sh --status` (or `--check`) that prints the record and checks plugins, blocks, hooks and Python | replaces most manual verify steps; a person can see what is installed | low-medium: new code path in a 48 KB installer |
| 7 | Tighter context budgets in `skills_format.py` (sum of descriptions, per-skill ratchet, install.md) | token cost cannot creep back unseen | low; needs today's sizes as the start values |
| 8 | Run `run_all.py` files in parallel (a pool of N processes) | local and CI wall time towards the slowest file | low-medium: tests that share `$HOME`-like state must be checked |
| 9 | Fold `git`/`gh`/`gh_command` into `landing.py` (core) and `next_issue.py` (issue-chats) | ~150 lines, uniform UTF-8 and stdin handling on Windows | medium: wrappers differ in raising vs returning; per-script tests needed |
| 10 | Skip the context gate's Python start on events it cannot act on (PreToolUse below the decision point needs the transcript read; consider caching the last context per session in the state file and reading only the transcript tail grown since) | ~150-200 ms per tool call in issue chats | medium: the hook's correctness (#77) depends on fresh reads |
| 11 | Split `pre_tool_delete_guard.py` (shell lexer vs delete policy) and share the lexer with the git guard | maintainability of the largest file | high: guard behaviour; wait until #118 and #122 are closed |

## Not checked

- No real install, update or uninstall was run (no dry-run mode exists); the installer was
  read and its `--help` run. `tests/installer.py` covers it with stub clients.
- Hook timings are from one Mac inside Claude Code's sandbox; Linux, Windows (Git Bash) and a
  cold disk cache were not measured. Whether Claude Code runs one event's hooks in parallel
  was taken from its documentation, not measured.
- `question_label.py` and `archive_guard.py` were timed only on their early-exit path (no
  question label setting reached, no archive), not with a real `gh` call.
- The sandbox-network guard's refusal size is from this session's transcript, not a probe.
- Script output on success (terse or verbose) was judged from the code, not by running each
  script against a real repository, because most need `gh` and the network.
- CI per-test timings were not read from the logs.
