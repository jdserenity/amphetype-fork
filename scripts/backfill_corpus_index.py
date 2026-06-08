#!/usr/bin/env python3
"""Build text_fts for novel chunks already in the DB. Run once after upgrading to FTS search.

  python scripts/backfill_corpus_index.py [path/to.db]

Uses the app DB if no path given (amphetype.ini, then amphetype/data/<user>.db, then
~/Library/Application Support/amphetype/<user>.db). New imports are indexed automatically.
"""

import getpass
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from amphetype.text_index import backfill_corpus_index, ensure_corpus_index  # noqa: E402


class _DB:
  def __init__(self, conn):
    self._conn = conn
  def execute(self, sql, params=()):
    return self._conn.execute(sql, params)


def _default_db_path():
  ini = ROOT / "amphetype/data/amphetype.ini"
  if ini.is_file():
    for line in ini.read_text(encoding='utf-8').splitlines():
      if line.startswith('db_name='):
        p = Path(line.split('=', 1)[1].strip())
        if p.is_file():
          return p
  user = re.sub(r'[^a-z0-9_-]', '', getpass.getuser(), flags=re.I) or 'user'
  local = ROOT / "amphetype/data" / f"{user}.db"
  default = Path.home() / "Library/Application Support/amphetype" / f"{user}.db"
  if local.is_file():
    return local
  if default.is_file():
    return default
  return default


def main():
  db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_db_path()
  if not db_path.is_file():
    print("No database at %s" % db_path, file=sys.stderr)
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
