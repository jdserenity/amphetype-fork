"""Tests for RunStats / timingtuple."""

import pytest

from amphetype.timingtuple import RunStats, collect_run_stat_rows


def test_timed_words_includes_short_words():
  run = RunStats.make('the of us')
  words = [w.text for w in run.timed_words(complete=False)]
  assert 'the' in words
  assert 'of' in words
  assert 'us' in words


def test_run_stats_pause_excludes_idle_time(monkeypatch):
  # First key at 0, pause at 1, resume after 60s idle at 61, second key immediately.
  times = [0.0, 1.0, 61.0, 61.0]
  monkeypatch.setattr('amphetype.timingtuple.timer', lambda: times.pop(0) if times else 61.0)

  run = RunStats.make('ab', started=0.0)
  run.visit(True)
  run.advance(True)
  run.pause()
  run.resume()
  run.visit(True)
  run.advance(True)

  assert run[1].timing == pytest.approx(1.0)
  assert not run.is_paused()


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
