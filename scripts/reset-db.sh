#!/usr/bin/env bash
# Clear typing stats; keep imported books/sources and book reading progress.
# Backs up the current file as <name>.bak-<timestamp> beside it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT/scripts/reset_db.py" "$@"
