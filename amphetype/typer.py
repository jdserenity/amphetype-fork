from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from amphetype.settings import *
from amphetype.layout import FBoxLayout
from amphetype.fwidgets import FStackedWidget
from amphetype.timingtuple import RunStats, collect_run_stat_rows
from amphetype.WeakSpot import WeakSpotLessonBuilder
from amphetype.WeakSpotLessons import build_focus_lesson
from amphetype.Config import Settings
from amphetype.book_mode import (
  BookLessonBuilder, MODE_BOOK, format_book_progress, lesson_text_id,
  practice_mode_from_settings, practice_mode_to_settings,
)
from amphetype.speed_heatmap import book_return_role
from amphetype.read_ahead import (
  hidden_char_indices, hidden_word_indices, word_index_at,
  READ_AHEAD_OFF, document_read_ahead_mode, READ_AHEAD_LEVEL_LABELS,
)

from amphetype.Data import Statistic
from amphetype.speed_heatmap import (
  MODE_LABELS, char_heatmap_colors, fetch_speed_stats, make_heatmap_legend, mode_stat_type,
)
from collections import defaultdict, Counter

from time import time
from amphetype import timer
import logging as log
# log.root.setLevel(log.INFO)


RETURN_CHAR = '⏎' # '↵'
PARA_SEP = '\u2029'
LINE_SEP = '\u2028'

# Lesson text backgrounds only for error highlighting; untyped/correct/inactive stay clear.
_NO_FILL_STYLE_ATTRS = frozenset({'untyped', 'correct', 'inactive'})

MODE_NORMAL = 'normal'
MODE_WEAKSPOT = 'weakspot'
_WEAKSPOT_BTN_LABEL = 'weakspot'
_GENERATING_BTN_LABEL = 'generating…'


def lesson_completion_action(mode, is_lesson, auto_review, has_review_words, focus_drill=False):
  """What to do after a typing session ends."""
  if focus_drill:
    return 'focus_repeat'
  if mode == MODE_BOOK:
    return 'book_next'
  if mode == MODE_WEAKSPOT:
    return 'weakspot_next'
  if not is_lesson and auto_review and has_review_words:
    return 'review'
  return 'normal_next'


_SOURCE_FILE_EXTS = ('.txt', '.text', '.md', '.markdown', '.epub', '.html', '.htm', '.rtf', '.pdf')

def _display_source_name(source_name):
  name = source_name.strip()
  lower = name.lower()
  for ext in _SOURCE_FILE_EXTS:
    if lower.endswith(ext):
      return name[: -len(ext)].rstrip()
  return name

def format_source_attribution(source_name):
  """Footer line for novel sources, e.g. '— Pride and Prejudice'. Empty for system sources."""
  if not source_name:
    return ''
  name = _display_source_name(source_name)
  if not name or (name.startswith('<') and name.endswith('>')):
    return ''
  return f'— {name}'


def configure_transparent_typer(typer):
  """QTextEdit + viewport must both be transparent; stylesheet on the edit alone is not enough."""
  typer.setStyleSheet('QTextEdit { background: transparent; border: none; padding: 0; }')
  vp = typer.viewport()
  vp.setAutoFillBackground(False)
  vp.setStyleSheet('background: transparent;')
