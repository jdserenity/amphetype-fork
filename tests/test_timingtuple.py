"""Tests for RunStats / timingtuple."""

from amphetype.timingtuple import RunStats, collect_run_stat_rows


def test_timed_words_includes_short_words():
  run = RunStats.make('the of us')
  words = [w.text for w in run.timed_words(complete=False)]
  assert 'the' in words
  assert 'of' in words
  assert 'us' in words


def test_three_letter_words_saved_as_word_type_not_trigram(qapp):
  from PyQt5.QtGui import QFont
  from amphetype.typer import LessonDocument
  doc = LessonDocument(QFont('Arial', 12))
  doc.set_text('the of ')
  for ch in 'the of ':
    doc.insert(ch)
  run = doc._run
  rows = collect_run_stat_rows(run, run.median_timing, 1.0, 1)
  by_type = {(r[6], r[5]) for r in rows}
  assert ('the', 2) in by_type
  assert ('of', 2) in by_type
  assert ('the', 1) in by_type
