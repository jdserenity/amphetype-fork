


import random
import time

from amphetype.Data import DB
from amphetype.stats_query import ANALYSIS_OUTER_SQL, STATS_AGG_SUBQUERY
from amphetype.speed_heatmap import OBLIVION_WPM
from amphetype.WeakSpotLessons import ana_what_kind
from amphetype.QtUtil import *
from amphetype.Config import *

from PyQt5.QtCore import *
from PyQt5.QtGui import *



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

  def __init__(self, *args):
    super(StringStats, self).__init__(*args)

    self.model = WordModel()
    tw = AmphTree(self.model)
    tw.setIndentation(0)
    tw.setUniformRowHeights(True)
    tw.setRootIsDecorated(False)
    tw.setAlternatingRowColors(True)
    tw.setMinimumHeight(220)
    tw.doubleClicked['QModelIndex'].connect(self._drill_row)
    self.stats = tw

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
        ["Show", wc, "sorted by", ob, None,
          AmphButton("Drill worst 3", self._drill_worst_3),
          AmphButton("Drill 3 oblivion", self._drill_3_oblivion)],
        ["Limit list to", lim, "items and don't show items with a count less than", self.w_count, None],
        (self.stats, 1)
      ]))

  def _query_rows(self, order, limit):
    cat = Settings.get('ana_what')
    count = Settings.get('ana_count')
    hist = time.time() - Settings.get('history') * 86400.0
    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, order, limit)
    return DB.fetchall(sql, (hist, cat, count)), cat

  def update(self, *arg):
    rows, _ = self._query_rows(Settings.get('ana_which'), Settings.get('ana_many'))
    self.model.setData(rows)

  def _targets_from_rows(self, rows, cat):
    kind = ana_what_kind(cat)
    return [(kind, r[0], r[1]) for r in rows]

  def _drill_row(self, idx):
    if not idx.isValid() or idx.row() >= len(self.model.words):
      return
    cat = Settings.get('ana_what')
    self.startDrill.emit(self._targets_from_rows([self.model.words[idx.row()]], cat))

  def _drill_worst_3(self):
    rows, cat = self._query_rows('damage desc', 3)
    if not rows:
      return
    self.startDrill.emit(self._targets_from_rows(rows[:3], cat))

  def _drill_3_oblivion(self):
    rows, cat = self._query_rows('wpm asc', Settings.get('ana_many'))
    pool = [r for r in rows if r[1] is not None and r[1] < OBLIVION_WPM]
    if not pool:
      return
    picks = random.sample(pool, min(3, len(pool)))
    self.startDrill.emit(self._targets_from_rows(picks, cat))
