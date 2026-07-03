"""Zip/tar.gz packaging for PyInstaller one-folder Windows/Linux builds."""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

APP_NAME = 'Typing Program'


def app_folder(dist_dir: Path) -> Path:
  return dist_dir / APP_NAME


def main_executable(app_dir: Path, *, windows: bool) -> Path:
  if windows:
    return app_dir / f'{APP_NAME}.exe'
  return app_dir / APP_NAME


def zip_path(dist_dir: Path) -> Path:
  return dist_dir / f'{APP_NAME}-win.zip'


def tar_gz_path(dist_dir: Path) -> Path:
  return dist_dir / f'{APP_NAME}-linux.tar.gz'


def validate_app_folder(app_dir: Path, *, windows: bool) -> None:
  if not app_dir.is_dir():
    raise FileNotFoundError(f'app folder not found: {app_dir}')
  exe = main_executable(app_dir, windows=windows)
  if not exe.is_file():
    raise FileNotFoundError(f'main executable not found: {exe}')


def create_zip(dist_dir: Path) -> Path:
  folder = app_folder(dist_dir)
  validate_app_folder(folder, windows=True)
  out = zip_path(dist_dir)
  if out.exists():
    out.unlink()
  with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for path in folder.rglob('*'):
      if path.is_file():
        zf.write(path, Path(APP_NAME) / path.relative_to(folder))
  return out


def create_tar_gz(dist_dir: Path) -> Path:
  folder = app_folder(dist_dir)
  validate_app_folder(folder, windows=False)
  out = tar_gz_path(dist_dir)
  if out.exists():
    out.unlink()
  with tarfile.open(out, 'w:gz') as tf:
    tf.add(folder, arcname=APP_NAME)
  return out


if __name__ == '__main__':
  root = Path(__file__).resolve().parents[1]
  dist = root / 'dist'
  target = sys.argv[1] if len(sys.argv) > 1 else ''
  if target == 'windows':
    archive = create_zip(dist)
  elif target == 'linux':
    archive = create_tar_gz(dist)
  else:
    print('usage: release_archive.py windows|linux', file=sys.stderr)
    sys.exit(2)
  print(f'Wrote {archive}')
  sys.exit(0 if archive.is_file() else 1)
