"""Tests for split statistic aggregation (normal vs weakspot drill rows)."""

import sqlite3
import unittest

import pytest

from typing_program.speed_heatmap import OBLIVION_WPM
from typing_program.stats_query import (
  ALL_TIME_HIST, ANALYSIS_OUTER_SQL, RAW_TARGETS_SQL, STATS_AGG_SUBQUERY,
  STAT_TYPE_CHAR, STAT_TYPE_TRIGRAM, STAT_TYPE_WORD, STAT_TYPE_BIWORD, aggregate_session_wpm,
  aggregate_session_wpm_from_results, analysis_floor_sql, analysis_min_count, analysis_order_clause,
  analysis_order_sql, count_analysis_words, count_unique_typed,
  fetch_analysis_baseline_wpm, fetch_analysis_search, fetch_oblivion_pool, fetch_oblivion_picks,
  fetch_word_book_sources, delete_stat_target, raw_targets_sql,
)
from typing_program.WeakSpotLessons import fetch_weak_targets, score_target


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


def _two_books(conn):
  return _add_source(conn, 'BookA'), _add_source(conn, 'BookB')


def _split_found(now, data, t, count, mistakes, viscosity, books):
  """Two statistic rows so `data` qualifies as found (distinct books)."""
  a, b = books
  c1 = max(1, int(count) - 1) if count >= 2 else int(count)
  c2 = int(count) - c1
  rows = [(now, data, STAT_TYPE_WORD, t, c1, mistakes, viscosity, a)]
  if c2 > 0:
    rows.append((now, data, STAT_TYPE_WORD, t, c2, 0, viscosity, b))
  return rows


class TestStatsAggregation(unittest.TestCase):

  def test_drill_row_updates_median_not_corpus(self):
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
    self.assertEqual(row[3], 20)   # corpus
    self.assertEqual(row[4], 2)    # corpus_mistakes
    self.assertEqual(row[5], 1)    # drilled (legacy count=0 → 1)
    self.assertEqual(row[6], 1)    # drill_mistakes
    self.assertAlmostEqual(row[1], 0.35)  # median(0.5, 0.2)

  def test_focus_drill_rows_add_drill_samples_not_corpus(self):
    from typing_program.timingtuple import collect_focus_drill_stat_rows, RunStats
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.execute(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      (now, 'slow', STAT_TYPE_WORD, 0.50, 10, 2, 5.0, book))
    run = RunStats.make('slow slow', started=1000.0)
    t = 1000.0; last = None
    for i in range(len(run)):
      run[i].visit(True, last, t)
      last = t; t += 0.20
      run[i].last = t
    run.index = len(run)
    for t, vis, w, c, m, tp, data in collect_focus_drill_stat_rows(
        run, run.median_timing, now + 1, [('word', 'slow')]):
      conn.execute(
        'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
        (w, data, tp, t, c, m, vis, weak))
    row = conn.execute(STATS_AGG_SUBQUERY, (0, STAT_TYPE_WORD)).fetchone()
    self.assertEqual(row[3], 10)   # corpus unchanged
    self.assertEqual(row[4], 2)    # corpus_mistakes unchanged
    self.assertEqual(row[5], 2)    # drilled = two "slow" samples
    self.assertEqual(row[6], 0)    # drill_mistakes
    self.assertLess(row[1], 0.50)   # median time improved

  def test_discounted_high_count_row_ignored(self):
    conn = _test_db(); now = 1e9
    books = _two_books(conn)
    weak = _add_source(conn, '<Weakspot>', 1)
    rows = _split_found(now, 'realword', 0.4, 20, 1, 1.0, books)
    rows.append((now, 'drillword', 2, 1.0, 500, 0, 1.0, weak))
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      rows)
    targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
    words = [t[1] for t in targets if t[0] == 'word']
    self.assertEqual(words, ['realword'])
    self.assertNotIn('drillword', words)

  def test_faster_drill_lowers_damage_score(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    other = _add_source(conn, 'Other')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'slow', 2, 0.60, 9, 0, 1.0, book),
        (now, 'slow', 2, 0.40, 1, 0, 1.0, other),
      ])
    t0, total0, misses0 = conn.execute(raw_targets_sql(2), (0, 2, 2)).fetchone()[1:]
    before = score_target(t0, total0, misses0)
    conn.execute(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      (now + 1, 'slow', 2, 0.10, 0, 0, 1.0, weak))
    t, total, misses = conn.execute(raw_targets_sql(2), (0, 2, 2)).fetchone()[1:]
    after = score_target(t, total, misses)
    self.assertEqual(total, 10)
    self.assertLess(t, t0)
    self.assertLess(after, before)

  def test_analysis_sql_corpus_drill_perfect_order(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'from', 2, 0.40, 10, 1, 5.0, book),
        (now + 1, 'from', 2, 0.30, 3, 0, 4.0, weak),
      ])
    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'books >= ?', 'damage desc', 10)
    row = conn.execute(sql, (0, 2, 1)).fetchone()
    self.assertEqual(row[0], 'from')
    self.assertEqual(row[3], 10)   # corpus
    self.assertEqual(row[4], 3)    # drill
    self.assertEqual(row[5], 12)   # perfect = (10-1) + (3-0)

  def test_analysis_sql_perfect_is_corpus_minus_mistakes(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'Novel')
    conn.execute(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      (now, 'once', 2, 0.40, 1, 1, 5.0, book))
    sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'books >= ?', 'corpus desc', 10)
    row = conn.execute(sql, (0, 2, 1)).fetchone()
    self.assertEqual(row[3], 1)   # corpus
    self.assertEqual(row[4], 0)   # drill
    self.assertEqual(row[5], 0)   # perfect

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
    books = _two_books(conn)
    rows = []
    for data, count in [('from', 10), ('therefore', 8), ('the', 5), ('Lady', 5)]:
      rows.extend(_split_found(now, data, 0.5, count, 0, 1.0, books))
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      rows)
    hits = fetch_analysis_search(conn, 0, STAT_TYPE_WORD, 1, 'the', 'data asc')
    self.assertEqual([r[0] for r in hits], ['the', 'therefore'])

  def test_fetch_analysis_search_words_respects_min_count(self):
    conn = _test_db(); now = 1e9
    books = _two_books(conn)
    # min_count=3 → need 3 distinct books for 'the'; 'there' has only 1.
    a, b = books
    c = _add_source(conn, 'BookC')
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'the', STAT_TYPE_WORD, 0.5, 2, 0, 1.0, a),
        (now, 'the', STAT_TYPE_WORD, 0.5, 2, 0, 1.0, b),
        (now, 'the', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, c),
        (now, 'there', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, a),
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
    books = _two_books(conn)
    rows = []
    for i in range(40):
      rows.extend(_split_found(now, 'w%02d' % i, 0.5, 10, 0, 1.0, books))
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      rows)
    limited = conn.execute(
      ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'books >= ?', 'data asc', 10),
      (0, STAT_TYPE_WORD, 1)).fetchall()
    self.assertEqual(len(limited), 10)
    hits = fetch_analysis_search(conn, 0, STAT_TYPE_WORD, 1, 'w', 'data asc')
    self.assertEqual(len(hits), 40)


