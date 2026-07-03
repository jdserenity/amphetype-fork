"""Performance Analysis progress card — WPM since start + heatmap climb strip."""

from typing_program.progress_stats import (
  count_all_time_tier_climbs, tier_climb_colors, tier_climb_labels,
)
from typing_program.speed_heatmap import PROGRESS_GREEN, WPM_BUCKETS
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
_ARROW_STYLE = 'font-size: 11px; color: #888; padding: 0 2px;'
_COUNT_STYLE = 'font-size: 12px; font-weight: 600; padding: 0 2px;'


def _swatch_style(color, fg='#111'):
  return (
    'QLabel { background: %s; color: %s; min-width: 14px; max-width: 14px; min-height: 14px;'
    ' max-height: 14px; border-radius: 2px; padding: 0; margin: 0; }' % (color, fg))


class ClimbStrip(QWidget):
  def __init__(self, parent=None):
    super(ClimbStrip, self).__init__(parent)
    self._row_lay = QHBoxLayout(self)
    self._row_lay.setContentsMargins(0, 0, 0, 0)
    self._row_lay.setSpacing(4)

  def _clear_row(self):
    while self._row_lay.count():
      item = self._row_lay.takeAt(0)
      w = item.widget()
      if w is not None:
        w.deleteLater()

  def _add_swatch(self, color, tip, fg='#111'):
    if color == WPM_BUCKETS[0][1]:
      fg = '#fff'
    lbl = QLabel(parent=self)
    lbl.setStyleSheet(_swatch_style(color, fg))
    lbl.setToolTip(tip)
    self._row_lay.addWidget(lbl, 0)

  def set_climbs(self, climbs):
    self._clear_row()
    labels = tier_climb_labels()
    colors = tier_climb_colors()
    active = [(i, n) for i, n in enumerate(climbs) if n > 0]
    if not active:
      self.hide()
      return
    self.show()
    first_i, first_n = active[0]
    self._add_swatch(colors[first_i], labels[first_i])
    cnt = QLabel(str(first_n), parent=self)
    cnt.setStyleSheet(_COUNT_STYLE)
    cnt.setToolTip(labels[first_i])
    self._row_lay.addWidget(cnt, 0)
    arrow = QLabel('→', parent=self)
    arrow.setStyleSheet(_ARROW_STYLE)
    arrow.setToolTip(labels[first_i])
    self._row_lay.addWidget(arrow, 0)
    self._add_swatch(WPM_BUCKETS[first_i + 1][1], labels[first_i])
    for i, n in active[1:]:
      cnt = QLabel(str(n), parent=self)
      cnt.setStyleSheet(_COUNT_STYLE)
      cnt.setToolTip(labels[i])
      self._row_lay.addWidget(cnt, 0)
      arrow = QLabel('→', parent=self)
      arrow.setStyleSheet(_ARROW_STYLE)
      arrow.setToolTip(labels[i])
      self._row_lay.addWidget(arrow, 0)
      self._add_swatch(WPM_BUCKETS[i + 1][1], labels[i])


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

    self._strip = ClimbStrip(parent=self)
    self._strip.hide()

    top = QWidget(parent=self)
    top_lay = QHBoxLayout(top)
    top_lay.setContentsMargins(10, 8, 10, 4)
    top_lay.setSpacing(16)
    top_lay.addWidget(gain_col, 0, Qt.AlignVCenter)
    top_lay.addWidget(self._wpm_lbl, 0, Qt.AlignVCenter)
    top_lay.addWidget(self._words_lbl, 0, Qt.AlignVCenter)
    top_lay.addWidget(self._practice_lbl, 0, Qt.AlignVCenter)
    top_lay.addStretch(1)

    strip_wrap = QWidget(parent=self)
    strip_lay = QHBoxLayout(strip_wrap)
    strip_lay.setContentsMargins(10, 0, 10, 8)
    strip_lay.addStretch(1)
    strip_lay.addWidget(self._strip, 0, Qt.AlignRight)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(top, 0)
    lay.addWidget(strip_wrap, 0)
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
      self._strip.hide()
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
    self._strip.set_climbs(count_all_time_tier_climbs(self._db))
