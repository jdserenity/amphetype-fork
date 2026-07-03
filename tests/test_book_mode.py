"""Tests for book mode chapter splitting, chunking, cache, and progress."""

import json
import sqlite3
import time

import pytest

from typing_program.Data import AppDatabase
from typing_program.book_mode import (
  BookCatalog,
  done_chunk_count,
  ensure_practice_mode_migrated,
  format_book_progress,
  get_book_progress,
  is_chapter_header,
  lesson_text_id,
  list_book_sources,
  mark_chunk_done,
  MODE_CORPUS,
  MODE_IMPROVE,
  partition_chapter,
  practice_mode_from_settings,
  practice_mode_to_settings,
  reflow_paragraphs,
  set_book_progress,
  split_chapters,
  ensure_book_tables,
  _chunks_from_lengths,
  _lengths_from_chunks,
)


def test_is_chapter_header():
  assert is_chapter_header('Chapter 1')
  assert is_chapter_header('CHAPTER XII')
  assert is_chapter_header('I')
  assert is_chapter_header('Part 2')
  assert not is_chapter_header('It is a truth universally acknowledged')


def test_split_chapters_pride_style():
  text = "Chapter 1\n\nFirst line.\n\nChapter 2\n\nSecond line."
  ch = split_chapters(text)
  assert len(ch) == 2
  assert ch[0][0] == 'Chapter 1'
  assert 'First line' in ch[0][1]
  assert ch[1][0] == 'Chapter 2'


def test_split_chapters_kafka_roman():
  text = "I\n\nOne morning.\n\nII\n\nHe thought."
  ch = split_chapters(text)
  assert len(ch) == 2
  assert ch[0][0] == 'I'


def test_reflow_paragraphs_joins_wrapped_lines():
  text = "It is a truth\nof a good fortune.\n\nHowever little known"
  assert reflow_paragraphs(text) == "It is a truth of a good fortune.\n\nHowever little known"


def test_partition_chapter_joins_full_text():
  body = reflow_paragraphs("Para one.\n\nPara two is here.\n\nPara three.")
  chunks = partition_chapter(body, 10, 40)
  assert len(chunks) > 1
  assert ''.join(chunks) == body


def test_partition_preserves_paragraph_breaks_in_body():
  body = "Alpha.\n\nBeta."
  chunks = partition_chapter(body, 5, 100)
  assert chunks == [body]
  assert '\n\n' in body


def test_lesson_text_id_stable():
  a = lesson_text_id(3, 1, 0)
  b = lesson_text_id(3, 1, 0)
  c = lesson_text_id(3, 1, 1)
  assert a == b
  assert a != c


def test_practice_mode_settings_mapping():
  assert practice_mode_from_settings(0) == MODE_IMPROVE
  assert practice_mode_from_settings(1) == 'book'
  assert practice_mode_from_settings(2) == MODE_CORPUS
  assert practice_mode_to_settings('book') == 1
  assert practice_mode_to_settings(MODE_IMPROVE) == 0
  assert practice_mode_to_settings(MODE_CORPUS) == 2


class _FakeSettings:
  def __init__(self, data=None):
    self._data = dict(data or {})

  def contains(self, key):
    return key in self._data

  def value(self, key):
    return self._data[key]

  def get(self, key):
    return self._data[key]

  def set(self, key, val):
    self._data[key] = val


def test_practice_mode_migration_from_legacy():
  s = _FakeSettings({'practice_mode': 2})
  ensure_practice_mode_migrated(s)
  assert s.get('practice_mode') == 0
  assert s.get('practice_mode_v3') is True


def test_practice_mode_migration_old_normal_stays_improve():
  s = _FakeSettings({'practice_mode': 0})
  ensure_practice_mode_migrated(s)
  assert s.get('practice_mode') == 0


def test_practice_mode_v3_fixes_v2_corpus_default():
  s = _FakeSettings({'practice_mode': 2, 'practice_mode_v2': True})
  ensure_practice_mode_migrated(s)
  assert s.get('practice_mode') == 0
  assert s.get('practice_mode_v3') is True


def test_practice_mode_migration_skips_when_v3():
  s = _FakeSettings({'practice_mode': 2, 'practice_mode_v3': True})
  ensure_practice_mode_migrated(s)
  assert s.get('practice_mode') == 2


