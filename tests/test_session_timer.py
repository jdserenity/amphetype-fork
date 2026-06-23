"""Tests for focused session timer."""

import pytest

from amphetype.session_timer import FocusedSessionTimer, format_session_time


def test_format_session_time():
  assert format_session_time(0) == '0:00:00'
  assert format_session_time(65) == '0:01:05'
  assert format_session_time(3661) == '1:01:01'


def test_focused_session_timer_runs_only_while_resumed(monkeypatch):
  times = [0.0, 10.0, 10.0, 25.0, 40.0]
  monkeypatch.setattr('amphetype.session_timer.timer', lambda: times.pop(0) if times else 40.0)

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
