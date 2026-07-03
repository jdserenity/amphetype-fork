"""All-time progress stats for Performance Analysis (WPM gain, heatmap tier climbs)."""

from collections import defaultdict

from typing_program.speed_heatmap import (
  WPM_BUCKET_LABELS, WPM_BUCKETS, wpm_bucket_index, wpm_bucket_transition_count,
)
from typing_program.stats_query import STAT_TYPE_WORD, _STAT_IS_COUNTED
from typing_program.timingtuple import median

WORD_CHRONO_TIMES_SQL = """select s.data, s.time
  from statistic s
  left join source as src on s.source = src.rowid
  where s.type=? and %s and s.count > 0 and s.time > 0
  order by s.data, s.w""" % _STAT_IS_COUNTED


def honest_climbs_for_word(spcs):
  """One adjacent-tier credit per median jump; multi-tier jumps credit the exit arrow only."""
  climbs = [0] * wpm_bucket_transition_count()
  pool = []
  prev_bucket = None
  for spc in spcs:
    pool.append(spc)
    m = median(list(pool))
    if m is None or m <= 0:
      continue
    bucket = wpm_bucket_index(12.0 / m)
    if bucket is None:
      continue
    if prev_bucket is not None and bucket > prev_bucket and prev_bucket < len(climbs):
      climbs[prev_bucket] += 1
    prev_bucket = bucket
  return climbs


def count_all_time_tier_climbs(db):
  """All-time honest heatmap climbs per adjacent tier (words only)."""
  rows = db.execute(WORD_CHRONO_TIMES_SQL, (STAT_TYPE_WORD,)).fetchall()
  by_word = defaultdict(list)
  for data, t in rows:
    by_word[data].append(t)
  totals = [0] * wpm_bucket_transition_count()
  for spcs in by_word.values():
    word_climbs = honest_climbs_for_word(spcs)
    for i, n in enumerate(word_climbs):
      totals[i] += n
  return tuple(totals)


def tier_climb_labels():
  """Short labels for tooltips: '<31 → 32–54', etc."""
  out = []
  for i in range(wpm_bucket_transition_count()):
    out.append('%s → %s' % (WPM_BUCKET_LABELS[i], WPM_BUCKET_LABELS[i + 1]))
  return tuple(out)


def tier_climb_colors():
  """Source color for each climb arrow (the tier being left)."""
  return tuple(c for _t, c in WPM_BUCKETS[:-1])
