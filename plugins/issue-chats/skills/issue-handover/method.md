# Issue chats: one issue per chat, the chat that hands itself over

A method for a repository whose work is its GitHub issues: each chat takes one ready issue,
claims it, works on its own branch in a new worktree until the branch is ready to push, picks
the next ready issue, starts the chat for it, sees its pull request through review and CI to the
merge and then archives itself, or, in local-main mode, archives itself once its work has landed
on local main. Several such chains run at once, at most five (§1). *The guide*
below is Anthropic's <https://code.claude.com/docs/en/best-practices>, cited by section.

This file owns the method, the repository settings, the chat title form, the limit of five
chains and how side chats end (§4). The procedures are skills: `issue-handover` (pickup, claim and how a chat ends, in
[SKILL.md](SKILL.md)), `archive-finished-chats` (how finished chats leave the sidebar), and in
the core plugin `open-issue` (how an issue becomes ready), `requirements` (how new work is
specified and split into ready issues) and `ship-change` (review, checks, overlap check, the
push and the pull request). The scripts are in this plugin's `scripts/` folder: `next_issue.py`,
`start_issue_chat.py`, `chat_archivable.py` and the hook `archive_guard.py`; the overlap check
is the core plugin's, run as `ship-change` names it. Codex follows the same lifecycle with its
own chat tools: [the Codex adapter](codex.md).

**In the pull-request flow.** The core rules hold here unchanged: work on a branch in a
worktree; push on the user's yes, or under a standing grant through `push_branch.py`; mark ready
and merge on the user's word for that pull request, or through `merge_pr.py` where the user
switched automatic merging on in the repository (`ship-change` steps 6 to 8). So a chat's task
ends when its branch is *ready to push*: the chat hands over then, without waiting for the push
or for CI, so the chain goes on. It stays to see its own pull request through (`ship-change`
step 8: the CI monitor, an independent review, fixes as new commits, the merge) and leaves the
sidebar only after the merge and its cleanup.

**In local-main mode** (the core plugin's `landing.py` decides per repository, `ship-change`
step 1): a chat's task ends when its work has *landed* on the local landing branch (the
`ship-change` skill's `local-main.md`, §1, or §2 where an agent that did not write it reviews and
lands it). The chat records the landing, hands over and archives itself in that same turn: its
commits are on local main, where the primary checkout keeps them, so the archive loses nothing.
The push of the landing branch stays the user's word, given in any chat (`local-main.md` §5);
its cleanup closes the landed issues.

## 1. The settings section switches it on

A repository works by this method when its `HANDOFF.md` has a section `## Issue chats settings`.
The section counts as it stands on the default branch: adding or changing it is a pull request
like any other, merged by the people who decide for the repository, and it applies once merged.

That section is also the **standing permission** for the repository: a chat picks and claims
the next ready issue, starts the chat for it and archives chats that pass the worktree check,
without asking again, and in local-main mode lands the chat's work on local main (local work).
It never covers a push, a merge or marking a pull request ready: those stay on the user's word
for each push and each pull request, unless a standing grant covers the push of a chat's own
task branch, or the user switched automatic merging on in `## Landing settings`
(`ship-change` steps 1 and 6 to 8). Deleting the section switches all of it off.

The skills read their values from it; a row left out takes its default:

