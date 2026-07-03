"""Find pre-rename (Amphetype) user data and prefer it when the new location is empty."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PyQt5.QtCore import QSettings

LEGACY_APP_FOLDER = 'amphetype'
LEGACY_SETTINGS_APP = 'amphetype'

_active_app_data_dir: Path | None = None


def legacy_app_support_dir() -> Path:
  home = Path.home()
  if sys.platform == 'darwin':
    return home / 'Library' / 'Application Support' / LEGACY_APP_FOLDER
  if sys.platform == 'win32':
    return home / 'AppData' / 'Local' / LEGACY_APP_FOLDER
  return home / '.local' / 'share' / LEGACY_APP_FOLDER


def active_app_data_dir(fallback: Path) -> Path:
  return _active_app_data_dir if _active_app_data_dir is not None else fallback


def db_has_user_content(db_path: Path) -> bool:
  if not db_path.is_file():
    return False
  try:
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
      texts = conn.execute('select count(*) from text').fetchone()[0]
      stats = conn.execute('select count(*) from statistic').fetchone()[0]
      return texts > 0 or stats > 0
    finally:
      conn.close()
  except sqlite3.Error:
    return False


def resolve_database_path(new_data_dir: Path, db_filename: str) -> Path:
  """Use the legacy database when the new default path is empty but the old one has data."""
  global _active_app_data_dir
  new_db = new_data_dir / db_filename
  legacy_dir = legacy_app_support_dir()
  legacy_db = legacy_dir / db_filename

  if legacy_db.is_file() and db_has_user_content(legacy_db) and not db_has_user_content(new_db):
    _active_app_data_dir = legacy_dir
    return legacy_db

  _active_app_data_dir = None
  return new_db


def migrate_legacy_settings(settings) -> int:
  """Copy keys from the old amphetype.ini into the new settings object. Returns count copied."""
  legacy = QSettings(QSettings.IniFormat, QSettings.UserScope, LEGACY_SETTINGS_APP, LEGACY_SETTINGS_APP)
  legacy_file = Path(legacy.fileName())
  if not legacy_file.is_file():
    return 0
  copied = 0
  for key in legacy.allKeys():
    if settings.contains(key):
      continue
    settings.setValue(key, legacy.value(key))
    copied += 1
  if copied:
    settings.sync()
  return copied
