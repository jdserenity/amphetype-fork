"""Improve mode submodes: mixed weakspot lessons and auto-picked focus drills."""

from typing_program.stats_query import (
  STAT_TYPE_WORD,
  fetch_damage_picks, fetch_hesitant_picks, fetch_oblivion_picks, fetch_slowest_picks,
)
from typing_program.speed_heatmap import OBLIVION_WPM

# Order is UI cycle order on the improve submode button.
IMPROVE_SUBMODE_LABELS = ('normal', 'trigrams', 'oblivion', 'slowest', 'hesitant', 'damage')
IMPROVE_SUBMODE_NORMAL = 0
IMPROVE_SUBMODE_TRIGRAMS = 1
IMPROVE_SUBMODE_OBLIVION = 2
IMPROVE_SUBMODE_SLOWEST = 3
IMPROVE_SUBMODE_HESITANT = 4
IMPROVE_SUBMODE_DAMAGE = 5


def rows_to_targets(rows, kind):
  return [(kind, r[0], r[1]) for r in rows]


def fetch_improve_submode_targets(db, submode, hist_cutoff, min_count, n=3):
  """Return [(kind, data, wpm), ...] for a focus-drill improve submode, or [] if none.

  Auto-drills always pick words — same as the old Stats 'Drill 3 oblivion' / worst-3 buttons.
  Trigrams uses a separate gibberish lesson builder (not this path)."""
  if submode in (IMPROVE_SUBMODE_NORMAL, IMPROVE_SUBMODE_TRIGRAMS):
    return []
  kind = 'word'
  stat_type = STAT_TYPE_WORD
  if submode == IMPROVE_SUBMODE_OBLIVION:
    rows = fetch_oblivion_picks(db, hist_cutoff, stat_type, n, OBLIVION_WPM, min_count)
  elif submode == IMPROVE_SUBMODE_SLOWEST:
    rows = fetch_slowest_picks(db, hist_cutoff, stat_type, n, min_count)
  elif submode == IMPROVE_SUBMODE_HESITANT:
    rows = fetch_hesitant_picks(db, hist_cutoff, stat_type, n, min_count)
  elif submode == IMPROVE_SUBMODE_DAMAGE:
    rows = fetch_damage_picks(db, hist_cutoff, stat_type, n, min_count)
  else:
    return []
  return rows_to_targets(rows, kind)
