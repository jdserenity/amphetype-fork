"""Compose readable practice lines from weak characters, trigrams, and words."""

import random
import sqlite3
import time
from collections import defaultdict

# type tag, data, weight (higher = prioritize)
Target = tuple

WEAK_SQL = """select data, total*time*time*(1.0+cast(misses as real)/total) as damage
  from (
    select data, agg_median(time) as time, sum(count) as total, sum(mistakes) as misses
    from statistic where w >= ? and type = ? group by data)
  where total >= ?
  order by damage desc limit ?"""

TYPE_TAGS = {0: 'char', 1: 'trigram', 2: 'word'}

_dict_cache = {}
_TRAIL_PUNCT = '.,!?;:'


def is_practice_word(w):
  if not w or len(w) < 2:
    return False
  return w.isalpha()


def _cross_word(trigram):
  return len(trigram) == 3 and trigram[1] == ' '


def _ends_with_surface(form, ch):
  return len(form) > 0 and form[-1] == ch


def _starts_with_surface(form, ch):
  return len(form) > 0 and form[0] == ch


def _surface_end(word, ch):
  """Render word so its last character is ch (quotes, periods, or natural letter)."""
  if ch == '"':
    return f'"{word[0].upper() + word[1:]}"'
  if ch in _TRAIL_PUNCT:
    return word + ch
  if word.endswith(ch):
    return word
  return None


def _pick_by_damage(candidates, dmg):
  if not candidates:
    return None
  return max(candidates, key=lambda w: (dmg.get(w.lower(), 0.0), w))


def word_pairs_for_trigram(trigram, words):
  """Test helper: pairs from a flat word list."""
  out = []
  if _cross_word(trigram):
    a, _, b = trigram
    for w1 in words:
      for w2 in words:
        f1 = _surface_end(w1, a) if not w1.endswith(a) else w1
        if f1 is None and not w1.endswith(a):
          f1 = _surface_end(w1, a)
        if f1 is None:
          continue
        if w2.startswith(b):
          out.append((f1, w2))
  else:
    for w in words:
      if trigram in w:
        out.append((w,))
  return out


def words_containing_char(ch, words):
  cl = ch.lower()
  return [w for w in words if cl in w.lower()]


class LessonIndex:
  """Weak DB words first; bundled dictionary for fill and fallback."""

  def __init__(self, weak_words, dict_words, weak_damage=None):
    self.weak_damage = weak_damage or {}
    self.weak = []
    seen = set()
    for w in weak_words:
      wl = w.lower()
      if wl not in seen and (is_practice_word(w) or wl.isalpha()):
        seen.add(wl)
        self.weak.append(wl)
    self.dict = sorted({w.lower() for w in dict_words if is_practice_word(w)} - seen)
    self._ends = defaultdict(list)
    self._starts = defaultdict(list)
    for w in self.weak + self.dict:
      self._ends[w[-1]].append(w)
      self._starts[w[0]].append(w)
    self.weak_set = set(self.weak)

  @property
  def words(self):
    return self.weak + self.dict

  def _weak_first(self, weak_pool, dict_pool):
    return weak_pool if weak_pool else dict_pool

  def best_in_word(self, tri, rng):
    weak = [w for w in self.weak if tri in w]
    if weak:
      return _pick_by_damage(weak, self.weak_damage), True
    d = [w for w in self.dict if tri in w]
    return (rng.choice(d) if d else ''), False

  def cross_word_pairs(self, tri):
    a, _, b = tri
    pairs = []
    seen = set()
    for from_weak in (True, False):
      words = self.weak if from_weak else self.dict
      for w in words:
        if w.endswith(a):
          f1 = w
        else:
          f1 = _surface_end(w, a)
        if f1 is None:
          continue
        w2_weak = [x for x in self.weak if x.startswith(b)]
        w2_dict = [x for x in self.dict if x.startswith(b)]
        for w2 in self._weak_first(w2_weak, w2_dict):
          key = (f1, w2)
          if key in seen:
            continue
          seen.add(key)
          pairs.append((f1, w2, w in self.weak_set, w2 in self.weak_set))
    return pairs

  def best_cross_pair(self, tri, rng):
    pairs = self.cross_word_pairs(tri)
    if not pairs:
      return None
    def rank(p):
      form1, w2, w1_weak, w2_weak = p
      pri = (2 if w1_weak else 0) + (2 if w2_weak else 0)
      raw1 = form1.strip('"').rstrip(_TRAIL_PUNCT).lower()
      d = self.weak_damage.get(w2.lower(), 0) + self.weak_damage.get(raw1, 0)
      return (pri, d, rng.random())
    form1, w2, _, _ = max(pairs, key=rank)
    return form1, w2

  def random_word(self, rng, prefer_weak=False):
    if prefer_weak and self.weak:
      return _pick_by_damage(self.weak, self.weak_damage)
    pool = self.dict or self.weak
    return rng.choice(pool) if pool else ''

  def word_for_char(self, ch, rng):
    weak = words_containing_char(ch, self.weak)
    if weak:
      return _capitalize_for_char(_pick_by_damage(weak, self.weak_damage), ch)
    d = words_containing_char(ch, self.dict)
    if d:
      return _capitalize_for_char(rng.choice(d), ch)
    w = self.random_word(rng)
    return _capitalize_for_char(w, ch) if w else ''


