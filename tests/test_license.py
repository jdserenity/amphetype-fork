import io
import json
import urllib.error
from unittest.mock import MagicMock

import pytest

from typing_program.license import (
  activate,
  clear_license,
  is_validate_ok,
  license_bypassed,
  machine_id,
  save_license,
  stored_license,
  validate,
)


ACTIVATE_OK = json.dumps({
  'activated': True,
  'error': None,
  'instance': {'id': 'inst-1', 'name': 'machine-a'},
  'license_key': {'status': 'active'},
}).encode('utf-8')

VALIDATE_OK = json.dumps({
  'valid': True,
  'error': None,
  'license_key': {'status': 'active'},
  'instance': {'id': 'inst-1'},
}).encode('utf-8')

ACTIVATE_FAIL = json.dumps({
  'activated': False,
  'error': 'activation limit reached',
}).encode('utf-8')


def _mock_opener(payload):
  resp = MagicMock()
  resp.read.return_value = payload
  resp.__enter__ = lambda s: s
  resp.__exit__ = MagicMock(return_value=False)
  return lambda req, timeout=20: resp


def _mock_http_error_opener(payload, code=404):
  def opener(req, timeout=20):
    raise urllib.error.HTTPError(req.full_url, code, 'error', {}, io.BytesIO(payload))
  return opener


class _FakeSettings:
  def __init__(self):
    self._data = {}

  def value(self, key, default='', type=str):
    return self._data.get(key, default)

  def setValue(self, key, val):
    self._data[key] = val

  def remove(self, key):
    self._data.pop(key, None)


def test_activate_success():
  data = activate('key-abc', 'machine-a', opener=_mock_opener(ACTIVATE_OK))
  assert data['activated'] is True
  assert data['instance']['id'] == 'inst-1'


def test_activate_failure():
  from typing_program.license import LicenseError
  with pytest.raises(LicenseError, match='activation limit'):
    activate('key-abc', 'machine-a', opener=_mock_opener(ACTIVATE_FAIL))


def test_activate_failure_on_http_error():
  from typing_program.license import LicenseError
  with pytest.raises(LicenseError, match='activation limit'):
    activate('key-abc', 'machine-a', opener=_mock_http_error_opener(ACTIVATE_FAIL, code=404))


def test_validate_not_found_on_http_error():
  payload = json.dumps({'valid': False, 'error': 'license_key not found.'}).encode('utf-8')
  data = validate('key-abc', opener=_mock_http_error_opener(payload, code=404))
  assert is_validate_ok(data) is False


def test_validate_ok():
  data = validate('key-abc', 'inst-1', opener=_mock_opener(VALIDATE_OK))
  assert is_validate_ok(data, 'inst-1') is True


def test_machine_id_stable():
  s = _FakeSettings()
  a = machine_id(s)
  b = machine_id(s)
  assert a == b
  assert len(a) == 36


def test_save_and_load_license():
  s = _FakeSettings()
  save_license(s, 'key-1', 'inst-1')
  assert stored_license(s) == ('key-1', 'inst-1')
  clear_license(s)
  assert stored_license(s) == ('', '')


def test_license_bypass_env(monkeypatch):
  monkeypatch.delenv('TYPING_PROGRAM_SKIP_LICENSE', raising=False)
  assert license_bypassed() is False
  monkeypatch.setenv('TYPING_PROGRAM_SKIP_LICENSE', '1')
  assert license_bypassed() is True
