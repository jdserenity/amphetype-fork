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

SPEED_STATS_ALL_TIME_SQL = f"""select data,
  12.0 / agg_median(time) as wpm,
  sum(case when {_STAT_IS_COUNTED} then st.count else 0 end) * agg_median(time) * agg_median(time)
    * (1.0 + cast(sum(case when {_STAT_IS_COUNTED} then st.mistakes else 0 end) as real)
       / nullif(sum(case when {_STAT_IS_COUNTED} then st.count else 0 end), 0)) as damage
  from statistic as st
  left join source as src on st.source = src.rowid
  where st.type = ?
  group by data"""
