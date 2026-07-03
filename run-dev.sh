#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv venv venv --python 3.11
# shellcheck source=/dev/null
source venv/bin/activate

uv pip install -r requirements.txt
uv pip install -e .

echo ""
echo "Starting typing-program..."
exec typing-program --skip-license
