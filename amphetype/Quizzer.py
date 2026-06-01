
import time
import collections
import re
import sys

from amphetype import timer
from amphetype.Data import Statistic, DB
from amphetype.Config import Settings

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from amphetype.QtUtil import *


class Typer(QTextEdit):
  sigDone = pyqtSignal()
  sigCancel = pyqtSignal()
  
  def __init__(self, *args):
    super().__init__(*args)

    self.setPalettes()

    self.textChanged.connect(self.checkText)
    #self.setLineWrapMode(QTextEdit.NoWrap)
    Settings.signal_for("quiz_wrong_fg").connect(self.setPalettes)
    Settings.signal_for("quiz_wrong_bg").connect(self.setPalettes)
    Settings.signal_for("quiz_right_fg").connect(self.setPalettes)
    Settings.signal_for("quiz_right_bg").connect(self.setPalettes)
    self.target = None

  def sizeHint(self):
    return QSize(600, 10)

  def keyPressEvent(self, e):
    if e.key() == Qt.Key_Escape:
      self.sigCancel.emit()
    return QTextEdit.keyPressEvent(self, e)

  def setPalettes(self):
    self._css = {
      'wrong': f"QTextEdit {{ background-color: {Settings.get('quiz_wrong_bg')}; color: {Settings.get('quiz_wrong_fg')} }}",
      'right': f"QTextEdit {{ background-color: {Settings.get('quiz_right_bg')}; color: {Settings.get('quiz_right_fg')} }}",
      'inactive': '' }
    
    self.setStyleSheet(self._css['inactive'])

  def setTarget(self,  text):
    self.editflag = True
    self.target = text
    self.when = [0] * (len(self.target)+1)
    self.times = [0] * len(self.target)
    self.mistake = [False] * len(self.target)
    self.mistakes = {} #collections.defaultdict(lambda: [])
    self.where = 0
    self.clear()
    # self.setPalette(self.palettes['inactive'])
    self.setStyleSheet(self._css['inactive'])
    self.setText(self.getWaitText())
    self.selectAll()
    self.editflag = False

  def getWaitText(self):
    if Settings.get('req_space'):
      return "Press SPACE and then immediately start typing the text\n" + \
          "Press ESCAPE to restart with a new text at any time"
    else:
      return "Press ESCAPE to restart with a new text at any time"

  def checkText(self):
    if self.target is None or self.editflag:
      return

    v = str(self.toPlainText())
    if self.when[0] == 0:
      space = len(v) > 0 and v[-1] == " "
      req = Settings.get('req_space')

      self.editflag = True
      if space:
        self.when[0] = timer()
        self.clear()
        # self.setPalette(self.palettes['right'])
        self.setStyleSheet(self._css['right'])
      elif req:
        self.setText(self.getWaitText())
        self.selectAll()
      self.editflag = False

      if req or space:
        return
      else:
        self.when[0] = -1

    y = 0
    for y in range(min(len(v), len(self.target)), -1, -1):
      if v[0:y] == self.target[0:y]:
        break
    lcd = v[0:y]
    self.where = y

    if self.when[y] == 0 and y == len(v):
      self.when[y] = timer()
      if y > 0:
        self.times[y-1] = self.when[y] - self.when[y-1]

    if lcd == self.target:
      self.sigDone.emit()
      return

    if y < len(v) and y < len(self.target):
      self.mistake[y] = True
      self.mistakes[y] = self.target[y] + v[y]

    if v == lcd:
      # self.setPalette(self.palettes['right'])
      self.setStyleSheet(self._css['right'])
    else:
      # self.setPalette(self.palettes['wrong'])
      self.setStyleSheet(self._css['wrong'])

  def getMistakes(self):
    inv = collections.defaultdict(lambda: 0)
    for p, m in self.mistakes.items():
      inv[m] += 1
    return inv

  def getStats(self):
    if self.when[0] == -1:
      t = self.times[1:]
      t.sort(reverse=True)
      v = DB.fetchone('select time from statistic where type = 0 and data = ? order by rowid desc limit 1', (t[len(t)//5], ), (self.target[0], ))
      self.times[0] = v[0]
      self.when[0] = self.when[1] - self.times[0]
    return self.when[self.where]-self.when[0], self.where, self.times, self.mistake, self.getMistakes()



class Quizzer(QWidget):
  wantReview = pyqtSignal('PyQt_PyObject')
  wantText = pyqtSignal()
  statsChanged = pyqtSignal()

  def __init__(self, *args):
    super(Quizzer, self).__init__(*args)

    self.result = QLabel()
    self.typer = Typer()
    self.label = WWLabel()
    self.result.setVisible(Settings.get("show_last"))
    #self.label.setFrameStyle(QFrame.Raised | QFrame.StyledPanel)
    #self.typer.setBuddy(self.label)
    #self.info = QLabel()
    self.typer.sigDone.connect(self.done)
    self.typer.sigCancel.connect(self.wantText)
    Settings.signal_for("typer_font").connect(self.readjust)
    Settings.signal_for("show_last").connect(self.result.setVisible)

    self.text = ('','', 0, None)

    layout = QVBoxLayout()
    #layout.addWidget(self.info)
    #layout.addSpacing(20)
    layout.addWidget(self.result, 0, Qt.AlignRight)
    layout.addWidget(self.label, 1, Qt.AlignBottom)
    layout.addWidget(self.typer, 1)
    self.setLayout(layout)
    self.readjust()

  def readjust(self):
    f = Settings.getFont("typer_font")
    self.label.setFont(f)
    self.typer.setFont(f)

  def setText(self, text):
    self.text = text
    self.label.setText(self.text[2].replace("\n", "↵\n"))
    self.typer.setTarget(self.text[2])
    self.typer.setFocus()

  def showEvent(self, evt):
    self.typer.setFocus()
    return super().showEvent(evt)

  def done(self):
    now = time.time()
    elapsed, chars, times, mis, mistakes = self.typer.getStats()

    assert chars == len(self.text[2])

    accuracy = 1.0 - len([_f for _f in mis if _f]) / chars
    spc = elapsed / chars
    viscosity = sum([((x-spc)/spc)**2 for x in times]) / chars

    DB.execute('insert into result (w,text_id,source,wpm,accuracy,viscosity) values (?,?,?,?,?,?)',
           (now, self.text[0], self.text[1], 12.0/spc, accuracy, viscosity))

    v2 = DB.fetchone("""select agg_median(wpm),agg_median(acc) from
      (select wpm,100.0*accuracy as acc from result order by w desc limit %d)""" % Settings.get('def_group_by'), (0.0, 100.0))
    self.result.setText("Last: %.1fwpm (%.1f%%), last 10 average: %.1fwpm (%.1f%%)"
      % ((12.0/spc, 100.0*accuracy) + v2))

    self.statsChanged.emit()

    stats = collections.defaultdict(Statistic)
    visc = collections.defaultdict(Statistic)
    text = self.text[2]

    for c, t, m in zip(text, times, mis):
      stats[c].append(t, m)
      visc[c].append(((t-spc)/spc)**2)

    def gen_tup(s, e):
      perch = sum(times[s:e])/(e-s)
      if perch < 1e-7:
        log.warning(f"timing for span ({s},{e}) summed to zero or near-zero ({perch}); skipping it")
        return (None, None, None, None)
      visc = sum([((x-perch)/perch)**2 for x in times[s:e]])/(e-s)
      return (text[s:e], perch, len([_f for _f in mis[s:e] if _f]), visc)

    for tri, t, m, v in [gen_tup(i, i+3) for i in range(0, chars-2)]:
      if tri is None:
        continue
      stats[tri].append(t, m > 0)
      visc[tri].append(v)

    regex = re.compile(r"(\w|'(?![A-Z]))+(-\w(\w|')*)*")

    for w, t, m, v in [gen_tup(*x.span()) for x in regex.finditer(text) if x.end()-x.start() > 3]:
      if w is None:
        continue
      stats[w].append(t, m > 0)
      visc[w].append(v)

    def type(k):
      if len(k) == 1:
        return 0
      elif len(k) == 3:
        return 1
      return 2

    vals = []
    for k, s in stats.items():
      v = visc[k].median()
      vals.append( (s.median(), v*100.0, now, len(s), s.flawed(), type(k), k, self.text[1]) )

    is_lesson = DB.fetchone("select discount from source where rowid=?", (None,), (self.text[1], ))[0]

    if Settings.get('use_lesson_stats') or not is_lesson:
      DB.executemany_('''insert into statistic
        (time,viscosity,w,count,mistakes,type,data,source) values (?,?,?,?,?,?,?,?)''', vals)
      DB.executemany_('insert into mistake (w,target,mistake,count) values (?,?,?,?)',
          [(now, k[0], k[1], v) for k, v in mistakes.items()])

    DB.commit()

    if is_lesson:
      mins = (Settings.get("min_lesson_wpm"), Settings.get("min_lesson_acc"))
    else:
      mins = (Settings.get("min_wpm"), Settings.get("min_acc"))

    if 12.0/spc < mins[0] or accuracy < mins[1]/100.0:
      self.setText(self.text)
    elif not is_lesson and Settings.get('auto_review'):
      ws = [x for x in vals if x[5] == 2]
      if len(ws) == 0:
        self.wantText.emit()
        return
      ws.sort(key=lambda x: (x[4],x[0]), reverse=True)
      i = 0
      while ws[i][4] != 0:
        i += 1
      i += (len(ws) - i) // 4

      self.wantReview.emit([x[6] for x in ws[0:i]])
    else:
      self.wantText.emit()

