"""Find the app SQLite file without starting Qt (dev scripts)."""

import getpass
import os
import re
import sys
from pathlib import Path

from typing_program import DATA_DIR
from typing_program.legacy_data import legacy_app_support_dir, resolve_database_path

APP_DATA_FOLDER = 'Typing Program'


def default_db_filename():
  try:
    user = getpass.getuser() or 'user'
  except Exception:
    user = 'user'
  user = re.sub(r'[^a-z0-9_-]', '', user, flags=re.I) or 'user'
  return user + '.db'


def app_local_data_dir():
  home = Path.home()
  if sys.platform == 'darwin':
    return home / 'Library' / 'Application Support' / APP_DATA_FOLDER
  if sys.platform == 'win32':
    local = os.environ.get('LOCALAPPDATA')
    base = Path(local) if local else home / 'AppData' / 'Local'
    return base / APP_DATA_FOLDER
  xdg = os.environ.get('XDG_DATA_HOME')
  base = Path(xdg) if xdg else home / '.local' / 'share'
  return base / APP_DATA_FOLDER


def _env_local():
  return os.environ.get('TYPING_PROGRAM_LOCAL', '').strip().lower() in ('1', 'true', 'yes')


def _db_name_from_ini(ini_path):
  if not ini_path.is_file():
    return None
  for line in ini_path.read_text(encoding='utf-8').splitlines():
    if line.startswith('db_name='):
      raw = line.split('=', 1)[1].strip()
      if raw:
        return Path(raw).expanduser()
  return None


def resolve_default_database_path():
  """Same rules as Config before the GUI starts (local flag, ini override, legacy)."""
  dbfile = default_db_filename()
  if _env_local():
    return DATA_DIR / dbfile
  settings_ini = os.environ.get('TYPING_PROGRAM_SETTINGS')
  if settings_ini:
    p = _db_name_from_ini(Path(settings_ini))
    if p is not None:
      return p
  p = _db_name_from_ini(DATA_DIR / 'typing_program.ini')
  if p is not None:
    return p
  app_dir = app_local_data_dir()
  app_dir.mkdir(parents=True, exist_ok=True)
  return resolve_database_path(app_dir, dbfile)


def database_search_paths():
  """Paths to try when the primary default file is missing."""
  dbfile = default_db_filename()
  paths = []
  seen = set()

  def add(p):
    p = Path(p).expanduser()
    key = str(p)
    if key in seen:
      return
    seen.add(key)
    paths.append(p)

  add(resolve_default_database_path())
  if not _env_local():
    add(DATA_DIR / dbfile)
    add(legacy_app_support_dir() / dbfile)
    add(app_local_data_dir() / dbfile)
  return paths


def find_database_path(cli_path=None):
  """Return (existing path or None, paths checked)."""
  if cli_path:
    p = Path(cli_path).expanduser()
    return (p.resolve() if p.is_file() else None), [p]
  tried = database_search_paths()
  for p in tried:
    if p.is_file():
      return p.resolve(), tried
  return None, tried
