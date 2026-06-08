"""Tests for consolidated Performance Analysis tab."""

import re

import pytest

from amphetype.Performance import perf_hist_cutoff, PerformanceHistory
from amphetype.PerformanceAnalysis import PerformanceAnalysis
from amphetype.StatWidgets import StringStats


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
  assert not hasattr(st, 'lessonStrings')


def test_main_window_has_performance_analysis_tab(qapp):
  from amphetype.Amphetype import AmphetypeWindow
  w = AmphetypeWindow()
  tabs = w.centralWidget()
  labels = [tabs.tabText(i) for i in range(tabs.count())]
  assert labels == ["Typer", "Performance Analysis", "Preferences"]
