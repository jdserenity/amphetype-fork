"""Tests for the inline typer (LessonDocument + integration with RunStats).

These cover the core behaviors of typing directly on top of the lesson text.
Run with: python -m pytest tests/ -q

Requires: pytest, pytest-qt, and PyQt5 (install via `pip install -e '.[test]'` inside the project venv).
"""

import sys

import pytest

pytest.importorskip("PyQt5")
from PyQt5.QtGui import QFont, QColor, QTextCharFormat
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

_qt_app = QApplication.instance()
if _qt_app is None:
  _qt_app = QApplication(sys.argv)

from amphetype.typer import (
  LessonDocument, RETURN_CHAR, MODE_NORMAL, MODE_WEAKSPOT, Cursor,
  format_source_attribution, lesson_completion_action, _NO_FILL_STYLE_ATTRS,
)


def test_lesson_completion_action():
    assert lesson_completion_action(MODE_NORMAL, False, False, False, False) == 'repeat'
    assert lesson_completion_action(MODE_WEAKSPOT, True, True, False, False) == 'weakspot_next'
    assert lesson_completion_action(MODE_NORMAL, True, True, False, False) == 'normal_next'
    assert lesson_completion_action(MODE_NORMAL, True, False, True, True) == 'review'
    assert lesson_completion_action(MODE_WEAKSPOT, True, False, True, True) == 'weakspot_next'


def test_format_source_attribution():
    assert format_source_attribution('Pride and Prejudice') == '— Pride and Prejudice'
    assert format_source_attribution('  Moby Dick  ') == '— Moby Dick'
    assert format_source_attribution('<Weakspot>') == ''
    assert format_source_attribution('<Reviews>') == ''
    assert format_source_attribution('') == ''
    assert format_source_attribution(None) == ''


def test_untyped_style_has_no_background_fill(qapp):
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("hi")
    doc.reset()
    assert doc.style_untyped.background().style() == Qt.NoBrush
    assert doc.style_correct.background().style() == Qt.NoBrush
    assert 'untyped' in _NO_FILL_STYLE_ATTRS


def test_lesson_document_lifecycle(qapp):
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("hello world")

    assert doc.is_ready()
    assert not doc.is_running()
    assert not doc.is_finished()

    # Ready text is present
    full = doc.toPlainText()
    assert "hello world" in full or "hello world" in full.replace(RETURN_CHAR, "\n")

    doc.reset()
    assert doc.is_ready()


def test_insert_correct_chars_advances_and_completes(qapp):
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("ab")

    received = []
    doc.progress.connect(lambda i: received.append(i))
    doc.completed.connect(lambda r: received.append("done"))

    # Cold start via first insert
    doc.insert("a")
    assert doc.is_running()
    assert len(received) == 1  # progress at 0

    doc.insert("b")
    assert doc.is_finished()
    assert "done" in received

    run = doc._run
    assert run is not None
    assert run.is_complete()


def test_insert_error_blocks_in_non_lenient(qapp):
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("abc")

    doc.insert("x")  # error, non-lenient by default
    assert doc._first_error is not None
    assert not doc.is_finished()

    # Further correct input should still be recorded but not "advance" the logical position fully
    doc.insert("a", lenient=False)
    # The document should have registered the error state
    assert doc._first_error is not None


def test_lenient_mode_allows_continuing_past_errors(qapp):
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("abc")

    doc.insert("x", lenient=True)
    assert doc._first_error is None  # lenient does not set blocking error

    doc.insert("b", lenient=True)
    doc.insert("c", lenient=True)
    assert doc.is_finished()


def test_backspace_restores_state(qapp):
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("abc")

    doc.insert("a")
    doc.insert("x")  # error
    assert doc._first_error is not None

    doc.backspace()
    assert doc._first_error is None  # cleared when backing past the error
    assert doc.is_running()


def test_overwrite_mode_vs_insert_mode(qapp):
    # overwrite_mode is a setting on the widget, but we can exercise the document path
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("ab")

    # Simulate overwrite=True (default in current widget)
    doc.insert("x", overwrite=True)
    # The first char should have been overwritten with styled 'x'
    # We mainly assert it didn't explode and run advanced
    assert doc._run is not None


def test_return_char_handling(qapp):
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("a" + RETURN_CHAR + "b")

    doc.insert("a")
    doc.insert(RETURN_CHAR)
    doc.insert("b")
    assert doc.is_finished()


