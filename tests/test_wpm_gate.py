"""Tests for progress gate and perfect-rate / legacy WPM helpers."""

import sqlite3
import time

import pytest

from typing_program.app_meta import PERFECT_RATE_BASELINE_KEY, get_app_meta_float
from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
from typing_program.stats_query import (
  STAT_TYPE_WORD,
  WPM_GATE_MIN_LESSONS,
  count_wpm_gate_lessons,
  ensure_perfect_rate_baseline,
  first_qualifying_session_wpm,
  format_perfect_rate_gain,
  format_perfect_rate_label,
  format_progress_gate_label,
  lesson_qualifies_for_wpm_gate,
  overall_word_perfect_rate,
  perfect_rate_since_start_gain,
  session_wpm_since_start_gain,
  wpm_gate_complete,
)


def _gate_db():
  from typing_program.Data import AppDatabase
  conn = sqlite3.connect(':memory:', 5, 0, 'DEFERRED', False, AppDatabase)
  conn.execute("insert into source (name, discount) values ('Novel', null)")
  novel = conn.execute("select rowid from source where name='Novel'").fetchone()[0]
  conn.execute("insert into source (name, discount) values ('<Weakspot>', 1)")
  weak = conn.execute("select rowid from source where name='<Weakspot>'").fetchone()[0]
  conn.execute("insert into source (name, discount) values ('<Reviews>', 1)")
  reviews = conn.execute("select rowid from source where name='<Reviews>'").fetchone()[0]
  conn._gate_ids = (novel, weak, reviews)
  return conn


def _insert_qualifying(conn, source_id, wpm=60.0, char_count=60, duration=12.0):
  conn.execute(
    'insert into result (w, text_id, source, wpm, accuracy, viscosity, char_count, duration) values (?,?,?,?,?,?,?,?)',
    (time.time(), 't', source_id, wpm, 1.0, 1.0, char_count, duration))


def _insert_word(conn, data, count, mistakes, wpm=60.0):
  conn.execute(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    (time.time(), data, STAT_TYPE_WORD, 12.0 / wpm, count, mistakes, 1.0, None))


def test_format_perfect_rate_gain_one_decimal():
  assert format_perfect_rate_gain(None) == '—'
  assert format_perfect_rate_gain(0.0) == '+0.0%'
  assert format_perfect_rate_gain(6.0) == '+6.0%'
  assert format_perfect_rate_gain(12.5) == '+12.5%'
  assert format_perfect_rate_gain(-1.5) == '-1.5%'


def test_lesson_qualifies_for_wpm_gate():
  assert lesson_qualifies_for_wpm_gate(MODE_CORPUS)
  assert lesson_qualifies_for_wpm_gate(MODE_BOOK)
  assert lesson_qualifies_for_wpm_gate(MODE_IMPROVE, improve_submode=0)
  assert not lesson_qualifies_for_wpm_gate(MODE_IMPROVE, improve_submode=1)
  assert not lesson_qualifies_for_wpm_gate(MODE_CORPUS, focus_drill=True)


def test_count_wpm_gate_lessons_includes_corpus_book_and_weakspot():
  conn = _gate_db()
  novel, weak, reviews = conn._gate_ids
  _insert_qualifying(conn, novel)
  _insert_qualifying(conn, weak)
  conn.execute(
    'insert into result (w, text_id, source, wpm, accuracy, viscosity, char_count, duration) values (?,?,?,?,?,?,?,?)',
    (time.time(), 'r', reviews, 50.0, 1.0, 1.0, 50, 10.0))
  assert count_wpm_gate_lessons(conn) == 2


def test_format_perfect_rate_label_hides_until_ten():
  conn = _gate_db()
  novel = conn._gate_ids[0]
  assert format_progress_gate_label(conn) == 'Complete 10 lessons to calculate perfect rate'
  assert format_perfect_rate_label(conn) == 'Complete 10 lessons to calculate perfect rate'
  for _ in range(3):
    _insert_qualifying(conn, novel)
  assert format_perfect_rate_label(conn) == 'Complete 7 more lessons to calculate perfect rate'


def test_format_perfect_rate_label_after_gate():
  conn = _gate_db()
  novel = conn._gate_ids[0]
  for _ in range(WPM_GATE_MIN_LESSONS):
    _insert_qualifying(conn, novel)
  assert wpm_gate_complete(conn)
  assert format_perfect_rate_label(conn) == 'Perfect rate: —'
  _insert_word(conn, 'hi', 8, 2)  # 6/8 = 75%
  _insert_word(conn, 'yo', 2, 0)  # 2/2 = 100%; overall 8/10 = 80%
  assert format_perfect_rate_label(conn) == 'Perfect rate: 80.0%'


def test_overall_word_perfect_rate_sample_weighted():
  conn = _gate_db()
  _insert_word(conn, 'a', 8, 2)  # 6 perfect
  _insert_word(conn, 'b', 2, 0)  # 2 perfect
  assert overall_word_perfect_rate(conn) == pytest.approx(80.0)
  _insert_word(conn, 'once', 1, 0)  # below floor — ignored
  assert overall_word_perfect_rate(conn) == pytest.approx(80.0)


def test_perfect_rate_since_start_gain_hidden_until_gate():
  conn = _gate_db()
  novel = conn._gate_ids[0]
  _insert_qualifying(conn, novel)
  _insert_word(conn, 'hi', 4, 1)
  assert perfect_rate_since_start_gain(conn) is None


def test_perfect_rate_since_start_snapshots_baseline():
  conn = _gate_db()
  novel = conn._gate_ids[0]
  for _ in range(WPM_GATE_MIN_LESSONS):
    _insert_qualifying(conn, novel)
  _insert_word(conn, 'hi', 8, 2)  # 75%
  gain0 = perfect_rate_since_start_gain(conn)
  assert gain0 == pytest.approx(0.0)
  assert get_app_meta_float(conn, PERFECT_RATE_BASELINE_KEY) == pytest.approx(75.0)
  _insert_word(conn, 'hi', 8, 0)  # now 14/16 = 87.5%
  gain = perfect_rate_since_start_gain(conn)
  assert gain == pytest.approx(12.5)
  assert get_app_meta_float(conn, PERFECT_RATE_BASELINE_KEY) == pytest.approx(75.0)


def test_ensure_perfect_rate_baseline_idempotent():
  conn = _gate_db()
  novel = conn._gate_ids[0]
  for _ in range(WPM_GATE_MIN_LESSONS):
    _insert_qualifying(conn, novel)
  _insert_word(conn, 'x', 4, 1)
  a = ensure_perfect_rate_baseline(conn)
  b = ensure_perfect_rate_baseline(conn)
  assert a == b == pytest.approx(75.0)


def test_session_wpm_since_start_gain_hidden_until_gate():
  conn = _gate_db()
  novel = conn._gate_ids[0]
  _insert_qualifying(conn, novel, wpm=40.0, char_count=40, duration=12.0)
  assert session_wpm_since_start_gain(conn) is None


def test_session_wpm_since_start_gain_after_gate():
  conn = _gate_db()
  novel = conn._gate_ids[0]
  _insert_qualifying(conn, novel, wpm=40.0, char_count=40, duration=12.0)
  for _ in range(WPM_GATE_MIN_LESSONS - 1):
    _insert_qualifying(conn, novel, wpm=80.0, char_count=80, duration=12.0)
  assert first_qualifying_session_wpm(conn) == pytest.approx(40.0)
  gain = session_wpm_since_start_gain(conn)
  assert gain is not None
  assert gain > 0
