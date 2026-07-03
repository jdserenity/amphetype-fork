"""Find pre-rename (Amphetype) user data and migrate it into Typing Program folders."""

from __future__ import annotations

import getpass
import re
import shutil
import sqlite3
import sys
from pathlib import Path

from PyQt5.QtCore import QSettings

LEGACY_APP_FOLDER = 'amphetype'
LEGACY_SETTINGS_APP = 'amphetype'
DEFAULT_DB_FILENAME = 'typing-program.db'

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


def legacy_username_db_filename():
  try:
    user = getpass.getuser() or 'user'
  except Exception:
    user = 'user'
  user = re.sub(r'[^a-z0-9_-]', '', user, flags=re.I) or 'user'
  return user + '.db'


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


def _atomic_copy_file(src: Path, dst: Path):
  dst.parent.mkdir(parents=True, exist_ok=True)
  tmp = dst.with_name(dst.name + '.tmp')
  shutil.copy2(src, tmp)
  tmp.replace(dst)


def _legacy_db_sources(legacy_dir: Path, new_data_dir: Path):
  """Old database files that may still hold the user's data."""
  seen = set()
  for name in (legacy_username_db_filename(), DEFAULT_DB_FILENAME):
    if name in seen:
      continue
    seen.add(name)
    for base in (legacy_dir, new_data_dir):
      p = base / name
      if p.is_file() and db_has_user_content(p):
        yield p


def migrate_legacy_support_files(legacy_dir: Path, new_data_dir: Path):
  new_data_dir.mkdir(parents=True, exist_ok=True)
  src = legacy_dir / 'gutenberg'
  dst = new_data_dir / 'gutenberg'
  if src.is_dir() and not dst.exists():
    shutil.copytree(src, dst)


def resolve_database_path(new_data_dir: Path, db_filename: str) -> Path:
  """Default database path under Typing Program; one-time copy from Amphetype if needed."""
  global _active_app_data_dir
  _active_app_data_dir = None
  new_db = new_data_dir / db_filename
  if db_has_user_content(new_db):
    return new_db
  legacy_dir = legacy_app_support_dir()
  for legacy_db in _legacy_db_sources(legacy_dir, new_data_dir):
    if legacy_db.resolve() == new_db.resolve():
      return new_db
    _atomic_copy_file(legacy_db, new_db)
    migrate_legacy_support_files(legacy_dir, new_data_dir)
    return new_db
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
