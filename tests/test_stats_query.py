"""Tests for split statistic aggregation (normal vs weakspot drill rows)."""

import sqlite3
import unittest

import pytest

from amphetype.speed_heatmap import OBLIVION_WPM
from amphetype.stats_query import (
  ANALYSIS_OUTER_SQL, RAW_TARGETS_SQL, STATS_AGG_SUBQUERY,
  STAT_TYPE_CHAR, STAT_TYPE_TRIGRAM, STAT_TYPE_WORD, aggregate_result_wpm, analysis_order_clause,
  average_typing_wpm, count_unique_typed, perf_hist_cutoff,
  fetch_analysis_search, fetch_first_sample_wpm, fetch_oblivion_pool, fetch_oblivion_picks,
)
from amphetype.WeakSpotLessons import fetch_weak_targets, score_target


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


def _add_source(conn, name, discount=None):
  conn.execute('insert into source (name, discount) values (?,?)', (name, discount))
  return conn.execute('select rowid from source where name=?', (name,)).fetchone()[0]


class TestStatsAggregation(unittest.TestCase):

  def test_drill_row_updates_median_not_count(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'from', 2, 0.50, 20, 2, 10.0, book),
        (now + 1, 'from', 2, 0.20, 0, 1, 8.0, weak),
      ])
    row = conn.execute(STATS_AGG_SUBQUERY, (0, 2)).fetchone()
    self.assertEqual(row[0], 'from')
    self.assertEqual(row[3], 20)   # total
    self.assertEqual(row[4], 2)    # mistakes
    self.assertEqual(row[5], 1)    # drilled
    self.assertAlmostEqual(row[1], 0.35)  # median(0.5, 0.2)

  def test_discounted_high_count_row_ignored(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'realword', 2, 0.4, 20, 1, 1.0, book),
        (now, 'drillword', 2, 1.0, 500, 0, 1.0, weak),
      ])
    targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
    words = [t[1] for t in targets if t[0] == 'word']
    self.assertEqual(words, ['realword'])
    self.assertNotIn('drillword', words)

  def test_faster_drill_lowers_damage_score(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.execute(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      (now, 'slow', 2, 0.50, 10, 0, 1.0, book))
    before = score_target(0.50, 10, 0)
    conn.execute(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      (now + 1, 'slow', 2, 0.20, 0, 0, 1.0, weak))
    t, total, misses = conn.execute(RAW_TARGETS_SQL, (0, 2, 1)).fetchone()[1:]
    after = score_target(t, total, misses)
    self.assertEqual(total, 10)
    self.assertLess(t, 0.50)
    self.assertLess(after, before)

  def test_analysis_sql_includes_drilled_columns(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'from', 2, 0.40, 10, 1, 5.0, book),
        (now + 1, 'from', 2, 0.30, 0, 2, 4.0, weak),
      ])
    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'damage desc', 10)
    row = conn.execute(sql, (0, 2, 1)).fetchone()
    self.assertEqual(row[0], 'from')
    self.assertEqual(row[4], 10)   # total
    self.assertEqual(row[5], 1)    # mistakes (counted only)
    self.assertEqual(row[6], 1)    # drilled
    self.assertAlmostEqual(row[2], 90.0)  # accuracy 10-1/10

  def test_word_stats_keep_case_separate(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'Lady', 2, 12.0 / 70.0, 10, 0, 1.0, book),
        (now + 1, 'lady', 2, 12.0 / 25.0, 8, 0, 1.0, book),
      ])
    rows = {r[0]: r[1] for r in conn.execute(STATS_AGG_SUBQUERY, (0, 2)).fetchall()}
    self.assertEqual(set(rows), {'Lady', 'lady'})
    self.assertAlmostEqual(12.0 / rows['Lady'], 70.0)
    self.assertAlmostEqual(12.0 / rows['lady'], 25.0)

  def test_fetch_analysis_search_words_case_insensitive(self):
    conn = _test_db(); now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'from', STAT_TYPE_WORD, 0.5, 10, 0, 1.0, None),
        (now, 'therefore', STAT_TYPE_WORD, 0.5, 8, 0, 1.0, None),
        (now, 'the', STAT_TYPE_WORD, 0.5, 5, 0, 1.0, None),
        (now, 'Lady', STAT_TYPE_WORD, 0.5, 5, 0, 1.0, None),
      ])
    hits = fetch_analysis_search(conn, 0, STAT_TYPE_WORD, 1, 'the', 'data asc')
    self.assertEqual([r[0] for r in hits], ['the', 'therefore'])

  def test_fetch_analysis_search_words_respects_min_count(self):
    conn = _test_db(); now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'the', STAT_TYPE_WORD, 0.5, 5, 0, 1.0, None),
        (now, 'there', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, None),
      ])
    hits = fetch_analysis_search(conn, 0, STAT_TYPE_WORD, 3, 'the', 'data asc')
    self.assertEqual([r[0] for r in hits], ['the'])

  def test_fetch_analysis_search_trigram_case_sensitive(self):
    conn = _test_db(); now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'The', STAT_TYPE_TRIGRAM, 0.5, 5, 0, 1.0, None),
        (now, 'the', STAT_TYPE_TRIGRAM, 0.5, 5, 0, 1.0, None),
      ])
    hits = fetch_analysis_search(conn, 0, STAT_TYPE_TRIGRAM, 1, 'the', 'data asc')
    self.assertEqual([r[0] for r in hits], ['the'])

  def test_fetch_analysis_search_returns_all_matches_not_limited(self):
    conn = _test_db(); now = 1e9
    rows = [(now, 'w%02d' % i, STAT_TYPE_WORD, 0.5, 10, 0, 1.0, None) for i in range(40)]
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      rows)
    limited = conn.execute(
      ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'data asc', 10),
      (0, STAT_TYPE_WORD, 1)).fetchall()
    self.assertEqual(len(limited), 10)
    hits = fetch_analysis_search(conn, 0, STAT_TYPE_WORD, 1, 'w', 'data asc')
    self.assertEqual(len(hits), 40)


