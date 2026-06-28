
from amphetype.Config import Settings, SettingsEdit
from amphetype.Data import DB
from amphetype.QtUtil import *
from amphetype.Performance import PerformanceHistory, perf_hist_cutoff
from amphetype.StatWidgets import StringStats
from amphetype.stats_query import STAT_TYPE_TRIGRAM, STAT_TYPE_WORD, average_result_wpm, count_unique_typed

from PyQt5.QtCore import *
from PyQt5.QtWidgets import QLabel, QTabWidget


class PerformanceAnalysis(QWidget):
  setText = pyqtSignal('PyQt_PyObject')
  gotoText = pyqtSignal()
  startDrill = pyqtSignal(list)
  loadCorpusText = pyqtSignal('PyQt_PyObject')

  def __init__(self, *args):
    super(PerformanceAnalysis, self).__init__(*args)
    self.ph = PerformanceHistory()
    self.st = StringStats()
    self.ph.setText.connect(self.setText.emit)
    self.ph.gotoText.connect(self.gotoText.emit)
    self.st.startDrill.connect(self._forward_drill)
    self.st.corpusTextReady.connect(self._on_corpus_text)
    Settings.signal_for("history").connect(self.updateAll)
    _counter_style = 'font-size: 15px; padding: 2px 0;'
    self._words_lbl = QLabel()
    self._trigrams_lbl = QLabel()
    self._wpm_lbl = QLabel()
    self._words_lbl.setStyleSheet(_counter_style)
    self._trigrams_lbl.setStyleSheet(_counter_style)
    self._wpm_lbl.setStyleSheet(_counter_style)
    subtabs = QTabWidget()
    subtabs.addTab(self.st, "Stats")
    subtabs.addTab(self.ph, "Progress")
    self.subtabs = subtabs
    subtabs.currentChanged.connect(lambda *_: self.st.clear_corpus_msg())
    self.setLayout(AmphBoxLayout([
        ["Last", SettingsEdit("history"), "days.", 16, self._words_lbl, 16, self._trigrams_lbl, 16, self._wpm_lbl, None],
        (subtabs, 1),
      ]))

  def refreshSources(self):
    self.ph.refreshSources()

  def updateData(self, *args):
    self.ph.updateData(*args)

  def updateAll(self, *args):
    hist = perf_hist_cutoff()
    words = count_unique_typed(DB, hist, STAT_TYPE_WORD)
    tris = count_unique_typed(DB, hist, STAT_TYPE_TRIGRAM)
    self._words_lbl.setText('Unique words typed: %d' % words)
    self._trigrams_lbl.setText('Unique trigrams typed: %d' % tris)
    avg_wpm = average_result_wpm(DB, hist)
    self._wpm_lbl.setText('Average WPM: %s' % ('%.1f' % avg_wpm if avg_wpm is not None else '—'))
    self.ph.updateData(*args)
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
