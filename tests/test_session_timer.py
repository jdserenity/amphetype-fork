"""Tests for focused session timer."""

import pytest

from typing_program.session_timer import FocusedSessionTimer, format_session_label


def test_format_session_label():
  assert format_session_label(0) == '0:00:00 session'
  assert format_session_label(65) == '0:01:05 session'
  assert format_session_label(900) == '0:15:00 session'
  assert format_session_label(3661) == '1:01:01 session'


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
