"""Tests for improve mode submode target selection."""

import random
import re
import sqlite3

from typing_program.improve_mode import (
  IMPROVE_SUBMODE_ACCURACY, IMPROVE_SUBMODE_DAMAGE, IMPROVE_SUBMODE_HESITANT,
  IMPROVE_SUBMODE_LABELS, IMPROVE_SUBMODE_NORMAL, IMPROVE_SUBMODE_OBLIVION,
  IMPROVE_SUBMODE_SLOWEST, IMPROVE_SUBMODE_TRIGRAMS, clamp_improve_submode,
  fetch_improve_submode_targets, is_improve_submode_available, next_improve_submode,
  oblivion_submode_available,
)
from typing_program.stats_query import (
  FOCUS_DRILL_PICK_COUNT, FOCUS_DRILL_POOL_SIZE, STAT_TYPE_TRIGRAM, STAT_TYPE_WORD,
  WORD_ANALYSIS_MIN_COUNT, fetch_accuracy_picks, fetch_slowest_picks,
)
from typing_program.WeakSpotLessons import (
  build_trigram_gibberish_lesson, fetch_weak_targets, fetch_weak_trigram_targets,
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


def _add_source(conn, name, discount=None):
  conn.execute('insert into source (name, discount) values (?,?)', (name, discount))
  return conn.execute('select rowid from source where name=?', (name,)).fetchone()[0]


def _two_books(conn):
  return _add_source(conn, 'BookA'), _add_source(conn, 'BookB')


def _found_word_rows(now, words, books=None):
  """words: (data, time, count, mistakes, viscosity). Split each across 2 books."""
  # books created by caller via _two_books when None not allowed here — require books.
  a, b = books
  out = []
  for data, t, count, mist, visc in words:
    c1 = max(1, int(count) - 1) if count >= 2 else int(count)
    c2 = int(count) - c1
    out.append((now, data, STAT_TYPE_WORD, t, c1, mist, visc, a))
    if c2 > 0:
      out.append((now, data, STAT_TYPE_WORD, t, c2, 0, visc, b))
  return out


def _seed_words(conn, now):
  books = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    _found_word_rows(now, [
      ('slow', 12.0 / 20.0, 10, 0, 5.0),
      ('mid', 12.0 / 60.0, 10, 0, 12.0),
      ('fast', 12.0 / 120.0, 10, 0, 2.0),
      ('risky', 12.0 / 80.0, 10, 5, 3.0),
    ], books))


def test_improve_submode_labels_trigrams_second_after_normal():
  assert IMPROVE_SUBMODE_LABELS[0] == 'normal'
  assert IMPROVE_SUBMODE_LABELS[1] == 'trigrams'
  assert IMPROVE_SUBMODE_TRIGRAMS == 1
  assert IMPROVE_SUBMODE_LABELS == (
    'normal', 'trigrams', 'oblivion', 'slowest', 'hesitant', 'accuracy', 'damage')
  assert IMPROVE_SUBMODE_OBLIVION == 2
  assert IMPROVE_SUBMODE_SLOWEST == 3
  assert IMPROVE_SUBMODE_HESITANT == 4
  assert IMPROVE_SUBMODE_ACCURACY == 5
  assert IMPROVE_SUBMODE_DAMAGE == 6


def test_improve_submode_normal_returns_empty():
  conn = _test_db()
  assert fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_NORMAL, 0, 1) == []


def test_improve_submode_trigrams_returns_empty_targets():
  """Trigrams uses its own lesson builder, not the word focus-drill path."""
  conn = _test_db()
  assert fetch_improve_submode_targets(conn, IMPROVE_SUBMODE_TRIGRAMS, 0, 1) == []


def test_focus_drill_defaults_are_pool_20_pick_5():
  assert FOCUS_DRILL_POOL_SIZE == 20
  assert FOCUS_DRILL_PICK_COUNT == 5


def test_improve_submode_slowest_samples_from_slowest_pool():
  conn = _test_db(); now = 1e9
  _seed_words(conn, now)
  # Only 4 eligible words → pick all of them (order random).
  picks = fetch_improve_submode_targets(
    conn, IMPROVE_SUBMODE_SLOWEST, 0, 1, n=5, rng=random.Random(0))
  assert {t[1] for t in picks} == {'slow', 'mid', 'fast', 'risky'}
  assert all(t[0] == 'word' for t in picks)


def test_improve_submode_samples_five_from_bottom_twenty():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  words = []
  for i in range(30):
    wpm = 10 + i
    words.append(('w%02d' % i, 12.0 / wpm, 10, 0, 1.0))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    _found_word_rows(now, words, books))
  picks = fetch_slowest_picks(conn, 0, STAT_TYPE_WORD, n=5, min_count=1, pool_size=20, rng=random.Random(1))
  assert len(picks) == 5
  names = {r[0] for r in picks}
  assert names <= {'w%02d' % i for i in range(20)}
  assert names.isdisjoint({'w%02d' % i for i in range(20, 30)})


