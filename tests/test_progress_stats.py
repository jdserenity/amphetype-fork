"""Tests for all-time progress stats (heatmap tier climbs)."""

import sqlite3

import pytest

from typing_program.progress_stats import count_all_time_tier_climbs, honest_climbs_for_word
from typing_program.speed_heatmap import wpm_bucket_index
from typing_program.stats_query import STAT_TYPE_WORD


def _stats_db():
  conn = sqlite3.connect(':memory:')
  conn.executescript("""
    create table source (rowid integer primary key, name text, disabled integer, discount integer);
    create table statistic (
      rowid integer primary key, time real, viscosity real, w real, count integer,
      mistakes integer, type integer, data text, source integer);
  """)
  conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', 0)")
  return conn


def _word_row(conn, w, spc, word='alpha'):
  conn.execute(
    'insert into statistic (time, viscosity, w, count, mistakes, type, data, source) values (?,?,?,?,?,?,?,?)',
    (spc, 1.0, w, 1, 0, STAT_TYPE_WORD, word, 1))


def test_wpm_bucket_index_tiers():
  assert wpm_bucket_index(20) == 0
  assert wpm_bucket_index(40) == 1
  assert wpm_bucket_index(60) == 2
  assert wpm_bucket_index(90) == 3
  assert wpm_bucket_index(110) == 4


def test_honest_climb_credits_exit_arrow_only(monkeypatch):
  seq = iter([0, 2])
  monkeypatch.setattr('typing_program.progress_stats.wpm_bucket_index', lambda _wpm: next(seq))
  climbs = honest_climbs_for_word([1.0, 0.1])
  assert climbs == [1, 0, 0, 0]


def test_honest_climb_adjacent_steps():
  climbs = honest_climbs_for_word([1.0, 0.2, 0.08])
  assert climbs[0] >= 1


def test_count_all_time_tier_climbs(monkeypatch):
  conn = _stats_db()
  _word_row(conn, 1.0, 1.0, 'slow')
  _word_row(conn, 2.0, 0.08, 'slow')
  monkeypatch.setattr(
    'typing_program.progress_stats.honest_climbs_for_word',
    lambda spcs: [1, 0, 0, 0] if len(spcs) == 2 else [0, 0, 0, 0])
  assert count_all_time_tier_climbs(conn) == (1, 0, 0, 0)
