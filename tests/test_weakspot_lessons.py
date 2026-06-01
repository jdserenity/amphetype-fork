import sqlite3
import tempfile
import unittest
from amphetype.WeakSpotLessons import (
  LessonIndex,
  _make_index,
  build_lesson,
  build_lesson_from_db,
  compose_phrase,
  fetch_db_marker,
  fetch_weak_targets,
  lesson_cache_valid,
  load_wordlist,
  word_pairs_for_trigram,
)


DICT = [
  "above", "home", "blue", "horizon", "large", "house", "safe", "harbor",
  "from", "fly", "cloth", "spell", "cat", "dog", "community", "comedy",
]


class _MedianAggregate(list):
  def step(self, val):
    if val is not None:
      self.append(val)
  def finalize(self):
    if not self:
      return None
    s = sorted(self)
    n = len(s)
    if n & 1:
      return s[n // 2]
    return (s[n // 2] + s[n // 2 - 1]) / 2.0


def _test_db():
  conn = sqlite3.connect(':memory:')
  conn.create_aggregate('agg_median', 1, _MedianAggregate)
  conn.executescript("""
    create table statistic (w real, data text, type integer, time real,
      count integer, mistakes integer, viscosity real);
  """)
  return conn


def _wordlist_file(words):
  f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
  f.write(' '.join(words))
  f.close()
  return f.name


class TestLessonCache(unittest.TestCase):
  def test_cache_valid_when_marker_unchanged(self):
    m = (1000.0, 42)
    self.assertTrue(lesson_cache_valid(('hello world', m), m))

  def test_cache_invalid_when_stats_added(self):
    cached = ('hello world', (1000.0, 42))
    self.assertFalse(lesson_cache_valid(cached, (1001.0, 43)))

  def test_db_marker_changes_after_insert(self):
    conn = _test_db()
    m0 = fetch_db_marker(conn)
    conn.execute(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
      (999.0, 'x', 2, 0.3, 1, 0, 1.0))
    self.assertNotEqual(m0, fetch_db_marker(conn))


class TestPracticeWordFilter(unittest.TestCase):
  def test_letters_only(self):
    from amphetype.WeakSpotLessons import is_practice_word
    self.assertTrue(is_practice_word("hello"))
    self.assertFalse(is_practice_word('"Spell"'))
    self.assertFalse(is_practice_word("a-b"))


class TestTrigramLookup(unittest.TestCase):
  def test_cross_word_e_h(self):
    pairs = word_pairs_for_trigram("e h", DICT)
    self.assertIn(("above", "home"), pairs)


class TestWeakWordPriority(unittest.TestCase):
  def test_in_word_trigram_prefers_weak_word(self):
    targets = [
      ("word", "become", 5.0),
      ("word", "common", 3.0),
      ("trigram", "com", 1.0),
    ]
    index = _make_index(targets, ["community", "comedy"])
    line = compose_phrase(targets, index, __import__("random").Random(0))
    self.assertIn(line, ("become", "common"))

  def test_char_uses_weak_grape(self):
    targets = [("char", "G", 2.0), ("word", "grape", 5.0)]
    index = _make_index(targets, DICT)
    line = compose_phrase(targets, index)
    self.assertEqual(line, "Grape")

  def test_quote_trigram(self):
    targets = [
      ("word", "grape", 3.0),
      ("word", "ever", 3.0),
      ("trigram", '" e', 2.0),
    ]
    index = _make_index(targets, DICT)
    line = compose_phrase(targets, index, __import__("random").Random(0))
    self.assertIn('"Grape"', line)
    self.assertIn('ever', line)

  def test_period_trigram(self):
    targets = [
      ("word", "your", 3.0),
      ("word", "tripod", 2.0),
      ("trigram", ". y", 2.0),
    ]
    index = _make_index(targets, DICT)
    line = compose_phrase(targets, index, __import__("random").Random(0))
    self.assertIn('your', line)
    self.assertIn('.', line)


class TestComposePhrase(unittest.TestCase):
  def setUp(self):
    self.index = LessonIndex([], DICT)
    self.rng = __import__("random").Random(0)

  def test_trigram_only(self):
    line = compose_phrase([("trigram", "e h", 1.0)], self.index)
    w1, w2 = line.split()
    self.assertEqual(w1[-1] + ' ' + w2[0], "e h")

  def test_word_from_db_not_in_dict(self):
    targets = [("word", "xyzzy", 1.0)]
    index = _make_index(targets, DICT)
    line = compose_phrase(targets, index, self.rng)
    self.assertEqual(line, "xyzzy")

  def test_trigram_no_match_returns_empty_not_filler(self):
    line = compose_phrase([("trigram", "q z", 1.0)], self.index, self.rng)
    self.assertEqual(line, '')


class TestBuildLesson(unittest.TestCase):
  def test_no_random_filler_words(self):
    targets = [
      ("trigram", "e h", 3.0),
      ("word", "from", 2.0),
      ("char", "c", 1.0),
    ]
    lesson = build_lesson(targets, DICT, min_chars=999, max_chars=4000, rng=__import__("random").Random(1))
    self.assertTrue(lesson)


class TestDbIntegration(unittest.TestCase):
  def test_fetch_weak_targets_all_types(self):
    conn = _test_db()
    now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
      [
        (now, 'C', 0, 0.5, 10, 2, 1.0),
        (now, 'e h', 1, 0.4, 8, 1, 1.0),
        (now, 'from', 2, 0.3, 12, 3, 1.0),
      ])
    targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
    self.assertEqual({t[0] for t in targets}, {'char', 'trigram', 'word'})

  def test_build_lesson_from_db(self):
    conn = _test_db()
    now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
      [
        (now, 'e h', 1, 0.4, 20, 1, 1.0),
        (now, 'from', 2, 0.3, 20, 1, 1.0),
      ])
    path = _wordlist_file(DICT)
    lesson = build_lesson_from_db(conn, hist=0, min_count=1, per_type=10,
                                  min_chars=40, max_chars=200, wordlist_path=path,
                                  rng=__import__("random").Random(2))
    self.assertGreaterEqual(len(lesson), 40)


if __name__ == "__main__":
  unittest.main()
