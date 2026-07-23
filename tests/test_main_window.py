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


def test_main_tabs_flush_with_window_top(qapp):
  """Tab strip is the central widget — no spacer gap under the title bar."""
  import typing_program.mainwindow as A

  w = A.MainWindow()
  assert w.centralWidget() is w._tabs


def test_session_clock_vertically_aligned_with_tabs(qapp):
  import typing_program.mainwindow as A

  w = A.MainWindow()
  w.resize(w.sizeHint())
  w.show()
  qapp.processEvents()
  w._reposition_session_clock()
  qapp.processEvents()
  bar = w._tabs.tabBar()
  tab_r = bar.tabRect(0)
  clock = w._session_clock
  tab_mid = tab_r.y() + tab_r.height() / 2.0
  clock_mid = clock.y() + clock.height() / 2.0
  assert abs(tab_mid - clock_mid) <= 3


def test_main_tabs_suppress_pane_border(qapp):
  """Main tab strip must not draw the full-width line through tabs/session clock."""
  import typing_program.mainwindow as A
  from PyQt5.QtWidgets import QStackedWidget

  w = A.MainWindow()
  assert w._tabs.objectName() == 'mainTabs'
  assert w._tabs.documentMode() is True
  sheet = w._tabs.styleSheet().replace(' ', '')
  assert 'QTabWidget#mainTabs::pane{border:none;background:transparent;}' in sheet
  # Preferences is a page stack only — no nested tab bar.
  prefs = w._tabs.widget(2)
  assert isinstance(prefs, QStackedWidget)


def test_prefs_subtabs_on_top_toolbar_only_when_preferences_active(qapp):
  import typing_program.mainwindow as A

  w = A.MainWindow()
  w.resize(w.sizeHint())
  w.show()
  qapp.processEvents()

  bar = w._prefs_bar
  assert [bar.tabText(i) for i in range(bar.count())] == [
    'General Options', 'Typer Options', 'Sources']

  w._tabs.setCurrentIndex(0)  # Typer
  qapp.processEvents()
  assert not bar.isVisible()

  w._tabs.setCurrentIndex(w._prefs_tab_idx)
  qapp.processEvents()
  assert bar.isVisible()

  bar.setCurrentIndex(2)
  qapp.processEvents()
  assert w._prefs.currentIndex() == 2


def test_prefs_bar_sits_flush_against_preferences_tab(qapp):
  import typing_program.mainwindow as A

  w = A.MainWindow()
  w.resize(w.sizeHint())
  w.show()
  w._tabs.setCurrentIndex(w._prefs_tab_idx)
  qapp.processEvents()
  w._reposition_prefs_bar()
  qapp.processEvents()
  prefs_r = w._tabs.tabBar().tabRect(w._prefs_tab_idx)
  assert w._prefs_bar.x() == prefs_r.right()


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
