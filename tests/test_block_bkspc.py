"""Tests for Block ⌫ mode (block_bkspc): plain Backspace blocked; stats preserved."""

import pytest

from typing_program.block_bkspc import allows_backspace
from typing_program.typer import LessonDocument
from typing_program.timingtuple import collect_run_stat_rows
from PyQt5.QtGui import QFont, QColor


def test_allows_backspace_when_mode_off():
  assert allows_backspace(False, by_word=False) is True
  assert allows_backspace(False, by_word=True) is True


def test_blocks_char_backspace_when_mode_on():
  assert allows_backspace(True, by_word=False) is False


def test_allows_word_backspace_when_mode_on():
  assert allows_backspace(True, by_word=True) is True


class _FakeTyperSettings:
  def __init__(self, **vals):
    self._vals = vals
    self._vals.setdefault('require_space', False)
    self._vals.setdefault('lenient_mode', False)
    self._vals.setdefault('overwrite_mode', True)
    self._vals.setdefault('limit_backspace', False)
    self._vals.setdefault('show_progress', False)
    self._vals.setdefault('background_color', QColor('white'))
    self._vals.setdefault('typing_sound', '')
    self._vals.setdefault('typing_error_sound', '')
    self._vals.setdefault('typing_sound_volume', 50)
    self._vals.setdefault('word_delete_enabled', True)

  def __getitem__(self, k):
    return self._vals[k]

  def __call__(self, name):
    outer = self
    class _V:
      def bind_value(self, f, call=True):
        if call:
          f(outer._vals.get(name))
      def bind_change(self, f, call=True):
        if call:
          f()
      def set(self, v):
        outer._vals[name] = v
      def get(self):
        return outer._vals.get(name)
    return _V()

  def get(self, k, default=None):
    return self._vals.get(k, default)


def test_widget_backspace_blocked_for_char_when_mode_on(qapp):
  from typing_program.typer import TyperWidget

  w = TyperWidget(_FakeTyperSettings(word_delete_enabled=True))
  doc = LessonDocument(QFont('Arial', 12))
  doc.set_text('hello')
  w.setLesson(doc)
  doc.insert('h')
  doc.insert('x')  # error on 'e'; cursor advances in overwrite
  idx_before = doc._run.index
  w.backspace(word=False)
  assert doc._run.index == idx_before  # char backspace blocked


def test_widget_word_backspace_still_works_when_mode_on(qapp):
  from typing_program.typer import TyperWidget

  w = TyperWidget(_FakeTyperSettings(word_delete_enabled=True))
  doc = LessonDocument(QFont('Arial', 12))
  doc.set_text('hello world')
  w.setLesson(doc)
  for ch in 'hello wo':
    doc.insert(ch)
  idx_before = doc._run.index
  assert idx_before > 0
  w.backspace(word=True)
  assert doc._run.index < idx_before


def test_widget_char_backspace_works_when_mode_off(qapp):
  from typing_program.typer import TyperWidget

  w = TyperWidget(_FakeTyperSettings(word_delete_enabled=False))
  doc = LessonDocument(QFont('Arial', 12))
  doc.set_text('hello')
  w.setLesson(doc)
  doc.insert('h')
  doc.insert('x')
  w.backspace(word=False)
  assert doc._run.index == 1


def test_by_word_backspace_then_retype_counts_occurrence_once_with_mistakes(qapp):
  """Occurrence retyped after by-word backspace: one sample; mistakes kept."""
  doc = LessonDocument(QFont('Arial', 12))
  doc.set_text('cat dog')
  # First attempt at "cat": mistype then correct via char backspace (document API, free)
  doc.insert('c')
  doc.insert('x')  # mistake on 'a'
  doc.backspace(by_word=False)
  doc.insert('a')
  doc.insert('t')
  doc.insert(' ')
  assert doc._run[1].mistakes >= 1
  idx_after_cat = doc._run.index
  assert idx_after_cat == 4

  # By-word backspace of "cat " (PreviousWord from after the space)
  doc.backspace(by_word=True)
  assert doc._run.index < idx_after_cat

  # Retype "cat " and finish "dog"
  while doc._run.index < 4:
    expected = 'cat '[doc._run.index]
    doc.insert(expected)
  for ch in 'dog':
    doc.insert(ch)

  run = doc._run
  assert run.is_complete()
  rows = collect_run_stat_rows(run, run.median_timing, 1.0, 1)
  word_rows = [r for r in rows if r[5] == 2 and r[6] == 'cat']
  assert len(word_rows) == 1
  assert word_rows[0][3] == 1  # one completion of this occurrence in the run
  assert run[1].mistakes >= 1  # mistake from first attempt still on the char
  assert word_rows[0][4] >= 1  # flawed sample (mistakes field)
