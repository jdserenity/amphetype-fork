from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from typing_program.settings import *
from typing_program.timingtuple import RunStats, IDLE_THRESHOLD
from typing_program.Config import Settings
from typing_program.speed_heatmap import book_return_role, char_heatmap_colors, fetch_speed_stats, mode_stat_type, PROGRESS_GREEN, PROGRESS_ORANGE
from typing_program.read_ahead import (
  hidden_char_indices, hidden_word_indices, word_index_at, READ_AHEAD_OFF,
)
from typing_program.Data import Statistic
from typing_program.word_progress import (
  improved_word_spans, new_word_spans, word_perfect_rate_improves,
  word_spans, word_wpm_from_slice,
)
from typing_program import timer
import logging as log

from typing_program.typer.styles import TYPER_CANVAS_DEFAULT

RETURN_CHAR = '⏎' # '↵'
PARA_SEP = '\u2029'
LINE_SEP = '\u2028'

# Lesson text backgrounds only for error highlighting; untyped/correct/inactive stay clear.
_NO_FILL_STYLE_ATTRS = frozenset({'untyped', 'correct', 'inactive'})

### TEXTDOCUMENT

text_props = dict(
  underline=QTextCharFormat.FontUnderline,
  color=QTextCharFormat.ForegroundBrush,
  background=QTextCharFormat.BackgroundBrush,
  kerning=QTextCharFormat.FontKerning,
  overline=QTextCharFormat.FontOverline,
  italic=QTextCharFormat.FontItalic)

def text_style(*args, **kwargs):
  res = QTextCharFormat()
  for a in args:
    res.setProperty(text_props[a], True)
  for k,v in kwargs.items():
    res.setProperty(text_props[k], v)
  return res

def block_style(*args, **kwargs):
  b = QTextBlockFormat()
  b.setTopMargin(20.0)
  b.setBottomMargin(20.0)
  return b


class Cursor(QTextCursor):
  def __init__(self, doc_or_cursor, position=None, select=None, fixed=False, **kwargs):
    super().__init__(doc_or_cursor, **kwargs)
    self.setKeepPositionOnInsert(fixed)
    if position is not None:
      if isinstance(position, tuple):
        self.setPosition(position[0])
        self.setPosition(position[1], self.KeepAnchor)
      else:
        self.setPosition(position)
    if select is not None:
      self.movePosition(select, self.KeepAnchor)

  def nextChar(self):
    return self.document().characterAt(self.position())

  def __repr__(self):
    if self.hasSelection():
      return f'({self.position()}/a={self.anchor()}/t="{self.selectedText()}")'
    return f'({self.position()})'


