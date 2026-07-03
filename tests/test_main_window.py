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