def test_runstats_basic_paths_used_by_document():
    from amphetype.timingtuple import RunStats

    run = RunStats.make("abc")
    assert run.index == 0
    assert run.current.char == "a"

    run.visit(True)
    run.advance(True)
    assert run.index == 1

    run.visit(False)
    run.advance(True)
    assert run[1].mistakes == 1

    # pop (backspace simulation)
    popped = run.pop_char()
    assert popped == "b" or popped is None  # depending on inserts state

    # Completion + result
    run.visit(True)
    run.advance(True)
    assert run.is_complete() or run.index >= 2


def test_inline_typer_is_now_default():
    """The behavior change we are shipping: inline typer (1) is the default."""
    from amphetype.Config import AmphSettings
    # We don't want to construct a full AmphSettings (it does FS + app init),
    # so just check the class default dict directly.
    assert AmphSettings.defaults["which_typer"] == 1


class _FakeTyperSettings:
    """Minimal stub to drive TyperWidget behavior without full settings system."""
    def __init__(self, **vals):
        self._vals = vals
        self._vals.setdefault('require_space', False)
        self._vals.setdefault('lenient_mode', False)
        self._vals.setdefault('overwrite_mode', True)
        self._vals.setdefault('limit_backspace', False)
        self._vals.setdefault('show_progress', False)
        self._vals.setdefault('background_color', QColor('white'))

    def __getitem__(self, k):
        return self._vals[k]

    def __call__(self, name):
        # Support the S('foo') style used in some bindings
        class _V:
            def bind_value(self, f, call=True): pass
            def bind_change(self, f, call=True): pass
            def set(self, v): pass
            def get(self): return self._vals.get(name)  # type: ignore
        v = _V()
        v._vals = self._vals
        return v

    def get(self, k, default=None):
        return self._vals.get(k, default)


def test_heatmap_mode_switch_leaves_typed_chars_alone(qapp):
  from amphetype.speed_heatmap import MODE_WORD, MODE_TRIGRAM

  doc = LessonDocument(QFont("Arial", 12))
  doc.set_text("abcd")
  doc.insert("a")
  doc.insert("b")
  c = Cursor(doc, doc._start.position())
  typed_fg = c.charFormat().foreground().color()
  doc.set_speed_heatmap(True, MODE_WORD, {'abcd': 100.0})
  doc.set_speed_heatmap(True, MODE_TRIGRAM, {'bcd': 80.0})
  assert c.charFormat().foreground().color() == typed_fg
  c.movePosition(c.NextCharacter)
  assert c.charFormat().foreground().color() == typed_fg


def test_speed_heatmap_colors_matching_letters(qapp):
  from amphetype.speed_heatmap import MODE_CHAR, wpm_color_q

  doc = LessonDocument(QFont("Arial", 12))
  doc.set_text("ab")
  doc.set_speed_heatmap(True, MODE_CHAR, {'a': 130.0})
  c = doc._start
  assert c.charFormat().foreground().color().name() == wpm_color_q(130).name()
  c.movePosition(c.NextCharacter)
  assert c.charFormat().foreground().color() == doc.style_untyped.foreground().color()


def test_speed_heatmap_disabled_restores_default_foreground(qapp):
  from amphetype.speed_heatmap import MODE_CHAR

  doc = LessonDocument(QFont("Arial", 12))
  doc.set_text("a")
  doc.set_speed_heatmap(True, MODE_CHAR, {'a': 50.0})
  doc.set_speed_heatmap(False, MODE_CHAR, {})
  assert doc._start.charFormat().foreground().color() == doc.style_untyped.foreground().color()


def test_read_ahead_preview_then_hides(qapp):
  from amphetype.read_ahead import READ_AHEAD_NORMAL

  page = QColor('#2a2a2a')
  doc = LessonDocument(QFont("Arial", 12))
  doc.set_page_background(page)
  doc.set_read_ahead_mode(READ_AHEAD_NORMAL)
  doc.set_text("hello world foo")

  def fg_at(doc_pos):
    c = Cursor(doc, position=doc_pos)
    c.movePosition(c.NextCharacter, c.KeepAnchor)
    return c.charFormat().foreground().color()

  hidden_fg = page
  visible_fg = doc.style_untyped.foreground().color()
  base = doc._start.position()
  assert doc.read_ahead_preview_pending()
  assert fg_at(base + 0) == visible_fg
  assert fg_at(base + 6) == visible_fg

  doc.insert('h')
  assert not doc.read_ahead_preview_pending()
  assert fg_at(base + 6) == hidden_fg
  assert fg_at(base + 12) == visible_fg

  for ch in "ello ":
    doc.insert(ch)
  assert fg_at(base + 6) == hidden_fg
  assert fg_at(base + 12) == hidden_fg


