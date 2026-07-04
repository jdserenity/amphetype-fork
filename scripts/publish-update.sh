#!/usr/bin/env bash
# Upload a release build to R2 and refresh manifest.json.
# Requires: wrangler logged in, bucket typing-program-updates created once via:
#   npx wrangler r2 bucket create typing-program-updates
#
# Usage (from repo root):
#   ./scripts/publish-update.sh VERSION PLATFORM FILE
#
# PLATFORM: darwin | win32 | linux
# FILE: path to Typing Program-mac.zip, Typing Program-win.zip, or Typing Program-linux.tar.gz
#
# Example:
#   ./scripts/publish-update.sh 1.3.0 darwin "dist/Typing Program-mac.zip"
#   ./scripts/publish-update.sh 1.3.0 win32 "dist/Typing Program-win.zip"
#   ./scripts/publish-update.sh 1.3.0 linux "dist/Typing Program-linux.tar.gz"
#
# After uploading each platform for a version, manifest.json in R2 lists that version.
# Re-run for the same VERSION + PLATFORM to replace that platform's artifact.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
PLATFORM="${2:-}"
FILE="${3:-}"

if [[ -z "$VERSION" || -z "$PLATFORM" || -z "$FILE" ]]; then
  echo "usage: $0 VERSION PLATFORM FILE" >&2
  exit 1
fi

case "$PLATFORM" in
  darwin|win32|linux) ;;
  *) echo "PLATFORM must be darwin, win32, or linux" >&2; exit 1 ;;
esac

if [[ ! -f "$FILE" ]]; then
  echo "file not found: $FILE" >&2
  exit 1
fi

BASENAME="$(basename "$FILE")"
OBJECT_KEY="releases/${VERSION}/${BASENAME}"
SHA256="$(shasum -a 256 "$FILE" | awk '{print $1}')"
BUCKET="typing-program-updates"
MANIFEST_LOCAL="$(mktemp)"
trap 'rm -f "$MANIFEST_LOCAL"' EXIT

echo "Uploading $FILE -> r2://${BUCKET}/${OBJECT_KEY}"
npx wrangler r2 object put "${OBJECT_KEY}" --file "$FILE" --bucket "$BUCKET" --remote

if npx wrangler r2 object get manifest.json --bucket "$BUCKET" --remote --file "$MANIFEST_LOCAL" 2>/dev/null; then
  :
else
  echo '{"version":"","release_notes":"","platforms":{}}' > "$MANIFEST_LOCAL"
fi

python3 - "$MANIFEST_LOCAL" "$VERSION" "$PLATFORM" "$OBJECT_KEY" "$SHA256" <<'PY'
import json, sys
path, version, platform, object_key, sha256 = sys.argv[1:6]
with open(path, encoding='utf-8') as f:
  data = json.load(f)
cur = (data.get('version') or '').strip()
if not cur or tuple(int(x) for x in version.split('.')) >= tuple(int(x) for x in cur.split('.')):
  data['version'] = version
platforms = data.setdefault('platforms', {})
platforms[platform] = {'object_key': object_key, 'sha256': sha256}
with open(path, 'w', encoding='utf-8') as f:
  json.dump(data, f, indent=2)
  f.write('\n')
PY

echo "Publishing manifest.json (version $(python3 -c "import json; print(json.load(open('$MANIFEST_LOCAL'))['version'])"))"
npx wrangler r2 object put manifest.json --file "$MANIFEST_LOCAL" --bucket "$BUCKET" --content-type application/json --remote

echo "Done. Set UPDATE_SIGNING_SECRET on Cloudflare Pages if not already."
