


from amphetype.Data import DB
from amphetype.corpus_find import find_text_for_target
from amphetype.stats_query import (
  ALL_TIME_HIST, ANALYSIS_OUTER_SQL, STATS_AGG_SUBQUERY, STAT_TYPE_WORD,
  analysis_min_count, analysis_order_clause, analysis_order_sql,
  delete_stat_target, fetch_analysis_search, fetch_first_sample_wpm)
from amphetype.word_progress import lifetime_wpm_gain
from amphetype.WeakSpotLessons import analysis_what_kind
from amphetype.QtUtil import *
from amphetype.Config import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QLabel, QMenu, QLineEdit, QMessageBox



class WordModel(AmphModel):
  def __init__(self):
    self.words = []
    self._words_mode = False
    super(WordModel, self).__init__()

  def signature(self):
    hdr = ["Type target", "Speed", "Hesitation", "Count", "Perfect", "Drilled", "Impact"]
    fmt = [None, "%.1f wpm", "%.1f", None, None, None, "%.1f"]
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




class AnalysisSortCombo(QComboBox):
  SORT_OPTIONS = [
    ('wpm asc', 'slowest'),
    ('wpm desc', 'fastest'),
    ('viscosity desc', 'most hesitation'),
    ('viscosity asc', 'least hesitation'),
    ('perfect_pct asc', 'lowest perfect %'),
    ('perfect_pct desc', 'highest perfect %'),
    ('total desc', 'most common'),
    ('damage desc', 'most damaging'),
    ('improved desc', 'most improved'),
  ]

  def __init__(self):
    super(AnalysisSortCombo, self).__init__()
    self._keys = []
    Settings.signal_for('analysis_what').connect(self._sync_items)
    Settings.signal_for('analysis_which').connect(self._sync_selection)
    self.activated[int].connect(lambda idx: Settings.set('analysis_which', self._keys[idx]))
    self._sync_items()

  def _words_only(self):
    return Settings.get('analysis_what') == 2

  def _sync_items(self):
    words = self._words_only()
    cur = Settings.get('analysis_which')
    if not words and cur == 'improved desc':
      Settings.set('analysis_which', 'damage desc')
      cur = 'damage desc'
    if cur in ('accuracy asc', 'misses desc', 'perfect asc'):
      Settings.set('analysis_which', 'perfect_pct asc')
      cur = 'perfect_pct asc'
    elif cur == 'perfect desc':
      Settings.set('analysis_which', 'perfect_pct desc')
      cur = 'perfect_pct desc'
    self.blockSignals(True)
    self.clear()
    self._keys = []
    for k, v in self.SORT_OPTIONS:
      if k == 'improved desc' and not words:
        continue
      self.addItem(v)
      self._keys.append(k)
    self._sync_selection()
    self.blockSignals(False)

  def _sync_selection(self):
    cur = Settings.get('analysis_which')
    if cur not in self._keys:
      return
    self.blockSignals(True)
    self.setCurrentIndex(self._keys.index(cur))
    self.blockSignals(False)


class AnalysisCountEdit(SettingsEdit):
  """Performance Analysis minimum-count filter; never below 2."""
  _MIN = 2

  def __init__(self):
    if Settings.get('analysis_count') < self._MIN:
      Settings.set('analysis_count', self._MIN)
    super(AnalysisCountEdit, self).__init__('analysis_count')

  def updateVal(self):
    try:
      v = max(self._MIN, self.conv(self.text()))
    except ValueError as err:
      QMessageBox.warning(self, "String Conversion Error", f"Couldn't convert setting value:\n{err}")
    else:
      Settings.set(self.setting, v)
      if self.text() != self.fmt(v):
        self.setText(self.fmt(v))


