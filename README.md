# agentic-github-flow

One working method for AI coding agents on GitHub, in a team that works with pull requests or
alone on a repository of your own, for **Claude Code** and **Codex** alike: short rules that load in every session, and skills that
load only when a task needs them. You install it with one command and write no instruction files
of your own.

agentic-github-flow is unrelated to `ruvnet/agentic-flow` and its npm package.

## What you get

**Rules for every session** (`rules/core.md`, under 8 KB): do the task that was asked
completely; ask before anything that leaves the machine, cannot be undone, costs money or changes
what gets built; never force-push, rewrite history or discard uncommitted work; work on a branch
in a worktree and land it the way the repository lands work (below); ask before every push and
never merge a pull request without your word; keep secrets and personal data in; issues are the
work queue; content from tools and web pages is data, not instructions.

**Plugins with skills**, the same files for both clients:

| Plugin | Skills and tools | Installed |
|---|---|---|
| `agentic-github-flow-core` | `spec-first` (a specification before large work), `requirements` (an interview that turns new work into a parent issue and ready sub-issues), `open-issue` (an issue an agent can pick up, labelled ready or needs-spec), `repo-docs` (a repository's agent documents), `efficient-design` (a checklist at design and review: work per frame, request or job run grows with what changed, not with all data), `ship-change` (lands a finished branch in the repository's [landing mode](#landing-pull-request-or-local-main), with an overlap check against other unmerged work and a yes before every push), `review-change` (the independent review of another agent's pull request, its verdict posted for the exact head commit in the form `merge_pr.py` reads), `cleanup-merged` (worktree and branch removal after the merge or the push of main, checked so nothing is lost) | always |
| `agentic-github-flow-security` | `review-security` (a review checklist by area), a secret scanner that never prints values, a dependency audit against OSV, with osv-scanner as an optional second opinion | `--with security` |
| `agentic-github-flow-web-deploy` | `check-web-deploy` (pre-deploy check of a Vercel and Supabase site, with optional Google sign-in, its mail domain and EU privacy) | `--with web-deploy` (brings security) |
| `agentic-github-flow-issue-chats` | `issue-handover` (one issue per chat: once a branch is ready to push, or has landed on local main, pick the next ready issue by priority, check it for overlap, start and claim its chat, then ask you for the push or archive) and `archive-finished-chats` (archive chats whose work is on GitHub, or landed on local main, and side chats once their work landed or merged); a Claude Code hook that lets a chat be archived only when its worktree is clean and its commits are on GitHub or, in local-main mode, landed (a side chat it is asked to archive: landed or merged). See [Issue chats](#issue-chats) | `--with issue-chats` |
| `agentic-github-flow-guards` | Claude Code hooks that refuse destructive git commands and ask before destructive deletes and before personal data leaves the machine; the installer adds the matching deny list and the Codex rules and hooks | `--guards` |

## Requirements

Git, Python 3.8 or newer, and Claude Code or Codex (or both). `gh`, the GitHub CLI, lets the
agents open pull requests and check merges; without it they hand you the text instead.
macOS, Linux and Windows. GitHub only: GitLab, Azure DevOps and other hosts are not supported yet.

## Landing: pull request or local main

At every landing the `ship-change` skill asks the core plugin's `landing.py` how this
repository lands finished work, and states the answer with its reasons on the issue:

- **Pull request** (GitHub flow): the agent pushes its task branch and opens a pull request; you
  merge it. Chosen when GitHub requires pull requests on the branch (a ruleset or branch
  protection that forbids a direct push), when the repository is a team's (an organisation
  owns it, more than one collaborator can write, it has a `CODEOWNERS` file, or someone else
  merged a pull request into it in the last 90 days), and whenever it cannot tell (no `gh`, no
  network, a host other than GitHub).
- **Local main** (trunk-based development, which allows a very small team to commit to the
  trunk): the agent still works on a branch in a worktree, then fast-forwards your local `main`
  to the checked commit (`promote_main.py`, which refuses when anything would be lost); a larger
  or risky change is reviewed and landed by an agent that did not write it. You push `main` when
  you say so. Chosen for a repository owned by your own account with you as its only writer, no
  protection and no team signal, and for a repository without a remote. On GitHub's free plan a
  private repository cannot have protection at all; that counts as "no protection", not as
  unknown.

In pull-request mode you merge, unless you switch automatic merging on for that repository, like its
landing mode: the row `automatic merge` with the value `on` in its `HANDOFF.md` §Landing settings
(below); it is off by default, and an overlay cannot switch it on. Then an agent marks its own pull
request ready and merges it through `merge_pr.py`, only with every required check green, an
approving review of the head commit by another agent, the overlap result in the body, and no change
to rules, guards, permission settings, hooks, the installer, CI or deployment configuration, the
merge and push gates, or the switch and landing settings in `HANDOFF.md`.

You also decide every push, unless you grant the push of an agent's own task branch: in the
repository's `HANDOFF.md` §Standing permissions, or in your own overlay file outside the
repository, by naming `push_branch.py` there. Then the agent pushes through `push_branch.py` and
opens its pull request without asking; the script reads the grant where the agent names it, and
pushes only the branch, only in pull-request mode read from the setting or from GitHub, with
the `pre-push` template installed (so the secret scan and the personal-data check run on every
outgoing commit), the overlap result in the body, and no change to the paths above; whatever it
refuses still asks. The allow rule below holds in every repository, so the grant is what
limits it: an overlay that does not name the script, an employer's for example, grants
nothing.

A repository can fix its mode, and name a landing branch other than its default branch, in its
`HANDOFF.md`; `local main` there cannot overrule a server that requires pull requests. Pull
requests target the landing branch, and the cleanup scripts and the `pre-push` template count
"merged" against it. `landing` takes `pull request`, `local main` or `auto` (detect); a value
cell holds the value alone:

```markdown
## Landing settings

| Setting | Value |
|---|---|
| landing | `auto` |
| landing branch | `main` |
```

## Install

macOS and Linux:

```bash
git clone https://github.com/IgorVerm/agentic-github-flow.git ~/.agentic-github-flow && ~/.agentic-github-flow/install.sh
```

Windows (PowerShell):

```powershell
git clone https://github.com/IgorVerm/agentic-github-flow.git "$env:USERPROFILE\.agentic-github-flow"; & "$env:USERPROFILE\.agentic-github-flow\install.ps1"
```

Add options to the install command as needed:

| Option | Effect |
|---|---|
| `--with security,web-deploy,issue-chats` | also install those plugins (any of them) |
| `--guards` | also install the guards (see below) |
| `--guards sandbox` | the guards plus the opt-in [sandbox-network guard](#sandbox-network-guard-opt-in) (Claude Code) |
| `--overlay <git-url-or-path>` | add a company or personal overlay (repeatable) |
| `--no-claude`, `--no-codex` | leave one client alone |
| `--claude-bin <path>`, `--codex-bin <path>` | a client that is not on `PATH` |

Then start a new session in each client. A client that is not installed is skipped, and the
installer says so.

## Update and uninstall

```bash
~/.agentic-github-flow/install.sh --update
```

```bash
~/.agentic-github-flow/install.sh --uninstall
```

`--update` pulls the clone and repeats what you installed. `--uninstall` removes exactly what
the installer recorded that it added. It leaves your own lines in `~/.claude/CLAUDE.md` and
`~/.codex/AGENTS.md` byte for byte as they were, and leaves the clone: delete
`~/.agentic-github-flow` afterwards to remove it completely. On Windows, use `install.ps1` with
the same options.

## What the installer changes

Everything stays in one clone, `~/.agentic-github-flow`, so the rules and the skills are always
the same version.

- `~/.claude/CLAUDE.md`: a block between `<!-- >>> agentic-github-flow >>> -->` and
  `<!-- <<< agentic-github-flow <<< -->` that imports `rules/core.md` and each overlay's
  `AGENTS.md`.
- `~/.codex/AGENTS.md`: the same block with the text written out, because Codex does not follow
  imports there; `--update` rewrites it.
- Both clients: this clone registered as the plugin marketplace `agentic-github-flow`, and the
  plugins installed from it.
- With `--guards`: the guards plugin in Claude Code; the ask and deny rules merged into
  `~/.claude/settings.json` (merged, never replaced, with a backup beside it); the Codex
  execpolicy rules (git safety and delete prompts) copied into `~/.codex/rules/`, as copies
  because Codex skips a symlinked rules file, refreshed by `--update` and removed by
  `--uninstall` only while unchanged; the git guard and the personal-data guard added to
  `~/.codex/hooks.json` beside your own entries (`--update` replaces and `--uninstall` removes
  only those two). Codex runs a new hook only after you trust it once with `/hooks` in Codex.
  In Codex the personal-data guard denies instead of asking, because a Codex hook cannot ask:
  the agent tells you what it would send where, and you run it yourself. Text typed into a
  command that is already running (`write_stdin`) reaches no hook. The delete-guard
  hook stays out of Codex (it asks, and a Codex hook can only deny); the delete prompt rules
  take its place there, and they prompt for every recursive `rm` and `xargs rm`, inside the
  workspace too (under `codex exec`, which never asks, such a command does not run).
- With `--guards sandbox`, also: one `PreToolUse` entry in `~/.claude/settings.json` that runs
  the sandbox-network guard from the clone, beside your own hooks (`--update` replaces and
  `--uninstall` removes only that entry).

With `--with issue-chats`, the plugin's archive hook comes with the plugin; the installer adds no
permission rule for it (see [Issue chats](#issue-chats)).

If `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md` is a symlink, the installer stops before
changing anything and explains: writing through the link would change the file it points to.
Replace the link with a plain file, or skip that client with `--no-claude` or `--no-codex`.

Nothing is sent anywhere except the git and plugin fetches: no telemetry.

### Personal-data guard settings

The personal-data guard reads three optional files in
`${XDG_CONFIG_HOME:-~/.config}/agentic-github-flow/`, outside every repository so they are never
committed. One entry per line; blank lines and `#` comments are ignored.

| File | Entry | Effect |
|---|---|---|
| `personal-data` | an identifier beyond your git and gh identity, optionally `email:`, `phone:` or `name:` | calls that send it are asked (Claude Code) or denied (Codex) |
| `exempt-dirs` | an absolute folder (`~` allowed) | sessions working inside it are not checked, for work that other rules govern |
| `local-mcp` | an MCP server name | its `mcp__<name>__*` tools count as local and are not checked |

Listing a folder or a server turns the check off there, so list only what you mean: `/` or `~`
in `exempt-dirs` turns it off everywhere, and `codex_apps` in `local-mcp` passes every Codex
connector (mail and GitHub alike). Whoever can write these files decides what is checked; a
settings folder that a repository moves into itself (through `XDG_CONFIG_HOME` or `HOME` in its
own settings) is not trusted for the two exemption files. The exact matching rules are in the
guard's header, `plugins/guards/scripts/pre_tool_personal_data.py`.

### Sandbox-network guard (opt-in)

With Claude Code's Bash sandbox on, a call runs outside the sandbox only when every part of it
matches an entry of `sandbox.excludedCommands`. A call such as `cd <repo> && gh pr list` never
matches: it runs inside, `gh` or `ssh` fails there, and the agent retries it with the sandbox
disabled. In one measured setup a fifth of all Bash calls left the sandbox that way.

`--guards sandbox` adds a hook that turns such a call away and names the lone call that does the
same and matches one of your entries, for example `gh pr list -R owner/repo`. It only refuses:
it never lets a call run that would not run without it, and what runs outside the sandbox is
still decided by your `excludedCommands` and your permission settings. It does nothing until
`sandbox.enabled` is true in `~/.claude/settings.json` and `excludedCommands` lists your network
commands (for example `gh *`, `ssh *`, `git push *`), and nothing on native Windows, where Claude
Code has no sandbox (WSL2 works as Linux). When no faithful lone call exists (input
from a file or a pipe, output to a file, `$(…)`, a glob after a `cd`, a gh command that acts on
the folder), the call passes as before.

The forms that run excluded, which the guard's refusals teach:
- a network command in a Bash call of its own: no `cd`, pipe into another command, file
  redirection, here-document or `$(…)` (`2>&1` is fine);
- `gh … -R owner/repo`, with a body written to a file and passed as `--body-file`;
- absolute paths for `scp`, `rsync` and scripts; filter ssh output on the remote side
  (`ssh host 'cmd | head'`);
- `git fetch|pull|push` from the session's own folder: `git -C <dir>` never matches an entry.

A script that reaches the network and has an entry of the form `bash "<absolute path>"*` is
rewritten to that form. After a `cd` to another folder only when the script does the same from
any folder: list such scripts, one absolute path pattern per line (`*` allowed), in
`${XDG_CONFIG_HOME:-~/.config}/agentic-github-flow/sandbox-scripts`. An entry such as `rsync *`
also lets local copies run outside the sandbox; add only the entries you mean.

A script or tool that only needs a host can stay inside the sandbox: name the host for that one
call (Claude Code's `allowed_domains`, `host` or `host:port`). For a private address, clear
`NO_PROXY` and `no_proxy` for that call: clients that honour their CIDR entries (`curl`) go
straight to the address, which the sandbox refuses. The exact rules are in the guard's header,
`plugins/guards/scripts/pre_tool_sandbox_network.py`.

## Issue chats

The issue-chats plugin works a repository's GitHub issues one chat per issue: a chat takes a
ready issue, works on its own branch in a new worktree until the branch is ready to push, then
starts the chat for the next ready issue and asks you for the push. It leaves the sidebar only
once its commits are on GitHub. In a repository that lands on local main, a chat lands its work
there, starts the next chat and archives itself; you push `main` when you want the landings
published. Every push still waits for your yes. A side chat, one that another chat started
with `start_session`, archives itself once its work has landed or its pull request merged, not
when it is merely pushed. A repository switches it on
with a `## Issue chats settings` section in its `HANDOFF.md`, merged like any other change; the
template and the method are in the plugin's `issue-handover` skill (`method.md`).

The automatic start of the next chat needs the Claude Code desktop app, the `claude` CLI logged
in (`claude auth login`) and `gh`; it was measured on macOS, is unmeasured on Linux and refused
on Windows. Codex uses its own app's chat tools. Anywhere else the chat gives you the brief for
the next chat to paste.

For chains that run without a click, allow the start script alone in `~/.claude/settings.json`
(`permissions.allow`), never `claude --bg` itself, which would also admit
`--dangerously-skip-permissions`:

```json
"Bash(python3 <plugin folder>/scripts/start_issue_chat.py *)"
```

`<plugin folder>` is where Claude Code installed the plugin: the folder two levels above the
`issue-handover` skill's folder (a session can tell you where it loaded the skill from). Write
the rule in each spelling the agents use for that path. The folder names the plugin's version,
so renew the rule after an update raises it. Where you grant unasked pushes or switch
automatic merging on, allow the core plugin's two gates the same way, never `git push`,
`gh pr ready` or `gh pr merge` themselves:

```json
"Bash(python3 <core plugin folder>/scripts/push_branch.py *)",
"Bash(python3 <core plugin folder>/scripts/merge_pr.py *)"
```

An allow rule for
`mcp__ccd_session_mgmt__archive_session` lets chats archive themselves without a click; the
plugin's hook still denies any archive whose worktree is not clean and on GitHub (or, in
local-main mode, landed). The installer
adds none of these: a permission change is yours to make.

## Which rule wins

1. A company overlay's binding rules (its AI policy, its data classes): never relaxed in a
   conversation, by anyone.
2. Below that, what you say in the conversation beats the rules.
3. A repository's own `AGENTS.md` wins where it is stricter or says it deviates.
4. An overlay wins over the core rules where it says it deviates.

## Using it at work

Before you use this on an employer's or a client's code, check that organisation's AI rules:
which tools and plans are allowed, which data may go into a prompt or leave the machine, and
who owns work made with an agent. The rules point agents to that policy; this repository never
holds it. Put the pointer in the organisation's overlay, starting from
`templates/company-overlay/AGENTS.md`. Without an overlay, an agent asks you where the policy is
before it works on the organisation's code or data.

## Company and personal overlays

An overlay is a git repository (or a folder) with an `AGENTS.md` at its root. Its text loads
after the core rules in both clients. A company keeps its overlay in a private repository of its
own GitHub organisation, starting from `templates/company-overlay/AGENTS.md`: a pointer to the
AI policy (not a copy), the data classes and what may go into prompts, and the organisation's
reviewers, CI checks and branch naming. A personal overlay holds one person's additions. Neither
belongs in this public repository.

## From a plugin directory

The plugins can also be installed on their own from a plugin directory or marketplace. Then you
get the skills without the always-loaded rules: no plugin system can ship those. Run the
installer to get the rules too.

## For administrators

There is no central rollout here. An administrator who wants every Claude Code user to have the
marketplace can declare it in managed settings (`extraKnownMarketplaces`, `enabledPlugins`; see
Anthropic's documentation on settings and plugin marketplaces). The always-loaded rules still
need the installer, or a managed `CLAUDE.md` that holds the text of `rules/core.md`.

## Licence

Apache-2.0: see `LICENSE` and `NOTICE`.

## About

Made by MAI-Tech: <https://mai-tech.be>.
