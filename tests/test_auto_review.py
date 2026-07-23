"""Unit tests for auto-review lesson text building."""

from typing_program.auto_review import build_review_sentences, build_review_text

def test_build_review_sentences_batches_and_repeats():
  # defaults: take=2, copies=3, mix=concatenate
  assert build_review_sentences(['a', 'b', 'c', 'd']) == [
    'a b a b a b',
    'c d c d c d',
  ]

def test_build_review_sentences_take_all_when_zero():
  assert build_review_sentences(['x', 'y'], take=0, copies=2) == [
    'x y x y',
  ]

def test_build_review_text_joins_sentences():
  assert build_review_text(['a', 'b']) == 'a b a b a b'

def test_build_review_text_empty():
  assert build_review_text([]) == ''
