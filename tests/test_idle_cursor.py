"""Tests for idle mouse-cursor hide logic."""

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QMouseEvent

from typing_program.idle_cursor import (
  MOUSE_CURSOR_IDLE_MS, should_apply_idle_blank, should_hide_mouse_cursor,
)


def test_should_hide_after_threshold():
  assert not should_hide_mouse_cursor(0)
  assert not should_hide_mouse_cursor(MOUSE_CURSOR_IDLE_MS - 1)
  assert should_hide_mouse_cursor(MOUSE_CURSOR_IDLE_MS)
  assert should_hide_mouse_cursor(MOUSE_CURSOR_IDLE_MS + 500)


def test_custom_threshold():
  assert not should_hide_mouse_cursor(999, threshold_ms=1000)
  assert should_hide_mouse_cursor(1000, threshold_ms=1000)


def test_should_not_blank_when_pointer_left_canvas():
  assert not should_apply_idle_blank(False)
  assert not should_apply_idle_blank(False, idle_ms=MOUSE_CURSOR_IDLE_MS)
  assert should_apply_idle_blank(True)
  assert should_apply_idle_blank(True, idle_ms=MOUSE_CURSOR_IDLE_MS)
  assert not should_apply_idle_blank(True, idle_ms=MOUSE_CURSOR_IDLE_MS - 1)


def test_footer_mode_buttons_use_pointing_hand(qapp):
  """Hand cursor comes from setCursor — not stylesheet `cursor:` (Qt warns on that)."""
  import typing_program.mainwindow  # noqa: F401
  from PyQt5.QtCore import Qt
  from typing_program.typer import TyperWindow, _footer_btn_style

  tw = TyperWindow()
  assert 'cursor:' not in tw._mode_btn_style
  assert 'cursor:' not in _footer_btn_style(False)
  assert tw._btn_improve.cursor().shape() == Qt.PointingHandCursor
  assert tw._btn_corpus.cursor().shape() == Qt.PointingHandCursor
  assert tw._btn_book.cursor().shape() == Qt.PointingHandCursor
  # Follow is greyed in improve (cold start) — arrow until corpus/book.
  assert tw._btn_follow.cursor().shape() == Qt.ArrowCursor


def test_viewport_mouse_move_restores_cursor(qapp):
  """QTextEdit mouse moves hit the viewport — filter must un-blank on move."""
  from tests.test_typer_document import _FakeTyperSettings
  from typing_program.typer import TyperWidget

  w = TyperWidget(_FakeTyperSettings())
  w.resize(400, 200)
  w.show()
  qapp.processEvents()
  # Simulate an already-blanked canvas (underMouse is false in headless tests).
  w.setCursor(Qt.BlankCursor)
  w.viewport().setCursor(Qt.BlankCursor)
  assert w.viewport().cursor().shape() == Qt.BlankCursor

  move = QMouseEvent(
    QEvent.MouseMove, QPoint(10, 10), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
  w.eventFilter(w.viewport(), move)
  assert w.viewport().cursor().shape() != Qt.BlankCursor


def test_hide_skipped_when_pointer_not_over_canvas(qapp):
  from tests.test_typer_document import _FakeTyperSettings
  from typing_program.typer import TyperWidget

  w = TyperWidget(_FakeTyperSettings())
  w.show()
  qapp.processEvents()
  # Headless: pointer is not over the widget, so idle hide must no-op.
  w._hide_idle_mouse_cursor()
  assert w.viewport().cursor().shape() != Qt.BlankCursor
