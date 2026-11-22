# Q4: safety kept, and the cost of a refused call avoided

The maintainer's question on #123, 2026-11-22: how to guarantee safety and avoid the token
cost of the refused tool calls themselves. Evidence: `refusals.md` with `refusal_stats.py`
(the transcripts, same window as the audit), the Claude Code documentation read on 2026-11-22,
and an analysis of both guards with a prototype (held back, see §5).

## 1. What a refused call costs, measured

One failed or refused call makes the chat re-read its whole context once, from the prompt
cache.

| Cause, 2026-10-12 to 2026-11-22 | Calls | Tokens re-read |
|---|---:|---:|
| Sandbox failures (no guard involved) | 962 | 140.7M |
| `archive_session` failures outside the guard | | 56.5M |
| Auto-mode denials | 236 | 47.4M |
| Settings-rule denials | 179 | 45.8M |
| Archive guard | 171 | 43.3M |
| Git guard | 138 | 27.4M |
| Sandbox-network guard | 102 | 13.6M (median 90k per refusal, the cheapest) |
| **All refusals and sandbox failures** | **2,005** | **about 398M** |

In proportion: 398M is 1.2% of the 32.0B cache-read tokens of the window. So the tokens are a
small gain. The larger reasons to act are safety (a quarter of all Bash calls run with the
sandbox off) and the prompts the person answers.

## 2. What the measurements say about each way

**A refusal that names the lone call teaches it; a plain failure teaches the opposite.**

| After the first… | later network calls in that session |
|---|---|
| refusal by the sandbox-network guard (88 sessions, 1,208 later calls) | 74% lone, 15% sandbox off, 1.2% refused again; 85% of sessions are never refused twice |
| plain sandbox failure (3,528 later calls) | 23% lone, 67% sandbox off, 9% chained again |

**Nothing is learned across sessions.** The first network call of a session is chained with the
sandbox on in 67% of sessions before the guard and 63% after it (1.5 days of data). The chained
form had appeared earlier in the session in only 3% of them, and no rule, skill or script of
this repository shows it: it is the model's own default. `main` holds no rule that asks for the
lone call, so prevention by text has not been tried yet. It is unmeasured, not disproved.

**A hook that rewrites the call is not a way out.**
- Claude Code's documentation: a hook that returns a changed input without a decision is
  refused in auto mode with "a hook changed this call's input after auto mode reviewed it", and
  the model must issue the call again (https://code.claude.com/docs/en/hooks.md, read
  2026-11-22). That is a failed round trip of its own. The transcripts hold 65 such denials
  from other tools' hooks; in 30 of 47 cases the next call failed again.
- A rewrite returned with "allow" would skip the ask rules (`gh pr merge`, for example), and the
  other guards have judged only the original text.
- Only 8% of the chained `gh` calls and 12% of the `cd <dir> && …` calls have a faithful
  one-call form. The rest (`$(gh …)`, loops, other commands chained, here-documents) need two
  calls, which a hook cannot make.

**The sandbox flag can be closed in the settings.** With `sandbox.allowUnsandboxedCommands`
set to `false`, a call that asks to leave the sandbox is ignored: only what matches
`sandbox.excludedCommands` runs outside (https://code.claude.com/docs/en/sandboxing.md, read
2026-11-22). That is the one guarantee among the options: it does not depend on a model
following a text.

**Most escapes are not `gh` at all.** Of 17,721 calls that left the sandbox: 827 needed no
escape, 699 have a lone form the guard names today, 6,811 have none, and 9,367 show no
network command: mostly this repository's own scripts. Eleven of them reach GitHub
(`promote_main.py`, `new_worktree.py`, `push_branch.py`, `merge_pr.py`, `review_verdict.py`,
`overlap_check.py`, `landing.py`, `remove_merged_worktree.py`, `delete_merged_branch.py`,
`next_issue.py`, `chat_archivable.py`). No skill says so before the call, and three skills
tell the agent to switch the sandbox off instead of naming a lone call
(`ship-change/SKILL.md:33-36`, `local-main.md:29-30`, `issue-handover/SKILL.md:115`).

## 3. The options