def test_analysis_order_clause_rejects_unknown_sort():
  assert analysis_order_clause('improved desc') == 'improved desc'
  assert analysis_order_clause('bogus desc') == 'wpm asc'
  assert analysis_order_clause('damage desc') == 'damage desc'


def test_fetch_first_sample_wpm():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now - 1000, 'slow', STAT_TYPE_WORD, 12.0 / 30.0, 5, 0, 1.0, None),
      (now, 'slow', STAT_TYPE_WORD, 12.0 / 60.0, 5, 0, 1.0, None),
    ])
  first = fetch_first_sample_wpm(conn, STAT_TYPE_WORD, ['slow'])
  assert first['slow'] == pytest.approx(30.0)


def test_fetch_first_sample_wpm_ignores_drill_rows():
  conn = _test_db(); now = 1e9
  conn.execute('insert into source (name, disabled, discount) values (?,?,?)', ('<Weakspot>', 1, 1))
  ws = conn.execute('select rowid from source where name=?', ('<Weakspot>',)).fetchone()[0]
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now - 1000, 'once', STAT_TYPE_WORD, 12.0 / 40.0, 1, 0, 1.0, None),
      (now - 500, 'once', STAT_TYPE_WORD, 12.0 / 80.0, 0, 0, 1.0, ws),
    ])
  first = fetch_first_sample_wpm(conn, STAT_TYPE_WORD, ['once'])
  assert first['once'] == pytest.approx(40.0)


def test_fetch_oblivion_pool_returns_all_under_threshold():
  conn = _test_db(); now = 1e9
  rows = []
  for i in range(35):
    wpm = 10 + (i % 19)
    rows.append((now, 'w%d' % i, STAT_TYPE_WORD, 12.0 / wpm, 10, 0, 1.0, None))
  for i in range(10):
    wpm = 40 + i
    rows.append((now, 'fast%d' % i, STAT_TYPE_WORD, 12.0 / wpm, 10, 0, 1.0, None))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    rows)
  limited = conn.execute(
    ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'wpm asc', 30),
    (0, STAT_TYPE_WORD, 1)).fetchall()
  old_pool = [r for r in limited if r[1] is not None and r[1] < OBLIVION_WPM]
  assert len(old_pool) == 30
  assert len(fetch_oblivion_pool(conn, 0, STAT_TYPE_WORD, OBLIVION_WPM)) == 35