def test_analysis_order_clause_rejects_unknown_sort():
  assert analysis_order_clause('improved desc') == 'improved desc'
  assert analysis_order_clause('bogus desc') == 'wpm asc'
  assert analysis_order_clause('damage desc') == 'damage desc'
  assert analysis_order_clause('accuracy asc') == 'perfect_pct asc'
  assert analysis_order_clause('misses desc') == 'perfect_pct asc'
  assert analysis_order_clause('perfect asc') == 'perfect_pct asc'
  assert analysis_order_clause('perfect desc') == 'perfect_pct desc'
  assert analysis_order_clause('perfect_pct desc') == 'perfect_pct desc'
  assert analysis_order_sql('perfect_pct asc') == (
    'cast(perfect as real) / nullif(corpus + drilled, 0) asc, corpus asc')
  assert analysis_order_sql('perfect_pct desc') == (
    'cast(perfect as real) / nullif(corpus + drilled, 0) desc, corpus desc')
  assert analysis_order_sql('total desc') == 'corpus desc'


def test_analysis_min_count_requires_two_for_words():
  assert analysis_min_count(STAT_TYPE_WORD, 1) == 2
  assert analysis_min_count(STAT_TYPE_WORD, 5) == 5
  assert analysis_min_count(STAT_TYPE_TRIGRAM, 1) == 1
  assert analysis_min_count(STAT_TYPE_BIWORD, 1) == 2
  assert analysis_min_count(STAT_TYPE_BIWORD, 5) == 5
  assert analysis_min_count(STAT_TYPE_CHAR, 1) == 1


def test_fetch_analysis_top_hides_one_shot_words():
  conn = _test_db(); now = 1e9
  a, b = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'once', STAT_TYPE_WORD, 0.5, 1, 1, 1.0, a),
      *_split_found(now, 'often', 0.5, 5, 0, 1.0, (a, b)),
    ])
  sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'books >= ?', 'data asc', 10)
  rows = conn.execute(sql, (0, STAT_TYPE_WORD, analysis_min_count(STAT_TYPE_WORD, 1))).fetchall()
  assert [r[0] for r in rows] == ['often']


