
from typing_program.Data import DB
from typing_program.QtUtil import *
from typing_program.StatWidgets import StringStats
from typing_program.progress_card import ProgressCard

from PyQt5.QtCore import *


class PerformanceAnalysis(QWidget):
  setText = pyqtSignal('PyQt_PyObject')
  gotoText = pyqtSignal()
  startDrill = pyqtSignal(list)
  loadCorpusText = pyqtSignal('PyQt_PyObject')

  def __init__(self, *args):
    super(PerformanceAnalysis, self).__init__(*args)
    self.st = StringStats()
    self.st.startDrill.connect(self._forward_drill)
    self.st.corpusTextReady.connect(self._on_corpus_text)
    self._progress = ProgressCard(DB)
    self.setLayout(AppBoxLayout([
        (self._progress, 0),
        (self.st, 1),
      ]))

  def set_session_timer(self, session_timer):
    self._progress.set_session_timer(session_timer)

  def updateAll(self, *args):
    self._progress.update_all()
    self.st.update(*args)

  def showEvent(self, evt):
    self.updateAll()
    return super(PerformanceAnalysis, self).showEvent(evt)

  def _forward_drill(self, targets):
    self.startDrill.emit(targets)
    self.gotoText.emit()

  def _on_corpus_text(self, v):
    self.loadCorpusText.emit(v)
    self.gotoText.emit()

  def hideEvent(self, evt):
    self.st.clear_corpus_msg()
    self.st.clear_search()
    return super(PerformanceAnalysis, self).hideEvent(evt)
