import os
from unittest.mock import MagicMock

import certifi

from typing_program.https import ssl_context, urlopen


def test_ssl_context_uses_certifi_bundle():
  bundle = certifi.where()
  assert os.path.isfile(bundle)
  ctx = ssl_context()
  assert ctx.check_hostname is True


def test_urlopen_passes_ssl_context(monkeypatch):
  captured = {}

  def fake_urlopen(url_or_req, timeout=20, context=None):
    captured['context'] = context
    resp = MagicMock()
    resp.read.return_value = b'ok'
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp

  monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
  with urlopen('https://example.com', timeout=5):
    pass
  assert captured['context'] is ssl_context()
