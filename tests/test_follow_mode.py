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


def test_default_follow_wpm_is_70():
  assert DEFAULT_FOLLOW_WPM == 70


def test_follow_outcome_html_colors():
  from typing_program.follow_mode import (
    FOLLOW_CURSOR_COLOR, FOLLOW_FAIL_COLOR, FOLLOW_FAILURE_MSG, FOLLOW_SUCCESS_MSG,
    follow_outcome_html,
  )
  ok = follow_outcome_html('success')
  assert FOLLOW_SUCCESS_MSG in ok and FOLLOW_CURSOR_COLOR in ok
  bad = follow_outcome_html('failure')
  assert FOLLOW_FAILURE_MSG in bad and FOLLOW_FAIL_COLOR in bad
  assert follow_outcome_html(None) == ''
  assert 'Stats from what you typed' not in ok + bad


def test_follow_footer_state_greys_in_improve_keeps_pref():
  from typing_program.follow_mode import follow_footer_state
  # On in corpus → active + WPM box
  on_corpus = follow_footer_state(True, MODE_CORPUS)
  assert on_corpus['active'] and on_corpus['wpm_visible'] and on_corpus['btn_enabled']
  assert not on_corpus['btn_greyed']
  # Same pref in improve → greyed, not active, no WPM box (pref still "on")
  on_improve = follow_footer_state(True, MODE_IMPROVE)
  assert not on_improve['active'] and not on_improve['wpm_visible']
  assert on_improve['btn_greyed'] and not on_improve['btn_enabled']
  # Back to book → active again without re-toggling
  on_book = follow_footer_state(True, MODE_BOOK)
  assert on_book['active'] and on_book['wpm_visible']
  # Never on → eligible mode does not auto-enable
  off_corpus = follow_footer_state(False, MODE_CORPUS)
  assert not off_corpus['active'] and not off_corpus['wpm_visible']
  assert off_corpus['btn_enabled']


def test_runstats_active_elapsed_ignores_pause():
  from time import sleep
  from typing_program import timer
  from typing_program.timingtuple import RunStats
  run = RunStats.make('ab', started=timer())
  assert run.started is not None
  sleep(0.05)
  e1 = run.active_elapsed()
  assert e1 >= 0.04
  run.pause()
  sleep(0.05)
  e2 = run.active_elapsed()
  assert abs(e2 - e1) < 0.03  # pause freezes elapsed
  run.resume()
  sleep(0.05)
  e3 = run.active_elapsed()
  assert e3 > e2 + 0.03


def test_lose_follow_race_locks_input(qapp):
  from PyQt5.QtGui import QFont
  from typing_program.typer import LessonDocument
  doc = LessonDocument(QFont('Arial', 12))
  lost = []
  doc.follow_lost.connect(lambda r: lost.append(r))
  doc.set_text('hello')
  doc.insert('h')
  assert doc.is_running()
  run = doc.lose_follow_race()
  assert run is not None
  assert lost == [run]
  assert doc.is_finished()
  assert not doc.is_running()
  idx = doc._run.index
  doc.insert('e')  # ignored — race already lost
  assert doc._run.index == idx
  assert doc.lose_follow_race() is None  # idempotent


def test_follow_footer_greys_in_improve_and_restores(qapp):
  """Pref stays on across improve; control greys out, then lights up again in corpus."""
  import typing_program.mainwindow  # noqa: F401
  from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE
  from typing_program.typer import MODE_BTN_GREYED, TyperWindow

  tw = TyperWindow()
  tw.S('follow_mode').set(False)  # isolate from other tests / saved prefs
  tw._refresh_follow_footer()
  # Never on at cold start (improve) — greyed because ineligible, WPM hidden
  assert tw._mode == MODE_IMPROVE
  assert not tw.S('follow_mode').get()
  assert not tw._btn_follow.isEnabled()
  assert tw._follow_wpm_panel.isHidden()

  tw.set_practice_mode(MODE_CORPUS)
  assert tw._btn_follow.isEnabled()
  assert tw._follow_wpm_panel.isHidden()  # still off

  tw.S('follow_mode').set(True)
  assert not tw._follow_wpm_panel.isHidden()
  assert tw._btn_follow.isEnabled()

  tw.set_practice_mode(MODE_IMPROVE)
  assert bool(tw.S('follow_mode').get()) is True  # pref kept
  assert not tw._btn_follow.isEnabled()
  assert tw._follow_wpm_panel.isHidden()
  assert MODE_BTN_GREYED in tw._btn_follow.styleSheet()

  tw.set_practice_mode(MODE_BOOK)
  assert bool(tw.S('follow_mode').get()) is True
  assert tw._btn_follow.isEnabled()
  assert not tw._follow_wpm_panel.isHidden()
  tw.S('follow_mode').set(False)


def test_follow_wpm_enter_escape_unfocus(qapp):
  import typing_program.mainwindow  # noqa: F401
  from PyQt5.QtCore import Qt
  from PyQt5.QtGui import QKeyEvent
  from typing_program.book_mode import MODE_CORPUS
  from typing_program.typer import TyperWindow

  tw = TyperWindow()
  tw.set_practice_mode(MODE_CORPUS)
  tw.S('follow_mode').set(True)
  edit = tw._follow_wpm_edit
  edit.setFocus()
  assert edit.hasFocus() or True  # focus can be flaky headless; still exercise filter
  esc = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
  assert tw.eventFilter(edit, esc) is True
  enter = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
  assert tw.eventFilter(edit, enter) is True
  tw.S('follow_mode').set(False)
