"""Tests for per-word progress vs baseline."""

import sqlite3
import time

import pytest

from amphetype.speed_heatmap import PROGRESS_GREEN, PROGRESS_ORANGE, PROGRESS_RED
from amphetype.timingtuple import RunStats
from amphetype.word_progress import (
  analyze_run_progress, avg_wpm_bump, fetch_word_baselines, format_progress_html,
  improved_word_spans, lesson_words, lifetime_wpm_gain, median_wpm_bump,
  progress_badges_for_run, word_wpm_from_slice,
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


def _bl(wpm, *extra_spcs):
  times = [12.0 / wpm] + list(extra_spcs)
  return {'wpm': wpm, 'times': times}


def test_median_wpm_bump_needs_one_whole_wpm():
  run = _make_run('ab', spc=12.0 / 80.0)
  assert median_wpm_bump(run[0:2], _bl(50.0)) == 11
  run2 = _make_run('fast', spc=12.0 / 52.0)
  times = [12.0 / 50.0] * 10
  base = {'wpm': 50.0, 'times': times}
  bump = median_wpm_bump(run2[0:4], base)
  assert bump is None or bump < 1


def test_avg_wpm_bump_single_prior_sample():
  old = [12.0 / 50.0]
  bump = avg_wpm_bump(old, 12.0 / 80.0)
  assert bump == 11  # median spc drops 0.24→0.195, WPM 50→61


def test_avg_wpm_bump_smaller_than_instance_delta():
  old = [12.0 / 50.0, 12.0 / 48.0, 12.0 / 52.0]
  bump = avg_wpm_bump(old, 12.0 / 90.0)
  assert bump is not None
  assert bump < 40  # instance would be ~+40; median pool moves less


def test_no_badge_when_median_bump_is_zero():
  run = _make_run('fast', spc=12.0 / 52.0)
  times = [12.0 / 50.0] * 10
  base = {'wpm': 50.0, 'times': times}
  assert median_wpm_bump(run[0:4], base) is None or median_wpm_bump(run[0:4], base) < 1
  badges = progress_badges_for_run(run, {'fast': base}, 'fast')
  assert badges == []
  assert improved_word_spans(run, {'fast': base}, 'fast') == []
  p = analyze_run_progress(run, {'fast': base}, 'fast')
  assert p.improved == 0


def test_lifetime_wpm_gain():
  assert lifetime_wpm_gain(70.0, 40.0) == 30
  assert lifetime_wpm_gain(40.0, 40.0) == 0


def test_word_wpm_from_slice():
  run = _make_run('hi', spc=12.0 / 60.0)
  wpm = word_wpm_from_slice(run[0:2])
  assert wpm == pytest.approx(60.0)


def test_word_wpm_from_slice_uses_whole_word_not_char_median():
  run = RunStats.make('hello', started=1000.0)
  t = 1000.0
  for i in range(5):
    run[i].visit(True, t)
    t += 0.5 if i == 0 else 0.05
    run[i].last = t
    run.index = i + 1
  sub = run[0:5]
  assert word_wpm_from_slice(sub) == pytest.approx(12.0 / sub.stats[0])
  assert word_wpm_from_slice(sub) == pytest.approx(85.714, rel=1e-3)


def test_word_wpm_from_slice_skips_incomplete():
  run = RunStats.make('ab', started=None)
  run[0].visit(True, None)
  run[0].last = 1000.5
  run[1].visit(True, 1000.5)
  run[1].last = 1000.55
  run.index = 2
  assert word_wpm_from_slice(run[0:2]) is None


def test_progress_badges_for_run():
  run = _make_run('fast slow', spc=12.0 / 80.0)
  badges = progress_badges_for_run(run, {'fast': _bl(50.0), 'slow': _bl(90.0)}, 'fast slow')
  assert len(badges) == 1
  assert badges[0][2] == 11


def test_improved_word_spans_includes_last_word():
  run = _make_run('ab', spc=12.0 / 80.0)
  spans = improved_word_spans(run, {'ab': _bl(50.0)}, 'ab')
  assert len(spans) == 1
  assert spans[0][1] == 2


def test_analyze_run_progress_improved_and_new():
  run = _make_run('fast slow newword', spc=12.0 / 80.0)
  baselines = {'fast': _bl(50.0), 'slow': _bl(90.0)}
  p = analyze_run_progress(run, baselines)
  assert p.known == 2
  assert p.improved == 1  # fast 80 vs 50; slow 80 vs 90 not improved
  assert p.avg_gain == 11
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
  p = analyze_run_progress(run, {'bad': _bl(10.0)})
  assert p.known == 0


def test_format_progress_html_zero_improved_is_red():
  html = format_progress_html(analyze_run_progress(_make_run('a', spc=0.2), {'a': _bl(200.0)}))
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
  assert baselines['Lady']['wpm'] == 70.0
  assert baselines['lady']['wpm'] == 40.0
  assert len(baselines['Lady']['times']) == 1


def test_format_progress_html_improved_green():
  run = _make_run('fast', spc=12.0 / 80.0)
  html = format_progress_html(analyze_run_progress(run, {'fast': _bl(50.0)}))
  assert PROGRESS_GREEN in html
  assert '+11</span>wpm!' in html
