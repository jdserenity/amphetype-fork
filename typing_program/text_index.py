"""FTS5 index over imported novel chunks for fast Find in corpus."""

import random
import re

_WORD_RE = re.compile(r"\w+(?:['-]\w+)*")

_CORPUS_TEXTS_SQL = """select t.id, t.source, t.text
  from text as t
  join source as s on t.source = s.rowid
  where t.disabled is null and coalesce(s.discount, 0) = 0"""

_FTS_CREATE = """create virtual table if not exists text_fts using fts5(
  body,
  text_id unindexed,
  source_id unindexed,
  tokenize='unicode61'
)"""

_FTS_INSERT = "insert into text_fts (body, text_id, source_id) values (?,?,?)"
_FTS_DELETE = "delete from text_fts where text_id = ?"


def fts_quote(term):
  return '"' + term.replace('"', '""') + '"'


def ensure_corpus_index(db):
  db.execute(_FTS_CREATE)


def is_corpus_source(db, source_id):
  row = db.execute(
    "select coalesce(s.discount, 0) from source as s where s.rowid = ?", (source_id,)).fetchone()
  return row is not None and int(row[0] or 0) == 0


def index_chunk(db, text_id, source_id, body):
  if not is_corpus_source(db, source_id):
    return
  ensure_corpus_index(db)
  db.execute(_FTS_DELETE, (text_id,))
  db.execute(_FTS_INSERT, (body, text_id, source_id))


def backfill_corpus_index(db):
  """Index corpus chunks not yet in text_fts (bulk import / Sources import)."""
  ensure_corpus_index(db)
  try:
    indexed = {r[0] for r in db.execute("select text_id from text_fts").fetchall()}
  except Exception:
    indexed = set()
  for text_id, source_id, body in db.execute(_CORPUS_TEXTS_SQL).fetchall():
    if text_id not in indexed:
      db.execute(_FTS_INSERT, (body, text_id, source_id))


def word_in_text(data, text):
  return any(m.group(0) == data for m in _WORD_RE.finditer(text))


def _load_chunk(db, text_id):
  row = db.execute(
    "select id, source, text from text where id = ? and disabled is null", (text_id,)).fetchone()
  if row:
    return row
  return db.execute(
    "select text_id, source_id, body from text_fts where text_id = ?", (text_id,)).fetchone()


def _fts_hits(db, data, source_ids=None):
  try:
    q = fts_quote(data)
    if source_ids:
      placeholders = ','.join('?' * len(source_ids))
      sql = ("select text_id, source_id from text_fts"
             " where body match ? and source_id in (%s)") % placeholders
      return db.execute(sql, (q,) + tuple(source_ids)).fetchall()
    return db.execute(
      """select f.text_id, f.source_id from text_fts as f
        join source as s on f.source_id = s.rowid
        where f.body match ? and coalesce(s.discount, 0) = 0""",
      (q,)).fetchall()
  except Exception:
    return []


def find_word_in_sources(db, data, sources, rng=None):
  """FTS lookup with case-sensitive verify; sources=None searches all corpus."""
  rng = rng or random.Random()
  source_ids = list(sources) if sources is not None else None
  if source_ids is not None:
    source_ids = list(source_ids)
    rng.shuffle(source_ids)
  hits = _fts_hits(db, data, source_ids)
  if source_ids is None:
    rng.shuffle(hits)
  verified = []
  for text_id, _ in hits:
    row = _load_chunk(db, text_id)
    if row and word_in_text(data, row[2]):
      verified.append(row)
  if verified:
    return rng.choice(verified)
  return None
