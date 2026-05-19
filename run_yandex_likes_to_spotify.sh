#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  printf 'Missing venv. Run from %s:\n  uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt\n' "$SCRIPT_DIR" >&2
  exit 1
fi

cd "$SCRIPT_DIR"
exec "$PYTHON" "$SCRIPT_DIR/yandex_likes_to_spotify.py" "$@"
