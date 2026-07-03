#!/usr/bin/env bash
# Build Typing Program one-folder bundle on Linux, then wrap in .tar.gz for distribution.
# Run on Linux only. Output: dist/Typing Program-linux.tar.gz
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != Linux ]]; then
  echo "build-linux.sh must run on Linux (PyInstaller builds for the host OS)." >&2
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

python scripts/release_archive.py linux
