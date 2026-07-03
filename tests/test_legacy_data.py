"""Tests for legacy Amphetype data directory resolution."""

import sqlite3
from pathlib import Path

from PyQt5.QtCore import QSettings

from typing_program.legacy_data import (
  LEGACY_APP_FOLDER,
  db_has_user_content,
  migrate_legacy_settings,
  resolve_database_path,
)
from typing_program.Data import AppDatabase


def _make_db(path: Path, *, texts: int = 0, stats: int = 0):
  path.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(str(path), 5, 0, 'DEFERRED', False, AppDatabase)
  for i in range(texts):
    conn.execute('insert into text (id, source, text) values (?, 1, ?)', (f't{i}', 'hello'))
  for i in range(stats):
    conn.execute(
      'insert into statistic (data, type, w, time, count, mistakes) values (?, 0, ?, 0.1, 1, 0)',
      (f'k{i}', float(i)),
    )
  conn.commit()
  conn.close()


def test_legacy_folder_name():
  assert LEGACY_APP_FOLDER == 'amphetype'


def test_db_has_user_content_false_for_missing(tmp_path):
  assert db_has_user_content(tmp_path / 'missing.db') is False


def test_db_has_user_content_true_with_text(tmp_path):
  db = tmp_path / 'x.db'
  _make_db(db, texts=1)
  assert db_has_user_content(db) is True


def test_db_has_user_content_false_for_empty_schema(tmp_path):
  db = tmp_path / 'x.db'
  _make_db(db)
  assert db_has_user_content(db) is False


def test_resolve_uses_legacy_when_new_empty(tmp_path, monkeypatch):
  new_dir = tmp_path / 'new'
  legacy_dir = tmp_path / 'legacy'
  monkeypatch.setattr('typing_program.legacy_data.legacy_app_support_dir', lambda: legacy_dir)
  _make_db(legacy_dir / 'user.db', texts=3)
  _make_db(new_dir / 'user.db')

  resolved = resolve_database_path(new_dir, 'user.db')
  assert resolved == legacy_dir / 'user.db'


def test_resolve_keeps_new_when_new_has_data(tmp_path, monkeypatch):
  new_dir = tmp_path / 'new'
  legacy_dir = tmp_path / 'legacy'
  monkeypatch.setattr('typing_program.legacy_data.legacy_app_support_dir', lambda: legacy_dir)
  _make_db(legacy_dir / 'user.db', texts=3)
  _make_db(new_dir / 'user.db', stats=2)

  resolved = resolve_database_path(new_dir, 'user.db')
  assert resolved == new_dir / 'user.db'


def test_migrate_legacy_settings_copies_missing_keys(tmp_path, monkeypatch):
  legacy_ini = tmp_path / 'amphetype.ini'
  legacy_ini.write_text('[General]\nhistory=42\n', encoding='utf-8')
  legacy_store = QSettings(str(legacy_ini), QSettings.IniFormat)

  target = QSettings(str(tmp_path / 'target.ini'), QSettings.IniFormat)
  target.setValue('practice_mode', 1)

  real_qsettings = QSettings

  def fake_qsettings(*args, **kwargs):
    if len(args) >= 4 and args[3] == 'amphetype':
      return legacy_store
    return real_qsettings(*args, **kwargs)

  fake_qsettings.IniFormat = QSettings.IniFormat
  fake_qsettings.UserScope = QSettings.UserScope
  monkeypatch.setattr('typing_program.legacy_data.QSettings', fake_qsettings)
  copied = migrate_legacy_settings(target)
  assert copied == 1
  assert int(target.value('history')) == 42
  assert int(target.value('practice_mode')) == 1
