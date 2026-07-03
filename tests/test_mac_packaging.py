"""Tests for macOS .dmg packaging helpers."""

import os
import stat
from pathlib import Path

import pytest

from scripts.mac_dmg import (
  APP_NAME,
  app_bundle_path,
  create_dmg,
  dmg_path,
  main_executable,
  prepare_staging,
  staging_dir,
  validate_app_bundle,
)

REPO = Path(__file__).resolve().parents[1]


def test_app_name_and_paths():
  dist = Path('/tmp/example-dist')
  assert app_bundle_path(dist) == dist / 'Typing Program.app'
  assert dmg_path(dist) == dist / 'Typing Program.dmg'
  assert staging_dir(dist) == dist / 'dmg-staging'
  assert main_executable(app_bundle_path(dist)).name == APP_NAME


def test_validate_app_bundle_requires_directory(tmp_path):
  missing = tmp_path / 'Typing Program.app'
  with pytest.raises(FileNotFoundError, match='app bundle not found'):
    validate_app_bundle(missing)


def test_validate_app_bundle_requires_executable(tmp_path):
  bundle = tmp_path / 'Typing Program.app'
  bundle.mkdir()
  (bundle / 'Contents' / 'MacOS').mkdir(parents=True)
  with pytest.raises(FileNotFoundError, match='main executable not found'):
    validate_app_bundle(bundle)


def test_validate_app_bundle_ok(tmp_path):
  bundle = tmp_path / 'Typing Program.app'
  exe = bundle / 'Contents' / 'MacOS' / APP_NAME
  exe.parent.mkdir(parents=True)
  exe.write_text('', encoding='utf-8')
  validate_app_bundle(bundle)


def test_prepare_staging_copies_app_and_links_applications(tmp_path):
  dist = tmp_path / 'dist'
  dist.mkdir()
  bundle = app_bundle_path(dist)
  exe = main_executable(bundle)
  exe.parent.mkdir(parents=True)
  exe.write_text('#!/bin/sh\necho hi\n', encoding='utf-8')
  exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

  stage = prepare_staging(dist)
  assert stage == staging_dir(dist)
  assert (stage / 'Typing Program.app' / 'Contents' / 'MacOS' / APP_NAME).is_file()
  apps = stage / 'Applications'
  assert apps.is_symlink()
  assert os.readlink(apps) == '/Applications'


def test_create_dmg_calls_hdiutil(tmp_path, monkeypatch):
  dist = tmp_path / 'dist'
  dist.mkdir()
  bundle = app_bundle_path(dist)
  exe = main_executable(bundle)
  exe.parent.mkdir(parents=True)
  exe.write_text('', encoding='utf-8')

  calls = []

  def fake_run(cmd, check):
    calls.append(cmd)
    assert check is True
    out = dmg_path(dist)
    out.write_bytes(b'dmg-bytes')

  monkeypatch.setattr('scripts.mac_dmg.subprocess.run', fake_run)
  out = create_dmg(dist, hdiutil='fake-hdiutil')
  assert out == dmg_path(dist)
  assert calls[0][0] == 'fake-hdiutil'
  assert '-volname' in calls[0] and APP_NAME in calls[0]
  assert not staging_dir(dist).exists()


def test_build_mac_dmg_script_exists_and_is_executable():
  script = REPO / 'scripts' / 'build-mac-dmg.sh'
  assert script.is_file()
  assert os.access(script, os.X_OK)
