from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from typing_program.settings import *
from typing_program.layout import FBoxLayout
from typing_program.fwidgets import FStackedWidget
from typing_program.timingtuple import RunStats, collect_focus_drill_stat_rows, collect_run_stat_rows, IDLE_THRESHOLD
from typing_program.WeakSpot import WeakSpotLessonBuilder
from typing_program.WeakSpotLessons import (
  build_focus_lesson, build_trigram_gibberish_lesson, fetch_weak_trigram_targets,
)
from typing_program.Config import Settings
from typing_program.book_mode import (
  BookLessonBuilder, MODE_BOOK, format_book_progress, lesson_text_id,
  apply_cold_start_practice_mode,
  practice_mode_from_settings, practice_mode_to_settings, ensure_practice_mode_migrated,
  MODE_IMPROVE, MODE_CORPUS,
)
from typing_program.improve_mode import (
  IMPROVE_SUBMODE_LABELS, IMPROVE_SUBMODE_NORMAL, IMPROVE_SUBMODE_TRIGRAMS,
  clamp_improve_submode, fetch_improve_submode_targets, next_improve_submode,
)
from typing_program.lesson_placeholders import (
  BOOK_EMPTY_LABEL, CORPUS_EMPTY_LABEL, IMPROVE_EMPTY_LABEL, IMPROVE_SUBMODE_EMPTY_LABEL,
)
from typing_program.stats_query import (
  ALL_TIME_HIST, STAT_TYPE_WORD, analysis_min_count, fetch_word_counted_totals,
  fetch_word_perfect_baselines,
)
from typing_program.speed_heatmap import book_return_role
from typing_program.read_ahead import (
  hidden_char_indices, hidden_word_indices, word_index_at,
  READ_AHEAD_OFF, document_read_ahead_mode, READ_AHEAD_LEVEL_LABELS,
)
from typing_program.block_bkspc import allows_backspace
from typing_program.idle_cursor import MOUSE_CURSOR_IDLE_MS
from typing_program.keyboard_nav import cycle_practice_mode
from typing_program.follow_mode import (
  FOLLOW_CURSOR_COLOR, MAX_FOLLOW_WPM, MIN_FOLLOW_WPM,
  clamp_follow_wpm, follow_active, follow_footer_state, follow_index,
  follow_outcome_html, follow_race_result, follow_reached_end, parse_follow_wpm,
)

from typing_program.Data import Statistic
from typing_program.speed_heatmap import (
  MODE_LABELS, char_heatmap_colors, fetch_speed_stats, make_heatmap_legend, mode_stat_type,
  PROGRESS_GREEN, PROGRESS_ORANGE,
)
from typing_program.word_progress import (
  analyze_run_progress, format_progress_html, improved_word_spans, lesson_words,
  new_word_spans, progress_badges_for_run, word_perfect_rate_improves,
  word_spans, word_wpm_from_slice,
)
from typing_program.typing_sounds import TypingSoundPlayer
from collections import defaultdict, Counter

from time import time
from typing_program import timer
import logging as log
# log.root.setLevel(log.INFO)


RETURN_CHAR = '⏎' # '↵'
PARA_SEP = '\u2029'
LINE_SEP = '\u2028'

# Lesson text backgrounds only for error highlighting; untyped/correct/inactive stay clear.
_NO_FILL_STYLE_ATTRS = frozenset({'untyped', 'correct', 'inactive'})

MODE_NORMAL = MODE_CORPUS
MODE_WEAKSPOT = MODE_IMPROVE
_IMPROVE_BTN_LABEL = 'improve'
_CORPUS_BTN_LABEL = 'corpus'
_GENERATING_BTN_LABEL = 'generating…'
_FOOTER_ITEM_GAP = 8
_BADGE_FONT_PT = 13
# Two-layer greys: outer chrome lighter; lesson canvas a step darker (not near-black).
TYPER_CHROME_COLOR = QColor('#4a4a4a')
TYPER_CANVAS_DEFAULT = QColor('#383838')
# Unselected footer modes — rgb(140, 140, 140).
MODE_BTN_INACTIVE = '#8c8c8c'
MODE_BTN_ACTIVE = '#ffffff'
MODE_BTN_HOVER = '#ffffff'
MODE_BTN_GREYED = '#5a5a5a'


def _footer_zero_margins(w):
  w.setContentsMargins(0, 0, 0, 0)
  if isinstance(w, QLabel):
    w.setMargin(0)


def _footer_btn_style(active=False, greyed=False):
  if greyed:
    color = MODE_BTN_GREYED
    hover = MODE_BTN_GREYED
  else:
    color = MODE_BTN_ACTIVE if active else MODE_BTN_INACTIVE
    hover = MODE_BTN_HOVER
  return (
    'QPushButton { color: %s; border: none; background: transparent; font-size: 11px;'
    ' padding: 0; margin: 0; min-width: 0; min-height: 0; }'
    'QPushButton:hover { color: %s; }' % (color, hover))


def lesson_completion_action(mode, is_lesson, auto_review, has_review_words, focus_drill=False):
  """What to do after a typing session ends."""
  if focus_drill:
    return 'focus_repeat'
  if mode == MODE_BOOK:
    return 'book_next'
  if mode == MODE_IMPROVE:
    return 'improve_next'
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


### WIDGET


