#!/bin/sh
# Run an issue-chats hook that must never stop work with the first Python 3.8+ found: python3,
# python, then py -3 (Windows, where Claude Code runs hook commands through Git Bash). Unlike
# run-guard.sh, without Python the call passes: question_label.py keeps a label true, and a
# question to the user must always be possible. -I keeps the hook from loading modules from the
# working directory or the user's PYTHON* settings.
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    exec "$candidate" -I "$@"
  fi
done
if command -v py >/dev/null 2>&1; then
  exec py -3 -I "$@"
fi
echo "agentic-github-flow issue chats: no Python 3.8+ found; the question-label hook did not run" >&2
exit 0
