#!/bin/sh
# Start context_limit.py only in an issue-chat branch (agent/<digit>...), so every other session
# pays one git call instead of a Python start per tool call. The folder fallback of
# question_label.chat_issue (a linked worktree named <n>-...) is not seen here: those chats get no
# context limit. The rest of the decision is context_limit.py's.
dir="${CLAUDE_PROJECT_DIR:-$PWD}"
case "$(git -C "$dir" branch --show-current 2>/dev/null)" in
  agent/[0-9]*) exec sh "$(dirname "$0")/run-hook.sh" "$(dirname "$0")/context_limit.py" ;;
esac
exit 0
