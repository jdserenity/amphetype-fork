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
  viscosity, total, total - mistakes as perfect, drilled,
  total*time*time*(1.0+mistakes/total) as damage
  from (%s)
  where total >= ?
  order by %s limit %d"""

ANALYSIS_SEARCH_OUTER_SQL = """select data, 12.0/time as wpm,
  viscosity, total, total - mistakes as perfect, drilled,
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

COUNT_TYPED_MIN_SQL = f"""select count(*) from (
  select data from statistic as st
  left join source as src on st.source = src.rowid
  where st.w >= ? and st.type = ?
  group by data
  having sum(case when {_STAT_IS_COUNTED} then st.count else 0 end) >= ?
)"""

STAT_TYPE_CHAR = 0
STAT_TYPE_TRIGRAM = 1
STAT_TYPE_WORD = 2

# Performance Analysis words: one-off typos are noise; only show repeat vocabulary.
WORD_ANALYSIS_MIN_COUNT = 2

# WPM = (chars / seconds) * (60 / 5); five characters is the usual "word" in typing tests.
WPM_CHARS_PER_WORD = 5
WPM_SECONDS_FACTOR = 12.0  # 60.0 / WPM_CHARS_PER_WORD

SESSION_WPM_TOTALS_SQL = """select sum(char_count), sum(duration)
  from result
  where w >= ? and char_count > 0 and duration > 0"""


# w >= 0 includes every statistic/result row (all-time).
ALL_TIME_HIST = 0

# Session WPM stays hidden until this many corpus/book/improve-normal lessons finish.
WPM_GATE_MIN_LESSONS = 10

WPM_GATE_LESSONS_SQL = """select count(*) from result r
  join source s on r.source = s.rowid
  where (coalesce(s.discount, 0) = 0 and s.name not like '<%>')
     or s.name = '<Weakspot>'"""

WPM_GATE_FIRST_LESSON_SQL = """select r.char_count, r.duration from result r
  join source s on r.source = s.rowid
  where ((coalesce(s.discount, 0) = 0 and s.name not like '<%>')
     or s.name = '<Weakspot>')
    and r.char_count > 0 and r.duration > 0
  order by r.w asc limit 1"""

