"""Tests for SQLite app_meta UI state."""

import sqlite3

from typing_program.Data import AppDatabase
from typing_program.app_meta import (
  PREFERENCES_TAB_KEY,
  ensure_app_meta,
  get_app_meta_int,
  set_app_meta_int,
)


def _mem_db():
  return sqlite3.connect(':memory:', 5, 0, 'DEFERRED', False, AppDatabase)


def test_app_meta_table_created_on_migration():
  db = _mem_db()
  row = db.fetchone(
    "select name from sqlite_master where type='table' and name='app_meta'",
    (None,))
  assert row is not None


def test_preferences_tab_roundtrip():
  db = _mem_db()
  ensure_app_meta(db)
  assert get_app_meta_int(db, PREFERENCES_TAB_KEY, 0) == 0
  set_app_meta_int(db, PREFERENCES_TAB_KEY, 2)
  assert get_app_meta_int(db, PREFERENCES_TAB_KEY, 0) == 2


def test_app_meta_int_invalid_value_returns_default():
  db = _mem_db()
  ensure_app_meta(db)
  db.execute(
    "insert into app_meta (key, value) values (?,?)",
    (PREFERENCES_TAB_KEY, 'nope'))
  db.commit()
  assert get_app_meta_int(db, PREFERENCES_TAB_KEY, 1) == 1
