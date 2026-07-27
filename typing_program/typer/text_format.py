"""Text format helpers and cursor for the lesson document."""

from PyQt5.QtGui import QBrush, QColor, QTextBlockFormat, QTextCharFormat, QTextCursor

RETURN_CHAR = '⏎' # '↵'
PARA_SEP = '\u2029'
LINE_SEP = '\u2028'

# Lesson text backgrounds only for error highlighting; untyped/correct/inactive stay clear.
_NO_FILL_STYLE_ATTRS = frozenset({'untyped', 'correct', 'inactive'})

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
