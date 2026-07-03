"""Tests for focused session timer."""

import pytest

from typing_program.Data import AppDatabase
from typing_program.app_meta import TOTAL_PRACTICE_SECONDS_KEY, ensure_app_meta, get_app_meta_int
from typing_program.session_timer import (
  SESSION_IDLE_TIMEOUT,
  FocusedSessionTimer,
  format_practice_total_label,
  format_session_label,
  total_practice_seconds_from_db,
)


def _meta_db():
  db = AppDatabase(':memory:', 5, 0, 'DEFERRED', False, AppDatabase)
  ensure_app_meta(db)
  return db


def test_format_session_label():
  assert format_session_label(0) == '0:00:00 session'
  assert format_session_label(65) == '0:01:05 session'
  assert format_session_label(900) == '0:15:00 session'
  assert format_session_label(3661) == '1:01:01 session'


def test_format_practice_total_label():
  assert format_practice_total_label(3661) == '1:01:01'


def test_focused_session_timer_runs_only_while_resumed(monkeypatch):
  times = [0.0, 10.0, 10.0, 25.0, 40.0]
  monkeypatch.setattr('typing_program.session_timer.timer', lambda: times.pop(0) if times else 40.0)

  t = FocusedSessionTimer()
  t.resume()
  t.pause()
  assert t.elapsed() == pytest.approx(10.0)

  t.resume()
  t.pause()
  assert t.elapsed() == pytest.approx(25.0)


def test_focused_session_timer_idle_until_resume():
  t = FocusedSessionTimer()
  assert t.elapsed() == 0.0


def test_total_seconds_includes_saved_and_segment(monkeypatch):
  monkeypatch.setattr('typing_program.session_timer.timer', lambda: 10.0)
  t = FocusedSessionTimer()
  t.set_saved(100.0)
  t.resume()
  assert t.total_seconds() == pytest.approx(100.0)


def test_idle_pauses_after_sixty_seconds_without_interaction(monkeypatch):
  times = [0.0, 30.0, 30.0, 90.0, 90.0]
  monkeypatch.setattr('typing_program.session_timer.timer', lambda: times.pop(0) if times else 90.0)
  t = FocusedSessionTimer()
  t.resume()
  t.check_idle()
  assert t.elapsed() == pytest.approx(30.0)
  t.check_idle()
  assert t.elapsed() == pytest.approx(90.0)


def test_touch_resumes_after_idle_while_window_still_wants_run(monkeypatch):
  times = [0.0, 90.0, 100.0]
  monkeypatch.setattr('typing_program.session_timer.timer', lambda: times.pop(0) if times else 100.0)
  t = FocusedSessionTimer()
  t.resume()
  t.check_idle()
  assert t._running_since is None
  t.touch()
  assert t._running_since is not None


def test_flush_to_db_persists_total(monkeypatch):
  times = [0.0, 15.0, 15.0]
  monkeypatch.setattr('typing_program.session_timer.timer', lambda: times.pop(0) if times else 15.0)
  db = _meta_db()
  t = FocusedSessionTimer()
  t.set_saved(30)
  t.resume()
  t.flush_to_db(db)
  assert get_app_meta_int(db, TOTAL_PRACTICE_SECONDS_KEY, 0) == 45
  assert t.total_seconds() == pytest.approx(45.0)


def test_total_practice_seconds_from_db():
  db = _meta_db()
  db.execute(
    "insert into app_meta (key, value) values (?,?)",
    (TOTAL_PRACTICE_SECONDS_KEY, '120'))
  db.commit()
  assert total_practice_seconds_from_db(db) == 120


def test_session_idle_timeout_is_one_minute():
  assert SESSION_IDLE_TIMEOUT == 60.0
