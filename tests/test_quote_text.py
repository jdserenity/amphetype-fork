"""Quotes-only normalization for lesson text and keystrokes."""

from typing_program.quote_text import normalize_quotes


def test_normalize_quotes_curly_apostrophe_and_doubles():
  assert normalize_quotes('don\u2019t') == "don't"
  assert normalize_quotes('\u201chello\u201d') == '"hello"'
  assert normalize_quotes('\u2018hi\u2019') == "'hi'"


def test_normalize_quotes_guillemets_and_low9():
  assert normalize_quotes('\u00abbonjour\u00bb') == '"bonjour"'
  assert normalize_quotes('\u201ethey said\u201d') == '"they said"'


def test_normalize_quotes_keeps_accents():
  assert normalize_quotes('caf\u00e9') == 'caf\u00e9'
  assert normalize_quotes('na\u00efve') == 'na\u00efve'
  assert normalize_quotes('\u00fcber') == '\u00fcber'
  assert normalize_quotes('espa\u00f1ol') == 'espa\u00f1ol'


def test_normalize_quotes_plain_ascii_unchanged():
  assert normalize_quotes("She said, \"hello.\"") == 'She said, "hello."'
  assert normalize_quotes("it's fine") == "it's fine"
