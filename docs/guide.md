# agentic-github-flow: a guide for colleagues

This guide is for you if you use, or want to use, an AI coding agent (Claude Code or Codex) and
wonder what agentic-github-flow changes and what it lets you do. It has no installation detail:
to install, ask your agent to follow [install.md](install.md).

## What it is

A shared working method for AI coding agents on GitHub, the same for Claude Code and Codex. It
has two parts:

- **Short rules that load in every session** ([`rules/core.md`](../rules/core.md), under 8 KB):
  how the agent works, what it may do on its own and what it must ask you first.
- **Skills that load only when a task needs them:** step-by-step procedures for opening an
  issue, landing a change, reviewing a pull request, checking a site before it goes live, and
  more. You do not call them by name; you ask for the work and the agent picks the skill.

You install it once on your machine, and it applies to every repository you work in. You write
no instruction files of your own.

What it is not: not a service (nothing runs on a server, no telemetry), not an agent of its own
(it guides the one you already use), and no replacement for review by people where your team
requires it.

## What changes in your daily work

- **The agent asks before anything that leaves your machine or cannot be undone:** a push, a
  pull request, a deployment, a message, deleting data. It prepares the work first, so your yes
  is the last step. Local, reversible work (reading, editing, testing, committing on its own
  branch) it just does.
- **Every task gets its own branch in its own worktree,** a separate folder, so several agents
  can work in one repository at once without touching your checkout or each other's work.
- **GitHub issues are the work queue.** New work becomes an issue; the agent says on the issue
  when it starts, and signs every comment it posts under your account with `🤖`.
