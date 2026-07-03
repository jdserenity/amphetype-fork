


from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from functools import cmp_to_key

def maybe_cmp_func(f):
  def _maybe_cmp_func(a,b):
    a,b = f(a),f(b)
    if a==b: return 0
    if a is None: return -1
    if b is None: return 1
    if a < b: return -1
    return 1
  return _maybe_cmp_func

class WWLabel(QLabel):
  def __init__(self, *args):
    super(QLabel, self).__init__(*args)
    self.setWordWrap(True)
    self.setOpenExternalLinks(True)


class AppModel(QAbstractItemModel):
  def __init__(self, *args):
    super(AppModel, self).__init__(*args)
    self.hidden = 0
    self.levels = 2
    self.rows = None
    self.head, self.fmt = self.signature()
    self.cols = len(self.head)
    self.idxs = {}

  def hasChildren(self, parent):
    if not parent.isValid():
      return True
    idxs = parent.internalPointer()
    if len(idxs) +1 >= self.levels:
      return False
    return True

  def index(self, row, column, parent):
    if row < 0 or column < 0 or row >= self.rowCount(parent) or column >= self.columnCount(parent):
      return QModelIndex()
    v = self.indexList(parent)
    if v not in self.idxs:
      self.idxs[v] = v
    return self.createIndex(row, column, self.idxs[v])

  def parent(self, index):
    if not index.isValid():
      return QModelIndex()

    idxs = index.internalPointer()

    if len(idxs) == 0:
      return QModelIndex()

    return self.createIndex(idxs[-1], 0, idxs[0:-1])

  def indexList(self, index):
    if not index.isValid():
      return ()
    return index.internalPointer() + (index.row(), )

  def findList(self, parent):
    if not parent.isValid():
      if self.rows is None:
        self.rows = self.populateData([])
      return self.rows

    tab = self.findList(parent.parent())
    row = parent.row()
    r = tab[row]
    if len(r) <= self.cols+self.hidden:
      r.append(self.populateData(self.indexList(parent)))
    return r[self.cols+self.hidden]

  def rowCount(self, index=QModelIndex()):
    tab = self.findList(index)
    return len(tab)
  def columnCount(self, index=QModelIndex()):
    return self.cols

  def data(self, index, role=Qt.DisplayRole):
    if not index.isValid():
       return QVariant()

    if role != Qt.DisplayRole and role != Qt.UserRole:
      return QVariant()

    row, col = index.row(), index.column()
    tab = self.findList(index.parent())

    if role == Qt.UserRole:
      return tab[row]

    if not (0 <= row < len(tab)) or not (0 <= col < self.cols):
      return QVariant()

    data = tab[row][col+self.hidden]
    if data is None:
      return QVariant()
    if self.fmt[col] is None:
      return QVariant(data)
    elif isinstance(self.fmt[col], str):
      return QVariant(self.fmt[col] % data)
    return QVariant(self.fmt[col](data))

  def headerData(self, section, orientation, role=Qt.DisplayRole):
    if role != Qt.DisplayRole:
      return QVariant()
    if orientation != Qt.Horizontal:
      return QVariant()
    return QVariant(self.head[section])

  def sort(self, col, order=Qt.AscendingOrder):
    self.beginResetModel()
    reverse = order != Qt.AscendingOrder
    self.rows.sort(key=cmp_to_key(maybe_cmp_func(lambda z: z[col+self.hidden])), reverse=reverse)
    self.idxs = {}
    self.endResetModel()

  def reset(self):
    self.beginResetModel()
    self.rows = self.populateData(())
    self.idxs = {}
    self.endResetModel()

  def populateData(self, idxs):
    pass

  def signature(self):
    return ([], [])



class AppTree(QTreeView):
  def __init__(self, model, *args):
    super(AppTree, self).__init__(*args)

    self.setModel(model)
    self.setWordWrap(True)
    self.setSelectionMode(QAbstractItemView.ExtendedSelection)
    #self.setExpandsOnDoubleClick(False)
    self.header().setSectionsClickable(True)
    self.header().sectionClicked[int].connect(self.sortByColumn)