# DIAMOND = '◈'
# VIS_SPACE = '␣'



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

    if self._curtext is not None:
      self.set_text(*self._curtext)

  # Cursor position changed.
  sig_position = pyqtSignal(QTextCursor)

  started = pyqtSignal()
  paused = pyqtSignal()
  resumed = pyqtSignal()
  ready = pyqtSignal(str)
  completed = pyqtSignal('PyQt_PyObject')
  error = pyqtSignal(str)
  progress = pyqtSignal(int)

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
    self.set_text('default text')

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
    if not self._book_chunks or self._book_chunk_index + 1 >= len(self._book_chunks):
      return False
    self.set_book_chapter(
      ''.join(self._book_chunks), self._book_chunks, self._book_chunk_index + 1, self._book_auto_returns)
    return True

  def set_text(self, text, prologue='', epilogue='', book_mode=False):
    if not book_mode:
      self._book_auto_returns = False
    self._curtext = (text, prologue, epilogue)

    text = text or 'default text'

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
        return
      self._run.visit(True)
      self.progress.emit(mi)
      c.insertText(RETURN_CHAR, self.style_hidden_return)
      self._first_error = None
      self._run.advance(True)
      self._cursor_to_match_index(self._run.index)
      self._consume_auto_returns()
      self._finish_book_insert()
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
      return

    self._run.visit(True)
    self.progress.emit(mi)
    c.insertText(RETURN_CHAR, self.style_hidden_return)
    self._run.advance(True)
    self._cursor_to_match_index(self._run.index)
    self._consume_auto_returns()
    self._finish_book_insert()

  def is_running(self):
    """True if a lesson has started but not yet completed."""
    return self._run is not None and not self._run.is_complete()

  def is_paused(self):
    return self._run is not None and self._run.is_paused()

  def pause(self):
    if not self.is_running() or self.is_paused():
      return False
    self._run.pause()
    self.paused.emit()
    return True

  def resume(self):
    if not self.is_paused():
      return False
    self._run.resume()
    self.resumed.emit()
    return True

  def is_finished(self):
    """True if a lesson has started and then completed."""
    return self._run is not None and self._run.is_complete()

  def is_ready(self):
    """True if a lesson has not yet started."""
    return self._run is None

  def start(self):
    """Switches to running state (warm start)."""
    assert self.is_ready()      
    self._run = RunStats.make(self._match_text, timer())
    self.started.emit()

  def insert(self, char, overwrite=True, lenient=False):
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

    if self.is_finished():
      self.completed.emit(self._run)
    else:
      self._refresh_untyped_styles()
      self.sig_position.emit(self.cursor)

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
        self.cursor.insertText(c, self.style_untyped)
        self.cursor.movePosition(QTextCursor.PreviousCharacter)
      self.cursor.deletePreviousChar()
    
    if self._first_error and self.cursor <= self._first_error:
      self._first_error = None

    self._refresh_read_ahead()
    self.sig_position.emit(self.cursor)

  def set_speed_heatmap(self, enabled, mode, stats):
    self._speed_heatmap_enabled = enabled
    self._speed_heatmap_mode = mode
    self._speed_heatmap_stats = stats or {}
    self._heatmap_colors_cache_key = None
    self._refresh_read_ahead(force=True)


### WIDGET


class _LessonPauseOverlay(QWidget):
  continueClicked = pyqtSignal()
  restartClicked = pyqtSignal()

  def __init__(self, parent):
    super().__init__(parent)
    self.setAttribute(Qt.WA_StyledBackground, True)
    self.setStyleSheet('background-color: rgba(0, 0, 0, 0.55);')
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addStretch(1)
    row = QHBoxLayout()
    row.addStretch(1)
    btn_style = (
      'QPushButton { color: #ffffff; background: #444444; border: 1px solid #666666;'
      ' padding: 8px 20px; font-size: 13px; }'
      'QPushButton:hover { background: #555555; }')
    self._btn_restart = QPushButton('Restart', flat=False)
    self._btn_continue = QPushButton('Continue', flat=False)
    for b in (self._btn_restart, self._btn_continue):
      b.setFocusPolicy(Qt.NoFocus)
      b.setCursor(Qt.PointingHandCursor)
      b.setStyleSheet(btn_style)
    row.addWidget(self._btn_restart)
    row.addSpacing(16)
    row.addWidget(self._btn_continue)
    row.addStretch(1)
    lay.addLayout(row)
    lay.addStretch(1)
    self._btn_restart.clicked.connect(self.restartClicked.emit)
    self._btn_continue.clicked.connect(self.continueClicked.emit)
    self.hide()


class TyperCanvas(QWidget):
  def __init__(self, typer, overlay, *args, **kwargs):
    super().__init__(*args, objectName='TyperCanvas', **kwargs)
    self._overlay = overlay
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(typer)
    overlay.setParent(self)
    overlay.hide()

  def resizeEvent(self, evt):
    super().resizeEvent(evt)
    self._overlay.setGeometry(self.rect())


