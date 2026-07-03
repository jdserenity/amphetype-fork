"""Compose dense, readable practice lines from weak characters, trigrams, and words.

Ground truth: a trigram (or character, or word) is "practiced" iff its exact
surface form appears in the rendered lesson text. A trigram is just any 3-char
window of real typing, including spaces and punctuation, so we satisfy it by
constructing word/biword tokens whose joined text literally contains it.
"""

import random
import re
from collections import defaultdict

from typing_program.stats_query import ALL_TIME_HIST, RAW_TARGETS_SQL

# A target is (kind, data, weight); kind in {'char','trigram','word'}.
TYPE_TAGS = {0: 'char', 1: 'trigram', 2: 'word'}
ANA_WHAT_KINDS = ('char', 'trigram', 'word')

def ana_what_kind(cat_index):
  return ANA_WHAT_KINDS[cat_index]

_dict_cache = {}
_TRAIL_PUNCT = '.,!?;:'   # punctuation that naturally trails a word
_OPEN_PUNCT = '"(\''       # punctuation that naturally leads a word
CAND_CAP = 150             # cap dictionary candidates considered per slot

# Raw aggregates per item; scoring done in Python (sqlite lacks log()).
RAW_SQL = RAW_TARGETS_SQL


def is_practice_word(w):
  if not w or len(w) < 2:
    return False
  return w.isalpha()


def _alpha_runs(text):
  return re.findall(r"[A-Za-z]+", text)


def target_key(t):
  return (t[0], t[1])


def _focus_word_in_text(word, text):
  return bool(re.search(r'(?<![A-Za-z])' + re.escape(word) + r'(?![A-Za-z])', text))


def covered_targets(text, targets):
  """Return the set of target keys whose surface form literally appears in text."""
  res = set()
  if not text:
    return res
  runs = {r.lower() for r in _alpha_runs(text)}
  for t in targets:
    kind, data = t[0], t[1]
    if kind == 'word':
      if data.lower() in runs: res.add((kind, data))
    elif kind == 'char':
      if data in text: res.add((kind, data))
    elif kind == 'trigram':
      if data in text: res.add((kind, data))
  return res


def focus_covered_targets(text, targets):
  """Focus drills: word targets match exact surface (Lady ≠ lady)."""
  res = set()
  if not text:
    return res
  for t in targets:
    kind, data = t[0], t[1]
    if kind == 'word':
      if _focus_word_in_text(data, text): res.add((kind, data))
    elif kind == 'char':
      if data in text: res.add((kind, data))
    elif kind == 'trigram':
      if data in text: res.add((kind, data))
  return res


def _cap_first(w):
  return w[0].upper() + w[1:] if w else w


def _capitalize_for_char(word, ch):
  if not word:
    return word
  if ch.isupper():
    return _cap_first(word)
  return word


def _pick_by_damage(candidates, dmg):
  if not candidates:
    return None
  return max(candidates, key=lambda w: (dmg.get(w.lower(), 0.0), w))


def score_target(time, count, misses):
  """Importance ("damage") score for selection.

  This is the total cost an item imposes on the user: it scales with how slow it
  is (quadratic in seconds-per-char), how *often* it is typed (linear in count),
  and how error-prone it is. So a merely-slow item typed once is unimportant,
  while a moderately-slow item typed constantly dominates — that is the point.
  """
  if time is None or count is None or count <= 0:
    return 0.0
  return (time * time) * (count + (misses or 0))


# ---------------------------------------------------------------------------
# Dictionary / weak-word index
# ---------------------------------------------------------------------------

