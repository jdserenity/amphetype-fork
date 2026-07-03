"""Tests for CLI database path resolution (no Qt)."""

import sqlite3
from pathlib import Path

from typing_program.db_paths import (
  APP_DATA_FOLDER,
  database_search_paths,
  find_database_path,
  resolve_default_database_path,
)
from typing_program.Data import AppDatabase


def _make_db(path, *, texts=0):
  path.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(str(path), 5, 0, 'DEFERRED', False, AppDatabase)
  for i in range(texts):
    conn.execute('insert into text (id, source, text) values (?, 1, ?)', ('t%d' % i, 'hi'))
  conn.commit()
  conn.close()


def test_app_data_folder_matches_qt_application_name():
  assert APP_DATA_FOLDER == 'Typing Program'


def test_resolve_prefers_legacy_when_new_empty(tmp_path, monkeypatch):
  new_dir = tmp_path / 'new'
  legacy_dir = tmp_path / 'legacy'
  monkeypatch.setattr('typing_program.db_paths.app_local_data_dir', lambda: new_dir)
  monkeypatch.setattr('typing_program.legacy_data.legacy_app_support_dir', lambda: legacy_dir)
  _make_db(legacy_dir / 'user.db', texts=2)
  _make_db(new_dir / 'user.db')
  monkeypatch.setattr('typing_program.db_paths.default_db_filename', lambda: 'user.db')
  assert resolve_default_database_path() == legacy_dir / 'user.db'


def test_find_database_path_returns_first_existing(tmp_path, monkeypatch):
  legacy_dir = tmp_path / 'legacy'
  monkeypatch.setattr('typing_program.db_paths.app_local_data_dir', lambda: tmp_path / 'new')
  monkeypatch.setattr('typing_program.legacy_data.legacy_app_support_dir', lambda: legacy_dir)
  monkeypatch.setattr('typing_program.db_paths.default_db_filename', lambda: 'user.db')
  db = legacy_dir / 'user.db'
  _make_db(db, texts=1)
  found, tried = find_database_path()
  assert found == db.resolve()
  assert db in tried


def test_find_database_path_explicit_missing(tmp_path):
  missing = tmp_path / 'nope.db'
  found, tried = find_database_path(str(missing))
  assert found is None
  assert tried == [missing]
