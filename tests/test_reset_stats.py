"""Tests for dev reset: clear typing stats, keep books and reading progress."""

import sqlite3
import time

from typing_program.Data import AppDatabase
from typing_program.app_meta import ensure_app_meta, set_app_meta_int
from typing_program.book_mode import ensure_book_tables, set_book_progress, mark_chunk_done
from typing_program.reset_stats import reset_typing_stats, TYPING_STAT_TABLES


def _seed_db(path):
  db = sqlite3.connect(str(path), 5, 0, 'DEFERRED', False, AppDatabase)
  db.execute("insert into source (name, disabled, discount) values ('Pride and Prejudice', null, null)")
  sid = db.execute('select rowid from source').fetchone()[0]
  db.execute("insert into text (id, source, text, disabled) values ('t1', ?, 'It is a truth.', null)", (sid,))
  db.execute(
    'insert into result (w, text_id, source, wpm, accuracy, viscosity, char_count, duration) values (?,?,?,?,?,?,?,?)',
    (time.time(), 't1', sid, 80.0, 0.99, 0.0, 12, 1.5),
  )
  w = time.time()
  db.execute(
    'insert into statistic (w, data, type, time, count, mistakes, viscosity, source) values (?,?,?,?,?,?,?,?)',
    (w, 'truth', 2, 0.12, 3, 0, 0.0, sid),
  )
  db.execute(
    'insert into mistake (w, target, mistake, count) values (?,?,?,?)',
    (w, 'truth', 'truh', 1),
  )
  ensure_app_meta(db)
  set_app_meta_int(db, 'preferences_tab', 2)
  ensure_book_tables(db)
  set_book_progress(db, sid, 1, 2)
  mark_chunk_done(db, sid, 0, 0, time.time())
  db.execute(
    'insert into book_source_meta (source, content_key, chapter_count) values (?,?,?)',
    (sid, 'v2:file:test.txt:1:100', 5),
  )
  db.execute(
    'insert into book_chapter_cache (source, chapter_index, title, body, chunk_lengths, spec_key) values (?,?,?,?,?,?)',
    (sid, 0, 'Chapter 1', 'Body text', '[10]', '50:200'),
  )
  db.commit()
  return db, sid


def test_reset_typing_stats_clears_stats_only(tmp_path):
  db_path = tmp_path / 'test.db'
  db, sid = _seed_db(db_path)
  reset_typing_stats(db)
  for table in TYPING_STAT_TABLES:
    assert db.execute('select count(*) from %s' % table).fetchone()[0] == 0
  assert db.execute('select count(*) from source').fetchone()[0] == 1
  assert db.execute('select count(*) from text').fetchone()[0] == 1
  assert db.fetchone('select chapter_index, chunk_index from book_progress where source=?', None, (sid,)) == (1, 2)
  assert db.execute('select count(*) from book_lesson_done where source=?', (sid,)).fetchone()[0] == 1
  assert db.execute('select count(*) from book_source_meta where source=?', (sid,)).fetchone()[0] == 1
  assert db.execute('select count(*) from book_chapter_cache where source=?', (sid,)).fetchone()[0] == 1
  assert db.fetchone('select value from app_meta where key=?', (None,), ('preferences_tab',))[0] == '2'
  db.close()


def test_reset_typing_stats_sets_weakspot_discount(tmp_path):
  db_path = tmp_path / 'test.db'
  db = sqlite3.connect(str(db_path), 5, 0, 'DEFERRED', False, AppDatabase)
  db.execute("insert into source (name, disabled, discount) values ('<Weakspot>', null, null)")
  reset_typing_stats(db)
  assert db.execute('select discount from source where name=?', ('<Weakspot>',)).fetchone()[0] == 1
  db.close()
