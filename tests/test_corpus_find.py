"""Tests for corpus lookup from Analysis type targets."""

import random
import sqlite3
import unittest

from typing_program.corpus_find import corpus_sources, find_text_for_target, target_in_text
from typing_program.text_index import backfill_corpus_index, ensure_corpus_index


class _DB:
  def __init__(self, conn):
    self._conn = conn
  def execute(self, sql, params=()):
    return self._conn.execute(sql, params)


class TestTargetInText(unittest.TestCase):

  def test_word_case_sensitive(self):
    self.assertTrue(target_in_text('word', 'lady', 'the lady sat'))
    self.assertFalse(target_in_text('word', 'lady', 'the Lady sat'))
    self.assertTrue(target_in_text('word', 'Lady', 'the Lady sat'))

  def test_trigram_substring(self):
    self.assertTrue(target_in_text('trigram', 'e h', 'above home'))
    self.assertFalse(target_in_text('trigram', 'e h', 'abovehouse'))

  def test_char(self):
    self.assertTrue(target_in_text('char', 'C', 'Cloth'))
    self.assertFalse(target_in_text('char', 'c', 'Cloth'))

  def test_biword_consecutive_words(self):
    self.assertTrue(target_in_text('biword', 'the cat', 'see the cat run'))
    self.assertFalse(target_in_text('biword', 'the cat', 'the big cat'))
    self.assertFalse(target_in_text('biword', 'the cat', 'The cat sat'))
    self.assertTrue(target_in_text('biword', 'hello world', 'say hello, world now'))


class TestCorpusFind(unittest.TestCase):

  def _db(self):
    conn = sqlite3.connect(':memory:')
    conn.executescript("""
      create table source (rowid integer primary key, name text, discount integer);
      create table text (id text primary key, source integer, text text, disabled integer);
    """)
    db = _DB(conn)
    ensure_corpus_index(db)
    return db, conn

  def _index(self, db):
    backfill_corpus_index(db)

  def test_find_word_via_fts(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    conn.execute("insert into text (id, source, text, disabled) values ('n1', 1, 'please share this', null)")
    self._index(db)
    hit = find_text_for_target(db, 'word', 'share')
    self.assertEqual(hit[0], 'n1')

  def test_random_among_matching_chunks(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'A', null)")
    conn.executemany('insert into text (id, source, text, disabled) values (?,?,?,?)', [
      ('a1', 1, 'share one', None),
      ('a2', 1, 'share two', None),
    ])
    self._index(db)
    hits = {find_text_for_target(db, 'word', 'share', rng=random.Random(i))[0] for i in range(8)}
    self.assertEqual(hits, {'a1', 'a2'})

  def test_trigram_scans_corpus(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    conn.execute("insert into text (id, source, text, disabled) values ('t1', 1, 'fly from here', null)")
    hit = find_text_for_target(db, 'trigram', 'y f')
    self.assertEqual(hit[0], 't1')

  def test_biword_scans_corpus(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    conn.execute("insert into text (id, source, text, disabled) values ('b1', 1, 'of the people', null)")
    hit = find_text_for_target(db, 'biword', 'of the')
    self.assertEqual(hit[0], 'b1')

  def test_no_match_returns_none(self):
    db, conn = self._db()
    conn.execute("insert into source (rowid, name, discount) values (1, 'Novel', null)")
    conn.execute("insert into text (id, source, text, disabled) values ('x', 1, 'nothing', null)")
    self._index(db)
    self.assertIsNone(find_text_for_target(db, 'word', 'share'))
    self.assertEqual(corpus_sources(db), [1])
