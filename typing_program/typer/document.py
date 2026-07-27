"""Lesson document: type-on-top matching, run lifecycle, word-progress styles."""

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from typing_program.quote_text import normalize_quotes
from typing_program.timingtuple import RunStats
from typing_program.speed_heatmap import book_return_role, PROGRESS_GREEN, PROGRESS_ORANGE
from typing_program.read_ahead import READ_AHEAD_OFF
from typing_program.word_progress import (
  improved_word_spans, new_word_spans, word_perfect_rate_improves, word_spans,
)
from typing_program import timer
import logging as log
import unicodedata

from typing_program.typer.text_format import (
  RETURN_CHAR, PARA_SEP, LINE_SEP, _NO_FILL_STYLE_ATTRS,
  Cursor, text_style, block_style, text_props,
)
from typing_program.typer.book_typing import BookTypingMixin
from typing_program.typer.lesson_display import LessonDisplayMixin

# Re-export for `from typing_program.typer.document import …`
__all__ = [
  'RETURN_CHAR', 'PARA_SEP', 'LINE_SEP', '_NO_FILL_STYLE_ATTRS',
  'Cursor', 'LessonDocument', 'text_style', 'block_style', 'text_props',
]


class LessonDocument(BookTypingMixin, LessonDisplayMixin, QTextDocument):
  style_untyped = text_style(kerning=False, color=QBrush(QColor('#ffffff')))
  style_error = text_style(kerning=False,
                           background=QBrush(QColor('firebrick')),
                           color=QBrush(QColor('white')))
  style_anyerror = text_style(kerning=False,
                              background=QBrush(QColor('darksalmon')))
  style_correct = text_style(kerning=False, color=QBrush(QColor('#e8e8e8')))
  style_inactive = text_style(color=QBrush(QColor('#888888')))

  style_block = block_style()

  def onColor(self, var):
    cat, name = var.objectName().split('/')

    if cat == 'typer':
      style = self.style_block
      if name == 'para_margin':
        m = var.get()
        style.setTopMargin(m//2)
        style.setBottomMargin((m+1)//2)
      elif name == 'para_lineheight':
        style.setLineHeight(var.get()*100.0, 1)
      else:
        raise RuntimeError(f"internal error: unknown option {cat}/{name}")
    else:
      attr, fgbg = name.split('_')
      style = getattr(self, f'style_{attr}')
      assert style is not None
      if fgbg == 'bg':
        if attr in _NO_FILL_STYLE_ATTRS:
          style.setBackground(QBrush(Qt.NoBrush))
        else:
          style.setBackground(QBrush(var.get()))
      else:
        style.setForeground(QBrush(var.get()))

    if self._curtext is not None and self._match_text:
      self.set_text(*self._curtext)

  # Cursor position changed.
  sig_position = pyqtSignal(QTextCursor)

  started = pyqtSignal()
  paused = pyqtSignal()
  resumed = pyqtSignal()
  ready = pyqtSignal(str)
  completed = pyqtSignal('PyQt_PyObject')
  follow_lost = pyqtSignal('PyQt_PyObject')  # run when follow caret wins the race
  error = pyqtSignal(str)
  progress = pyqtSignal(int)
  progress_badges_changed = pyqtSignal()
  key_typed = pyqtSignal(bool)  # True = correct keystroke, False = error

  def __init__(self, font, *args, **kwargs):
    super().__init__(*args, undoRedoEnabled=False, **kwargs)
    self.setDefaultFont(font)
    self.setDocumentMargin(28)  # breathing room now that the editor frame is gone
    self._speed_heatmap_enabled = False
    self._speed_heatmap_mode = 0
    self._speed_heatmap_stats = {}
    self._heatmap_colors_cache = None
    self._heatmap_colors_cache_key = None
    self._read_ahead_mode = READ_AHEAD_OFF
    self._read_ahead_preview = False
    self._read_ahead_revealed = set()
    self._page_bg = QColor('#f0f0f0')
    self.style_hidden = text_style(kerning=False, color=QBrush(self._page_bg))
    self.style_hidden_return = text_style(kerning=False, color=QBrush(self._page_bg))
    self._book_auto_returns = False
    self._book_chunks = None
    self._book_chunk_index = 0
    self._pre_start_paused = False
    self._follow_lost = False
    self._word_baselines = {}
    self._word_prior_sources = {}
    self._word_spans = []
    self._progress_badges = []
    self.style_progress = text_style(kerning=False, color=QBrush(QColor(PROGRESS_GREEN)))
    self.style_progress_new = text_style(kerning=False, color=QBrush(QColor(PROGRESS_ORANGE)))
    self.set_idle_placeholder()

  def _clear_lesson_state(self):
    self._book_auto_returns = False
    self._book_chunks = None
    self._book_chunk_index = 0
    self._curtext = None
    self._original_text = ''
    self._match_text = None
    self._display_text = None
    self._run = None
    self._first_error = None
    self._pre_start_paused = False
    self._follow_lost = False
    self._progress_badges = []
    self._word_baselines = {}
    self._word_prior_sources = {}
    self._word_spans = []
    self._read_ahead_preview = False
    self._read_ahead_revealed = set()

  def set_idle_placeholder(self):
    """Clear the lesson canvas when there is nothing to type."""
    self.clear()
    self._clear_lesson_state()

  def set_idle_message(self, msg):
    """Show a non-typable message in the lesson canvas."""
    self.clear()
    self._clear_lesson_state()
    c = Cursor(self)
    c.setBlockFormat(self.style_block)
    c.insertText(msg or '', self.style_inactive)
    self.cursor = Cursor(self, position=0)

  def set_text(self, text, prologue='', epilogue='', book_mode=False):
    if not book_mode:
      self._book_auto_returns = False
    # Curly quotes → keyboard ' / "; accents and other Unicode stay.
    text = normalize_quotes(text if text is not None else '')
    prologue = normalize_quotes(prologue or '')
    epilogue = normalize_quotes(epilogue or '')
    self._curtext = (text, prologue, epilogue)

    self.clear()

    c = Cursor(self)
    c.setBlockFormat(self.style_block)

    c.insertText(prologue, self.style_inactive)
    pos = c.position()
    c.insertText(epilogue, self.style_inactive)

    self._original_text = text
    self._match_text = self.sanitize(text)
    self._display_text = self._make_display_text(self._match_text)

    self._start = Cursor(self, position=pos, fixed=True)
    self._end = Cursor(self, position=pos)
    self.cursor = Cursor(self, position=pos)

    self.reset()

  def reset(self):
    assert self._match_text and self._display_text

    self.active_region().insertText(self._display_text, self.style_untyped)

    if self.cursor != self._start:
      self.cursor.setPosition(self._start.position())
      self.sig_position.emit(self.cursor)

    self._run = None
    self._first_error = None
    self._pre_start_paused = False
    self._follow_lost = False
    self._progress_badges = []
    self._read_ahead_preview = bool(self._read_ahead_mode)
    self._read_ahead_revealed = set()
    self._refresh_read_ahead()
    self.ready.emit(self._match_text)

  def active_region(self):
    c = Cursor(self, position=self._start.position())
    c.setPosition(self._end.position(), c.KeepAnchor)
    return c

  def sanitize(self, text):
    text = text.replace('\r\n', '\n')
    text = text.replace('\r', '\n')
    text = text.replace('\n', RETURN_CHAR)
    return text

  def is_running(self):
    """True if a lesson has started but not yet completed."""
    return self._run is not None and not self._run.is_complete() and not self._follow_lost

  def is_paused(self):
    return self._pre_start_paused or (self._run is not None and self._run.is_paused())

  def pause(self):
    if self.is_paused() or self.is_finished():
      return False
    if self.is_ready():
      self._pre_start_paused = True
      self.paused.emit()
      return True
    self._run.pause()
    self.paused.emit()
    return True

  def resume(self):
    if not self.is_paused():
      return False
    if self._pre_start_paused:
      self._pre_start_paused = False
      self.resumed.emit()
      return True
    self._run.resume()
    self.resumed.emit()
    return True

  def is_finished(self):
    """True if a lesson has started and then completed (or follow race lost)."""
    return self._follow_lost or (self._run is not None and self._run.is_complete())

  def lose_follow_race(self):
    """Abort the lesson because the follow caret reached the end first."""
    if self._follow_lost or not self._run or self._run.is_complete():
      return None
    if self.is_paused() and not self._pre_start_paused:
      self._run.resume()
    self._pre_start_paused = False
    self._follow_lost = True
    self.follow_lost.emit(self._run)
    return self._run

  def is_ready(self):
    """True if a lesson has not yet started."""
    return self._run is None and self._match_text is not None and not self._follow_lost

  def start(self):
    """Switches to running state (warm start)."""
    assert self.is_ready()
    self._run = RunStats.make(self._match_text, timer())
    self.started.emit()

  def insert(self, char, overwrite=True, lenient=False):
    if self._match_text is None or self._follow_lost:
      return
    if self.is_paused():
      return
    if not char:
      return

    # Quotes only: ’ → ' so keystrokes match lesson text. Accents pass through.
    if char != RETURN_CHAR:
      char = normalize_quotes(char)
      if not char:
        return
      if len(char) > 1:
        for c in char:
          self.insert(c, overwrite=overwrite, lenient=lenient)
        return
      # Ignore lone combining marks from dead keys (composed é arrives via IME).
      if unicodedata.category(char) == 'Mn':
        return

    if self.read_ahead_preview_pending():
      self.dismiss_read_ahead_preview()
    if self._run is None:
      # Cold start.
      self._run = RunStats.make(self._match_text)
      self.started.emit()

    if self._run.current is None:
      return

    if self._book_para_enter_index() is not None:
      self._insert_book_para_enter(char, lenient=lenient)
      return

    correct = char == self._run.current.char
    should_advance = correct or overwrite

    if self._first_error is not None:
      # Previous error blocking us.
      if not correct:
        self._reveal_read_ahead_word_at(self._run.index)
      self._run.advance(should_advance)
      style = self.style_anyerror if correct else self.style_error
      self.actual_insert(char, style, overwrite=should_advance)
      self._refresh_untyped_styles()
      self.key_typed.emit(correct)
      return

    # Update timing data.
    self._run.visit(correct)

    if correct:
      self.progress.emit(self._run.index)
    else:
      self._reveal_read_ahead_word_at(self._run.index)
      self._run.current.errors += char
      if not lenient:
        self._first_error = Cursor(self.cursor, fixed=True)

    # If not really advancing `_run` will track inserts we're doing.
    mi = self._run.index
    self._run.advance(should_advance)

    style = self.style_correct if correct else self.style_error
    hide_ret = (self._book_auto_returns and char == RETURN_CHAR
                and book_return_role(self._match_text, mi, RETURN_CHAR) == 'para_enter')
    if hide_ret and correct:
      self.actual_insert(char, self.style_hidden_return, overwrite=should_advance)
    else:
      self.actual_insert(char, style, overwrite=should_advance)

    if correct and self._book_auto_returns:
      self._consume_auto_returns()
    if correct and should_advance:
      self._maybe_style_completed_word()
      self._consume_trailing_whitespace()

    if self.is_finished():
      self.completed.emit(self._run)
    else:
      self._refresh_untyped_styles()
      self.sig_position.emit(self.cursor)
    self.key_typed.emit(correct)

  def actual_insert(self, char, style, overwrite=True):
    # One match slot ↔ one display glyph. Callers must pass a single character.
    self.cursor.insertText(char, style)
    if overwrite:
      self.cursor.deleteChar()
    if self.cursor.atBlockEnd() and not (self._run and self._run.ending):
      self.cursor.movePosition(QTextCursor.NextCharacter)

  def backspace(self, by_word=False, protected=False):
    if not self.is_running() or self.is_paused():
      return

    mi = self._book_para_enter_index()
    if mi is not None and self._book_para_enter_glyph_replaced(mi):
      self._restore_book_para_enter_untyped(mi)
      if self._first_error and self.cursor.position() <= self._first_error.position():
        self._first_error = None
      self._refresh_read_ahead()
      self.sig_position.emit(self.cursor)
      return

    mark = Cursor(self.cursor)

    if mark.atBlockStart():
      mark.movePosition(mark.PreviousCharacter)
    if by_word:
      mark.movePosition(mark.PreviousWord)
    else:
      mark.movePosition(mark.PreviousCharacter)
    if mark < self._start:
      mark.setPosition(self._start.position())

    if mark == self.cursor:
      return

    while self.cursor > mark:
      if protected and not self._run.last_was_error():
        break
      if self.cursor.atBlockStart():
        self.cursor.movePosition(mark.PreviousCharacter)
        continue
      c = self._run.pop_char()
      log.debug("backspacing over <%s> (by_word=%s protected=%s cursor=%s mark=%s)", c, by_word, protected, str(self.cursor), str(mark))
      if c is not None:
        self._drop_badges_from(self._run.index)
        self.cursor.insertText(c, self.style_untyped)
        self.cursor.movePosition(QTextCursor.PreviousCharacter)
      self.cursor.deletePreviousChar()

    if self._first_error and self.cursor <= self._first_error:
      self._first_error = None

    self._refresh_read_ahead()
    self.sig_position.emit(self.cursor)

  def set_word_baselines(self, baselines):
    self._word_baselines = dict(baselines or {})

  def set_word_prior_sources(self, sources):
    self._word_prior_sources = {w: set(s) for w, s in (sources or {}).items()}
    self._word_spans = word_spans(self._match_text) if self._match_text else []

  def progress_badges(self):
    return list(self._progress_badges)

  def set_progress_badges(self, badges):
    self._progress_badges = list(badges)
    self.progress_badges_changed.emit()

  def apply_improved_word_styles(self, run, baselines):
    for start, end in improved_word_spans(run, baselines, self._match_text):
      for j in range(start, end):
        self._style_match_index(j, self.style_progress)

  def apply_new_word_styles(self, run, new_common):
    for start, end in new_word_spans(run, new_common, self._match_text):
      for j in range(start, end):
        self._style_match_index(j, self.style_progress_new)

  def _drop_badges_from(self, match_index):
    n = len(self._progress_badges)
    self._progress_badges = [(s, e, g) for s, e, g in self._progress_badges if e <= match_index]
    if len(self._progress_badges) != n:
      self.progress_badges_changed.emit()

  def _maybe_style_completed_word(self):
    if not self._word_baselines or not self._run:
      return
    mi = self._run.index
    if mi <= 0:
      return
    for start, end, word in self._word_spans:
      if end != mi:
        continue
      sub = self._run[start:end]
      if not sub.is_complete() or any(sub[i].mistakes for i in range(len(sub))):
        return
      base = self._word_baselines.get(word)
      if base is None:
        return
      if word_perfect_rate_improves(base):
        for j in range(start, end):
          self._style_match_index(j, self.style_progress)
      return
