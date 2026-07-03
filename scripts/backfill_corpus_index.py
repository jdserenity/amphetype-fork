#!/usr/bin/env python3
"""Build text_fts for novel chunks already in the DB. Run once after upgrading to FTS search.

  python scripts/backfill_corpus_index.py [path/to.db]

Uses the app DB if no path given (see typing_program/db_paths.py). New imports are indexed automatically.
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from typing_program.db_paths import find_database_path  # noqa: E402
from typing_program.text_index import backfill_corpus_index, ensure_corpus_index  # noqa: E402


class _DB:
  def __init__(self, conn):
    self._conn = conn
  def execute(self, sql, params=()):
    return self._conn.execute(sql, params)


def main():
  explicit = sys.argv[1] if len(sys.argv) > 1 else None
  db_path, tried = find_database_path(explicit)
  if db_path is None:
    print('Could not find a database file.', file=sys.stderr)
    for p in tried:
      print('  %s' % p, file=sys.stderr)
    sys.exit(1)
  conn = sqlite3.connect(str(db_path))
  db = _DB(conn)
  ensure_corpus_index(db)
  before = conn.execute("select count(*) from text_fts").fetchone()[0]
  backfill_corpus_index(db)
  after = conn.execute("select count(*) from text_fts").fetchone()[0]
  conn.commit()
  conn.close()
  print("DB: %s" % db_path)
  print("Indexed %d new chunks (%d total in text_fts)" % (after - before, after))


if __name__ == "__main__":
  main()
