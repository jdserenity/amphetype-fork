"""Import novel .txt files into the app DB (same as Sources → Import text)."""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from typing_program.lesson_miner import (
  DEFAULT_BREAK_SENTENCES,
  DEFAULT_MAX_CHARS,
  DEFAULT_MIN_CHARS,
  mine_lessons_from_file,
)
from typing_program.text_index import index_chunk


@dataclass
class ImportResult:
  source_name: str
  source_id: int
  inserted: int
  skipped: bool = False
  replaced: bool = False


def get_or_create_source(db, source_name, lesson=None):
  row = db.execute(
    'select rowid, discount from source where name = ? limit 1', (source_name,)).fetchone()
  if row:
    rid, disc = row
    db.execute('update source set disabled = NULL where rowid = ?', (rid,))
    if lesson is not None and disc is None:
      db.execute('update source set discount = ? where rowid = ?', (lesson, rid))
    return rid
  db.execute('insert into source (name, discount) values (?,?)', (source_name, lesson))
  return get_or_create_source(db, source_name, lesson)


def clear_source_texts(db, source_id):
  # Set-based — same idea as TextManager._clear_source_texts.
  db.execute('delete from result where text_id in (select id from text where source = ?)', (source_id,))
  try:
    db.execute('delete from text_fts where source_id = ?', (source_id,))
  except Exception:
    pass
  db.execute('delete from text where source = ?', (source_id,))


def source_text_count(db, source_id):
  return int(db.execute(
    'select count(*) from text where source = ?', (source_id,)).fetchone()[0])


def insert_lessons(db, source_id, lessons, *, index=True):
  inserted = 0
  for x in lessons:
    h = hashlib.sha1()
    h.update(x.encode('utf-8'))
    txt_id = h.hexdigest()
    try:
      db.execute('insert into text (id,text,source,disabled) values (?,?,?,?)',
                 (txt_id, x, source_id, None))
      if index:
        index_chunk(db, txt_id, source_id, x)
      inserted += 1
    except Exception:
      pass # silently skip duplicates (same as TextManager.addTexts)
  return inserted


def import_text_file(db, path, *, texts_dir=None, replace=False, skip_existing=True,
                     min_chars=DEFAULT_MIN_CHARS, max_chars=DEFAULT_MAX_CHARS,
                     break_sentences=DEFAULT_BREAK_SENTENCES, progress=None, index=True):
  path = Path(path)
  if not path.is_file():
    raise FileNotFoundError(path)
  source_name = path.name
  if texts_dir is not None:
    dest = Path(texts_dir) / source_name
    if path.resolve() != dest.resolve():
      dest.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(path, dest)
    path = dest

  source_id = get_or_create_source(db, source_name)
  if skip_existing and not replace and source_text_count(db, source_id) > 0:
    return ImportResult(source_name, source_id, 0, skipped=True)

  replaced = False
  if replace and source_text_count(db, source_id) > 0:
    clear_source_texts(db, source_id)
    replaced = True

  lessons = mine_lessons_from_file(
    str(path), min_chars=min_chars, max_chars=max_chars,
    break_sentences=break_sentences, progress=progress)
  inserted = insert_lessons(db, source_id, lessons, index=index)
  return ImportResult(source_name, source_id, inserted, replaced=replaced)


def list_text_files(texts_dir):
  d = Path(texts_dir)
  return sorted(p for p in d.glob('*.txt') if p.is_file())


def import_texts_dir(db, texts_dir, *, replace=False, skip_existing=True,
                     min_chars=DEFAULT_MIN_CHARS, max_chars=DEFAULT_MAX_CHARS,
                     break_sentences=DEFAULT_BREAK_SENTENCES, on_file=None, index=True):
  results = []
  for path in list_text_files(texts_dir):
    if on_file is not None:
      on_file(path)
    results.append(import_text_file(
      db, path, texts_dir=texts_dir, replace=replace, skip_existing=skip_existing,
      min_chars=min_chars, max_chars=max_chars, break_sentences=break_sentences,
      index=index))
  return results


def rebuild_corpus_index(db):
  """Drop and rebuild text_fts in one pass (safer than indexing every insert)."""
  from typing_program.text_index import backfill_corpus_index, ensure_corpus_index
  try:
    db.execute('drop table if exists text_fts')
  except Exception:
    pass
  ensure_corpus_index(db)
  backfill_corpus_index(db)