def test_perfect_pct_sort_lowest_first():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  rows = []
  rows.extend(_split_found(now, 'good', 0.5, 10, 1, 1.0, books))
  rows.extend(_split_found(now, 'bad', 0.5, 10, 9, 1.0, books))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    rows)
  sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'books >= ?', analysis_order_sql('perfect_pct asc'), 10)
  rows = conn.execute(sql, (0, STAT_TYPE_WORD, 2)).fetchall()
  assert [r[0] for r in rows] == ['bad', 'good']
  assert rows[0][5] == 1   # perfect
  assert rows[1][5] == 9


def test_perfect_pct_desc_ties_rank_higher_count():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  rows = []
  rows.extend(_split_found(now, 'few', 0.5, 2, 0, 1.0, books))
  rows.extend(_split_found(now, 'many', 0.5, 6, 0, 1.0, books))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    rows)
  sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'books >= ?', analysis_order_sql('perfect_pct desc'), 10)
  rows = conn.execute(sql, (0, STAT_TYPE_WORD, 2)).fetchall()
  assert [r[0] for r in rows] == ['many', 'few']


def test_count_analysis_words_excludes_one_shot():
  conn = _test_db(); now = 1e9
  a, b = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'once', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, a),
      (now, 'twice', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, a),
      (now, 'twice', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, b),
      (now, ' fr', STAT_TYPE_TRIGRAM, 0.5, 1, 0, 1.0, a),
    ])
  assert count_analysis_words(conn, 0) == 1
  assert count_unique_typed(conn, 0, STAT_TYPE_WORD) == 2


def test_count_analysis_words_ignores_improve_mode_drill_rows():
  """Improve (including normal) writes discounted Weakspot rows with count=0 — no new common words."""
  conn = _test_db(); now = 1e9
  weak = _add_source(conn, '<Weakspot>', 1)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'onlydrill', STAT_TYPE_WORD, 0.2, 0, 0, 1.0, weak),
      (now, 'onlydrill', STAT_TYPE_WORD, 0.2, 0, 0, 1.0, weak),
      (now, 'onlydrill', STAT_TYPE_WORD, 0.2, 0, 0, 1.0, weak),
    ])
  assert count_analysis_words(conn, 0) == 0
  assert fetch_word_book_sources(conn, ['onlydrill']) == {}


def test_fetch_analysis_baseline_wpm_one_sample():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now - 1000, 'slow', STAT_TYPE_WORD, 12.0 / 30.0, 5, 0, 1.0, None),
      (now, 'slow', STAT_TYPE_WORD, 12.0 / 60.0, 5, 0, 1.0, None),
    ])
  base = fetch_analysis_baseline_wpm(conn, STAT_TYPE_WORD, ['slow'], 1)
  assert base['slow'] == pytest.approx(30.0)


def test_fetch_analysis_baseline_wpm_median_of_first_n():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now - 1000, 'slow', STAT_TYPE_WORD, 12.0 / 30.0, 1, 0, 1.0, None),
      (now - 500, 'slow', STAT_TYPE_WORD, 12.0 / 60.0, 1, 0, 1.0, None),
      (now, 'slow', STAT_TYPE_WORD, 12.0 / 90.0, 1, 0, 1.0, None),
    ])
  base = fetch_analysis_baseline_wpm(conn, STAT_TYPE_WORD, ['slow'], 2)
  assert base['slow'] == pytest.approx(45.0)


def test_fetch_analysis_baseline_wpm_ignores_drill_rows():
  conn = _test_db(); now = 1e9
  conn.execute('insert into source (name, disabled, discount) values (?,?,?)', ('<Weakspot>', 1, 1))
  ws = conn.execute('select rowid from source where name=?', ('<Weakspot>',)).fetchone()[0]
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now - 1000, 'once', STAT_TYPE_WORD, 12.0 / 40.0, 1, 0, 1.0, None),
      (now - 500, 'once', STAT_TYPE_WORD, 12.0 / 80.0, 0, 0, 1.0, ws),
    ])
  base = fetch_analysis_baseline_wpm(conn, STAT_TYPE_WORD, ['once'], 2)
  assert base['once'] == pytest.approx(40.0)


def test_fetch_oblivion_pool_returns_all_under_threshold():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  rows = []
  for i in range(35):
    wpm = 10 + (i % 19)
    rows.extend(_split_found(now, 'w%d' % i, 12.0 / wpm, 10, 0, 1.0, books))
  for i in range(10):
    wpm = 40 + i
    rows.extend(_split_found(now, 'fast%d' % i, 12.0 / wpm, 10, 0, 1.0, books))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    rows)
  limited = conn.execute(
    ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, 'books >= ?', 'wpm asc', 30),
    (0, STAT_TYPE_WORD, 1)).fetchall()
  old_pool = [r for r in limited if r[1] is not None and r[1] < OBLIVION_WPM]
  assert len(old_pool) == 30
  assert len(fetch_oblivion_pool(conn, 0, STAT_TYPE_WORD, OBLIVION_WPM)) == 35


