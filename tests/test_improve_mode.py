"""Tests for improve mode submode target selection."""

import sqlite3

from amphetype.improve_mode import (
  IMPROVE_SUBMODE_DAMAGE, IMPROVE_SUBMODE_HESITANT, IMPROVE_SUBMODE_NORMAL,
  IMPROVE_SUBMODE_OBLIVION, IMPROVE_SUBMODE_SLOWEST, fetch_improve_submode_targets,
)
from amphetype.stats_query import STAT_TYPE_WORD


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


def _seed_words(conn, now):
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'slow', STAT_TYPE_WORD, 12.0 / 20.0, 10, 0, 5.0, None),
      (now, 'mid', STAT_TYPE_WORD, 12.0 / 60.0, 10, 0, 12.0, None),
      (now, 'fast', STAT_TYPE_WORD, 12.0 / 120.0, 10, 0, 2.0, None),
      (now, 'risky', STAT_TYPE_WORD, 12.0 / 80.0, 10, 5, 3.0, None),
    ])


def test_improve_submode_normal_returns_empty():
  conn = _test_db()
  assert fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_NORMAL, 0, 1) == []


def test_improve_submode_slowest_picks_lowest_wpm():
  conn = _test_db(); now = 1e9
  _seed_words(conn, now)
  picks = fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_SLOWEST, 0, 1, n=3)
  assert [t[1] for t in picks] == ['slow', 'mid', 'risky']


def test_improve_submode_hesitant_picks_highest_viscosity():
  conn = _test_db(); now = 1e9
  _seed_words(conn, now)
  picks = fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_HESITANT, 0, 1, n=3)
  assert [t[1] for t in picks[0:3]] == ['mid', 'slow', 'risky']


def test_improve_submode_damage_picks_highest_damage():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'risky', STAT_TYPE_WORD, 12.0 / 40.0, 20, 10, 1.0, None),
      (now, 'ok', STAT_TYPE_WORD, 12.0 / 80.0, 20, 1, 1.0, None),
      (now, 'fine', STAT_TYPE_WORD, 12.0 / 100.0, 20, 0, 1.0, None),
    ])
  picks = fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_DAMAGE, 0, 1, n=3)
  assert picks[0][1] == 'risky'


def test_improve_submode_oblivion_under_threshold():
  conn = _test_db(); now = 1e9
  _seed_words(conn, now)
  picks = fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_OBLIVION, 0, 1, n=3)
  assert {t[1] for t in picks} == {'slow'}


def test_improve_submode_always_picks_words_not_trigrams():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'ol,', 1, 12.0 / 10.0, 10, 0, 1.0, None),
      (now, 'slowword', STAT_TYPE_WORD, 12.0 / 15.0, 10, 0, 1.0, None),
    ])
  picks = fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_SLOWEST, 0, 1, n=3)
  assert picks == [('word', 'slowword', 15.0)]
