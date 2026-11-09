---
name: issue-handover
description: Pick and claim the next ready GitHub issue and hand an issue chat over to the chat for it - record that the branch is ready to push or landed on local main, pick the next issue by priority, check it for overlap, start its chat in the background, claim the issue and hand over the brief, then ask for the push or archive. Use when an issue chat's branch is ready to push or landed, when its context nears the limit, after two failed corrections, or when the user asks to start issue chats.
compatibility: The background start needs the Claude Code desktop app and a logged-in claude CLI (measured on macOS; Linux unmeasured; Windows unsupported) plus gh. Codex desktop uses codex.md. Elsewhere the chat gives the user the brief to paste.
---

# Pick the next issue and hand over to its chat

**Codex:** use [the Codex adapter](codex.md) for this hand-over, including its authorization
and fallback checks; do not run the Claude-specific steps below. The adapter adds no permission
by itself: the repository's settings section or the user's request supplies it.

The method and why the steps come in this order: [method.md](method.md), §4 and §5. The
repository's `HANDOFF.md` section `## Issue chats settings` gives the values below (model and
effort, labels, area labels, spread over areas, sidebar section, worktree tool, title prefix,
start reading, extras); a row it leaves out takes the default of method.md §1. `<plugin>` is the
folder two levels above this skill's folder, where the scripts are
([next_issue.py](../../scripts/next_issue.py),
[start_issue_chat.py](../../scripts/start_issue_chat.py),
[chat_archivable.py](../../scripts/chat_archivable.py)). The overlap check and the worktree
tool are the core plugin's, run as the `ship-change` skill names them. Everything up to the ask
for the push runs in the foreground of the turn of the task's work.

**The push stays the user's.** The settings section lets this chat pick, claim, start the next
chat and archive itself without asking; it never covers a push, a merge or marking a pull
request ready. This chat pushes only after the user's yes for this push, typed in this chat.
In local-main mode (`ship-change` step 1) the chat lands its own work on local main instead, as
the `ship-change` skill's `local-main.md` says, and the push of the landing branch waits for
the user's word in any chat; steps 2, 6 and 7 below say what changes.

**Never archive this chat** while any of these holds: its worktree, or a task worktree it
worked in, fails the worktree check (`python3 <plugin>/scripts/chat_archivable.py <worktree>`
says `keep:`, as it does while a commit of this chat is not on GitHub or, in local-main
mode, not landed); a run, subagent or background job of it is still
running; another session it started is not detached and is running or fails the worktree check
with `--landed` (method.md §4 *Side chats*), because archiving takes its finished side sessions
along and removes their worktrees; a
question to the user is unanswered and the next step needs its answer (any other question waits
on its issue, step 2). Without the settings section there is no standing permission: start the
next chat only on the user's request or by the card of step 5, and archive nothing unasked.

**A probe that must not be merged** keeps its commits on a local branch
`scratch/<issue>-<what>` (`git branch scratch/<issue>-<what> <sha>`), named on the issue with
what it proved; then `git switch --detach origin/<default branch>` in its worktree, since the
worktree check reads HEAD. A `cleanup-merged` sweep deletes it once the issue is closed.

1. **Leave nothing half-held.** Stop or finish your runs and agents. Run the hand-over extras.
   Commit verified work on the task branch, each commit a call of its own
   (`git commit -m "…" -- <paths>`); a fix is a new commit, never `--amend`. Anything
   uncommitted stops the hand-over: name it.
