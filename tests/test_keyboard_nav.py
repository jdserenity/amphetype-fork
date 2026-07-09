"""Keyboard navigation helpers and shortcut wiring."""

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
from typing_program.keyboard_nav import (
  PRACTICE_MODE_ORDER, SUBMODE_HEATMAP, SUBMODE_IMPROVE, SUBMODE_READ_AHEAD,
  active_submode_keys, cycle_index, cycle_practice_mode, resolve_tab_submode_key,
)
from typing_program.read_ahead import READ_AHEAD_LEVEL_LABELS
from typing_program.speed_heatmap import MODE_LABELS


def test_practice_mode_order_matches_footer():
  assert PRACTICE_MODE_ORDER == (MODE_IMPROVE, MODE_CORPUS, MODE_BOOK)


def test_cycle_practice_mode_forward():
  assert cycle_practice_mode(MODE_IMPROVE, 1) == MODE_CORPUS
  assert cycle_practice_mode(MODE_CORPUS, 1) == MODE_BOOK
  assert cycle_practice_mode(MODE_BOOK, 1) == MODE_IMPROVE


def test_cycle_practice_mode_backward():
  assert cycle_practice_mode(MODE_IMPROVE, -1) == MODE_BOOK
  assert cycle_practice_mode(MODE_BOOK, -1) == MODE_CORPUS
  assert cycle_practice_mode(MODE_CORPUS, -1) == MODE_IMPROVE


def test_cycle_practice_mode_unknown_starts_at_improve():
  assert cycle_practice_mode('nope', 1) == MODE_CORPUS  # index treated as 0 → +1
  assert cycle_practice_mode('nope', 0) == MODE_IMPROVE


def test_cycle_index_wraps():
  assert cycle_index(0, 3, 1) == 1
  assert cycle_index(2, 3, 1) == 0
  assert cycle_index(0, 3, -1) == 2
  assert cycle_index(1, 3, -1) == 0


def test_cycle_index_empty_count():
  assert cycle_index(5, 0, 1) == 0
  assert cycle_index(5, -1, 1) == 0


def test_active_submode_keys_footer_order():
  assert active_submode_keys(MODE_IMPROVE, False, False) == [SUBMODE_IMPROVE]
  assert active_submode_keys(MODE_BOOK, True, False) == [SUBMODE_READ_AHEAD]
  assert active_submode_keys(MODE_CORPUS, False, True) == [SUBMODE_HEATMAP]
  assert active_submode_keys(MODE_IMPROVE, True, True) == [
    SUBMODE_IMPROVE, SUBMODE_READ_AHEAD, SUBMODE_HEATMAP]
  assert active_submode_keys(MODE_BOOK, False, False) == []


def test_resolve_tab_submode_key_sticky():
  keys = [SUBMODE_IMPROVE, SUBMODE_READ_AHEAD]
  assert resolve_tab_submode_key(SUBMODE_READ_AHEAD, keys) == SUBMODE_READ_AHEAD
  assert resolve_tab_submode_key(SUBMODE_HEATMAP, keys) == SUBMODE_IMPROVE
  assert resolve_tab_submode_key(SUBMODE_IMPROVE, []) is None


def test_typer_window_has_mode_and_submode_shortcuts(qapp):
  import typing_program.mainwindow  # noqa: F401 — init app.settings
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  assert hasattr(tw, '_cycle_practice_mode')
  assert tw._sc_mode_next is not None
  assert tw._sc_mode_prev is not None
  # Tab is handled on the typer widget (not a QShortcut). Bound methods are new objects each access.
  assert tw._typer._on_tab_nav is not None
  assert tw._typer._on_tab_nav.__func__ is tw.cycle_active_submode.__func__
  assert tw._typer._on_tab_nav.__self__ is tw


def test_tab_key_cycles_improve_submode(qapp):
  import typing_program.mainwindow  # noqa: F401
  from PyQt5.QtCore import Qt
  from PyQt5.QtGui import QKeyEvent, QFont
  from typing_program.typer import TyperWindow, LessonDocument

  tw = TyperWindow()
  assert tw._mode == MODE_IMPROVE
  doc = LessonDocument(QFont('Arial', 12))
  doc.set_text('hello')
  tw._typer.setLesson(doc)
  tw._doc = doc

  evt = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier)
  tw._typer.keyPressEvent(evt)
  # With empty DB, oblivion may be skipped but normal→trigrams always works.
  assert tw._improve_submode == 1  # trigrams after normal


def test_tab_cycles_read_ahead_level_when_focused(qapp):
  import typing_program.mainwindow  # noqa: F401
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  tw.set_practice_mode(MODE_BOOK)
  tw._settings.set('read_ahead_enabled', True)
  tw._set_read_ahead_ui(True, 0, refresh_doc=True)
  tw._focus_tab_submode(SUBMODE_READ_AHEAD)
  assert tw._read_ahead_level == 0
  tw.cycle_active_submode()
  assert tw._read_ahead_level == 1
  assert READ_AHEAD_LEVEL_LABELS[tw._read_ahead_level] == 'hard'
  tw.cycle_active_submode()
  assert tw._read_ahead_level == 2  # easy


def test_tab_cycles_heatmap_mode_when_focused(qapp):
  import typing_program.mainwindow  # noqa: F401
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  tw.set_practice_mode(MODE_CORPUS)
  tw.S('speed_heatmap').set(True)
  tw._focus_tab_submode(SUBMODE_HEATMAP)
  start = int(tw.S('speed_heatmap_mode').get())
  tw.cycle_active_submode()
  assert int(tw.S('speed_heatmap_mode').get()) == (start + 1) % len(MODE_LABELS)


def test_enabling_read_ahead_focuses_its_submode_for_tab(qapp):
  import typing_program.mainwindow  # noqa: F401
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  assert tw._tab_submode_key == SUBMODE_IMPROVE
  # Start with read-ahead off, then toggle on (focus should stick to read-ahead).
  if tw._read_ahead_on:
    tw.toggle_read_ahead()
  tw.toggle_read_ahead()
  assert tw._read_ahead_on
  assert tw._tab_submode_key == SUBMODE_READ_AHEAD
  level0 = tw._read_ahead_level
  tw.cycle_active_submode()
  assert tw._read_ahead_level == (level0 + 1) % len(READ_AHEAD_LEVEL_LABELS)


def test_cycle_practice_mode_on_typer_window(qapp):
  import typing_program.mainwindow  # noqa: F401
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  # Cold start is improve
  assert tw._mode == MODE_IMPROVE
  tw._cycle_practice_mode(1)
  assert tw._mode == MODE_CORPUS
  tw._cycle_practice_mode(1)
  assert tw._mode == MODE_BOOK
  tw._cycle_practice_mode(-1)
  assert tw._mode == MODE_CORPUS


def test_main_window_has_tab_cycle_shortcuts(qapp):
  import typing_program.mainwindow as A

  w = A.MainWindow()
  assert w._tabs.count() >= 3
  assert w._sc_tab_next is not None
  assert w._sc_tab_prev is not None
  start = w._tabs.currentIndex()
  w._cycle_main_tab(1)
  assert w._tabs.currentIndex() == (start + 1) % w._tabs.count()
  w._cycle_main_tab(-1)
  assert w._tabs.currentIndex() == start