| Setting | What it holds | When it is left out |
|---|---|---|
| model and effort | the model id and effort level every issue chat starts on (`claude --model`, `--effort`); a change applies from the next start | the starting chat's own model and effort |
| ready label | the label that makes an issue ready for pickup | the default the `open-issue` skill states |
| requirements label | the label of new work whose requirements are open | the default the `open-issue` skill states |
| question label | the label of an issue that holds a question for the user | `needs-user` |
| area labels | labels a chain may be limited to (`--area`); they own nothing | none |
| spread over areas | `yes` or `no`; after `yes`, the area labels in backticks that a pick spreads over, up to the first `;` (the rest is a comment), without them every label in backticks of the row `area labels` (*Spreading over areas* below) | `no` |
| sidebar section | the desktop app sidebar section the chats file themselves under | the repository's name |
| worktree tool | the command, run from the primary checkout, that makes a new worktree for `<issue>-<short name>` | the core plugin's `new_worktree.py <issue>-<short name>`, as the `ship-change` skill names it (in local-main mode it starts from landings not pushed yet); or, in pull-request mode, `git worktree add -b agent/<issue>-<short name> ../<repo>-worktrees/<issue>-<short name> origin/<default branch>` |
| title prefix | what the chat title puts before `#<issue>` (§2), and older title forms that still count as this repository's issue chats when archiving | none |
| context limit | the context size at which a chat hands over | none: the chat judges |
| start reading | what every chat reads at its start besides its issue: named sections, the repository's reading map | none |
| ready extras | what the repository adds to the definition of ready of the `requirements` skill | none |
| start extras, hand-over extras | repository steps at a chat's start and before it ends | none |

**Chains at once is not a repository setting:** at most five issue chats work at the same time
in a repository, counted with those already working. A chat whose branch waits for the push,
whose pull request waits for review, or whose work landed on local main no longer counts.

**Spreading over areas.** With `spread over areas` set to yes, a chain that picks prefers the
most important ready issue from an area no working chat is in yet. An area is taken while an
open issue with its label is assigned (the claim) and its newest claim or hand-off comment
(right after the signature: `claimed for chat`, `ready to push:`, `pull request opened:` or
`landed on local <branch> at`, skill `issue-handover`) is a claim. An issue whose branch is ready
to push, or whose work landed on local main, stays assigned until the merge or the verified push
closes it, but no chat works on it any more. `priority: critical` and
`priority: high` still go first, even in a taken area. An issue counts as in a free area when it
carries one of the listed labels and none of them is taken. When every area with ready work is
taken, the pick is the normal one; an area without ready work is skipped, never waited on. A
chain limited to one area (`--area`) picks normally within it. `next_issue.py` owns the order;
off, it is the normal one: critical, high, then the rest, oldest first.

The section, to copy into `HANDOFF.md` and fill in:

```markdown
## Issue chats settings

The method: the `issue-handover` skill's method file (agentic-github-flow-issue-chats plugin).
This section switches on its standing permission in this repository: picking and claiming the
next ready issue, starting its chat, and archiving chats that pass the worktree check. Pushes,
merges and ready-marking follow the `ship-change` skill: the user's word, unless a standing
grant or the `automatic merge` row of §Landing settings says otherwise.

| Setting | Value |
|---|---|
| model and effort | `<model id>`, `high` |
| ready label | `agent-ready` |
| area labels | none |
| spread over areas | `no` |
| sidebar section | `<repository name>` |
```

## 2. The chat title form

The sidebar shows which GitHub issue each chat works on. The parts are joined by ` · `: an issue
chat `<title prefix>#<issue> · <topic>`; a requirements chat
`<title prefix>Requirements · #<parent issue> · <topic>`, titled
`<title prefix>Requirements · new · <topic>` until it has created the parent and renamed at once
with `set_session_title`. `<issue>` is the issue the chat works on; work without an issue gets
one first (skill `open-issue`). `start_issue_chat.py` refuses a title of any other form
(`--prefix` carries the title prefix). A chat the user types in, for an overview or to start
chains, is not an issue chat and needs no form. `archive-finished-chats` checks requirements
chats like any other issue chat: the newest chat of each open issue stays, and any other one
goes once its worktree passes the worktree check.

## 3. One issue, one chat

1. **A task is one issue, ready to push or, in local-main mode, landed:** committed, reviewed by
   an agent that did not write it where `ship-change` asks for that, the overlap check run, the
   checks green, the pull request text prepared (`ship-change` steps 1 to 5), or in local-main
   mode the work landed (`local-main.md` §1 or §2). It runs in its own chat, which starts with an
   empty context. Unrelated work never shares a chat (the guide, *Manage context aggressively*,
   *The kitchen sink session*). Inside the task the context may grow; at the context limit the
   chat finishes the step it is on and hands over instead of starting a new step.