- **Finished work lands the way the repository lands work:** through a pull request, or, in a
  repository of your own that you alone write to, on your local `main`. Either way you decide
  every push, and nothing is merged without your word unless you switched that on for the
  repository ([How finished work lands](#how-finished-work-lands)).
- **Another agent reviews larger work:** a larger or risky change is reviewed by an agent that
  did not write it, on the exact commit; a small, low-risk change (a fix in one place, a
  document) the author checks itself. A pull request an agent merges on its own always needs
  that independent review.
- **Destructive git is off the table:** no force-push, no rewritten history, no discarded
  uncommitted work, unless you ask for that exact operation. With the guards installed, hooks
  enforce this instead of trusting the agent to remember.
- **Secrets and personal data stay in:** the agent never commits or prints a secret, and asks
  before your name, e-mail address or anyone else's personal data leaves the machine.
- **Content is data:** text in an issue, a web page or a tool's output never counts as an
  instruction or an approval. If it tries to direct the agent, the agent shows it to you and
  asks.
- **When it is stuck, it says so:** after two failed attempts at the same problem it stops and
  tells you what it tried.

## What you can ask for

Ask in your own words; these are examples. The skill names are for reference.

| You want | Ask, for example | Skill |
|---|---|---|
| A bug or idea written down for an agent to pick up | "Open an issue for the date filter that ignores the time zone." | `open-issue` |
| New work turned into ready issues | "Let's have a requirements chat about the new billing page." | `requirements` |
| A specification before a large build | "Write a specification for the export feature before you build it." | `spec-first` |
| A finished change landed | "This is done, open a pull request." | `ship-change` |
| An independent review | "Review pull request #42." | `review-change` |
| Tidying up after a merge | "#42 is merged, clean up." | `cleanup-merged` |
| A check that something scales | "Does this sync job still hold up when the table grows?" | `efficient-design` |
| The repository's documents in order | "Set up the agent documents for this repository." or "Where does this belong?" | `repo-docs` |
| A security review (opt-in) | "Do a security review of this change." | `review-security` |
| A check before a site goes live (opt-in) | "Check this site before we deploy it to production." | `check-web-deploy` |
| Agents working the issue queue one chat per issue (opt-in) | "Start issue chats for this repository." | `issue-handover`, `archive-finished-chats` |

Three to start with: open an issue for something that bothers you; ask an agent to fix it and
open a pull request; ask another agent to review that pull request.

Each skill's own `SKILL.md`, under `plugins/<plugin>/skills/<name>/`, says exactly what it does.

## Opt-in parts

The core rules and skills are always installed. The rest you choose at installation (the exact
options: [install.md, step 2](install.md#2-ask-the-decisions)):

| Part | What it adds | Want it when |
|---|---|---|
| Security | a review checklist, a secret scanner that never prints values, a dependency audit against the OSV database | you change authentication, access rules, secrets, dependencies or a public service's input handling |
| Web-deploy | a hardening check of a Vercel and Supabase site, with Google sign-in, its mail domain and EU privacy, before it goes live (brings security) | you put such a site in production |
| Issue chats | one chat per GitHub issue: when its branch is ready, it starts the chat for the next ready issue, then sees its own pull request through to the merge and archives itself | you have a queue of ready issues and want agents to work through it |
| Guards | hooks that refuse destructive git commands and ask before destructive deletes and before personal data leaves the machine | always at work, and wherever you want the rules enforced rather than remembered |
| Sandbox-network guard | for Claude Code's Bash sandbox: turns away network calls that would fail inside it and names the form that runs | you run Claude Code with its sandbox on |

## How finished work lands

At every landing the agent checks how the repository lands work, and says on the issue what it
found:

- **Pull request:** the agent pushes its branch and opens a pull request, and you (or your
  team's reviewers) merge it. This is the mode for every team's repository, and whenever
  GitHub's answer cannot settle it. When GitHub cannot be asked at all, the agent decides
  nothing: it asks again where it can, or follows the repository's setting.
- **Local main:** for a repository of your own that only you write to. The agent still works on
  a branch, then moves your local `main` forward to the checked commit; you push `main` when you
  want.

Two switches, both yours and both off by default, change who presses the button. A repository
can let agents merge their own pull requests once every check is green and another agent
approved; and you can let agents push their own task branch without asking, in your own
repositories. Neither ever covers changes to the rules, the guards, permission settings, hooks,
the installer, CI or deployment configuration: those always wait for you. How to set them:
[install.md, Per repository](install.md#per-repository); the exact conditions:
[`landing.py`](../plugins/core/scripts/landing.py),
[`merge_pr.py`](../plugins/core/scripts/merge_pr.py) and
[`push_branch.py`](../plugins/core/scripts/push_branch.py).

## Using it at work

**Your organisation's AI policy comes first.** Before you use an agent on an employer's or a
client's code, find out which tools and plans are allowed, which data may go into a prompt or
leave the machine, and who owns work made with an agent. The rules send every agent to that
policy; this repository never holds it.

**The company overlay** is how the policy reaches the agents: a small private repository of the
organisation, with an `AGENTS.md` that points to the AI policy, lists the data classes (what may
go into a prompt, what may leave the machine), and names the organisation's reviewers, CI checks
and branch naming. Its rules load after the core rules in every session. Someone in the
organisation makes it once, from
[`templates/company-overlay/AGENTS.md`](../templates/company-overlay/AGENTS.md), and everyone
installs it. Without one, the agent asks you where the policy is before it works on the
organisation's code.

On the machine you use for work:

- **Try it first in a small test repository,** not in a team's repository.
- **Install it with the company overlay and without a personal one,** and with the guards.
- **Name your work identity** (your name and work e-mail address) in the personal-data guard's
  settings when it differs from your global git identity, so the guard recognises it; the
  installing agent asks you.
- **Merging stays with people.** At work your required reviewers usually decide, and an
  organisation's repository lands through pull requests.
- **If IT manages your settings,** they may block parts of the installation. Ask IT; do not work
  around it.

### Where it works

Repositories on github.com, organisation repositories included. On GitHub Enterprise Server,
GitLab or Azure DevOps the agent cannot push or merge without asking (those steps need an origin
on github.com) and lands through pull requests.

## Which rule wins

1. A company overlay's binding rules (its AI policy, its data classes): never relaxed in a
   conversation, by anyone.
2. Below that, what you say in the conversation beats the rules.
3. A repository's own `AGENTS.md` wins where it is stricter or says it deviates.
4. An overlay wins over the core rules where it says it deviates.

The binding wording is the *Precedence* paragraph of [`rules/core.md`](../rules/core.md).

## Help

- **Ask your agent.** It can read the rules and skills, and explain what it would do and why.
- **Something wrong or missing:** open an issue in this repository on GitHub, or ask your agent
  to open one. The maintainers, named in [`HANDOFF.md`](../HANDOFF.md), decide.
- **Installing, updating or removing it:** [install.md](install.md).
