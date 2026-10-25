#!/bin/sh
# Run a guard script with the first Python 3.8+ found: python3, python, then py -3 (Windows, where
# Claude Code runs hook commands through Git Bash). Without Python the call passes: a guard that
# cannot run must not stop all work, and the written rules still bind. -I keeps the guard from
# loading modules from the working directory or the user's PYTHON* settings.
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    exec "$candidate" -I "$@"
  fi
done
if command -v py >/dev/null 2>&1; then
  exec py -3 -I "$@"
fi
echo "agentic-github-flow guards: no Python 3.8+ found; the guard did not run" >&2
exit 0
