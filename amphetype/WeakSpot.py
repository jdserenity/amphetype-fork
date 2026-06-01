
import time
from collections import deque

from amphetype.Data import DB
from amphetype.Config import Settings
from amphetype.QtUtil import *
from amphetype.WeakSpotLessons import build_lesson_from_db, fetch_db_marker, lesson_cache_valid

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


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
    from amphetype.Data import AmphDatabase
    conn = sqlite3.connect(Settings.get('db_name'), 5, 0, "DEFERRED", False, AmphDatabase)
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


class WeakSpotWidget(QWidget):
  startLesson = pyqtSignal(str)
  gotoTyper = pyqtSignal()

  def __init__(self, *args):
    super(WeakSpotWidget, self).__init__(*args)
    self._lesson = ''
    self._worker = None
    self._cache = None  # (lesson text, db_marker)
    self._gen_marker = None
    self._recent = deque(maxlen=2)  # sets of emphasized keys from recent lessons
    self.preview = QTextEdit()
    self.preview.setWordWrapMode(QTextOption.WordWrap)
    self.preview.setAcceptRichText(False)
    self.preview.setReadOnly(True)
    self.status = QLabel('')

    self.setLayout(AmphBoxLayout([
      ["Weakspot lessons are built automatically from your slowest characters, trigrams, and words."],
      ["Reuses the current lesson until you type it or your stats change.", None],
      10,
      ["Lesson preview:", (self.preview, 1)],
      [self.status, None,
        AmphButton("New lesson", lambda: self.regenerate(force=True)),
        AmphButton("Start typing", self.startTyping)],
    ]))

    Settings.signal_for('history').connect(self._on_settings)
    Settings.signal_for('min_chars').connect(self._on_settings)
    Settings.signal_for('max_chars').connect(self._on_settings)

  def _db_marker(self):
    return fetch_db_marker(DB)

  def _show_lesson(self, lesson):
    self._lesson = lesson
    self.preview.setPlainText(lesson or '(No statistics yet — type some texts first, then come back.)')
    n = len(lesson.split()) if lesson else 0
    self.status.setText(f'{len(lesson)} chars, {n} words' if lesson else '')

  def _on_settings(self, *args):
    if self.isVisible():
      self.regenerate(force=True)

  def on_stats_changed(self):
    if self._cache and self._db_marker() != self._cache[1]:
      self._cache = None
      if self.isVisible() and not (self._worker and self._worker.isRunning()):
        self.regenerate()

  def showEvent(self, event):
    super(WeakSpotWidget, self).showEvent(event)
    self.regenerate()

  def _wordlist_path(self):
    return str(Settings.DATA_DIR / 'wordlists' / 'words-20.txt')

  def regenerate(self, force=False):
    if self._worker and self._worker.isRunning():
      return
    if not force and lesson_cache_valid(self._cache, self._db_marker()):
      self._show_lesson(self._cache[0])
      return
    self._gen_marker = self._db_marker()
    self.preview.setPlainText('Generating lesson…')
    self.status.setText('')
    hist = time.time() - Settings.get('history') * 86400.0
    recent = set().union(*self._recent) if self._recent else set()
    self._worker = _LessonWorker(
      hist, Settings.get('ana_count'), Settings.get('ana_many'),
      Settings.get('min_chars'), Settings.get('max_chars'), self._wordlist_path(), recent)
    self._worker.done.connect(self._on_lesson)
    self._worker.start()

  def _on_lesson(self, lesson, emphasized):
    self._cache = (lesson, self._gen_marker)
    if emphasized:
      self._recent.append(set(emphasized))
    self._show_lesson(lesson)

  def startTyping(self):
    if self._worker and self._worker.isRunning():
      return
    if not self._lesson:
      QMessageBox.information(self, "No lesson", "Nothing to type yet. Import a book and practice a bit first.")
      return
    self.startLesson.emit(self._lesson)
    self.gotoTyper.emit()
