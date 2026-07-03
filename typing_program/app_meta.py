"""Small key/value store in the SQLite database for UI state."""

PREFERENCES_TAB_KEY = 'preferences_tab'
TOTAL_PRACTICE_SECONDS_KEY = 'total_practice_seconds'
TOTAL_PRACTICE_BACKFILL_KEY = 'total_practice_backfill_done'


def ensure_app_meta(db):
  db.execute("""
    create table if not exists app_meta (
      key text primary key,
      value text not null
    )
  """)


def get_app_meta_int(db, key, default=0):
  row = db.fetchone('select value from app_meta where key=?', (None,), (key,))
  if row is None:
    return default
  try:
    return int(row[0])
  except (TypeError, ValueError):
    return default


def set_app_meta_int(db, key, value):
  db.execute("""
    insert into app_meta (key, value) values (?,?)
    on conflict(key) do update set value=excluded.value
  """, (key, str(int(value))))
  db.commit()


def backfill_total_practice_seconds(db):
  """One-time: seed total practice from sum of saved lesson durations (pre-session-timer DBs)."""
  if get_app_meta_int(db, TOTAL_PRACTICE_BACKFILL_KEY, 0):
    return
  if get_app_meta_int(db, TOTAL_PRACTICE_SECONDS_KEY, 0) <= 0:
    row = db.execute('select sum(duration) from result where duration > 0').fetchone()
    total = int(row[0] or 0) if row else 0
    if total > 0:
      set_app_meta_int(db, TOTAL_PRACTICE_SECONDS_KEY, total)
  set_app_meta_int(db, TOTAL_PRACTICE_BACKFILL_KEY, 1)
