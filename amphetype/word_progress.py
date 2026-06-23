"""Per-word progress vs historical baseline WPM."""

import re

from amphetype.speed_heatmap import PROGRESS_GREEN, PROGRESS_RED, fetch_speed_stats
from amphetype.stats_query import STAT_TYPE_WORD

_WORD_RE = re.compile(r"\w+(?:['-]\w+)*")


def lesson_words(text):
  return [m.group(0) for m in _WORD_RE.finditer(text or '')]


def word_spans(text):
  return [(m.start(), m.end(), m.group(0)) for m in _WORD_RE.finditer(text or '')]


def fetch_word_baselines(db, words):
  """All-time word WPM for each word that exists in statistic (case-sensitive keys)."""
  if not words:
    return {}
  stats = fetch_speed_stats(db, hist_cutoff=0, stat_type=STAT_TYPE_WORD)
  return {w: stats[w]['wpm'] for w in words if w in stats}


def word_wpm_from_slice(sub):
  """WPM for a completed word slice; same median-spc pool as collect_run_stat_rows."""
  from amphetype.timingtuple import median
  if not sub.is_complete():
    return None
  spcs = []
  for i in range(len(sub)):
    st = sub[i:i + 1].stats
    if st is None:
      return None
    spcs.append(st[0])
  m = median(spcs)
  if m is None or m <= 0:
    return None
  return 12.0 / m


def is_improved(run_wpm, baseline_wpm):
  """At least 1 whole WPM faster; fractional-only gains do not count."""
  return int(run_wpm) >= int(baseline_wpm) + 1


class RunProgress:
  __slots__ = ('improved', 'known', 'new_words')

  def __init__(self, improved=0, known=0, new_words=None):
    self.improved = improved
    self.known = known
    self.new_words = list(new_words or [])

  @property
  def new_count(self):
    return len(self.new_words)


def analyze_run_progress(run, baselines):
  """Score a finished run against baselines captured before the run wrote stats."""
  improved = 0; known = 0; new_words = []
  seen_new = set()
  for sub in run.timed_words(complete=True):
    word = sub.text
    if any(sub[i].mistakes for i in range(len(sub))):
      continue
    wpm = word_wpm_from_slice(sub)
    if wpm is None:
      continue
    base = baselines.get(word)
    if base is not None:
      known += 1
      if is_improved(wpm, base):
        improved += 1
    elif word not in seen_new:
      seen_new.add(word)
      new_words.append(word)
  return RunProgress(improved, known, new_words)


def format_progress_html(progress, stats_saved=True):
  imp_color = PROGRESS_GREEN if progress.improved > 0 else PROGRESS_RED
  lines = [
    'You improved on <span style="color:%s">%d</span> out of %d words!' % (
      imp_color, progress.improved, progress.known),
  ]
  if progress.new_count > 0:
    lines.append('You typed %d unique new word%s!' % (
      progress.new_count, '' if progress.new_count == 1 else 's'))
  if not stats_saved:
    lines.append('<i>Drill only — stats were not saved.</i>')
  return '<br />'.join(lines)
