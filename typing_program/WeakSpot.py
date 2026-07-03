
import time
from collections import deque

from typing_program.Data import DB
from typing_program.Config import Settings
from typing_program.WeakSpotLessons import build_lesson_from_db, fetch_db_marker, lesson_cache_valid

from PyQt5.QtCore import *


class _LessonWorker(QThread):
  done = pyqtSignal(str, 'PyQt_PyObject')

  def __init__(self, hist, min_count, per_type, min_chars, max_chars, wordlist_path, recent):
    super(_LessonWorker, self).__init__()
    self.hist = hist
    self.min_count = min_count
    self.per_type = per_type
    self.min_chars = min_chars
    self.max_chars = max_chars
    self.wordlist_path = wordlist_path
    self.recent = recent

  def run(self):
    import sqlite3
    from typing_program.Data import AppDatabase
    conn = sqlite3.connect(Settings.get('db_name'), 5, 0, "DEFERRED", False, AppDatabase)
    try:
      lesson, emphasized = build_lesson_from_db(
        conn,
        hist=self.hist,
        min_count=self.min_count,
        per_type=self.per_type,
        min_chars=self.min_chars,
        max_chars=self.max_chars,
        wordlist_path=self.wordlist_path,
        recent=self.recent,
      )
    finally:
      conn.close()
    self.done.emit(lesson, emphasized)


class WeakSpotLessonBuilder(QObject):
  """Build weakspot lessons on a background thread; cache until stats change or forced."""

  lessonReady = pyqtSignal(str)
  busyChanged = pyqtSignal(bool)

  def __init__(self, parent=None):
    super(WeakSpotLessonBuilder, self).__init__(parent)
    self._worker = None
    self._cache = None  # (lesson text, db_marker)
    self._gen_marker = None
    self._recent = deque(maxlen=2)

    Settings.signal_for('history').connect(lambda *a: self.invalidate_cache())
    Settings.signal_for('min_chars').connect(lambda *a: self.invalidate_cache())
    Settings.signal_for('max_chars').connect(lambda *a: self.invalidate_cache())

  def invalidate_cache(self):
    self._cache = None

  def _db_marker(self):
    return fetch_db_marker(DB)

  def _wordlist_path(self):
    return str(Settings.DATA_DIR / 'wordlists' / 'words-20.txt')

  def on_stats_changed(self):
    if self._cache and self._db_marker() != self._cache[1]:
      self._cache = None

  def request_next_lesson(self, force=False):
    self.regenerate(force=force)

  def regenerate(self, force=False):
    if self._worker and self._worker.isRunning():
      return
    if not force and lesson_cache_valid(self._cache, self._db_marker()):
      self.lessonReady.emit(self._cache[0])
      return
    self._gen_marker = self._db_marker()
    self.busyChanged.emit(True)
    hist = time.time() - Settings.get('history') * 86400.0
    recent = set().union(*self._recent) if self._recent else set()
    self._worker = _LessonWorker(
      hist, Settings.get('ana_count'), Settings.get('ana_many'),
      Settings.get('min_chars'), Settings.get('max_chars'), self._wordlist_path(), recent)
    self._worker.done.connect(self._on_lesson)
    self._worker.start()

  def _on_lesson(self, lesson, emphasized):
    self.busyChanged.emit(False)
    self._cache = (lesson, self._gen_marker)
    if emphasized:
      self._recent.append(set(emphasized))
    self.lessonReady.emit(lesson or '')
