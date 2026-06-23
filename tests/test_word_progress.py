"""Tests for per-word progress vs baseline."""

import sqlite3
import time

import pytest

from amphetype.speed_heatmap import PROGRESS_GREEN, PROGRESS_ORANGE, PROGRESS_RED
from amphetype.timingtuple import RunStats
from amphetype.word_progress import (
  analyze_run_progress, fetch_word_baselines, format_progress_html, is_improved,
  lesson_words, word_wpm_from_slice,
)


class _MedianAggregate(list):
  def step(self, val):
    if val is not None:
      self.append(val)
  def finalize(self):
    if not self:
      return None
    s = sorted(self); n = len(s)
    if n & 1:
      return s[n // 2]
    return (s[n // 2] + s[n // 2 - 1]) / 2.0


def _test_db():
  conn = sqlite3.connect(':memory:')
  conn.create_aggregate('agg_median', 1, _MedianAggregate)
  conn.executescript("""
    create table source (name text, disabled integer, discount integer);
    create table statistic (w real, data text, type integer, time real, count integer, mistakes integer, viscosity real, source integer);
  """)
  return conn


def _make_run(text, spc=0.1):
  run = RunStats.make(text, started=1000.0)
  t = 1000.0
  for i in range(len(text)):
    run[i].visit(True, t)
    t += spc
    run[i].last = t
    run.index = i + 1
  run.index = len(text)
  return run


def test_is_improved_needs_one_whole_wpm():
  assert is_improved(51.0, 50.0)
  assert is_improved(50.9, 49.0)
  assert not is_improved(50.9, 50.0)
  assert not is_improved(50.0, 50.0)


def test_word_wpm_from_slice():
  run = _make_run('hi', spc=12.0 / 60.0)
  wpm = word_wpm_from_slice(run[0:2])
  assert wpm == pytest.approx(60.0)


def test_word_wpm_from_slice_skips_chars_without_timing():
  run = RunStats.make('ab', started=None)
  run[0].visit(True, None)
  run[0].last = 1000.5
  run[1].visit(True, 1000.5)
  run[1].last = 1000.6
  run.index = 2
  wpm = word_wpm_from_slice(run[0:2])
  assert wpm == pytest.approx(120.0)


def test_analyze_run_progress_improved_and_new():
  run = _make_run('fast slow newword', spc=12.0 / 80.0)
  baselines = {'fast': 50.0, 'slow': 90.0}
  p = analyze_run_progress(run, baselines)
  assert p.known == 2
  assert p.improved == 1  # fast 80 vs 50; slow 80 vs 90 not improved
  assert p.avg_gain == 30
  assert p.new_words == ['newword']


def test_analyze_run_progress_skips_mistyped_words():
  run = RunStats.make('bad', started=1000.0)
  run[0].visit(False, 1000.0)
  run[0].visit(True, 1001.0)
  run[0].last = 1001.0
  run.index = 1
  run[1].visit(True, 1001.0)
  run[1].last = 1001.1
  run[2].visit(True, 1001.1)
  run[2].last = 1001.2
  run.index = 3
  p = analyze_run_progress(run, {'bad': 10.0})
  assert p.known == 0


def test_format_progress_html_zero_improved_is_red():
  html = format_progress_html(analyze_run_progress(_make_run('a', spc=0.2), {'a': 200.0}))
  assert PROGRESS_RED in html
  assert '0</span> out of 1 words at an average of' in html
  assert '+0</span>wpm!' in html


def test_format_progress_html_new_words_orange():
  p = analyze_run_progress(_make_run('newword', spc=0.1), {})
  html = format_progress_html(p)
  assert PROGRESS_ORANGE in html
  assert '1</span> unique new word!' in html


def test_format_progress_html_drill_note():
  html = format_progress_html(analyze_run_progress(_make_run('a', spc=0.1), {}), stats_saved=False)
  assert 'stats were not saved' in html


def test_fetch_word_baselines_case_sensitive():
  conn = _test_db(); now = time.time()
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'Lady', 2, 12.0 / 70.0, 5, 0, 1.0, None),
      (now, 'lady', 2, 12.0 / 40.0, 5, 0, 1.0, None),
    ])
  baselines = fetch_word_baselines(conn, lesson_words('Lady lady'))
  assert baselines['Lady'] == 70.0
  assert baselines['lady'] == 40.0


def test_format_progress_html_improved_green():
  run = _make_run('fast', spc=12.0 / 80.0)
  html = format_progress_html(analyze_run_progress(run, {'fast': 50.0}))
  assert PROGRESS_GREEN in html
  assert '+30</span>wpm!' in html