def test_oblivion_pool_excludes_words_below_analysis_min_count():
  """One-book and drill-only words must not enter the oblivion focus-drill pool."""
  from typing_program.stats_query import WORD_ANALYSIS_MIN_COUNT
  conn = _test_db(); now = 1e9
  a, b = _two_books(conn)
  weak = _add_source(conn, '<Weakspot>', 1)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'once', STAT_TYPE_WORD, 12.0 / 15.0, 1, 0, 1.0, a),
      (now, 'drillonly', STAT_TYPE_WORD, 12.0 / 18.0, 0, 1, 1.0, weak),
      *_split_found(now, 'often', 12.0 / 20.0, WORD_ANALYSIS_MIN_COUNT, 0, 1.0, (a, b)),
      *_split_found(now, 'plenty', 12.0 / 22.0, 10, 0, 1.0, (a, b)),
    ])
  pool = fetch_oblivion_pool(conn, 0, STAT_TYPE_WORD, OBLIVION_WPM, min_count=1)
  names = {r[0] for r in pool}
  assert names == {'often', 'plenty'}
  assert 'once' not in names
  assert 'drillonly' not in names


def test_oblivion_pool_excludes_displayed_32_wpm():
  """32 is red — raw 31.96 shows as 32.0 and must not enter the oblivion pool."""
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  rows = []
  for data, wpm in [('edge32', 31.96), ('exact32', 32.0), ('slow31', 31.0), ('slow319', 31.9)]:
    rows.extend(_split_found(now, data, 12.0 / wpm, 10, 0, 1.0, books))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    rows)
  names = {r[0] for r in fetch_oblivion_pool(conn, 0, STAT_TYPE_WORD, OBLIVION_WPM)}
  assert names == {'slow31', 'slow319'}
  assert 'edge32' not in names
  assert 'exact32' not in names


def test_all_time_hist_is_zero():
  assert ALL_TIME_HIST == 0


def test_fetch_oblivion_picks_all_time():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  rows = []
  for data, wpm, age in [('old1', 20.0, 200000), ('old2', 22.0, 200000), ('old3', 24.0, 200000), ('new1', 18.0, 0)]:
    rows.extend(_split_found(now - age, data, 12.0 / wpm, 5, 0, 1.0, books))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    rows)
  picks = fetch_oblivion_picks(conn, ALL_TIME_HIST, STAT_TYPE_WORD, 3, OBLIVION_WPM)
  assert len(picks) == 3


def test_aggregate_session_wpm_matches_total_chars_over_time():
  # 100 chars in 20s + 400 chars in 60s → 500 chars in 80s → 75 WPM.
  assert aggregate_session_wpm(500, 80) == pytest.approx(75.0)
  assert aggregate_session_wpm(0, 10) is None


def test_aggregate_session_wpm_from_results():
  conn = sqlite3.connect(':memory:')
  conn.executescript("""
    create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real, char_count integer, duration real);
  """)
  now = 1e9
  conn.executemany(
    'insert into result (w,text_id,source,wpm,accuracy,viscosity,char_count,duration) values (?,?,?,?,?,?,?,?)',
    [(now, 'a', 1, 60.0, 1.0, 1.0, 100, 20.0), (now, 'b', 1, 80.0, 1.0, 1.0, 400, 60.0)])
  assert aggregate_session_wpm_from_results(conn, now - 86400) == pytest.approx(75.0)
  assert aggregate_session_wpm_from_results(conn, now + 1) is None


def test_aggregate_session_wpm_from_results_skips_rows_without_duration():
  conn = sqlite3.connect(':memory:')
  conn.executescript("""
    create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real, char_count integer, duration real);
  """)
  now = 1e9
  conn.executemany(
    'insert into result (w,text_id,source,wpm,accuracy,viscosity,char_count,duration) values (?,?,?,?,?,?,?,?)',
    [(now, 'a', 1, 60.0, 1.0, 1.0, 100, None), (now, 'b', 1, 80.0, 1.0, 1.0, 400, 60.0)])
  assert aggregate_session_wpm_from_results(conn, now - 86400) == pytest.approx(80.0)


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


def test_delete_stat_target_removes_all_rows_for_data():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'gone', STAT_TYPE_WORD, 0.5, 10, 0, 1.0, None),
      (now - 100, 'gone', STAT_TYPE_WORD, 0.6, 5, 0, 1.0, None),
      (now, 'stay', STAT_TYPE_WORD, 0.5, 5, 0, 1.0, None),
    ])
  assert delete_stat_target(conn, STAT_TYPE_WORD, 'gone') == 2
  assert conn.execute('select count(*) from statistic where data = ?', ('gone',)).fetchone()[0] == 0
  assert conn.execute('select count(*) from statistic where data = ?', ('stay',)).fetchone()[0] == 1
