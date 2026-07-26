"""Corpus mode: equal-weight book rotation with DB-persisted used set."""

import hashlib
import random
import sqlite3

import pytest

from typing_program.Data import AppDatabase
from typing_program.app_meta import ensure_app_meta, get_app_meta_raw
from typing_program.corpus_select import (
  CORPUS_USED_SOURCES_KEY,
  list_eligible_corpus_sources,
  load_used_sources,
  pick_corpus_text,
  save_used_sources,
)


@pytest.fixture
def db():
  return sqlite3.connect(':memory:', 5, 0, 'DEFERRED', False, AppDatabase)


def _src(db, name, discount=None):
  db.execute('insert into source (name, discount) values (?,?)', (name, discount))
  db.commit()
  return db.execute('select rowid from source where name=?', (name,)).fetchone()[0]


def _text(db, source_id, body, disabled=None):
  tid = hashlib.sha1(body.encode('utf-8')).hexdigest()
  db.execute(
    'insert into text (id,text,source,disabled) values (?,?,?,?)',
    (tid, body, source_id, disabled))
  db.commit()
  return tid


def test_eligible_sources_skip_discounted_system_and_disabled(db):
  a = _src(db, 'Alice.txt')
  b = _src(db, 'Bob.txt')
  _src(db, '<Weakspot>', discount=1)
  _src(db, '<Reviews>', discount=2)
  dead = _src(db, 'All Disabled.txt')
  _text(db, a, 'alice passage one with enough words here')
  _text(db, b, 'bob passage one with enough words here')
  _text(db, dead, 'disabled only', disabled=1)
  assert set(list_eligible_corpus_sources(db)) == {a, b}


def test_used_sources_roundtrip_in_app_meta(db):
  ensure_app_meta(db)
  save_used_sources(db, {3, 1, 2})
  assert load_used_sources(db) == {1, 2, 3}
  raw = get_app_meta_raw(db, CORPUS_USED_SOURCES_KEY)
  assert raw is not None


def test_pick_rotates_books_without_replacement(db):
  ids = [_src(db, f'Book{i}.txt') for i in range(3)]
  for sid in ids:
    _text(db, sid, f'passage for source {sid} with enough padding words')
  rng = random.Random(7)
  seen = []
  for _ in range(3):
    row = pick_corpus_text(db, rng=rng)
    assert row is not None
    seen.append(row[1])
  assert set(seen) == set(ids)
  assert load_used_sources(db) == set(ids)


def test_pick_resets_round_when_pool_exhausted(db):
  ids = [_src(db, f'Book{i}.txt') for i in range(2)]
  for sid in ids:
    _text(db, sid, f'only passage for {sid} enough words yes')
  rng = random.Random(1)
  first = {pick_corpus_text(db, rng=rng)[1] for _ in range(2)}
  assert first == set(ids)
  # Round exhausted → next pick starts fresh (used becomes {chosen}).
  row = pick_corpus_text(db, rng=rng)
  assert row[1] in ids
  assert load_used_sources(db) == {row[1]}


def test_pick_persists_used_across_calls(db):
  a = _src(db, 'A.txt')
  b = _src(db, 'B.txt')
  _text(db, a, 'text a with enough words for a lesson chunk')
  _text(db, b, 'text b with enough words for a lesson chunk')
  pick_corpus_text(db, rng=random.Random(0))
  used_after_one = load_used_sources(db)
  assert len(used_after_one) == 1
  # New "session": same DB, used set still there.
  remaining = set(list_eligible_corpus_sources(db)) - used_after_one
  row = pick_corpus_text(db, rng=random.Random(99))
  assert row[1] in remaining
  assert load_used_sources(db) == used_after_one | {row[1]}


def test_pick_within_chosen_book_is_random(db):
  sid = _src(db, 'One Book.txt')
  tids = [
    _text(db, sid, f'chunk {i} with enough padding words to be unique')
    for i in range(5)
  ]
  hits = {pick_corpus_text(db, rng=random.Random(i))[0] for i in range(40)}
  assert hits == set(tids)


def test_pick_returns_none_when_empty(db):
  assert pick_corpus_text(db) is None


def test_stale_used_ids_are_pruned(db):
  a = _src(db, 'Keep.txt')
  gone = _src(db, 'Gone.txt')
  _text(db, a, 'keep me with enough words for eligibility')
  save_used_sources(db, {a, gone, 99999})
  row = pick_corpus_text(db, rng=random.Random(2))
  # Only Keep is eligible; used contained Keep so pool empty → reset → pick Keep.
  assert row[1] == a
  assert load_used_sources(db) == {a}