class LessonIndex:
  """Weak DB words first, bundled dictionary for completing trigram boundaries."""

  def __init__(self, weak_words, dict_words, weak_damage=None):
    self.weak_damage = weak_damage or {}
    self.weak = []
    seen = set()
    for w in weak_words:
      wl = w.lower()
      if wl not in seen and wl.isalpha() and len(wl) >= 1:
        seen.add(wl); self.weak.append(wl)
    self.dict = sorted({w.lower() for w in dict_words if is_practice_word(w)} - seen)
    self.weak_set = set(self.weak)
    self._all = self.weak + self.dict
    self._ends = defaultdict(list)
    self._starts = defaultdict(list)
    for w in self._all:
      self._ends[w[-1]].append(w)
      self._starts[w[0]].append(w)
    self._contains_cache = {}
    self._prefix_cache = {}
    self._suffix_cache = {}

  @property
  def words(self):
    return self._all

  def all_words(self):
    return self._all

  def words_ending(self, ch):
    return self._ends.get(ch, [])

  def words_starting(self, ch):
    return self._starts.get(ch, [])

  def words_with_prefix(self, p):
    p = p.lower()
    if p not in self._prefix_cache:
      weak = [w for w in self.weak if w.startswith(p)]
      dct = [w for w in self.dict if w.startswith(p)]
      self._prefix_cache[p] = weak + dct[:CAND_CAP]
    return self._prefix_cache[p]

  def words_with_suffix(self, s):
    s = s.lower()
    if s not in self._suffix_cache:
      weak = [w for w in self.weak if w.endswith(s)]
      dct = [w for w in self.dict if w.endswith(s)]
      self._suffix_cache[s] = weak + dct[:CAND_CAP]
    return self._suffix_cache[s]

  def words_containing(self, sub):
    sub = sub.lower()
    if sub in self._contains_cache:
      return self._contains_cache[sub]
    weak = [w for w in self.weak if sub in w]
    dct = [w for w in self.dict if sub in w]
    out = weak + dct[:CAND_CAP]
    self._contains_cache[sub] = out
    return out

  def word_for_char(self, ch, rng, remaining=None, targets=None):
    """A real word rendered so it contains ch (exact case)."""
    low = ch.lower()
    if ch.isupper():
      cands = self.words_starting(low)
      if cands:
        return _cap_first(_best_word(cands[:CAND_CAP], _cap_first, self, remaining, targets, rng))
      return ''
    cands = [w for w in self._all if low in w]
    if not cands:
      return ''
    weak = [w for w in cands if w in self.weak_set]
    pool = (weak + cands[:CAND_CAP]) if weak else cands[:CAND_CAP]
    return _decorate(_best_word(pool, lambda x: x, self, remaining, targets, rng), remaining, targets)


DictIndex = LessonIndex   # back-compat alias
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


# ---------------------------------------------------------------------------
# Token rendering / candidate scoring
# ---------------------------------------------------------------------------

def _decorate(word, remaining, targets):
  """Capitalize first letter if that covers an uncovered uppercase char target."""
  if not word or not targets:
    return word
  rem = remaining if remaining is not None else _keys(targets)
  for t in targets:
    if t[0] == 'char' and t[1].isupper() and (t[0], t[1]) in rem:
      if word[0].lower() == t[1].lower():
        return _cap_first(word)
  return word


def _keys(targets):
  return {(t[0], t[1]) for t in targets}


def _best_word(cands, render, index, remaining, targets, rng):
  """Pick the candidate whose rendered form covers the most uncovered targets,
  preferring weak words and higher damage. Ties broken by rng for variety."""
  if not cands:
    return None
  rng = rng or random.Random()
  rem_targets = []
  if targets is not None:
    rem = remaining if remaining is not None else _keys(targets)
    rem_targets = [t for t in targets if (t[0], t[1]) in rem]
  best = None; best_key = None
  for w in cands:
    extra = len(covered_targets(render(w), rem_targets)) if rem_targets else 0
    key = (extra, 1 if w in index.weak_set else 0, index.weak_damage.get(w, 0.0), rng.random())
    if best_key is None or key > best_key:
      best_key = key; best = w
  return best


def _split_segments(tri):
  """Classify a no-space trigram into (leading_alpha, mid, trailing) pieces."""
  la = 0
  while la < 3 and tri[la].isalpha(): la += 1   # leading alpha length
  ta = 3
  while ta > 0 and tri[ta-1].isalpha(): ta -= 1  # index where trailing alpha begins
  return la, ta


