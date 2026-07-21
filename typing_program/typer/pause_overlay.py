from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

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

