"""Small key/value store in the SQLite database for UI state."""

PREFERENCES_TAB_KEY = 'preferences_tab'


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
