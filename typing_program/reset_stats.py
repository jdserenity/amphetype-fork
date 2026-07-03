"""Clear typing statistics while keeping imported texts, sources, and book progress."""

TYPING_STAT_TABLES = ('statistic', 'result', 'mistake')
_REQUIRED_TABLES = ('source',) + TYPING_STAT_TABLES


def reset_typing_stats(db):
  """Delete word/char/trigram stats and lesson results; keep books and reading place."""
  tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'").fetchall()}
  missing = [t for t in _REQUIRED_TABLES if t not in tables]
  if missing:
    raise RuntimeError('Not a Typing Program database (missing: %s)' % ', '.join(missing))
  for table in TYPING_STAT_TABLES:
    db.execute('delete from %s' % table)
  db.execute("update source set discount = 1 where name = '<Weakspot>' and discount is null")
  db.commit()
