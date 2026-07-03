from PyQt5.QtWidgets import *

class FStackedLayout(QStackedLayout):
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

class FBoxLayout(QBoxLayout):
  def __init__(self, tree, *args, direction=QBoxLayout.TopToBottom):
    super().__init__(direction, *args)

    for x in tree:
      if isinstance(x, tuple):
        self.addStuff(*x)
      else:
        self.addStuff(x)

  def addStuff(self, x, stretch=0):
    if isinstance(x, str):
      if '\n' in x:
        self.addWidget(QLabel(x.strip(), wordWrap=True, openExternalLinks=True))
      else:
        self.addWidget(QLabel(x), stretch)
    elif isinstance(x, list):
      self.addLayout(FBoxLayout(x, direction=self.dualLayout()), stretch)
    elif isinstance(x, complex):
      x,y = round(x.real), round(x.imag)
      if x: self.addSpacing(x)
      if y: self.addStretch(x)
    elif isinstance(x, int):
      self.addSpacing(x)
    elif x is None:
      self.addStretch(1 if stretch == 0 else stretch)
    elif isinstance(x, QLayout):
      self.addLayout(x, stretch)
    else:
      self.addWidget(x, stretch)

  def dualLayout(self):
    if self.direction() == QBoxLayout.TopToBottom or self.direction() == QBoxLayout.BottomToTop:
      return QBoxLayout.LeftToRight
    return QBoxLayout.TopToBottom
