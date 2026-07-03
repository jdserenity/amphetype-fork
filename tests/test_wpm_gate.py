"""Tests for WPM calibration gate (first N lessons)."""

import sqlite3
import time

import pytest

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
from typing_program.stats_query import (
  WPM_GATE_MIN_LESSONS,
  aggregate_session_wpm_from_results,
  count_wpm_gate_lessons,
  format_avg_wpm_label,
  lesson_qualifies_for_wpm_gate,
  should_record_lesson_wpm,
  wpm_gate_complete,
)


def _gate_db():
  conn = sqlite3.connect(':memory:')
  conn.executescript("""
    create table source (rowid integer primary key, name text, disabled integer, discount integer);
    create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real, char_count integer, duration real);
  """)
  conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
  conn.execute("insert into source (rowid, name, discount) values (2, '<Weakspot>', 1)")
  conn.execute("insert into source (rowid, name, discount) values (3, '<Reviews>', 1)")
  return conn


def _insert_qualifying(conn, source_id, wpm=60.0, char_count=60, duration=12.0):
  conn.execute(
    'insert into result (w, text_id, source, wpm, accuracy, viscosity, char_count, duration) values (?,?,?,?,?,?,?,?)',
    (time.time(), 't', source_id, wpm, 1.0, 1.0, char_count, duration))


def test_lesson_qualifies_for_wpm_gate():
  assert lesson_qualifies_for_wpm_gate(MODE_CORPUS)
  assert lesson_qualifies_for_wpm_gate(MODE_BOOK)
  assert lesson_qualifies_for_wpm_gate(MODE_IMPROVE, improve_submode=0)
  assert not lesson_qualifies_for_wpm_gate(MODE_IMPROVE, improve_submode=1)
  assert not lesson_qualifies_for_wpm_gate(MODE_CORPUS, focus_drill=True)


def test_count_wpm_gate_lessons_includes_corpus_book_and_weakspot():
  conn = _gate_db()
  _insert_qualifying(conn, 1)
  _insert_qualifying(conn, 2, wpm=None, char_count=None, duration=None)
  conn.execute(
    'insert into result (w, text_id, source, wpm, accuracy, viscosity, char_count, duration) values (?,?,?,?,?,?,?,?)',
    (time.time(), 'r', 3, 50.0, 1.0, 1.0, 50, 10.0))
  assert count_wpm_gate_lessons(conn) == 2


def test_should_record_lesson_wpm_after_gate():
  conn = _gate_db()
  assert not should_record_lesson_wpm(conn)
  for _ in range(WPM_GATE_MIN_LESSONS):
    _insert_qualifying(conn, 1, wpm=None, char_count=None, duration=None)
  assert wpm_gate_complete(conn)
  assert should_record_lesson_wpm(conn)


def test_format_avg_wpm_label_before_and_after_gate():
  conn = _gate_db()
  assert format_avg_wpm_label(conn) == 'Complete 10 lessons to calculate WPM'
  for i in range(3):
    _insert_qualifying(conn, 1, wpm=None, char_count=None, duration=None)
  assert format_avg_wpm_label(conn) == 'Complete 7 more lessons to calculate WPM'
  for _ in range(7):
    _insert_qualifying(conn, 1, wpm=60.0, char_count=60, duration=12.0)
  assert format_avg_wpm_label(conn) == 'Avg WPM: 60.0'


def test_aggregate_session_wpm_from_results_ignores_ungated_rows():
  conn = _gate_db()
  now = 1e9
  conn.executemany(
    'insert into result (w,text_id,source,wpm,accuracy,viscosity,char_count,duration) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'a', 1, None, 1.0, 1.0, None, None),
      (now, 'b', 1, 80.0, 1.0, 1.0, 400, 60.0),
    ])
  assert aggregate_session_wpm_from_results(conn, now - 86400) == pytest.approx(80.0)
