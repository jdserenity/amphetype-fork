"""Unit tests for speed heatmap logic (no DB/GUI)."""

import pytest

from amphetype.speed_heatmap import (
  MODE_CHAR, MODE_TRIGRAM, MODE_WORD,
  WPM_BUCKETS, char_heatmap_colors, fetch_speed_stats, spc_to_wpm, wpm_color, wpm_color_q,
)


def test_spc_to_wpm():
  assert spc_to_wpm(0.12) == pytest.approx(100.0)


def test_wpm_color_buckets():
  assert wpm_color(29) == WPM_BUCKETS[0][1]
  assert wpm_color(29.9) == WPM_BUCKETS[0][1]
  assert wpm_color(30) == WPM_BUCKETS[1][1]
  assert wpm_color(59.9) == WPM_BUCKETS[1][1]
  assert wpm_color(60) == WPM_BUCKETS[2][1]
  assert wpm_color(89.9) == WPM_BUCKETS[2][1]
  assert wpm_color(90) == WPM_BUCKETS[3][1]
  assert wpm_color(119.9) == WPM_BUCKETS[3][1]
  assert wpm_color(120) == WPM_BUCKETS[4][1]
  assert wpm_color(200) == WPM_BUCKETS[4][1]


def test_wpm_color_none_for_unknown():
  assert wpm_color(None) is None


def test_heatmap_legend_widget_spacing(qapp):
  from PyQt5.QtWidgets import QHBoxLayout
  from amphetype.speed_heatmap import make_heatmap_legend
  w = make_heatmap_legend()
  lay = w.layout()
  assert isinstance(lay, QHBoxLayout)
  assert lay.spacing() >= 10
  assert lay.count() == 6  # five pills + wpm


def test_wpm_color_q_is_bright_stoplight():
  oblivion, slow, fast = wpm_color_q(20), wpm_color_q(50), wpm_color_q(140)
  assert oblivion.name() == '#a855f7'
  assert slow.name() == '#d64545'
  assert fast.name() == '#00e676'


def _stat(wpm, damage=0.0):
  return {'wpm': wpm, 'damage': damage}


def test_char_mode_colors_known_chars_only():
  stats = {'a': _stat(130), 'b': _stat(80)}
  colors = char_heatmap_colors('abx', MODE_CHAR, stats)
  assert colors[0] == wpm_color_q(130)
  assert colors[1] == wpm_color_q(80)
  assert colors[2] is None


def test_trigram_mode_highest_damage_wins_without_overlap():
  stats = {'abc': _stat(50, 1), 'bcd': _stat(150, 100)}
  colors = char_heatmap_colors('abcde', MODE_TRIGRAM, stats)
  assert colors[0] is None
  assert colors[1:4] == [wpm_color_q(150)] * 3
  assert colors[4] is None


def test_trigram_mode_aligned_blocks_fill_gaps():
  stats = {'abc': _stat(80, 1), 'def': _stat(120, 1)}
  colors = char_heatmap_colors('abcdef', MODE_TRIGRAM, stats)
  assert colors[0:3] == [wpm_color_q(80)] * 3
  assert colors[3:6] == [wpm_color_q(120)] * 3


def test_trigram_mode_ignores_non_trigram_keys():
  stats = {'ab': _stat(99)}
  assert char_heatmap_colors('ab', MODE_TRIGRAM, stats) == [None, None]


def test_word_mode_colors_case_sensitive():
  stats = {'hello': _stat(110), 'Hello': _stat(50)}
  colors = char_heatmap_colors('say Hello!', MODE_WORD, stats)
  assert colors[0] is None
  assert colors[4] == wpm_color_q(50)
  assert colors[8] == wpm_color_q(50)
  assert colors[9] is None


def test_display_text_newline_after_return_char():
  ret = '\u23ce'  # same glyph as typer.RETURN_CHAR
  stats = {'a': _stat(100)}
  disp = 'a' + ret + '\n' + 'b'
  colors = char_heatmap_colors(disp, MODE_CHAR, stats, match_text='a' + ret + 'b')
  assert colors[0] == wpm_color_q(100)
  assert colors[1] is None  # return glyph — no char stat
  assert colors[2] is None  # display-only newline
  assert colors[3] is None  # b not in stats