def _left_token(ch, index, remaining, targets, rng):
  """Render a token whose last visible char is ch."""
  if ch == '"':
    cands = index.all_words()
    w = _best_word(cands[:CAND_CAP] if not index.weak else index.weak + index.dict[:CAND_CAP],
                   lambda x: '"' + _cap_first(x) + '"', index, remaining, targets, rng)
    return '"' + _cap_first(w) + '"' if w else ''
  if ch in _TRAIL_PUNCT or ch == ')':
    cands = index.weak + index.dict[:CAND_CAP]
    w = _best_word(cands, lambda x: _decorate(x, remaining, targets) + ch, index, remaining, targets, rng)
    return _decorate(w, remaining, targets) + ch if w else ''
  if ch == "'":
    cands = index.weak + index.dict[:CAND_CAP]
    w = _best_word(cands, lambda x: _decorate(x, remaining, targets) + "'", index, remaining, targets, rng)
    return _decorate(w, remaining, targets) + "'" if w else ''
  if ch.isalpha():
    cands = index.words_ending(ch.lower())
    if not cands:
      return ''
    cands = cands[:CAND_CAP] if len(cands) > CAND_CAP else cands
    w = _best_word(cands, lambda x: _decorate(x, remaining, targets), index, remaining, targets, rng)
    return _decorate(w, remaining, targets) if w else ''
  return ''


def _right_token(ch, index, remaining, targets, rng):
  """Render a token whose first visible char is ch."""
  if ch in _OPEN_PUNCT:
    cands = index.weak + index.dict[:CAND_CAP]
    w = _best_word(cands, lambda x: ch + _decorate(x, remaining, targets), index, remaining, targets, rng)
    return ch + _decorate(w, remaining, targets) if w else ''
  if ch.isalpha():
    cands = index.words_starting(ch.lower())
    if not cands:
      return ''
    cands = cands[:CAND_CAP] if len(cands) > CAND_CAP else cands
    if ch.isupper():
      w = _best_word(cands, _cap_first, index, remaining, targets, rng)
      return _cap_first(w) if w else ''
    w = _best_word(cands, lambda x: _decorate(x, remaining, targets), index, remaining, targets, rng)
    return _decorate(w, remaining, targets) if w else ''
  if ch in _TRAIL_PUNCT:   # rare: token starting with sentence punctuation
    cands = index.weak + index.dict[:CAND_CAP]
    w = _best_word(cands, lambda x: ch + _decorate(x, remaining, targets), index, remaining, targets, rng)
    return ch + _decorate(w, remaining, targets) if w else ''
  return ''


def _neighbor_token(index, remaining, targets, rng):
  """A productive neighbor: prefer an uncovered weak word, else any weak/dict word.

  Used only to realize a required space for edge-space trigrams; we still pick
  something that covers an outstanding target when possible (never pure filler)."""
  rem = remaining if remaining is not None else _keys(targets or [])
  uncovered = [t[1].lower() for t in (targets or [])
               if t[0] == 'word' and (t[0], t[1]) in rem and t[1].lower() in index.weak_set]
  if uncovered:
    return _decorate(_pick_by_damage(uncovered, index.weak_damage), remaining, targets)
  if index.weak:
    return _decorate(_pick_by_damage(index.weak, index.weak_damage), remaining, targets)
  if index.dict:
    return rng.choice(index.dict[:CAND_CAP])
  return ''