def test_oblivion_pool_includes_drill_only_rows():
  conn = _test_db(); now = 1e9
  weak = _add_source(conn, '<Weakspot>', 1)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'However', STAT_TYPE_WORD, 12.0 / 20.0, 0, 1, 1.0, weak),
      (now, 'from', STAT_TYPE_WORD, 12.0 / 25.0, 0, 0, 1.0, weak),
      (now, 'with', STAT_TYPE_WORD, 12.0 / 28.0, 0, 0, 1.0, weak),
    ])
  pool = fetch_oblivion_pool(conn, 0, STAT_TYPE_WORD, OBLIVION_WPM)
  assert {r[0] for r in pool} == {'However', 'from', 'with'}


def test_fetch_oblivion_picks_falls_back_all_time():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now - 200000, 'old1', STAT_TYPE_WORD, 12.0 / 20.0, 5, 0, 1.0, None),
      (now - 200000, 'old2', STAT_TYPE_WORD, 12.0 / 22.0, 5, 0, 1.0, None),
      (now - 200000, 'old3', STAT_TYPE_WORD, 12.0 / 24.0, 5, 0, 1.0, None),
      (now, 'new1', STAT_TYPE_WORD, 12.0 / 18.0, 5, 0, 1.0, None),
    ])
  picks = fetch_oblivion_picks(conn, now - 86400, STAT_TYPE_WORD, 3, OBLIVION_WPM)
  assert len(picks) == 3


def test_aggregate_result_wpm_matches_total_chars_over_time():
  # 100 chars @ 60 WPM → 20s; 400 chars @ 80 WPM → 60s → 500 chars in 80s → 75 WPM.
  assert aggregate_result_wpm(500, 80) == pytest.approx(75.0)
  assert aggregate_result_wpm(0, 10) is None


def test_average_typing_wpm_from_counted_char_stats():
  conn = _test_db(); now = 1e9
  book = _add_source(conn, 'Novel')
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'a', STAT_TYPE_CHAR, 0.10, 100, 0, 1.0, book),
      (now, 'b', STAT_TYPE_CHAR, 0.15, 300, 0, 1.0, book),
    ])
  # 100 @ 0.10 s/char + 300 @ 0.15 s/char → mean 0.1375 s/char → 87.3 WPM.
  assert average_typing_wpm(conn, now - 86400) == pytest.approx(87.27272727272727)


def test_average_typing_wpm_ignores_weakspot_drill_rows():
  conn = _test_db(); now = 1e9
  book = _add_source(conn, 'Novel')
  weak = _add_source(conn, '<Weakspot>', 1)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'a', STAT_TYPE_CHAR, 0.10, 50, 0, 1.0, book),
      (now, 'a', STAT_TYPE_CHAR, 0.40, 0, 0, 1.0, weak),
    ])
  assert average_typing_wpm(conn, now - 86400) == pytest.approx(120.0)


def test_average_typing_wpm_falls_back_to_corpus_results():
  conn = sqlite3.connect(':memory:')
  conn.executescript("""
    create table source (name text, disabled integer, discount integer);
    create table statistic (w real, data text, type integer, time real, count integer, mistakes integer, viscosity real, source integer);
    create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real, char_count integer);
  """)
  now = 1e9
  conn.execute('insert into source (name, discount) values (?,?)', ('Novel', None))
  sid = conn.execute('select rowid from source').fetchone()[0]
  conn.execute(
    'insert into result (w,text_id,source,wpm,accuracy,viscosity,char_count) values (?,?,?,?,?,?,?)',
    (now, 't1', sid, 80.0, 1.0, 1.0, 200))
  assert average_typing_wpm(conn, now - 86400) == pytest.approx(80.0)


def test_count_unique_typed_respects_history_window():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'from', STAT_TYPE_WORD, 0.5, 10, 0, 1.0, None),
      (now, 'the', STAT_TYPE_WORD, 0.5, 5, 0, 1.0, None),
      (now - 200000, 'old', STAT_TYPE_WORD, 0.5, 5, 0, 1.0, None),
      (now, ' fr', STAT_TYPE_TRIGRAM, 0.5, 5, 0, 1.0, None),
      (now, 'fro', STAT_TYPE_TRIGRAM, 0.5, 5, 0, 1.0, None),
    ])
  assert count_unique_typed(conn, now - 86400, STAT_TYPE_WORD) == 2
  assert count_unique_typed(conn, now - 86400, STAT_TYPE_TRIGRAM) == 2
  assert count_unique_typed(conn, now + 1, STAT_TYPE_WORD) == 0