DictIndex = LessonIndex  # compat
CorpusIndex = LessonIndex


def load_wordlist(path):
  try:
    with open(path, 'r', encoding='utf-8-sig') as f:
      return [w.lower() for w in f.read().split() if is_practice_word(w)]
  except OSError:
    return []


def get_dict_index(wordlist_path):
  if wordlist_path not in _dict_cache:
    _dict_cache[wordlist_path] = LessonIndex([], load_wordlist(wordlist_path))
  return _dict_cache[wordlist_path]


def _capitalize_for_char(word, ch):
  if not word:
    return word
  if ch.isupper():
    return word[0].upper() + word[1:]
  return word


def _weak_damage_map(targets):
  return {t[1].lower(): t[2] for t in targets if t[0] == 'word'}


def _weak_word_list(targets):
  return [t[1] for t in targets if t[0] == 'word']


def _apply_targets_to_tokens(w1, w2, targets):
  chars = [t for t in targets if t[0] == 'char']
  words_only = [t for t in targets if t[0] == 'word']
  dmg = _weak_damage_map(targets)
  for _, data, _ in words_only:
    dl = data.lower()
    if w2 and w2.lower() == dl:
      w2 = data
    if w1 and w1.strip('"').lower() == dl:
      if w1.startswith('"'):
        w1 = f'"{data[0].upper() + data[1:]}"'
      else:
        w1 = data
  for _, ch, _ in chars:
    if w1 and ch.lower() in w1.lower():
      if w1.startswith('"'):
        inner = w1.strip('"')
        w1 = f'"{_capitalize_for_char(inner, ch)}"'
      else:
        w1 = _capitalize_for_char(w1.rstrip(_TRAIL_PUNCT), ch) + (w1[-1] if w1[-1] in _TRAIL_PUNCT else '')
    if w2 and ch.lower() in w2.lower():
      w2 = _capitalize_for_char(w2, ch)
  # prefer weak word for char when listed
  for _, ch, _ in chars:
    for _, data, _ in words_only:
      if ch.lower() in data.lower():
        w = _capitalize_for_char(data, ch)
        if w2 and w2.lower() == data.lower():
          w2 = w
        elif w1 and w1.strip('"').lower() == data.lower():
          w1 = f'"{w}"' if w1.startswith('"') else w
  return w1, w2


def _target_weights(targets):
  return {t[1]: t[2] for t in targets}


def _pick_weak_word_fallback(words_only, chars, dmg, rng):
  if words_only:
    w = _pick_by_damage([t[1] for t in words_only], dmg)
    for _, ch, _ in chars:
      w = _capitalize_for_char(w, ch)
    return w
  return ''