class AppBoxLayout(QBoxLayout):
  def __init__(self, tree, dir=QBoxLayout.TopToBottom):
    QBoxLayout.__init__(self, dir)

    for x in tree:
      if isinstance(x, tuple):
        self.addStuff(*x)
      else:
        self.addStuff(x)

  def addStuff(self, x, stretch=0):
    if isinstance(x, str):
      if x[-1] == "\n":
        self.addWidget(WWLabel(x[:-1]), stretch)
      else:
        self.addWidget(QLabel(x), stretch)
    elif isinstance(x, list):
      self.addLayout(self.getInstance(x), stretch)
    elif isinstance(x, int):
      self.addSpacing(x)
    elif x is None:
      self.addStretch(1 if stretch == 0 else stretch)
    elif isinstance(x, QLayout):
      self.addLayout(x, stretch)
    else:
      self.addWidget(x, stretch)

  def getInstance(self, x):
    if self.direction() == QBoxLayout.TopToBottom:
      next = QBoxLayout.LeftToRight
    else:
      next = QBoxLayout.TopToBottom
    return AppBoxLayout(x, next)


class AppGridLayout(QGridLayout):
  def __init__(self, grid):
    QGridLayout.__init__(self)

    for row in range(len(grid)):
      for col in range(len(grid[row])):
        x = grid[row][col]
        if isinstance(x, tuple):
          self.addStuff(x[0], (row, col), *x[1:])
        else:
          self.addStuff(x, (row, col))

  def addStuff(self, x, pos, span=(1, 1), align=0):
    if align == 0:
      args = pos + span
    else:
      args = pos + span + (align, )
    if isinstance(x, str):
      if x[-1] == "\n":
        self.addWidget(WWLabel(x[:-1]), *args)
      else:
        self.addWidget(QLabel(x), *args)
    elif isinstance(x, list):
      self.addLayout(self.getInstance(x), *args)
    elif x is None:
      self.setColumnStretch(pos[1], span[1])
      self.setRowStretch(pos[0], span[0])
    elif isinstance(x, int):
      pass
    elif isinstance(x, complex):
      self.setRowStretch(int(x.real), span[0])
      self.setColumnStretch(int(x.imag), span[1])
    elif isinstance(x, QLayout):
      self.addLayout(x, *args)
    else:
      self.addWidget(x, *args)

  def getInstance(self, x):
    return AppGridLayout(x)


class AppButton(QPushButton):
  def __init__(self, text, callback, *args):
    super(AppButton, self).__init__(text, *args)
    self.clicked.connect(callback)

class AppEdit(QLineEdit):
  def __init__(self, text, callback, validator=None):
    super(AppEdit, self).__init__(text)
    if validator is not None:
      self.setValidator(validator(self))
    self.editingFinished.connect(callback)


def centered_frame_origin(screen_rect, frame_width, frame_height):
  """Top-left (x, y) for a window frame centered in screen_rect (QRect-like)."""
  return (
    screen_rect.x() + (screen_rect.width() - frame_width) // 2,
    screen_rect.y() + (screen_rect.height() - frame_height) // 2,
  )


def center_widget_on_screen(widget, screen=None):
  """Move widget so its frame is centered on the screen's usable area."""
  app = QApplication.instance()
  if app is None:
    return
  if screen is None:
    screen = app.primaryScreen()
  if screen is None:
    return
  geo = screen.availableGeometry()
  frame = widget.frameGeometry()
  frame.moveCenter(geo.center())
  widget.move(frame.topLeft())


def should_clear_focus_on_click(focused, clicked):
  """True when a mouse press on clicked should drop focus from focused."""
  if focused is None or clicked is None:
    return False
  if focused is clicked or focused.isAncestorOf(clicked):
    return False
  if isinstance(focused, QComboBox):
    view = focused.view()
    if view is not None:
      popup = view.window()
      if popup is not None and (clicked is popup or popup.isAncestorOf(clicked)):
        return False
  return True

