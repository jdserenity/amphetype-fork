"""Performance Analysis progress card — session stats header."""

from typing_program.speed_heatmap import PROGRESS_GREEN
from typing_program.stats_query import (
  ALL_TIME_HIST, count_analysis_words, format_avg_wpm_label, format_wpm_gate_label,
  session_wpm_since_start_gain,
)
from typing_program.QtUtil import *

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QSizePolicy, QWidget


_CARD_STYLE = (
  'ProgressCard { background: rgba(0, 0, 0, 0.06); border: 1px solid rgba(0, 0, 0, 0.12);'
  ' border-radius: 6px; }')
_HERO_NUM_STYLE = 'font-size: 24px; font-weight: 700; padding: 0; margin: 0;'
_HERO_CAP_STYLE = 'font-size: 11px; color: #666; padding: 0; margin: 0;'
_STAT_STYLE = 'font-size: 15px; padding: 2px 0;'
_METRIC_GAP = 32


class ProgressCard(QWidget):
  def __init__(self, db, hist_cutoff=ALL_TIME_HIST, parent=None):
    super(ProgressCard, self).__init__(parent)
    self._db = db
    self._hist = hist_cutoff
    self.setObjectName('ProgressCard')
    self.setStyleSheet(_CARD_STYLE)

    self._gain_num = QLabel(parent=self)
    self._gain_cap = QLabel('WPM since start', parent=self)
    self._gain_num.setStyleSheet(_HERO_NUM_STYLE)
    self._gain_cap.setStyleSheet(_HERO_CAP_STYLE)
    gain_col = QWidget(parent=self)
    gain_lay = QVBoxLayout(gain_col)
    gain_lay.setContentsMargins(0, 0, 0, 0)
    gain_lay.setSpacing(0)
    gain_lay.addWidget(self._gain_num, 0)
    gain_lay.addWidget(self._gain_cap, 0)

    self._wpm_lbl = QLabel(parent=self)
    self._words_lbl = QLabel(parent=self)
    self._practice_lbl = QLabel(parent=self)
    for lbl in (self._wpm_lbl, self._words_lbl, self._practice_lbl):
      lbl.setStyleSheet(_STAT_STYLE)
    self._session_timer = None

    row = QWidget(parent=self)
    row_lay = QHBoxLayout(row)
    row_lay.setContentsMargins(12, 10, 12, 10)
    row_lay.setSpacing(_METRIC_GAP)
    row_lay.addWidget(gain_col, 0, Qt.AlignVCenter)
    row_lay.addWidget(self._wpm_lbl, 0, Qt.AlignVCenter)
    row_lay.addWidget(self._words_lbl, 0, Qt.AlignVCenter)
    row_lay.addWidget(self._practice_lbl, 0, Qt.AlignVCenter)
    row_lay.addStretch(1)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(row, 0)
    self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

  def set_session_timer(self, session_timer):
    self._session_timer = session_timer

  def _practice_time_text(self):
    from typing_program.session_timer import format_practice_total_label, total_practice_seconds_from_db
    if self._session_timer is not None:
      secs = self._session_timer.total_seconds()
    else:
      secs = total_practice_seconds_from_db(self._db)
    return 'Total practice time: %s' % format_practice_total_label(secs)

  def update_all(self):
    words = count_analysis_words(self._db, self._hist)
    self._words_lbl.setText('Unique common words typed: %d' % words)
    self._wpm_lbl.setText(format_avg_wpm_label(self._db, self._hist))
    self._practice_lbl.setText(self._practice_time_text())
    gate = format_wpm_gate_label(self._db)
    if gate:
      self._gain_num.setText('—')
      self._gain_num.setStyleSheet(_HERO_NUM_STYLE + ' color: #888;')
      self._gain_cap.setText(gate)
      return
    gain = session_wpm_since_start_gain(self._db, self._hist)
    self._gain_cap.setText('WPM since start')
    if gain is None:
      self._gain_num.setText('—')
      self._gain_num.setStyleSheet(_HERO_NUM_STYLE + ' color: #888;')
    elif gain > 0:
      self._gain_num.setText('+%d' % gain)
      self._gain_num.setStyleSheet(_HERO_NUM_STYLE + ' color: %s;' % PROGRESS_GREEN)
    elif gain < 0:
      self._gain_num.setText('%d' % gain)
      self._gain_num.setStyleSheet(_HERO_NUM_STYLE + ' color: #c44;')
    else:
      self._gain_num.setText('+0')
      self._gain_num.setStyleSheet(_HERO_NUM_STYLE + ' color: #888;')