def test_improve_submode_hesitant_samples_high_viscosity_pool():
  conn = _test_db(); now = 1e9
  _seed_words(conn, now)
  picks = fetch_improve_submode_targets(
    conn, IMPROVE_SUBMODE_HESITANT, 0, 1, n=3, rng=random.Random(2))
  assert len(picks) == 3
  assert {t[1] for t in picks} <= {'slow', 'mid', 'fast', 'risky'}
  # mid has highest viscosity (12); with pool of 4 and pick 3, mid is usually included.
  # At minimum every pick is from the ranked pool.
  assert all(t[0] == 'word' for t in picks)


def test_improve_submode_damage_includes_highest_damage_in_pool():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    _found_word_rows(now, [
      ('risky', 12.0 / 40.0, 20, 10, 1.0),
      ('ok', 12.0 / 80.0, 20, 1, 1.0),
      ('fine', 12.0 / 100.0, 20, 0, 1.0),
    ], books))
  picks = fetch_improve_submode_targets(
    conn, IMPROVE_SUBMODE_DAMAGE, 0, 1, n=3, rng=random.Random(0))
  assert {t[1] for t in picks} == {'risky', 'ok', 'fine'}
  assert 'risky' in {t[1] for t in picks}


def test_improve_submode_accuracy_samples_lowest_perfect_pct_pool():
  """Accuracy focus drill picks from the worst perfect-rate words."""
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    _found_word_rows(now, [
      ('typoish', 12.0 / 80.0, 10, 8, 1.0),  # 20% perfect
      ('shaky', 12.0 / 80.0, 10, 5, 1.0),    # 50%
      ('solid', 12.0 / 80.0, 10, 0, 1.0),    # 100%
      ('ok', 12.0 / 80.0, 10, 2, 1.0),       # 80%
    ], books))
  # Pool of worst 3 by perfect % → typoish, shaky, ok; sample all 3.
  picks = fetch_improve_submode_targets(
    conn, IMPROVE_SUBMODE_ACCURACY, 0, 1, n=3, pool_size=3, rng=random.Random(0))
  assert {t[1] for t in picks} == {'typoish', 'shaky', 'ok'}
  assert 'solid' not in {t[1] for t in picks}
  assert all(t[0] == 'word' for t in picks)


def test_fetch_accuracy_picks_samples_from_lowest_perfect_pool():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  words = []
  for i in range(30):
    mistakes = 9 - (i // 4)  # w0..w3 have 9 mistakes, …
    words.append(('w%02d' % i, 12.0 / 80.0, 10, max(0, mistakes), 1.0))
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    _found_word_rows(now, words, books))
  picks = fetch_accuracy_picks(conn, 0, STAT_TYPE_WORD, n=5, min_count=1, pool_size=20, rng=random.Random(1))
  assert len(picks) == 5
  names = {r[0] for r in picks}
  # Worst 20 by perfect % are the ones with most mistakes (lowest i).
  assert names <= {'w%02d' % i for i in range(20)}
  assert names.isdisjoint({'w%02d' % i for i in range(20, 30)})


def test_improve_submode_oblivion_under_threshold():
  conn = _test_db(); now = 1e9
  _seed_words(conn, now)
  picks = fetch_improve_submode_targets(
    conn, IMPROVE_SUBMODE_OBLIVION, 0, 1, n=5, rng=random.Random(0))
  assert {t[1] for t in picks} == {'slow'}


def test_oblivion_submode_hidden_when_no_words():
  conn = _test_db()
  assert not oblivion_submode_available(conn, 0, 1)
  assert not is_improve_submode_available(conn, IMPROVE_SUBMODE_OBLIVION, 0, 1)
  assert next_improve_submode(IMPROVE_SUBMODE_TRIGRAMS, conn, 0, 1) == IMPROVE_SUBMODE_SLOWEST
  assert clamp_improve_submode(IMPROVE_SUBMODE_OBLIVION, conn, 0, 1) == IMPROVE_SUBMODE_NORMAL


def test_oblivion_submode_available_with_one_word():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    _found_word_rows(now, [('slow', 12.0 / 20.0, 10, 0, 1.0)], books))
  assert oblivion_submode_available(conn, 0, 1)
  assert next_improve_submode(IMPROVE_SUBMODE_TRIGRAMS, conn, 0, 1) == IMPROVE_SUBMODE_OBLIVION