| | Option | Guarantees | Costs |
|---|---|---|---|
| A | **Refuse precisely and print the complete lone command** (P7 after #122): chained and piped `gh`, `cd`, `git -C`, and a call that switches the sandbox off although each part has a lone form. Passes when no faithful lone form exists. | Nothing more leaves the sandbox than the person's own `excludedCommands` allow. A refusal never widens anything. | One refusal per session, about 90k cache-read tokens; 85% of sessions never a second. Covers the 1,526 calls with a lone form, not the 6,811 without. |
| B | **Say it before the first call:** one sentence of fact at session start, from a hook the sandbox guard installs, so only users who opted in to that guard carry it (about 40 tokens per session, and per subagent if the client offers a start hook for them). Not in `rules/core.md`. | Nothing by itself: it is text. | 40 tokens per session. Benefit unmeasured: a trial of one week, measured as the share of sessions whose first network call is lone (7% before the guard, 25% with it). |
| C | **Scripts say where they must run:** each of the eleven scripts stops at once with one line when it cannot reach GitHub from inside a sandbox (already in #128), and each skill names its script's call as a lone call before the step. | Nothing leaves the sandbox that did not before. | Text in four skills. Does not remove the escape itself: the script still runs outside. |
| D | **Close the flag:** `allowUnsandboxedCommands: false` in the person's settings, documented in `docs/install.md` as the strict setting, with A, B and C in place first. The scripts of C then need an entry in `excludedCommands` each, by exact path. | The strongest: no model can leave the sandbox, whatever it was told. | Every call without a lone form fails until the chat restructures it. An excluded script runs git outside the sandbox on a repository the chat can write: the class the reviews of #105 found for the Codex worker. So entries only for scripts reviewed for that, one by one. |
| E | **A rewriting hook** | Less than A: it changes what was reviewed. | A denial in auto mode per rewrite; 8–12% of calls rewritable. **Not recommended.** |
| F | **GitHub reachable inside the sandbox** (allowed domains, the token readable by sandboxed commands) | Chained forms work, no failure and no escape. | Every sandboxed command can read the GitHub token and send data to github.com. It weakens what the sandbox is for. **Not recommended**; named because it is the only option without any failed first call. |

**Recommended: A, B and C now; D as a second step, on the maintainer's word, after a week of
numbers.** A alone turns the costly failure (140.7M tokens, and a lesson that says "switch the
sandbox off") into the cheapest refusal (and a lesson that says "lone call"). B is the only
candidate that could avoid the first refusal too, and costs 40 tokens to find out. D is what
makes it a guarantee instead of a habit.

## 4. The git guard's brace check (P10)

- 45 refusals in six weeks for "brace expansion it cannot read". 30 are inside a
  here-document body (program code, file text), 10 are an expansion in another command such as
  `mkdir`, and 5 are in the git command itself. So the check is wrong for 89% of what it
  refuses.
- Cause: it runs on the whole call before here-documents are set aside
  (`pre_tool_git_guard.py:412-414`).
- **The analysis also found two forms the guard passes today although the shell runs a git
  command it would refuse**. The narrowing closes both.
  The exact forms are not written here (§5).

Which forms are safe to stop refusing, each argued from what the shell expands and measured in
bash, zsh and sh:

| Form | Verdict | Condition |
|---|---|---|
| A here-document body with a quoted delimiter | pass | the body is not read by a shell, an interpreter or ssh |
| A here-document body with an unquoted delimiter | pass for braces | its command substitutions are judged as commands |
| A here-string | pass | |
| Braces in single or double quotes, `${var}`, `@{u}`, `HEAD@{1}`, `{}`, `{x}` | pass (already today) | a brace inside a `${x:-…}` default stays refused |
| Brace expansion in a command that is not git or gh | pass | the command word holds no brace and is no wrapper naming git; no assignment, loop, function or alias; not piped with git |
| Anything in the call that runs text as code (a shell, `xargs`, `ssh`, `eval`, an interpreter on stdin) | refuse | as today |
| Brace expansion in git's own arguments | refuse | the message prints the written-out command when the expansion is simple |

- A prototype passes 39 of the 43 measured refusals it was replayed on, keeps all 136 refused
  and 99 passed test cases unchanged, keeps all 22 hostile forms refused and closes both
  bypasses.
- It stays a deny: a prompt stalls an unattended chat, and Codex has no "ask".
- Order: after #33, whose comment stripping one of the two fixes needs.
- Residual risk, as today: braces that arrive through a file or a variable, and interpreter
  code that is only pattern-matched.

**Recommended: do P10 in this narrow, proven form, and treat it as a safety fix, not only as
comfort.**

## 5. Held back

`guards-analysis.md` holds the two bypasses in runnable form. The repository is public, so the
file is not committed or pushed. The maintainer decides: publish it with the fix, or before.

## 6. Questions for the maintainer

1. **A, B, C as recommended?** (B as a one-week trial with the measurement named above.)
2. **D:** document the strict setting in `docs/install.md` now, and decide on your own settings
   after the week of numbers? Excluding scripts from the sandbox touches the risk you ruled on
   for the Codex worker, so each script would come to you by name.
3. **P10 in the narrow form,** after #33?
4. **The two bypasses:** fix first and publish the details with the fix (recommended), or may
   the analysis be pushed now?
