"""Tests for CLI database path resolution (no Qt)."""

import sqlite3
from pathlib import Path

from typing_program.db_paths import (
  APP_DATA_FOLDER,
  database_search_paths,
  default_db_filename,
  find_database_path,
  resolve_default_database_path,
)
from typing_program.legacy_data import DEFAULT_DB_FILENAME, legacy_username_db_filename
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


def test_default_db_filename_is_product_name():
  assert default_db_filename() == 'typing-program.db'


def test_resolve_migrates_legacy_into_typing_program_folder(tmp_path, monkeypatch):
  new_dir = tmp_path / 'new'
  legacy_dir = tmp_path / 'legacy'
  monkeypatch.setattr('typing_program.db_paths.app_local_data_dir', lambda: new_dir)
  monkeypatch.setattr('typing_program.legacy_data.legacy_app_support_dir', lambda: legacy_dir)
  _make_db(legacy_dir / legacy_username_db_filename(), texts=2)
  _make_db(new_dir / DEFAULT_DB_FILENAME)
  resolved = resolve_default_database_path()
  assert resolved == new_dir / DEFAULT_DB_FILENAME
  assert resolved.is_file()
  from typing_program.legacy_data import db_has_user_content
  assert db_has_user_content(resolved)


def test_find_database_path_returns_migrated_file(tmp_path, monkeypatch):
  new_dir = tmp_path / 'new'
  legacy_dir = tmp_path / 'legacy'
  monkeypatch.setattr('typing_program.db_paths.app_local_data_dir', lambda: new_dir)
  monkeypatch.setattr('typing_program.legacy_data.legacy_app_support_dir', lambda: legacy_dir)
  legacy_db = legacy_dir / legacy_username_db_filename()
  _make_db(legacy_db, texts=1)
  found, tried = find_database_path()
  assert found == (new_dir / DEFAULT_DB_FILENAME).resolve()
  assert len(tried) >= 1


def test_find_database_path_explicit_missing(tmp_path):
  missing = tmp_path / 'nope.db'
  found, tried = find_database_path(str(missing))
  assert found is None
  assert tried == [missing]
