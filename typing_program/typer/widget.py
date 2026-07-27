from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from typing_program.settings import *
from typing_program.Config import Settings
from typing_program.block_bkspc import allows_backspace
from typing_program.idle_cursor import MOUSE_CURSOR_IDLE_MS, should_apply_idle_blank
from typing_program.follow_mode import FOLLOW_CURSOR_COLOR
from typing_program.typing_sounds import TypingSoundPlayer
from typing_program.speed_heatmap import PROGRESS_GREEN, PROGRESS_ORANGE

from typing_program.typer.document import Cursor, RETURN_CHAR
from typing_program.typer.styles import _BADGE_FONT_PT

def configure_transparent_typer(typer):
  """QTextEdit + viewport must both be transparent; stylesheet on the edit alone is not enough."""
  typer.setStyleSheet('QTextEdit { background: transparent; border: none; padding: 0; }')
  vp = typer.viewport()
  vp.setAutoFillBackground(False)
  vp.setStyleSheet('background: transparent;')
# DIAMOND = '◈'

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
    # Mouse moves land on the viewport (QTextEdit), not TyperWidget — filter them.
    self.setMouseTracking(True)
    self.viewport().setMouseTracking(True)
    self.viewport().installEventFilter(self)
    self._mouse_cursor_timer = QTimer(self)
    self._mouse_cursor_timer.setSingleShot(True)
    self._mouse_cursor_timer.setInterval(MOUSE_CURSOR_IDLE_MS)
    self._mouse_cursor_timer.timeout.connect(self._hide_idle_mouse_cursor)
    self._mouse_cursor_timer.start()

  def _pointer_over_canvas(self):
    return self.underMouse() or self.viewport().underMouse()

  def _restore_mouse_cursor(self):
    self.unsetCursor()
    self.viewport().unsetCursor()

  def _show_mouse_cursor(self):
    self._restore_mouse_cursor()
    self._mouse_cursor_timer.start()

  def _hide_idle_mouse_cursor(self):
    # Timer may fire after the pointer already left for the footer.
    if not should_apply_idle_blank(self._pointer_over_canvas()):
      return
    self.setCursor(Qt.BlankCursor)
    self.viewport().setCursor(Qt.BlankCursor)

  def eventFilter(self, obj, event):
    if obj is self.viewport():
      t = event.type()
      if t in (QEvent.MouseMove, QEvent.Enter):
        self._show_mouse_cursor()
      elif t == QEvent.Leave:
        self._mouse_cursor_timer.stop()
        self._restore_mouse_cursor()
    return super().eventFilter(obj, event)

  def mouseMoveEvent(self, e):
    self._show_mouse_cursor()
    super().mouseMoveEvent(e)

  def enterEvent(self, e):
    self._show_mouse_cursor()
    super().enterEvent(e)

  def leaveEvent(self, e):
    self._mouse_cursor_timer.stop()
    self._restore_mouse_cursor()
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
    elif evt.text():
      # One printable char per call. Multi-char / composed input uses inputMethodEvent.
      t = evt.text()
      if len(t) == 1 and ord(t) >= 32:
        self.insert(t)
      elif len(t) > 1:
        for ch in t:
          if ord(ch) >= 32:
            self.insert(ch)
      else:
        evt.ignore()
        return
    else:
      evt.ignore()
      return

    evt.accept()

  def inputMethodEvent(self, evt):
    """Dead keys / IME: only commit finished characters; ignore in-progress accents."""
    if not self._lesson or self._lesson.is_finished() or self._lesson.is_paused():
      evt.ignore()
      return
    commit = evt.commitString()
    if commit:
      for ch in commit:
        if ord(ch) >= 32:
          self.insert(ch)
      evt.accept()
      return
    # Pre-edit (composing) string — don't paint half-made accents into the lesson.
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


