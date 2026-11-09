#!/bin/sh
# Run the archive guard with the first Python 3.8+ found: python3, python, then py -3 (Windows,
# where Claude Code runs hook commands through Git Bash). Unlike the guards plugin's
# run-python.sh, this one fails closed: without Python the archive is denied (exit 2), because
# archiving removes a worktree and the user can always archive a chat by hand. -I keeps the
# guard from loading modules from the working directory or the user's PYTHON* settings.
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    exec "$candidate" -I "$@"
  fi
done
if command -v py >/dev/null 2>&1; then
  exec py -3 -I "$@"
fi
echo "archive guard: no Python 3.8+ found, so the worktree could not be checked; archive the chat by hand" >&2
exit 2