def _nospace_token(tri, index, remaining, targets, rng):
  """Render a single token containing a 3-char trigram that has no spaces."""
  if tri.isalpha():
    if tri[0].isupper() and tri[1:].islower():
      cands = index.words_with_prefix(tri.lower())
      cands = (cands[:CAND_CAP]) if len(cands) > CAND_CAP else cands
      w = _best_word(cands, _cap_first, index, remaining, targets, rng)
      return _cap_first(w) if w else ''
    if tri.islower():
      cands = index.words_containing(tri)
      w = _best_word(cands, lambda x: x, index, remaining, targets, rng)
      return _decorate(w, remaining, targets) if w else ''
    # mixed case mid-word: place lower match then restore uppercase positions
    cands = index.words_containing(tri.lower())
    w = _best_word(cands, lambda x: _casematch(x, tri), index, remaining, targets, rng)
    return _casematch(w, tri) if w else ''

  la, ta = _split_segments(tri)
  # letters then trailing punctuation: 'ol,', 'o,"', 'ed.'
  if 1 <= la < 3 and all(not c.isalpha() for c in tri[la:]):
    suffix = tri[:la]; tail = tri[la:]
    cands = index.words_with_suffix(suffix)
    cands = cands[:CAND_CAP] if len(cands) > CAND_CAP else cands
    w = _best_word(cands, lambda x: _decorate(x, remaining, targets) + tail, index, remaining, targets, rng)
    if w:
      return _decorate(w, remaining, targets) + tail
  # leading punctuation then letters: '-fe', '"fe', '(ab'
  if ta < 3 and tri[0] in (_OPEN_PUNCT + '-'):
    lead = tri[0]; rest = tri[1:]
    if lead == '-':
      cands = index.words_with_prefix(rest)
      cands = cands[:CAND_CAP] if len(cands) > CAND_CAP else cands
      right = _best_word(cands, lambda x: x, index, remaining, targets, rng)
      left = _neighbor_token(index, remaining, targets, rng)
      if right and left:
        token = f'{left}-{_decorate(right, remaining, targets)}'
        if tri in token:
          return token
    else:
      cands = index.words_with_prefix(rest)
      cands = cands[:CAND_CAP] if len(cands) > CAND_CAP else cands
      w = _best_word(cands, lambda x: lead + x, index, remaining, targets, rng)
      if w:
        return lead + _decorate(w, remaining, targets)
  # letter, internal punct, letter: 'e-m', "o'c", 'a.b'
  if tri[0].isalpha() and not tri[1].isalpha() and tri[2].isalpha():
    mid = tri[1]
    lefts = index.words_ending(tri[0].lower())
    rights = index.words_starting(tri[2].lower())
    if lefts and rights:
      lw = _best_word(lefts[:CAND_CAP], lambda x: x, index, remaining, targets, rng)
      rw = _best_word(rights[:CAND_CAP], lambda x: x, index, remaining, targets, rng)
      token = f'{_decorate(lw, remaining, targets)}{mid}{rw}'
      if tri in token:
        return token
  return ''


def _casematch(w, tri):
  if not w:
    return ''
  idx = w.find(tri.lower())
  if idx < 0:
    return ''
  lst = list(w)
  for k, ch in enumerate(tri):
    if ch.isupper():
      lst[idx + k] = ch
  return ''.join(lst)


def _suffix_casematch(word, suf):
  """Render word (which ends with suf.lower()) with suf's uppercase positions applied."""
  if not word or not word.endswith(suf.lower()):
    return word
  start = len(word) - len(suf)
  lst = list(word)
  for k, ch in enumerate(suf):
    if ch.isupper():
      lst[start + k] = ch
  return ''.join(lst)


