---
name: codex-worker
description: Hand the implementation of an issue to Codex from a Claude Code issue chat - the job, a turn, the thread record, the export and import of Codex's commits and the review - under the issue chats settings row `codex worker`. Use in an issue chat whose repository has that row and whose issue carries its label, when handing over to such an issue, and after cleanup-merged in such a repository.
compatibility: macOS only, the one system the worker's read deny list is measured on. Needs the codex command logged in (codex login), python3 and the issue-chats plugin.
---

# Codex as the worker

With the settings row `codex worker`, an issue that carries its label is built by Codex. The
Claude issue chat stays its owner: it claims the issue, asks the user the questions, runs every
GitHub step, reviews Codex's work and pushes it on the user's word. Codex writes the code and
commits it, in a job folder of its own; the chat imports the commits. Why: the user's ruling
(`DESIGN_DECISIONS.md`, #103). The worker
runs outside Claude Code's sandbox, so it runs no git and opens no file that the chat or Codex
wrote: everything that reads such data runs inside Codex's sandbox, and Codex's work comes back
as a git bundle, which is data (#107).

This skill belongs to the issue-chats method (the `issue-handover` skill's method file): the chat
runs it inside item 2 of that method's lifecycle (§4), in place of writing the code itself.
`<plugin>` is the folder two levels above this skill's folder. `<worker>` is
`python3 -I <plugin>/scripts/codex_worker.py`, by the path that the person's allow rule names
(the repository's `docs/install.md`, *Codex as the worker*; the installed clone puts it at
`~/.agentic-github-flow/plugins/codex/scripts/codex_worker.py`).

## The settings row

A row of the repository's `## Issue chats settings` (the method's §1), owned here:

| Setting | What it holds | When it is left out |
|---|---|---|
| codex worker | the label that hands an issue's implementation to Codex, the Codex model, then optionally the time limit of a turn in minutes (a number) and the reasoning effort (`minimal`, `low`, `medium`, `high`, `xhigh` or `max`; not every model takes every value), either or both, told apart by their form, each in backticks (`` `astra`, `gpt-6.2-astra`, `90`, `xhigh` `` or `` `astra`, `gpt-6.2-astra`, `xhigh` ``) | off: the Claude chat does the work itself; the time limit 60; no effort: the model's own |

## The route

1. **Commit first.** The worktree is clean, so Codex starts from all of the chat's work; the
   setup of a job refuses a dirty worktree.
2. **Write the prompt** to a file: the issue number and its task, its check and code paths, the
   repository's `AGENTS.md` to follow, commits by path whose subject ends in `(#<issue>)`,
   nothing under `.claude/`, `.codex/` or `.agents/`, no `.mcp.json`, `CLAUDE.md`, `AGENTS.md`,
   submodule, hook or hook manager's file (the import refuses them). The worker adds a note of
   its own on Codex's git setup, never pushing and that Codex cannot ask. The file is read
   inside Codex's sandbox, under its read deny list; its text goes to OpenAI.
3. **Run a turn:** `<worker> <worktree> --model <model> --prompt-file <file> [--time-limit
   <minutes>] [--effort <effort>]`, in the background, since a turn may run long; wait for it in
   this turn (the method's §4). One turn is
   one `codex exec`: Codex works until it stops, which may be a large task with many commits.
   The first turn makes the job, in a folder of the worker's under `~/.cache` that the chat's
   sandbox cannot write. The worker's header owns the refusals and Codex's sandbox: it writes
   only the job, has no network and reads the disk except the deny list (all of `~/.claude`,
   `~/.ssh`, `~/.aws`, `~/.netrc`, `~/.gnupg`, `~/.config/gh`, `.env` files, `*.pem`, `*.key`,
   `*.p12`, and what the user's and the managed Claude Code settings and the project settings of
   the worktree it is given deny reads of, read at each run); approval `never`, the person's
   Codex configuration and rules ignored, no hooks, no apps or plugins, at most 2 of Codex's
   own subagents at a time, each tool output capped in its context. The time limit is the
   settings row's number after the model, else 60 minutes. The effort is its value from the
   effort list, passed as `--effort` on every turn, each `--resume` too (a resume does not keep
   the effort of the turn before it, measured 2026-11-22); without it a turn runs at the model's
   default effort, since the person's Codex configuration is ignored. At the limit, or when
   Codex ends, the worker kills what is left of the turn. Of the report the chat reads `status`
   and Codex's `last_message`, nothing else: a few hundred tokens per turn. A project may list
   tools that Codex's own sandbox cannot run in `.agents/codex-tools.json`; the worker serves
   them for the turn (`codex_tools.py`'s header owns the format and the anchors in Claude Code's
   settings).
4. **Record it:** a signed comment on the issue whose text after the signature opens with
   `codex thread: <thread id>`, with the model. The thread outlives the chat, so a successor
   finds it there and resumes it; the person opens it with `codex resume <id>`. The Codex desktop
   app does not list it, since `codex exec` threads carry the source `exec` (measured
   2026-11-20).
5. **Decide the next step** from the last message, by rounds: a round is one task in a prompt of
   its own (a part of the issue, a round of a model), and the chat decides where one ends.
   Within a round, `--resume <thread id>` with a new prompt file and the row's `--effort`
   carries on the thread: an answer to a question (the user's, through the method's §4
   *Questions for the user*, or the chat's own), a review finding, a turn the time limit cut.
   The next task in the job is a turn without `--resume`: a fresh thread, to which the worker
   hands the job's commits and the last final message (the worker's header, *A round*), so the
   old context is not re-sent with every request; the prompt adds only what the chat knows
   beyond that. Or done. `--fresh` starts a new job from the chat's HEAD, dropping what the old
   one held.
6. **Export and import, once, when Codex is done:** `<worker> <worktree> --export` has a git
   bundle of Codex's commits cut inside Codex's sandbox and reports its path as `bundle`; then,
   inside the chat's own sandbox, `python3 <plugin>/scripts/codex_import.py <worktree> <bundle>`
   fast-forwards the branch. The import refuses (and changes nothing) when the bundle holds a
   merge, a submodule, `.gitmodules`, a `.claude`, `.codex` or `.agents` file, a `.mcp.json`, a
   `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md` or `AGENTS.override.md`, a hook manager's file
   (`.husky`, `.pre-commit-config.yaml`, `lefthook.yml`), or a change on a hooks path in the
   worktree (a link on the way to it, above it or beside it too), or does not descend from HEAD.
   It runs no hook while it fast-forwards. Then the chat makes such a change
   itself, or sends Codex back with `--resume`. Between the first turn and the import the chat
   does not commit on the branch.
7. **Review once,** as a reviewer that did not write it: `git diff <base>..<head>` from the
   import's report. A finding goes back to Codex with `--resume`, followed by a new export and
   import, or the chat fixes it in a commit of its own. The review clears by hand what the
   import cannot refuse but a later hook or push would run: a hook manager's configuration in
   `package.json` (husky 4, `simple-git-hooks`, `lint-staged`) or `.overcommit.yml`, and scripts
   these call. The cost of this review grows with the size of the diff, not with the number of
   turns, so a large task (a whole building) is split into issues per part, as for Claude work.
8. **Then on as usual:** the checks, `ship-change` steps 1 to 5, the hand-over. The review route
   of `ship-change` does not change: the chat that ran Codex is not the independent reviewer of
   the branch.

## At the hand-over and after the merge

- **The start brief** (`issue-handover` step 5) for an issue that carries the row's label says
  that Codex builds it, through this skill.
- **After the merge,** right after the `cleanup-merged` skill removed the chat's worktree:
  `<worker> --sweep`, spelled as the allow rule names it, removes the worker's jobs and logs of
  worktrees that are gone; it starts no Codex (the worker's header has what it removes and
  keeps).

## What the route does not give

Codex's commands are not seen by Claude Code's hooks, only the `codex_worker.py` call is. Inside
a worker turn the person's Codex configuration, execpolicy rules, MCP servers and hooks do not
apply, nor do the ChatGPT account's apps (connectors) and Codex plugins, because each of them
can run a command or a tool outside Codex's sandbox; `~/.codex/AGENTS.md` still loads, and
without an effort in the settings row the reasoning effort is the model's default. An approval
never reaches the user, because Codex asks for none. A process of a turn that leaves its
process group and drops its environment outlives the kill, inside Codex's sandbox, where it
writes only its own job. Codex's folder holds no `.git` folder (git works through `GIT_DIR`),
and no tracked file under a top-level `.codex/` or `.agents/` or with a name on the deny list:
those are marked skip-worktree, so Codex does not commit their removal. The worker needs Codex
logged in (`codex login`) and runs outside Claude Code's sandbox, which keeps Codex from the
network and from writing its sessions under `~/.codex`. It runs on macOS only, the one system
its read deny list is measured on. There a job's files are copy-on-write clones, so a
repository with gigabytes of tracked files costs no disk per job (measured on pax_deorum:
16,891 files, 13 GiB, 64 s, 15.7 MiB).

OpenAI's documentation behind Codex's sandbox and approvals, with read dates:
[sources.md](sources.md).