2. **Every brief carries its check:** the end state and the command that proves it, so the agent
   iterates until it passes and shows the output (*Give Claude a way to verify its work*).
3. **Two agents per larger change,** the reviewer looking only for defects in correctness and
   missed requirements (`ship-change` step 1; *Add an adversarial review step*). Small changes
   take the small-change route.
4. **Plan only what needs a plan.** Open requirements get an interview and a specification
   first (`spec-first`; *Explore first, then plan, then code*, *Let Claude interview you*); a
   requirements chat does this and opens ready issues (skill `requirements`). A chat that hits
   open requirements in its issue gives it the requirements label in place of the ready label,
   removes its claim, says on it what is open, and moves on (`issue-handover` step 3).
5. **Briefs name sections, not whole documents; investigations go to a subagent** with a narrow
   question and a bounded report (*Use subagents for investigation*, *The infinite exploration*).
6. **After two failed corrections, a new chat** with a better statement of the task (*Course-
   correct early and often*).
7. **At most five chains at once** (§1). Nobody polls. A chat waits for long runs in the
   foreground of its turn, not for a background notification (§4).
8. **No standing coordinator chat.** The user starts chains from a chat they type in (§7); for an
   overview they start a short chat.
9. **Work in flight stays in its worktree.** A chat that takes over a branch in flight, named in
   the issue's newest state comment, works in that branch's worktree; its own new worktree stays
   unused until the `cleanup-merged` skill removes it.
10. **Review comments on an open pull request** are work on the same branch, done by the chat
    that opened it, which stays until the merge (§4) and is woken by the CI monitor where the
    client has one. When that chat is gone, a chat takes the branch over as work in flight
    (item 9): the user opens a chat on the issue, or a running chat starts one, with the branch
    and its worktree named in a state comment (when that worktree is gone, a new one on the
    branch from `origin/<branch>`). An archived chat is not unarchived for this.

## 4. The chat lifecycle

Each issue chat runs this:

1. **Start:** set its title to the title form (§2), file itself under the sidebar section and
   work in its own worktree (the new one the hand-over made, or the one in flight its issue
   names), as the start brief says first. A chat that a card started detaches itself first
   (`detach_session "self"`). Then, in this order:
   1. **Read** the issue with its comments (the newest state comment and the claim), the
      sections it names, and the settings' start reading. The client loads the repository's
      `AGENTS.md` itself; a brief does not send the chat to read it, or any document whole
      (§3 item 5).
   2. **Check the claim:** the issue is assigned and its newest claim comment names this chat's
      title and worktree. A claim for another chat or branch means a second chat on one issue:
      stop and report. A chat started without a claim (the user typed it, a card) runs the
      pickup of `issue-handover` step 3 for its own issue first.
   3. **The design note,** when the claim names an overlap or the issue is labelled
      `type:design-first`: a short signed comment on the issue before any code (§5).
   4. **Housekeeping:** run the start extras; run `archive-finished-chats` for this repository.
   5. **The requirements stop:** a task that turns out to have open requirements is not built
      (§3 item 4).
2. **Work:** the one task, with its check, to a branch ready to push (`ship-change` steps 1 to
   5, the overlap check included), or in local-main mode landed on local main, in the
   foreground of the turn the start brief began.
3. **Hand over** (skill `issue-handover`), in that same turn: comment `ready to push:` on the
   issue (it stays open and assigned until the merge closes it); pick the next ready issue
   (`next_issue.py`) and run the overlap check on its paths; start the next chat on the
   settings' model and effort, claim its issue and hand it a complete brief; then ask the user
   for the push of this chat's branch (`ship-change` step 6) and end the turn. Under a standing
   grant for the push the chat pushed and opened the pull request before the pick (the comment
   then opens `pull request opened: #<n>`): it tells the user and goes on with item 4 in the
   same turn. In local-main
   mode the comment opens `landed on local <branch> at <commit>`, the chat tells the user what
   landed in place of asking for a push, ends its own live work and archives itself (item 4
   does not apply).
