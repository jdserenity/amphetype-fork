"""Improve mode submodes: mixed weakspot lessons and auto-picked focus drills."""

from amphetype.stats_query import (
  STAT_TYPE_WORD,
  fetch_damage_picks, fetch_hesitant_picks, fetch_oblivion_picks, fetch_slowest_picks,
)
from amphetype.speed_heatmap import OBLIVION_WPM

IMPROVE_SUBMODE_LABELS = ('normal', 'oblivion', 'slowest', 'hesitant', 'damage')
IMPROVE_SUBMODE_NORMAL = 0
IMPROVE_SUBMODE_OBLIVION = 1
IMPROVE_SUBMODE_SLOWEST = 2
IMPROVE_SUBMODE_HESITANT = 3
IMPROVE_SUBMODE_DAMAGE = 4


def rows_to_targets(rows, kind):
  return [(kind, r[0], r[1]) for r in rows]


def fetch_improve_submode_targets(db, submode, hist_cutoff, min_count, n=3):
  """Return [(kind, data, wpm), ...] for a focus-drill improve submode, or [] if none.

  Auto-drills always pick words — same as the old Stats 'Drill 3 oblivion' / worst-3 buttons."""
  if submode == IMPROVE_SUBMODE_NORMAL:
    return []
  kind = 'word'
  stat_type = STAT_TYPE_WORD
  if submode == IMPROVE_SUBMODE_OBLIVION:
    rows = fetch_oblivion_picks(db, hist_cutoff, stat_type, n, OBLIVION_WPM)
  elif submode == IMPROVE_SUBMODE_SLOWEST:
    rows = fetch_slowest_picks(db, hist_cutoff, stat_type, n, min_count)
  elif submode == IMPROVE_SUBMODE_HESITANT:
    rows = fetch_hesitant_picks(db, hist_cutoff, stat_type, n, min_count)
  elif submode == IMPROVE_SUBMODE_DAMAGE:
    rows = fetch_damage_picks(db, hist_cutoff, stat_type, n, min_count)
  else:
    return []
  return rows_to_targets(rows, kind)
