# Codex: native chat tools for the issue-chat hand-over

Use the same lifecycle ([method.md](method.md) §4) and the common steps of
[issue-handover](SKILL.md): leave nothing half-held, make the branch ready to push and record
it, pick the next ready unclaimed issue with its overlap check, start the next chat, claim its
issue and hand over the brief, push (on the user's yes or under a standing grant), see the pull
request through to its merge, and archive only after the merge and its cleanup (in local-main
mode: land the work, tell the user, and archive once it has landed). Every chain hands itself over; there is no standing coordinator chat. This file replaces
only the Claude-specific calls of that procedure: the background start with
`start_issue_chat.py`, the desktop app's session tools and the archive guard hook. Queue,
labels, questions, pushes, context limits and worktrees keep their owners there; nothing here
repeats them.

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
- **Status:** report in this chat; the issue's claim and state comments keep their duties. Do
  not send routine status to other chats.
- **Archive:** after the merge, the cleanup, the `merged:` comment and the worktree check
  (`chat_archivable.py` says `ok`; SKILL.md step 7), or in local-main mode after the landing comment and that
  check, use `set_thread_archived`, only within the settings
  section's grant or the user's request. Archiving a Codex chat and removing a worktree are
  separate: never use `archive_worktree` or a deletion for repository cleanup; that is the
  `cleanup-merged` skill after the merge.
- **Fallback:** when tools or authorization are missing, keep the prepared brief and the exact
  failure and give the brief to the user to paste. Check whether a failed creation made a chat
  before you retry. Never change permissions or use another client's tools to get around a
  restriction. One observed transfer proves only that transfer, not an unattended chain.