class _LessonPauseOverlay(QWidget):
  continueClicked = pyqtSignal()
  restartClicked = pyqtSignal()
  newClicked = pyqtSignal()

  _BTN_STYLE = (
    'QPushButton { color: #ffffff; background: #444444; border: 1px solid #666666;'
    ' min-width: 120px; padding: 8px 20px; font-size: 13px; }'
    'QPushButton:hover { background: #555555; }')
  _BTN_STYLE_SELECTED = (
    'QPushButton { color: #ffffff; background: #555555; border: 2px solid #aaaaaa;'
    ' min-width: 120px; padding: 8px 20px; font-size: 13px; }'
    'QPushButton:hover { background: #666666; }')

  def __init__(self, parent):
    super().__init__(parent)
    self.setAttribute(Qt.WA_StyledBackground, True)
    self.setStyleSheet('background-color: rgba(0, 0, 0, 0.55);')
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addStretch(1)
    row = QHBoxLayout()
    row.addStretch(1)
    btns = QVBoxLayout()
    btns.setSpacing(10)
    self._btn_continue = QPushButton('Continue', flat=False)
    self._btn_new = QPushButton('New', flat=False)
    self._btn_restart = QPushButton('Restart', flat=False)
    self._buttons = (self._btn_continue, self._btn_new, self._btn_restart)
    self._selected = 0
    for b in self._buttons:
      b.setFocusPolicy(Qt.NoFocus)
      b.setCursor(Qt.PointingHandCursor)
      btns.addWidget(b, 0, Qt.AlignHCenter)
    row.addLayout(btns)
    row.addStretch(1)
    lay.addLayout(row)
    lay.addStretch(1)
    self._btn_continue.clicked.connect(self.continueClicked.emit)
    self._btn_new.clicked.connect(self.newClicked.emit)
    self._btn_restart.clicked.connect(self.restartClicked.emit)
    self._update_selection()
    self.hide()

  def selected_index(self):
    return self._selected

  def reset_selection(self):
    self._selected = 0
    self._update_selection()

  def _update_selection(self):
    for i, b in enumerate(self._buttons):
      b.setStyleSheet(self._BTN_STYLE_SELECTED if i == self._selected else self._BTN_STYLE)

  def _move_selection(self, delta):
    self._selected = (self._selected + delta) % len(self._buttons)
    self._update_selection()

  def handle_key(self, evt):
    key = evt.key()
    if key in (Qt.Key_Down, Qt.Key_Right):
      self._move_selection(1)
      return True
    if key in (Qt.Key_Up, Qt.Key_Left):
      self._move_selection(-1)
      return True
    if key in (Qt.Key_Return, Qt.Key_Enter):
      self._buttons[self._selected].click()
      return True
    return False

  def showEvent(self, evt):
    self.reset_selection()
    return super().showEvent(evt)


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
    self._pause_overlay = None
    self._pin_typing_center = False
    self._on_awaiting_enter = None
    self._on_tab_nav = None  # optional callback: Tab → cycle improve submode
    self._follow_match_index = None  # None = hide follow caret
    self._sounds = TypingSoundPlayer()
    # settings('lenient_mode').bind_value(self.setLenientMode)
    # settings('require_space').bind_value(self.setRequireSpace)
    settings('overwrite_mode').bind_value(self.setOverwriteMode)
    settings('typing_sound').bind_change(self._reload_sounds)
    settings('typing_error_sound').bind_change(self._reload_sounds)
    settings('typing_sound_volume').bind_change(self._reload_sounds)
    self._reload_sounds()
    configure_transparent_typer(self)
    settings('background_color').bind_value(lambda v: configure_transparent_typer(self))

    # Blank the mouse pointer after a couple seconds still; show it on move.
    self.setMouseTracking(True)
    self.viewport().setMouseTracking(True)
    self._mouse_cursor_timer = QTimer(self)
    self._mouse_cursor_timer.setSingleShot(True)
    self._mouse_cursor_timer.setInterval(MOUSE_CURSOR_IDLE_MS)
    self._mouse_cursor_timer.timeout.connect(self._hide_idle_mouse_cursor)
    self._mouse_cursor_timer.start()

  def _show_mouse_cursor(self):
    self.unsetCursor()
    self.viewport().unsetCursor()
    self._mouse_cursor_timer.start()

  def _hide_idle_mouse_cursor(self):
    self.setCursor(Qt.BlankCursor)
    self.viewport().setCursor(Qt.BlankCursor)

  def mouseMoveEvent(self, e):
    self._show_mouse_cursor()
    super().mouseMoveEvent(e)

  def enterEvent(self, e):
    self._show_mouse_cursor()
    super().enterEvent(e)

  def leaveEvent(self, e):
    self._mouse_cursor_timer.stop()
    self.unsetCursor()
    self.viewport().unsetCursor()
    super().leaveEvent(e)

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

  def set_awaiting_enter(self, cb):
    self._on_awaiting_enter = cb
    self.viewport().update()

  def _badge_rect(self, start_mi, end_mi):
    lesson = self._lesson
    lo = lesson._display_span(start_mi)[0]
    hi = lesson._display_span(end_mi - 1)[0] + lesson._display_span(end_mi - 1)[1]
    r = self.cursorRect(Cursor(lesson, lo))
    r = r.united(self.cursorRect(Cursor(lesson, max(lo, hi - 1))))
    return r

  def set_follow_cursor_index(self, match_index):
    """Draw the follow-mode race caret at match_index, or hide when None."""
    if self._follow_match_index == match_index:
      return
    self._follow_match_index = match_index
    self.viewport().update()

  def paintEvent(self, evt):
    super().paintEvent(evt)
    if not self._lesson:
      return
    p = QPainter(self.viewport())
    p.setRenderHint(QPainter.Antialiasing)
    if self._follow_match_index is not None and self._lesson._match_text is not None:
      self._paint_follow_caret(p, self._follow_match_index)
    badges = self._lesson.progress_badges()
    if badges:
      f = QFont()
      f.setPointSize(_BADGE_FONT_PT)
      p.setFont(f)
      fm = QFontMetrics(f)
      for start, end, gain in badges:
        r = self._badge_rect(start, end)
        pad = 2
        box_h = max(r.height() + pad * 2, fm.height() + 4)
        box = QRect(r.left() - pad, r.top() - pad, r.width() + pad * 2, box_h)
        p.fillRect(box, QColor(80, 80, 80, 120))
        p.setPen(QColor('#f0f0f0'))
        full_lbl = '+%dwpm' % gain
        short_lbl = '+%d' % gain
        lbl = full_lbl if fm.horizontalAdvance(full_lbl) + 4 <= box.width() else short_lbl
        p.drawText(box, Qt.AlignCenter, lbl)
    p.end()

  def _paint_follow_caret(self, painter, match_index):
    lesson = self._lesson
    n = len(lesson._match_text or '')
    if n <= 0:
      return
    if match_index >= n:
      di, w = lesson._display_span(n - 1)
      pos = di + w
    else:
      pos = lesson._display_span(match_index)[0]
    r = self.cursorRect(Cursor(lesson, position=pos))
    w = max(2, self.cursorWidth())
    painter.fillRect(QRect(r.left(), r.top(), w, r.height()), QColor(FOLLOW_CURSOR_COLOR))

  def resizeEvent(self, evt):
    super().resizeEvent(evt)
    if self._pin_typing_center:
      self.center_typing_vertically()

  def setLesson(self, lesson):
    if lesson == self._lesson:
      if getattr(lesson, '_match_text', None):
        self._follow_cursor(lesson.cursor)
      self.updateStatus()
      return
    
    if self._lesson is not None:
      self._lesson.sig_position.disconnect(self._follow_cursor)
      self._lesson.ready.disconnect(self.updateStatus)
      self._lesson.completed.disconnect(self.updateStatus)
      self._lesson.progress_badges_changed.disconnect(self._repaint_badges)
      self._lesson.key_typed.disconnect(self._on_key_typed)

    if self.document() != lesson:
      w = self.cursorWidth() # Layout thingamajig resets cursor width.
      self.setDocument(lesson)
      self.setCursorWidth(w)
    if getattr(lesson, '_match_text', None):
      self._follow_cursor(lesson.cursor)
    self.updateStatus()

    lesson.sig_position.connect(self._follow_cursor)
    lesson.ready.connect(self.updateStatus)
    lesson.completed.connect(self.updateStatus)
    lesson.progress_badges_changed.connect(self._repaint_badges)
    lesson.key_typed.connect(self._on_key_typed)
    self._lesson = lesson

  def _on_key_typed(self, correct):
    self._sounds.play_keystroke(correct)

  def _reload_sounds(self, *_):
    def _get(k, default):
      try:
        return self._settings[k]
      except (KeyError, ValueError):
        return default
    self._sounds.configure(
      _get('typing_sound', ''), _get('typing_error_sound', ''), _get('typing_sound_volume', 50))

  def _repaint_badges(self):
    self.viewport().update()

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
    elif self._lesson.is_ready() or self._lesson.is_running():
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
    # Tab cycles improve submode (wired via parent TyperWindow callback).
    # Handle even with no lesson so navigation always works on the typer canvas.
    if evt.key() == Qt.Key_Tab:
      if self._on_tab_nav is not None:
        self._on_tab_nav()
      evt.accept()
      return

    if not self._lesson:
      evt.ignore()
      return

    if self._lesson.is_finished() and self._on_awaiting_enter:
      if evt.key() in (Qt.Key_Enter, Qt.Key_Return):
        self._on_awaiting_enter()
        evt.accept()
        return

    if evt.key() == Qt.Key_Escape:
      if self._lesson.is_paused() or self._lesson.is_ready() or self._lesson.is_running():
        self._toggle_pause()
      evt.accept()
      return

    if self._lesson.is_paused():
      if self._pause_overlay and self._pause_overlay.handle_key(evt):
        evt.accept()
        return
      evt.ignore()
      return

    if evt.key() == Qt.Key_Backspace or evt.key() == Qt.Key_Back:
      by_word = bool(evt.modifiers() & (Qt.ControlModifier | Qt.MetaModifier | Qt.AltModifier))
      if not allows_backspace(self._settings['word_delete_enabled'], by_word):
        evt.accept()
        return
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
    if not allows_backspace(self._settings['word_delete_enabled'], word):
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
    # Required for background-color in stylesheets on QWidget (macOS/Qt otherwise
    # ignores the fill once the widget is reparented into the tab pane).
    self.setAttribute(Qt.WA_StyledBackground, True)

    app = QApplication.instance()
    self._settings = app.settings
    self.S = app.settings.typer_settings
    self.DB = app.DB

    self._current_lesson = None
    self._read_ahead_on = False
    self._read_ahead_level = 0
    self._mode = MODE_IMPROVE
    self._improve_submode = 0
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._focus_drill_from_pa = False
    self._awaiting_next = False
    self._pending_action = None
    self._pending_now = None
    self._pending_review_words = None
    self._weakspot = WeakSpotLessonBuilder(self)
    self._weakspot.lessonReady.connect(self._on_weakspot_lesson)
    self._weakspot.busyChanged.connect(self._on_weakspot_busy)
    self._book = BookLessonBuilder(self.DB, self)
    self._book.lessonReady.connect(self._on_book_lesson)
    self._book.progressChanged.connect(self._on_book_progress)
    self._book_meta = None
    self._typer = TyperWidget(self.S)
    self._typer._on_tab_nav = self.cycle_improve_submode
    hack = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Ignored)
    self._label = QLabel(wordWrap=True, sizePolicy=hack)
    self._prog = QProgressBar()
    self._prog.setTextVisible(False)
    self._prog.setValue(0)
    self._progw = FStackedWidget([QLabel('Type like the wind!'), self._prog])
    self._prog_layout = FStackedWidget([self._label, self._progw])

    self.S('show_progress').bind_value(self._on_show_progress_pref, call=True)
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

    # Progress strip is shown before the first keystroke (empty bar), not only after start.
    doc.started.connect(self._show_progress_strip)
    doc.started.connect(self._on_lesson_started)
    doc.progress.connect(self._prog.setValue)
    doc.ready.connect(self.typingReady)
    doc.ready.connect(self._on_lesson_ready)
    doc.completed.connect(self.typingDone)
    doc.follow_lost.connect(self.typingFollowLost)
    doc.paused.connect(self._on_lesson_paused)
    doc.resumed.connect(self._on_lesson_resumed)

    self._typer.setLesson(doc)
    self._doc = doc

    # Canvas = darker lesson page (background_color), same rect as the pause overlay.
    # Outer TyperWindow stays chrome gray. TyperWidget is transparent on the canvas.
    self._pause_overlay = _LessonPauseOverlay(None)
    self._pause_overlay.continueClicked.connect(self._doc.resume)
    self._pause_overlay.restartClicked.connect(self._restart_lesson)
    self._pause_overlay.newClicked.connect(self._new_lesson)
    self._canvas = QWidget()
    self._canvas.setObjectName('TyperCanvas')
    self._canvas.setAttribute(Qt.WA_StyledBackground, True)
    self._canvas.setLayout(FBoxLayout([self._typer]))
    self._pause_overlay.setParent(self._canvas)
    self._typer._pause_overlay = self._pause_overlay
    self._canvas.installEventFilter(self)

    self._source_lbl = QLabel(wordWrap=True)
    self._source_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    self._source_lbl.installEventFilter(self)
    self._book_prog_text = ''

    self._mode_btn_style = (
      'QPushButton { color: %s; border: none; background: transparent; font-size: 11px;'
      ' padding: 0; margin: 0; min-width: 0; min-height: 0; }'
      'QPushButton:hover { color: %s; }'
      'QPushButton[activeMode="true"] { color: %s; }' % (
        MODE_BTN_INACTIVE, MODE_BTN_HOVER, MODE_BTN_ACTIVE))

    self._btn_improve = QPushButton(_IMPROVE_BTN_LABEL, flat=True)
    self._btn_book = QPushButton('book', flat=True)
    self._btn_corpus = QPushButton(_CORPUS_BTN_LABEL, flat=True)
    self._btn_read_ahead = QPushButton('read ahead', flat=True)
    self._btn_read_ahead_level = QPushButton('normal', flat=True)
    self._btn_block_bkspc = QPushButton('Block ⌫', flat=True)
    self._btn_improve_level = QPushButton('normal', flat=True)
    self._btn_heatmap = QPushButton('heatmap', flat=True)
    self._btn_heatmap.clicked.connect(self._toggleHeatmap)
    self._btn_heatmap_kind = QPushButton(flat=True)
    self._btn_heatmap_kind.clicked.connect(self._cycleHeatmapMode)
    self._btn_follow = QPushButton('follow', flat=True)
    self._btn_follow.clicked.connect(self._toggleFollow)
    self._follow_wpm_panel = self._make_follow_wpm_panel()
    for b in (self._btn_improve, self._btn_corpus, self._btn_book, self._btn_read_ahead,
              self._btn_read_ahead_level, self._btn_block_bkspc, self._btn_improve_level):
      b.setCursor(Qt.PointingHandCursor)
      b.setFocusPolicy(Qt.NoFocus)
      b.setStyleSheet(self._mode_btn_style)
      b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
      _footer_zero_margins(b)
    for b in (self._btn_heatmap, self._btn_heatmap_kind, self._btn_follow):
      b.setCursor(Qt.PointingHandCursor)
      b.setFocusPolicy(Qt.NoFocus)
      b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
      _footer_zero_margins(b)
    self._btn_improve.clicked.connect(self._on_improve_click)
    self._btn_corpus.clicked.connect(self._on_corpus_click)
    self._btn_book.clicked.connect(lambda: self.set_practice_mode(MODE_BOOK))
    self._btn_read_ahead.clicked.connect(self.toggle_read_ahead)
    self._btn_read_ahead_level.clicked.connect(self.cycle_read_ahead_level)
    self._btn_block_bkspc.clicked.connect(self.toggle_block_bkspc)
    self._btn_improve_level.clicked.connect(self.cycle_improve_submode)
    self._weakspot_generating = False

    self._heatmap_legend = make_heatmap_legend()
    self._heatmap_panel = QWidget()
    hp_lay = QHBoxLayout(self._heatmap_panel)
    hp_lay.setContentsMargins(0, 0, 0, 0)
    hp_lay.setSpacing(_FOOTER_ITEM_GAP)
    hp_lay.addWidget(self._btn_heatmap_kind, 0)
    hp_lay.addWidget(self._heatmap_legend, 0)

    mode_row = QWidget()
    mode_lay = QHBoxLayout(mode_row)
    mode_lay.setContentsMargins(0, 0, 0, 0)
    mode_lay.setSpacing(_FOOTER_ITEM_GAP)
    self._heatmap_panel.setVisible(False)
    self._follow_wpm_panel.setVisible(False)
    # Footer: improve · corpus · book · read ahead · Block ⌫ · heatmap · follow
    for w in (self._btn_improve, self._btn_improve_level, self._btn_corpus, self._btn_book,
              self._btn_read_ahead, self._btn_read_ahead_level, self._btn_block_bkspc,
              self._btn_heatmap, self._heatmap_panel, self._btn_follow, self._follow_wpm_panel):
      mode_lay.addWidget(w)
    mode_lay.addStretch(1)
    mode_lay.addWidget(self._source_lbl)

    self._follow_timer = QTimer(self)
    self._follow_timer.setInterval(50)
    self._follow_timer.timeout.connect(self._on_follow_tick)
    self._follow_racing = False
    self._follow_race_outcome = None
    self._follow_clock_started = None
    self._follow_clock_pause_total = 0.0
    self._follow_clock_paused_at = None

    self.S('speed_heatmap').bind_value(self._onHeatmapSetting, call=True)
    self.S('speed_heatmap_mode').bind_value(self._onHeatmapSetting, call=True)
    self.S('word_delete_enabled').bind_value(self._onBlockBkspcSetting, call=True)
    self.S('follow_mode').bind_value(self._onFollowSetting, call=True)
    self.S('follow_wpm').bind_value(self._onFollowWpmSetting, call=True)

    self.setLayout(FBoxLayout([
      (self._prog_layout, 0),
      (self._canvas, 100),
      (mode_row, 0),
      ]))

    self.S('background_color').bind_value(self._applyBackground, call=True)
    self.statsChanged.connect(self._weakspot.on_stats_changed)
    ensure_practice_mode_migrated(self._settings)
    # Cold start always Typer at improve · normal (ignore last session's mode).
    apply_cold_start_practice_mode(self._settings, self.S)
    self.S('improve_submode').bind_value(self._onImproveSubmodeSetting, call=True)
    self._apply_practice_mode_from_settings()
    self._apply_read_ahead_from_settings()
    self._refresh_follow_footer()
    self._install_keyboard_nav()

  def _install_keyboard_nav(self):
    """Cmd/Ctrl+Opt/Alt+←→ cycle practice mode. Tab cycles submode (TyperWidget).

    QKeySequence 'Ctrl' is Command on macOS, 'Alt' is Option. Tab is not a
    QShortcut — QTextEdit would otherwise swallow it or double-fire.
    """
    self._sc_submode = None  # Tab via TyperWidget._on_tab_nav → cycle_improve_submode
    self._sc_mode_next = QShortcut(QKeySequence('Ctrl+Alt+Right'), self)
    self._sc_mode_next.setContext(Qt.WidgetWithChildrenShortcut)
    self._sc_mode_next.activated.connect(lambda: self._cycle_practice_mode(1))
    self._sc_mode_prev = QShortcut(QKeySequence('Ctrl+Alt+Left'), self)
    self._sc_mode_prev.setContext(Qt.WidgetWithChildrenShortcut)
    self._sc_mode_prev.activated.connect(lambda: self._cycle_practice_mode(-1))

  def _cycle_practice_mode(self, delta):
    self.set_practice_mode(cycle_practice_mode(self._mode, delta))

  def _polish_mode_btn(self, btn):
    btn.style().unpolish(btn)
    btn.style().polish(btn)

  def _refresh_book_btn(self):
    if self._mode == MODE_BOOK and self._book_prog_text:
      self._btn_book.setText('book · ' + self._book_prog_text)
    else:
      self._btn_book.setText('book')

  def _apply_read_ahead_from_settings(self):
    enabled = bool(self._settings.get('read_ahead_enabled'))
    level = self.S['read_ahead_level']
    self._set_read_ahead_ui(enabled, level, refresh_doc=True)

  def _onImproveSubmodeSetting(self, level):
    self._set_improve_submode_ui(level)

  def cycle_improve_submode(self):
    if self._mode != MODE_IMPROVE:
      return
    level = next_improve_submode(
      self._improve_submode, self.DB, ALL_TIME_HIST, Settings.get('analysis_count'))
    self._focus_drill_from_pa = False
    self.S('improve_submode').set(level)
    self._load_improve_lesson()

  def _set_improve_submode_ui(self, level):
    self._improve_submode = level
    visible = self._mode == MODE_IMPROVE
    self._btn_improve_level.setText(IMPROVE_SUBMODE_LABELS[level])
    self._btn_improve_level.setVisible(visible)
    if visible:
      self._btn_improve_level.setStyleSheet(self._mode_btn_style)
      self._btn_improve_level.setProperty('activeMode', True)
      self._polish_mode_btn(self._btn_improve_level)

  def _load_improve_lesson(self):
    # Drop empty oblivion (and any other unavailable saved index) before loading.
    submode = clamp_improve_submode(
      self._improve_submode, self.DB, ALL_TIME_HIST, Settings.get('analysis_count'))
    if submode != self._improve_submode:
      self._improve_submode = submode
      self._set_improve_submode_ui(submode)
      self.S('improve_submode').set(submode)
    if submode == IMPROVE_SUBMODE_NORMAL:
      self._focus_drill = None
      self._focus_drill_wpm = {}
      self._focus_drill_from_pa = False
      self._weakspot.request_next_lesson(force=True)
      return
    if submode == IMPROVE_SUBMODE_TRIGRAMS:
      self._focus_drill = None
      self._focus_drill_wpm = {}
      self._focus_drill_from_pa = False
      targets = fetch_weak_trigram_targets(
        self.DB, ALL_TIME_HIST, Settings.get('analysis_count'), Settings.get('analysis_many'))
      if not targets:
        self._show_idle_placeholder(IMPROVE_SUBMODE_EMPTY_LABEL)
        return
      lesson = build_trigram_gibberish_lesson(
        targets, min_chars=Settings.get('min_chars'), max_chars=Settings.get('max_chars'))
      if not lesson:
        self._show_idle_placeholder(IMPROVE_SUBMODE_EMPTY_LABEL)
        return
      self._set_improve_footer_busy(False)
      self.needWeakspotLesson.emit(lesson)
      return
    targets = fetch_improve_submode_targets(
      self.DB, submode, ALL_TIME_HIST, Settings.get('analysis_count'))
    if not targets:
      self._show_idle_placeholder(IMPROVE_SUBMODE_EMPTY_LABEL)
      return
    self._start_focus_drill(targets, from_pa=False)

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

  def toggle_block_bkspc(self):
    self.S('word_delete_enabled').set(not self.S('word_delete_enabled').get())

  def _onBlockBkspcSetting(self, *_):
    on = bool(self.S('word_delete_enabled').get())
    self._btn_block_bkspc.setStyleSheet(self._mode_btn_style)
    self._btn_block_bkspc.setProperty('activeMode', on)
    self._polish_mode_btn(self._btn_block_bkspc)

  def updateFont(self):
    self._doc.setDefaultFont(self._settings.getFont('typer_font'))

  def _toggleHeatmap(self):
    self.S('speed_heatmap').set(not self.S('speed_heatmap').get())

  def _cycleHeatmapMode(self):
    mode = (self.S('speed_heatmap_mode').get() + 1) % len(MODE_LABELS)
    self.S('speed_heatmap_mode').set(mode)

  def _style_heatmap_footer_btn(self, btn, on):
    btn.setStyleSheet(_footer_btn_style(on))

  def _onHeatmapSetting(self, *_):
    on = bool(self.S('speed_heatmap').get())
    mode = int(self.S('speed_heatmap_mode').get())
    self._style_heatmap_footer_btn(self._btn_heatmap, on)
    self._heatmap_panel.setVisible(on)
    self._btn_heatmap_kind.setText(MODE_LABELS[mode])
    self._style_heatmap_footer_btn(self._btn_heatmap_kind, on)
    self._refreshHeatmap()

  def _toggleFollow(self):
    if not follow_footer_state(True, self._mode)['eligible']:
      return
    self.S('follow_mode').set(not self.S('follow_mode').get())

  def _make_follow_wpm_panel(self):
    """Minimal − N + stepper matching the footer (no chrome box)."""
    panel = QWidget()
    lay = QHBoxLayout(panel)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    btn_style = _footer_btn_style(active=True)
    self._follow_wpm_down = QPushButton('−', flat=True)
    self._follow_wpm_up = QPushButton('+', flat=True)
    for b in (self._follow_wpm_down, self._follow_wpm_up):
      b.setCursor(Qt.PointingHandCursor)
      b.setFocusPolicy(Qt.NoFocus)
      b.setStyleSheet(btn_style)
      b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
      b.setFixedWidth(14)
      _footer_zero_margins(b)
    self._follow_wpm_edit = QLineEdit()
    self._follow_wpm_edit.setAlignment(Qt.AlignCenter)
    self._follow_wpm_edit.setFixedWidth(28)
    self._follow_wpm_edit.setMaxLength(3)
    self._follow_wpm_edit.setFocusPolicy(Qt.ClickFocus)
    self._follow_wpm_edit.setToolTip('Follow caret speed (WPM)')
    self._follow_wpm_edit.setStyleSheet(
      'QLineEdit { color: %s; background: transparent; border: none;'
      ' font-size: 11px; padding: 0; margin: 0; selection-background-color: #555; }'
      % MODE_BTN_ACTIVE)
    self._follow_wpm_edit.setText(str(clamp_follow_wpm(self.S('follow_wpm').get())))
    self._follow_wpm_edit.setValidator(QIntValidator(MIN_FOLLOW_WPM, MAX_FOLLOW_WPM, self))
    self._follow_wpm_down.clicked.connect(lambda: self._nudge_follow_wpm(-1))
    self._follow_wpm_up.clicked.connect(lambda: self._nudge_follow_wpm(1))
    self._follow_wpm_edit.textChanged.connect(self._on_follow_wpm_text)
    self._follow_wpm_edit.installEventFilter(self)
    lay.addWidget(self._follow_wpm_down, 0)
    lay.addWidget(self._follow_wpm_edit, 0)
    lay.addWidget(self._follow_wpm_up, 0)
    return panel

  def _nudge_follow_wpm(self, delta):
    wpm = clamp_follow_wpm(int(self.S('follow_wpm').get()) + delta)
    self.S('follow_wpm').set(wpm)
    self._sync_follow_wpm_edit(wpm)

  def _sync_follow_wpm_edit(self, wpm):
    text = str(clamp_follow_wpm(wpm))
    if self._follow_wpm_edit.text() != text:
      self._follow_wpm_edit.blockSignals(True)
      self._follow_wpm_edit.setText(text)
      self._follow_wpm_edit.blockSignals(False)

  def _on_follow_wpm_text(self, text):
    # Live: whatever number is in the box is the speed (empty → keep last until valid).
    s = (text or '').strip()
    if not s:
      return
    wpm = parse_follow_wpm(s, default=int(self.S('follow_wpm').get()))
    if wpm != int(self.S('follow_wpm').get()):
      self.S('follow_wpm').set(wpm)

  def _blur_follow_wpm(self):
    """Commit the box and return focus to the lesson canvas."""
    wpm = parse_follow_wpm(self._follow_wpm_edit.text(), default=int(self.S('follow_wpm').get()))
    self.S('follow_wpm').set(wpm)
    self._sync_follow_wpm_edit(wpm)
    self._typer.setFocus()

  def _onFollowSetting(self, *_):
    self._refresh_follow_footer()

  def _onFollowWpmSetting(self, *_):
    self._sync_follow_wpm_edit(self.S('follow_wpm').get())
    # Live WPM: next tick uses the new value; no Enter required.
    if self._follow_racing:
      self._on_follow_tick()

  def _refresh_follow_footer(self):
    enabled = bool(self.S('follow_mode').get())
    st = follow_footer_state(enabled, self._mode)
    self._btn_follow.setEnabled(st['btn_enabled'])
    self._btn_follow.setCursor(Qt.PointingHandCursor if st['btn_enabled'] else Qt.ArrowCursor)
    self._btn_follow.setStyleSheet(
      _footer_btn_style(active=st['btn_active_style'], greyed=st['btn_greyed']))
    self._follow_wpm_panel.setVisible(st['wpm_visible'])
    if st['active']:
      self._arm_follow_race()
    else:
      self._stop_follow_race(clear_caret=True)

  def _follow_is_active(self):
    return follow_active(self.S('follow_mode').get(), self._mode)

  def _arm_follow_race(self):
    """Show the follow caret at the start; timer runs once the lesson starts."""
    if not self._follow_is_active() or not self._doc._match_text:
      self._typer.set_follow_cursor_index(None)
      return
    self._follow_race_outcome = None
    self._typer.set_follow_cursor_index(0)
    if self._doc.is_running() and not self._doc.is_paused():
      self._start_follow_clock()
      self._follow_racing = True
      if not self._follow_timer.isActive():
        self._follow_timer.start()
      self._on_follow_tick()
    else:
      self._follow_racing = False
      self._follow_timer.stop()
      self._reset_follow_clock()

  def _reset_follow_clock(self):
    self._follow_clock_started = None
    self._follow_clock_pause_total = 0.0
    self._follow_clock_paused_at = None

  def _start_follow_clock(self):
    """Own clock — RunStats.started is often unset on cold start until the end."""
    if self._follow_clock_started is None:
      self._follow_clock_started = timer()
      self._follow_clock_pause_total = 0.0
      self._follow_clock_paused_at = None

  def _pause_follow_clock(self):
    if self._follow_clock_started is not None and self._follow_clock_paused_at is None:
      self._follow_clock_paused_at = timer()

  def _resume_follow_clock(self):
    if self._follow_clock_paused_at is not None:
      self._follow_clock_pause_total += timer() - self._follow_clock_paused_at
      self._follow_clock_paused_at = None

  def _follow_elapsed(self):
    if self._follow_clock_started is None:
      return 0.0
    t = self._follow_clock_paused_at if self._follow_clock_paused_at is not None else timer()
    return max(0.0, t - self._follow_clock_started - self._follow_clock_pause_total)

  def _stop_follow_race(self, clear_caret=False):
    self._follow_racing = False
    self._follow_timer.stop()
    self._reset_follow_clock()
    if clear_caret:
      self._typer.set_follow_cursor_index(None)

  def _on_follow_tick(self):
    if not self._follow_racing or not self._follow_is_active():
      self._stop_follow_race(clear_caret=not self._follow_is_active())
      return
    text = self._doc._match_text or ''
    if not self._doc._run or not text:
      return
    if self._doc.is_paused():
      return
    wpm = int(self.S('follow_wpm').get())
    elapsed = self._follow_elapsed()
    idx = follow_index(elapsed, wpm, len(text))
    self._typer.set_follow_cursor_index(idx)
    user_done = bool(self._doc._run.is_complete())
    cursor_done = follow_reached_end(elapsed, wpm, len(text))
    outcome = follow_race_result(user_done, cursor_done)
    if outcome == 'failure':
      self._follow_race_outcome = 'failure'
      self._stop_follow_race(clear_caret=False)
      self._doc.lose_follow_race()
    elif outcome == 'success':
      self._follow_race_outcome = 'success'
      self._stop_follow_race(clear_caret=False)

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

  def _paint_solid_bg(self, widget, selector, color):
    """Solid fill that survives tab reparent on macOS (needs WA_StyledBackground)."""
    qcolor = color if isinstance(color, QColor) else QColor(color)
    name = qcolor.name()
    widget.setAttribute(Qt.WA_StyledBackground, True)
    pal = widget.palette()
    pal.setColor(QPalette.Window, qcolor)
    pal.setColor(QPalette.Base, qcolor)
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)
    widget.setStyleSheet('%s { background-color: %s; }' % (selector, name))
    # Re-assert after setStyleSheet (polish can clear these).
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)

  def _applyBackground(self, color):
    """Two layers — do not collapse them into one color.

    1. TyperWindow (chrome around the lesson): system window gray — footer,
       margins, area outside the pause rectangle.
    2. TyperCanvas (lesson page): user background_color — same rectangle as the
       ESC pause overlay; darker than chrome, lighter than the pause dim.

    The lesson QTextEdit stays transparent on the canvas. Main tab ::pane must
    stay transparent so neither layer is covered.
    """
    if hasattr(color, 'name'):
      page = color
    else:
      page = QColor(color)
    self._paint_solid_bg(self, 'TyperWindow', TYPER_CHROME_COLOR)
    self._paint_solid_bg(self._canvas, 'QWidget#TyperCanvas', page)
    configure_transparent_typer(self._typer)
    self._doc.set_page_background(page)

  def eventFilter(self, obj, evt):
    if obj is self._canvas and evt.type() == QEvent.Resize:
      self._pause_overlay.setGeometry(self._canvas.rect())
    if getattr(self, '_follow_wpm_edit', None) is obj and evt.type() == QEvent.KeyPress:
      if evt.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
        self._blur_follow_wpm()
        return True
    if obj is self._source_lbl and self._mode == MODE_BOOK:
      if evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.LeftButton:
        self._show_book_menu()
        return True
    return super().eventFilter(obj, evt)

  def showEvent(self, evt):
    # Re-apply after tab reparent/style polish so the page fill cannot be lost.
    self._applyBackground(self.S['background_color'])
    self._typer.setFocus()
    if self._typer._pin_typing_center:
      QTimer.singleShot(0, self._typer._center_typing_when_ready)
    return super().showEvent(evt)

  def _on_lesson_started(self):
    self._typer._pin_typing_center = False
    if self._follow_is_active():
      self._start_follow_clock()
      self._follow_racing = True
      self._follow_race_outcome = None
      if not self._follow_timer.isActive():
        self._follow_timer.start()
      self._on_follow_tick()

  def _on_lesson_paused(self):
    self._pause_follow_clock()
    self._pause_overlay.setGeometry(self._canvas.rect())
    self._pause_overlay.show()
    self._pause_overlay.raise_()
    self._typer.updateStatus()

  def _on_lesson_resumed(self):
    self._resume_follow_clock()
    self._pause_overlay.hide()
    self._typer.updateStatus()
    self._typer.setFocus()
    if self._follow_is_active() and self._doc.is_running():
      self._follow_racing = True
      if not self._follow_timer.isActive():
        self._follow_timer.start()

  def _restart_lesson(self):
    self._pause_overlay.hide()
    self._stop_follow_race(clear_caret=False)
    self._doc.reset()
    if self._follow_is_active():
      self._arm_follow_race()
    self._typer.setFocus()

  def _new_lesson(self):
    self._pause_overlay.hide()
    if self._doc.is_paused():
      self._doc.resume()
    self._request_new_lesson()
    self._typer.setFocus()

  def _request_new_lesson(self):
    """Load a fresh exercise for the current practice mode."""
    if self._mode in (MODE_WEAKSPOT, MODE_IMPROVE):
      if self._focus_drill:
        # Auto improve drills re-sample targets; PA drills keep the chosen targets.
        if self._focus_drill_from_pa:
          if not self._emit_focus_lesson(self._focus_drill):
            self.updateLabel('Could not rebuild focus drill for those targets.')
        else:
          self._load_improve_lesson()
        return
      self._load_improve_lesson()
    elif self._mode == MODE_BOOK:
      self._book.invalidate_cache()
      self._book.request_lesson(advance_chapter=False)
    else:
      self._set_improve_footer_busy(False)
      self.wantText.emit()

  def _schedule_typing_center(self):
    self._typer.setTextCursor(self._doc.cursor)
    self._typer._pin_typing_center = True
    QTimer.singleShot(0, self._typer._center_typing_when_ready)

  def _on_show_progress_pref(self, on):
    self._progw.setCurrentIndex(1 if on else 0)
    # Prefer the progress strip over an empty status label when the pref is on.
    if on and not self._awaiting_next and not (self._label.text() or '').strip():
      self._prog_layout.setCurrentIndex(1)

  def _show_progress_strip(self):
    """Top area: empty or live progress bar (or wind text if progress pref is off)."""
    self._prog_layout.setCurrentIndex(1)
    self._progw.setCurrentIndex(1 if self.S['show_progress'] else 0)

  def _show_result_label(self):
    """Top area: post-lesson summary / prompts."""
    self._prog_layout.setCurrentIndex(0)

  def typingReady(self, text):
    self._pause_overlay.hide()
    self._prog.setMaximum(max(1, len(text)))
    self._prog.setValue(0)
    self._show_progress_strip()
    if self._follow_is_active():
      self._arm_follow_race()
    else:
      self._typer.set_follow_cursor_index(None)

  def setDefaultText(self):
    log.error("setDefaultText() NOT IMPLEMENTED")
    print("setDefaultText() NOT IMPLEMENTED")

  def setText(self, txt):
    body = (txt[2] or '').strip()
    if self._mode == MODE_CORPUS and not body:
      self._show_idle_placeholder(CORPUS_EMPTY_LABEL)
      return
    self._current_lesson = txt
    textid, srcid, _ = txt
    self._update_source_label(srcid)
    pre, _, post = self.DB.getTextContext(textid)

    # Only show real surrounding context from the same source. Never insert ugly placeholder labels.
    prologue = (pre[2] + '\n') if pre is not None else ''
    epilogue = ('\n' + post[2]) if post is not None else ''

    self._doc.set_text(txt[2], prologue=prologue, epilogue=epilogue)
    if self._mode == MODE_CORPUS:
      self._schedule_typing_center()
    else:
      self._typer._pin_typing_center = False
    self._refreshHeatmap()
    self._typer.setFocus()
    self._prog.setMaximum(max(1, len(txt[2] or '')))
    self._prog.setValue(0)
    self._show_progress_strip()

  def _update_source_label(self, srcid):
    row = self.DB.fetchone('select name from source where rowid=?', (None,), (srcid,))
    text = format_source_attribution(row[0] if row else '')
    self._source_lbl.setText(text)
    self._source_lbl.setVisible(bool(text) and self._mode == MODE_CORPUS)

  def _update_book_footer(self, meta=None):
    if meta is None:
      meta = self._book_meta or {}
    prog = format_book_progress(
      meta.get('title') or '', meta.get('chunk_index', 0), meta.get('chunk_count', 0))
    self._book_prog_text = prog
    self._refresh_book_btn()
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
      self._book_prog_text = msg
      self._refresh_book_btn()

  def _show_idle_placeholder(self, msg):
    self._pause_overlay.hide()
    self._stop_follow_race(clear_caret=True)
    self._current_lesson = None
    self._book_meta = None
    self._doc.set_idle_message(msg)
    self._source_lbl.clear()
    self._source_lbl.setVisible(False)
    self._typer.setReadOnly(True)
    self._typer._pin_typing_center = False
    self._prog.setValue(0)
    self._prog.setMaximum(1)
    self._show_progress_strip()
    self.updateLabel()

  def _on_book_lesson(self, lesson):
    if self._mode != MODE_BOOK:
      return
    if not lesson:
      self._show_idle_placeholder(BOOK_EMPTY_LABEL)
      return
    tid, srcid, meta = lesson
    body = meta['full_text']
    chunks = meta['chunks']
    if self._settings.get('text_force_ascii'):
      from typing_program.TextManager import force_ascii
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
    self._prog.setMaximum(max(1, len(active)))
    self._show_progress_strip()

  def _apply_practice_mode_from_settings(self):
    mode = practice_mode_from_settings(self._settings.get('practice_mode'))
    self._set_mode_ui(mode, load=False)
    if mode == MODE_IMPROVE:
      self._load_improve_lesson()
    elif mode == MODE_BOOK:
      self._book.invalidate_cache()
      self._book.request_lesson(advance_chapter=False)

  def _on_improve_click(self):
    if self._mode == MODE_IMPROVE and (self._focus_drill or self._improve_submode != IMPROVE_SUBMODE_NORMAL):
      self._exit_focus_drill()
      return
    self.set_practice_mode(MODE_IMPROVE)

  def _on_corpus_click(self):
    if self._mode == MODE_CORPUS:
      self._set_improve_footer_busy(False)
      self.wantText.emit()
      return
    self.set_practice_mode(MODE_CORPUS)

  def _exit_focus_drill(self):
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._focus_drill_from_pa = False
    if self._improve_submode != IMPROVE_SUBMODE_NORMAL:
      self.S('improve_submode').set(IMPROVE_SUBMODE_NORMAL)
    self._weakspot.request_next_lesson(force=True)

  def load_corpus_text(self, v):
    """Open a corpus chunk in corpus mode (from Performance Analysis Find in corpus)."""
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._focus_drill_from_pa = False
    self._settings.set('practice_mode', practice_mode_to_settings(MODE_CORPUS))
    self._set_mode_ui(MODE_CORPUS, load=False)
    self.setText(v)

  def _emit_focus_lesson(self, targets):
    wl = str(Settings.DATA_DIR / 'wordlists' / 'words-20.txt')
    lesson = build_focus_lesson(
      targets, wordlist_path=wl,
      min_chars=Settings.get('focus_min_chars'),
      max_chars=Settings.get('focus_max_chars'))
    if not lesson:
      return False
    self._set_improve_footer_busy(False)
    self.needWeakspotLesson.emit(lesson)
    return True

  def _start_focus_drill(self, targets, from_pa=False):
    self._focus_drill = [(t[0], t[1]) for t in targets]
    self._focus_drill_wpm = {}
    self._focus_drill_from_pa = from_pa
    for t in targets:
      if len(t) > 2 and t[2] is not None:
        self._focus_drill_wpm[t[1]] = t[2]
    if not self._emit_focus_lesson(self._focus_drill):
      self._focus_drill = None
      self._focus_drill_wpm = {}
      self._focus_drill_from_pa = False
      self.updateLabel('Could not build a drill for those targets.')
      return False
    return True

  def start_focus_drill(self, targets):
    """Start improve focus drill on specific type targets from Performance Analysis."""
    self._settings.set('practice_mode', practice_mode_to_settings(MODE_IMPROVE))
    self._set_mode_ui(MODE_IMPROVE, load=False)
    if not self._start_focus_drill(targets, from_pa=True):
      return

  def set_practice_mode(self, mode):
    if mode == self._mode:
      return
    if mode != MODE_IMPROVE:
      self._focus_drill = None
      self._focus_drill_from_pa = False
    self._focus_drill_wpm = {}
    self._settings.set('practice_mode', practice_mode_to_settings(mode))
    self._set_mode_ui(mode, load=True)

  def _set_mode_ui(self, mode, load):
    self._mode = mode
    for btn, m in ((self._btn_improve, MODE_IMPROVE), (self._btn_corpus, MODE_CORPUS), (self._btn_book, MODE_BOOK)):
      btn.setStyleSheet(self._mode_btn_style)
      btn.setProperty('activeMode', mode == m)
      self._polish_mode_btn(btn)
    self._set_improve_submode_ui(self._improve_submode)
    self._refresh_book_btn()
    self._refresh_follow_footer()
    if self._current_lesson and mode == MODE_CORPUS:
      self._source_lbl.setCursor(Qt.ArrowCursor)
      self._update_source_label(self._current_lesson[1])
    elif mode == MODE_BOOK and self._book_meta:
      self._update_book_footer()
    else:
      self._source_lbl.setVisible(False)
      self._source_lbl.setCursor(Qt.ArrowCursor)
    if not load:
      return
    if mode == MODE_IMPROVE:
      self._load_improve_lesson()
    elif mode == MODE_BOOK:
      self._book.invalidate_cache()
      self._book.request_lesson(advance_chapter=False)
    else:
      self._set_improve_footer_busy(False)
      self.wantText.emit()

  def _set_improve_footer_busy(self, busy):
    self._weakspot_generating = busy
    if busy and self._mode == MODE_IMPROVE:
      self._btn_improve.setText(_GENERATING_BTN_LABEL)
      self._btn_improve.setEnabled(False)
    else:
      self._btn_improve.setText(_IMPROVE_BTN_LABEL)
      self._btn_improve.setEnabled(True)

  def _on_weakspot_busy(self, busy):
    self._set_improve_footer_busy(busy)

  def _on_weakspot_lesson(self, lesson):
    if self._mode != MODE_IMPROVE:
      return
    if not lesson:
      self._show_idle_placeholder(IMPROVE_EMPTY_LABEL)
      return
    self._set_improve_footer_busy(False)
    self.needWeakspotLesson.emit(lesson)

  def _on_lesson_ready(self, match_text):
    self._load_word_baselines(match_text)
    if self._awaiting_next and self._doc.is_ready():
      self._clear_awaiting()
      self.updateLabel()

  def _load_word_baselines(self, match_text):
    words = lesson_words(match_text)
    self._doc.set_word_baselines(fetch_word_perfect_baselines(self.DB, words))
    self._doc.set_word_prior_counts(fetch_word_counted_totals(self.DB, words))

  def _clear_awaiting(self):
    self._awaiting_next = False
    self._pending_action = None
    self._pending_now = None
    self._pending_review_words = None
    self._typer.set_awaiting_enter(None)

  def _show_progress_summary(self, run, stats_saved=True):
    baselines = self._doc._word_baselines
    match_text = self._doc._match_text
    # Improve modes (normal + focus drills) never gather counted word samples, so they
    # cannot mint "new common words" for the analysis pool — hide that feedback entirely.
    show_new_common = self._mode != MODE_IMPROVE
    min_count = analysis_min_count(STAT_TYPE_WORD, Settings.get('analysis_count'))
    progress = analyze_run_progress(
      run, baselines, match_text,
      prior_counts=self._doc._word_prior_counts, min_count=min_count,
      include_new_common=show_new_common)
    if show_new_common:
      self._doc.apply_new_word_styles(run, progress.new_words)
    self._doc.apply_improved_word_styles(run, baselines)
    self._doc.set_progress_badges(progress_badges_for_run(run, baselines, match_text))
    self._awaiting_next = True
    self._typer.set_awaiting_enter(self._continue_lesson)
    msg = format_progress_html(progress, stats_saved=stats_saved)
    banner = follow_outcome_html(self._follow_race_outcome)
    if banner:
      msg = banner + '<br />' + msg
    self.updateLabel(msg)

  def _continue_lesson(self):
    action = self._pending_action
    now = self._pending_now
    review_words = self._pending_review_words
    self._clear_awaiting()
    self.updateLabel()
    if action == 'focus_repeat':
      if self._focus_drill and self._focus_drill_from_pa:
        if not self._emit_focus_lesson(self._focus_drill):
          self.updateLabel('Could not rebuild focus drill for those targets.')
      elif self._focus_drill:
        # New random 5 from the bottom 20 (or smaller pool) each finish.
        self._load_improve_lesson()
      else:
        self.setText(self._current_lesson)
      return
    if action == 'book_chunk' and self._mode == MODE_BOOK and self._book_meta is not None:
      m = self._book_meta
      srcid = self._current_lesson[1]
      if self._doc.advance_book_chunk():
        m = dict(m, chunk_index=m['chunk_index'] + 1)
        self._book_meta = m
        active = m['chunks'][m['chunk_index']]
        tid = lesson_text_id(srcid, m['chapter_index'], m['chunk_index'])
        self._current_lesson = (tid, srcid, active)
        self._update_book_footer(m)
        self._prog.setValue(0)
        self._prog.setMaximum(max(1, len(active)))
        self._show_progress_strip()
        self._schedule_typing_center()
        self._refreshHeatmap()
      return
    if action == 'book_next':
      self._book.request_lesson(advance_chapter=False)
    elif action == 'improve_next':
      self._weakspot.invalidate_cache()
      self._load_improve_lesson()
    elif action == 'review' and review_words:
      review_words.sort(key=lambda x: (x[4], x[0]), reverse=True)
      u = sum(x[4] != 0 for x in review_words)
      u += (len(review_words) - u) // 4
      self.wantReview.emit([x[6] for x in review_words[:u]])
    elif action == 'normal_next':
      self.wantText.emit()

  def updateLabel(self, msg=None):
    text = []
    if msg is not None:
      text.append('<big><b>' + msg + '</b></big>')
    if self._awaiting_next:
      text.append("Press ENTER to start the next exercise.")
    self._label.setText('<br />'.join(text) if text else '')
    if text:
      self._show_result_label()

  def typingFailed(self, txt):
    self.updateLabel(txt)

  def typingFollowLost(self, run):
    """Follow caret reached the end before the typist finished."""
    self._pause_overlay.hide()
    self._stop_follow_race(clear_caret=False)
    self._follow_race_outcome = 'failure'
    self._show_result_label()
    self._typer.updateStatus()

    if self._current_lesson is None:
      log.error("follow lost with no lesson started?")
      return

    now = time()
    med_char = run.median_timing
    stats_saved = False
    textid, srcid, _ = self._current_lesson
    if med_char:
      vals = collect_run_stat_rows(run, med_char, now, srcid)
      is_lesson = self.DB.fetchone("select discount from source where rowid=?", (None,), (srcid, ))[0]
      write_stats = self._mode not in (MODE_IMPROVE,) and (not is_lesson or self._settings.get('use_lesson_stats'))
      if write_stats and vals:
        self.DB.executemany_('''
        insert into statistic
        (time,viscosity,w,count,mistakes,type,data,source)
        values (?,?,?,?,?,?,?,?)
        ''', vals)
        self.DB.commit()
        self.statsChanged.emit()
        self._refreshHeatmap()
        stats_saved = True

    # Book place still advances on follow failure (same as a finished chunk).
    if self._mode == MODE_BOOK and self._book_meta is not None:
      m = self._book_meta
      self._book.on_chunk_completed(srcid, m['chapter_index'], m['chunk_index'], now)
      if self._doc.has_next_book_chunk():
        self._pending_action = 'book_chunk'
      else:
        self._pending_action = 'book_next'
    else:
      self._pending_action = 'normal_next'
    self._pending_now = now
    self._pending_review_words = None
    self._show_progress_summary(run, stats_saved=stats_saved)

  def typingDone(self, run):
    self._stop_follow_race(clear_caret=False)
    if self._follow_is_active() and self._follow_race_outcome is None:
      self._follow_race_outcome = 'success'
    self._show_result_label()

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
      now = time()
      ws_src = self.DB.getSource('<Weakspot>', lesson=1)
      drill_rows = collect_focus_drill_stat_rows(run, med_char, now, self._focus_drill)
      if drill_rows:
        self.DB.executemany_('''
        insert into statistic
        (time,viscosity,w,count,mistakes,type,data,source)
        values (?,?,?,?,?,?,?,?)
        ''', [(t, vis, w, c, m, tp, data, ws_src) for t, vis, w, c, m, tp, data in drill_rows])
        self.DB.commit()
        self.statsChanged.emit()
        self._refreshHeatmap()
      self._pending_action = 'focus_repeat'
      self._show_progress_summary(run, stats_saved=bool(drill_rows))
      return

    now = time()
    textid, srcid, _ = self._current_lesson
    _, visc, acc = run.result(accuracy=True)
    duration = run.active_duration()
    wpm = (len(run) / duration * 12.0) if duration else 0.0

    self.DB.execute('''
    insert into result
    (w, text_id, source, wpm, accuracy, viscosity, char_count, duration)
    values (?,?,?, ?,?,?,?,?)
    ''', (now, textid, srcid,
          wpm, acc, visc, len(run), duration))

    self.DB.commit()
    # type (0: char, 1: trigram, 2: word)

    vals = collect_run_stat_rows(run, med_char, now, srcid)

    is_lesson = self.DB.fetchone("select discount from source where rowid=?", (None,), (srcid, ))[0]
    write_stats = self._mode not in (MODE_IMPROVE,) and (not is_lesson or self._settings.get('use_lesson_stats'))

    if self._mode == MODE_IMPROVE:
      ws_src = self.DB.getSource('<Weakspot>', lesson=1)
      # Keep real count/mistakes so drills raise perfect rate; discounted source
      # still blocks inventing new known words (corpus floor only).
      drill_vals = [(t, vis, w, c, m, tp, data, ws_src) for t, vis, w, c, m, tp, data, _s in vals]
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

    self._pending_now = now
    self._pending_review_words = review_words if action == 'review' else None

    if self._mode == MODE_BOOK and self._book_meta is not None:
      m = self._book_meta
      srcid = self._current_lesson[1]
      # Always persist place on every finished chunk (not only chapter ends).
      # Mid-chapter advances used to skip this and reopened the same chunk forever.
      self._book.on_chunk_completed(srcid, m['chapter_index'], m['chunk_index'], now)
      if self._doc.has_next_book_chunk():
        self._pending_action = 'book_chunk'
        self._show_progress_summary(run, stats_saved=True)
        return

    self._pending_action = action
    self._show_progress_summary(run, stats_saved=True)