def compose_phrase(targets, index, rng=None):
  rng = rng or random.Random()
  targets = [t for t in targets if t]
  if not targets:
    return ''

  dmg = _target_weights(targets)
  words_only = [t for t in targets if t[0] == 'word']
  tris = [t for t in targets if t[0] == 'trigram']
  chars = [t for t in targets if t[0] == 'char']

  if len(tris) == 0 and words_only:
    return _pick_weak_word_fallback(words_only, chars, dmg, rng)

  for _, tri, _ in sorted(tris, key=lambda t: t[2], reverse=True):
    if not _cross_word(tri):
      w, _ = index.best_in_word(tri, rng)
      if w:
        w1, _ = _apply_targets_to_tokens(w, None, targets)
        return w1

  for _, tri, tw in sorted(tris, key=lambda t: t[2], reverse=True):
    if _cross_word(tri):
      pair = index.best_cross_pair(tri, rng)
      if pair:
        w1, w2 = _apply_targets_to_tokens(pair[0], pair[1], targets)
        return f'{w1} {w2}'

  if chars:
    return index.word_for_char(chars[0][1], rng)

  return _pick_weak_word_fallback(words_only, chars, dmg, rng)


def _make_index(targets, dict_words):
  return LessonIndex(_weak_word_list(targets), dict_words, _weak_damage_map(targets))


def generate_lesson_lines(targets, dict_words, n_lines=5, rng=None):
  rng = rng or random.Random()
  index = _make_index(targets, dict_words)
  lines = []
  pool = list(targets)
  if not pool:
    return lines
  for _ in range(n_lines):
    rng.shuffle(pool)
    batch = pool[: min(4, len(pool))]
    line = compose_phrase(batch, index, rng)
    if line and line not in lines:
      lines.append(line)
  return lines


def _batch_for_uncovered(pool, covered, rng, n=6):
  """Prefer high-weight targets not yet covered in this lesson."""
  uncovered = [t for t in pool if t[1] not in covered]
  if not uncovered:
    uncovered = list(pool)
  uncovered.sort(key=lambda t: t[2], reverse=True)
  top = uncovered[:n]
  rng.shuffle(top)
  return top


def build_lesson(targets, dict_words, min_chars=220, max_chars=600, rng=None):
  """Assemble lesson from weak targets only; dict used for pair lookup, not filler."""
  rng = rng or random.Random()
  if not targets:
    return ''
  index = _make_index(targets, dict_words)
  phrases = []
  covered = set()
  text = ''
  pool = list(targets)
  attempts = 0
  max_attempts = max(len(pool) * 6, 12)

  while len(text) < min_chars and attempts < max_attempts:
    attempts += 1
    batch = _batch_for_uncovered(pool, covered, rng)
    phrase = compose_phrase(batch, index, rng)
    if not phrase:
      continue
    for t in batch:
      covered.add(t[1])
    phrases.append(phrase)
    text = ' '.join(phrases)
    if len(text) >= max_chars:
      break

  if not text:
    batch = sorted(pool, key=lambda t: t[2], reverse=True)[:6]
    text = compose_phrase(batch, index, rng)

  return text[:max_chars] if len(text) > max_chars else text


def fetch_weak_targets(conn, hist=None, min_count=1, per_type=15):
  if hist is None:
    hist = time.time() - 30 * 86400.0
  targets = []
  for tp, tag in TYPE_TAGS.items():
    rows = conn.execute(WEAK_SQL, (hist, tp, min_count, per_type)).fetchall()
    for data, damage in rows:
      targets.append((tag, data, float(damage or 1.0)))
  targets.sort(key=lambda t: t[2], reverse=True)
  return targets


def fetch_db_marker(conn):
  return conn.execute("select coalesce(max(w),0), count(*) from statistic").fetchone()


def lesson_cache_valid(cached, db_marker):
  return cached is not None and bool(cached[0]) and cached[1] == db_marker


def build_lesson_from_db(conn, hist=None, min_count=1, per_type=15,
                         min_chars=220, max_chars=600, wordlist_path=None, rng=None):
  targets = fetch_weak_targets(conn, hist, min_count, per_type)
  dict_words = load_wordlist(wordlist_path) if wordlist_path else []
  return build_lesson(targets, dict_words, min_chars, max_chars, rng)
