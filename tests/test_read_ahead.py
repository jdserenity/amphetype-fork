"""Unit tests for read-ahead word hiding logic."""

from amphetype.read_ahead import (
  READ_AHEAD_OFF, READ_AHEAD_NORMAL, READ_AHEAD_EASY, READ_AHEAD_HARD,
  READ_AHEAD_LEVEL_NORMAL, READ_AHEAD_LEVEL_HARD, READ_AHEAD_LEVEL_EASY,
  current_word_index, hidden_word_indices, hidden_char_indices, word_spans,
  document_read_ahead_mode,
)


TEXT = "hello world foo bar"


def test_word_spans():
  assert word_spans(TEXT) == [(0, 5), (6, 11), (12, 15), (16, 19)]


def test_current_word_on_first_word():
  assert current_word_index(TEXT, 0) == 0
  assert current_word_index(TEXT, 4) == 0


def test_current_word_on_space_before_next():
  assert current_word_index(TEXT, 5) == 1


def test_current_word_on_later_word():
  assert current_word_index(TEXT, 12) == 2


def test_hidden_off():
  assert hidden_word_indices(TEXT, 0, READ_AHEAD_OFF) == []
  assert hidden_char_indices(TEXT, 0, READ_AHEAD_OFF) == set()


def test_hidden_easy_from_start():
  assert hidden_word_indices(TEXT, 0, READ_AHEAD_EASY) == [0]


def test_hidden_normal_from_start():
  assert hidden_word_indices(TEXT, 0, READ_AHEAD_NORMAL) == [0, 1]


def test_hidden_hard_from_start():
  assert hidden_word_indices(TEXT, 0, READ_AHEAD_HARD) == [0, 1, 2]


def test_hidden_shifts_as_typing_advances():
  assert hidden_word_indices(TEXT, 12, READ_AHEAD_NORMAL) == [2, 3]
  assert hidden_word_indices(TEXT, 16, READ_AHEAD_NORMAL) == [3]


def test_hidden_char_indices_cover_word_letters_only():
  hidden = hidden_char_indices(TEXT, 0, READ_AHEAD_NORMAL)
  assert hidden == set(range(0, 5)) | set(range(6, 11))


def test_hidden_near_text_end():
  assert hidden_word_indices("one two", 0, READ_AHEAD_HARD) == [0, 1]
  assert hidden_word_indices("one two", 4, READ_AHEAD_HARD) == [1]


def test_revealed_word_excluded_from_hidden():
  revealed = {0}
  hidden = hidden_char_indices(TEXT, 0, READ_AHEAD_NORMAL, revealed)
  assert hidden == set(range(6, 11))  # hello revealed; world still hidden


def test_document_read_ahead_mode():
  assert document_read_ahead_mode(False, READ_AHEAD_LEVEL_NORMAL) == READ_AHEAD_OFF
  assert document_read_ahead_mode(True, READ_AHEAD_LEVEL_NORMAL) == READ_AHEAD_NORMAL
  assert document_read_ahead_mode(True, READ_AHEAD_LEVEL_HARD) == READ_AHEAD_HARD
  assert document_read_ahead_mode(True, READ_AHEAD_LEVEL_EASY) == READ_AHEAD_EASY
