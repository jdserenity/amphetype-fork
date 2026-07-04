"""HTTPS helpers for frozen and dev builds (certifi CA bundle)."""

import ssl
import urllib.request

import certifi

_CTX = None


def ssl_context():
  global _CTX
  if _CTX is None:
    _CTX = ssl.create_default_context(cafile=certifi.where())
  return _CTX


def urlopen(url_or_req, timeout=20):
  return urllib.request.urlopen(url_or_req, timeout=timeout, context=ssl_context())
