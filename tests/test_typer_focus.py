"""Tests for keeping typer keyboard focus (except follow WPM)."""

from typing_program.typer_focus import (
  focus_is_follow_wpm, focus_is_typer, should_refocus_typer,
)


class _W:
  def __init__(self, parent=None):
    self._parent = parent
    self._kids = []
    if parent is not None:
      parent._kids.append(self)

  def isAncestorOf(self, child):
    w = child
    while w is not None:
      if w is self:
        return True
      w = getattr(w, '_parent', None)
    return False


def test_follow_wpm_is_allowed_focus():
  root = _W()
  edit = _W(root)
  typer = _W(root)
  assert focus_is_follow_wpm(edit, edit)
  assert not focus_is_follow_wpm(typer, edit)
  assert not should_refocus_typer(
    edit, True, True, typer, edit)


def test_typer_keeps_own_focus():
  root = _W()
  edit = _W(root)
  typer = _W(root)
  viewport = _W(typer)
  assert focus_is_typer(typer, typer)
  assert focus_is_typer(viewport, typer)
  assert not should_refocus_typer(typer, True, True, typer, edit)
  assert not should_refocus_typer(viewport, True, True, typer, edit)


def test_footer_chrome_triggers_refocus():
  root = _W()
  edit = _W(root)
  typer = _W(root)
  btn = _W(root)
  assert should_refocus_typer(btn, True, True, typer, edit)


def test_cleared_focus_on_visible_typer_refocuses():
  root = _W()
  edit = _W(root)
  typer = _W(root)
  assert should_refocus_typer(None, True, False, typer, edit)


def test_other_tab_keeps_focus():
  root = _W()
  edit = _W(root)
  typer = _W(root)
  other = _W()
  assert not should_refocus_typer(other, True, False, typer, edit)


def test_hidden_typer_does_not_steal():
  root = _W()
  edit = _W(root)
  typer = _W(root)
  btn = _W(root)
  assert not should_refocus_typer(btn, False, True, typer, edit)


def test_typer_window_refocuses_after_footer_click(qapp):
  import typing_program.mainwindow  # noqa: F401
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  tw.show()
  qapp.processEvents()
  tw._typer.setFocus()
  qapp.processEvents()
  # Simulate focus landing on a footer button (should not stick).
  tw._on_app_focus_changed(tw._typer, tw._btn_improve)
  qapp.processEvents()
  assert tw._typer.hasFocus() or tw._typer.viewport().hasFocus()
  tw.close()
  tw.deleteLater()
  qapp.processEvents()


def test_follow_wpm_may_keep_focus(qapp):
  import typing_program.mainwindow  # noqa: F401
  from typing_program.book_mode import MODE_CORPUS
  from typing_program.typer import TyperWindow
  from typing_program.typer_focus import should_refocus_typer

  tw = TyperWindow()
  tw.set_practice_mode(MODE_CORPUS)
  tw.S('follow_mode').set(True)
  tw.show()
  qapp.processEvents()
  edit = tw._follow_wpm_edit
  tw._on_app_focus_changed(tw._typer, edit)
  qapp.processEvents()
  # Must not yank focus away from the WPM box.
  assert not should_refocus_typer(edit, True, True, tw._typer, edit)
  tw.close()
  tw.deleteLater()
  qapp.processEvents()
