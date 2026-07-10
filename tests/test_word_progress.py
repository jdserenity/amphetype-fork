"""Tests for per-word progress vs perfect-rate baselines."""

import sqlite3
import time

import pytest

from typing_program.speed_heatmap import PROGRESS_GREEN, PROGRESS_ORANGE, PROGRESS_RED
from typing_program.stats_query import WORD_ANALYSIS_MIN_COUNT, fetch_word_counted_totals, fetch_word_perfect_baselines
from typing_program.timingtuple import RunStats
from typing_program.word_progress import (
  analyze_run_progress, avg_wpm_bump, fetch_word_baselines, format_progress_html,
  improved_word_spans, lesson_words, lifetime_wpm_gain, median_wpm_bump,
  new_word_spans, perfect_rate_rises, progress_badges_for_run, run_word_sample_counts,
  word_perfect_rate_improves, word_wpm_from_slice, words_crossing_min_count,
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
  last = None
  for i in range(len(text)):
    run[i].visit(True, last, t)
    last = t
    t += spc
    run[i].last = t
    run.index = i + 1
  run.index = len(text)
  return run


def _bl(perfect, count):
  return {'perfect': perfect, 'count': count}


def test_perfect_rate_rises():
  assert perfect_rate_rises(8, 10)  # 80% -> 81.8%
  assert not perfect_rate_rises(10, 10)  # already 100%
  assert not perfect_rate_rises(0, 0)
  assert perfect_rate_rises(0, 2)  # 0% -> 33%


def test_word_perfect_rate_improves():
  assert word_perfect_rate_improves(_bl(8, 10))
  assert not word_perfect_rate_improves(_bl(10, 10))
  assert not word_perfect_rate_improves({})


def test_median_wpm_bump_needs_one_whole_wpm():
  run = _make_run('ab', spc=12.0 / 80.0)
  assert median_wpm_bump(run[0:2], {'wpm': 50.0, 'times': [12.0 / 50.0]}) == 11


def test_avg_wpm_bump_single_prior_sample():
  old = [12.0 / 50.0]
  bump = avg_wpm_bump(old, 12.0 / 80.0)
  assert bump == 11


def test_lifetime_wpm_gain():
  assert lifetime_wpm_gain(70.0, 40.0) == 30
  assert lifetime_wpm_gain(40.0, 40.0) == 0


def test_word_wpm_from_slice():
  run = _make_run('hi', spc=12.0 / 60.0)
  wpm = word_wpm_from_slice(run[0:2])
  assert wpm == pytest.approx(60.0)


def test_word_wpm_from_slice_skips_incomplete():
  run = RunStats.make('ab', started=None)
  run[0].visit(True, None, 1000.0)
  run[0].last = 1000.5
  run[1].visit(True, 1000.0, 1000.5)
  run[1].last = 1000.55
  run.index = 2
  assert word_wpm_from_slice(run[0:2]) is None


def test_no_badge_when_already_perfect():
  run = _make_run('fast', spc=12.0 / 80.0)
  base = _bl(10, 10)
  assert progress_badges_for_run(run, {'fast': base}, 'fast') == []
  assert improved_word_spans(run, {'fast': base}, 'fast') == []
  p = analyze_run_progress(run, {'fast': base}, 'fast')
  assert p.improved == 0
  assert p.known == 1


def test_progress_badges_always_empty():
  run = _make_run('fast', spc=12.0 / 80.0)
  assert progress_badges_for_run(run, {'fast': _bl(5, 10)}, 'fast') == []


def test_words_crossing_min_count_needs_pool_floor():
  assert words_crossing_min_count({}, {'brand': 1}, min_count=2) == []
  assert words_crossing_min_count({}, {'brand': 2}, min_count=2) == ['brand']
  assert words_crossing_min_count({'brand': 1}, {'brand': 1}, min_count=2) == ['brand']
  assert words_crossing_min_count({'brand': 2}, {'brand': 1}, min_count=2) == []


def test_new_word_spans_only_new_common():
  run = _make_run('fast brand', spc=12.0 / 80.0)
  spans = new_word_spans(run, ['brand'], 'fast brand')
  assert spans == [(5, 10)]
  assert new_word_spans(run, [], 'fast brand') == []


def test_improved_word_spans_includes_last_word():
  run = _make_run('ab', spc=12.0 / 80.0)
  spans = improved_word_spans(run, {'ab': _bl(5, 10)}, 'ab')
  assert spans == [(0, 2)]


def test_analyze_run_progress_improved_and_new_common():
  run = _make_run('fast slow brand once', spc=12.0 / 80.0)
  baselines = {
    'fast': _bl(5, 10),   # improves
    'slow': _bl(10, 10),  # already 100% — known but not improved
    'brand': _bl(1, 2),   # improves
  }
  p = analyze_run_progress(
    run, baselines, prior_counts={'brand': 1}, min_count=WORD_ANALYSIS_MIN_COUNT)
  assert p.known == 3
  assert p.improved == 2  # fast + brand
  assert p.new_words == ['brand']


def test_analyze_run_progress_two_shots_in_one_lesson_cross_floor():
  run = _make_run('new new', spc=12.0 / 80.0)
  p = analyze_run_progress(run, {}, prior_counts={}, min_count=2)
  assert p.new_words == ['new']
  assert run_word_sample_counts(run)['new'] == 2


def test_analyze_run_progress_skips_new_common_when_disabled():
  run = _make_run('brand brand', spc=12.0 / 80.0)
  p = analyze_run_progress(
    run, {}, prior_counts={}, min_count=2, include_new_common=False)
  assert p.new_words == []


def test_analyze_run_progress_skips_mistyped_words():
  run = RunStats.make('bad', started=1000.0)
  run[0].visit(False, None, 1000.0)
  run[0].visit(True, 1000.0, 1001.0)
  run[0].last = 1001.0
  run.index = 1
  run[1].visit(True, 1001.0, 1001.0)
  run[1].last = 1001.1
  run[2].visit(True, 1001.0, 1001.1)
  run[2].last = 1001.2
  run.index = 3
  p = analyze_run_progress(run, {'bad': _bl(0, 5)})
  assert p.known == 0


def test_format_progress_html_zero_improved_is_red():
  html = format_progress_html(analyze_run_progress(_make_run('a', spc=0.2), {'a': _bl(10, 10)}))
  assert PROGRESS_RED in html
  assert '0</span> out of 1 words' in html
  assert 'perfect rate' in html
  assert 'wpm' not in html


def test_format_progress_html_new_common_words_orange():
  p = analyze_run_progress(
    _make_run('brand brand', spc=0.1), {}, prior_counts={}, min_count=2)
  html = format_progress_html(p)
  assert PROGRESS_ORANGE in html
  assert 'You found' in html
  assert '1</span> new common word!' in html
  assert 'typed' not in html
  assert 'unique' not in html


def test_format_progress_html_drill_note():
  html = format_progress_html(analyze_run_progress(_make_run('a', spc=0.1), {}), stats_saved=False)
  assert 'stats were not saved' in html


def test_fetch_word_perfect_baselines():
  conn = _test_db(); now = time.time()
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'Lady', 2, 12.0 / 70.0, 5, 1, 1.0, None),
      (now, 'lady', 2, 12.0 / 40.0, 4, 0, 1.0, None),
    ])
  baselines = fetch_word_perfect_baselines(conn, lesson_words('Lady lady'))
  assert baselines['Lady'] == {'count': 5, 'perfect': 4, 'corpus': 5}
  assert baselines['lady'] == {'count': 4, 'perfect': 4, 'corpus': 4}


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


def test_fetch_word_counted_totals_ignores_weakspot_drills():
  conn = _test_db(); now = time.time()
  conn.execute('insert into source (name, disabled, discount) values (?,?,?)', ('<Weakspot>', 1, 1))
  ws = conn.execute('select rowid from source where name=?', ('<Weakspot>',)).fetchone()[0]
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'real', 2, 0.2, 1, 0, 1.0, None),
      (now, 'real', 2, 0.2, 0, 0, 1.0, ws),
      (now, 'drillonly', 2, 0.2, 0, 0, 1.0, ws),
    ])
  totals = fetch_word_counted_totals(conn, ['real', 'drillonly', 'missing'])
  assert totals == {'real': 1, 'drillonly': 0}


def test_format_progress_html_improved_green():
  run = _make_run('fast', spc=12.0 / 80.0)
  html = format_progress_html(analyze_run_progress(run, {'fast': _bl(5, 10)}))
  assert PROGRESS_GREEN in html
  assert '1</span> out of 1 words' in html
  assert 'wpm' not in html