class LessonDocument(QTextDocument):
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
    # f = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    # f.setPointSize(16)
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
    self._word_prior_counts = {}
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
    self._word_prior_counts = {}
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

  def _book_plain_display(self, text):
    import re
    return re.sub(r'\n\n+', '\n', (text or '').replace('\r\n', '\n').replace('\r', '\n'))

  def set_book_chapter(self, full_text, chunks, chunk_index, auto_returns=True):
    self._book_auto_returns = auto_returns
    self._book_chunks = chunks
    self._book_chunk_index = int(chunk_index)
    before = self._book_plain_display(''.join(chunks[:chunk_index]))
    active = chunks[chunk_index]
    after = self._book_plain_display(''.join(chunks[chunk_index + 1:]))
    self.set_text(active, prologue=before, epilogue=after, book_mode=True)

  def advance_book_chunk(self):
    if not self.has_next_book_chunk():
      return False
    self.set_book_chapter(
      ''.join(self._book_chunks), self._book_chunks, self._book_chunk_index + 1, self._book_auto_returns)
    return True

  def has_next_book_chunk(self):
    return bool(self._book_chunks) and self._book_chunk_index + 1 < len(self._book_chunks)

  def set_text(self, text, prologue='', epilogue='', book_mode=False):
    if not book_mode:
      self._book_auto_returns = False
    self._curtext = (text, prologue, epilogue)

    text = text if text is not None else ''

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

  def _reveal_read_ahead_word_at(self, match_index):
    if not self._read_ahead_mode or self.read_ahead_preview_pending():
      return
    wi = word_index_at(self._match_text, match_index)
    if wi in hidden_word_indices(self._match_text, match_index, self._read_ahead_mode):
      self._read_ahead_revealed.add(wi)

  def read_ahead_preview_pending(self):
    return bool(self._read_ahead_mode) and self.is_ready() and self._read_ahead_preview

  def dismiss_read_ahead_preview(self):
    if not self.read_ahead_preview_pending():
      return False
    self._read_ahead_preview = False
    self._refresh_read_ahead()
    return True

  def set_page_background(self, color):
    self._page_bg = QColor(color)
    self.style_hidden.setForeground(QBrush(self._page_bg))
    self.style_hidden_return.setForeground(QBrush(self._page_bg))
    self._refresh_read_ahead()

  def set_read_ahead_mode(self, mode):
    self._read_ahead_mode = mode
    if self.is_ready() and mode:
      self._read_ahead_preview = True
    elif not mode:
      self._read_ahead_preview = False
    self._refresh_read_ahead()

  def _read_ahead_hidden_indices(self):
    if self._match_text is None or self.read_ahead_preview_pending():
      return set()
    pos = self._run.index if self._run is not None else 0
    return hidden_char_indices(self._match_text, pos, self._read_ahead_mode, self._read_ahead_revealed)

  def _heatmap_colors(self):
    if not self._speed_heatmap_enabled or not self._display_text:
      return []
    key = (self._display_text, self._speed_heatmap_mode, id(self._speed_heatmap_stats))
    if self._heatmap_colors_cache_key != key:
      self._heatmap_colors_cache_key = key
      self._heatmap_colors_cache = char_heatmap_colors(
        self._display_text, self._speed_heatmap_mode, self._speed_heatmap_stats, self._match_text,
        return_char=RETURN_CHAR, book_returns=self._book_auto_returns)
    return self._heatmap_colors_cache

  def _needs_untyped_style_refresh(self):
    return bool(self._read_ahead_mode)

  def _refresh_untyped_styles(self):
    if not self._needs_untyped_style_refresh():
      return
    self._refresh_read_ahead()

  def _refresh_read_ahead(self, force=False):
    if self._match_text is None:
      return
    if not force and not self._read_ahead_mode and not self._speed_heatmap_enabled and not self._book_auto_returns:
      return
    pos = self._run.index if self._run is not None else 0
    hidden = self._read_ahead_hidden_indices()
    colors = self._heatmap_colors() if self._speed_heatmap_enabled else []
    base = self._start.position()
    mi = 0; di = base
    c = Cursor(self)
    c.beginEditBlock()
    while mi < len(self._match_text):
      n = self._match_display_width(mi)
      if mi >= pos:
        for j in range(n):
          disp_i = di + j - base
          if (self._book_auto_returns and j == 0 and self._match_text[mi] == RETURN_CHAR
              and book_return_role(self._match_text, mi, RETURN_CHAR) == 'para_enter'
              and self._book_para_enter_revealed(mi)):
            break
          if (self._book_auto_returns and j == 0 and self._match_text[mi] == RETURN_CHAR
              and book_return_role(self._match_text, mi, RETURN_CHAR) == 'para_enter'):
            style = self.style_hidden_return
          elif self._read_ahead_mode and mi in hidden:
            style = self.style_hidden
          else:
            style = QTextCharFormat(self.style_untyped)
            if colors and disp_i < len(colors) and colors[disp_i] is not None:
              style.setForeground(QBrush(colors[disp_i]))
          c.setPosition(di + j)
          c.movePosition(c.NextCharacter, c.KeepAnchor)
          c.setCharFormat(style)
      di += n; mi += 1
    c.endEditBlock()

  def active_region(self):
    c = Cursor(self, position=self._start.position())
    c.setPosition(self._end.position(), c.KeepAnchor)
    return c

  def sanitize(self, text):
    text = text.replace('\r\n', '\n')
    text = text.replace('\r', '\n')
    text = text.replace('\n', RETURN_CHAR)
    return text

  def _make_display_text(self, match_text):
    if self._book_auto_returns:
      out = []; i = 0
      while i < len(match_text):
        if match_text[i] == RETURN_CHAR:
          role = book_return_role(match_text, i, RETURN_CHAR)
          if role == 'soft_nl':
            out.append('\n'); i += 1
          elif role == 'para_enter':
            out.append(RETURN_CHAR + '\n'); i += 1
            while i < len(match_text) and book_return_role(match_text, i, RETURN_CHAR) == 'para_tail':
              i += 1
          else:
            i += 1
        else:
          out.append(match_text[i]); i += 1
      return ''.join(out)
    return match_text.replace(RETURN_CHAR, RETURN_CHAR + '\n')

  def _match_display_width(self, mi):
    if mi >= len(self._match_text):
      return 0
    if self._match_text[mi] == RETURN_CHAR:
      if self._book_auto_returns:
        role = book_return_role(self._match_text, mi, RETURN_CHAR)
        if role == 'soft_nl':
          return 1
        if role == 'para_enter':
          return 2
        return 0
      return 2
    return 1

  def _display_span(self, mi):
    base = self._start.position()
    di = base
    for i in range(mi):
      di += self._match_display_width(i)
    n = self._match_display_width(mi)
    return di, n

  def _style_match_index(self, mi, style):
    di, n = self._display_span(mi)
    c = Cursor(self)
    for j in range(n):
      c.setPosition(di + j)
      c.movePosition(c.NextCharacter, c.KeepAnchor)
      c.setCharFormat(style)

  def _cursor_to_match_index(self, mi):
    if mi >= len(self._match_text):
      self.cursor.setPosition(self._end.position())
      return
    self.cursor.setPosition(self._display_span(mi)[0])

  def _consume_auto_returns(self):
    while self._run and not self._run.is_complete() and self._run.current and self._run.current.char == RETURN_CHAR:
      mi = self._run.index
      if self._book_auto_returns and book_return_role(self._match_text, mi, RETURN_CHAR) == 'para_enter':
        break
      self._run.visit(True)
      self._run.advance(True)
      self._style_match_index(mi, self.style_correct)
      self._cursor_to_match_index(self._run.index)
      self.progress.emit(self._run.index)

  def _consume_trailing_whitespace(self):
    """Auto-complete trailing whitespace so the last letter ends the lesson."""
    while self._run and not self._run.is_complete() and self._run.current:
      rest = self._match_text[self._run.index:]
      if not rest or not all(c.isspace() for c in rest):
        break
      mi = self._run.index
      self._run.visit(True)
      self._run.advance(True)
      self._style_match_index(mi, self.style_correct)
      self._cursor_to_match_index(self._run.index)
      self.progress.emit(mi)

  def _book_para_enter_index(self):
    if not self._book_auto_returns or not self._run or not self._run.current:
      return None
    mi = self._run.index
    if self._run.current.char != RETURN_CHAR:
      return None
    if book_return_role(self._match_text, mi, RETURN_CHAR) != 'para_enter':
      return None
    return mi

  def _book_para_enter_revealed(self, mi):
    if self._book_para_enter_index() != mi:
      return False
    di, _ = self._display_span(mi)
    if self.characterAt(di) != RETURN_CHAR:
      return True
    return self._first_error is not None and self._first_error.position() == di

  def _book_para_enter_glyph_replaced(self, mi):
    return self._book_para_enter_revealed(mi)

  def _restore_book_para_enter_untyped(self, mi):
    di, _ = self._display_span(mi)
    c = Cursor(self, position=di)
    c.setPosition(di + 1, c.KeepAnchor)
    c.insertText(RETURN_CHAR, self.style_hidden_return)
    self._cursor_to_match_index(mi)

  def _finish_book_insert(self):
    if self.is_finished():
      self.completed.emit(self._run)
    else:
      self._refresh_untyped_styles()
      self.sig_position.emit(self.cursor)

  def _insert_book_para_enter(self, char, lenient=False):
    """Type (or recover) the hidden paragraph break — only the first display glyph is mutable."""
    mi = self._book_para_enter_index()
    assert mi is not None
    correct = char == RETURN_CHAR
    di, _ = self._display_span(mi)
    c = Cursor(self, position=di)
    c.setPosition(di + 1, c.KeepAnchor)

    if self._first_error is not None:
      if not correct:
        self._reveal_read_ahead_word_at(mi)
        self._run.visit(False)
        c.insertText(RETURN_CHAR, self.style_error)
        self._finish_book_insert()
        self.key_typed.emit(False)
        return
      self._run.visit(True)
      self.progress.emit(mi)
      c.insertText(RETURN_CHAR, self.style_hidden_return)
      self._first_error = None
      self._run.advance(True)
      self._cursor_to_match_index(self._run.index)
      self._consume_auto_returns()
      self._consume_trailing_whitespace()
      self._finish_book_insert()
      self.key_typed.emit(True)
      return

    if not correct:
      self._reveal_read_ahead_word_at(mi)
      self._run.visit(False)
      self._run.current.errors += char
      if not lenient:
        self._first_error = Cursor(self, position=di, fixed=True)
      c.insertText(RETURN_CHAR, self.style_error)
      self._cursor_to_match_index(mi)
      self._finish_book_insert()
      self.key_typed.emit(False)
      return

    self._run.visit(True)
    self.progress.emit(mi)
    c.insertText(RETURN_CHAR, self.style_hidden_return)
    self._run.advance(True)
    self._cursor_to_match_index(self._run.index)
    self._consume_auto_returns()
    self._consume_trailing_whitespace()
    self._finish_book_insert()
    self.key_typed.emit(True)

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

  def set_word_prior_counts(self, counts):
    self._word_prior_counts = dict(counts or {})
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

  def set_speed_heatmap(self, enabled, mode, stats):
    self._speed_heatmap_enabled = enabled
    self._speed_heatmap_mode = mode
    self._speed_heatmap_stats = stats or {}
    self._heatmap_colors_cache_key = None
    self._refresh_read_ahead(force=True)

