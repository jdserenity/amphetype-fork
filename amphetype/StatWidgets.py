


import time

from amphetype.Data import DB
from amphetype.corpus_find import find_text_for_target
from amphetype.stats_query import ANALYSIS_OUTER_SQL, ANALYSIS_ORDER_OPTIONS, STATS_AGG_SUBQUERY, analysis_order_clause, fetch_analysis_search, fetch_oblivion_picks
from amphetype.speed_heatmap import OBLIVION_WPM
from amphetype.WeakSpotLessons import ana_what_kind
from amphetype.QtUtil import *
from amphetype.Config import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QLabel, QMenu, QLineEdit



class WordModel(AmphModel):
  def signature(self):
    self.words = []
    return (["Type target", "Speed", "Accuracy", "Hesitation", "Count", "Mistakes", "Drilled", "Impact"],
        [None, "%.1f wpm", "%.1f%%", "%.1f", None, None, None, "%.1f"])

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

    ob = SettingsCombo('ana_which', ANALYSIS_ORDER_OPTIONS)

    wc = SettingsCombo('ana_what', ['keys', 'trigrams', 'words'])
    lim = SettingsEdit('ana_many')
    self.w_count = SettingsEdit('ana_count')
    self._baseline_rows = []
    self._search_applied = None
    self._search_edit = QLineEdit()
    self._search_edit.setPlaceholderText('target…')
    self._search_btn = AmphButton('Search', self._on_search_btn)
    self._search_edit.textChanged.connect(self._sync_search_btn)
    self._search_edit.returnPressed.connect(self._apply_search)

    Settings.signal_for("ana_which").connect(self.update)
    Settings.signal_for("ana_what").connect(self.update)
    Settings.signal_for("ana_many").connect(self.update)
    Settings.signal_for("ana_count").connect(self.update)
    Settings.signal_for("history").connect(self.update)

    self.setLayout(AmphBoxLayout([
        ["Show", wc, "sorted by", ob, None,
          AmphButton("Drill worst 3", self._drill_worst_3),
          AmphButton("Drill 3 oblivion", self._drill_3_oblivion)],
        ["Limit list to", lim, "items and don't show items with a count less than", self.w_count, None],
        ["Search", self._search_edit, self._search_btn, None],
        self._corpus_lbl,
        (self.stats, 1)
      ]))

  def clear_corpus_msg(self):
    self._corpus_lbl.hide()
    self._corpus_lbl.clear()

  def clear_search(self):
    self._search_applied = None
    self._search_edit.clear()
    self.model.setData(self._baseline_rows)
    self._sync_search_btn()

  def _sync_search_btn(self):
    term = self._search_edit.text()
    if self._search_applied is not None and term == self._search_applied:
      self._search_btn.setText('Clear')
    else:
      self._search_btn.setText('Search')

  def _on_search_btn(self):
    if self._search_btn.text() == 'Clear':
      self.clear_search()
    else:
      self._apply_search()

  def _apply_search(self):
    term = self._search_edit.text().strip()
    if not term:
      return
    rows = fetch_analysis_search(
      DB, time.time() - Settings.get('history') * 86400.0,
      Settings.get('ana_what'), Settings.get('ana_count'), term, analysis_order_clause(Settings.get('ana_which')))
    self._search_applied = term
    self.model.setData(rows)
    self._sync_search_btn()

  def _show_corpus_msg(self, msg):
    self._corpus_lbl.setText(msg)
    self._corpus_lbl.show()

  def _query_rows(self, order, limit):
    cat = Settings.get('ana_what')
    count = Settings.get('ana_count')
    hist = time.time() - Settings.get('history') * 86400.0
    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, analysis_order_clause(order), limit)
    return DB.fetchall(sql, (hist, cat, count)), cat

  def update(self, *arg):
    self.clear_corpus_msg()
    rows, _ = self._query_rows(analysis_order_clause(Settings.get('ana_which')), Settings.get('ana_many'))
    self._baseline_rows = list(rows)
    if self._search_applied is not None:
      self._apply_search()
    else:
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

  def _drill_worst_3(self):
    rows, cat = self._query_rows('damage desc', 3)
    if not rows:
      return
    self.startDrill.emit(self._targets_from_rows(rows[:3], cat))

  def _drill_3_oblivion(self):
    cat = Settings.get('ana_what')
    hist = time.time() - Settings.get('history') * 86400.0
    picks = fetch_oblivion_picks(DB, hist, cat, 3, OBLIVION_WPM)
    if not picks:
      return
    self.startDrill.emit(self._targets_from_rows(picks, cat))
