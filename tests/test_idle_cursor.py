"""Tests for idle mouse-cursor hide logic."""

from typing_program.idle_cursor import MOUSE_CURSOR_IDLE_MS, should_hide_mouse_cursor


def test_should_hide_after_threshold():
  assert not should_hide_mouse_cursor(0)
  assert not should_hide_mouse_cursor(MOUSE_CURSOR_IDLE_MS - 1)
  assert should_hide_mouse_cursor(MOUSE_CURSOR_IDLE_MS)
  assert should_hide_mouse_cursor(MOUSE_CURSOR_IDLE_MS + 500)


def test_custom_threshold():
  assert not should_hide_mouse_cursor(999, threshold_ms=1000)
  assert should_hide_mouse_cursor(1000, threshold_ms=1000)