OBLIVION_POOL_SQL = """select data, 12.0/time as wpm,
  viscosity, total, total - mistakes as perfect, drilled,
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
  ('perfect_pct asc', 'lowest perfect %'),
  ('perfect_pct desc', 'highest perfect %'),
  ('total desc', 'most common'),
  ('damage desc', 'most damaging'),
)
ANALYSIS_ORDER_CLAUSES = frozenset(k for k, _ in ANALYSIS_ORDER_OPTIONS) | frozenset(['improved desc'])
DEFAULT_ANALYSIS_ORDER = 'wpm asc'
_LEGACY_ANALYSIS_ORDER = {
  'accuracy asc': 'perfect_pct asc',
  'misses desc': 'perfect_pct asc',
  'perfect asc': 'perfect_pct asc',
  'perfect desc': 'perfect_pct desc',
}
_ANALYSIS_ORDER_SQL = {
  'perfect_pct asc': 'cast(total - mistakes as real) / total asc',
  'perfect_pct desc': 'cast(total - mistakes as real) / total desc',
}


def analysis_order_clause(order):
  order = _LEGACY_ANALYSIS_ORDER.get(order, order)
  return order if order in ANALYSIS_ORDER_CLAUSES else DEFAULT_ANALYSIS_ORDER


def analysis_order_sql(order):
  key = analysis_order_clause(order)
  return _ANALYSIS_ORDER_SQL.get(key, key)


def analysis_min_count(stat_type, configured):
  """Words in Performance Analysis need at least WORD_ANALYSIS_MIN_COUNT completions."""
  n = int(configured or 1)
  if stat_type == STAT_TYPE_WORD:
    return max(n, WORD_ANALYSIS_MIN_COUNT)
  return n


def analysis_search_data_clause(stat_type):
  if stat_type == STAT_TYPE_WORD:
    return 'instr(lower(data), lower(?)) > 0'
  return 'instr(data, ?) > 0'


def fetch_analysis_search(db, hist_cutoff, stat_type, min_count, term, order):
  term = (term or '').strip()
  if not term:
    return []
  clause = analysis_search_data_clause(stat_type)
  sql = ANALYSIS_SEARCH_OUTER_SQL % (STATS_AGG_SUBQUERY, clause, analysis_order_sql(order))
  return db.execute(sql, (hist_cutoff, stat_type, analysis_min_count(stat_type, min_count), term)).fetchall()


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


def count_analysis_words(db, hist_cutoff):
  """Distinct words with enough completions to appear in Performance Analysis."""
  row = db.execute(
    COUNT_TYPED_MIN_SQL, (hist_cutoff, STAT_TYPE_WORD, WORD_ANALYSIS_MIN_COUNT)).fetchone()
  return int(row[0]) if row else 0


def aggregate_session_wpm(total_chars, total_seconds):
  """Session WPM across finished lessons: total chars / total typing seconds * (60/5)."""
  if not total_chars or not total_seconds:
    return None
  return total_chars / total_seconds * WPM_SECONDS_FACTOR


def aggregate_session_wpm_from_results(db, hist_cutoff):
  """Sum char_count and duration from result rows that recorded both at lesson end."""
  row = db.execute(SESSION_WPM_TOTALS_SQL, (hist_cutoff,)).fetchone()
  if not row:
    return None
  return aggregate_session_wpm(row[0] or 0, row[1] or 0)


def count_wpm_gate_lessons(db):
  """Finished corpus, book, or improve-normal lessons (counts toward the WPM gate)."""
  row = db.execute(WPM_GATE_LESSONS_SQL).fetchone()
  return int(row[0]) if row else 0


def wpm_gate_complete(db):
  return count_wpm_gate_lessons(db) >= WPM_GATE_MIN_LESSONS


def wpm_gate_remaining(db):
  return max(0, WPM_GATE_MIN_LESSONS - count_wpm_gate_lessons(db))


def format_wpm_gate_label(db):
  if wpm_gate_complete(db):
    return None
  left = wpm_gate_remaining(db)
  if left == WPM_GATE_MIN_LESSONS:
    return 'Complete %d lessons to calculate WPM' % WPM_GATE_MIN_LESSONS
  return 'Complete %d more lesson%s to calculate WPM' % (left, '' if left == 1 else 's')


def format_avg_wpm_label(db, hist_cutoff=ALL_TIME_HIST):
  """Performance Analysis header: hide Avg WPM until enough lessons; then use all saved runs."""
  gate = format_wpm_gate_label(db)
  if gate:
    return gate
  avg = aggregate_session_wpm_from_results(db, hist_cutoff)
  if avg is None:
    return 'Avg WPM: —'
  from typing_program.wpm_percentile import format_adult_top_percent_label
  rank_lbl = format_adult_top_percent_label(avg)
  return 'Avg WPM: %.1f · %s' % (avg, rank_lbl) if rank_lbl else 'Avg WPM: %.1f' % avg


def first_qualifying_session_wpm(db):
  """WPM from the earliest gate-qualifying lesson in result."""
  row = db.execute(WPM_GATE_FIRST_LESSON_SQL).fetchone()
  if not row:
    return None
  return aggregate_session_wpm(row[0] or 0, row[1] or 0)


def session_wpm_since_start_gain(db, hist_cutoff=ALL_TIME_HIST):
  """Current session WPM minus WPM from the first qualifying lesson. None until gate opens."""
  if not wpm_gate_complete(db):
    return None
  current = aggregate_session_wpm_from_results(db, hist_cutoff)
  first = first_qualifying_session_wpm(db)
  if current is None or first is None:
    return None
  return int(round(current - first))


def lesson_qualifies_for_wpm_gate(mode, improve_submode=0, focus_drill=False):
  """True for corpus, book, and improve-normal lessons (not focus drills)."""
  from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
  if focus_drill:
    return False
  if mode in (MODE_CORPUS, MODE_BOOK):
    return True
  return mode == MODE_IMPROVE and improve_submode == 0


def fetch_oblivion_pool(db, hist_cutoff, stat_type, oblivion_wpm=30):
  sql = OBLIVION_POOL_SQL % STATS_AGG_SUBQUERY
  return db.execute(sql, (hist_cutoff, stat_type, oblivion_wpm)).fetchall()


def fetch_oblivion_picks(db, hist_cutoff, stat_type, n=3, oblivion_wpm=30):
  """Up to n oblivion targets from the statistic pool."""
  import random
  pool = fetch_oblivion_pool(db, hist_cutoff, stat_type, oblivion_wpm)
  if not pool:
    return []
  return random.sample(pool, min(n, len(pool)))


def fetch_analysis_top(db, hist_cutoff, stat_type, order, limit, min_count=1):
  sql = ANALYSIS_OUTER_SQL % (STATS_AGG_SUBQUERY, analysis_order_sql(order), limit)
  return db.execute(sql, (hist_cutoff, stat_type, analysis_min_count(stat_type, min_count))).fetchall()


def fetch_slowest_picks(db, hist_cutoff, stat_type, n=3, min_count=1):
  return fetch_analysis_top(db, hist_cutoff, stat_type, 'wpm asc', n, min_count)[:n]


def fetch_hesitant_picks(db, hist_cutoff, stat_type, n=3, min_count=1):
  return fetch_analysis_top(db, hist_cutoff, stat_type, 'viscosity desc', n, min_count)[:n]


def fetch_damage_picks(db, hist_cutoff, stat_type, n=3, min_count=1):
  return fetch_analysis_top(db, hist_cutoff, stat_type, 'damage desc', n, min_count)[:n]


DELETE_STAT_TARGET_SQL = 'delete from statistic where type = ? and data = ?'


def delete_stat_target(db, stat_type, data):
  """Remove all statistic rows for one keys/trigrams/words target."""
  return db.execute(DELETE_STAT_TARGET_SQL, (stat_type, data)).rowcount
