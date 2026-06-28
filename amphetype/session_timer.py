"""Focused session clock — elapsed time while the main window is frontmost."""

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel

from amphetype import timer


def format_session_label(secs):
  secs = max(0, int(secs))
  h, rem = divmod(secs, 3600)
  m, s = divmod(rem, 60)
  return f'{h}:{m:02d}:{s:02d} session'


class FocusedSessionTimer:
  def __init__(self):
    self._elapsed = 0.0
    self._running_since = None

  def resume(self):
    if self._running_since is not None:
      return
    self._running_since = timer()

  def pause(self):
    if self._running_since is None:
      return
    self._elapsed += timer() - self._running_since
    self._running_since = None

  def elapsed(self):
    if self._running_since is None:
      return self._elapsed
    return self._elapsed + (timer() - self._running_since)


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
    self.setText(format_session_label(self._session_timer.elapsed()))
    self.textChanged.emit()
