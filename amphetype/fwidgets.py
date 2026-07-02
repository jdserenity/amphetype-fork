from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class FColorButton(QPushButton):
  def __init__(self, var, text=''):
    super().__init__(clicked=self.pickColor)
    self._var = var
    self._text = text
    self.updateIcon()

  def pickColor(self):
    color = QColorDialog.getColor(self._var.get(), self)
    if not color.isValid():
      return
    self._var.set(color)
    self.updateIcon()

  def updateIcon(self):
    pix = QPixmap(64, 32)
    pix.fill(self._var.get())
    self.setText(f'{self._text} {self._var.get().name()}'.strip())
    self.setIcon(QIcon(pix))


def scroll_widget(w):
  """Wrap a tall/wide settings page so QTabWidget min size stays small."""
  sa = QScrollArea()
  sa.setWidgetResizable(True)
  sa.setWidget(w)
  sa.setFrameShape(QFrame.NoFrame)
  sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
  sa.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
  return sa


class FStackedWidget(QStackedWidget):
  def __init__(self, contents, *args, **kwargs):
    super().__init__(*args, **kwargs)

    for w in contents:
      self.add(w)

  def add(self, what):
    if isinstance(what, str):
      self.addWidget(QLabel(what))
    elif isinstance(what, QWidget):
      self.addWidget(what)
    else:
      raise ValueError(f"unknown type {type(what)} added to layout")

  def cycle(self, times=1):
    self.setCurrentIndex((self.currentIndex() + times) % self.count())

  def showFirst(self):
    if self.count() > 0:
      self.setCurrentIndex(0)

  def showLast(self):
    n = self.count()
    if n > 0:
      self.setCurrentIndex(n-1)
