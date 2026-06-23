


import time

from amphetype.Data import DB
from amphetype.corpus_find import find_text_for_target
from amphetype.stats_query import ANALYSIS_OUTER_SQL, STATS_AGG_SUBQUERY, STAT_TYPE_WORD, fetch_first_sample_wpm
from amphetype.word_progress import lifetime_wpm_gain
from amphetype.WeakSpotLessons import ana_what_kind
from amphetype.QtUtil import *
from amphetype.Config import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QLabel, QMenu



class WordModel(AmphModel):
  def __init__(self):
    super(WordModel, self).__init__()
    self.words = []
    self._words_mode = False

  def signature(self):
    hdr = ["Type target", "Speed", "Accuracy", "Hesitation", "Count", "Mistakes", "Drilled", "Impact"]
    fmt = [None, "%.1f wpm", "%.1f%%", "%.1f", None, None, None, "%.1f"]
    if self._words_mode:
      hdr = hdr[:2] + ["Improved"] + hdr[2:]
      fmt = fmt[:2] + ["%+d"] + fmt[2:]
    return (hdr, fmt)

  def set_words_mode(self, on):
    on = bool(on)
    if on == self._words_mode:
      return
    self._words_mode = on
    self.head, self.fmt = self.signature()
    self.cols = len(self.head)

  def populateData(self, idx):
    if len(idx) != 0:
      return []

    return self.words

  def setData(self, words):
    self.words = list(map(list, words))
    self.reset()




class StringStats(QWidget):
  startDrill = pyqtSignal(list)
  corpusTextReady = pyqtSignal('PyQt_PyObject')

  def __init__(self, *args):
    super(StringStats, self).__init__(*args)

    self.model = WordModel()
    tw = AmphTree(self.model)
    tw.setIndentation(0)
    tw.setUniformRowHeights(True)
    tw.setRootIsDecorated(False)
    tw.setAlternatingRowColors(True)
    tw.setMinimumHeight(220)
    tw.setContextMenuPolicy(Qt.CustomContextMenu)
    tw.customContextMenuRequested.connect(self._stats_context_menu)
    self.stats = tw
    self._corpus_lbl = QLabel()
    self._corpus_lbl.setStyleSheet('color: #c44;')
    self._corpus_lbl.hide()

    ob = SettingsCombo('ana_which', [
          ('wpm asc', 'slowest'),
          ('wpm desc', 'fastest'),
          ('viscosity desc', 'most hesitation'),
          ('viscosity asc', 'least hesitation'),
          ('accuracy asc', 'least accurate'),
          ('misses desc', 'most mistyped'),
          ('total desc', 'most common'),
          ('damage desc', 'most damaging'),
          ])

    wc = SettingsCombo('ana_what', ['keys', 'trigrams', 'words'])
    lim = SettingsEdit('ana_many')
    self.w_count = SettingsEdit('ana_count')

    Settings.signal_for("ana_which").connect(self.update)
    Settings.signal_for("ana_what").connect(self.update)
    Settings.signal_for("ana_many").connect(self.update)
    Settings.signal_for("ana_count").connect(self.update)
    Settings.signal_for("history").connect(self.update)

    self.setLayout(AmphBoxLayout([
        ["Show", wc, "sorted by", ob, None],
        ["Limit list to", lim, "items and don't show items with a count less than", self.w_count, None],
        self._corpus_lbl,
        (self.stats, 1)
      ]))

  def clear_corpus_msg(self):
    self._corpus_lbl.hide()
    self._corpus_lbl.clear()

  def _show_corpus_msg(self, msg):
    self._corpus_lbl.setText(msg)
    self._corpus_lbl.show()

  def _query_rows(self, order, limit):
    cat = Settings.get('ana_what')
    count = Settings.get('ana_count')
    hist = time.time() - Settings.get('history') * 86400.0
    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, order, limit)
    return DB.fetchall(sql, (hist, cat, count)), cat

  def update(self, *arg):
    self.clear_corpus_msg()
    rows, cat = self._query_rows(Settings.get('ana_which'), Settings.get('ana_many'))
    self.model.set_words_mode(cat == 2)
    if cat == 2 and rows:
      first = fetch_first_sample_wpm(DB, STAT_TYPE_WORD, [r[0] for r in rows])
      rows = [list(r[:2]) + [lifetime_wpm_gain(r[1], first.get(r[0]))] + list(r[2:]) for r in rows]
    self.model.setData(rows)

  def _targets_from_rows(self, rows, cat):
    kind = ana_what_kind(cat)
    return [(kind, r[0], r[1]) for r in rows]

  def _row_idx(self, idx):
    return idx if idx.isValid() else None

  def _drill_row(self, idx):
    if idx is None or idx.row() >= len(self.model.words):
      return
    cat = Settings.get('ana_what')
    self.startDrill.emit(self._targets_from_rows([self.model.words[idx.row()]], cat))

  def _find_in_corpus(self, idx):
    if idx is None or idx.row() >= len(self.model.words):
      return
    cat = Settings.get('ana_what')
    row = self.model.words[idx.row()]
    kind = ana_what_kind(cat)
    v = find_text_for_target(DB, kind, row[0])
    if v:
      self.clear_corpus_msg()
      self.corpusTextReady.emit(v)
    else:
      self._show_corpus_msg('No corpus text found for %r.' % row[0])

  def _stats_context_menu(self, pos):
    idx = self._row_idx(self.stats.indexAt(pos))
    if idx is None or idx.row() >= len(self.model.words):
      return
    menu = QMenu(self)
    drill_act = menu.addAction('Drill')
    find_act = menu.addAction('Find in corpus')
    picked = menu.exec_(self.stats.viewport().mapToGlobal(pos))
    if picked == drill_act:
      self._drill_row(idx)
    elif picked == find_act:
      self._find_in_corpus(idx)
