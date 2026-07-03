"""Performance Analysis progress card — WPM since start + heatmap climb strip."""

from typing_program.progress_stats import (
  count_all_time_tier_climbs, tier_climb_colors, tier_climb_labels,
)
from typing_program.speed_heatmap import PROGRESS_GREEN, WPM_BUCKET_LABELS, WPM_BUCKETS
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
_HEADER_STYLE = 'font-size: 15px; padding: 2px 0;'
_STRIP_HINT = 'font-size: 11px; color: #888; padding: 0;'
_ARROW_STYLE = 'font-size: 11px; color: #888; padding: 0 2px;'
_COUNT_STYLE = 'font-size: 12px; font-weight: 600; padding: 0 2px;'


def _swatch_style(color, fg='#111'):
  return (
    'QLabel { background: %s; color: %s; min-width: 14px; max-width: 14px; min-height: 14px;'
    ' max-height: 14px; border-radius: 2px; padding: 0; margin: 0; }' % (color, fg))


class ClimbStrip(QWidget):
  def __init__(self, parent=None):
    super(ClimbStrip, self).__init__(parent)
    self._hint = QLabel('Words climbed (all time)', parent=self)
    self._hint.setStyleSheet(_STRIP_HINT)
    self._row = QWidget(parent=self)
    self._row_lay = QHBoxLayout(self._row)
    self._row_lay.setContentsMargins(0, 0, 0, 0)
    self._row_lay.setSpacing(4)
    self._empty = QLabel('No heatmap climbs yet', parent=self)
    self._empty.setStyleSheet(_STRIP_HINT)
    self._empty.hide()
    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lay.addWidget(self._hint, 0, Qt.AlignRight)
    lay.addWidget(self._row, 0, Qt.AlignRight)
    lay.addWidget(self._empty, 0, Qt.AlignRight)

  def _clear_row(self):
    while self._row_lay.count():
      item = self._row_lay.takeAt(0)
      w = item.widget()
      if w is not None:
        w.deleteLater()

  def set_climbs(self, climbs):
    self._clear_row()
    labels = tier_climb_labels()
    colors = tier_climb_colors()
    any_climbs = any(climbs)
    self._row.setVisible(any_climbs)
    self._empty.setVisible(not any_climbs)
    if not any_climbs:
      return
    for i, n in enumerate(climbs):
      if n <= 0:
        continue
      fg = '#fff' if i == 0 else '#111'
      src = QLabel(parent=self._row)
      src.setStyleSheet(_swatch_style(colors[i], fg))
      src.setToolTip(labels[i])
      self._row_lay.addWidget(src, 0)
      cnt = QLabel(str(n), parent=self._row)
      cnt.setStyleSheet(_COUNT_STYLE)
      cnt.setToolTip(labels[i])
      self._row_lay.addWidget(cnt, 0)
      arrow = QLabel('→', parent=self._row)
      arrow.setStyleSheet(_ARROW_STYLE)
      arrow.setToolTip(labels[i])
      self._row_lay.addWidget(arrow, 0)
      nxt_fg = '#fff' if i + 1 == 0 else '#111'
      dst = QLabel(parent=self._row)
      dst.setStyleSheet(_swatch_style(WPM_BUCKETS[i + 1][1], nxt_fg))
      dst.setToolTip(labels[i])
      self._row_lay.addWidget(dst, 0)
      if i < len(climbs) - 1:
        gap = QLabel('  ', parent=self._row)
        self._row_lay.addWidget(gap, 0)


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
    hero_col = QWidget(parent=self)
    hero_lay = QVBoxLayout(hero_col)
    hero_lay.setContentsMargins(0, 0, 0, 0)
    hero_lay.setSpacing(0)
    hero_lay.addWidget(self._gain_num, 0)
    hero_lay.addWidget(self._gain_cap, 0)

    self._words_lbl = QLabel(parent=self)
    self._wpm_lbl = QLabel(parent=self)
    self._words_lbl.setStyleSheet(_HEADER_STYLE)
    self._wpm_lbl.setStyleSheet(_HEADER_STYLE)
    hdr_col = QWidget(parent=self)
    hdr_lay = QVBoxLayout(hdr_col)
    hdr_lay.setContentsMargins(0, 0, 0, 0)
    hdr_lay.setSpacing(0)
    hdr_lay.addWidget(self._words_lbl, 0)
    hdr_lay.addWidget(self._wpm_lbl, 0)

    self._strip = ClimbStrip(parent=self)

    top = QWidget(parent=self)
    top_lay = QHBoxLayout(top)
    top_lay.setContentsMargins(10, 8, 10, 4)
    top_lay.setSpacing(12)
    top_lay.addWidget(hero_col, 0, Qt.AlignTop)
    top_lay.addStretch(1)
    top_lay.addWidget(hdr_col, 0, Qt.AlignTop)

    strip_wrap = QWidget(parent=self)
    strip_lay = QHBoxLayout(strip_wrap)
    strip_lay.setContentsMargins(10, 0, 10, 8)
    strip_lay.addStretch(1)
    strip_lay.addWidget(self._strip, 0)

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(top, 0)
    lay.addWidget(strip_wrap, 0)
    self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

  def update_all(self):
    words = count_analysis_words(self._db, self._hist)
    self._words_lbl.setText('Unique common words typed: %d' % words)
    self._wpm_lbl.setText(format_avg_wpm_label(self._db, self._hist))
    gate = format_wpm_gate_label(self._db)
    if gate:
      self._gain_num.setText('—')
      self._gain_num.setStyleSheet(_HERO_NUM_STYLE + ' color: #888;')
      self._gain_cap.setText(gate)
      self._strip.setVisible(False)
      return
    gain = session_wpm_since_start_gain(self._db, self._hist)
    self._gain_cap.setText('WPM since start')
    self._strip.setVisible(True)
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
