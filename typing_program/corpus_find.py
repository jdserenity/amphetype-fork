"""Find imported corpus text containing a Performance Analysis type target."""

import random
import re

from typing_program.text_index import find_word_in_sources as _find_word_fts

_WORD_RE = re.compile(r"\w+(?:['-]\w+)*")

_CORPUS_SOURCES_SQL = """select distinct t.source
  from text as t
  join source as s on t.source = s.rowid
  where t.disabled is null and coalesce(s.discount, 0) = 0"""

_TEXTS_SQL = """select id, source, text from text
  where disabled is null and source = ?"""


def target_in_text(kind, data, text):
  if kind == 'word':
    return any(m.group(0) == data for m in _WORD_RE.finditer(text))
  if kind == 'biword':
    parts = (data or '').split(' ', 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
      return data in text
    w1, w2 = parts
    words = [m.group(0) for m in _WORD_RE.finditer(text or '')]
    return any(words[i] == w1 and words[i + 1] == w2 for i in range(len(words) - 1))
  return data in text


def corpus_sources(db):
  return [r[0] for r in db.execute(_CORPUS_SOURCES_SQL).fetchall()]


def find_text_for_target(db, kind, data, rng=None):
  """Random matching chunk from imported corpus (FTS for words, scan for trigram/char)."""
  rng = rng or random.Random()
  if kind == 'word':
    hit = _find_word_fts(db, data, None, rng)
    if hit:
      return hit
  sources = corpus_sources(db)
  rng.shuffle(sources)
  for source_id in sources:
    rows = db.execute(_TEXTS_SQL, (source_id,)).fetchall()
    matches = [r for r in rows if target_in_text(kind, data, r[2])]
    if matches:
      return rng.choice(matches)
  return None
