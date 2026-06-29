
from amphetype.Config import Settings, SettingsEdit
from amphetype.Data import DB
from amphetype.QtUtil import *
from amphetype.StatWidgets import StringStats
from amphetype.stats_query import STAT_TYPE_TRIGRAM, STAT_TYPE_WORD, count_unique_typed, perf_hist_cutoff

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
    Settings.signal_for("history").connect(self.updateAll)
    _counter_style = 'font-size: 15px; padding: 2px 0;'
    self._words_lbl = QLabel()
    self._trigrams_lbl = QLabel()
    self._words_lbl.setStyleSheet(_counter_style)
    self._trigrams_lbl.setStyleSheet(_counter_style)
    self.setLayout(AmphBoxLayout([
        ["Last", SettingsEdit("history"), "days.", 16, self._words_lbl, 16, self._trigrams_lbl, None],
        (self.st, 1),
      ]))

  def updateAll(self, *args):
    hist = perf_hist_cutoff()
    words = count_unique_typed(DB, hist, STAT_TYPE_WORD)
    tris = count_unique_typed(DB, hist, STAT_TYPE_TRIGRAM)
    self._words_lbl.setText('Unique words typed: %d' % words)
    self._trigrams_lbl.setText('Unique trigrams typed: %d' % tris)
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
