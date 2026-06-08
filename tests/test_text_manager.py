import hashlib
import sqlite3

import pytest

from amphetype.Data import AmphDatabase


@pytest.fixture
def db(tmp_path, monkeypatch):
  path = tmp_path / 'test.db'
  conn = sqlite3.connect(str(path), 5, 0, 'DEFERRED', False, AmphDatabase)
  monkeypatch.setattr('amphetype.TextManager.DB', conn)
  return conn


def _insert_text(db, source_id, content):
  txt_id = hashlib.sha1(content.encode('utf-8')).hexdigest()
  db.execute('insert into text (id,text,source,disabled) values (?,?,?,?)',
             (txt_id, content, source_id, None))
  return txt_id


def test_addTexts_replace_removes_old_lessons(db):
  from amphetype.TextManager import TextManager

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
