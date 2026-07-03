#!/usr/bin/env python3
"""Clear typing stats; keep imported books, sources, and book reading progress.

  python scripts/reset_db.py [path/to.db]

From anywhere in the repo (or pass an absolute path to your .db file).
Backs up the database as <name>.bak-<timestamp> beside it before clearing stats.

Without a path, uses the same database location as the running app:
  - TYPING_PROGRAM_LOCAL=1 → typing_program/data/<user>.db
  - db_name= in typing_program.ini or TYPING_PROGRAM_SETTINGS
  - otherwise ~/Library/Application Support/Typing Program/typing-program.db, with legacy
    ~/Library/Application Support/amphetype/<user>.db copied once on first run if needed
"""

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from typing_program.db_paths import find_database_path  # noqa: E402
from typing_program.reset_stats import reset_typing_stats  # noqa: E402


def _backup_db(db_path):
  stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
  bak = db_path.with_name('%s.bak-%s' % (db_path.name, stamp))
  shutil.copy2(db_path, bak)
  return bak


def main():
  explicit = sys.argv[1] if len(sys.argv) > 1 else None
  db_path, tried = find_database_path(explicit)
  if db_path is None:
    print('Could not find a database file.', file=sys.stderr)
    if explicit:
      print('Not found: %s' % tried[0], file=sys.stderr)
    else:
      print('Checked:', file=sys.stderr)
      for p in tried:
        print('  %s' % p, file=sys.stderr)
    print('Usage: python scripts/reset_db.py [path/to.db]', file=sys.stderr)
    sys.exit(1)
  bak = _backup_db(db_path)
  print('Backup: %s' % bak)
  conn = sqlite3.connect(str(db_path))
  try:
    reset_typing_stats(conn)
  except RuntimeError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
  finally:
    conn.close()
  print('Typing stats cleared (books, sources, and book progress kept).')
  print('Database: %s' % db_path)


if __name__ == '__main__':
  main()
