"""Clear typing statistics while keeping imported texts, sources, and book progress."""

TYPING_STAT_TABLES = ('statistic', 'result', 'mistake')


def reset_typing_stats(db):
  """Delete word/char/trigram stats and lesson results; keep books and reading place."""
  for table in TYPING_STAT_TABLES:
    db.execute('delete from %s' % table)
  db.execute("update source set discount = 1 where name = '<Weakspot>' and discount is null")
  db.commit()
