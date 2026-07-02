"""Main window layout — tab min sizes must not block resizing the Typer view."""


def test_main_window_minimum_size_stays_resizable(qapp):
  import amphetype.Amphetype as A

  w = A.AmphetypeWindow()
  msh = w.minimumSizeHint()
  # Before scroll areas on Preferences, min height was ~950px and width ~1280px.
  assert msh.width() < 900, msh.width()
  assert msh.height() < 700, msh.height()


def test_main_window_default_size_hint(qapp):
  import amphetype.Amphetype as A

  hint = A.AmphetypeWindow().sizeHint()
  assert hint.width() == 1100
  assert hint.height() == 712
