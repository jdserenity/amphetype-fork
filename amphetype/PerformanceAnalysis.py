
from amphetype.Data import DB
from amphetype.QtUtil import *
from amphetype.StatWidgets import StringStats
from amphetype.stats_query import (
  ALL_TIME_HIST, STAT_TYPE_WORD, aggregate_session_wpm_from_results,
  count_analysis_words,
)

from PyQt5.QtCore import *
from PyQt5.QtWidgets import QLabel


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
    _counter_style = 'font-size: 15px; padding: 2px 0;'
    self._words_lbl = QLabel()
    self._wpm_lbl = QLabel()
    self._words_lbl.setStyleSheet(_counter_style)
    self._wpm_lbl.setStyleSheet(_counter_style)
    self.setLayout(AmphBoxLayout([
        [self._words_lbl, 16, self._wpm_lbl, None],
        (self.st, 1),
      ]))

  def updateAll(self, *args):
    words = count_analysis_words(DB, ALL_TIME_HIST)
    avg_wpm = aggregate_session_wpm_from_results(DB, ALL_TIME_HIST)
    self._words_lbl.setText('Unique words typed: %d' % words)
    self._wpm_lbl.setText('Avg WPM: %s' % ('%.1f' % avg_wpm if avg_wpm is not None else '—'))
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
