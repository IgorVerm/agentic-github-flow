---
name: archive-finished-chats
description: Archive the finished issue chats of a repository - chats whose worktrees are clean and whose commits are on GitHub - and file this chat under the repository's sidebar section. Use at the start of every issue chat, when the user asks to tidy or archive old chats, or when the sidebar fills with finished chats.
compatibility: Claude Code desktop app only (its session and sidebar tools). Elsewhere it lists the chats that look finished and the user archives them.
---

# Archive the finished issue chats

The method, the settings, the title form and the session tools: the `issue-handover` skill's
[method.md](../issue-handover/method.md), §1, §2 and §6. The repository's `HANDOFF.md` section
`## Issue chats settings` is the standing permission: a chat that passes every check below is
archived without asking again; a chat that fails a check stays, and you say why. Without that
section, list what would go and ask the user. Archiving is reversible (the Archived list,
`unarchive_session`); deleting is never done here. The title prefix and older title forms and
the sidebar section come from the settings. A chat archives itself only by `issue-handover`,
never here. **Outside the desktop app** (no session tools), list the chats that look finished by
these checks and leave the archiving to the user.

The worktree check is `python3 <plugin>/scripts/chat_archivable.py <worktree>`, `<plugin>` being
the folder two levels above this skill's folder
([chat_archivable.py](../../scripts/chat_archivable.py)): `ok` when the worktree is gone, or
clean with its HEAD in origin's default branch or in the branch's own `origin/<branch>` after a
fetch; otherwise `keep:` and the reason. A chat whose branch still waits for the user's push
fails it, and stays.

0. **Stand on your own.** If another session started this chat (`get_session "self"` shows a
   `parentSessionId` and `detached` false, as after a card), call `detach_session "self"`: a
   chat still nested under its predecessor would be archived with it. If it is refused, say so.
   A chat that `issue-handover` started from the CLI has no parent: nothing to do.
1. **List** the sessions (`list_sessions`, limit 50). Issue chats carry the title form
   (`<title prefix>#<issue> · <topic>`) or one of the older forms the settings list, and a
   working directory in this repository or its worktrees. Requirements chats
   (`<title prefix>Requirements · …`) and every chat of another form (a chat the user types in)
   are left alone.
2. **Keep** this chat, every chat that is running (`isRunning`), any chat pinned or open on
   screen, and the newest chat of each issue that is still open (it may wait for the user's
   push or hold the issue's last report).
3. **Check each other chat:** `get_session` gives its `worktreePath`; run the worktree check on
   it. Archive only on `ok`, because archiving removes an app-made worktree. A chat without
   `worktreePath` removes no worktree when archived: it passes. A worktree made with the
   worktree tool stays on disk until `cleanup-merged` removes it after the merge.
   **Never archive a chat from which another unarchived session descends** (`startedBy` is that
   chat, or a session it started, at any depth): the app archives the chain with it, a running
   chat included. Keep it until its descendants have detached (step 0). Keep, too, a chat
   whose worktree another unarchived chat is working in (a branch in flight it took over):
   archiving would remove that chat's working folder.
4. **Archive** with `archive_session` and `reason`: `finished issue chat #<issue>; worktree
   clean, on GitHub`. The plugin's guard hook repeats step 3 and may deny the call; it does not
   check step 2 or the descendants: those stay yours.
5. **File this chat** under the sidebar section: `list_sections`, `create_section` only if it is
   missing, then `move_sessions` with `"self"` and its `section_id`. One section per
   repository, no group per issue. Moving another chat asks the user first, so each chat files
   itself.
6. **Report** in one or two lines: how many chats were archived, and each one kept with its
   reason (for example `keep: 3 commit(s) of agent/12-export are not on GitHub`).
