"""Tests for Windows/Linux release archive helpers."""

import os
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.release_archive import (
  APP_NAME,
  app_folder,
  create_tar_gz,
  create_zip,
  main_executable,
  tar_gz_path,
  validate_app_folder,
  zip_path,
)

REPO = Path(__file__).resolve().parents[1]


def test_app_name_and_paths():
  dist = Path('/tmp/example-dist')
  assert app_folder(dist) == dist / 'Typing Program'
  assert zip_path(dist) == dist / 'Typing Program-win.zip'
  assert tar_gz_path(dist) == dist / 'Typing Program-linux.tar.gz'
  assert main_executable(app_folder(dist), windows=True).name == 'Typing Program.exe'
  assert main_executable(app_folder(dist), windows=False).name == APP_NAME


def test_validate_app_folder_requires_directory(tmp_path):
  missing = tmp_path / 'Typing Program'
  with pytest.raises(FileNotFoundError, match='app folder not found'):
    validate_app_folder(missing, windows=False)


def test_validate_app_folder_requires_executable(tmp_path):
  folder = tmp_path / 'Typing Program'
  folder.mkdir()
  with pytest.raises(FileNotFoundError, match='main executable not found'):
    validate_app_folder(folder, windows=True)


def test_validate_app_folder_ok(tmp_path):
  folder = tmp_path / 'Typing Program'
  exe = main_executable(folder, windows=False)
  exe.parent.mkdir(parents=True)
  exe.write_text('', encoding='utf-8')
  validate_app_folder(folder, windows=False)


def test_create_zip_packages_app_folder(tmp_path):
  dist = tmp_path / 'dist'
  folder = app_folder(dist)
  exe = main_executable(folder, windows=True)
  exe.parent.mkdir(parents=True)
  exe.write_bytes(b'exe')
  (folder / 'typing_program' / 'VERSION').parent.mkdir(parents=True)
  (folder / 'typing_program' / 'VERSION').write_text('1.0.0', encoding='utf-8')

  out = create_zip(dist)
  assert out == zip_path(dist)
  with zipfile.ZipFile(out) as zf:
    names = zf.namelist()
  assert 'Typing Program/Typing Program.exe' in names
  assert 'Typing Program/typing_program/VERSION' in names


def test_create_tar_gz_packages_app_folder(tmp_path):
  dist = tmp_path / 'dist'
  folder = app_folder(dist)
  exe = main_executable(folder, windows=False)
  exe.parent.mkdir(parents=True)
  exe.write_text('#!/bin/sh\necho hi\n', encoding='utf-8')
  exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

  out = create_tar_gz(dist)
  assert out == tar_gz_path(dist)
  with tarfile.open(out, 'r:gz') as tf:
    names = tf.getnames()
  assert 'Typing Program/Typing Program' in names


def test_build_linux_script_exists_and_is_executable():
  script = REPO / 'scripts' / 'build-linux.sh'
  assert script.is_file()
  assert os.access(script, os.X_OK)


def test_build_windows_script_exists():
  script = REPO / 'scripts' / 'build-windows.ps1'
  assert script.is_file()
