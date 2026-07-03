"""macOS .dmg packaging helpers (used by scripts/build-mac-dmg.sh)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

APP_NAME = 'Typing Program'


def app_bundle_path(dist_dir: Path) -> Path:
  return dist_dir / f'{APP_NAME}.app'


def dmg_path(dist_dir: Path) -> Path:
  return dist_dir / f'{APP_NAME}.dmg'


def staging_dir(dist_dir: Path) -> Path:
  return dist_dir / 'dmg-staging'


def main_executable(app_bundle: Path) -> Path:
  return app_bundle / 'Contents' / 'MacOS' / APP_NAME


def validate_app_bundle(app_bundle: Path) -> None:
  if not app_bundle.is_dir():
    raise FileNotFoundError(f'app bundle not found: {app_bundle}')
  exe = main_executable(app_bundle)
  if not exe.is_file():
    raise FileNotFoundError(f'main executable not found: {exe}')


def prepare_staging(dist_dir: Path) -> Path:
  app_bundle = app_bundle_path(dist_dir)
  validate_app_bundle(app_bundle)
  stage = staging_dir(dist_dir)
  if stage.exists():
    shutil.rmtree(stage)
  stage.mkdir(parents=True)
  shutil.copytree(app_bundle, stage / f'{APP_NAME}.app')
  (stage / 'Applications').symlink_to('/Applications')
  return stage


def create_dmg(dist_dir: Path, hdiutil: str = 'hdiutil') -> Path:
  stage = prepare_staging(dist_dir)
  out = dmg_path(dist_dir)
  if out.exists():
    out.unlink()
  subprocess.run(
    [hdiutil, 'create', '-volname', APP_NAME, '-srcfolder', str(stage), '-ov', '-format', 'UDZO', str(out)],
    check=True,
  )
  shutil.rmtree(stage)
  return out


if __name__ == '__main__':
  import sys
  root = Path(__file__).resolve().parents[1]
  out = create_dmg(root / 'dist')
  print(f'Wrote {out}')
  sys.exit(0 if out.is_file() else 1)
