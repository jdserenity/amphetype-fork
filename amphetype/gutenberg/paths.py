from pathlib import Path

from amphetype import cli_options, DATA_DIR


def texts_dir():
  d = DATA_DIR / 'texts'
  d.mkdir(parents=True, exist_ok=True)
  return d


def gutenberg_cache_dir():
  if cli_options.local:
    d = DATA_DIR / 'gutenberg'
  else:
    from PyQt5.QtCore import QStandardPaths
    pth = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    d = Path(pth) / 'gutenberg' if pth else DATA_DIR / 'gutenberg'
  d.mkdir(parents=True, exist_ok=True)
  return d