def trigram_tokens(tri, index, remaining, targets, rng):
  """Return a list of token strings whose join contains tri, or [] if impossible."""
  if len(tri) != 3:
    return []
  sp = tuple(i for i, c in enumerate(tri) if c == ' ')
  c0, c1, c2 = tri[0], tri[1], tri[2]

  if sp == ():
    t = _nospace_token(tri, index, remaining, targets, rng)
    return [t] if t else []

  if sp == (1,):   # cross-word: left ends c0, right starts c2
    left = _left_token(c0, index, remaining, targets, rng)
    right = _right_token(c2, index, remaining, targets, rng)
    return [left, right] if left and right else []

  if sp == (0,):   # ' XY': token starting with c1c2, preceded by a space
    tok = _right_token(c1, index, remaining, targets, rng) if not c2.isalpha() else None
    if c1.isalpha():
      cands = index.words_with_prefix((c1 + c2).lower())
      cands = cands[:CAND_CAP] if len(cands) > CAND_CAP else cands
      render = _cap_first if c1.isupper() else (lambda x: _decorate(x, remaining, targets))
      w = _best_word(cands, render, index, remaining, targets, rng)
      tok = render(w) if w else ''
    elif c1 in _OPEN_PUNCT:
      inner = _right_token(c2, index, remaining, targets, rng)
      tok = (c1 + inner) if inner else ''
    if not tok:
      return []
    left = _neighbor_token(index, remaining, targets, rng)
    return [left, tok] if left else [tok]

  if sp == (2,):   # 'XY ': token ending with c0c1, followed by a space
    tok = ''
    if c0.isalpha() and c1.isalpha():
      suf = c0 + c1
      cands = index.words_with_suffix(suf.lower())
      if any(c.isupper() for c in suf):
        # uppercase only reads naturally at a word start, so prefer the exact short word
        exact = [w for w in cands if len(w) == len(suf)]
        cands = exact or cands
      cands = cands[:CAND_CAP] if len(cands) > CAND_CAP else cands
      render = (lambda x: _suffix_casematch(x, suf))
      w = _best_word(cands, render, index, remaining, targets, rng)
      tok = render(w) if w else ''
    elif c0.isalpha() and not c1.isalpha():   # word ending c0, then trailing punct c1
      base = _left_token(c0, index, remaining, targets, rng)
      tok = (base + c1) if base else ''
    elif not c0.isalpha() and not c1.isalpha():   # word + both punct, e.g. ',"'
      anyw = _neighbor_token(index, remaining, targets, rng)
      tok = (anyw + c0 + c1) if anyw else ''
    if not tok:
      return []
    right = _neighbor_token(index, remaining, targets, rng)
    return [tok, right] if right else [tok]

  if sp == (0, 2):   # ' X ': single-char token
    if c1.lower() in ('a', 'i'):
      mid = c1 if c1.isupper() else c1
      left = _neighbor_token(index, remaining, targets, rng)
      right = _neighbor_token(index, remaining, targets, rng)
      toks = [t for t in [left, mid, right] if t]
      return toks if len(toks) >= 3 else []
    return []

  return []


def phrase_for_trigram(tri, index, rng=None):
  """Convenience: a single rendered phrase string that contains tri."""
  rng = rng or random.Random()
  toks = trigram_tokens(tri, index, None, [("trigram", tri, 1.0)], rng)
  return ' '.join(t for t in toks if t).strip()


def word_pairs_for_trigram(trigram, words):
  """Test helper: simple word pairs whose boundary forms a cross-word trigram."""
  out = []
  if len(trigram) == 3 and trigram[1] == ' ':
    a, _, b = trigram
    for w1 in words:
      if not w1.endswith(a):
        continue
      for w2 in words:
        if w2.startswith(b):
          out.append((w1, w2))
  else:
    for w in words:
      if trigram in w:
        out.append((w,))
  return out


# ---------------------------------------------------------------------------
# Phrase / lesson assembly
# ---------------------------------------------------------------------------

def _word_token(data, remaining, targets):
  """Render a weak word, capitalized only if needed for an uncovered upper char."""
  base = data if any(c.isupper() for c in data) else data.lower()
  return _decorate(base, remaining, targets)


def _make_index(targets, dict_words):
  weak = [t[1] for t in targets if t[0] == 'word']
  dmg = {t[1].lower(): t[2] for t in targets if t[0] == 'word'}
  return LessonIndex(weak, dict_words, dmg)


def compose_phrase(targets, index, rng=None):
  """Build one dense phrase covering as many of these targets as possible."""
  rng = rng or random.Random()
  targets = [t for t in targets if t]
  if not targets:
    return ''
  remaining = _keys(targets)
  tris = [t for t in targets if t[0] == 'trigram']
  words = [t for t in targets if t[0] == 'word']
  chars = [t for t in targets if t[0] == 'char']

  if tris:
    tri = max(tris, key=lambda t: t[2])[1]
    toks = trigram_tokens(tri, index, remaining, targets, rng)
    if toks:
      return ' '.join(t for t in toks if t).strip()

  if words:
    dmg = {t[1].lower(): t[2] for t in words}
    w = _pick_by_damage([t[1].lower() for t in words], dmg)
    return _decorate(w, remaining, targets)

  if chars:
    return index.word_for_char(chars[0][1], rng, remaining, targets)

  return ''


