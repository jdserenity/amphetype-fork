"""Main window layout — tab min sizes must not block resizing the Typer view."""


def test_main_window_minimum_size_stays_resizable(qapp):
  import typing_program.mainwindow as A

  w = A.MainWindow()
  msh = w.minimumSizeHint()
  # Before scroll areas on Preferences, min height was ~950px and width ~1280px.
  assert msh.width() < 900, msh.width()
  assert msh.height() < 700, msh.height()


def test_main_window_default_size_hint(qapp):
  import typing_program.mainwindow as A

  hint = A.MainWindow().sizeHint()
  assert hint.width() == 1100
  assert hint.height() == 712


def test_main_tabs_inset_from_window_edge(qapp):
  """Tab buttons should sit below the top window edge, not flush against it."""
  import typing_program.mainwindow as A

  w = A.MainWindow()
  w.resize(w.sizeHint())
  w.show()
  qapp.processEvents()
  shell = w.centralWidget()
  assert w._tabs.pos().y() >= A.MAIN_TAB_TOP_INSET
  bar = w._tabs.tabBar()
  tab_top = bar.mapTo(shell, bar.tabRect(0).topLeft()).y()
  assert tab_top >= A.MAIN_TAB_TOP_INSET


def test_session_clock_vertically_aligned_with_tabs(qapp):
  import typing_program.mainwindow as A

  w = A.MainWindow()
  w.resize(w.sizeHint())
  w.show()
  qapp.processEvents()
  w._reposition_session_clock()
  qapp.processEvents()
  shell = w.centralWidget()
  bar = w._tabs.tabBar()
  tab_r = bar.tabRect(0)
  tab_top = bar.mapTo(shell, tab_r.topLeft()).y()
  clock = w._session_clock
  tab_mid = tab_top + tab_r.height() / 2.0
  clock_mid = clock.y() + clock.height() / 2.0
  assert abs(tab_mid - clock_mid) <= 3


def test_should_clear_focus_on_click(qapp):
  from PyQt5.QtWidgets import QComboBox, QLabel, QWidget
  from typing_program.QtUtil import should_clear_focus_on_click

  parent = QWidget()
  combo = QComboBox(parent)
  combo.addItem('words')
  label = QLabel('elsewhere', parent)
  assert not should_clear_focus_on_click(combo, combo)
  assert should_clear_focus_on_click(combo, label)
  assert not should_clear_focus_on_click(None, label)
