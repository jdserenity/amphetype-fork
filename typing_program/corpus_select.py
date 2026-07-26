"""Equal-weight corpus book rotation; used-book set persists in app_meta."""

import json
import random

from typing_program.app_meta import ensure_app_meta, get_app_meta_raw, set_app_meta_raw

CORPUS_USED_SOURCES_KEY = 'corpus_used_sources'

_ELIGIBLE_SOURCES_SQL = """
select distinct s.rowid
  from source as s
  join text as t on t.source = s.rowid
 where t.disabled is null
   and s.disabled is null
   and coalesce(s.discount, 0) = 0
   and s.name not like '<%>'
"""

_TEXTS_FOR_SOURCE_SQL = """
select id, source, text from text
 where disabled is null and source = ?
"""


def list_eligible_corpus_sources(db):
  return [r[0] for r in db.execute(_ELIGIBLE_SOURCES_SQL).fetchall()]


def load_used_sources(db):
  ensure_app_meta(db)
  raw = get_app_meta_raw(db, CORPUS_USED_SOURCES_KEY, None)
  if not raw:
    return set()
  try:
    data = json.loads(raw)
  except (TypeError, ValueError, json.JSONDecodeError):
    return set()
  if not isinstance(data, list):
    return set()
  out = set()
  for x in data:
    try:
      out.add(int(x))
    except (TypeError, ValueError):
      pass
  return out


def save_used_sources(db, used):
  ensure_app_meta(db)
  set_app_meta_raw(db, CORPUS_USED_SOURCES_KEY, json.dumps(sorted(int(x) for x in used)))


def pick_corpus_text(db, rng=None):
  """Pick (id, source, text) by rotating books without replacement; None if empty."""
  rng = rng or random.Random()
  eligible = set(list_eligible_corpus_sources(db))
  if not eligible:
    return None
  used = load_used_sources(db) & eligible
  pool = list(eligible - used)
  if not pool:
    used = set()
    pool = list(eligible)
  source_id = rng.choice(pool)
  rows = db.execute(_TEXTS_FOR_SOURCE_SQL, (source_id,)).fetchall()
  if not rows:
    return None
  row = rng.choice(rows)
  used.add(source_id)
  save_used_sources(db, used)
  return row