def _kind_rank(kind):
  return {'trigram': 0, 'word': 1, 'char': 2}.get(kind, 3)


def _tokens_for_target(t, index, remaining, targets, rng, exact_surface=False):
  """Render token(s) that practise a single target. `remaining` steers slot
  fillers toward still-uncovered targets; when empty they vary for freshness."""
  if t[0] == 'trigram':
    return [x for x in trigram_tokens(t[1], index, remaining, targets, rng) if x]
  if t[0] == 'word':
    if exact_surface:
      return [t[1]] if t[1] else []
    w = _word_token(t[1], remaining, targets)
    return [w] if w else []
  w = index.word_for_char(t[1], rng, remaining, targets)
  return [w] if w else []


def allocate_repeats(targets, budget, cap=6):
  """How many times each target should appear, ∝ importance (weight).

  Every target gets at least one (coverage). The rest of `budget` is shared by
  largest-remainder on weight, so important items recur more, capped so a single
  item can't swamp the lesson."""
  n = len(targets)
  if n == 0:
    return {}
  budget = max(budget, n)
  counts = {target_key(t): 1 for t in targets}
  remaining = budget - n
  total_w = sum(max(t[2], 0.0) for t in targets) or 1.0
  fracs = []
  for t in targets:
    share = remaining * max(t[2], 0.0) / total_w
    whole = int(share)
    counts[target_key(t)] += whole
    fracs.append((share - whole, target_key(t)))
  leftover = remaining - sum(int(remaining * max(t[2], 0.0) / total_w) for t in targets)
  fracs.sort(reverse=True)
  i = 0
  while leftover > 0 and fracs:
    counts[fracs[i % len(fracs)][1]] += 1
    leftover -= 1; i += 1
  return {k: min(cap, v) for k, v in counts.items()}


def _interleave(instances, rng):
  """Shuffle, then nudge apart adjacent instances of the same target."""
  rng.shuffle(instances)
  for i in range(1, len(instances)):
    if instances[i][1] == instances[i-1][1]:
      for j in range(i+1, len(instances)):
        if instances[j][1] != instances[i-1][1]:
          instances[i], instances[j] = instances[j], instances[i]
          break
  return instances


