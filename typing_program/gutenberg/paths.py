from pathlib import Path

from typing_program import cli_options, DATA_DIR


def texts_dir():
  d = DATA_DIR / 'texts'
  d.mkdir(parents=True, exist_ok=True)
  return d


def gutenberg_cache_dir():
  if cli_options.local:
    d = DATA_DIR / 'gutenberg'
  else:
    from PyQt5.QtCore import QStandardPaths
    from typing_program.legacy_data import active_app_data_dir
    pth = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    root = active_app_data_dir(Path(pth) if pth else DATA_DIR)
    d = root / 'gutenberg'
  d.mkdir(parents=True, exist_ok=True)
  return d