4. **Push, see it through, and leave:** when the user says yes, in a later turn, or right
   after a push under a grant, the chat pushes and opens the pull request (`ship-change`
   step 7) and comments `pull request opened: #<n>` on the issue. Then `ship-change` step 8:
   the CI monitor on, a review subagent given only the pull request number, findings as new
   commits and a new review, the wait for CI; with automatic merging switched on,
   `merge_pr.py --ready` merges, otherwise the chat tells the user the pull request is ready to
   merge and waits for their word in a later turn. After the merge: `cleanup-merged`, a signed
   `merged: #<n> at <commit>` comment on the issue, its own live work ended, the worktree check,
   the archive. Without a yes for the push it stays; the user can say push in it at any time, or
   tell it what to change first.

Why that order. The claim and the brief name the issue, so the next chat reads its state from
GitHub, not from a document. The CLI starts the next chat, not this one's `start_session`, so it
is not this chat's child: archiving this chat does not take it along and nothing needs detaching
(a session that `start_session` starts hangs under its starter until detached, and archiving a
session also archives its finished side sessions). Archiving removes the chat's app-made
worktree, so the worktree check comes right before it, and the check passes only once the
branch is on GitHub: a chat whose work exists only in its worktree never leaves the sidebar. In
local-main mode it passes once the work is on the local landing branch, which the archive does
not touch.

The app refuses to archive a session with live background work, so a chat that kept a subagent
or a background task of its own running stayed in the sidebar after its hand-over until the user
archived it by hand. So before every archive of itself the chat ends its own live work
(`issue-handover`, *End your own live work*). A run whose result the work still needs (a remote
gate, a capture) keeps the chat, as unfinished work does; a session it started is a side chat
(*Side chats* below).

A chat that handed its unfinished issue to a successor working on its own branch (started from
this chat's head) passes once that branch is pushed: the check then finds HEAD in another branch
of origin that GitHub still has, and, as for every `ok`, proves with the reflogs that no commit
only this worktree held is lost. A successor's branch only on this machine does not count, in
either mode.

### The next chat starts in the background

Measured with Claude Code CLI 2.1.292 and the desktop app on macOS: the desktop app refuses
`start_session` with `"user_asked"` in every turn that did not begin with a message the user
typed, and a chat's turns begin with another chat's start brief or with subagent notifications.
What works, from Bash in a turn a notification began, with no click and no prompt
(`start_issue_chat.py` runs it, `issue-handover` step 5):

- `claude --bg --name <title> --model <model> --effort <effort> "<prompt>"`, run in a fresh
  worktree, starts a background session on that model and effort and prints its short id;
  `claude agents --json` lists it with `sessionId`, `name` and `status`, which turns `idle` once
  it has answered;
- after `claude stop <short id>`, `script -q /dev/null claude --desktop --resume <sessionId>`
  opens it in the desktop app as `local_<sessionId>` (plain `--desktop` refuses without a
  terminal); started in the starting chat's own worktree, the later message failed with "this
  session's branch is checked out somewhere else", hence the fresh worktree;
- `send_message` to `local_<sessionId>` with the brief came back "delivered; its turn has
  started"; the new chat then ran `set_session_title` and `move_sessions ["self"]` into the
  repository's section.

It needs the terminal CLI logged in with the user's own account (`claude auth login`;
`claude auth status` shows `"loggedIn": true`) and, for an unattended chain, one narrow allow
rule for `start_issue_chat.py` (§7): allow rules on the bare commands would have to match
`claude --bg *`, which also admits `--dangerously-skip-permissions`, `--settings` and any
prompt, with no classifier check. On Linux the tool uses `script -q -c "<command>" /dev/null`,
which has not been measured; on Windows it refuses, and the chat gives the user the brief.

