#!/usr/bin/env bash
# Build Typing Program.app with PyInstaller, then wrap it in a .dmg for distribution.
# Run on macOS only. Output: dist/Typing Program.dmg
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != Darwin ]]; then
  echo "build-mac-dmg.sh must run on macOS (PyInstaller builds for the host OS)." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found. Install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv venv venv --python 3.11
# shellcheck source=/dev/null
source venv/bin/activate

uv pip install -r requirements.txt
uv pip install -e .
uv pip install pyinstaller pillow

pyinstaller typing_program.spec --noconfirm --clean

python scripts/mac_dmg.py
