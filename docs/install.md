# Installing agentic-github-flow: a guide for the installing agent

You are an AI coding agent (Claude Code or Codex) asked to install agentic-github-flow for the
person you work with. Follow these steps in order. Ask the person every decision in step 2
before you run anything that changes their machine, and report what each step printed. What
agentic-github-flow is, for the person: [guide.md](guide.md).

The installer's behaviour is owned by the docstring of
[`tools/installer.py`](../tools/installer.py); where this guide and that docstring disagree, the
docstring is right and this guide is to be corrected.

## 1. Check the requirements

Run each check and tell the person what is missing. Stop until the hard requirements are met.

| Need | Check | When it is missing |
|---|---|---|
| git | `git --version` | hard requirement; on Windows Git for Windows (`winget install Git.Git`) |
| Python 3.8 or newer | `python3 --version` (Windows: `py -3 --version`) | hard requirement; on Windows for example `winget install Python.Python.3.12` |
| Claude Code, Codex or both | `claude --version`, `codex --version` | at least one; a client that is missing is skipped |
| the GitHub CLI, signed in | `gh auth status` | optional: without it agents cannot open pull requests or check merges and hand the person the text instead |

macOS, Linux and Windows are supported. The repositories it works on must be on github.com:
GitHub Enterprise Server, GitLab and Azure DevOps are not supported (the details:
[guide.md, Where it works](guide.md#where-it-works)).

If `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md` is a symlink, the installer refuses before it
changes anything, because writing through the link would change the file it points to. Tell the
person, and either replace the link with a plain file (for example a copy of its target) with
their agreement, or leave that client out with `--no-claude` or `--no-codex`.

## 2. Ask the decisions

Ask these in one message, with your recommendation, and wait for the answers.

1. **Personal machine or work machine?** For work on an employer's or a client's code, the
   organisation's AI policy comes first: ask whether the organisation has a company overlay
   (a git repository, or a folder, with an `AGENTS.md` at its root, started from
   [`templates/company-overlay/AGENTS.md`](../templates/company-overlay/AGENTS.md)) and where it
   lives. Without one, tell the person that their agents will ask where the AI policy is before
   working on the organisation's code, and that someone in the organisation can make the
   overlay.
2. **Which overlays?** At work: the company overlay (`--overlay <its clone URL or folder>`)
   and **no personal overlay**: an overlay loads in every session on the machine, and a personal
   overlay's grants, such as the push grant, are meant for the person's own repositories. On a
   personal machine: a personal overlay if they keep one, or none.
3. **Which opt-in parts?** Explain each in a line (the person's view of them:
   [guide.md, Opt-in parts](guide.md#opt-in-parts)):
   - `--with security`: security review, secret scanner, dependency audit;
   - `--with web-deploy`: the pre-deploy check of a Vercel and Supabase site or a Google Cloud
     site on Cloud Run, Cloud SQL, IAP and Secret Manager (brings security);
   - `--with issue-chats`: one chat per GitHub issue, handing over to the next ready issue;
   - `--guards`: hooks that refuse destructive git commands and ask before destructive deletes
     and before personal data leaves the machine. Recommend it, at work certainly;
   - `--guards sandbox`: the guards plus the sandbox-network guard, for Claude Code users who run
     its Bash sandbox (step 5);
   - `--guards gcloud`: the guards plus the Google Cloud guard, for people who are signed in to
     Google Cloud on this machine (step 5); `--guards sandbox,gcloud` for both.
4. **Which clients?** Both by default; `--no-claude` or `--no-codex` leaves one alone. A client
   that is not on `PATH`: `--claude-bin <path>` or `--codex-bin <path>`.
5. **Their work identity** (for `--guards`): the personal-data guard knows the person's
   `git config --global` identity, the gh login of github.com and the local account name. Ask
   whether they use another name or e-mail address at work (set per repository, for example);
   if so it goes into the guard's `personal-data` file in step 5.

## 3. Clone and install

macOS and Linux:

```bash
git clone https://github.com/IgorVerm/agentic-github-flow.git ~/.agentic-github-flow && ~/.agentic-github-flow/install.sh <options>
```

Windows (PowerShell):

```powershell
git clone https://github.com/IgorVerm/agentic-github-flow.git "$env:USERPROFILE\.agentic-github-flow"; & "$env:USERPROFILE\.agentic-github-flow\install.ps1" <options>
```

When `~/.agentic-github-flow` already holds the clone, run `install.sh` (or `install.ps1`) alone:
it clones only when the folder is missing, and refuses (`STOP`) when the folder exists but is no
clone of this repository.

The options, all optional, combined as the person decided:

| Option | Effect |
|---|---|
| `--with security,web-deploy,issue-chats` | also install those plugins (any of them); `web-deploy` brings `security` |
| `--guards` | also install the guards |
| `--guards sandbox` | the guards plus the opt-in sandbox-network guard (Claude Code) |
| `--guards gcloud` | the guards plus the opt-in Google Cloud guard (both clients) |
| `--overlay <git-url-or-path>` | add a company or personal overlay (repeatable) |
| `--no-claude`, `--no-codex` | leave one client alone |
| `--claude-bin <path>`, `--codex-bin <path>` | a client that is not on `PATH` |

For example, a work machine: `~/.agentic-github-flow/install.sh --guards --overlay <company-overlay>`.

A second plain run keeps what an earlier one installed and adds what it names: it never removes a
plugin, the guards or an overlay. To drop one, run `--uninstall` (step 7) and install again with
every option wanted. Where a personal overlay is installed on a machine that now becomes a work
machine, that is the way to remove it.

The installer prints one line per step, starting with its status:

| Status | Meaning |
|---|---|
| `ok` | the step was done |
| `skip` | the step was left out, with the reason (a client that is not installed, for example) |
| `warn` | done, with a warning to pass on |
| `FAIL` | the step failed; the rest still ran |
| `STOP` | refused before any change |
| `done` | the last line: everything succeeded |

Exit codes: 0 done; 1 a step failed (the rest ran); 2 usage; 3 refused before any change.

### What the installer changes

Everything stays in the one clone, `~/.agentic-github-flow`, so the rules and the skills are
always the same version. Tell the person what changed:

- `~/.claude/CLAUDE.md`: a block between `<!-- >>> agentic-github-flow >>> -->` and
  `<!-- <<< agentic-github-flow <<< -->` that imports `rules/core.md` and each overlay's
  `AGENTS.md`. Lines outside the block are never touched.
- `~/.codex/AGENTS.md`: the same block with the text written out, because Codex does not follow
  imports there; `--update` rewrites it.
- Both clients: the clone registered as the plugin marketplace `agentic-github-flow`, and the
  chosen plugins installed from it.
- With `--guards`: the guards plugin in Claude Code (Codex has no guards plugin: its guards are
  the rules and hooks that follow); the ask and deny rules merged into
  `~/.claude/settings.json` (merged, never replaced); the Codex
  execpolicy rules (git safety and delete prompts) copied into `~/.codex/rules/`; the git guard
  and the personal-data guard added to `~/.codex/hooks.json` beside the person's own entries.
  In Codex the personal-data guard denies instead of asking, because a Codex hook cannot ask;
  the delete prompt rules take the delete guard's place there. The exact behaviour, also of
  `--update` and `--uninstall`: the installer's docstring.
- With `--guards sandbox`, also: one `PreToolUse` entry in `~/.claude/settings.json` that runs the
  sandbox-network guard from the clone.
- With `--guards gcloud`, also: the Google Cloud ask and deny rules merged into
  `~/.claude/settings.json` like the others, and a third rules file copied into `~/.codex/rules/`.
- Overlays: one given as a git URL is cloned into `~/.agentic-github-flow/overlays/`; one given
  as a folder is used where it is, so it must stay there (Claude Code imports it by its absolute
  path). Codex gets the overlay's text written out, so after an overlay changes, run
  `install.sh --update` (it also pulls the cloned ones).
- Backups: before each change to an existing `~/.claude/settings.json` or `~/.codex/hooks.json`,
  by an install, `--update` or `--uninstall`, the installer copies it beside itself as
  `<file>.agentic-github-flow-backup-<date>-<time>`. These copies stay; they are the person's to
  delete.
- Everything added is recorded in `~/.agentic-github-flow/.state/install.json`, so `--update`
  repeats it and `--uninstall` removes exactly that.

Nothing is sent anywhere except the git and plugin fetches: no telemetry.

## 4. Verify

1. **The last line is `done`** and no line says `FAIL`. On a `FAIL`, go to step 6.
2. **Codex with `--guards`:** Codex runs a new hook only after the person trusts it once: ask
   them to run `/hooks` in Codex and trust the two hooks the installer named.
3. **The plugins are installed:** `claude plugin list` shows `agentic-github-flow-core`, each
   chosen plugin and, with `--guards`, `agentic-github-flow-guards`, from the marketplace
   `agentic-github-flow`. For Codex the installer's `ok codex: add …` lines are the proof (its
   `plugin list` also lists plugins that are only available); Codex never gets the guards
   plugin.
4. **A fresh session loads the rules:** ask the person to start a new session in each client
   (the running ones do not reload) and ask it "Which agentic-github-flow rules and skills do you
   have?". It should name the rules (ask before a push, work in a worktree, issues as the queue)
   and skills such as `ship-change` and `open-issue`.
5. **With `--guards`, a scratch test:** in a new, empty repository outside the person's real
   work (`git init` in a temporary folder, one commit), ask the fresh session to run
   `git reset --hard`. Claude Code must refuse it (the deny list) and Codex must forbid it (the
   execpolicy rules). Then delete the scratch folder with the system's trash.
6. **Settings that point into the plugin cache:** if `~/.claude/settings.json` has permission
   rules or sandbox exclusions that point into `~/.claude/plugins/cache/`, each install names
   them and gives the same entry with the clone's path; when there are none it prints nothing.
   Pass such a list on: such an entry silently
   stops matching after an update. The installer changes none of them; a permission change is
   the person's to make.

## 5. Optional settings

None of these is made by the installer. Each changes what the agents may do or what is checked,
so make it only with the person's agreement, and show the line first.

### The personal-data guard

The guard reads three optional files in `${XDG_CONFIG_HOME:-~/.config}/agentic-github-flow/`,
outside every repository so they are never committed. One entry per line; blank lines and `#`
comments are ignored.

| File | Entry | Effect |
|---|---|---|
| `personal-data` | an identifier beyond the git and gh identity, optionally `email:`, `phone:` or `name:` | calls that send it are asked (Claude Code) or denied (Codex) |
| `exempt-dirs` | an absolute folder (`~` allowed) | sessions working inside it are not checked, for work that other rules govern |
| `local-mcp` | an MCP server name | its `mcp__<name>__*` tools count as local and are not checked |

The work identity of step 2 goes into `personal-data`. Listing a folder or a server turns the
check off there: `/` or `~` in `exempt-dirs` turns it off everywhere, and `codex_apps` in
`local-mcp` passes every Codex connector. A settings folder that a repository moves into itself
(through `XDG_CONFIG_HOME` or `HOME` in its own settings) is not trusted for the two exemption
files. The exact matching rules: the header of
[`plugins/guards/scripts/pre_tool_personal_data.py`](../plugins/guards/scripts/pre_tool_personal_data.py).

### The sandbox-network guard (`--guards sandbox`)

With Claude Code's Bash sandbox on, a call runs outside the sandbox only when every part of it
matches an entry of `sandbox.excludedCommands`. A call such as `cd <repo> && gh pr list` never
matches: it runs inside, `gh` or `ssh` fails there, and the agent retries it with the sandbox
disabled. The guard turns such a call away and names the lone call that does the same and
matches one of the person's entries, for example `gh pr list -R owner/repo`. It only refuses: it
never lets a call run that would not run without it.

It does nothing until `sandbox.enabled` is true in `~/.claude/settings.json` and
`excludedCommands` lists the network commands (for example `gh *`, `ssh *`, `git push *`), and
nothing on native Windows, where Claude Code has no sandbox (WSL2 works as Linux). Scripts that
reach the network after a `cd` can be listed, one absolute path pattern per line (`*` allowed),
in `${XDG_CONFIG_HOME:-~/.config}/agentic-github-flow/sandbox-scripts`. An entry such as
`rsync *` also lets local copies run outside the sandbox: add only the entries the person means.
What it refuses and the forms it teaches: the header of
[`plugins/guards/scripts/pre_tool_sandbox_network.py`](../plugins/guards/scripts/pre_tool_sandbox_network.py).

### The Google Cloud guard (`--guards gcloud`)

An agent on the machine can use the person's Google Cloud login: `gcloud`, `gsutil`, `bq` and
`cloud-sql-proxy` act with their credentials on live projects and data. The guard makes each of
those commands wait for the person's approval (Claude Code: an ask rule; Codex: a prompt rule),
and in Claude Code denies reading and editing the gcloud configuration folder
(`~/.config/gcloud/`; on Windows `%APPDATA%\gcloud`, not measured there), which holds the login
and the Application Default Credentials file. With Claude Code's Bash sandbox on
(`sandbox.enabled`, which this guard does not switch on) the deny also closes the folder to every
Bash command, so an approved command runs only outside the sandbox, which asks again. Without the
sandbox the deny covers only Claude's own file tools, not Bash; the installer says so.

It is not complete: rules match a program's name at the start of a command, so a full path
(`/opt/homebrew/bin/gcloud`), a wrapper (`env`, `bash -c`), a variable in front
(`CLOUDSDK_CORE_PROJECT=prod gcloud …`) and other tools on the same credentials (Terraform's
Google provider, `docker push` through gcloud's credential helper, `kubectl`, `firebase`) are
not asked about; with the sandbox on the credentials stay closed to them inside it, without it a
command such as `cat` reads them. Codex rules cannot close a folder; a folder moved with
`CLOUDSDK_CONFIG` or a key file named in `GOOGLE_APPLICATION_CREDENTIALS` is not covered; and a
database client such as `psql` to a production database looks like one to a local database. The
written rules still bind there. The rules: the `gcloud` key of
[`plugins/guards/policy/claude-permissions.json`](../plugins/guards/policy/claude-permissions.json)
and [`plugins/guards/policy/gcloud.rules`](../plugins/guards/policy/gcloud.rules).

**Setting up gcloud.** Give the person these steps, each with Google's page
(docs.cloud.google.com, read 2026-11-19), to run in their own terminal (in Claude Code,
`! <command>`): the logins open a browser, and they are theirs.

1. **Install** the gcloud CLI: *Install the Google Cloud CLI* (`sdk/docs/install-sdk`). macOS
   and Linux: the archive and `./google-cloud-sdk/install.sh`; Windows:
   `GoogleCloudSDKInstaller.exe`; then a new terminal.
2. **Sign in and pick the project:** `gcloud init` signs in and sets a default configuration,
   including the project; later `gcloud auth login` and `gcloud config set project <project id>`
   (*Authenticate for the gcloud CLI*, `docs/authentication/gcloud`; *Managing gcloud CLI
   configurations*, `sdk/docs/configurations`). A configuration per project
   (`gcloud config configurations create <name>`) keeps a production project from being the
   default by accident.
3. **Application Default Credentials**, for code and tools on the machine that call Google (the
   Cloud SQL Auth Proxy, client libraries): `gcloud auth application-default login` (*Set up ADC
   for a local development environment*, `docs/authentication/set-up-adc-local-dev-environment`).
   It writes `application_default_credentials.json` into the gcloud folder. No service account
   key file.
4. **Cloud SQL through the Auth Proxy** (*Connect using the Cloud SQL Auth Proxy*,
   `sql/docs/postgres/connect-auth-proxy`): download the `cloud-sql-proxy` binary for the
   system, then `./cloud-sql-proxy --port 5432 <instance connection name>` (the name is
   `<project>:<region>:<instance>`; `gcloud sql instances describe <instance>` shows it), and
   `psql "host=127.0.0.1 dbname=<db> user=<user>"`. With IAM database authentication add
   `--auto-iam-authn`; the database user is then the person's full e-mail address (*Log in using
   IAM database authentication*, `sql/docs/postgres/iam-logins`). The account needs the Cloud SQL
   Client role (`roles/cloudsql.client`).

With the guard, every one of those commands an agent proposes asks first; the person's own
terminal is not affected. A proxy to a production database stays in the person's own terminal
too: an agent's database client connected to it looks like any other, and the guard does not
see it.

### Issue chats without a click (`--with issue-chats`)

For chains of issue chats that run without a click, allow the start script alone in
`~/.claude/settings.json` (`permissions.allow`), never `claude --bg` itself, which would also
admit `--dangerously-skip-permissions`:

```json
"Bash(python3 ~/.agentic-github-flow/plugins/issue-chats/scripts/start_issue_chat.py *)"
```

Claude Code loads the plugin's skills from the clone, so the agents run the script by that path,
which stays the same across versions. Write the rule, and a `sandbox.excludedCommands` entry
for the script, in each spelling the agents use: with `~` and with the home folder written out.
Never name the copy under `~/.claude/plugins/cache/`. Where the person grants unasked pushes or
switches automatic merging on (below), allow the core plugin's two gates the same way, never
`git push`, `gh pr ready` or `gh pr merge` themselves:

```json
"Bash(python3 ~/.agentic-github-flow/plugins/core/scripts/push_branch.py *)",
"Bash(python3 ~/.agentic-github-flow/plugins/core/scripts/merge_pr.py *)"
```

An allow rule for `mcp__ccd_session_mgmt__archive_session` lets chats archive themselves without
a click; the plugin's hook still denies any archive whose worktree is not clean and on GitHub
(or, in local-main mode, landed). The automatic start of the next chat needs the Claude Code
desktop app, the `claude` CLI logged in (`claude auth login`) and `gh`; it was measured on macOS,
is unmeasured on Linux and refused on Windows. The full list of what a chain needs: the
`issue-handover` skill's [method.md](../plugins/issue-chats/skills/issue-handover/method.md),
§7.

### Codex as the worker (issue chats, opt-in per repository)

A repository whose `## Issue chats settings` has the row `codex worker` (a label, a Codex model
and optionally a time limit per turn) lets a Claude issue chat hand the implementation of an
issue with that label to Codex, while the chat keeps the issue, the questions to the person, the
review and the push (method.md §4 *Codex as the worker*). Codex must be installed and logged in
(`codex login`); the route runs on macOS only, the one system its read deny list is measured
on. The chat runs Codex through one script, which fixes Codex's sandbox and never passes a
`--dangerously-*` option:

- **Writes:** only a job folder of the script's own under
  `~/.cache/agentic-github-flow/codex-worker/`, never the chat's repository. Its files are
  copy-on-write clones of the worktree's and cost no disk. Once the worktree is removed, the
  chat's `codex_worker.py --sweep` removes its jobs and logs.
- **Reads:** the disk, except all of `~/.claude`, `~/.ssh`, `~/.aws`, `~/.netrc`, `~/.gnupg`,
  `~/.config/gh`, Claude Code's folders under `/private/tmp`, and any `.env`, `.env.*`, `*.pem`,
  `*.key` or `*.p12` file, plus, read at each run, every `Read(...)` deny rule and
  `sandbox.filesystem.denyRead` entry of `~/.claude/settings.json`, the managed settings and the
  project's `.claude/settings.json` and `settings.local.json` in the worktree the worker is
  given. The floor and the person's own settings hold for every run; a project's read limits
  bind only a run on that project's worktree, not a chat that hands the worker another one. A
  deny rule must be written as `**/name`, `~/path` or `//path`, a denyRead entry as `~/path`,
  `//path` or, in the person's own settings, `/path` (each with an optional trailing `/**`);
  another form refuses the run, as do `sandbox.credentials`,
  `permissions.blockReadsOutsideWorkingDirectories`, a plugin copy under `~/.claude`, and a
  settings source the script does not read: an MDM profile (`com.anthropic.claudecode.plist`
  under `/Library/Managed Preferences`), server-managed settings
  (`~/.claude/remote-settings.json`), or `CLAUDE_CONFIG_DIR`, `CLAUDE_CODE_MANAGED_SETTINGS_PATH`
  or `CLAUDE_CODE_REMOTE_SETTINGS_PATH` set. A session started with `--settings <file>` can add
  read limits the script cannot see. Everything else Codex may read can go to OpenAI: send it no work on a machine whose files may
  not.
- **No network**, approval `never`, a time limit per turn, after which the script kills what is
  left of it.
- **The person's Codex configuration does not apply in these turns** (`~/.codex/config.toml`,
  its rules, MCP servers and hooks), because each can run a command outside Codex's sandbox.
  **Nor do the ChatGPT account's apps (connectors) and Codex plugins:** they are on whenever
  Codex is logged in with ChatGPT, whatever the configuration, and their tools run outside
  Codex's sandbox with the account's connections, so the script turns them off for each turn.

The script itself runs outside Claude Code's sandbox (Codex needs the network and writes
`~/.codex`). It therefore runs no git and opens no file that the chat or Codex wrote: the setup
of a job, the reading of the prompt and the export of Codex's commits as a git bundle all run
inside Codex's sandbox, and the chat imports the bundle inside its own with `codex_import.py`,
which refuses submodules, hooks and hook managers' files, and changes to `.claude/`,
`.codex/`, `.agents/`, `.mcp.json`, `CLAUDE.md`, `AGENTS.md` and `AGENTS.override.md`, and runs
no hook while it fast-forwards. It takes no program to run (`codex` and `python3` come from
PATH). Three conditions are the person's: Claude Code's sandbox must not make
`~/.cache/agentic-github-flow`, the installed plugin folder or a folder on PATH before `codex`'s
and `python3`'s writable, and the rule below is spelled with `-I`, so that Python reads no
`PYTHONPATH`. On the person's yes, allow that script alone and exclude it from the sandbox, in
each spelling the agents use, never `codex exec` or `codex sandbox` itself and never
`codex_import.py` or `codex_job.py`:

```json
"Bash(python3 -I ~/.agentic-github-flow/plugins/issue-chats/scripts/codex_worker.py *)"
```

and in `sandbox.excludedCommands`
`"python3 -I ~/.agentic-github-flow/plugins/issue-chats/scripts/codex_worker.py *"`. Without them
each Codex turn asks. Codex's work counts against the person's Codex usage limits. OpenAI's
Codex plugin for Claude Code (`openai/codex-plugin-cc`) was reviewed and tried for this (#103)
and is not used: it does not run inside the sandbox either, answers every approval with an
error, may delegate to Codex unasked in every session, and drops its jobs when the session
ends.

### Worktree clones on macOS

Each task gets its own worktree, made by the core plugin's `new_worktree.py`. On macOS (APFS)
its tracked files are copy-on-write clones of the primary checkout's by default, so a repository
with gigabytes of tracked assets costs no extra disk per parallel task; the result is the same
checkout `git worktree add` gives. To switch it off for good, set this in the environment the
agents' shells start from, for example `~/.zshenv`:

```bash
export AGENTIC_GITHUB_FLOW_CLONES=0
```

Per run, `--no-clones` does the same. `clone_dedupe_worktree.py --apply <primary> <worktree>`
turns the unmodified large files of an existing worktree into clones. `du` counts clones in full;
`df` shows the disk they save. On Linux and Windows nothing changes.

### Per repository

These live in each repository, not on the machine. An agent sets them up with the person's
agreement, through a branch like any other change:

- **The `pre-push` hook:** `cp ~/.agentic-github-flow/templates/pre-push "$(git rev-parse --git-path hooks)/pre-push"`.
  It refuses force pushes, tag moves and unmerged deletions, and every push whose commits carry
  a secret or personal data. Unasked pushes (below) need it. Its header in
  [`templates/pre-push`](../templates/pre-push) owns the details.
- **The secrets block of `.gitignore`:** [`templates/gitignore-secrets`](../templates/gitignore-secrets).
- **The landing mode and automatic merging,** in the repository's `HANDOFF.md`. The mode is
  detected at every landing (pull request or local main); a repository can fix it, and name a
  landing branch other than its default branch. A value cell holds the value alone:

  ```markdown
  ## Landing settings

  | Setting | Value |
  |---|---|
  | landing | `auto` |
  | landing branch | `main` |
  | automatic merge | `off` |
  ```

  `landing` takes `pull request`, `local main` or `auto`; `local main` cannot overrule a server
  that requires pull requests. `automatic merge` is off by default and an overlay cannot switch
  it on; with `on`, an agent merges its own pull request through `merge_pr.py`, only with every
  required check green, an approving review of the head commit by another agent, the overlap
  result in the body, and no change to a protected path. The rules: the headers of
  [`landing.py`](../plugins/core/scripts/landing.py) and
  [`merge_pr.py`](../plugins/core/scripts/merge_pr.py) (`EXCLUDED` lists the protected paths).
- **The push grant:** the line `standing grant | push_branch.py` (a table row works too) in the
  repository's `HANDOFF.md` §Standing permissions, or in the person's own overlay file outside
  the repository and outside the clone, lets an agent push its own task branch and open its pull
  request without asking, through `push_branch.py`, in pull-request mode only, with the `pre-push`
  hook installed and no change to a protected path. Whatever the script refuses still asks. An
  overlay without that line, an employer's for example, grants nothing. The rules: the header of
  [`push_branch.py`](../plugins/core/scripts/push_branch.py).
- **Issue chats** are switched on per repository by a `## Issue chats settings` section in its
  `HANDOFF.md`: the template is in the `issue-handover` skill's
  [method.md](../plugins/issue-chats/skills/issue-handover/method.md), §1.

## 6. When a step fails

- **A `FAIL` on a plugin or marketplace step:** managed settings from IT can block a plugin
  marketplace or set permissions that win over the person's own. Report the line as printed and
  tell the person to ask IT. Never work around it (no hand-copied plugin folders, no edits to
  managed settings).
- **`STOP`:** nothing was changed. Report the reason it gives (a symlinked rules file, a folder
  that is no clone, a missing Python or git) and what the person can do about it.
- **`no client found`:** neither Claude Code nor Codex is installed; install one first.
- **`skip … plugins not installed`:** the client's folder exists but its command is not on
  `PATH`. Once it is, run `install.sh --update`, or name it with `--claude-bin` or `--codex-bin`.
- Anything else: report the output as printed and stop. Do not retry with other options to get
  past it.

## 7. Update and uninstall

```bash
~/.agentic-github-flow/install.sh --update
```

```bash
~/.agentic-github-flow/install.sh --uninstall
```

`--update` pulls the clone and repeats what was installed. `--uninstall` removes exactly what the
installer recorded that it added; it leaves the person's own lines in `~/.claude/CLAUDE.md` and
`~/.codex/AGENTS.md` byte for byte as they were. It leaves the clone, the backups of step 3, the
settings files of step 5 and anything made per repository: delete those afterwards, with the
person's agreement and the system's trash, to remove it completely. Neither combines with `--with`, `--guards` or `--overlay`; to change what is
installed, run the installer without `--update` (step 3). On Windows, use `install.ps1` with the same options. After either, start a
new session in each client.

## Other ways to install

- **From a plugin directory:** the plugins can also be installed on their own from a plugin
  directory or marketplace. Then the person gets the skills without the always-loaded rules: no
  plugin system can ship those. Run the installer to get the rules too.
- **For administrators:** there is no central rollout. An administrator who wants every Claude
  Code user to have the marketplace can declare it in managed settings (`extraKnownMarketplaces`,
  `enabledPlugins`; see Anthropic's documentation on settings and plugin marketplaces). The
  always-loaded rules still need the installer, or a managed `CLAUDE.md` that holds the text of
  `rules/core.md`.
