#!/usr/bin/env python3
"""Clear typing stats from the app DB; keep imported books/sources and book progress.

  python scripts/reset_db.py [path/to.db]

Backs up the current file as <name>.bak-<timestamp> beside it before changing anything.
Uses the app DB if no path given (typing_program.ini, then typing_program/data/<user>.db, then
~/Library/Application Support/typing-program/<user>.db).
"""

import getpass
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from typing_program.Data import AppDatabase  # noqa: E402
from typing_program.reset_stats import reset_typing_stats  # noqa: E402


def _default_db_path():
  ini = ROOT / "typing_program/data/typing_program.ini"
  if ini.is_file():
    for line in ini.read_text(encoding='utf-8').splitlines():
      if line.startswith('db_name='):
        p = Path(line.split('=', 1)[1].strip())
        if p.is_file():
          return p
  user = re.sub(r'[^a-z0-9_-]', '', getpass.getuser(), flags=re.I) or 'user'
  local = ROOT / "typing_program/data" / f"{user}.db"
  default = Path.home() / "Library/Application Support/typing-program" / f"{user}.db"
  if local.is_file():
    return local
  if default.is_file():
    return default
  return default


def _backup_db(db_path):
  if not db_path.is_file():
    return None
  stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
  bak = db_path.with_name('%s.bak-%s' % (db_path.name, stamp))
  shutil.copy2(db_path, bak)
  return bak


def main():
  db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_db_path()
  db_path.parent.mkdir(parents=True, exist_ok=True)
  bak = _backup_db(db_path)
  if bak is not None:
    print('Backup: %s' % bak)
  db = sqlite3.connect(str(db_path), 5, 0, 'DEFERRED', False, AppDatabase)
  reset_typing_stats(db)
  db.close()
  print('Typing stats cleared (books, sources, and book progress kept): %s' % db_path)


if __name__ == '__main__':
  main()