def test_fetch_speed_stats_sqlite(tmp_path):
  import sqlite3

  class _Median:
    def __init__(self): self.vals = []
    def step(self, v): self.vals.append(v)
    def finalize(self):
      xs = sorted(self.vals); n = len(xs)
      if not n: return None
      m = xs[n // 2]
      if n % 2 == 0: m = (m + xs[n // 2 - 1]) / 2.0
      return m

  db_path = tmp_path / 't.db'
  conn = sqlite3.connect(str(db_path))
  conn.create_aggregate('agg_median', 1, _Median)
  conn.execute('create table statistic (w real, data text, type integer, time real, count integer, mistakes integer, viscosity real, source integer)')
  conn.execute('create table source (rowid integer primary key, name text, discount integer)')
  now = 1e9
  conn.executemany('insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)', [
    (now, 'a', 0, 0.1, 5, 0, 0, None),
    (now, 'the', 2, 0.12, 3, 0, 0, None),
    (now - 99999999, 'old', 2, 0.2, 1, 0, 0, None),
  ])
  conn.commit()

  class DB:
    def execute(self, sql, params=()):
      return conn.execute(sql, params)

  stats = fetch_speed_stats(DB(), hist_cutoff=now - 86400, stat_type=0)
  assert stats['a']['wpm'] == pytest.approx(120.0)
  words = fetch_speed_stats(DB(), hist_cutoff=now - 86400, stat_type=2)
  assert words['the']['wpm'] == pytest.approx(100.0)
  assert 'old' not in words


def test_fetch_speed_stats_keeps_word_case_separate(tmp_path):
  import sqlite3

  class _Median:
    def __init__(self): self.vals = []
    def step(self, v): self.vals.append(v)
    def finalize(self):
      xs = sorted(self.vals); n = len(xs)
      if not n: return None
      m = xs[n // 2]
      if n % 2 == 0: m = (m + xs[n // 2 - 1]) / 2.0
      return m

  db_path = tmp_path / 'case.db'
  conn = sqlite3.connect(str(db_path))
  conn.create_aggregate('agg_median', 1, _Median)
  conn.execute('create table statistic (w real, data text, type integer, time real, count integer, mistakes integer, viscosity real, source integer)')
  conn.execute('create table source (rowid integer primary key, name text, discount integer)')
  now = 1e9
  conn.executemany('insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)', [
    (now, 'Lady', 2, 12.0 / 70.0, 5, 0, 0, None),
    (now, 'lady', 2, 12.0 / 25.0, 5, 0, 0, None),
  ])
  conn.commit()

  class DB:
    def execute(self, sql, params=()):
      return conn.execute(sql, params)

  words = fetch_speed_stats(DB(), hist_cutoff=now - 86400, stat_type=2)
  assert words['Lady']['wpm'] == pytest.approx(70.0)
  assert words['lady']['wpm'] == pytest.approx(25.0)


def test_fetch_speed_stats_includes_drill_rows_in_wpm(tmp_path):
  import sqlite3

  class _Median:
    def __init__(self): self.vals = []
    def step(self, v): self.vals.append(v)
    def finalize(self):
      xs = sorted(self.vals); n = len(xs)
      if not n: return None
      m = xs[n // 2]
      if n % 2 == 0: m = (m + xs[n // 2 - 1]) / 2.0
      return m

  db_path = tmp_path / 'drill.db'
  conn = sqlite3.connect(str(db_path))
  conn.create_aggregate('agg_median', 1, _Median)
  conn.execute('create table statistic (w real, data text, type integer, time real, count integer, mistakes integer, viscosity real, source integer)')
  conn.execute('create table source (rowid integer primary key, name text, discount integer)')
  conn.execute("insert into source (rowid, name, discount) values (1, '<Weakspot>', 1)")
  now = 1e9
  # Normal typing: fast (70 WPM). Weakspot drill: slow (25 WPM).
  conn.executemany('insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)', [
    (now, 'however', 2, 12.0 / 70.0, 5, 0, 0, None),
    (now, 'however', 2, 12.0 / 25.0, 0, 0, 0, 1),
  ])
  conn.commit()

  class DB:
    def execute(self, sql, params=()):
      return conn.execute(sql, params)

  wpm = fetch_speed_stats(DB(), hist_cutoff=now - 86400, stat_type=2)['however']['wpm']
  assert wpm == pytest.approx(12.0 / ((12.0 / 70.0 + 12.0 / 25.0) / 2.0))  # not 70 alone
  assert wpm_color(wpm) == WPM_BUCKETS[1][1]  # red 30–59, not orange 60–89


def test_word_mode_lady_and_Lady_are_distinct():
  stats = {'lady': _stat(25), 'Lady': _stat(70)}
  assert char_heatmap_colors('lady', MODE_WORD, stats)[0] == wpm_color_q(25)
  assert char_heatmap_colors('Lady', MODE_WORD, stats)[0] == wpm_color_q(70)


def test_focus_drill_wpm_override_colors():
  stats = {'Meryton': _stat(70), 'possession': _stat(25), 'lady': _stat(80)}
  overrides = {'Meryton': 28.0, 'possession': 22.0, 'lady': 29.0}
  merged = dict(stats)
  for key, wpm in overrides.items():
    merged[key] = {**merged.get(key, {}), 'wpm': wpm}
  text = 'Meryton possession lady'
  colors = char_heatmap_colors(text, MODE_WORD, merged)
  purple = wpm_color_q(28)
  for word, wpm in overrides.items():
    i = text.index(word)
    assert colors[i] == wpm_color_q(wpm)