def _mem_db():
  return sqlite3.connect(':memory:', 5, 0, 'DEFERRED', False, AppDatabase)


def test_book_progress_db():
  conn = _mem_db()
  ensure_book_tables(conn)
  conn.execute("insert into source (name) values ('Test Book')")
  sid = conn.execute('select rowid from source').fetchone()[0]
  assert get_book_progress(conn, sid) == (0, 0)
  set_book_progress(conn, sid, 2, 3)
  assert get_book_progress(conn, sid) == (2, 3)
  now = time.time()
  mark_chunk_done(conn, sid, 0, 0, now)
  assert done_chunk_count(conn, sid) == 1


def test_list_book_sources_excludes_system():
  conn = _mem_db()
  ensure_book_tables(conn)
  conn.execute("insert into source (name, discount) values ('<Weakspot>', 1)")
  conn.execute("insert into source (name) values ('My Novel')")
  conn.execute("insert into text (id, text, source) values ('a', 'hello', 2)")
  conn.commit()
  names = [n for _, n in list_book_sources(conn)]
  assert 'My Novel' in names
  assert '<Weakspot>' not in names


def test_list_book_sources_excludes_disabled_texts():
  conn = _mem_db()
  ensure_book_tables(conn)
  conn.execute("insert into source (name) values ('Disabled Book')")
  sid = conn.execute('select rowid from source').fetchone()[0]
  conn.execute("insert into text (id, text, source, disabled) values ('x', 'hi', ?, 1)", (sid,))
  conn.commit()
  names = [n for _, n in list_book_sources(conn)]
  assert 'Disabled Book' not in names


def test_format_book_progress():
  assert format_book_progress('Chapter 4', 2, 10) == 'Chapter 4 · 3/10'


def test_chunk_length_roundtrip():
  chunks = ['abc', 'defgh', 'ij']
  lens = _lengths_from_chunks(chunks)
  assert _chunks_from_lengths('abcdefghij', lens) == chunks


def test_pride_file_reflows_wrapped_dialogue():
  from pathlib import Path
  p = Path(__file__).resolve().parent.parent / 'data/texts/Austen, Jane - Pride and Prejudice.txt'
  text = p.read_text(encoding='utf-8-sig')
  body = split_chapters(text)[0][1]
  start = body.find('"My dear Mr. Bennet,"')
  end = body.find('Mr. Bennet replied', start)
  segment = body[start:end]
  assert 'Netherfield Park is let at last?' in segment
  assert 'heard that\n' not in body


def test_book_catalog_caches_chapters(tmp_path):
  conn = _mem_db()
  ensure_book_tables(conn)
  texts = tmp_path / 'texts'
  texts.mkdir()
  book = texts / 'Sample.txt'
  book.write_text(
    "Chapter 1\n\nHello world.\n\nChapter 2\n\nGoodbye.\n",
    encoding='utf-8',
  )
  conn.execute("insert into source (name) values ('Sample.txt')")
  sid = conn.execute('select rowid from source').fetchone()[0]
  conn.commit()
  cat = BookCatalog(conn, texts)
  ch1 = cat.chapters(sid, 'Sample.txt', 5, 50)
  ch2 = cat.chapters(sid, 'Sample.txt', 5, 50)
  assert ch1 is ch2
  assert len(ch1) == 2
  row = conn.fetchone(
    'select body, chunk_lengths from book_chapter_cache where source=? and chapter_index=0',
    None,
    (sid,),
  )
  assert row is not None
  assert json.loads(row[1])


def test_book_chunk_result_row_records_char_count_and_duration():
  """Book chunks use hash text_ids; result rows still get char_count + duration like other modes."""
  from typing_program.stats_query import aggregate_session_wpm_from_results
  conn = sqlite3.connect(':memory:')
  conn.executescript("""
    create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real, char_count integer, duration real);
  """)
  now = time.time()
  sid = 7
  tid = lesson_text_id(sid, 2, 1)
  conn.execute(
    'insert into result (w,text_id,source,wpm,accuracy,viscosity,char_count,duration) values (?,?,?,?,?,?,?,?)',
    (now, tid, sid, 72.0, 1.0, 1.0, 360, 60.0))
  assert aggregate_session_wpm_from_results(conn, now - 86400) == pytest.approx(72.0)
