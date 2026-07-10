"""Small key/value store in the SQLite database for UI state."""

PREFERENCES_TAB_KEY = 'preferences_tab'
TOTAL_PRACTICE_SECONDS_KEY = 'total_practice_seconds'
PERFECT_RATE_BASELINE_KEY = 'perfect_rate_baseline_pct'


def ensure_app_meta(db):
  db.execute("""
    create table if not exists app_meta (
      key text primary key,
      value text not null
    )
  """)


def get_app_meta_raw(db, key, default=None):
  row = db.fetchone('select value from app_meta where key=?', (None,), (key,))
  if row is None:
    return default
  return row[0]


def get_app_meta_int(db, key, default=0):
  raw = get_app_meta_raw(db, key, None)
  if raw is None:
    return default
  try:
    return int(raw)
  except (TypeError, ValueError):
    return default


def set_app_meta_int(db, key, value):
  db.execute("""
    insert into app_meta (key, value) values (?,?)
    on conflict(key) do update set value=excluded.value
  """, (key, str(int(value))))
  db.commit()


def get_app_meta_float(db, key, default=None):
  raw = get_app_meta_raw(db, key, None)
  if raw is None:
    return default
  try:
    return float(raw)
  except (TypeError, ValueError):
    return default


def set_app_meta_float(db, key, value):
  db.execute("""
    insert into app_meta (key, value) values (?,?)
    on conflict(key) do update set value=excluded.value
  """, (key, repr(float(value))))
  db.commit()
