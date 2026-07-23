import hashlib
import sqlite3
from pathlib import Path

import pytest

from typing_program.Data import AppDatabase
from typing_program.import_texts import (
  clear_source_texts,
  import_text_file,
  import_texts_dir,
  insert_lessons,
  list_text_files,
)
from typing_program.lesson_miner import mine_lessons_from_file
from typing_program.text_index import ensure_corpus_index


@pytest.fixture
def db(tmp_path):
  path = tmp_path / 'test.db'
  return sqlite3.connect(str(path), 5, 0, 'DEFERRED', False, AppDatabase)


def _write_book(path, paras):
  path.write_text('\n\n'.join(paras) + '\n', encoding='utf-8')
  return path


def test_mine_lessons_splits_on_blank_lines(tmp_path):
  # Several short paras so the miner packs them until min_chars.
  paras = [
    'Alpha one two three four five six seven eight nine ten.',
    'Bravo one two three four five six seven eight nine ten.',
    'Charlie one two three four five six seven eight nine ten.',
    'Delta one two three four five six seven eight nine ten.',
    'Echo one two three four five six seven eight nine ten.',
  ]
  p = _write_book(tmp_path / 'Tiny Book.txt', paras)
  lessons = mine_lessons_from_file(str(p), min_chars=80, max_chars=400, break_sentences=False)
  assert len(lessons) >= 1
  joined = '\n'.join(lessons)
  assert 'Alpha' in joined and 'Echo' in joined


def test_import_text_file_inserts_lessons_and_fts(db, tmp_path):
  book = _write_book(tmp_path / 'Demo Author - Demo Book.txt', [
    'Once upon a time there was a typing lesson with plenty of words in a row for length.',
    'Later the hero typed another paragraph with enough characters to fill a lesson chunk.',
    'Finally everyone celebrated with yet more words so the third paragraph also joins in.',
  ])
  texts_dir = tmp_path / 'texts'
  r = import_text_file(db, book, texts_dir=texts_dir, replace=False, skip_existing=True,
                       min_chars=60, max_chars=400)
  db.commit()
  assert r.skipped is False
  assert r.inserted >= 1
  assert (texts_dir / book.name).is_file()
  n = db.fetchone('select count(*) from text where source = ?', (0,), (r.source_id,))[0]
  assert n == r.inserted
  ensure_corpus_index(db)
  fts = db.fetchone('select count(*) from text_fts where source_id = ?', (0,), (r.source_id,))[0]
  assert fts == r.inserted


def test_import_skips_existing_unless_replace(db, tmp_path):
  book = _write_book(tmp_path / 'Skip Me.txt', [
    'Word ' * 40,
    'More ' * 40,
  ])
  texts_dir = tmp_path / 'texts'
  r1 = import_text_file(db, book, texts_dir=texts_dir, min_chars=40, max_chars=200)
  db.commit()
  r2 = import_text_file(db, book, texts_dir=texts_dir, min_chars=40, max_chars=200)
  assert r2.skipped is True
  assert r2.inserted == 0
  r3 = import_text_file(db, book, texts_dir=texts_dir, replace=True, skip_existing=False,
                        min_chars=40, max_chars=200)
  db.commit()
  assert r3.skipped is False
  assert r3.replaced is True
  assert r3.inserted >= 1


def test_clear_source_texts_removes_fts(db, tmp_path):
  book = _write_book(tmp_path / 'Clear.txt', ['Hello world ' * 30, 'Goodbye world ' * 30])
  r = import_text_file(db, book, texts_dir=tmp_path / 'texts', min_chars=40, max_chars=200)
  db.commit()
  clear_source_texts(db, r.source_id)
  db.commit()
  assert db.fetchone('select count(*) from text where source = ?', (0,), (r.source_id,))[0] == 0
  assert db.fetchone('select count(*) from text_fts where source_id = ?', (0,), (r.source_id,))[0] == 0


def test_import_texts_dir_imports_all_txt(db, tmp_path):
  d = tmp_path / 'texts'
  d.mkdir()
  _write_book(d / 'A.txt', ['Aaa ' * 50])
  _write_book(d / 'B.txt', ['Bbb ' * 50])
  (d / 'notes.md').write_text('nope', encoding='utf-8')
  assert [p.name for p in list_text_files(d)] == ['A.txt', 'B.txt']
  results = import_texts_dir(db, d, min_chars=40, max_chars=200)
  db.commit()
  assert len(results) == 2
  assert all(r.inserted >= 1 for r in results)


def test_import_without_index_then_rebuild(db, tmp_path):
  from typing_program.import_texts import rebuild_corpus_index
  book = _write_book(tmp_path / 'NoIndex.txt', ['Word ' * 40, 'More ' * 40])
  r = import_text_file(db, book, texts_dir=tmp_path / 'texts', min_chars=40, max_chars=200,
                       index=False)
  db.commit()
  assert r.inserted >= 1
  # No FTS rows until rebuild
  try:
    n = db.execute('select count(*) from text_fts').fetchone()[0]
  except Exception:
    n = 0
  assert n == 0
  rebuild_corpus_index(db)
  db.commit()
  assert db.execute('select count(*) from text_fts where source_id = ?',
                    (r.source_id,)).fetchone()[0] == r.inserted
