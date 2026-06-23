"""Shared statistic aggregation for Analysis and weakspot selection.

Drill rows (<Weakspot>, count=0) update median time/hesitation but not count,
mistakes, or damage frequency. Drill mistakes are tracked separately.
"""

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

STAT_TYPE_CHAR = 0
STAT_TYPE_TRIGRAM = 1
STAT_TYPE_WORD = 2

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
ANALYSIS_ORDER_CLAUSES = frozenset(k for k, _ in ANALYSIS_ORDER_OPTIONS)
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


def count_unique_typed(db, hist_cutoff, stat_type):
  row = db.execute(UNIQUE_TYPED_SQL, (hist_cutoff, stat_type)).fetchone()
  return int(row[0]) if row else 0


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
