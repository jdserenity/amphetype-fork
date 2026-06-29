"""Shared statistic aggregation for Analysis and weakspot selection.

Drill rows (<Weakspot>, count=0) update median time/hesitation but not count,
mistakes, or damage frequency. Drill mistakes are tracked separately.
"""

import time

from amphetype.Config import Settings

# Legacy: omit discounted sources entirely (heatmap, etc.).
STAT_OMIT_DISCOUNTED = "(st.source is null or src.discount is null)"

_STAT_IS_COUNTED = "(coalesce(src.discount, 0) = 0)"

STATS_AGG_SUBQUERY = f"""select data,
  agg_median(time) as time,
  agg_median(viscosity) as viscosity,
  sum(case when {_STAT_IS_COUNTED} then st.count else 0 end) as total,
  sum(case when {_STAT_IS_COUNTED} then st.mistakes else 0 end) as mistakes,
  sum(case when not {_STAT_IS_COUNTED} and st.count = 0 then 1 else 0 end) as drilled
  from statistic as st
  left join source as src on st.source = src.rowid
  where st.w >= ? and st.type = ?
  group by data"""

RAW_TARGETS_SQL = f"""select data,
  agg_median(time) as t,
  sum(case when {_STAT_IS_COUNTED} then st.count else 0 end) as total,
  sum(case when {_STAT_IS_COUNTED} then st.mistakes else 0 end) as misses
  from statistic as st
  left join source as src on st.source = src.rowid
  where st.w >= ? and st.type = ?
  group by data having sum(case when {_STAT_IS_COUNTED} then st.count else 0 end) >= ?"""

ANALYSIS_OUTER_SQL = """select data, 12.0/time as wpm,
  100.0-100.0*mistakes/cast(total as real) as accuracy,
  viscosity, total, mistakes, drilled,
  total*time*time*(1.0+mistakes/total) as damage
  from (%s)
  where total >= ?
  order by %s limit %d"""

ANALYSIS_SEARCH_OUTER_SQL = """select data, 12.0/time as wpm,
  100.0-100.0*mistakes/cast(total as real) as accuracy,
  viscosity, total, mistakes, drilled,
  total*time*time*(1.0+mistakes/total) as damage
  from (%s)
  where total >= ? and %s
  order by %s"""

# Heatmap WPM uses the same median-time pool as Analysis; damage uses counted rows only.
SPEED_STATS_SQL = f"""select data,
  12.0 / agg_median(time) as wpm,
  sum(case when {_STAT_IS_COUNTED} then st.count else 0 end) * agg_median(time) * agg_median(time)
    * (1.0 + cast(sum(case when {_STAT_IS_COUNTED} then st.mistakes else 0 end) as real)
       / nullif(sum(case when {_STAT_IS_COUNTED} then st.count else 0 end), 0)) as damage
  from statistic as st
  left join source as src on st.source = src.rowid
  where st.w >= ? and st.type = ?
  group by data"""

UNIQUE_TYPED_SQL = """select count(distinct data) from statistic
  where w >= ? and type = ?"""

STAT_TYPE_CHAR = 0
STAT_TYPE_TRIGRAM = 1
STAT_TYPE_WORD = 2

# WPM = (chars / seconds) * (60 / 5); five characters is the usual "word" in typing tests.
WPM_CHARS_PER_WORD = 5
WPM_SECONDS_FACTOR = 12.0  # 60.0 / WPM_CHARS_PER_WORD

COUNTED_CHAR_SPEED_SQL = f"""select
  sum(case when {_STAT_IS_COUNTED} then st.count else 0 end),
  sum(case when {_STAT_IS_COUNTED} then st.count * st.time else 0 end)
  from statistic as st
  left join source as src on st.source = src.rowid
  where st.w >= ? and st.type = {STAT_TYPE_CHAR}"""

RESULT_WPM_FALLBACK_SQL = """select r.wpm from result as r
  left join source as s on r.source = s.rowid
  where r.w >= ? and r.wpm > 0
    and coalesce(s.discount, 0) = 0
    and coalesce(s.name, '') != '<Weakspot>'"""


def perf_hist_cutoff(now=None, history_days=None):
  now = time.time() if now is None else now
  days = Settings.get('history') if history_days is None else history_days
  return now - days * 86400.0

OBLIVION_POOL_SQL = """select data, 12.0/time as wpm,
  100.0-100.0*mistakes/cast(total as real) as accuracy,
  viscosity, total, mistakes, drilled,
  total*time*time*(1.0+mistakes/total) as damage
  from (%s)
  where 12.0/time < ?
  order by wpm asc"""

SPEED_STATS_ALL_TIME_SQL = f"""select data,
  12.0 / agg_median(time) as wpm,
  sum(case when {_STAT_IS_COUNTED} then st.count else 0 end) * agg_median(time) * agg_median(time)
    * (1.0 + cast(sum(case when {_STAT_IS_COUNTED} then st.mistakes else 0 end) as real)
       / nullif(sum(case when {_STAT_IS_COUNTED} then st.count else 0 end), 0)) as damage
  from statistic as st
  left join source as src on st.source = src.rowid
  where st.type = ?
  group by data"""

