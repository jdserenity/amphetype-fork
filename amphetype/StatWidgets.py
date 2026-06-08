


import time

from amphetype.Data import DB
from amphetype.stats_query import ANALYSIS_OUTER_SQL, STATS_AGG_SUBQUERY
from amphetype.QtUtil import *
from amphetype.Text import LessonGeneratorPlain
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
  def __init__(self, *args):
    super(StringStats, self).__init__(*args)

    self.model = WordModel()
    tw = AmphTree(self.model)
    tw.setIndentation(0)
    tw.setUniformRowHeights(True)
    tw.setRootIsDecorated(False)
    tw.setAlternatingRowColors(True)
    tw.setMinimumHeight(220)
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
        ["Show", wc, "sorted by", ob, None],
        ["Limit list to", lim, "items and don't show items with a count less than", self.w_count, None],
        (self.stats, 1)
      ]))

  def update(self, *arg):

    ord = Settings.get('ana_which')
    cat = Settings.get('ana_what')
    limit = Settings.get('ana_many')
    count = Settings.get('ana_count')
    hist = time.time() - Settings.get('history') * 86400.0

    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, ord, limit)
    self.model.setData(DB.fetchall(sql, (hist, cat, count)))
