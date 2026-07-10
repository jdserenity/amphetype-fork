import sqlite3
import tempfile
import unittest
from typing_program.WeakSpotLessons import (
  LessonIndex,
  _make_index,
  allocate_repeats,
  build_lesson,
  build_focus_lesson, focus_covered_targets,
  build_lesson_from_db,
  compose_phrase,
  covered_targets,
  fetch_db_marker,
  fetch_weak_targets,
  is_practice_word,
  lesson_cache_valid,
  load_wordlist,
  phrase_for_trigram,
  score_target,
  target_key,
  word_pairs_for_trigram,
)
import random


# A dictionary rich enough to satisfy the weird trigram shapes below.
DICT = [
  "above", "home", "blue", "horizon", "large", "house", "safe", "harbor",
  "from", "fly", "cloth", "spell", "cat", "dog", "community", "comedy",
  "become", "common", "grape", "ever", "your", "tripod", "hello", "also",
  "always", "almost", "school", "control", "symbol", "few", "feel",
  "federal", "at", "apple", "orange", "yellow",
]


def _R(seed=0):
  return random.Random(seed)


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
    create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real);
    create table statistic (w real, data text, type integer, time real,
      count integer, mistakes integer, viscosity real, source integer);
  """)
  return conn


def _add_source(conn, name, discount=None):
  conn.execute('insert into source (name, discount) values (?, ?)', (name, discount))
  return conn.execute('select rowid from source where name = ?', (name,)).fetchone()[0]


def _wordlist_file(words):
  f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
  f.write(' '.join(words)); f.close()
  return f.name


def _keys(targets):
  return {(t[0], t[1]) for t in targets}


class TestCoveredTargets(unittest.TestCase):
  def test_substring_truth(self):
    targets = [("trigram", "e h", 1.0), ("trigram", "om", 1.0),
               ("word", "home", 1.0), ("char", "a", 1.0), ("char", "z", 1.0)]
    got = covered_targets("above home", targets)
    self.assertIn(("trigram", "e h"), got)
    self.assertIn(("trigram", "om"), got)
    self.assertIn(("word", "home"), got)
    self.assertIn(("char", "a"), got)
    self.assertNotIn(("char", "z"), got)

  def test_word_match_ignores_attached_punct(self):
    targets = [("word", "grape", 1.0)]
    self.assertIn(("word", "grape"), covered_targets('"Grape" ever', targets))

  def test_char_is_case_sensitive(self):
    self.assertIn(("char", "C"), covered_targets("Cloth", [("char", "C", 1.0)]))
    self.assertNotIn(("char", "C"), covered_targets("cloth", [("char", "C", 1.0)]))


class TestWeirdTrigrams(unittest.TestCase):
  """Every trigram is just a 3-char window; the rendered text must contain it literally."""

  def _assert_hits(self, tri):
    index = _make_index([("trigram", tri, 1.0)], DICT)
    phrase = phrase_for_trigram(tri, index, _R(1))
    self.assertTrue(phrase, f"no phrase produced for {tri!r}")
    self.assertIn(tri, phrase, f"{tri!r} not in {phrase!r}")

  def test_cross_word_letters(self):    self._assert_hits("e h")
  def test_in_word_letters(self):       self._assert_hits("com")
  def test_trailing_comma(self):        self._assert_hits("ol,")
  def test_letter_comma_quote(self):    self._assert_hits('o,"')
  def test_comma_quote_space(self):     self._assert_hits('," ')
  def test_hyphen_letters(self):        self._assert_hits("-fe")
  def test_word_then_space(self):       self._assert_hits("At ")
  def test_space_then_word(self):       self._assert_hits(" Al")
  def test_quote_space_letter(self):    self._assert_hits('" e')
  def test_period_space_letter(self):   self._assert_hits(". y")

  def test_build_lesson_hits_weird_set(self):
    weird = ["ol,", '," ', "-fe", "At ", 'o,"', " Al"]
    targets = [("trigram", t, 1.0) for t in weird]
    lesson = build_lesson(targets, DICT, rng=_R(3))
    covered = covered_targets(lesson, targets)
    self.assertEqual(covered, _keys(targets), f"missed in {lesson!r}: {_keys(targets)-covered}")


class TestCompression(unittest.TestCase):
  """Density is a per-phrase property: one word/biword should pack many targets."""

  def test_single_word_covers_many(self):
    targets = [("word", "become", 5.0), ("trigram", "com", 4.0),
               ("char", "b", 1.0), ("char", "o", 1.0), ("char", "m", 1.0)]
    index = _make_index(targets, DICT)
    line = compose_phrase(targets, index, _R(0))
    self.assertEqual(line, "become")
    self.assertEqual(covered_targets(line, targets), _keys(targets))

  def test_biword_covers_four(self):
    targets = [("trigram", "e h", 5.0), ("word", "above", 3.0),
               ("word", "home", 3.0), ("char", "h", 1.0)]
    lesson = build_lesson(targets, DICT, min_chars=40, max_chars=200, rng=_R(0))
    self.assertEqual(covered_targets(lesson, targets), _keys(targets))

  def test_build_covers_all_targets(self):
    targets = [
      ("trigram", "e h", 9.0), ("word", "home", 8.0), ("word", "above", 7.0),
      ("trigram", "com", 6.0), ("word", "become", 5.0), ("char", "G", 4.0),
      ("word", "grape", 3.0),
    ]
    lesson = build_lesson(targets, DICT, min_chars=120, max_chars=400, rng=_R(2))
    self.assertEqual(covered_targets(lesson, targets), _keys(targets))

  def test_redundant_target_reuses_same_word(self):
    # 'home' already contains 'om', so the 'om' target reuses 'home', never a new word.
    targets = [("word", "home", 5.0), ("trigram", "om", 1.0)]
    lesson = build_lesson(targets, DICT, min_chars=40, max_chars=200, rng=_R(0))
    self.assertEqual(set(lesson.split()), {"home"})
    self.assertEqual(covered_targets(lesson, targets), _keys(targets))


class TestNoFiller(unittest.TestCase):
  def test_single_word_lesson_is_only_that_word(self):
    targets = [("word", "from", 5.0)]
    lesson = build_lesson(targets, DICT, min_chars=40, max_chars=200, rng=_R(1))
    self.assertEqual(set(lesson.split()), {"from"})
    self.assertGreater(len(lesson.split()), 1)   # importance -> repeated practice

  def test_no_phrase_practises_nothing(self):
    # Every space-joined chunk we emit must cover at least one target; here the
    # only legal tokens come from the target words + trigram boundaries.
    targets = [("trigram", "e h", 3.0), ("word", "from", 2.0), ("char", "c", 1.0)]
    lesson = build_lesson(targets, DICT, min_chars=120, max_chars=400, rng=_R(1))
    self.assertEqual(covered_targets(lesson, targets), _keys(targets))


class TestFocusDrill(unittest.TestCase):
  def test_focus_drill_repeats_single_word(self):
    targets = [('word', 'from')]
    lesson = build_focus_lesson(targets, DICT, max_chars=600, rng=_R(9))
    self.assertIn('from', lesson.lower())
    self.assertGreater(len(lesson.split()), 18)
    self.assertGreater(lesson.lower().count('from'), 8)

  def test_focus_drill_covers_all_targets(self):
    targets = [('word', 'from'), ('trigram', 'e h')]
    lesson = build_focus_lesson(targets, DICT, min_chars=120, max_chars=400, rng=_R(2))
    self.assertEqual(covered_targets(lesson, [(k, d, 1.0) for k, d in targets]), {('word', 'from'), ('trigram', 'e h')})

  def test_focus_drill_preserves_exact_word_surface(self):
    targets = [('word', 'lady'), ('word', 'Meryton')]
    lesson = build_focus_lesson(targets, DICT, max_chars=400, rng=_R(3))
    self.assertRegex(lesson, r'(?<![A-Za-z])lady(?![A-Za-z])')
    self.assertNotRegex(lesson, r'(?<![a-z])Lady(?![a-z])')
    self.assertRegex(lesson, r'(?<![A-Za-z])Meryton(?![A-Za-z])')

  def test_focus_covered_words_are_case_sensitive(self):
    targets = [('word', 'However'), ('word', 'however'), ('word', 'with')]
    self.assertEqual(focus_covered_targets('However', targets), {('word', 'However')})
    self.assertEqual(
      focus_covered_targets('However however with', targets),
      {('word', 'However'), ('word', 'however'), ('word', 'with')})

  def test_focus_drill_includes_biword_pairs(self):
    targets = [('biword', 'of the'), ('biword', 'the people')]
    lesson = build_focus_lesson(targets, DICT, max_chars=400, rng=_R(11))
    cov = focus_covered_targets(lesson, targets)
    self.assertEqual(cov, {('biword', 'of the'), ('biword', 'the people')})
    self.assertRegex(lesson, r'(?<![A-Za-z])of the(?![A-Za-z])')
    self.assertRegex(lesson, r'(?<![A-Za-z])the people(?![A-Za-z])')

  def test_focus_covered_biwords_need_consecutive_words(self):
    targets = [('biword', 'of the')]
    self.assertEqual(focus_covered_targets('of the land', targets), {('biword', 'of the')})
    self.assertEqual(focus_covered_targets('of all the', targets), set())

  def test_focus_drill_includes_all_three_oblivion_words(self):
    targets = [('word', 'However'), ('word', 'however'), ('word', 'with')]
    lesson = build_focus_lesson(targets, DICT, max_chars=600, rng=_R(7))
    cov = focus_covered_targets(lesson, targets)
    self.assertEqual(cov, {('word', 'However'), ('word', 'however'), ('word', 'with')})

  def test_focus_drill_balances_three_words(self):
    targets = [('word', 'from'), ('word', 'with'), ('word', 'blue')]
    lesson = build_focus_lesson(targets, DICT, max_chars=600, rng=_R(42))
    toks = lesson.lower().split()
    for w in ('from', 'with', 'blue'):
      self.assertGreaterEqual(toks.count(w), 3, w)

  def test_focus_drill_not_strict_round_robin(self):
    """Ordering should not be word1 word2 word3 word1 word2 word3 forever."""
    words = ['from', 'with', 'blue', 'home', 'safe']
    targets = [('word', w) for w in words]
    pure = 0
    for seed in range(24):
      lesson = build_focus_lesson(targets, DICT, max_chars=240, rng=_R(seed))
      toks = [t for t in lesson.split() if t in words]
      if len(toks) < 10:
        continue
      head = toks[:5]
      if set(head) == set(words) and all(toks[i] == head[i % 5] for i in range(len(toks))):
        pure += 1
    self.assertLess(pure, 6)

  def test_focus_drill_equal_weight_five_words(self):
    words = ['from', 'with', 'blue', 'home', 'safe']
    targets = [('word', w) for w in words]
    lesson = build_focus_lesson(targets, DICT, max_chars=400, rng=_R(11))
    toks = [t for t in lesson.split() if t in words]
    counts = [toks.count(w) for w in words]
    self.assertGreaterEqual(min(counts), 1)
    # Equal copies in the pool; a random prefix may clip by a couple.
    self.assertLessEqual(max(counts) - min(counts), 2)

  def test_focus_drill_ordering_is_highly_varied(self):
    """Across seeds, 8-word prefixes should almost all be unique — not a few loops."""
    words = ['from', 'with', 'blue', 'home', 'safe']
    targets = [('word', w) for w in words]
    prefixes = set()
    for seed in range(40):
      lesson = build_focus_lesson(targets, DICT, max_chars=240, rng=_R(seed))
      toks = [t for t in lesson.split() if t in words]
      if len(toks) >= 8:
        prefixes.add(tuple(toks[:8]))
    self.assertGreaterEqual(len(prefixes), 28)

  def test_focus_drill_allows_adjacent_repeats(self):
    """True shuffle: same word may appear back-to-back (no anti-repeat smoothing)."""
    words = ['from', 'with', 'blue', 'home', 'safe']
    targets = [('word', w) for w in words]
    saw_adjacent = False
    for seed in range(40):
      lesson = build_focus_lesson(targets, DICT, max_chars=240, rng=_R(seed))
      toks = [t for t in lesson.split() if t in words]
      if any(toks[i] == toks[i + 1] for i in range(len(toks) - 1)):
        saw_adjacent = True
        break
    self.assertTrue(saw_adjacent)

  def test_focus_drill_respects_max_chars_not_half(self):
    """Focus size is the configured max, not half of lesson max_chars."""
    targets = [('word', 'from')]
    short = build_focus_lesson(targets, DICT, min_chars=40, max_chars=80, rng=_R(1))
    long = build_focus_lesson(targets, DICT, min_chars=40, max_chars=240, rng=_R(1))
    self.assertLessEqual(len(short), 80 + 20)  # one trailing phrase may push slightly
    self.assertGreater(len(long), len(short))
    self.assertLessEqual(len(long), 240 + 30)

  def test_normalize_focus_drill_chars(self):
    from typing_program.WeakSpotLessons import normalize_focus_drill_chars
    self.assertEqual(normalize_focus_drill_chars(80, 300), (80, 300))
    self.assertEqual(normalize_focus_drill_chars(400, 100), (100, 400))  # swap inverted
    self.assertEqual(normalize_focus_drill_chars(0, 50), (1, 50))



class TestScoring(unittest.TestCase):
  """Importance ('damage') = slowness² x (count + misses). Frequency matters a lot."""

  def test_slower_beats_faster_at_equal_count(self):
    self.assertGreater(score_target(0.5, 5, 0), score_target(0.1, 5, 0))

  def test_frequent_dominates_slow_but_rare(self):
    slow_rare = score_target(time=1.0, count=1, misses=0)      # painful once
    fast_common = score_target(time=0.3, count=100, misses=0)  # typed constantly
    self.assertGreater(fast_common, slow_rare)

  def test_count_breaks_ties(self):
    self.assertGreater(score_target(0.4, 50, 0), score_target(0.4, 5, 0))

  def test_mistakes_increase_score(self):
    self.assertGreater(score_target(0.4, 20, 10), score_target(0.4, 20, 0))


class TestAllocateRepeats(unittest.TestCase):
  def test_importance_drives_repeat_count(self):
    targets = [("word", "big", 10.0), ("word", "small", 1.0)]
    counts = allocate_repeats(targets, budget=12)
    self.assertGreater(counts[("word", "big")], counts[("word", "small")])
    self.assertGreaterEqual(counts[("word", "small")], 1)

  def test_every_target_appears_at_least_once(self):
    targets = [("word", "a" * 3, 5.0), ("word", "b" * 3, 0.0)]
    counts = allocate_repeats(targets, budget=3)
    self.assertTrue(all(v >= 1 for v in counts.values()))


class TestRepetition(unittest.TestCase):
  def test_important_target_repeated_more(self):
    targets = [("word", "wwww", 10.0), ("word", "qqqq", 1.0)]
    lesson = build_lesson(targets, [], min_chars=120, max_chars=400, rng=_R(3))
    toks = lesson.split()
    self.assertGreater(toks.count("wwww"), toks.count("qqqq"))
    self.assertEqual(covered_targets(lesson, targets), _keys(targets))


class TestFreshness(unittest.TestCase):
  def test_realizations_vary_across_lessons(self):
    targets = [("trigram", "e h", 5.0)]
    a = build_lesson(targets, DICT, min_chars=140, max_chars=400, rng=random.Random(1))
    b = build_lesson(targets, DICT, min_chars=140, max_chars=400, rng=random.Random(2))
    self.assertNotEqual(a, b)

  def test_recent_keys_are_de_emphasized(self):
    targets = [("word", "xxxx", 5.0), ("word", "yyyy", 5.0)]
    base = build_lesson(targets, [], min_chars=40, max_chars=400, rng=random.Random(1))
    rec = build_lesson(targets, [], min_chars=40, max_chars=400, rng=random.Random(1),
                       recent={("word", "xxxx")})
    self.assertLess(rec.split().count("xxxx"), base.split().count("xxxx"))


class TestWeakWordPriority(unittest.TestCase):
  def test_in_word_trigram_prefers_weak_word(self):
    targets = [("word", "become", 5.0), ("word", "common", 3.0), ("trigram", "com", 1.0)]
    index = _make_index(targets, ["community", "comedy"])
    line = compose_phrase(targets, index, _R(0))
    self.assertIn(line, ("become", "common"))

  def test_char_uses_weak_grape(self):
    targets = [("char", "G", 2.0), ("word", "grape", 5.0)]
    index = _make_index(targets, DICT)
    self.assertEqual(compose_phrase(targets, index), "Grape")

  def test_quote_trigram(self):
    targets = [("word", "grape", 3.0), ("word", "ever", 3.0), ("trigram", '" e', 2.0)]
    index = _make_index(targets, DICT)
    line = compose_phrase(targets, index, _R(0))
    self.assertIn('" e', line)
    self.assertIn("grape", line.lower())
    self.assertIn("ever", line)

  def test_period_trigram(self):
    targets = [("word", "your", 3.0), ("word", "tripod", 2.0), ("trigram", ". y", 2.0)]
    index = _make_index(targets, DICT)
    line = compose_phrase(targets, index, _R(0))
    self.assertIn(". y", line)
    self.assertIn("your", line)


class TestComposePhrase(unittest.TestCase):
  def setUp(self):
    self.index = LessonIndex([], DICT)

  def test_trigram_only(self):
    line = compose_phrase([("trigram", "e h", 1.0)], self.index, _R(0))
    self.assertIn("e h", line)

  def test_word_from_db_not_in_dict(self):
    targets = [("word", "xyzzy", 1.0)]
    index = _make_index(targets, DICT)
    self.assertEqual(compose_phrase(targets, index, _R(0)), "xyzzy")

  def test_trigram_no_match_returns_empty(self):
    line = compose_phrase([("trigram", "q z", 1.0)], LessonIndex([], ["cat", "dog"]), _R(0))
    self.assertEqual(line, "")


class TestTrigramHelper(unittest.TestCase):
  def test_cross_word_e_h(self):
    pairs = word_pairs_for_trigram("e h", DICT)
    self.assertIn(("above", "home"), pairs)


class TestPracticeWordFilter(unittest.TestCase):
  def test_letters_only(self):
    self.assertTrue(is_practice_word("hello"))
    self.assertFalse(is_practice_word('"Spell"'))
    self.assertFalse(is_practice_word("a-b"))


class TestLessonCache(unittest.TestCase):
  def test_cache_valid_when_marker_unchanged(self):
    m = (1000.0, 42)
    self.assertTrue(lesson_cache_valid(('hello world', m), m))

  def test_cache_invalid_when_stats_added(self):
    self.assertFalse(lesson_cache_valid(('hello world', (1000.0, 42)), (1001.0, 43)))

  def test_db_marker_changes_after_insert(self):
    conn = _test_db()
    m0 = fetch_db_marker(conn)
    conn.execute('insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
                 (999.0, 'x', 2, 0.3, 1, 0, 1.0))
    self.assertNotEqual(m0, fetch_db_marker(conn))


class TestDbIntegration(unittest.TestCase):
  def test_fetch_weak_targets_all_types_and_scored(self):
    conn = _test_db(); now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
      [
        (now, 'C', 0, 0.5, 10, 2, 1.0),
        (now, 'e h', 1, 0.4, 8, 1, 1.0),
        (now, 'from', 2, 0.3, 12, 3, 1.0),
      ])
    targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
    self.assertEqual({t[0] for t in targets}, {'char', 'trigram', 'word'})
    self.assertTrue(all(t[2] > 0 for t in targets))

  def test_frequent_costly_item_ranked_first(self):
    conn = _test_db(); now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
      [
        (now, 'slow', 2, 1.0, 2, 0, 1.0),     # painful but rare (at analysis floor)
        (now, 'fast', 2, 0.3, 500, 0, 1.0),   # constant typing cost
      ])
    targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
    words = [t[1] for t in targets if t[0] == 'word']
    self.assertEqual(words[0], 'fast')

  def test_one_shot_words_never_enter_weak_targets(self):
    conn = _test_db(); now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
      [
        (now, 'once', 2, 2.0, 1, 1, 1.0),
        (now, 'twice', 2, 0.4, 2, 0, 1.0),
      ])
    targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
    words = [t[1] for t in targets if t[0] == 'word']
    self.assertEqual(words, ['twice'])

  def test_discounted_source_stats_excluded_from_analysis_aggregate(self):
    conn = _test_db(); now = 1e9
    from typing_program.Data import STAT_OMIT_DISCOUNTED
    book = _add_source(conn, 'My Book')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'realword', 2, 0.4, 20, 1, 1.0, book),
        (now, 'drillword', 2, 1.0, 500, 0, 1.0, weak),
      ])
    sql = """select data, sum(count) as total from statistic as st
      left join source as src on st.source = src.rowid
      where st.type = 2 and %s group by data""" % STAT_OMIT_DISCOUNTED
    rows = conn.execute(sql).fetchall()
    words = [r[0] for r in rows]
    self.assertEqual(words, ['realword'])
    self.assertNotIn('drillword', words)

  def test_weakspot_stats_excluded_from_selection(self):
    conn = _test_db(); now = 1e9
    book = _add_source(conn, 'My Book')
    weak = _add_source(conn, '<Weakspot>', 1)
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity,source) values (?,?,?,?,?,?,?,?)',
      [
        (now, 'realword', 2, 0.4, 20, 1, 1.0, book),
        (now, 'drillword', 2, 1.0, 500, 0, 1.0, weak),  # would dominate if counted
      ])
    targets = fetch_weak_targets(conn, hist=0, min_count=1, per_type=5)
    words = [t[1] for t in targets if t[0] == 'word']
    self.assertEqual(words, ['realword'])
    self.assertNotIn('drillword', words)

  def test_build_lesson_from_db_covers_targets(self):
    conn = _test_db(); now = 1e9
    conn.executemany(
      'insert into statistic (w,data,type,time,count,mistakes,viscosity) values (?,?,?,?,?,?,?)',
      [
        (now, 'e h', 1, 0.4, 20, 1, 1.0),
        (now, 'from', 2, 0.3, 20, 1, 1.0),
      ])
    path = _wordlist_file(DICT)
    lesson, emphasized = build_lesson_from_db(conn, hist=0, min_count=1, per_type=10,
                                  min_chars=40, max_chars=400, wordlist_path=path, rng=_R(2))
    self.assertIn("e h", lesson)
    self.assertIn("from", lesson.lower().split())
    self.assertTrue(emphasized)


if __name__ == "__main__":
  unittest.main()
