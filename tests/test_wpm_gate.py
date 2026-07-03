"""Tests for WPM calibration gate (first N lessons)."""

import sqlite3
import time

import pytest

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
from typing_program.stats_query import (
  WPM_GATE_MIN_LESSONS,
  aggregate_session_wpm_from_results,
  count_wpm_gate_lessons,
  first_qualifying_session_wpm,
  format_avg_wpm_label,
  lesson_qualifies_for_wpm_gate,
  session_wpm_since_start_gain,
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
  _insert_qualifying(conn, 2)
  conn.execute(
    'insert into result (w, text_id, source, wpm, accuracy, viscosity, char_count, duration) values (?,?,?,?,?,?,?,?)',
    (time.time(), 'r', 3, 50.0, 1.0, 1.0, 50, 10.0))
  assert count_wpm_gate_lessons(conn) == 2


def test_format_avg_wpm_label_hides_until_ten_then_uses_all_saved_runs():
  conn = _gate_db()
  assert format_avg_wpm_label(conn) == 'Complete 10 lessons to calculate WPM'
  for _ in range(3):
    _insert_qualifying(conn, 1, wpm=40.0, char_count=40, duration=12.0)
  assert format_avg_wpm_label(conn) == 'Complete 7 more lessons to calculate WPM'
  assert aggregate_session_wpm_from_results(conn, 0) == pytest.approx(40.0)
  for _ in range(7):
    _insert_qualifying(conn, 1, wpm=80.0, char_count=80, duration=12.0)
  assert wpm_gate_complete(conn)
  assert format_avg_wpm_label(conn).startswith('Avg WPM:')


def test_session_wpm_since_start_gain_hidden_until_gate():
  conn = _gate_db()
  _insert_qualifying(conn, 1, wpm=40.0, char_count=40, duration=12.0)
  assert session_wpm_since_start_gain(conn) is None


def test_session_wpm_since_start_gain_after_gate():
  conn = _gate_db()
  _insert_qualifying(conn, 1, wpm=40.0, char_count=40, duration=12.0)
  for _ in range(WPM_GATE_MIN_LESSONS - 1):
    _insert_qualifying(conn, 1, wpm=80.0, char_count=80, duration=12.0)
  assert first_qualifying_session_wpm(conn) == pytest.approx(40.0)
  gain = session_wpm_since_start_gain(conn)
  assert gain is not None
  assert gain > 0


def test_avg_wpm_after_gate_includes_first_ten_lessons():
  conn = _gate_db()
  _insert_qualifying(conn, 1, wpm=40.0, char_count=40, duration=12.0)
  _insert_qualifying(conn, 1, wpm=80.0, char_count=80, duration=12.0)
  for _ in range(WPM_GATE_MIN_LESSONS - 2):
    _insert_qualifying(conn, 1, wpm=60.0, char_count=60, duration=12.0)
  assert format_avg_wpm_label(conn).startswith('Avg WPM:')
  total_chars = 40 + 80 + 60 * (WPM_GATE_MIN_LESSONS - 2)
  total_time = 12.0 * WPM_GATE_MIN_LESSONS
  expected = total_chars / total_time * 12.0
  assert aggregate_session_wpm_from_results(conn, 0) == pytest.approx(expected)
