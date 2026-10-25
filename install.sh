#!/usr/bin/env bash
# agentic-github-flow installer for macOS and Linux. The one command (README):
#   git clone https://github.com/IgorVerm/agentic-github-flow.git ~/.agentic-github-flow && ~/.agentic-github-flow/install.sh
# It makes sure the clone exists in ~/.agentic-github-flow, finds Python 3.8+ and hands over to
# tools/installer.py in that clone, which owns every step. Options (all passed on):
#   --with security,web-deploy   --guards   --overlay <git-url-or-path>   --update   --uninstall
#   --no-claude   --no-codex   --claude-bin <path>   --codex-bin <path>   --help
set -eu

REPO_URL="${AGENTIC_GITHUB_FLOW_REPO:-https://github.com/IgorVerm/agentic-github-flow.git}"
TARGET="$HOME/.agentic-github-flow"

python=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    python="$candidate"
    break
  fi
done
if [ -z "$python" ]; then
  echo "STOP  agentic-github-flow needs Python 3.8 or newer (python3). Install it, then run this again." >&2
  exit 3
fi
if ! command -v git >/dev/null 2>&1; then
  echo "STOP  agentic-github-flow needs git. Install it, then run this again." >&2
  exit 3
fi

if [ ! -f "$TARGET/tools/installer.py" ]; then
  if [ -e "$TARGET" ]; then
    echo "STOP  $TARGET exists but is not an agentic-github-flow clone; move it away first." >&2
    exit 3
  fi
  case " $* " in *" --uninstall "*)
    echo "STOP  nothing to uninstall: $TARGET does not exist." >&2
    exit 3 ;;
  esac
  git clone --quiet "$REPO_URL" "$TARGET"
  echo "ok    cloned $REPO_URL into $TARGET"
fi

exec "$python" "$TARGET/tools/installer.py" "$@"
