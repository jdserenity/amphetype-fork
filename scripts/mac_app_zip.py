#!/usr/bin/env python3
"""Zip dist/Typing Program.app for in-app updates (macOS). DMG is for first install email only."""
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'dist' / 'Typing Program.app'
OUT = ROOT / 'dist' / 'Typing Program-mac.zip'


def main():
  if not APP.is_dir():
    print(f'missing {APP} — run pyinstaller first', file=sys.stderr)
    return 1
  if OUT.is_file():
    OUT.unlink()
  with zipfile.ZipFile(OUT, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    for p in APP.rglob('*'):
      if p.is_file():
        zf.write(p, p.relative_to(APP.parent))
  print(OUT)
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
