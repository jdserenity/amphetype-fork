"""Tests for split statistic aggregation (normal vs weakspot drill rows)."""

import sqlite3
import unittest

from amphetype.stats_query import ANALYSIS_OUTER_SQL, RAW_TARGETS_SQL, STATS_AGG_SUBQUERY
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