### Unattended up to the ask for the push

An issue chat works without the user from its start brief to the ask for the push, and, under a
standing grant for the push and the automatic-merge switch, on to the merge. Unattended
chats stop on ask rules (which prompt even in auto mode), on the auto-mode classifier denying
what no narrow allow rule covers, and on `start_session` leaving a card in a turn a background
notification began. So:

- **A chat pushes only on the user's yes for that push,** typed in that chat, or under a
  standing grant through `push_branch.py`; the settings section never covers a push. The one
  narrow allow rule each of `push_branch.py` and `merge_pr.py` needs is the user's to add (§7).
- **No `--amend`:** a fix is a new commit.
- **A correction to an issue comment is a new comment,** never an edit.
- **Commands run as single calls,** not chained with other steps: `git commit -m "…" --
  <paths>` on its own, each script on its own, without `cd`. An ask or deny rule applies if any
  part of a chained command matches, and a chain with a part no allow rule covers goes to the
  classifier; a single call that a narrow allow rule covers resolves before it.
- **The work runs in the foreground of the turn the start brief began:** a long run is waited
  for by a blocking wait command, called again when the tool's timeout ends it, never by ending
  the turn for a notification. The hand-over happens in that same turn, so nothing of the chat
  runs on in the background; what still runs at the archive the chat ends first, since
  `archive_session` refuses a session with live background work. After the hand-over, a
  subagent's report is the one thing a chat may end its turn for (`issue-handover`, *End your
  own live work*).
- **Questions for the user go on the owning issue** with the question label. They do not block
  the hand-over unless the next step needs the answer. A question that is really new scope gets
  the requirements label instead.
- **The machine stays awake:** at the start of long work the chat calls `request_keep_awake`
  with `until: "session_idle"`. It prevents idle sleep only; a closed laptop lid still sleeps.
- **The fallback is the user's click:** when the start from the CLI fails, the chat makes sure
  no half-made next chat is left, leaves a card (`start_session`, `"own_initiative"`) or, where
  there is no card, the brief to paste, and says so (`issue-handover`, *The card fallback*).

### Side chats

A side chat is a chat another chat started with `start_session` and that has not detached
(`get_session` shows a `parentSessionId` and `detached` false), for work of its own: a fix, a
review, a pull request. It is no issue chat, whatever its title, and nothing archived it so
far: the app archives it with its parent only, and a parent the user types in may live for
weeks. So it ends this way:

