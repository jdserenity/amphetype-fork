"""Tests for Performance Analysis tab."""

import pytest

from amphetype.PerformanceAnalysis import PerformanceAnalysis
from amphetype.StatWidgets import StringStats, WordModel, AnalysisSortCombo, AnalysisCountEdit
from amphetype.stats_query import STAT_TYPE_WORD


def _sample_rows():
  return [
    ['alpha', 80.0, 1.0, 10, 10, 0, 50.0],
    ['beta', 70.0, 1.0, 8, 8, 0, 40.0],
    ['gamma', 60.0, 1.0, 6, 6, 0, 30.0],
  ]


def test_performance_analysis_has_no_history_window(qapp):
  from PyQt5.QtWidgets import QLabel
  pa = PerformanceAnalysis()
  header_texts = [lbl.text() for lbl in pa.findChildren(QLabel) if not pa.st.isAncestorOf(lbl)]
  assert 'Last' not in header_texts
  assert 'days.' not in header_texts


def test_performance_analysis_composes_sections(qapp):
  pa = PerformanceAnalysis()
  assert isinstance(pa.st, StringStats)


def test_performance_analysis_unique_typed_labels(qapp, monkeypatch):
  monkeypatch.setattr(
    'amphetype.PerformanceAnalysis.count_analysis_words',
    lambda db, hist: 42)
  monkeypatch.setattr(
    'amphetype.PerformanceAnalysis.aggregate_session_wpm_from_results',
    lambda db, hist: 74.5)
  pa = PerformanceAnalysis()
  pa.updateAll()
  assert pa._words_lbl.text() == 'Unique common words typed: 42'
  assert pa._wpm_lbl.text() == 'Avg WPM: 74.5'


def test_performance_analysis_refreshes_on_tab_select(qapp, monkeypatch):
  from amphetype.Amphetype import AmphetypeWindow
  calls = []
  monkeypatch.setattr(
    'amphetype.PerformanceAnalysis.PerformanceAnalysis.updateAll',
    lambda self, *a: calls.append(1))
  w = AmphetypeWindow()
  tabs = w.centralWidget()
  perf_idx = tabs.indexOf(tabs.widget(1))
  tabs.setCurrentIndex(0)
  calls.clear()
  tabs.setCurrentIndex(perf_idx)
  assert len(calls) >= 1


def test_performance_analysis_avg_wpm_shows_dash_when_no_data(qapp, monkeypatch):
  monkeypatch.setattr('amphetype.PerformanceAnalysis.count_analysis_words', lambda *a: 0)
  monkeypatch.setattr(
    'amphetype.PerformanceAnalysis.aggregate_session_wpm_from_results',
    lambda db, hist: None)
  pa = PerformanceAnalysis()
  pa.updateAll()
  assert pa._wpm_lbl.text() == 'Avg WPM: —'


def test_performance_analysis_is_stats_only(qapp):
  pa = PerformanceAnalysis()
  assert pa.st is not None
  assert not hasattr(pa, 'subtabs')
  assert not hasattr(pa, 'ph')


