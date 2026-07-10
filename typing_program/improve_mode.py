"""Improve mode submodes: mixed weakspot lessons and auto-picked focus drills."""

from typing_program.stats_query import (
  FOCUS_DRILL_PICK_COUNT, FOCUS_DRILL_POOL_SIZE, STAT_TYPE_WORD,
  fetch_accuracy_picks, fetch_damage_picks, fetch_hesitant_picks, fetch_oblivion_picks,
  fetch_oblivion_pool, fetch_slowest_picks,
)
from typing_program.speed_heatmap import OBLIVION_WPM

# Order is UI cycle order on the improve submode button.
IMPROVE_SUBMODE_LABELS = (
  'normal', 'trigrams', 'oblivion', 'slowest', 'hesitant', 'accuracy', 'damage')
IMPROVE_SUBMODE_NORMAL = 0
IMPROVE_SUBMODE_TRIGRAMS = 1
IMPROVE_SUBMODE_OBLIVION = 2
IMPROVE_SUBMODE_SLOWEST = 3
IMPROVE_SUBMODE_HESITANT = 4
IMPROVE_SUBMODE_ACCURACY = 5
IMPROVE_SUBMODE_DAMAGE = 6


def rows_to_targets(rows, kind):
  return [(kind, r[0], r[1]) for r in rows]


def oblivion_submode_available(db, hist_cutoff, min_count):
  """True when at least one analysis-eligible word is under the oblivion WPM line."""
  return len(fetch_oblivion_pool(db, hist_cutoff, STAT_TYPE_WORD, OBLIVION_WPM, min_count)) >= 1


def is_improve_submode_available(db, submode, hist_cutoff, min_count):
  """Whether a submode should appear in the improve cycle (oblivion only when it has targets)."""
  if submode == IMPROVE_SUBMODE_OBLIVION:
    return oblivion_submode_available(db, hist_cutoff, min_count)
  return 0 <= submode < len(IMPROVE_SUBMODE_LABELS)


def next_improve_submode(current, db, hist_cutoff, min_count):
  """Next available submode after current (skips empty oblivion)."""
  n = len(IMPROVE_SUBMODE_LABELS)
  cur = int(current) % n
  for step in range(1, n + 1):
    cand = (cur + step) % n
    if is_improve_submode_available(db, cand, hist_cutoff, min_count):
      return cand
  return IMPROVE_SUBMODE_NORMAL


def clamp_improve_submode(submode, db, hist_cutoff, min_count):
  """If saved/selected submode is unavailable, fall back to normal."""
  if is_improve_submode_available(db, submode, hist_cutoff, min_count):
    return submode
  return IMPROVE_SUBMODE_NORMAL


def fetch_improve_submode_targets(db, submode, hist_cutoff, min_count,
                                  n=FOCUS_DRILL_PICK_COUNT, pool_size=FOCUS_DRILL_POOL_SIZE, rng=None):
  """Return [(kind, data, wpm), ...] for a focus-drill improve submode, or [] if none.

  Auto-drills pick words from the worst `pool_size` in category, then random-sample `n`
  (or fewer if the program has not typed that many eligible words yet).
  Trigrams uses a separate gibberish lesson builder (not this path)."""
  if submode in (IMPROVE_SUBMODE_NORMAL, IMPROVE_SUBMODE_TRIGRAMS):
    return []
  kind = 'word'
  stat_type = STAT_TYPE_WORD
  if submode == IMPROVE_SUBMODE_OBLIVION:
    rows = fetch_oblivion_picks(
      db, hist_cutoff, stat_type, n, OBLIVION_WPM, min_count, pool_size, rng)
  elif submode == IMPROVE_SUBMODE_SLOWEST:
    rows = fetch_slowest_picks(db, hist_cutoff, stat_type, n, min_count, pool_size, rng)
  elif submode == IMPROVE_SUBMODE_HESITANT:
    rows = fetch_hesitant_picks(db, hist_cutoff, stat_type, n, min_count, pool_size, rng)
  elif submode == IMPROVE_SUBMODE_ACCURACY:
    rows = fetch_accuracy_picks(db, hist_cutoff, stat_type, n, min_count, pool_size, rng)
  elif submode == IMPROVE_SUBMODE_DAMAGE:
    rows = fetch_damage_picks(db, hist_cutoff, stat_type, n, min_count, pool_size, rng)
  else:
    return []
  return rows_to_targets(rows, kind)