- **It archives itself once its work has landed or merged,** not when it is merely pushed: in
  local-main mode in the turn its work lands on the local landing branch (`local-main.md` §1 or
  §2); in pull-request mode in the turn its pull request is merged in that chat, on the user's
  word for that pull request or by `merge_pr.py` where a standing grant allows it. While the
  pull request is open the chat stays, so a follow-up from its parent or a review comment still
  reaches it. Then: `chat_archivable.py <its worktree> --landed` (this plugin's `scripts/`); on
  `ok`, its report (it reaches the parent as the chat's last words), `get_session "self"`, and
  `archive_session "self"` as the last call of the turn. On `keep:` it stays and says why.
- **The brief says so.** A chat that starts a side chat ends the brief with: "Once your work has
  landed on local main or your pull request is merged, and `chat_archivable.py --landed` says
  ok for your worktree, report, then archive yourself (`archive_session "self"`); never before."
  The parent does not archive a side chat on its own initiative: the app leaves that to the
  user, and `archive-finished-chats` is the fallback.
- **A merge elsewhere** (on GitHub, from another chat) does not reach the side chat. Then
  `archive-finished-chats` archives it, under the settings section's standing permission or on
  the user's yes (its step 1 lists side chats). For pull-request work the desktop app can also
  archive a session when its pull request closes (its setting `auto_archive_on_pr_close`): the
  user's setting, not measured with side chats, and of no help in local-main mode, so it is an
  addition, never the rule.
- **The guard** checks a side chat with `--landed` whenever `archive_session` names it, the
  chat itself or another: a side chat whose work is only pushed, or only held by a successor's
  branch, is denied. It does not see the side chats that archiving their parent takes along
  (§6, `archive_session`): a parent stays while a side chat it started is running or fails the
  `--landed` check (`issue-handover`, *Never archive this chat*; `archive-finished-chats` step
  3).

## 5. Sharing the repository

Several chains work in one repository at once. What catches collisions between branches is the
second agent reading the first one's branch or note, the checks after bringing in the default
branch, and the announcement on the issue; this section makes the first and the last mechanical.

- **Every automatically started chat works in its own new worktree,** made with the worktree
  tool, never the primary checkout and never another chat's, except the worktree of a branch in
  flight that it takes over (§3 item 9).
- **The claim is the issue's assignee plus a signed comment.** All agents post as the user's
  account, so the assignee is that account; the comment says which chat claims it: its title,
  branch and worktree. Pickup skips assigned issues and `start_issue_chat.py` refuses one, so no
  issue gets two chats. The claim stays until the merge closes the issue; a chat that gives an
  issue up unassigns it and says why.
- **The overlap check** (the core plugin's `overlap_check.py`, git and `gh` reads only) lists
  the unmerged branches, open pull requests and claimed issues that touch the same files, with
  the design note to read. It runs at pickup on the paths the issue names (`issue-handover`
  step 3) and before the ask for the push on the task branch (`ship-change` step 5). For every
  hit the chat reads the other's note and writes, in its claim or its pull request text, one line
  per hit: how the two stay compatible, or that it waits for the other. An unmerged overlapping
  branch whose newest commit is older than 7 days is a reason to pick another issue, said in one
  line.
- **The design note** is a short signed comment on the issue before any code, when the pickup
  check reported an overlap or the issue is labelled `type:design-first`: the files it will
  touch, the public items it changes, removes or renames, and the design choice in two or three
  sentences, marked "design note". The reviewer checks it against the repository's decisions
  and the notes the overlap check lists.
- **The issue is the queue and the channel.** Chats come and go, so a message to another chat
  reaches it only while it exists. A claim, a question, an answer or a state goes on the issue,
  signed; a direct message is at most an extra nudge.

## 6. The desktop app's session tools

Claude Code desktop tools, as read with the CLI version above. Codex has different chat tools:
[the Codex adapter](codex.md). Without supported tools, give the user the prepared brief.

| Tool | What it does | Limits that matter here |
|---|---|---|
| `set_session_title` | renames a session; a new chat names itself with `"self"` | none seen |
| `send_message` | delivers a message to another session as a user turn labelled with the sender's title; the result says "delivered" (its turn has started), "queued" or why not | it cannot deliver into a session an orchestrator dispatched |
| `move_sessions` | files sessions under a sidebar section (`section_id` from `list_sections`) | moving any session but `"self"` asks the user first, so each chat files itself |
| `request_directory` | grants this session a folder outside its working directory | the working directory itself moves only with `change_directory`, at the end of the turn |
| `start_session` | starts a separate chat; `initiation: "user_asked"` starts it now; `"own_initiative"` only shows a card the user clicks | refused with `"user_asked"` in a turn the user did not type, so an issue chat uses it only for the card; `context: "fresh"` needs `prompt` (the brief) and `background` (at least 80 characters); `use_worktree: true` gives it its own worktree, cut from `source_branch`; a chat it starts for other work is a side chat, whose brief ends with the self-archive sentence (§4 *Side chats*) |
| `detach_session` | moves a session this chat started to top level: no longer archived with it; cannot be undone | only for a session this chat started, or `"self"` when another session started this one; refused for a session the user placed and for one that shares another session's worktree |
| `archive_session` | stops a session and by default removes its app-made worktree; `"self"` ends this conversation after the result; reversible from the Archived list | also archives its side sessions that share its worktree or have finished, without the guard checking them; refuses a session that is still working or has live background work, a pinned one, and one open on screen unless the user allowed it |
| `get_session` | `"self"` or an id: `worktreePath`, `parentSessionId`, `detached`, `isRunning`, `model` | it reports no effort; a chat's own effort is in `$CLAUDE_EFFORT` of its Bash |
| `request_keep_awake` | keeps the machine from idle sleep; `until: "session_idle"` also covers follow-up turns until the session is idle for about 5 minutes | a closed lid still sleeps; in auto mode the classifier decides each call unless an allow rule covers it |

Uncertain, so a chat stops and reports rather than guessing:

- Whether the effort passed to `claude --bg` holds after the session moves to the desktop app
  (`get_session` reports none). Never `claude rm` in this route: its help says it deletes a
  background session "and its worktree when that is safe", which for a session started in a
  worktree it did not make is not measured. A failure takes the fallback of `issue-handover`
  step 5 and stops the archive.
- `detach_session` says it is unavailable in unattended sessions; it was seen to work in the
  turn of the user's card click. Only the card fallback needs it.
- `archive_session "self"` archives unattended behind an allow rule and the guard hook (§7).
  Whether the allow rule counts while the user has the chat open on screen is not known. A
  refused archive leaves the chat as it is: it reports and stops.

## 7. Adopting issue chats in a repository

**Once per machine:** the Claude Code desktop app, its chats in auto permission mode (measured
on macOS only); the terminal CLI on the `PATH`, logged in with the same account; git and `gh`,
logged in; this plugin and the core plugin installed (the installer's `--with issue-chats`).
The plugin's hook guards `archive_session` wherever the plugin is enabled. Then open a new chat,
so it loads them.

**Optionally, for unattended chains,** narrow allow rules in the user's Claude Code settings,
added by the user (an agent never edits its own permissions): `start_issue_chat.py` by the exact
path of the script in the installer's clone (`~/.agentic-github-flow/plugins/<plugin>/scripts/`,
where Claude Code loads the skills from), in each spelling the agents write it; the read-only
scripts (`next_issue.py`, `chat_archivable.py`, the core plugin's `overlap_check.py`) the same
way; and `start_session`, `detach_session` and `request_keep_awake`; an allow rule for
`archive_session` only together with the guard hook; and, where the user grants the push of a
chat's own task branch or switches automatic merging on, the core plugin's `push_branch.py`
and `merge_pr.py` the same way (never `git push`, `gh pr merge` or `gh pr ready`
themselves). Never a broad allow, and every ask and deny
rule stays. A rule or a sandbox exclusion never names the copy under `~/.claude/plugins/cache/`:
its folder names the version, so an update silently breaks it; `install.sh --update` names each
one left. The README of this repository has the rule's form.

**Per repository,** on a branch, through a pull request the user approves:

1. **The settings section** in `HANDOFF.md` (§1), with the model and effort the user gives.
2. **The labels** in GitHub, and the open issues that are ready labelled (skill `open-issue`):
   the ready label, the requirements label, the question label, and `priority: critical` and
   `priority: high` where they are missing. Creating a label changes the repository on GitHub,
   so the user says yes first.
3. **No repository skill named `issue-handover`, `open-issue`, `archive-finished-chats` or
   `requirements`:** the client would run one copy and hide the other; the repository's values
   go in the settings section.

**Starting chains.** The user opens a chat on the repository's primary checkout and types, filled
in:

```
Start <n> issue chats in this repository by the issue-handover skill (at most five chains at
once; optionally only issues labelled <area label>).
```

That chat runs `issue-handover` steps 3 and 5 once per chain: pick, check the overlap, start,
claim, brief. With `spread over areas` on, each claim takes its area before the next pick, so
the chains start one per area with the most important ready work (critical and high first).
From then on every chat starts its successor itself; the user reads along in the sidebar section
and says push in each chat whose branch is ready; in local-main mode they say push of the
landing branch in any chat when they want the landings published. New work whose requirements are open is not
started: it gets the requirements label and a requirements chat (skill `requirements`).
