"""Keyboard navigation helpers and shortcut wiring."""

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
from typing_program.keyboard_nav import (
  PRACTICE_MODE_ORDER, cycle_index, cycle_practice_mode, selectable_practice_modes,
)


def test_practice_mode_order_matches_footer():
  assert PRACTICE_MODE_ORDER == (MODE_IMPROVE, MODE_CORPUS, MODE_BOOK)


def test_cycle_practice_mode_forward():
  order = selectable_practice_modes()
  for i, mode in enumerate(order):
    assert cycle_practice_mode(mode, 1) == order[(i + 1) % len(order)]


def test_cycle_practice_mode_backward():
  order = selectable_practice_modes()
  for i, mode in enumerate(order):
    assert cycle_practice_mode(mode, -1) == order[(i - 1) % len(order)]


def test_cycle_practice_mode_unknown_starts_at_improve():
  order = selectable_practice_modes()
  assert cycle_practice_mode('nope', 1) == order[1]  # index treated as 0 → +1
  assert cycle_practice_mode('nope', 0) == order[0]


def test_cycle_index_wraps():
  assert cycle_index(0, 3, 1) == 1
  assert cycle_index(2, 3, 1) == 0
  assert cycle_index(0, 3, -1) == 2
  assert cycle_index(1, 3, -1) == 0


def test_cycle_index_empty_count():
  assert cycle_index(5, 0, 1) == 0
  assert cycle_index(5, -1, 1) == 0


def test_typer_window_has_mode_and_submode_shortcuts(qapp):
  import typing_program.mainwindow  # noqa: F401 — init app.settings
  from PyQt5.QtGui import QKeySequence
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  assert hasattr(tw, '_cycle_practice_mode')
  assert tw._sc_mode_next is not None
  assert tw._sc_mode_prev is not None
  # Cmd/Ctrl+Opt/Alt+arrows (Ctrl = Cmd on macOS in QKeySequence).
  assert tw._sc_mode_next.key() == QKeySequence('Ctrl+Alt+Right')
  assert tw._sc_mode_prev.key() == QKeySequence('Ctrl+Alt+Left')
  # Tab is handled on the typer widget (not a QShortcut). Bound methods are new objects each access.
  assert tw._typer._on_tab_nav is not None
  assert tw._typer._on_tab_nav.__func__ is tw.cycle_improve_submode.__func__
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


def test_cycle_practice_mode_on_typer_window(qapp):
  import typing_program.mainwindow  # noqa: F401
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  order = selectable_practice_modes()
  # Cold start is improve
  assert tw._mode == order[0]
  tw._cycle_practice_mode(1)
  assert tw._mode == order[1]
  tw._cycle_practice_mode(1)
  assert tw._mode == order[2 % len(order)]
  tw._cycle_practice_mode(-1)
  assert tw._mode == order[1]


def test_main_window_has_tab_cycle_shortcuts(qapp):
  import typing_program.mainwindow as A
  from PyQt5.QtGui import QKeySequence

  w = A.MainWindow()
  assert w._tabs.count() >= 3
  assert w._sc_tab_next is not None
  assert w._sc_tab_prev is not None
  # Cmd/Ctrl+Shift+[ ] (Ctrl = Cmd on macOS in QKeySequence).
  assert w._sc_tab_prev.key() == QKeySequence('Ctrl+Shift+[')
  assert w._sc_tab_next.key() == QKeySequence('Ctrl+Shift+]')
  w._tabs.setCurrentIndex(0)
  w._cycle_main_tab(1)
  assert w._tabs.currentIndex() == 1
  w._cycle_main_tab(-1)
  assert w._tabs.currentIndex() == 0


def test_tab_cycle_on_preferences_cycles_pref_subtabs(qapp):
  import typing_program.mainwindow as A

  w = A.MainWindow()
  # PA → enter Preferences at General, then through sub-tabs, then out to Typer.
  w._tabs.setCurrentIndex(w._perf_tab_idx)
  w._cycle_main_tab(1)
  assert w._tabs.currentIndex() == w._prefs_tab_idx
  assert w._prefs.currentIndex() == 0
  w._cycle_main_tab(1)
  assert w._prefs.currentIndex() == 1
  w._cycle_main_tab(1)
  assert w._prefs.currentIndex() == 2
  w._cycle_main_tab(1)
  assert w._tabs.currentIndex() == 0
  # From Typer left → Sources; from General left → Performance Analysis.
  w._cycle_main_tab(-1)
  assert w._tabs.currentIndex() == w._prefs_tab_idx
  assert w._prefs.currentIndex() == 2
  w._prefs.setCurrentIndex(0)
  w._cycle_main_tab(-1)
  assert w._tabs.currentIndex() == w._perf_tab_idx


def test_cycle_toolbar_tabs_flattens_prefs():
  from typing_program.keyboard_nav import cycle_toolbar_tabs, toolbar_cycle_pos

  # main: 0 Typer, 1 PA, 2 Preferences; 3 prefs sub-tabs
  assert toolbar_cycle_pos(0, 2, 0, 3) == 0
  assert toolbar_cycle_pos(1, 2, 0, 3) == 1
  assert toolbar_cycle_pos(2, 2, 0, 3) == 2
  assert toolbar_cycle_pos(2, 2, 2, 3) == 4
  assert cycle_toolbar_tabs(1, 2, 0, 3, 1) == (2, 0)
  assert cycle_toolbar_tabs(2, 2, 0, 3, 1) == (2, 1)
  assert cycle_toolbar_tabs(2, 2, 2, 3, 1) == (0, 2)  # out; keep last sub for click-restore
  assert cycle_toolbar_tabs(0, 2, 2, 3, -1) == (2, 2)
  assert cycle_toolbar_tabs(2, 2, 0, 3, -1) == (1, 0)
