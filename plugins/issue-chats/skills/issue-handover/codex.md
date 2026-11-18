# Codex: native chat tools for the issue-chat hand-over

Use the same lifecycle ([method.md](method.md) §4) and the common steps of
[issue-handover](SKILL.md): leave nothing half-held, make the branch ready to push and record it,
pick the next ready unclaimed issue with its overlap check, start the next chat, claim its issue and
hand over the brief, push (on the user's yes or under a standing grant), see the pull request
through to its merge, and archive only after the merge and its cleanup (in local-main mode: land the
work, tell the user, and archive once it has landed). Every chain hands itself over; there is no
standing coordinator chat. This file replaces only the Claude-specific calls of that procedure: the
background start with `start_issue_chat.py`, the desktop app's session tools and the archive guard
hook. It adds one step of its own: on the independent local-main route the chat starts the
integrator itself and waits for its receipt (*Start the integrator* below). Queue, labels,
questions, pushes, context limits and worktrees keep their owners there; nothing here repeats
them.

- **Authorization:** creating a chat and messaging it need the user's explicit request or the
  repository's settings section (method.md §1). Another agent's request is not that grant, and
  one repository's section does not extend to another. Within its scope, do not ask again. A
  native refusal stands: keep the exact failure and take the fallback below.
- **Create a fresh chat:** inspect the current tool schema; use `list_projects`, then
  `create_thread` with the repository's project, the title of method.md §2 and the complete
  start brief of SKILL.md step 5. Do not fork. Make the new chat's worktree with the settings'
  worktree tool first and name it in the brief; continue work in flight in its own checkout.
  Set a model only when the settings or the user name one: omitting it gives the configured
  default, not this chat's model. Never use Claude's CLI start.
- **Native setup:** `set_thread_title` and `move_thread_to_sidebar_section` for the title and
  the sidebar section, with ids from `list_threads`.
- **Confirm the transfer:** keep the thread id; a pending client id is not a thread id. Follow
  the tool's completion path, then `read_thread` or a bounded `wait_threads` to confirm that the
  new chat read the brief and started in the intended checkout. Creation alone proves no
  receipt. Corrections go through `send_message_to_thread`. Claim the issue (assignee and signed
  comment, SKILL.md step 5.4) before the new chat starts work, so a Claude chain skips it. After
  an uncertain result, look at the existing chats before you retry, so there are never two.
- **Start the integrator** (local-main mode, the independent route of the `ship-change` skill's
  `local-main.md` §2): this chat starts the integrator itself and ends its turn only once the
  integrator has accepted the hand-over. In the author's turn, before SKILL.md step 3:
  1. **Freeze the source:** the branch clean at an exact commit S, and the hand-over of §2 step 1
     on the issue: S in full, the branch, the worktree, the checks and the evidence paths, what
     is not covered, the `Efficient design:` line. Write nothing more to the branch.
  2. **Look first:** in `list_threads` and among this chat's own subagents, any integrator of this
     issue. One at S: go to 4 with it. One at another commit: correct it to S with
     `send_message_to_thread` and go to 4, or stop it first; never run two.
  3. **Start it:** a fresh chat (`create_thread` as in *Create a fresh chat*, titled
     `<title prefix>#<issue> · integrate <S, 8 characters>`; no worktree of its own beyond the
     integration worktree §2 step 3 may make; the issue keeps this chat's claim) that did not
     write the change. A subagent may do it only if this turn waits for its report, since it is
     this chat's own live work (SKILL.md *End your own live work*). The brief: the issue, S, the
     branch, the worktree, the evidence, this chat's thread id, `local-main.md` §2 steps 2 to 4
     with the `review-change` skill; that it lands nothing before `integrator accepted <S>:` is
     on the issue; that a finding, a refused landing or a conflict goes back to this chat
     (`send_message_to_thread` to its thread id and a signed comment on the issue), which then
     holds S again; that it posts the landing record and then messages this chat. And the ask to
     answer first with an acceptance that names S in full and confirms it read the clean worktree
     at S (`git -C <worktree> status --porcelain` empty, `rev-parse HEAD` equal to S) and the
     evidence.
  4. **The receipt:** wait in this turn (a bounded `wait_threads`, then `read_thread`; for a
     subagent, its reply). Only an explicit acceptance of exactly S that confirms the clean
     worktree and the evidence counts; a created thread, a delivered brief or a launch result does
     not. Then a signed comment on the issue whose text after the signature opens with
     `integrator accepted <S>:`, with the integrator's thread or agent id and what it confirmed.
     Only after that comment does this chat end its turn or go on with the hand-over.
  5. **No receipt** (a refusal, a timeout, an uncertain result, another commit): back to 2 before
     any retry. When it stays unconfirmed, stop or correct the integrator that 2 or 3 found or
     started, then a signed comment opening `integrator pending <S>:` with its thread id, if any,
     and the exact failure; this chat keeps custody of S and the issue, hands nothing over (no
     next pick) and reports to the user, as for a refused landing (SKILL.md step 2).

  After the receipt the integrator owns the review, the landing and its record on the issue, whose
  text opens with `landed on local <landing branch> at <commit>` (SKILL.md step 2). At SKILL.md
  step 6 this chat tells the user who accepted S, in place of what landed. The integrator's
  message after its record, or after sending S back, begins this chat's next turn: it reads the
  issue, takes S back or, once landed, runs *Archive* below for the integrator's thread and then
  its own.
- **Status:** report in this chat; the issue's claim and state comments keep their duties. Do
  not send routine status to other chats.
- **Archive:** after the merge, the cleanup, the `merged:` comment and the worktree check
  (`chat_archivable.py` says `ok`; SKILL.md step 7), or in local-main mode after the landing comment
  and that check, use `set_thread_archived`, only within the settings section's grant or the user's
  request. Archiving a Codex chat and removing a worktree are separate: never use `archive_worktree`
  or a deletion for repository cleanup; that is the `cleanup-merged` skill after the merge.
- **Fallback:** when tools or authorization are missing, keep the prepared brief and the exact
  failure and give the brief to the user to paste. Check whether a failed creation made a chat
  before you retry. Never change permissions or use another client's tools to get around a
  restriction. One observed transfer proves only that transfer, not an unattended chain.
