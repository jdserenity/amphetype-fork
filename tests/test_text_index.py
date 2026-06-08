"""Tests for corpus FTS index."""

import random
import sqlite3
import unittest

from amphetype.text_index import (
  backfill_corpus_index, ensure_corpus_index, find_word_in_sources, index_chunk,
)


class _DB:
  def __init__(self, conn):
    self._conn = conn
  def execute(self, sql, params=()):
    return self._conn.execute(sql, params)


class TestTextIndex(unittest.TestCase):

  def _db(self):
    conn = sqlite3.connect(':memory:')
    conn.executescript("""
      create table source (rowid integer primary key, name text, discount integer);
      create table text (id text primary key, source integer, text text, disabled integer);
      create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real);
      create table statistic (w real, data text, type integer, time real, count integer,
        mistakes integer, viscosity real, source integer);
    """)
    db = _DB(conn)
    ensure_corpus_index(db)
    return db, conn

  def test_backfill_indexes_corpus_only(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    conn.execute("insert into source (rowid, name, discount) values (2, '<Weakspot>', 1)")
    conn.executemany('insert into text (id, source, text, disabled) values (?,?,?,?)', [
      ('n1', 1, 'please share this', None),
      ('w1', 2, 'share drill', 1),
    ])
    backfill_corpus_index(db)
    self.assertEqual(conn.execute("select count(*) from text_fts").fetchone()[0], 1)
    hit = find_word_in_sources(db, 'share', [1], rng=random.Random(0))
    self.assertEqual(hit[0], 'n1')

  def test_case_sensitive_verify(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    conn.execute("insert into text (id, source, text, disabled) values ('a', 1, 'the Lady sat', null)")
    conn.execute("insert into text (id, source, text, disabled) values ('b', 1, 'a lady sat', null)")
    backfill_corpus_index(db)
    self.assertEqual(find_word_in_sources(db, 'lady', [1])[0], 'b')
    self.assertEqual(find_word_in_sources(db, 'Lady', [1])[0], 'a')

  def test_index_on_insert_path(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    index_chunk(db, 'x', 1, 'tokens to share')
    self.assertEqual(find_word_in_sources(db, 'share', [1])[0], 'x')

  def test_backfill_only_adds_missing_chunks(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    conn.executemany('insert into text (id, source, text, disabled) values (?,?,?,?)', [
      ('a', 1, 'one share', None),
      ('b', 1, 'two share', None),
    ])
    index_chunk(db, 'a', 1, 'one share')
    backfill_corpus_index(db)
    self.assertEqual(conn.execute("select count(*) from text_fts").fetchone()[0], 2)
