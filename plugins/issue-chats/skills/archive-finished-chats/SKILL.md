---
name: archive-finished-chats
description: Archive the finished issue chats and side chats of a repository - chats whose worktrees are clean and whose commits are on GitHub, or landed on local main in local-main mode; side chats (started by another chat with start_session) once their work landed or their pull request merged - and file this chat under the repository's sidebar section. Use at the start of every issue chat, when the user asks to tidy or archive old chats, or when the sidebar fills with finished chats.
compatibility: Claude Code desktop app only (its session and sidebar tools). Elsewhere it lists the chats that look finished and the user archives them.
---

# Archive the finished issue chats and side chats

The method, the settings, the title form, side chats and the session tools: the
`issue-handover` skill's [method.md](../issue-handover/method.md), §1, §2, §4 *Side chats* and
§6. The repository's `HANDOFF.md` section
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
fetch, or in local-main mode clean with its HEAD on the local landing branch, or, for a chat that
handed its issue over, held by another branch of origin that GitHub still has (a successor's
pushed branch); every `ok` but a gone worktree also needs that no commit only its own reflogs
hold would be lost; otherwise `keep:` and the reason. A chat whose branch
still waits for the user's push fails it, and stays. A side chat is checked with `--landed`
added: `ok` only once its HEAD is in origin's default or landing branch, on the local landing
branch in local-main mode, or the head of a merged pull request; a pushed branch with an open
pull request stays.

0. **Stand on your own.** If another session started this chat (`get_session "self"` shows a
   `parentSessionId` and `detached` false, as after a card), call `detach_session "self"`: a
   chat still nested under its predecessor would be archived with it. If it is refused, say so.
   A chat that `issue-handover` started from the CLI has no parent: nothing to do. This step
   is for issue chats only: a side chat started for other work stays under its parent and ends
   as method.md §4 *Side chats* says. Until it detaches, an issue chat counts as a side chat
   and is archived only once its work landed or merged.
1. **List** the sessions (`list_sessions`, limit 50; it gives each one's `startedBy`). Issue
   chats carry the title form (`<title prefix>#<issue> · <topic>`), requirements chats
   `<title prefix>Requirements · …` (method.md §2), or one of the older forms the settings list,
   and a working directory in this repository or its worktrees. Requirements chats are checked
   like any other issue chat. **Side chats** count too, whatever their title: a session another
   session started (`startedBy` names a session; `get_session` shows a `parentSessionId` and
   `detached` false) with a working directory in this repository or its worktrees. They are the
   fallback for a side chat that did not archive itself (method.md §4 *Side chats*), for
   example because its pull request was merged elsewhere. Every other chat (a chat the user
   types in) is left alone.
2. **Keep** this chat, every chat that is running (`isRunning`), any chat pinned or open on
   screen, and the newest chat of each issue that is still open, a requirements chat's parent
   issue included (it may wait for the user's push or hold the issue's last report). A side chat
   is not kept for its issue: the `--landed` check decides.
3. **Check each other chat:** `get_session` gives its `worktreePath`, `parentSessionId` and
   `detached`; run the worktree check on the `worktreePath`, with `--landed` for a side chat. A chat without one is checked on the worktree
   its working directory lies in (`originCwd`, else `cwd`, of `get_session`), when that is a
   linked worktree (`git rev-parse --git-dir` differs from `--git-common-dir`): work there may
   be only on this machine even though archiving does not remove it. Only a chat that worked in
   the primary checkout, or in a folder that is gone, passes unchecked. Archive only on `ok`. A
   worktree made with the worktree tool stays on disk until `cleanup-merged` removes it after
   the merge.
   **Never archive a chat from which another unarchived session descends** (the `startedBy` of
   `list_sessions` is that chat, or a session it started, at any depth; the `parentSessionId` of
   `get_session` gives the same link from the child's side): the app archives the chain with
   it, a running chat included. Keep it until its descendants have detached (step 0). Keep, too, a chat
   whose worktree another unarchived chat is working in (a branch in flight it took over):
   archiving would remove that chat's working folder.
4. **Archive** with `archive_session` and `reason`: `finished issue chat #<issue>; worktree
   clean, on GitHub` (or `landed on local main`, or `held by <successor branch>`), for a side
   chat `finished side chat; landed` (or `pull request #<n> merged`). The plugin's guard hook
   repeats step 3, `--landed` included for a side chat, and may deny the call; it does not
   check step 2 or the descendants: those stay yours.
5. **File this chat** under the sidebar section: `list_sections`, `create_section` only if it is
   missing, then `move_sessions` with `"self"` and its `section_id`. One section per
   repository, no group per issue. Moving another chat asks the user first, so each chat files
   itself.
6. **Report** in one or two lines: how many chats were archived, and each one kept with its
   reason (for example `keep: 3 commit(s) of agent/12-export are not on GitHub`).