def test_string_stats_search_on_toolbar_row(qapp):
  st = StringStats()
  # Search shares the Show / sorted-by row (four rows total, not five).
  assert st.layout().count() == 4


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
    ('slow', 50.0, 90.0, 100.0, 90, 0, 500.0),
    ('fast', 80.0, 95.0, 100.0, 100, 0, 500.0),
  ]

  def fake_get(key):
    return {
      'analysis_which': 'improved desc',
      'analysis_many': 2,
      'analysis_what': 2,
      'analysis_count': 1,
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


def test_string_stats_improved_blank_when_count_is_one(qapp, monkeypatch):
  st = StringStats()
  pool_rows = [
    ('once', 50.0, 80.0, 1.0, 1, 0, 50.0),
  ]

  def fake_get(key):
    return {
      'analysis_which': 'wpm asc',
      'analysis_many': 10,
      'analysis_what': 2,
      'analysis_count': 1,
    }.get(key, 0)

  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', fake_get)
  monkeypatch.setattr('amphetype.StatWidgets.DB.fetchall', lambda sql, args: pool_rows)
  monkeypatch.setattr(
    'amphetype.StatWidgets.fetch_first_sample_wpm',
    lambda db, tp, keys: {'once': 30.0})
  st.update()
  assert st.model.words[0][2] is None


def test_analysis_count_edit_clamps_to_two(qapp, monkeypatch):
  store = {'analysis_count': 1}

  def fake_get(key):
    return store.get(key, 0)

  def fake_set(key, val):
    store[key] = val

  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', fake_get)
  monkeypatch.setattr('amphetype.StatWidgets.Settings.set', fake_set)
  edit = AnalysisCountEdit()
  assert store['analysis_count'] == 2
  edit.setText('1')
  edit.updateVal()
  assert store['analysis_count'] == 2
  edit.setText('3')
  edit.updateVal()
  assert store['analysis_count'] == 3


def test_main_window_title(qapp):
  from amphetype.Amphetype import AmphetypeWindow
  w = AmphetypeWindow()
  assert w.windowTitle() == 'Typing Program That Helps You Type Better'


def test_analysis_sort_combo_hides_most_improved_for_keys(qapp, monkeypatch):
  store = {'analysis_what': 0, 'analysis_which': 'improved desc'}

  def fake_get(key):
    return store.get(key, 0)

  def fake_set(k, v):
    store[k] = v

  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', fake_get)
  monkeypatch.setattr('amphetype.StatWidgets.Settings.set', fake_set)
  combo = AnalysisSortCombo()
  assert store['analysis_which'] == 'damage desc'
  assert 'most improved' not in [combo.itemText(i) for i in range(combo.count())]


def test_analysis_sort_combo_shows_most_improved_for_words(qapp, monkeypatch):
  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', lambda k: {'analysis_what': 2, 'analysis_which': 'improved desc'}.get(k, 0))
  combo = AnalysisSortCombo()
  assert 'most improved' in [combo.itemText(i) for i in range(combo.count())]
  assert combo._keys[-1] == 'improved desc'


def test_main_window_has_performance_analysis_tab(qapp):
  from amphetype.Amphetype import AmphetypeWindow
  w = AmphetypeWindow()
  tabs = w.centralWidget()
  labels = [tabs.tabText(i) for i in range(tabs.count())]
  assert labels == ["Typer", "Performance Analysis", "Preferences"]


def test_string_stats_search_shows_all_matches(qapp, monkeypatch):
  st = StringStats()
  monkeypatch.setattr(st, '_query_rows', lambda *a: (_sample_rows(), 2))
  monkeypatch.setattr(
    'amphetype.StatWidgets.fetch_analysis_search',
    lambda *a: [['alpha', 80.0, 1.0, 10, 10, 0, 50.0]])
  st.update()
  st._search_edit.setText('alp')
  st._apply_search()
  assert st._search_btn.text() == 'Clear'
  assert [r[0] for r in st.model.words] == ['alpha']


def test_string_stats_clear_search_restores_baseline(qapp, monkeypatch):
  st = StringStats()
  monkeypatch.setattr(st, '_query_rows', lambda *a: (_sample_rows(), 2))
  monkeypatch.setattr(
    'amphetype.StatWidgets.fetch_analysis_search',
    lambda *a: [['beta', 70.0, 1.0, 8, 8, 0, 40.0]])
  st.update()
  st._search_edit.setText('bet')
  st._apply_search()
  st.clear_search()
  assert st._search_btn.text() == 'Search'
  assert [r[0] for r in st.model.words] == ['alpha', 'beta', 'gamma']


def test_string_stats_search_btn_returns_to_search_when_term_edited(qapp, monkeypatch):
  st = StringStats()
  monkeypatch.setattr(st, '_query_rows', lambda *a: (_sample_rows(), 2))
  monkeypatch.setattr(
    'amphetype.StatWidgets.fetch_analysis_search',
    lambda *a: [['alpha', 80.0, 1.0, 10, 10, 0, 50.0]])
  st.update()
  st._search_edit.setText('alpha')
  st._apply_search()
  st._search_edit.setText('alph')
  assert st._search_btn.text() == 'Search'


def test_string_stats_double_click_opens_menu(qapp, monkeypatch):
  from PyQt5.QtCore import QModelIndex
  st = StringStats()
  st.model.setData(_sample_rows())
  calls = []
  monkeypatch.setattr(st, '_open_stats_menu', lambda idx, pos=None: calls.append(idx.row()))
  st._stats_double_click(st.model.index(0, 0, QModelIndex()))
  assert calls == [0]


def test_string_stats_delete_target_after_confirm(qapp, monkeypatch):
  from PyQt5.QtCore import QModelIndex
  from PyQt5.QtWidgets import QMessageBox
  st = StringStats()
  st.model.setData(_sample_rows())
  monkeypatch.setattr('amphetype.StatWidgets.Settings.get', lambda k: 2 if k == 'analysis_what' else 0)
  monkeypatch.setattr('amphetype.StatWidgets.QMessageBox.question', lambda *a: QMessageBox.Yes)
  deleted = []
  monkeypatch.setattr(
    'amphetype.StatWidgets.delete_stat_target',
    lambda db, tp, data: deleted.append((tp, data)) or 1)
  monkeypatch.setattr('amphetype.StatWidgets.DB.commit', lambda: None)
  monkeypatch.setattr(st, 'update', lambda *a: None)
  emitted = []
  st.statsChanged.connect(lambda: emitted.append(1))
  st._delete_target(st.model.index(0, 0, QModelIndex()))
  assert deleted == [(2, 'alpha')]
  assert emitted == [1]


def test_string_stats_delete_cancelled(qapp, monkeypatch):
  from PyQt5.QtCore import QModelIndex
  from PyQt5.QtWidgets import QMessageBox
  st = StringStats()
  st.model.setData(_sample_rows())
  monkeypatch.setattr('amphetype.StatWidgets.QMessageBox.question', lambda *a: QMessageBox.No)
  deleted = []
  monkeypatch.setattr('amphetype.StatWidgets.delete_stat_target', lambda *a: deleted.append(1))
  st._delete_target(st.model.index(0, 0, QModelIndex()))
  assert deleted == []
  assert len(st.model.words) == 3


def test_performance_analysis_hide_clears_stats_search(qapp, monkeypatch):
  from PyQt5.QtGui import QHideEvent
  pa = PerformanceAnalysis()
  monkeypatch.setattr(pa.st, '_query_rows', lambda *a: (_sample_rows(), STAT_TYPE_WORD))
  monkeypatch.setattr(
    'amphetype.StatWidgets.fetch_analysis_search',
    lambda *a: [['alpha', 80.0, 1.0, 10, 10, 0, 50.0]])
  pa.st.update()
  pa.st._search_edit.setText('alpha')
  pa.st._apply_search()
  pa.hideEvent(QHideEvent())
  assert pa.st._search_applied is None
  assert pa.st._search_btn.text() == 'Search'
