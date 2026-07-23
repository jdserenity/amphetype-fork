import hashlib
import sqlite3

import pytest

from typing_program.Data import AppDatabase


@pytest.fixture
def db(tmp_path, monkeypatch):
  path = tmp_path / 'test.db'
  conn = sqlite3.connect(str(path), 5, 0, 'DEFERRED', False, AppDatabase)
  monkeypatch.setattr('typing_program.TextManager.DB', conn)
  return conn


def _insert_text(db, source_id, content):
  txt_id = hashlib.sha1(content.encode('utf-8')).hexdigest()
  db.execute('insert into text (id,text,source,disabled) values (?,?,?,?)',
             (txt_id, content, source_id, None))
  return txt_id


def test_addTexts_replace_removes_old_lessons(db):
  from typing_program.TextManager import TextManager

  tm = TextManager()
  sid = db.getSource('Kafka, Franz - Metamorphosis.txt')
  old_id = _insert_text(db, sid, 'old boilerplate lesson one two three four five')
  db.execute('insert into result (w,text_id,source,wpm,accuracy,viscosity) values (?,?,?,?,?,?)',
             (1.0, old_id, sid, 50.0, 1.0, 0.0))

  tm.addTexts('Kafka, Franz - Metamorphosis.txt', ['fresh lesson one two three four five six'], replace=True)
  db.commit()

  rows = db.fetchall('select text from text where source = ?', (sid,))
  assert len(rows) == 1
  assert rows[0][0].startswith('fresh lesson')
  assert db.fetchall('select text_id from result where text_id = ?', (old_id,)) == []


def test_addTexts_can_defer_fts_until_backfill(db):
  from typing_program.TextManager import TextManager
  from typing_program.text_index import backfill_corpus_index, ensure_corpus_index

  tm = TextManager()
  lessons = [
    'first lesson with enough words to be a real chunk of practice text here',
    'second lesson with enough words to be a real chunk of practice text here',
  ]
  ids = tm.addTexts('Fast Import.txt', lessons, update=False, index=False)
  db.commit()
  assert len(ids) == 2
  ensure_corpus_index(db)
  assert db.execute('select count(*) from text_fts').fetchone()[0] == 0
  tm._index_new_corpus_texts()
  db.commit()
  assert db.execute('select count(*) from text_fts').fetchone()[0] == 2


def test_clear_source_texts_removes_fts_rows(db):
  from typing_program.TextManager import TextManager
  from typing_program.text_index import index_chunk

  tm = TextManager()
  sid = db.getSource('Clear FTS.txt')
  body = 'lesson text for fts clear test with enough characters'
  txt_id = _insert_text(db, sid, body)
  index_chunk(db, txt_id, sid, body)
  db.commit()
  assert db.execute('select count(*) from text_fts where text_id = ?', (txt_id,)).fetchone()[0] == 1
  tm._clear_source_texts(sid)
  db.commit()
  assert db.execute('select count(*) from text where source = ?', (sid,)).fetchone()[0] == 0
  assert db.execute('select count(*) from text_fts where text_id = ?', (txt_id,)).fetchone()[0] == 0


def test_clear_source_texts_is_set_based_for_many_lessons(db, monkeypatch):
  """Deleting a source must not issue one DELETE per lesson (that is what made GUI deletes crawl)."""
  from typing_program.TextManager import TextManager
  from typing_program.text_index import ensure_corpus_index

  tm = TextManager()
  sid = db.getSource('Many Lessons.txt')
  ensure_corpus_index(db)
  for i in range(50):
    body = f'lesson number {i} with enough padding words to be unique content here'
    txt_id = _insert_text(db, sid, body)
    db.execute('insert into text_fts (body, text_id, source_id) values (?,?,?)',
               (body, txt_id, sid))
    db.execute('insert into result (w,text_id,source,wpm,accuracy,viscosity) values (?,?,?,?,?,?)',
               (1.0, txt_id, sid, 40.0, 1.0, 0.0))
  db.commit()

  deletes = []
  real_execute = db.execute
  def counting_execute(sql, *args):
    if isinstance(sql, str) and sql.strip().lower().startswith('delete'):
      deletes.append(sql.strip().split()[0:4])
    return real_execute(sql, *args)
  monkeypatch.setattr(db, 'execute', counting_execute)

  tm._clear_source_texts(sid)
  db.commit()
  # One delete each for result, text_fts, text — not 50×2+1.
  assert len(deletes) <= 4
  assert db.execute('select count(*) from text where source = ?', (sid,)).fetchone()[0] == 0
  assert db.execute('select count(*) from text_fts where source_id = ?', (sid,)).fetchone()[0] == 0
  assert db.execute('select count(*) from result where source = ?', (sid,)).fetchone()[0] == 0