class TyperWidget(QTextEdit):
  def __init__(self, settings, *args, text=None, **kwargs):
    # Need to set TextEditable flag to make the cursor the normal
    # blinky kind. Not sure how to show it for read-only mode.
    super().__init__(*args,
                     contextMenuPolicy=Qt.NoContextMenu,
                     textInteractionFlags=Qt.TextEditable,
                     objectName='TyperWidget',
                     undoRedoEnabled=False,
                     cursorWidth=3,
                     frameShape=QFrame.NoFrame,
                     **kwargs)

    self._settings = settings
    self._lesson = None
    self._pin_typing_center = False
    # settings('lenient_mode').bind_value(self.setLenientMode)
    # settings('require_space').bind_value(self.setRequireSpace)
    settings('overwrite_mode').bind_value(self.setOverwriteMode)
    configure_transparent_typer(self)
    settings('background_color').bind_value(lambda v: configure_transparent_typer(self))

  def _typing_region_doc_y_range(self):
    lesson = self._lesson
    region = lesson.active_region()
    if region.hasSelection():
      start_pos = region.selectionStart()
      end_pos = region.selectionEnd() - 1
    else:
      start_pos = end_pos = lesson._start.position()
    scroll = self.verticalScrollBar().value()
    y_top = self.cursorRect(Cursor(lesson, position=start_pos)).top() + scroll
    r_end = self.cursorRect(Cursor(lesson, position=end_pos))
    return y_top, r_end.bottom() + scroll

  def center_typing_vertically(self):
    """Scroll so the lesson typing region sits mid-viewport (normal mode)."""
    if not self._lesson:
      return True
    vp_h = self.viewport().height()
    if vp_h <= 0:
      return False
    sb = self.verticalScrollBar()
    if sb.maximum() <= 0:
      return True
    y_top, y_bot = self._typing_region_doc_y_range()
    target = int(round((y_top + y_bot) / 2 - vp_h / 2))
    sb.setValue(max(sb.minimum(), min(sb.maximum(), target)))
    return True

  def _center_typing_when_ready(self):
    if not self._pin_typing_center:
      return
    if not self.center_typing_vertically():
      QTimer.singleShot(0, self._center_typing_when_ready)

  def resizeEvent(self, evt):
    super().resizeEvent(evt)
    if self._pin_typing_center:
      self.center_typing_vertically()

  def setLesson(self, lesson):
    if lesson == self._lesson:
      self._follow_cursor(lesson.cursor)
      self.updateStatus()
      return
    
    if self._lesson is not None:
      self._lesson.sig_position.disconnect(self._follow_cursor)
      self._lesson.ready.disconnect(self.updateStatus)
      self._lesson.completed.disconnect(self.updateStatus)

    if self.document() != lesson:
      w = self.cursorWidth() # Layout thingamajig resets cursor width.
      self.setDocument(lesson)
      self.setCursorWidth(w)
    self._follow_cursor(lesson.cursor)
    self.updateStatus()

    lesson.sig_position.connect(self._follow_cursor)
    lesson.ready.connect(self.updateStatus)
    lesson.completed.connect(self.updateStatus)
    self._lesson = lesson

  def _follow_cursor(self, cursor):
    self.setTextCursor(cursor)
    self.ensureCursorVisible()

  def updateStatus(self):
    if self._lesson is None:
      return
    self.setReadOnly(self._lesson.is_finished() or self._lesson.is_paused())

  def _toggle_pause(self):
    if self._lesson.is_paused():
      self._lesson.resume()
    elif self._lesson.is_running():
      self._lesson.pause()

  # Block mouse cursor movement. (Focus should still work.)
  def mousePressEvent(self, e):
    if self._lesson and self._lesson.is_paused():
      return
    pass

  def mouseReleaseEvent(self, e):
    if self._lesson and self._lesson.is_paused():
      return
    pass

  def keyPressEvent(self, evt):
    if not self._lesson:
      evt.ignore()
      return

    if evt.key() == Qt.Key_Escape:
      if self._lesson.is_paused() or self._lesson.is_running():
        self._toggle_pause()
      evt.accept()
      return

    if self._lesson.is_paused():
      evt.ignore()
      return

    if evt.key() == Qt.Key_Backspace or evt.key() == Qt.Key_Back:
      by_word = bool(evt.modifiers() & (Qt.ControlModifier | Qt.MetaModifier | Qt.AltModifier))
      self.backspace(word=by_word)
    elif evt.key() == Qt.Key_Enter or evt.key() == Qt.Key_Return:
      self.insert(RETURN_CHAR)
    elif evt.text() and ord(evt.text()) >= 32:
      self.insert(evt.text())
    else:
      evt.ignore()
      return

    evt.accept()

  def insert(self, char):
    if self._lesson is None or self._lesson.is_finished() or self._lesson.is_paused():
      return

    if not self._lesson.is_running() and self._settings['require_space']:
      if char == ' ':
        self._lesson.start()
      return

    self._lesson.insert(char, overwrite=self.overwriteMode(), lenient=self._settings['lenient_mode'])

  def backspace(self, word=False):
    if self._lesson is None or not self._lesson.is_running() or self._lesson.is_paused():
      return
    self._lesson.backspace(by_word=word, protected=self._settings['limit_backspace'])