ANALYSIS_ORDER_OPTIONS = (
  ('wpm asc', 'slowest'),
  ('wpm desc', 'fastest'),
  ('viscosity desc', 'most hesitation'),
  ('viscosity asc', 'least hesitation'),
  ('accuracy asc', 'least accurate'),
  ('misses desc', 'most mistyped'),
  ('total desc', 'most common'),
  ('damage desc', 'most damaging'),
)
ANALYSIS_ORDER_CLAUSES = frozenset(k for k, _ in ANALYSIS_ORDER_OPTIONS) | frozenset(['improved desc'])
DEFAULT_ANALYSIS_ORDER = 'wpm asc'


def analysis_order_clause(order):
  return order if order in ANALYSIS_ORDER_CLAUSES else DEFAULT_ANALYSIS_ORDER


def analysis_search_data_clause(stat_type):
  if stat_type == STAT_TYPE_WORD:
    return 'instr(lower(data), lower(?)) > 0'
  return 'instr(data, ?) > 0'


def fetch_analysis_search(db, hist_cutoff, stat_type, min_count, term, order):
  term = (term or '').strip()
  if not term:
    return []
  clause = analysis_search_data_clause(stat_type)
  sql = ANALYSIS_SEARCH_OUTER_SQL % (STATS_AGG_SUBQUERY, clause, analysis_order_clause(order))
  return db.execute(sql, (hist_cutoff, stat_type, min_count, term)).fetchall()


def fetch_first_sample_wpm(db, stat_type, data_keys):
  """WPM from each key's earliest counted statistic row (all-time first typing)."""
  if not data_keys:
    return {}
  qs = ','.join('?' * len(data_keys))
  rows = db.execute(
    '''select s.data, min(12.0 / s.time)
    from statistic s
    left join source as src on s.source = src.rowid
    inner join (
      select st.data, min(st.w) as fw from statistic st
      left join source as src2 on st.source = src2.rowid
      where st.type=? and st.data in (%s)
        and %s and st.count > 0
      group by st.data
    ) x on s.data = x.data and s.w = x.fw and s.type=?
    where %s and s.count > 0
    group by s.data''' % (qs, _STAT_IS_COUNTED.replace('src', 'src2'), _STAT_IS_COUNTED),
    (stat_type, *data_keys, stat_type)).fetchall()
  return {d: w for d, w in rows}


def count_unique_typed(db, hist_cutoff, stat_type):
  row = db.execute(UNIQUE_TYPED_SQL, (hist_cutoff, stat_type)).fetchone()
  return int(row[0]) if row else 0


def aggregate_result_wpm(total_chars, total_seconds):
  """Overall WPM across runs: chars typed / elapsed seconds * (60/5)."""
  if not total_chars or not total_seconds:
    return None
  return total_chars / total_seconds * WPM_SECONDS_FACTOR


def _median(vals):
  if not vals:
    return None
  s = sorted(vals); n = len(s)
  if n & 1:
    return s[n // 2]
  return (s[n // 2 - 1] + s[n // 2]) / 2.0


def average_typing_wpm(db, hist_cutoff):
  """Mean WPM from counted per-character timing samples (same pool as Stats speed column)."""
  row = db.execute(COUNTED_CHAR_SPEED_SQL, (hist_cutoff,)).fetchone()
  n, time_weighted = (row[0] or 0), (row[1] or 0)
  if n > 0 and time_weighted > 0:
    return WPM_SECONDS_FACTOR / (time_weighted / n)
  rows = db.execute(RESULT_WPM_FALLBACK_SQL, (hist_cutoff,)).fetchall()
  return _median([r[0] for r in rows])


def fetch_oblivion_pool(db, hist_cutoff, stat_type, oblivion_wpm=30):
  sql = OBLIVION_POOL_SQL % STATS_AGG_SUBQUERY
  return db.execute(sql, (hist_cutoff, stat_type, oblivion_wpm)).fetchall()


def fetch_oblivion_picks(db, hist_cutoff, stat_type, n=3, oblivion_wpm=30):
  """Up to n oblivion targets; widen to all-time when the history window is too thin."""
  import random
  pool = fetch_oblivion_pool(db, hist_cutoff, stat_type, oblivion_wpm)
  if len(pool) < n and hist_cutoff > 0:
    pool = fetch_oblivion_pool(db, 0, stat_type, oblivion_wpm)
  if not pool:
    return []
  return random.sample(pool, min(n, len(pool)))


def fetch_analysis_top(db, hist_cutoff, stat_type, order, limit, min_count=1):
  sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, order, limit)
  return db.execute(sql, (hist_cutoff, stat_type, min_count)).fetchall()


def fetch_slowest_picks(db, hist_cutoff, stat_type, n=3, min_count=1):
  return fetch_analysis_top(db, hist_cutoff, stat_type, 'wpm asc', n, min_count)[:n]


def fetch_hesitant_picks(db, hist_cutoff, stat_type, n=3, min_count=1):
  return fetch_analysis_top(db, hist_cutoff, stat_type, 'viscosity desc', n, min_count)[:n]


def fetch_damage_picks(db, hist_cutoff, stat_type, n=3, min_count=1):
  return fetch_analysis_top(db, hist_cutoff, stat_type, 'damage desc', n, min_count)[:n]
