"""Speed heatmap: map lesson text to WPM bucket colors from statistic DB."""

import re

from amphetype.stats_query import ALL_TIME_HIST

MODE_WORD = 0
MODE_TRIGRAM = 1
MODE_CHAR = 2
MODE_LABELS = ('words', 'trigrams', 'chars')
_STAT_TYPE = {MODE_WORD: 2, MODE_TRIGRAM: 1, MODE_CHAR: 0}


def mode_stat_type(mode):
  return _STAT_TYPE[mode]

# Stoplight buckets — bright, full saturation (legend + underlines).
OBLIVION_WPM = 32
WPM_GREEN = '#00e676'
PROGRESS_GREEN = WPM_GREEN
PROGRESS_RED = '#d64545'
PROGRESS_ORANGE = '#ff8c00'
WPM_BUCKETS = (
  (0, '#a855f7'),     # 0–31 (oblivion)
  (32, '#d64545'),    # 32–54
  (55, '#ff8c00'),    # 55–77
  (78, '#ffd600'),    # 78–99
  (100, WPM_GREEN),   # 100+
)
WPM_BUCKET_LABELS = ('<31', '32–54', '55–77', '78–99', '100+')

_WORD_RE = re.compile(r"\w+(?:['-]\w+)*")


def spc_to_wpm(spc):
  return 12.0 / spc


def wpm_color(wpm):
  if wpm is None:
    return None
  color = WPM_BUCKETS[0][1]
  for threshold, c in WPM_BUCKETS:
    if wpm >= threshold:
      color = c
  return color


def wpm_color_q(wpm):
  from PyQt5.QtGui import QColor
  hex_c = wpm_color(wpm)
  return QColor(hex_c) if hex_c else None


def _stat_wpm(entry):
  if isinstance(entry, dict):
    return entry['wpm']
  return entry


def _stat_damage(entry):
  if isinstance(entry, dict):
    return entry.get('damage') or 0.0
  return 0.0


def fetch_speed_stats(db, hist_cutoff=ALL_TIME_HIST, stat_type=MODE_CHAR):
  from amphetype.stats_query import SPEED_STATS_SQL, SPEED_STATS_ALL_TIME_SQL
  if hist_cutoff <= 0:
    rows = db.execute(SPEED_STATS_ALL_TIME_SQL, (stat_type,)).fetchall()
  else:
    rows = db.execute(SPEED_STATS_SQL, (hist_cutoff, stat_type)).fetchall()
  return {data: {'wpm': wpm, 'damage': damage or 0.0} for data, wpm, damage in rows}


def _trigram_colors_by_damage(text, stats):
  """Non-overlapping 3-char blocks; highest damage wins contested spans."""
  n = len(text)
  colors = [None] * n
  cands = []
  for i in range(n - 2):
    tri = text[i:i + 3]
    if tri not in stats:
      continue
    cands.append((i, _stat_wpm(stats[tri]), _stat_damage(stats[tri])))
  cands.sort(key=lambda x: (-x[2], -x[1], x[0]))
  used = [False] * n
  for i, wpm, _ in cands:
    if any(used[i:i + 3]):
      continue
    col = wpm_color_q(wpm)
    for j in range(i, i + 3):
      colors[j] = col; used[j] = True
  # Aligned triples left blank (e.g. tail gap) — still solid blocks, no overlap.
  for i in range(0, n - 2, 3):
    if any(colors[i:i + 3]):
      continue
    tri = text[i:i + 3]
    if tri not in stats:
      continue
    col = wpm_color_q(_stat_wpm(stats[tri]))
    for j in range(i, i + 3):
      colors[j] = col
  return colors


def _word_spans(text):
  for m in _WORD_RE.finditer(text):
    yield m.start(), m.end(), m.group(0)


def _colors_for_match_text(text, mode, stats):
  n = len(text)
  colors = [None] * n
  if mode == MODE_CHAR:
    for i, ch in enumerate(text):
      if ch in stats:
        colors[i] = wpm_color_q(_stat_wpm(stats[ch]))
  elif mode == MODE_TRIGRAM:
    return _trigram_colors_by_damage(text, stats)
  else:
    for start, end, word in _word_spans(text):
      entry = stats.get(word)
      if entry is not None:
        c = wpm_color_q(_stat_wpm(entry))
        for i in range(start, end):
          colors[i] = c
  return colors


def book_return_role(match_text, mi, return_char):
  """Book mode: soft_nl (auto), para_enter (type ⏎), para_tail (auto after para_enter)."""
  if mi >= len(match_text) or match_text[mi] != return_char:
    return None
  next_is = mi + 1 < len(match_text) and match_text[mi + 1] == return_char
  prev_is = mi > 0 and match_text[mi - 1] == return_char
  if prev_is and next_is:
    return 'para_tail'
  if next_is:
    return 'para_enter'
  if prev_is:
    return 'para_tail'
  return 'soft_nl'


def _display_to_match_indices(display_text, match_text, return_char=None, book_returns=False):
  """Map each display char index to match_text index, or None for display-only."""
  if display_text == match_text:
    return list(range(len(display_text)))
  idxs = []
  mi = 0
  di = 0
  while di < len(display_text):
    if mi >= len(match_text):
      idxs.append(None); di += 1; continue
    dc = display_text[di]
    mc = match_text[mi]
    if return_char and mc == return_char and book_returns:
      role = book_return_role(match_text, mi, return_char)
      if role == 'soft_nl' and dc == '\n':
        idxs.append(mi); mi += 1; di += 1
      elif role == 'para_enter' and dc == return_char:
        idxs.append(mi); mi += 1; di += 1
        if di < len(display_text) and display_text[di] == '\n':
          idxs.append(None); di += 1
        while mi < len(match_text) and book_return_role(match_text, mi, return_char) == 'para_tail':
          mi += 1
      else:
        idxs.append(None); di += 1
    elif dc == mc:
      idxs.append(mi); mi += 1; di += 1
    elif return_char and mc == return_char and dc == return_char:
      idxs.append(None); mi += 1; di += 1
      if di < len(display_text) and display_text[di] == '\n':
        idxs.append(None); di += 1
    else:
      idxs.append(None); di += 1
  return idxs


def make_heatmap_legend(parent=None):
  """Widget legend — QLabel rich text ignores span margins; real layout spaces pills."""
  from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
  w = QWidget(parent)
  lay = QHBoxLayout(w)
  lay.setContentsMargins(0, 0, 0, 0)
  lay.setSpacing(10)
  for i, (label, (_, color)) in enumerate(zip(WPM_BUCKET_LABELS, WPM_BUCKETS)):
    lbl = QLabel(label, parent=w)
    fg = '#fff' if i == 0 else '#111'
    lbl.setStyleSheet(
      'QLabel { background: %s; color: %s; padding: 4px 8px; border-radius: 2px; font-size: 11px; min-height: 18px; }' % (color, fg))
    lay.addWidget(lbl)
  wpm = QLabel('wpm', parent=w)
  wpm.setStyleSheet('color: #888; font-size: 11px;')
  lay.addWidget(wpm)
  return w


def char_heatmap_colors(display_text, mode, stats, match_text=None, return_char=None, book_returns=False):
  if match_text is None:
    match_text = display_text
  match_colors = _colors_for_match_text(match_text, mode, stats)
  if display_text == match_text:
    return match_colors
  idxs = _display_to_match_indices(display_text, match_text, return_char, book_returns)
  return [match_colors[i] if i is not None else None for i in idxs]
