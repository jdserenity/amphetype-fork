"""Focused session clock — elapsed time while the main window is frontmost and active."""

from PyQt5.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel

from typing_program import timer
from typing_program.app_meta import TOTAL_PRACTICE_SECONDS_KEY, get_app_meta_int, set_app_meta_int

SESSION_IDLE_TIMEOUT = 60.0

INTERACTION_EVENTS = frozenset({
  QEvent.MouseButtonPress,
  QEvent.MouseButtonRelease,
  QEvent.KeyPress,
  QEvent.KeyRelease,
  QEvent.Wheel,
  QEvent.TouchBegin,
  QEvent.TouchUpdate,
  QEvent.TabletPress,
})


def format_session_label(secs):
  secs = max(0, int(secs))
  h, rem = divmod(secs, 3600)
  m, s = divmod(rem, 60)
  return f'{h}:{m:02d}:{s:02d} session'


def format_practice_total_label(secs):
  return format_session_label(secs).replace(' session', '')


def total_practice_seconds_from_db(db):
  return get_app_meta_int(db, TOTAL_PRACTICE_SECONDS_KEY, 0)


class FocusedSessionTimer:
  def __init__(self):
    self._saved = 0.0
    self._segment = 0.0
    self._running_since = None
    self._should_run = False
    self._last_interaction = None

  def set_saved(self, secs):
    self._saved = max(0.0, float(secs))

  def load_saved(self, db):
    self.set_saved(total_practice_seconds_from_db(db))

  def segment_elapsed(self):
    if self._running_since is None:
      return self._segment
    return self._segment + (timer() - self._running_since)

  def elapsed(self):
    """Current focused segment (top-right session clock)."""
    return self.segment_elapsed()

  def total_seconds(self):
    """All-time practice seconds: persisted total plus the live segment."""
    return self._saved + self.segment_elapsed()

  def touch(self):
    now = timer()
    self._last_interaction = now
    if self._should_run and self._running_since is None:
      self._running_since = now

  def resume(self):
    self._should_run = True
    if self._running_since is not None:
      return
    now = timer()
    self._last_interaction = now
    self._running_since = now

  def pause(self):
    self._should_run = False
    self._pause_segment()

  def _pause_segment(self):
    if self._running_since is None:
      return
    self._segment += timer() - self._running_since
    self._running_since = None

  def check_idle(self):
    if self._running_since is None or not self._should_run:
      return
    now = timer()
    if self._last_interaction is None:
      self._last_interaction = self._running_since
    if now - self._last_interaction >= SESSION_IDLE_TIMEOUT:
      self._pause_segment()

  def flush_to_db(self, db):
    self._pause_segment()
    total = int(self._saved + self._segment)
    self._saved = float(total)
    self._segment = 0.0
    set_app_meta_int(db, TOTAL_PRACTICE_SECONDS_KEY, total)


class SessionTimerLabel(QLabel):
  textChanged = pyqtSignal()

  def __init__(self, session_timer, parent=None):
    super().__init__(parent)
    self._session_timer = session_timer
    self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    self.setStyleSheet('color: #555; font-size: 11px; padding: 0 2px;')
    self._tick = QTimer(self)
    self._tick.setInterval(500)
    self._tick.timeout.connect(self._refresh)
    self._refresh()

  def start(self):
    self._tick.start()
    self._refresh()

  def _refresh(self):
    self._session_timer.check_idle()
    self.setText(format_session_label(self._session_timer.elapsed()))
    self.textChanged.emit()
