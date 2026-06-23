"""Tests for consolidated Performance Analysis tab."""

import re

import pytest

from amphetype.Performance import perf_hist_cutoff, PerformanceHistory
from amphetype.PerformanceAnalysis import PerformanceAnalysis
from amphetype.StatWidgets import StringStats, WordModel


def test_perf_hist_cutoff():
  now = 1_000_000.0
  assert perf_hist_cutoff(now=now, history_days=30) == now - 30 * 86400.0


def test_performance_history_sql_uses_history_window(qapp, monkeypatch):
  captured = []

  def fake_fetchall(sql, *args):
    captured.append(sql)
    return []

  monkeypatch.setattr('amphetype.Performance.DB.fetchall', fake_fetchall)
  ph = PerformanceHistory()
  captured.clear()
  ph.updateData()
  result_sql = [s for s in captured if 'from result' in s]
  assert result_sql
  m = re.search(r'r\.w >= ([\d.]+)', result_sql[0])
  assert m
  cutoff = float(m.group(1))
  assert cutoff == pytest.approx(perf_hist_cutoff(), abs=1.0)


def test_performance_analysis_composes_sections(qapp):
  pa = PerformanceAnalysis()
  assert isinstance(pa.ph, PerformanceHistory)
  assert isinstance(pa.st, StringStats)


def test_performance_analysis_unique_typed_labels(qapp, monkeypatch):
  monkeypatch.setattr(
    'amphetype.PerformanceAnalysis.count_unique_typed',
    lambda db, hist, tp: 42 if tp == 2 else 17)
  pa = PerformanceAnalysis()
  pa.updateAll()
  assert pa._words_lbl.text() == 'Unique words typed: 42'
  assert pa._trigrams_lbl.text() == 'Unique trigrams typed: 17'


def test_performance_analysis_has_stats_and_progress_subtabs(qapp):
  pa = PerformanceAnalysis()
  labels = [pa.subtabs.tabText(i) for i in range(pa.subtabs.count())]
  assert labels == ["Stats", "Progress"]
  assert pa.subtabs.currentIndex() == 0
  assert pa.subtabs.widget(0) is pa.st
  assert pa.subtabs.widget(1) is pa.ph


def test_string_stats_has_no_lesson_generator_button(qapp):
  from PyQt5.QtWidgets import QPushButton
  st = StringStats()
  texts = [b.text() for b in st.findChildren(QPushButton)]
  assert 'Send List to Lesson Generator' not in texts
  assert 'Update List' not in texts
  assert 'Drill worst 3' not in texts
  assert 'Drill 3 oblivion' not in texts
  assert not hasattr(st, 'lessonStrings')


def test_word_model_init(qapp):
  m = WordModel()
  assert m._words_mode is False
  assert 'Improved' not in m.head
  m.set_words_mode(True)
  assert 'Improved' in m.head


def test_string_stats_most_improved_sort(qapp, monkeypatch):
  st = StringStats()
  pool_rows = [
    ('slow', 50.0, 80.0, 90.0, 100.0, 10, 0, 0, 500.0),
    ('fast', 80.0, 95.0, 98.0, 100.0, 10, 0, 0, 500.0),
  ]

  def fake_get(key):
    return {
      'ana_which': 'improved desc',
      'ana_many': 2,
      'ana_what': 2,
      'ana_count': 1,
      'history': 365,
    }.get(key, 0)

  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', fake_get)
  monkeypatch.setattr('amphetype.StatWidgets.DB.fetchall', lambda sql, args: pool_rows)
  monkeypatch.setattr(
    'amphetype.StatWidgets.fetch_first_sample_wpm',
    lambda db, tp, keys: {'slow': 30.0, 'fast': 70.0})
  st.update()
  assert [r[0] for r in st.model.words] == ['slow', 'fast']
  assert st.model.words[0][2] == 20
  assert st.model.words[1][2] == 10


def test_analysis_sort_combo_hides_most_improved_for_keys(qapp, monkeypatch):
  from amphetype.StatWidgets import AnalysisSortCombo

  store = {'ana_what': 0, 'ana_which': 'improved desc'}

  def fake_get(key):
    return store.get(key, 0)

  def fake_set(k, v):
    store[k] = v

  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', fake_get)
  monkeypatch.setattr('amphetype.StatWidgets.Settings.set', fake_set)
  combo = AnalysisSortCombo()
  assert store['ana_which'] == 'damage desc'
  assert 'most improved' not in [combo.itemText(i) for i in range(combo.count())]


def test_analysis_sort_combo_shows_most_improved_for_words(qapp, monkeypatch):
  from amphetype.StatWidgets import AnalysisSortCombo

  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', lambda k: {'ana_what': 2, 'ana_which': 'improved desc'}.get(k, 0))
  combo = AnalysisSortCombo()
  assert 'most improved' in [combo.itemText(i) for i in range(combo.count())]
  assert combo._keys[-1] == 'improved desc'


def test_main_window_has_performance_analysis_tab(qapp):
  from amphetype.Amphetype import AmphetypeWindow
  w = AmphetypeWindow()
  tabs = w.centralWidget()
  labels = [tabs.tabText(i) for i in range(tabs.count())]
  assert labels == ["Typer", "Performance Analysis", "Preferences"]
