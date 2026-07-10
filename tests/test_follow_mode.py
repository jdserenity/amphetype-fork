"""Tests for follow mode: eligibility, WPM parsing, race math."""

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
from typing_program.follow_mode import (
  DEFAULT_FOLLOW_WPM, MAX_FOLLOW_WPM, MIN_FOLLOW_WPM,
  chars_per_second, clamp_follow_wpm, follow_active, follow_eligible,
  follow_index, follow_race_result, follow_reached_end, parse_follow_wpm,
)


def test_follow_eligible_corpus_and_book_only():
  assert follow_eligible(MODE_CORPUS) is True
  assert follow_eligible(MODE_BOOK) is True
  assert follow_eligible(MODE_IMPROVE) is False


def test_follow_active_requires_pref_and_eligible_mode():
  assert follow_active(True, MODE_CORPUS) is True
  assert follow_active(True, MODE_BOOK) is True
  assert follow_active(True, MODE_IMPROVE) is False
  assert follow_active(False, MODE_CORPUS) is False
  assert follow_active(False, MODE_IMPROVE) is False


def test_clamp_follow_wpm_bounds():
  assert clamp_follow_wpm(0) == MIN_FOLLOW_WPM
  assert clamp_follow_wpm(-5) == MIN_FOLLOW_WPM
  assert clamp_follow_wpm(9999) == MAX_FOLLOW_WPM
  assert clamp_follow_wpm(60) == 60
  assert clamp_follow_wpm('nope') == DEFAULT_FOLLOW_WPM


def test_parse_follow_wpm_live_box():
  assert parse_follow_wpm('45') == 45
  assert parse_follow_wpm('  50  ') == 50
  assert parse_follow_wpm('') == DEFAULT_FOLLOW_WPM
  assert parse_follow_wpm('abc') == DEFAULT_FOLLOW_WPM
  assert parse_follow_wpm('0') == MIN_FOLLOW_WPM


def test_chars_per_second_standard_five_char_word():
  # 60 WPM → 60*5/60 = 5 chars/sec
  assert chars_per_second(60) == 5.0
  assert chars_per_second(120) == 10.0


def test_follow_index_advances_with_time():
  # 60 WPM → 5 chars/sec; after 2s → index 10
  assert follow_index(0, 60, 100) == 0
  assert follow_index(2.0, 60, 100) == 10
  assert follow_index(100.0, 60, 100) == 100  # capped at end


def test_follow_reached_end():
  assert follow_reached_end(0, 60, 10) is False
  assert follow_reached_end(1.0, 60, 10) is False  # 5 chars
  assert follow_reached_end(2.0, 60, 10) is True   # 10 chars
  assert follow_reached_end(1.0, 60, 0) is False


def test_follow_race_result_success_failure_tie():
  assert follow_race_result(False, False) is None
  assert follow_race_result(True, False) == 'success'
  assert follow_race_result(False, True) == 'failure'
  assert follow_race_result(True, True) == 'success'  # tie → typist
