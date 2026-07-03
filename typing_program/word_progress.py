"""Per-word progress vs historical baseline WPM."""

import re
from collections import defaultdict

from typing_program.speed_heatmap import PROGRESS_GREEN, PROGRESS_ORANGE, PROGRESS_RED, fetch_speed_stats
from typing_program.stats_query import STAT_TYPE_WORD

_WORD_RE = re.compile(r"\w+(?:['-]\w+)*")


def lesson_words(text):
  return [m.group(0) for m in _WORD_RE.finditer(text or '')]


def word_spans(text):
  return [(m.start(), m.end(), m.group(0)) for m in _WORD_RE.finditer(text or '')]


def fetch_word_stat_times(db, words):
  """Per-word spc samples in statistic (same pool as agg_median(time))."""
  if not words:
    return {}
  qs = ','.join('?' * len(words))
  rows = db.execute(
    'select data, time from statistic where type=? and data in (%s)' % qs,
    (STAT_TYPE_WORD, *words)).fetchall()
  out = defaultdict(list)
  for data, t in rows:
    if t is not None and t > 0:
      out[data].append(t)
  return dict(out)


def fetch_word_baselines(db, words):
  """All-time word WPM plus raw timing samples for median-shift deltas."""
  if not words:
    return {}
  stats = fetch_speed_stats(db, hist_cutoff=0, stat_type=STAT_TYPE_WORD)
  times = fetch_word_stat_times(db, words)
  return {
    w: {'wpm': stats[w]['wpm'], 'times': times.get(w, [])}
    for w in words if w in stats
  }


def baseline_wpm(entry):
  if isinstance(entry, dict):
    return entry['wpm']
  return entry


def baseline_times(entry):
  if isinstance(entry, dict):
    ts = entry.get('times') or []
    if ts:
      return list(ts)
    wpm = entry.get('wpm')
    if wpm:
      return [12.0 / wpm]
  elif entry:
    return [12.0 / entry]
  return []


def word_spc_from_slice(sub):
  if not sub.is_complete():
    return None
  st = sub.stats
  if st is None or st[0] is None or st[0] <= 0:
    return None
  return st[0]


def word_wpm_from_slice(sub):
  """WPM for a completed word; same whole-word spc as collect_run_stat_rows word bucket."""
  spc = word_spc_from_slice(sub)
  return None if spc is None else 12.0 / spc


def wpm_from_spc_samples(spcs):
  from typing_program.timingtuple import median
  if not spcs:
    return None
  m = median(list(spcs))
  if m is None or m <= 0:
    return None
  return 12.0 / m


def avg_wpm_bump(old_times, new_spc):
  """Whole WPM gain if this run's sample were merged into the historical median pool."""
  if not old_times or new_spc is None or new_spc <= 0:
    return None
  old_wpm = wpm_from_spc_samples(old_times)
  new_wpm = wpm_from_spc_samples(old_times + [new_spc])
  if old_wpm is None or new_wpm is None:
    return None
  return int(new_wpm) - int(old_wpm)


def median_wpm_bump(sub, base_entry):
  spc = word_spc_from_slice(sub)
  if spc is None:
    return None
  return avg_wpm_bump(baseline_times(base_entry), spc)


class RunProgress:
  __slots__ = ('improved', 'known', 'new_words', 'gain_total', 'gain_count')

  def __init__(self, improved=0, known=0, new_words=None, gain_total=0, gain_count=0):
    self.improved = improved
    self.known = known
    self.new_words = list(new_words or [])
    self.gain_total = gain_total
    self.gain_count = gain_count

  @property
  def new_count(self):
    return len(self.new_words)

  @property
  def avg_gain(self):
    if not self.gain_count:
      return 0
    return int(round(self.gain_total / self.gain_count))


def _word_run_gain(sub, base_entry):
  bump = median_wpm_bump(sub, base_entry)
  if bump is None or bump < 1:
    return None, None
  return word_wpm_from_slice(sub), bump


def lifetime_wpm_gain(current_wpm, first_wpm):
  """Current median WPM minus WPM from the first recorded sample."""
  if current_wpm is None or first_wpm is None:
    return None
  return int(current_wpm) - int(first_wpm)


def new_word_spans(run, baselines, match_text):
  """Each first-time word occurrence: (start, end)."""
  out = []
  for start, end, word in word_spans(match_text or ''):
    if word in baselines:
      continue
    sub = run[start:end]
    if not sub.is_complete() or any(sub[i].mistakes for i in range(len(sub))):
      continue
    out.append((start, end))
  return out


def improved_word_spans(run, baselines, match_text):
  """Each improved word occurrence: (start, end, run_wpm, median_bump)."""
  out = []
  for start, end, word in word_spans(match_text or ''):
    sub = run[start:end]
    if not sub.is_complete() or any(sub[i].mistakes for i in range(len(sub))):
      continue
    base = baselines.get(word)
    if base is None:
      continue
    _wpm, bump = _word_run_gain(sub, base)
    if bump is not None:
      out.append((start, end, _wpm, bump))
  return out


def analyze_run_progress(run, baselines, match_text=None):
  """Score a finished run against baselines captured before the run wrote stats."""
  improved = 0; known = 0; new_words = []; gain_total = 0; gain_count = 0
  seen_new = set()
  for start, end, word in word_spans(match_text or run.text):
    sub = run[start:end]
    if not sub.is_complete() or any(sub[i].mistakes for i in range(len(sub))):
      continue
    wpm = word_wpm_from_slice(sub)
    if wpm is None:
      continue
    base = baselines.get(word)
    if base is not None:
      known += 1
      _wpm, bump = _word_run_gain(sub, base)
      if bump is not None:
        improved += 1
        gain_total += bump; gain_count += 1
    elif word not in seen_new:
      seen_new.add(word)
      new_words.append(word)
  return RunProgress(improved, known, new_words, gain_total, gain_count)


def progress_badges_for_run(run, baselines, match_text):
  """(start, end, gain) spans for improved words; shown after the run completes."""
  return [(s, e, g) for s, e, _w, g in improved_word_spans(run, baselines, match_text)]


def format_progress_html(progress, stats_saved=True):
  imp_color = PROGRESS_GREEN if progress.improved > 0 else PROGRESS_RED
  lines = [
    'You improved on <span style="color:%s">%d</span> out of %d words at an average of <span style="color:%s">+%d</span>wpm!' % (
      imp_color, progress.improved, progress.known, imp_color, progress.avg_gain),
  ]
  if progress.new_count > 0:
    lines.append('You typed <span style="color:%s">%d</span> unique new word%s!' % (
      PROGRESS_ORANGE, progress.new_count, '' if progress.new_count == 1 else 's'))
  if not stats_saved:
    lines.append('<i>Drill only — stats were not saved.</i>')
  return '<br />'.join(lines)