class StringStats(QWidget):
  startDrill = pyqtSignal(list)
  corpusTextReady = pyqtSignal('PyQt_PyObject')
  statsChanged = pyqtSignal()

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
    tw.doubleClicked['QModelIndex'].connect(self._stats_double_click)
    self.stats = tw
    self._corpus_lbl = QLabel()
    self._corpus_lbl.setStyleSheet('color: #c44;')
    self._corpus_lbl.hide()

    ob = AnalysisSortCombo()

    wc = SettingsCombo('analysis_what', ['keys', 'trigrams', 'words'])
    lim = SettingsEdit('analysis_many')
    self.w_count = AnalysisCountEdit()
    self._baseline_rows = []
    self._search_applied = None
    self._search_edit = QLineEdit()
    self._search_edit.setPlaceholderText('target…')
    self._search_btn = AmphButton('Search', self._on_search_btn)
    self._search_edit.textChanged.connect(self._sync_search_btn)
    self._search_edit.returnPressed.connect(self._apply_search)

    Settings.signal_for("analysis_which").connect(self.update)
    Settings.signal_for("analysis_what").connect(self.update)
    Settings.signal_for("analysis_many").connect(self.update)
    Settings.signal_for("analysis_count").connect(self.update)

    self.setLayout(AmphBoxLayout([
        ["Show", wc, "sorted by", ob, 16, self._search_edit, self._search_btn, None],
        ["Limit list to", lim, "items and don't show items with a count less than", self.w_count, None],
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
      DB, ALL_TIME_HIST,
      Settings.get('analysis_what'), Settings.get('analysis_count'), term,
      'total desc' if Settings.get('analysis_which') == 'improved desc' else analysis_order_clause(Settings.get('analysis_which')))
    self._search_applied = term
    cat = Settings.get('analysis_what')
    rows = self._finalize_rows(rows, cat, Settings.get('analysis_which'))
    self.model.setData(rows)
    self._sync_search_btn()

  def _show_corpus_msg(self, msg):
    self._corpus_lbl.setText(msg)
    self._corpus_lbl.show()

  def _query_rows(self, order, limit):
    cat = Settings.get('analysis_what')
    count = analysis_min_count(cat, Settings.get('analysis_count'))
    if order == 'improved desc':
      pool = max(limit * 10, 200)
      sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'total desc', pool)
      rows = DB.fetchall(sql, (ALL_TIME_HIST, cat, count))
      return rows, cat
    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, analysis_order_sql(order), limit)
    return DB.fetchall(sql, (ALL_TIME_HIST, cat, count)), cat

  def _enrich_word_rows(self, rows):
    if not rows:
      return rows
    first = fetch_first_sample_wpm(DB, STAT_TYPE_WORD, [r[0] for r in rows])
    out = []
    for r in rows:
      imp = None
      if r[3] >= 2:
        imp = lifetime_wpm_gain(r[1], first.get(r[0]))
      out.append(list(r[:2]) + [imp] + list(r[2:]))
    return out

  def _finalize_rows(self, rows, cat, order, limit=None):
    self.model.set_words_mode(cat == 2)
    if cat == 2 and rows:
      rows = self._enrich_word_rows(rows)
      if order == 'improved desc':
        rows.sort(key=lambda r: r[2] if r[2] is not None else -999999, reverse=True)
        if limit is not None:
          rows = rows[:limit]
    return rows

  def update(self, *arg):
    self.clear_corpus_msg()
    order = Settings.get('analysis_which')
    limit = Settings.get('analysis_many')
    rows, cat = self._query_rows(order, limit)
    rows = self._finalize_rows(rows, cat, order, limit)
    self._baseline_rows = list(rows)
    if self._search_applied is not None:
      self._apply_search()
    else:
      self.model.setData(rows)

  def _targets_from_rows(self, rows, cat):
    kind = analysis_what_kind(cat)
    return [(kind, r[0], r[1]) for r in rows]

  def _row_idx(self, idx):
    return idx if idx.isValid() else None

  def _drill_row(self, idx):
    if idx is None or idx.row() >= len(self.model.words):
      return
    cat = Settings.get('analysis_what')
    self.startDrill.emit(self._targets_from_rows([self.model.words[idx.row()]], cat))

  def _find_in_corpus(self, idx):
    if idx is None or idx.row() >= len(self.model.words):
      return
    cat = Settings.get('analysis_what')
    row = self.model.words[idx.row()]
    kind = analysis_what_kind(cat)
    v = find_text_for_target(DB, kind, row[0])
    if v:
      self.clear_corpus_msg()
      self.corpusTextReady.emit(v)
    else:
      self._show_corpus_msg('No corpus text found for %r.' % row[0])

  def _stats_double_click(self, idx):
    self._open_stats_menu(idx)

  def _stats_context_menu(self, pos):
    idx = self._row_idx(self.stats.indexAt(pos))
    self._open_stats_menu(idx, pos)

  def _open_stats_menu(self, idx, pos=None):
    if idx is None or idx.row() >= len(self.model.words):
      return
    row = self.model.words[idx.row()]
    menu = QMenu(self)
    drill_act = menu.addAction('Drill')
    find_act = menu.addAction('Find in corpus')
    delete_act = menu.addAction('Delete from database')
    if pos is None:
      rect = self.stats.visualRect(idx)
      global_pos = self.stats.viewport().mapToGlobal(rect.center())
    else:
      global_pos = self.stats.viewport().mapToGlobal(pos)
    picked = menu.exec_(global_pos)
    if picked == drill_act:
      self._drill_row(idx)
    elif picked == find_act:
      self._find_in_corpus(idx)
    elif picked == delete_act:
      self._delete_target(idx)

  def _delete_target(self, idx):
    if idx is None or idx.row() >= len(self.model.words):
      return
    cat = Settings.get('analysis_what')
    data = self.model.words[idx.row()][0]
    if QMessageBox.question(
        self, 'Delete from database',
        'Delete all statistics for %r?\nThis cannot be undone.' % data,
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
      return
    delete_stat_target(DB, cat, data)
    DB.commit()
    self.statsChanged.emit()
    self.update()