def build_lesson(targets, dict_words, min_chars=220, max_chars=600, rng=None, recent=None, repeat_cap=6):
  """Assemble a lesson from weak targets only — no random filler.

  Importance drives everything: targets are repeated proportionally to weight so
  high-impact error spaces get real practice, never just one token. Freshness
  comes from a fresh RNG per build (varied word realizations and ordering),
  weighted repetition, and `recent` (keys to de-emphasize so consecutive lessons
  rotate emphasis rather than feeling identical).
  """
  rng = rng or random.Random()
  if not targets:
    return ''
  if recent:
    targets = [(k, d, (w * 0.5 if (k, d) in recent else w)) for (k, d, w) in targets]
  index = _make_index(targets, dict_words)
  all_keys = _keys(targets)

  budget = max(len(targets), (min_chars // 8) + 1)
  counts = allocate_repeats(targets, budget, cap=repeat_cap)
  instances = []
  for t in targets:
    instances.extend([t] * counts[target_key(t)])
  _interleave(instances, rng)

  phrases = []
  text = ''
  covered = set()
  for t in instances:
    if text and len(text) >= max_chars:
      break
    remaining = all_keys - covered
    toks = _tokens_for_target(t, index, remaining, targets, rng)
    if not toks:
      continue
    phrase = ' '.join(toks)
    if not covered_targets(phrase, targets):
      continue   # never emit a phrase that practises nothing
    cand = (text + ' ' + phrase).strip() if text else phrase
    if text and len(cand) > max_chars:
      break
    phrases.append(phrase); text = cand
    covered = covered_targets(text, targets)

  # Guarantee at least one appearance of every composable target.
  for t in sorted(targets, key=lambda x: -x[2]):
    if target_key(t) in covered or (text and len(text) >= max_chars):
      continue
    toks = _tokens_for_target(t, index, all_keys - covered, targets, rng)
    if not toks:
      continue
    phrase = ' '.join(toks)
    cand = (text + ' ' + phrase).strip() if text else phrase
    if text and len(cand) > max_chars:
      break
    phrases.append(phrase); text = cand
    covered = covered_targets(text, targets)

  return text


# ---------------------------------------------------------------------------
# DB selection + caching
# ---------------------------------------------------------------------------

def build_focus_lesson(targets, dict_words=None, wordlist_path=None, min_chars=220, max_chars=600, rng=None):
  """Repeat only the given type targets (Performance Analysis drill). targets: [(kind, data), ...]."""
  if not targets:
    return ''
  if dict_words is None and wordlist_path:
    dict_words = load_wordlist(wordlist_path)
  weighted = [(k, d, 1.0) for k, d in targets]
  focus_chars = max(80, max_chars // 2)
  rng = rng or random.Random()
  index = _make_index(weighted, dict_words or [])
  all_keys = _keys(weighted)
  counts = {target_key(t): 0 for t in weighted}
  min_each = max(3, (focus_chars // 12) // len(weighted))
  text = ''
  covered = set()
  order = list(weighted)
  rng.shuffle(order)

  def _append_phrase(t, force=False):
    nonlocal text, covered
    toks = _tokens_for_target(t, index, all_keys - covered, weighted, rng, exact_surface=True)
    if not toks:
      return False
    phrase = ' '.join(toks)
    if not focus_covered_targets(phrase, weighted):
      return False
    cand = (text + ' ' + phrase).strip() if text else phrase
    if not force and text and len(cand) > focus_chars:
      return False
    text = cand
    covered = focus_covered_targets(text, weighted)
    counts[target_key(t)] += 1
    return True

  for t in weighted:
    if not _append_phrase(t):
      _append_phrase(t, force=True)
  idx = 0; fails = 0
  while len(text) < focus_chars and fails < len(weighted) * 4:
    t = order[idx % len(order)]
    idx += 1
    if all(c >= min_each for c in counts.values()) and len(text) >= focus_chars * 0.85:
      break
    if _append_phrase(t):
      fails = 0
    else:
      fails += 1
  return text


def fetch_weak_targets(conn, hist=ALL_TIME_HIST, min_count=1, per_type=15):
  """Pull weak chars/trigrams/words, scored by slowness (dominant) and frequency."""
  targets = []
  for tp, tag in TYPE_TAGS.items():
    rows = conn.execute(RAW_SQL, (hist, tp, min_count)).fetchall()
    scored = []
    for data, t, total, misses in rows:
      s = score_target(t, total, misses)
      if s > 0:
        scored.append((tag, data, s))
    scored.sort(key=lambda x: x[2], reverse=True)
    targets.extend(scored[:per_type])
  targets.sort(key=lambda t: t[2], reverse=True)
  return targets


def fetch_db_marker(conn):
  return conn.execute("select coalesce(max(w),0), count(*) from statistic").fetchone()


def lesson_cache_valid(cached, db_marker):
  return cached is not None and bool(cached[0]) and cached[1] == db_marker


def build_lesson_from_db(conn, hist=ALL_TIME_HIST, min_count=1, per_type=15,
                         min_chars=220, max_chars=600, wordlist_path=None, rng=None,
                         recent=None):
  targets = fetch_weak_targets(conn, hist, min_count, per_type)
  dict_words = load_wordlist(wordlist_path) if wordlist_path else []
  lesson = build_lesson(targets, dict_words, min_chars, max_chars, rng, recent=recent)
  # The keys most likely emphasized this lesson, for cross-lesson rotation.
  emphasized = [target_key(t) for t in targets[:max(3, len(targets) // 3)]]
  return lesson, emphasized