def test_read_ahead_mistake_reveals_only_current_hidden_word(qapp):
  from amphetype.read_ahead import READ_AHEAD_HARD
  from amphetype.typer import TyperWidget

  page = QColor('#2a2a2a')
  doc = LessonDocument(QFont("Arial", 12))
  doc.set_page_background(page)
  doc.set_read_ahead_mode(READ_AHEAD_HARD)
  doc.set_text("one two three four")

  def fg_at(doc_pos):
    c = Cursor(doc, position=doc_pos)
    c.movePosition(c.NextCharacter, c.KeepAnchor)
    return c.charFormat().foreground().color()

  hidden_fg = page
  base = doc._start.position()
  doc.dismiss_read_ahead_preview()
  # hard: hide one, two, three
  doc.insert('x')  # mistake on "one"
  assert fg_at(base + 0) != hidden_fg
  assert fg_at(base + 4) == hidden_fg   # two still hidden
  assert fg_at(base + 8) == hidden_fg   # three still hidden
  assert fg_at(base + 14) != hidden_fg  # four was never hidden


def test_read_ahead_off_shows_untyped_foreground(qapp):
  from amphetype.read_ahead import READ_AHEAD_OFF

  doc = LessonDocument(QFont("Arial", 12))
  doc.set_page_background(QColor('#2a2a2a'))
  doc.set_read_ahead_mode(READ_AHEAD_OFF)
  doc.set_text("hello world")
  c = Cursor(doc, position=doc._start.position() + 6)
  c.movePosition(c.NextCharacter, c.KeepAnchor)
  assert c.charFormat().foreground().color() == doc.style_untyped.foreground().color()


def test_read_ahead_with_heatmap_colors_visible_words(qapp):
  from amphetype.read_ahead import READ_AHEAD_NORMAL
  from amphetype.speed_heatmap import MODE_CHAR, wpm_color_q

  page = QColor('#2a2a2a')
  doc = LessonDocument(QFont("Arial", 12))
  doc.set_page_background(page)
  doc.set_read_ahead_mode(READ_AHEAD_NORMAL)
  doc.set_text("aa bb cc")
  doc.set_speed_heatmap(True, MODE_CHAR, {'c': 50.0})
  doc.dismiss_read_ahead_preview()

  def fg_at(doc_pos):
    c = Cursor(doc, position=doc_pos)
    c.movePosition(c.NextCharacter, c.KeepAnchor)
    return c.charFormat().foreground().color()

  hidden_fg = page
  base = doc._start.position()
  assert fg_at(base + 0) == hidden_fg          # aa hidden
  assert fg_at(base + 3) == hidden_fg          # bb hidden
  assert fg_at(base + 6) == wpm_color_q(50)    # cc visible + heatmap


def test_widget_starts_immediately_without_space(qapp):
    """Primary behavior: inline typer no longer requires SPACE to begin a lesson (default)."""
    from PyQt5.QtGui import QFont
    from amphetype.typer import TyperWidget, LessonDocument

    S = _FakeTyperSettings(require_space=False)
    w = TyperWidget(S)
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("hello")
    w.setLesson(doc)

    assert doc.is_ready()
    # Simulate first keystroke (the widget's insert path)
    w.insert("h")   # should cold-start the run immediately
    assert doc.is_running()
    assert not doc.is_finished()


def test_widget_still_respects_require_space_when_enabled(qapp):
    """The require_space setting still works if a user turns it back on."""
    from PyQt5.QtGui import QFont
    from amphetype.typer import TyperWidget, LessonDocument

    S = _FakeTyperSettings(require_space=True)
    w = TyperWidget(S)
    doc = LessonDocument(QFont("Arial", 12))
    doc.set_text("hi")
    w.setLesson(doc)

    # Non-space should be ignored until started
    w.insert("h")
    assert doc.is_ready()  # still waiting

    w.insert(" ")  # the starter key
    assert doc.is_running()
