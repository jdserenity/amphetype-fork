import logging as log
import re
from collections import defaultdict

from typing_program import timer
from typing_program.Data import Statistic

def median(lst):
  lst, n = sorted(lst), len(lst)
  if not n:
    return None
  res = lst[n//2]
  if n % 2 == 0:
    res = (lst[n // 2 - 1] + lst[n // 2]) / 2.0
  return res


class datatuple(tuple):
  def __getattr__(self, key):
    return tuple(getattr(x, key) for x in self)

  def __getitem__(self, idx):
    if isinstance(idx, tuple):
      return type(self)(x for (x,cond) in zip(self, idx))
    if isinstance(idx, list):
      return type(self)(self[i] for i in idx)
    res = super().__getitem__(idx)
    if isinstance(idx, slice):
      return type(self)(res)
    return res

  def split(self, pred):
    if not callable(pred):
      pred = lambda x, y=pred: x == y

    cur = []
    for x in self:
      if pred(x):
        yield type(self)(cur)
        cur = []
      else:
        cur.append(x)
    yield type(self)(cur)


class CharEntry():
  __slots__ = ('char', 'inserts', 'timing',
               'mistakes', 'first', 'first_any',
               'last', 'errors')
  
  def __init__(self, char):
    self.char = char
    self.inserts = 0
    self.first = None
    self.first_any = None
    self.last = None
    self.timing = None
    self.mistakes = 0
    self.errors = ''

  def visited(self):
    return self.first is not None

  def visit(self, correct, last_time, now):
    if self.first_any is None:
      self.first_any = now
      
    if correct:
      self.last = now
      if self.first is None:
        self.first = now
      if self.timing is None and last_time is not None:
        self.timing = self.first - last_time
    else:
      self.mistakes += 1

  def __repr__(self):
    return f'["{self.char}"+{self.inserts} {self.timing or -1:.2f}s m:{self.mistakes}]'


# Keystroke gaps longer than this are considered idle time (distraction, afk)
# and are capped when computing WPM so they don't unfairly tank your speed.
IDLE_THRESHOLD = 3.0  # seconds


class RunStats(datatuple):
  @staticmethod
  def make(text, started=None):
    assert len(text) > 0
    obj = RunStats(CharEntry(c) for c in text)
    obj.started = started
    obj._pause_total = 0.0
    obj._paused_at = None
    return obj
    
  def __new__(cls, cs):
    self = datatuple.__new__(cls, cs)
    idx = 0
    while idx < len(self) and self[idx].last is not None:
      idx += 1
    self.index = idx
    self.started = None
    self._pause_total = 0.0
    self._paused_at = None
    return self

  def __repr__(self):
    return '\n'.join([
      ' '.join([f"{c.char:^5s}" for c in self]),
      ' '.join([f"{c.timing or -1:5.2f}" for c in self]),
    ])

  def is_complete(self):
    return self.index >= len(self) and self.previous and self.previous.last is not None

  def has_started(self):
    return self.started is not None

  def is_paused(self):
    return self._paused_at is not None

  def _tnow(self):
    t = timer()
    if self._paused_at is not None:
      t = self._paused_at
    return t - self._pause_total

  def pause(self):
    if self._paused_at is None:
      self._paused_at = timer()

  def resume(self):
    if self._paused_at is not None:
      self._pause_total += timer() - self._paused_at
      self._paused_at = None

  @property
  def current(self):
    if self.index >= len(self):
      return None
    return self[self.index]

  @property
  def previous(self):
    if self.index == 0:
      return None
    return self[self.index-1]

  @property
  def next(self):
    if self.index >= len(self) - 1:
      return None
    return self[self.index+1]

  @property
  def ending(self):
    return self.index >= len(self) - 1

  @property
  def start_end(self):
    if not len(self):
      return (None, None)
    return self.started, self[-1].last

  @property
  def text(self):
    return ''.join(self.char)

  @property
  def duration(self):
    if self.started is None or not self.is_complete():
      return None
    return self.previous.last - self.started

  def active_duration(self, idle_threshold=None):
    """Sum of inter-keystroke gaps with idle gaps capped at idle_threshold.

    ESC-pause time is already excluded from individual timings (they use
    _tnow()). This additionally caps any single gap that exceeds the threshold,
    so zoning out mid-lesson without pressing ESC does not tank your WPM.
    Falls back to None when no timing data is available.
    """
    threshold = IDLE_THRESHOLD if idle_threshold is None else idle_threshold
    timings = [t for t in self.timing if t is not None]
    if not timings:
      return self.duration
    return sum(min(t, threshold) for t in timings)

  @property
  def per_sec(self):
    if self.duration is None:
      return None
    return len(self) / self.duration

  def __getitem__(self, idx):
    res = super().__getitem__(idx)
    if isinstance(idx, slice):
      s,e,d = idx.indices(len(self))
      assert d > 0
      if s-d == -1:
        res.started = self.started
      elif 0 <= s-d < len(self):
        res.started = self[s-d].last
    return res
        
  def last_was_error(self):
    if self.current and self.current.inserts > 0:
      return True
    if self.previous and self.previous.last is None:
      return True
    return False

  def pop_char(self):
    if self.current is None or self.current.inserts == 0:
      self.index -= 1
      return self.current.char
    if self.current.inserts > 0:
      self.current.inserts -= 1
    return None

  def visit(self, correct):
    if self.is_paused():
      return
    now = self._tnow()
    if self.previous:
      self.current.visit(correct, self.previous.last, now)
    else:
      self.current.visit(correct, self.started, now)

  def advance(self, real=True):
    if not real:
      self.current.inserts += 1
      return
    
    self.index += 1

    # Interpolate a reasonable start time if one wasn't set.
    if self.started is None and self.is_complete():
      self.fix_start()

  def fix_start(self):
    if self.started is not None or not self.is_complete():
      return

    i = 0
    while i < len(self) and self[i].last is None:
      i += 1

    med = self.median_timing
    if i == len(self) or med is None:
      log.error(f"cannot fixup broken run, all times are invalid:\n{self}")
      return

    self.started = self[i].last - (i+1) * med

  @property
  def median_timing(self):
    return median([t for t in self.timing if t])

  @property
  def faults(self):
    return sum(1 for c in self if c.mistakes > 0)

  @property
  def visc(self):
    # Bad, do something else?
    # mean = sum(xs)/len(xs)
    # return sum([(x/mean - 1.0)**2 for x in xs])

    # Experimental new viscosity.
    xs = [t for t in self.timing if t]
    if len(xs) < 3:
      return None
    return self.median_err(median(xs))

  def median_err(self, m):
    return sum([(max(0, x.timing - m))**2 for x in self if x.timing])

  def result(self, accuracy=False):
    # print(f'"{self.text}" {self.started=}, {self.duration=}, {self.previous=}, {self.per_sec=}')
    acc = 1.0 - self.faults / len(self) if accuracy else self.faults != 0
    return self.per_sec * 12.0, self.visc, acc

  @property
  def stats(self):
    return None if self.per_sec is None else 1.0 / self.per_sec, self.visc, self.faults != 0

  def timed_ngrams(self, n, complete=True):
    for i in range(n, len(self)):
      gram = self[i-n:i]
      if not complete or gram.is_complete():
        yield gram

  def timed_words(self, complete=True):
    for m in re.finditer(r"\w+(?:['-]\w+)*", self.text):
      word = self[m.start():m.end()]
      if not complete or word.is_complete():
        yield word


def collect_run_stat_rows(run, med_char, when, source_id):
  """Build statistic insert rows; char/trigram/word buckets kept separate (3-letter words are words)."""
  char_s, char_v = defaultdict(Statistic), defaultdict(Statistic)
  tri_s, tri_v = defaultdict(Statistic), defaultdict(Statistic)
  word_s, word_v = defaultdict(Statistic), defaultdict(Statistic)

  for i in range(len(run)):
    sub = run[i:i + 1]
    spc, _, flaw = sub.stats
    if spc is None:
      continue
    char_s[sub.text].append(spc, flaw)
    char_v[sub.text].append(sub.median_err(med_char))

  for sub in run.timed_ngrams(3):
    spc, vc, flaw = sub.stats
    if spc is None:
      continue
    tri_s[sub.text].append(spc, flaw)
    if vc is not None:
      tri_v[sub.text].append(vc)

  for sub in run.timed_words():
    spc, vc, flaw = sub.stats
    if spc is None:
      continue
    word_s[sub.text].append(spc, flaw)
    if vc is not None:
      word_v[sub.text].append(vc)

  rows = []
  for tp, st, vs in ((0, char_s, char_v), (1, tri_s, tri_v), (2, word_s, word_v)):
    for k, s in st.items():
      v = vs[k].median()
      if v is not None:
        v *= 100.0
      rows.append((s.median(), v, when, len(s), s.flawed(), tp, k, source_id))
  return rows

# Speedbumps:

# vv--- fast
# ABC
# ^^^-- slow

# Awkward:

# +---- fast
# |+--- fast
# ||+-- fast
# vvv
# ABC
# ∧∧∧--- slow