class TyperWindow(QWidget):
  wantReview = pyqtSignal('PyQt_PyObject')
  wantText = pyqtSignal()
  needWeakspotLesson = pyqtSignal(str)
  statsChanged = pyqtSignal()
  
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.setObjectName('TyperWindow')

    app = QApplication.instance()
    self._settings = app.settings
    self.S = app.settings.typer_settings
    self.DB = app.DB

    self._current_lesson = None
    self._read_ahead_on = False
    self._read_ahead_level = 0
    self._mode = MODE_NORMAL
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._weakspot = WeakSpotLessonBuilder(self)
    self._weakspot.lessonReady.connect(self._on_weakspot_lesson)
    self._weakspot.busyChanged.connect(self._on_weakspot_busy)
    self._book = BookLessonBuilder(self.DB, self)
    self._book.lessonReady.connect(self._on_book_lesson)
    self._book.progressChanged.connect(self._on_book_progress)
    self._book_meta = None
    self._typer = TyperWidget(self.S)
    hack = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Ignored)
    self._label = QLabel(wordWrap=True, sizePolicy=hack)
    self._prog = QProgressBar()
    self._progw = FStackedWidget([QLabel('Type like the wind!'), self._prog])
    self._prog_layout = FStackedWidget([self._label, self._progw])

    self.S('show_progress').bind_value(self._progw.setCurrentIndex)
    self.S('require_space').bind_change(lambda: self.updateLabel())

    # I am so confused. Settings system must have gone through 3 totally different paradigms.
    self._settings.signal_for("typer_font").connect(self.updateFont)

    doc = LessonDocument(self._settings.getFont('typer_font'))

    for var in self._settings.typer_colors:
      var.onChange.connect(doc.onColor)
      doc.onColor(var)
    for vname in ['para_lineheight', 'para_margin']:
      var = self._settings.typer_settings(vname)
      var.onChange.connect(doc.onColor)
      doc.onColor(var)

    doc.started.connect(self._prog_layout.cycle)
    doc.started.connect(self._on_lesson_started)
    doc.progress.connect(self._prog.setValue)
    doc.ready.connect(self.typingReady)
    doc.completed.connect(self.typingDone)
    doc.paused.connect(self._on_lesson_paused)
    doc.resumed.connect(self._on_lesson_resumed)

    self._typer.setLesson(doc)
    
    self._doc = doc

    # Canvas wrapper: provides the uniform background color chosen by the user.
    # The TyperWidget inside it is transparent + borderless, so there is no
    # distinct "text entry box" — the styled lesson text just lives on the canvas.
    self._pause_overlay = _LessonPauseOverlay(None)
    self._pause_overlay.continueClicked.connect(self._doc.resume)
    self._pause_overlay.restartClicked.connect(self._restart_lesson)
    self._canvas = TyperCanvas(self._typer, self._pause_overlay)

    self._source_lbl = QLabel(wordWrap=True)
    self._source_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    self._source_lbl.installEventFilter(self)
    self._book_prog_lbl = QLabel('')
    self._book_prog_lbl.setStyleSheet('color: #ffffff; font-size: 11px;')
    self._book_prog_lbl.setVisible(False)

    self._mode_btn_style = (
      'QPushButton { color: #555; border: none; background: transparent; font-size: 11px; padding: 2px 6px; }'
      'QPushButton:hover { color: #888; }'
      'QPushButton[activeMode="true"] { color: #ffffff; }')

    self._btn_normal = QPushButton('normal', flat=True)
    self._btn_book = QPushButton('book', flat=True)
    self._btn_weakspot = QPushButton('weakspot', flat=True)
    self._btn_read_ahead = QPushButton('read ahead', flat=True)
    self._btn_read_ahead_level = QPushButton('normal', flat=True)
    self._btn_heatmap = QPushButton('heatmap', flat=True)
    self._btn_heatmap.clicked.connect(self._toggleHeatmap)
    self._btn_heatmap_kind = QPushButton(flat=True)
    self._btn_heatmap_kind.clicked.connect(self._cycleHeatmapMode)
    for b in (self._btn_normal, self._btn_book, self._btn_weakspot, self._btn_read_ahead, self._btn_read_ahead_level):
      b.setCursor(Qt.PointingHandCursor)
      b.setFocusPolicy(Qt.NoFocus)
      b.setStyleSheet(self._mode_btn_style)
    for b in (self._btn_heatmap, self._btn_heatmap_kind):
      b.setCursor(Qt.PointingHandCursor)
      b.setFocusPolicy(Qt.NoFocus)
    self._btn_normal.clicked.connect(lambda: self.set_practice_mode(MODE_NORMAL))
    self._btn_book.clicked.connect(lambda: self.set_practice_mode(MODE_BOOK))
    self._btn_weakspot.clicked.connect(self._on_weakspot_click)
    self._btn_read_ahead.clicked.connect(self.toggle_read_ahead)
    self._btn_read_ahead_level.clicked.connect(self.cycle_read_ahead_level)
    self._weakspot_generating = False

    self._heatmap_legend = make_heatmap_legend()
    self._heatmap_panel = QWidget()
    hp_lay = QHBoxLayout(self._heatmap_panel)
    hp_lay.setContentsMargins(0, 0, 0, 0)
    hp_lay.setSpacing(8)
    hp_lay.addWidget(self._btn_heatmap_kind, 0)
    hp_lay.addWidget(self._heatmap_legend, 0)

    mode_row = QWidget()
    mode_lay = QHBoxLayout(mode_row)
    mode_lay.setContentsMargins(0, 0, 0, 0)
    mode_lay.setSpacing(0)
    mode_lay.addWidget(self._btn_normal)
    mode_lay.addWidget(self._btn_book)
    mode_lay.addWidget(self._book_prog_lbl)
    mode_lay.addWidget(self._btn_weakspot)
    mode_lay.addWidget(self._btn_read_ahead)
    mode_lay.addWidget(self._btn_read_ahead_level)
    mode_lay.addWidget(self._btn_heatmap)
    mode_lay.addWidget(self._heatmap_panel)
    mode_lay.addStretch(1)
    mode_lay.addWidget(self._source_lbl)
    self.S('speed_heatmap').bind_value(self._onHeatmapSetting, call=True)
    self.S('speed_heatmap_mode').bind_value(self._onHeatmapSetting, call=True)

    self.setLayout(FBoxLayout([
      (self._prog_layout, 0),
      (self._canvas, 100),
      (mode_row, 0),
      ]))

    self.S('background_color').bind_value(self._applyBackground, call=True)
    self.statsChanged.connect(self._weakspot.on_stats_changed)
    self._apply_practice_mode_from_settings()
    self._apply_read_ahead_from_settings()

  def _polish_mode_btn(self, btn):
    btn.style().unpolish(btn)
    btn.style().polish(btn)

  def _apply_read_ahead_from_settings(self):
    enabled = bool(self._settings.get('read_ahead_enabled'))
    level = self.S['read_ahead_level']
    self._set_read_ahead_ui(enabled, level, refresh_doc=True)

  def toggle_read_ahead(self):
    enabled = not self._read_ahead_on
    self._settings.set('read_ahead_enabled', enabled)
    self._set_read_ahead_ui(enabled, self._read_ahead_level, refresh_doc=True)

  def cycle_read_ahead_level(self):
    if not self._read_ahead_on:
      return
    level = (self._read_ahead_level + 1) % len(READ_AHEAD_LEVEL_LABELS)
    self.S('read_ahead_level').set(level)
    self._set_read_ahead_ui(True, level, refresh_doc=True)

  def _set_read_ahead_ui(self, enabled, level, refresh_doc=False):
    self._read_ahead_on = enabled
    self._read_ahead_level = level
    self._btn_read_ahead.setStyleSheet(self._mode_btn_style)
    self._btn_read_ahead.setProperty('activeMode', enabled)
    self._polish_mode_btn(self._btn_read_ahead)
    self._btn_read_ahead_level.setText(READ_AHEAD_LEVEL_LABELS[level])
    self._btn_read_ahead_level.setVisible(enabled)
    if enabled:
      self._btn_read_ahead_level.setStyleSheet(self._mode_btn_style)
      self._btn_read_ahead_level.setProperty('activeMode', True)
      self._polish_mode_btn(self._btn_read_ahead_level)
    if refresh_doc:
      self._doc.set_read_ahead_mode(document_read_ahead_mode(enabled, level))

  def updateFont(self):
    self._doc.setDefaultFont(self._settings.getFont('typer_font'))

  def _toggleHeatmap(self):
    self.S('speed_heatmap').set(not self.S('speed_heatmap').get())

  def _cycleHeatmapMode(self):
    mode = (self.S('speed_heatmap_mode').get() + 1) % len(MODE_LABELS)
    self.S('speed_heatmap_mode').set(mode)

  def _style_heatmap_footer_btn(self, btn, on):
    # Direct color — QSS activeMode only matches bool true, not int 1 from settings.
    color = '#ffffff' if on else '#555555'
    btn.setStyleSheet(
      'QPushButton { color: %s; border: none; background: transparent; font-size: 11px; padding: 2px 6px; }'
      'QPushButton:hover { color: #888888; }' % color)

  def _onHeatmapSetting(self, *_):
    on = bool(self.S('speed_heatmap').get())
    mode = int(self.S('speed_heatmap_mode').get())
    self._style_heatmap_footer_btn(self._btn_heatmap, on)
    self._heatmap_panel.setVisible(on)
    self._btn_heatmap_kind.setText(MODE_LABELS[mode])
    self._style_heatmap_footer_btn(self._btn_heatmap_kind, on)
    self._refreshHeatmap()

  def _heatmapStats(self):
    mode = self.S('speed_heatmap_mode').get()
    stats = fetch_speed_stats(self.DB, hist_cutoff=0, stat_type=mode_stat_type(mode))
    if self._focus_drill and self._focus_drill_wpm:
      stats = dict(stats)
      for kind, data in self._focus_drill:
        wpm = self._focus_drill_wpm.get(data)
        if wpm is not None:
          prev = stats.get(data) or {}
          stats[data] = {**prev, 'wpm': wpm}
    return stats

  def _refreshHeatmap(self):
    self._doc.set_speed_heatmap(
      self.S('speed_heatmap').get(),
      self.S('speed_heatmap_mode').get(),
      self._heatmapStats())

  def _applyBackground(self, color):
    """Uniform fill under the lesson; per-char formats stay clear except errors."""
    if hasattr(color, 'name'):
      name = color.name()
      qcolor = color
    else:
      name = str(color)
      qcolor = QColor(color)
    sheet = f'background-color: "{name}";'
    self.setStyleSheet(f'TyperWindow {{ {sheet} }}')
    self._canvas.setStyleSheet(f'QWidget#TyperCanvas {{ {sheet} }}')
    configure_transparent_typer(self._typer)
    self._doc.set_page_background(qcolor)

  def eventFilter(self, obj, evt):
    if obj is self._source_lbl and self._mode == MODE_BOOK:
      if evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.LeftButton:
        self._show_book_menu()
        return True
    return super().eventFilter(obj, evt)

  def showEvent(self, evt):
    self._typer.setFocus()
    if self._typer._pin_typing_center:
      QTimer.singleShot(0, self._typer._center_typing_when_ready)
    return super().showEvent(evt)

  def _on_lesson_started(self):
    self._typer._pin_typing_center = False

  def _on_lesson_paused(self):
    self._pause_overlay.show()
    self._pause_overlay.raise_()
    self._typer.updateStatus()

  def _on_lesson_resumed(self):
    self._pause_overlay.hide()
    self._typer.updateStatus()
    self._typer.setFocus()

  def _restart_lesson(self):
    self._pause_overlay.hide()
    self._doc.reset()
    self._typer.setFocus()

  def _schedule_typing_center(self):
    self._typer.setTextCursor(self._doc.cursor)
    self._typer._pin_typing_center = True
    QTimer.singleShot(0, self._typer._center_typing_when_ready)

  def typingReady(self, text):
    self._pause_overlay.hide()
    self._prog_layout.setCurrentIndex(0)
    self._prog.setMaximum(len(text))

  def setDefaultText(self):
    log.error("setDefaultText() NOT IMPLEMENTED")
    print("setDefaultText() NOT IMPLEMENTED")

  def setText(self, txt):
    self._current_lesson = txt
    textid, srcid, _ = txt
    self._update_source_label(srcid)
    pre, _, post = self.DB.getTextContext(textid)

    # Only show real surrounding context from the same source. Never insert ugly placeholder labels.
    prologue = (pre[2] + '\n') if pre is not None else ''
    epilogue = ('\n' + post[2]) if post is not None else ''

    self._doc.set_text(txt[2], prologue=prologue, epilogue=epilogue)
    if self._mode == MODE_NORMAL:
      self._schedule_typing_center()
    else:
      self._typer._pin_typing_center = False
    self._refreshHeatmap()
    self._typer.setFocus()
    self._prog.setValue(0)

  def _update_source_label(self, srcid):
    row = self.DB.fetchone('select name from source where rowid=?', (None,), (srcid,))
    text = format_source_attribution(row[0] if row else '')
    self._source_lbl.setText(text)
    self._source_lbl.setVisible(bool(text) and self._mode == MODE_NORMAL)

  def _update_book_footer(self, meta=None):
    if meta is None:
      meta = self._book_meta or {}
    prog = format_book_progress(
      meta.get('title') or '', meta.get('chunk_index', 0), meta.get('chunk_count', 0))
    self._book_prog_lbl.setText(prog)
    book = meta.get('book_name') or ''
    self._source_lbl.setText(format_source_attribution(book))
    self._source_lbl.setVisible(bool(book))
    self._source_lbl.setCursor(Qt.PointingHandCursor if book else Qt.ArrowCursor)

  def _show_book_menu(self):
    menu = QMenu(self)
    cur = self._book.current_source_id()
    for sid, _, label in self._book.source_menu_entries():
      act = menu.addAction(label)
      act.setCheckable(True)
      act.setChecked(sid == cur)
      act.triggered.connect(lambda _=False, s=sid: self._select_book(s))
    menu.exec_(self._source_lbl.mapToGlobal(QPoint(0, self._source_lbl.height())))

  def _select_book(self, source_id):
    self._book.set_source_id(int(source_id))
    self._book.request_lesson(advance_chapter=False)

  def _on_book_progress(self, msg):
    if self._mode == MODE_BOOK:
      self._book_prog_lbl.setText(msg)

  def _on_book_lesson(self, lesson):
    if self._mode != MODE_BOOK:
      return
    if not lesson:
      self.updateLabel('No books available — import a text on the Sources tab.')
      return
    tid, srcid, meta = lesson
    body = meta['full_text']
    chunks = meta['chunks']
    if self._settings.get('text_force_ascii'):
      from amphetype.TextManager import force_ascii
      body = force_ascii(body)
      chunks = [force_ascii(c) for c in chunks]
      meta = dict(meta, full_text=body, chunks=chunks)
    self._book_meta = meta
    active = chunks[meta['chunk_index']]
    self._current_lesson = (tid, srcid, active)
    self._update_book_footer(meta)
    self._doc.set_book_chapter(body, chunks, meta['chunk_index'], auto_returns=True)
    self._schedule_typing_center()
    self._refreshHeatmap()
    self._typer.setFocus()
    self._prog.setValue(0)
    self._prog.setMaximum(len(active))

  def _apply_practice_mode_from_settings(self):
    mode = practice_mode_from_settings(self._settings.get('practice_mode'))
    self._set_mode_ui(mode, load=False)
    if mode == MODE_WEAKSPOT:
      self._weakspot.request_next_lesson(force=True)
    elif mode == MODE_BOOK:
      self._book.invalidate_cache()
      self._book.request_lesson(advance_chapter=False)

  def _on_weakspot_click(self):
    if self._mode == MODE_WEAKSPOT and self._focus_drill:
      self._exit_focus_drill()
      return
    self.set_practice_mode(MODE_WEAKSPOT)

  def _exit_focus_drill(self):
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._weakspot.request_next_lesson(force=True)

  def load_corpus_text(self, v):
    """Open a corpus chunk in normal mode (from Performance Analysis Find in corpus)."""
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._settings.set('practice_mode', 0)
    self._set_mode_ui(MODE_NORMAL, load=False)
    self.setText(v)

  def _emit_focus_lesson(self, targets):
    wl = str(Settings.DATA_DIR / 'wordlists' / 'words-20.txt')
    lesson = build_focus_lesson(
      targets, wordlist_path=wl, max_chars=Settings.get('max_chars'))
    if not lesson:
      return False
    self._set_weakspot_footer_busy(False)
    self.needWeakspotLesson.emit(lesson)
    return True

  def start_focus_drill(self, targets):
    """Start weakspot focus drill on specific type targets from Performance Analysis."""
    self._focus_drill = [(t[0], t[1]) for t in targets]
    self._focus_drill_wpm = {}
    for t in targets:
      if len(t) > 2 and t[2] is not None:
        self._focus_drill_wpm[t[1]] = t[2]
    self._settings.set('practice_mode', 1)
    self._set_mode_ui(MODE_WEAKSPOT, load=False)
    if not self._emit_focus_lesson(self._focus_drill):
      self._focus_drill = None
      self._focus_drill_wpm = {}
      self.updateLabel('Could not build a drill for those targets.')
      return

  def set_practice_mode(self, mode):
    if mode == self._mode:
      return
    if mode != MODE_WEAKSPOT:
      self._focus_drill = None
    self._focus_drill_wpm = {}
    self._settings.set('practice_mode', practice_mode_to_settings(mode))
    self._set_mode_ui(mode, load=True)

  def _set_mode_ui(self, mode, load):
    self._mode = mode
    for btn, m in ((self._btn_normal, MODE_NORMAL), (self._btn_book, MODE_BOOK), (self._btn_weakspot, MODE_WEAKSPOT)):
      btn.setStyleSheet(self._mode_btn_style)
      btn.setProperty('activeMode', mode == m)
      self._polish_mode_btn(btn)
    self._book_prog_lbl.setVisible(mode == MODE_BOOK)
    if self._current_lesson and mode == MODE_NORMAL:
      self._source_lbl.setCursor(Qt.ArrowCursor)
      self._update_source_label(self._current_lesson[1])
    elif mode == MODE_BOOK and self._book_meta:
      self._update_book_footer()
    else:
      self._source_lbl.setVisible(False)
      self._source_lbl.setCursor(Qt.ArrowCursor)
    if not load:
      return
    if mode == MODE_WEAKSPOT:
      self._weakspot.request_next_lesson(force=True)
    elif mode == MODE_BOOK:
      self._book.invalidate_cache()
      self._book.request_lesson(advance_chapter=False)
    else:
      self._set_weakspot_footer_busy(False)
      self.wantText.emit()

  def _set_weakspot_footer_busy(self, busy):
    self._weakspot_generating = busy
    if busy and self._mode == MODE_WEAKSPOT:
      self._btn_weakspot.setText(_GENERATING_BTN_LABEL)
      self._btn_weakspot.setEnabled(False)
    else:
      self._btn_weakspot.setText(_WEAKSPOT_BTN_LABEL)
      self._btn_weakspot.setEnabled(True)

  def _on_weakspot_busy(self, busy):
    self._set_weakspot_footer_busy(busy)

  def _on_weakspot_lesson(self, lesson):
    if self._mode != MODE_WEAKSPOT:
      return
    if not lesson:
      self.updateLabel('No statistics yet — practice on normal mode first.')
      return
    self._set_weakspot_footer_busy(False)
    self.needWeakspotLesson.emit(lesson)

  def updateLabel(self, msg=None):
    text = []
    # text.append("[This beta typer will not collect statistics currently, don't use it!]")
    if msg is not None:
      text.append('<big><b>' + msg + '</b></big>')
    self._label.setText('<br />'.join(text) if text else '')

  def typingFailed(self, txt):
    self.updateLabel(txt)

  def typingDone(self, run):
    self._prog_layout.cycle()

    # Various sanity tests.
    if self._current_lesson is None:
      log.error("typing done with no lesson started?")
      return

    med_char = run.median_timing

    if run.per_sec is None or run.visc is None or not med_char:
      return self.typingFailed("Invalid run? (no stats found)")
    if run.per_sec < 1e-6:
      log.error("run seems to be ~0.0 duration: %s", run)
      return self.typingFailed("Invalid run? (~0 duration)")

    if self._focus_drill:
      if not self._emit_focus_lesson(self._focus_drill):
        self.updateLabel('Could not rebuild focus drill for those targets.')
      return

    now = time()
    textid, srcid, _ = self._current_lesson
    wpm, visc, acc = run.result(accuracy=True)
    secs_per_char = 1.0 / run.per_sec

    self.DB.execute('''
    insert into result
    (w, text_id, source, wpm, accuracy, viscosity)
    values (?,?,?, ?,?,?)
    ''', (now, textid, srcid,
          wpm, acc, visc))

    # Update last view
    if self._settings.get("show_last"):
      v2 = self.DB.fetchone("""select agg_median(wpm),agg_median(acc) from
        (select wpm,100.0*accuracy as acc from result order by w desc limit %d)""" % self._settings.get('def_group_by'), (0.0, 100.0))
      self.updateLabel("Last: %.1fwpm (%.1f%%), last 10 average: %.1fwpm (%.1f%%)" % ((wpm, 100.0*acc) + v2))

    self.DB.commit()
    # type (0: char, 1: trigram, 2: word)

    vals = collect_run_stat_rows(run, med_char, now, srcid)

    is_lesson = self.DB.fetchone("select discount from source where rowid=?", (None,), (srcid, ))[0]
    write_stats = self._mode not in (MODE_WEAKSPOT,) and (not is_lesson or self._settings.get('use_lesson_stats'))

    if self._mode == MODE_WEAKSPOT:
      ws_src = self.DB.getSource('<Weakspot>', lesson=1)
      drill_vals = [(t, vis, w, 0, m, tp, data, ws_src) for t, vis, w, _c, m, tp, data, _s in vals]
      self.DB.executemany_('''
      insert into statistic
      (time,viscosity,w,count,mistakes,type,data,source)
      values (?,?,?,?,?,?,?,?)
      ''', drill_vals)
    elif write_stats:
      self.DB.executemany_('''
      insert into statistic
      (time,viscosity,w,count,mistakes,type,data,source)
      values (?,?,?,?,?,?,?,?)
      ''', vals)

      mistakes = Counter((c.char, e) for c in run if c.mistakes > 0 for e in c.errors)
      self.DB.executemany_('''
      insert into mistake
      (w,target,mistake,count)
      values (?,?,?,?)
      ''', [(now, k[0], k[1], v) for k, v in mistakes.items()])

    self.DB.commit()
    self.statsChanged.emit()
    self._refreshHeatmap()

    review_words = [x for x in vals if x[5] == 2] if not is_lesson else []
    action = lesson_completion_action(
      self._mode, bool(is_lesson), self._settings.get('auto_review'), bool(review_words),
      focus_drill=bool(self._focus_drill))

    if self._mode == MODE_BOOK and self._book_meta is not None:
      m = self._book_meta
      srcid = self._current_lesson[1]
      if self._doc.advance_book_chunk():
        self._book.on_chunk_completed(srcid, m['chapter_index'], m['chunk_index'], now)
        m = dict(m, chunk_index=m['chunk_index'] + 1)
        self._book_meta = m
        active = m['chunks'][m['chunk_index']]
        tid = lesson_text_id(srcid, m['chapter_index'], m['chunk_index'])
        self._current_lesson = (tid, srcid, active)
        self._update_book_footer(m)
        self._prog_layout.setCurrentIndex(0)
        self._prog.setValue(0)
        self._prog.setMaximum(len(active))
        self._schedule_typing_center()
        self._refreshHeatmap()
        return
      self._book.on_chunk_completed(srcid, m['chapter_index'], m['chunk_index'], now)

    if action == 'focus_repeat':
      self.setText(self._current_lesson)
    elif action == 'book_next':
      self._book.request_lesson(advance_chapter=False)
    elif action == 'weakspot_next':
      self._weakspot.invalidate_cache()
      self._weakspot.request_next_lesson(force=True)
    elif action == 'review':
      review_words.sort(key=lambda x: (x[4], x[0]), reverse=True)
      u = sum(x[4] != 0 for x in review_words)
      u += (len(review_words) - u) // 4
      self.wantReview.emit([x[6] for x in review_words[:u]])
    else:
      self.wantText.emit()

