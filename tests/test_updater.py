import hashlib
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from typing_program import __version__
from typing_program.updater import (
  UpdateError,
  check_for_update,
  extract_archive,
  find_payload_root,
  is_frozen,
  is_newer,
  parse_version,
  verify_sha256,
)


class _FakeSettings:
  def __init__(self, key='', instance=''):
    self._data = {'license_key': key, 'license_instance_id': instance}

  def value(self, key, default='', type=str):
    return self._data.get(key, default)


CHECK_OK = json.dumps({
  'update_available': True,
  'version': '9.0.0',
  'sha256': 'abc',
  'download_url': 'https://example.com/dl',
  'release_notes': 'New stuff',
}).encode('utf-8')

CHECK_NONE = json.dumps({'update_available': False}).encode('utf-8')


def _mock_opener(payload):
  resp = MagicMock()
  resp.read.return_value = payload
  resp.__enter__ = lambda s: s
  resp.__exit__ = MagicMock(return_value=False)
  return lambda req, timeout=120: resp


def test_parse_version():
  assert parse_version('1.2.3') == (1, 2, 3)
  assert parse_version('1.2.1') == (1, 2, 1)


def test_is_newer():
  assert is_newer('1.3.0', '1.2.1') is True
  assert is_newer('1.2.1', '1.2.1') is False
  assert is_newer('1.2.0', '1.2.1') is False


def test_check_for_update_available():
  s = _FakeSettings('key-1', 'inst-1')
  info = check_for_update(s, current_version='1.0.0', opener=_mock_opener(CHECK_OK))
  assert info['update_available'] is True
  assert info['version'] == '9.0.0'
  assert info['download_url'] == 'https://example.com/dl'


def test_check_for_update_none():
  s = _FakeSettings('key-1', 'inst-1')
  info = check_for_update(s, opener=_mock_opener(CHECK_NONE))
  assert info['update_available'] is False


def test_check_for_update_requires_license():
  s = _FakeSettings()
  with pytest.raises(UpdateError, match='license'):
    check_for_update(s, opener=_mock_opener(CHECK_OK))


def test_verify_sha256(tmp_path):
  p = tmp_path / 'blob.bin'
  p.write_bytes(b'hello')
  digest = hashlib.sha256(b'hello').hexdigest()
  verify_sha256(p, digest)
  with pytest.raises(UpdateError, match='hash'):
    verify_sha256(p, '0' * 64)


def test_extract_zip_and_find_mac_payload(tmp_path):
  app = tmp_path / 'build' / 'Typing Program.app'
  app.mkdir(parents=True)
  (app / 'Contents').mkdir()
  zpath = tmp_path / 'update.zip'
  with zipfile.ZipFile(zpath, 'w') as zf:
    zf.writestr('Typing Program.app/Contents/Info.plist', 'ok')
  out = tmp_path / 'out'
  extract_archive(zpath, out)
  payload = find_payload_root(out, 'darwin')
  assert payload.name == 'Typing Program.app'


def test_is_frozen_false_by_default():
  assert is_frozen() is False
