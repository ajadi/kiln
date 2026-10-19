#!/bin/sh
# Kiln hook launcher for Claude Code: run a Kiln hook script with the first Python 3.10+ found.
#   bash py.sh <hook script path> [args...]
# macOS and many Linux systems have only python3, Windows usually only python (its python3 can
# be the Microsoft Store stub, which runs nothing): a hook started as plain `python` failed there
# and Claude Code went on without the guard. The working interpreter is cached.
script="$1"
shift
cache="${KILN_HOME:-$HOME/.kiln}/hook-python"
works() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; }
py=$(cat "$cache" 2>/dev/null)
if [ -z "$py" ] || ! command -v "$py" >/dev/null 2>&1; then
  py=""
  for candidate in python python3; do
    if command -v "$candidate" >/dev/null 2>&1 && works "$candidate"; then
      py=$(command -v "$candidate")
      mkdir -p "$(dirname "$cache")" 2>/dev/null && printf '%s\n' "$py" > "$cache" 2>/dev/null
      break
    fi
  done
fi
if [ -z "$py" ]; then
  echo "Kiln: no Python 3.10+ found as python or python3; Kiln's hooks (guard, session state) are not running. Install Python 3.11+ and restart." >&2
  exit 1
fi
exec "$py" "$script" "$@"
