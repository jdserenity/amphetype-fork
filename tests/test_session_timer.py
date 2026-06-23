"""Tests for focused session timer."""

import pytest

from amphetype.session_timer import FocusedSessionTimer, format_session_label


def test_format_session_label():
  assert format_session_label(0) == '0 second session'
  assert format_session_label(1) == '1 second session'
  assert format_session_label(45) == '45 second session'
  assert format_session_label(60) == '1 minute session'
  assert format_session_label(900) == '15 minute session'
  assert format_session_label(3661) == '1 hour session'
  assert format_session_label(7200) == '2 hour session'


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