2. **Make the branch ready to push and record it.** Run `ship-change` steps 1 to 5: the review
   route, the default branch brought in, the checks, the pull request text, the overlap check.
   Then a signed comment on the issue whose text after the signature opens with
   `ready to push:`: the branch, its head commit, the checks and their results, and one line per
   overlap hit (the next chat's pick reads this opening: the area is free again, method.md §1).
   The issue stays open and assigned; the merge closes it. **In local-main mode** land the work
   instead (`local-main.md` §1; for the independent route a subagent that did not write it
   reviews and lands it, §2), then the signed comment opens with
   `landed on local <landing branch> at <commit>`: what landed, the checks, the overlap lines;
   the issue stays open and assigned until the push's cleanup closes it. Landing refused: stop
   and report, no hand-over. A correction to an earlier comment is a new comment, never an edit. Each open question for the user stands on its owning issue,
   signed, with the question label.
3. **Pick the next issue:** `git fetch origin`, then
   `python3 <plugin>/scripts/next_issue.py -C <this worktree>`, with `--area <area label>` when
   this chain is limited to an area. It prints the ready issues in pick order:
   `priority: critical` first, then `priority: high`, then the rest, oldest first; with
   `spread over areas` on, the rest from an area no chat works in yet comes first. Exit 3:
   GitHub was not read, stop here. Take the first line unless you say in one line why another
   matters more. Skip an issue whose body names `after #n` for an issue that is still open
   (`gh issue view <n> --json state`). Read the chosen issue, then run the overlap check of
   `ship-change` step 5 with `--paths <the code paths the issue names> --issue <n>` in place of
   `--branch`: exit 0 none; 1 read each listed note and keep one line per hit for the claim (how
   the work stays compatible, or that it waits); a hit that is an unmerged branch whose newest
   commit is older than 7 days, or a second chat on the same issue, is a reason to pick the next
   issue instead, said in one line; 3 GitHub was not read: stop here. An issue whose
   requirements turn out to be open is not started: it gets the requirements label in place of
   the ready label and a comment on what is open, and you pick the next. No ready issue: start
   nothing, go to step 6.
4. **Check before you start anything:** no run of yours is still going and no half-made chat of
   an earlier attempt exists. The worktree check of your own worktree (the `worktreePath` of
   `get_session "self"`, or, for a chat with none, the worktree it worked in) is expected to say
   `keep:` while your branch waits for the push: that stops only the archive, never the start
   (in local-main mode it says `ok` once the work landed).
5. **Start the next chat and claim its issue.** Each numbered call stands alone, in the
   foreground of this turn; any failure goes to the fallback below.
   1. **Its worktree:** always a new one, made with the settings' worktree tool from the
      primary checkout, named `<issue>-<short name>`. Never this chat's own worktree: the app
      then refuses the message of step 5.5 ("this session's branch is checked out somewhere
      else").
   2. **Model and effort:** the settings' model and effort; unset, this chat's own: the `model`
      of `get_session "self"`, and the effort in `$CLAUDE_EFFORT` (the tool takes it when
      `--effort` is left out).
   3. **Start it and open it in the app:**
      `python3 <plugin>/scripts/start_issue_chat.py "<new worktree>" "<title>" --model <model> --effort <effort>`,
      with `--prefix "<title prefix>"` when the settings set one; the title is
      `<title prefix>#<issue> · <topic>` (method.md §2). It refuses before starting anything
      when the platform has no known form of `script`, the CLI is logged out, the worktree is a
      primary checkout, dirty or already some session's, the title is not of the form, another
      running chat carries the title, or the issue is closed or already assigned. Exit 0 prints
      `ok local_<sessionId>`: the new chat is open in the app. Exit 1 (`fail:`): nothing runs
      and nothing was opened. Exit 2 (`unsure:`): it may be open or running.
   4. **Claim the issue:** `gh issue edit <n> --add-assignee @me`, then a signed comment whose
      text after the signature opens with
      `claimed for chat "<title>" (local_<sessionId>), branch <branch>, worktree <path>`, and
      the overlap lines of step 3.
   5. **Hand over the brief:** `send_message` with `session_id` `local_<sessionId>` and
      `message` the start brief. Only a result that says "delivered" counts.

   **The start brief** is complete on its own: the new chat has no memory of this one. Its first
   lines make the new chat, before anything else: (a) set its title to the exact title of step
   5.3 with `set_session_title` on `"self"`; (b) file itself under the sidebar section
   (`list_sections`, `create_section` only if it is missing, `move_sessions` with `["self"]` and
   that `section_id`); (c) work only in its own worktree, by path and branch: the new one of
   step 5.1, or the one in flight the issue's state comment names; absolute paths into it, and
   `request_directory` with its path when a file tool refuses it; never the primary checkout.
   Then: the issue number and why it is next, its check, that this skill and method.md §4 step 1
   govern its start (read, check the claim, the design note when the claim names an overlap or
   the issue is labelled `type:design-first`, housekeeping, the requirements stop), and that it
   pushes only on the user's yes.

   **The fallback** when the worktree tool, the start tool or the claim fails, or the message
   was not "delivered": first make sure there is no half-made next chat, so there are never
   two. Exit 1 of step 5.3 left none. After exit 2 or an undelivered message:
   `local_<sessionId>` in `list_sessions` gets `archive_session` (it has done nothing; its
   worktree is the new, clean one, which the archive keeps); otherwise
   `claude agents --json --cwd "<new worktree>"` must print `[]`. Never `claude rm`: it deletes
   a session's worktree. Remove a claim step 5.4 made (`gh issue edit <n> --remove-assignee
   @me` and a comment why). If the half-made chat cannot be ruled out or archived, leave no
   card: report it and stop. Then a card, `start_session` with `initiation: "own_initiative"`,
   `context: "fresh"`, `title`, `prompt` the start brief, `background` (at least 80 characters)
   what is ready to push and why this issue is next, `use_worktree: true`,
   `source_branch: "<default branch>"` (*The card fallback* below); the chat the card starts
   claims its issue itself (method.md §4 step 1.2). Without the session tools, give the brief as
   one block for the user to paste into a new chat. Either way, report how the calls came back.
6. **Tell the user and ask for the push,** in a few lines and in their language: what is ready
   to push (`ship-change` step 6: the branch, how many commits, the checks and their results,
   the overlap check's result, the pull request title, draft or ready); which chat started with
   which model and effort, and its issue; anything that stopped you. Then end the turn: this
   chat waits for the yes and does not archive now. **In local-main mode** tell the user what
   landed (the commits and checks; the landing branch now holds unpushed landings, pushed on
   their word in any chat) in place of the ask, and go on with step 7 in this turn.
7. **Push and archive,** in the turn of the user's yes: `ship-change` step 7 (push your task
   branch, open the pull request, report its URL and first CI result); a signed comment on the
   issue whose text after the signature opens with `pull request opened: #<number>`; then rerun
   the worktree check, call `get_session "self"`, and `archive_session` with `session_id:
   "self"` and a short `reason`. No detach first: the CLI started the next chat, so it is not
   this chat's child. Tell the user before the archive, which ends the conversation. If the
   user wants changes first, they are new commits on this branch and steps 2 and 6 again; if
   anything fails, do not archive: report and stop. A chat with nothing to push (no next issue
   and no commits, or a task stopped for open requirements) archives at step 6 when the check
   passes. **In local-main mode** step 7 is the archive alone: rerun the worktree check (`ok`
   once landed), `get_session "self"`, tell the user, then `archive_session` with
   `session_id: "self"` and a short `reason`; no push and no pull request.

**Starting chains** (a chat the user types in, method.md §7): run steps 3 and 5 once per chain,
each pick after the previous claim, so a spreading repository gets one chain per area with the
most important ready work; at most five chains at once (method.md §1), counted with the issue
chats already working; then report. That chat does not archive itself.

**The card fallback.** When step 5 left a card, the user's click on it is their turn. In that
turn this chat detaches the session the click started (`detach_session` with its id, from the
turn or from `list_sessions` by the title of step 5), because that one is its child, and goes
on with step 6. If no turn reaches this chat, it stays as it is: the next chat detaches itself
and a later `archive-finished-chats` archives this one once its work is on GitHub (in
local-main mode: landed).

**A hand-over before the branch is ready** (context limit, two failed corrections) keeps the
issue: commit what is verified, a signed state comment on the issue (branch, worktree, head
commit, what is checked, the next step), then step 5 for the same issue with `--handover` (the
claim is this chat's own: the tool refuses unless the issue's newest claim comment names this
chat's `local_<sessionId>` or worktree) and a new claim comment naming the new chat and the
worktree in flight, which the new chat works in. Never an archive: this chat's commits are not
on GitHub. A later `archive-finished-chats` archives it once they are, or once a successor's
branch that holds them is pushed (the worktree check then names that branch).
