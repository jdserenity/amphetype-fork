"""Tests for RunStats / timingtuple."""

import pytest

from typing_program.timingtuple import RunStats, collect_focus_drill_stat_rows, collect_run_stat_rows


def test_timed_words_includes_short_words():
  run = RunStats.make('the of us')
  words = [w.text for w in run.timed_words(complete=False)]
  assert 'the' in words
  assert 'of' in words
  assert 'us' in words


def test_run_stats_pause_excludes_idle_time(monkeypatch):
  # First key at 0, pause at 1, resume after 60s idle at 61, second key immediately.
  times = [0.0, 1.0, 61.0, 61.0]
  monkeypatch.setattr('typing_program.timingtuple.timer', lambda: times.pop(0) if times else 61.0)

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
  from typing_program.typer import LessonDocument
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


def _make_typed_run(text, spc=0.1):
  run = RunStats.make(text, started=1000.0)
  t = 1000.0; last = None
  for i in range(len(text)):
    run[i].visit(True, last, t)
    last = t; t += spc
    run[i].last = t
  run.index = len(text)
  return run


def test_collect_focus_drill_stat_rows_one_row_per_word():
  run = _make_typed_run('slow slow slow fast fast')
  rows = collect_focus_drill_stat_rows(
    run, run.median_timing, 99.0, [('word', 'slow'), ('word', 'fast')])
  assert len(rows) == 2
  by_word = {data: (t, m, tp) for t, _vis, _w, m, tp, data in rows}
  assert set(by_word) == {'slow', 'fast'}
  assert by_word['slow'][2] == 2
  assert by_word['fast'][2] == 2


def test_collect_focus_drill_stat_rows_median_across_reps():
  run = RunStats.make('aaa', started=1000.0)
  spcs = [0.10, 0.20, 0.30]
  t = 1000.0; last = None
  for i, spc in enumerate(spcs):
    run[i].visit(True, last, t)
    last = t; t += spc
    run[i].last = t
  run.index = 3
  rows = collect_focus_drill_stat_rows(run, run.median_timing, 1.0, [('word', 'aaa')])
  assert len(rows) == 1
  assert rows[0][0] == pytest.approx(0.20)


def test_collect_focus_drill_stat_rows_ignores_non_targets():
  run = _make_typed_run('only')
  rows = collect_focus_drill_stat_rows(run, run.median_timing, 1.0, [('word', 'other')])
  assert rows == []