def test_focus_drill_submodes_exclude_words_below_analysis_min_count():
  """Holy N: focus drills never pull words that would be hidden from Performance Analysis."""
  conn = _test_db(); now = 1e9
  a, b = _two_books(conn)
  # One book only = not found; two books = found.
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'typo', STAT_TYPE_WORD, 12.0 / 8.0, 1, 1, 50.0, a),
      (now, 'real', STAT_TYPE_WORD, 12.0 / 25.0, 1, 0, 20.0, a),
      (now, 'real', STAT_TYPE_WORD, 12.0 / 25.0, 1, 0, 20.0, b),
      (now, 'solid', STAT_TYPE_WORD, 12.0 / 30.0, 9, 2, 15.0, a),
      (now, 'solid', STAT_TYPE_WORD, 12.0 / 30.0, 1, 0, 15.0, b),
    ])
  for submode in (
      IMPROVE_SUBMODE_OBLIVION, IMPROVE_SUBMODE_SLOWEST,
      IMPROVE_SUBMODE_HESITANT, IMPROVE_SUBMODE_ACCURACY, IMPROVE_SUBMODE_DAMAGE):
    picks = fetch_improve_submode_targets(conn, submode, 0, 1, n=3)
    names = {t[1] for t in picks}
    assert 'typo' not in names, f'{submode} pulled one-book word'
    assert names <= {'real', 'solid'}
    assert picks  # at least one eligible word


def test_fetch_weak_targets_excludes_words_below_analysis_min_count():
  conn = _test_db(); now = 1e9
  a, b = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'once', STAT_TYPE_WORD, 1.0, 1, 0, 1.0, a),
      (now, 'often', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, a),
      (now, 'often', STAT_TYPE_WORD, 0.5, 1, 0, 1.0, b),
      (now, 'x', 0, 0.5, 1, 0, 1.0, a),  # chars still allow count 1
    ])
  targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
  words = [t[1] for t in targets if t[0] == 'word']
  chars = [t[1] for t in targets if t[0] == 'char']
  assert words == ['often']
  assert 'once' not in words
  assert 'x' in chars


def test_improve_submode_always_picks_words_not_trigrams():
  conn = _test_db(); now = 1e9
  books = _two_books(conn)
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'ol,', 1, 12.0 / 10.0, 10, 0, 1.0, books[0]),
      *_found_word_rows(now, [('slowword', 12.0 / 15.0, 10, 0, 1.0)], books),
    ])
  picks = fetch_improve_submode_targets(
    conn, IMPROVE_SUBMODE_SLOWEST, 0, 1, n=5, rng=random.Random(0))
  assert picks == [('word', 'slowword', 15.0)]


def test_fetch_weak_trigram_targets_only_trigrams_by_damage():
  conn = _test_db(); now = 1e9
  conn.executemany(
    'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
    [
      (now, 'xqz', STAT_TYPE_TRIGRAM, 12.0 / 15.0, 20, 5, 1.0, None),
      (now, 'the', STAT_TYPE_TRIGRAM, 12.0 / 80.0, 20, 0, 1.0, None),
      (now, 'e h', STAT_TYPE_TRIGRAM, 12.0 / 40.0, 10, 2, 1.0, None),
      (now, 'slowword', STAT_TYPE_WORD, 12.0 / 10.0, 50, 10, 1.0, None),
    ])
  picks = fetch_weak_trigram_targets(conn, hist=0, min_count=1, limit=10)
  assert all(t[0] == 'trigram' for t in picks)
  assert [t[1] for t in picks] == ['xqz', 'e h', 'the']
  assert 'slowword' not in [t[1] for t in picks]


def test_build_trigram_gibberish_lesson_is_raw_trigram_soup():
  targets = [
    ('trigram', 'xqz', 10.0),
    ('trigram', 'th,', 5.0),
    ('trigram', 'e h', 3.0),
  ]
  lesson = build_trigram_gibberish_lesson(
    targets, min_chars=40, max_chars=120, rng=random.Random(0))
  assert lesson
  # Space-joined raw trigrams only — no dictionary padding words.
  assert re.fullmatch(r'(?:xqz|th,|e h)(?: (?:xqz|th,|e h))*', lesson)
  for tri in ('xqz', 'th,', 'e h'):
    assert tri in lesson
  # Must not look like normal English practice.
  for word in ('the', 'home', 'community', 'harbor', 'above'):
    assert word not in lesson.split()


def test_build_trigram_gibberish_lesson_no_double_spaces():
  """Leading/trailing spaces inside trigrams must not create '  ' runs."""
  targets = [
    ('trigram', 'he ', 8.0),
    ('trigram', ' th', 7.0),
    ('trigram', 'e h', 5.0),
    ('trigram', 'ab ', 4.0),
    ('trigram', 'xqz', 3.0),
  ]
  for seed in range(20):
    lesson = build_trigram_gibberish_lesson(
      targets, min_chars=40, max_chars=120, rng=random.Random(seed))
    assert lesson
    assert '  ' not in lesson, repr(lesson)
    assert not lesson.startswith(' ')
    assert not lesson.endswith(' ')


def test_build_trigram_gibberish_lesson_empty_without_targets():
  assert build_trigram_gibberish_lesson([], min_chars=40, max_chars=120) == ''
