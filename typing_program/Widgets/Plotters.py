
from typing_program.Config import Settings
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import math

class HoverItem(QGraphicsRectItem):
  def __init__(self, func, x, y, width, height, *args):
    super(HoverItem, self).__init__(x, y, width, height, *args)

    self.func_ = func
    self.setBrush(QBrush(Qt.NoBrush))
    self.setPen(QPen(Qt.NoPen))
    self.setAcceptsHoverEvents(True)

  def hoverEnterEvent(self, evt):
    self.setBrush(QBrush(QColor(255, 192, 0, 120)))
    self.func_()
    self.update()

  def hoverLeaveEvent(self, evt):
    self.setBrush(QBrush(Qt.NoBrush))
    self.update()

class CenteredText(QGraphicsSimpleTextItem):
  def __init__(self, x, y, *args):
    super().__init__(*args)
    self._center = (x,y)
    self.setBrush(QBrush(Qt.white, Qt.SolidPattern))
    self.setPen(QPen(Qt.black))
    self.adjustPos()

  def setText(self, txt):
    super().setText(txt)
    self.adjustPos()

  def adjustPos(self):
    br = self.boundingRect()
    self.setPos(self._center[0] - br.width()/2.0, self._center[1] - br.height()/2.0)

class SimpleText(QGraphicsSimpleTextItem):
  def __init__(self, *args):
    super().__init__(*args)
    self.setBrush(QBrush(Qt.black, Qt.SolidPattern))
    pen = QPen(Qt.black)
    pen.setCosmetic(True)
    self.setPen(pen)
    self.setTransformOriginPoint(self.boundingRect().center())
    self._pos = self.pos()

  def setText(self, txt):
    super().setText(txt)
    self.setTransformOriginPoint(self.boundingRect().center())
    self.adjustPos()
    return self

  def setPos(self, qpt):
    self._pos = qpt
    self.adjustPos()

  def adjustPos(self):
    br = self.boundingRect()
    super().setPos(self._pos.x() - br.width()/2, self._pos.y() - br.height()/2)

  def setColor(self, brush_color, pen_color, pen_width=None):
    if pen_color is not None:
      pen = QPen(QColor(pen_color))
      pen.setCosmetic(True)
      if pen_width:
        pen.setWidthF(pen_width)
      self.setPen(pen)
    if brush_color is not None:
      brush = QBrush(QColor(pen_color), Qt.SolidPattern)
      self.setBrush(brush)


class Plot(QGraphicsScene):
  def __init__(self, x, y, *args):
    super(Plot, self).__init__(*args)

    #self.connect(self, SIGNAL("sceneRectChanged(QRectF)"), self.setSceneRect)

    if len(x) < 2:
      return

    min_x, max_x = min(x), max(x)
    min_y, max_y = min(y), max(y)

    p = QPen(Qt.blue)
    p.setCosmetic(True)
    p.setWidthF(2.0)
    p.setCapStyle(Qt.RoundCap)
    for i in range(0, len(x)-1):
      self.addLine(x[i], -y[i], x[i+1], -y[i+1], p)

    # Add axes
    if Settings.get('show_xaxis'):
      if min_y > 0:
        min_y = 0
      elif max_y < 0:
        max_y = 0
    p.setColor(Qt.black)
    if min_y <= 0 <= min_y:
      self.addLine(min_x, 0, max_x, 0, p)
    if min_x <= 0 <= max_x:
      self.addLine(0, -min_y, 0, -max_y, p)

    w, h = max_x - min_x, max_y - min_y

    if h <= 0 or w <= 0:
      return

    # Add background lines
    spc = math.pow(10.0, math.ceil(math.log10(h)-1))
    while h/spc < 5:
      spc /= 2

    ns = int( min_y/spc ) * spc
    start = ns

    qp = QPen(QColor(Qt.lightGray))
    qp.setStyle(Qt.DotLine)
    qp.setWidth(2)
    qp.setCosmetic(True)

    from random import random

    while start < max_y + spc:
      lin = self.addLine(min_x, -start, max_x, -start, qp)
      lin.setZValue(-1.0)

      txt = QGraphicsSimpleTextItem("%g" % start)
      th, tw = txt.boundingRect().height(), txt.boundingRect().width()
      
      txt.setTransform(QTransform() \
               .translate(min_x - 0.03*w, -start - spc/2) \
               .scale(0.026*w/tw, spc/th))
      
      self.addItem(txt)
      start += spc

    qr = QRectF(min_x-0.03*w, -start+spc/2, 1.06*float(w), start-ns)

    self.setSceneRect(qr)


class Plotter(QGraphicsView):
  def __init__(self, *args):
    super(Plotter, self).__init__(*args)
    self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    #self.connect(scene, SIGNAL("sceneRectChanged(QRectF)"), self.fitInView)

  def resizeEvent(self, evt):
    QGraphicsView.resizeEvent(self, evt)
    if self.scene():
      self.fitInView(self.scene().sceneRect())

  def setScene(self, scene):
    QGraphicsView.setScene(self, scene)
    self.fitInView(scene.sceneRect())


if __name__ == '__main__':
  import random
  import sys
  import math

  app = QApplication(sys.argv)
  v = Plotter()
  quitSc = QShortcut(QKeySequence('Ctrl+Q'), v)
  quitSc.activated.connect(QApplication.instance().quit)

  p = Plot([1,2,3,4,5,6,7,8,9], [random.random() * 8 for _ in range(9)])
  r = p.sceneRect()
  print(r.x(),r.y(),r.width(),r.height())
  v.setScene(p)
  v.show()
  app.exec_()
  print("exis")

