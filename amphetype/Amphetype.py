
from amphetype import *
import sys
import logging as log

# The order of the code and imports here is important (and a kludge).
# Due to being young and stupid I made the module files do weird
# initialization stuff on import, and some of them depend on each
# other.

# Init QT and set appname.
from PyQt5.QtWidgets import *
class AmphetypeApp(QApplication):
  def __init__(self, *args, **kwargs):
    super().__init__(sys.argv, *args, applicationName='amphetype', **kwargs)


app = AmphetypeApp()

# Import Config.py; this will do argument parsing and set up the
# global var "Settings".
from amphetype.Config import Settings
app.settings = Settings

# Only AFTER settings has been initialized, import database:
from amphetype.Data import DB
from amphetype.app_meta import PREFERENCES_TAB_KEY, get_app_meta_int, set_app_meta_int
app.DB = DB

# After this we can do whatever we want.

import os
from pathlib import Path
from amphetype.TextManager import TextManager
from amphetype.PerformanceAnalysis import PerformanceAnalysis
from amphetype.Config import GeneralOptions, TyperOptions
from amphetype.Lesson import LessonGenerator

from amphetype.typer import TyperWindow
from amphetype.session_timer import FocusedSessionTimer, SessionTimerLabel
from amphetype.QtUtil import center_widget_on_screen

from PyQt5.QtCore import *
from PyQt5.QtGui import *


class AmphetypeWindow(QMainWindow):
  def __init__(self, *args):
    super().__init__(*args)

    self.setWindowTitle('Typing Program That Helps You Type Better')

    self.quitSc = QShortcut(QKeySequence('Ctrl+Q'), self)
    self.quitSc.activated.connect(QApplication.instance().quit)
    
    tabs = QTabWidget()

    tw = TyperWindow()
    tabs.addTab(tw, "Typer")

    tm = TextManager()
    tm.gotoText.connect(lambda: tabs.setCurrentIndex(0))

    pa = PerformanceAnalysis()
    pa.gotoText.connect(lambda: tabs.setCurrentIndex(0))
    tabs.addTab(pa, "Performance Analysis")

    # LessonGenerator not shown as a tab; kept for auto_review (wantReview → newReview).
    lg = LessonGenerator()
    lg.newLessons.connect(lambda: tabs.setCurrentIndex(1))
    lg.newLessons.connect(tm.addTexts)
    lg.newReview.connect(tm.newReview)

    pa.setText.connect(tm.emit_text)
    pa.setText.connect(tw.setText)
    tm.setText.connect(tw.setText)
    tw.wantText.connect(tm.nextText)
    tw.needWeakspotLesson.connect(tm.newWeakspot)
    tw.wantReview.connect(lg.wantReview)
    tw.statsChanged.connect(pa.updateAll)
    pa.startDrill.connect(tw.start_focus_drill)
    pa.loadCorpusText.connect(tw.load_corpus_text)

    pw = QTabWidget()
    pw.addTab(GeneralOptions(), "General Options")
    pw.addTab(TyperOptions(), "Typer Options")
    pw.addTab(tm, "Sources")
    prefs_tab = get_app_meta_int(DB, PREFERENCES_TAB_KEY, 0)
    if 0 <= prefs_tab < pw.count():
      pw.setCurrentIndex(prefs_tab)
    pw.currentChanged.connect(lambda i: set_app_meta_int(DB, PREFERENCES_TAB_KEY, i))
    tabs.addTab(pw, "Preferences")

    def goto_sources():
      tabs.setCurrentWidget(pw)
      pw.setCurrentWidget(tm)
    lg.newLessons.connect(goto_sources)

    self._session_timer = FocusedSessionTimer()
    self._session_clock = SessionTimerLabel(self._session_timer, tabs)
    self._session_clock.start()
    self._session_clock.textChanged.connect(self._reposition_session_clock)
    tabs.installEventFilter(self)

    self.setCentralWidget(tabs)
    self._window_placed = False
    Settings.signal_for('show_session_timer').connect(lambda *_: self._apply_session_clock_visible())
    self._apply_session_clock_visible()
    if self.isActiveWindow():
      self._session_timer.resume()

    pm = Settings.get('practice_mode')
    if pm == 2:
      tm.nextText()
    elif pm == 1:
      tw._book.request_lesson(advance_chapter=False)

  def _apply_session_clock_visible(self):
    on = bool(Settings.get('show_session_timer'))
    self._session_clock.setVisible(on)
    if on:
      self._reposition_session_clock()

  def _reposition_session_clock(self):
    tabs = self.centralWidget()
    if tabs is None or not self._session_clock.isVisible():
      return
    y = tabs.tabBar().height() - 5
    self._session_clock.adjustSize()
    self._session_clock.move(tabs.width() - self._session_clock.width() - 2, y)
    self._session_clock.raise_()

  def eventFilter(self, obj, evt):
    if obj is self.centralWidget() and evt.type() in (QEvent.Resize, QEvent.Show):
      self._reposition_session_clock()
    return super().eventFilter(obj, evt)

  def showEvent(self, evt):
    super().showEvent(evt)
    if not self._window_placed:
      center_widget_on_screen(self)
      self._window_placed = True
    self._reposition_session_clock()

  def changeEvent(self, evt):
    if evt.type() == QEvent.ActivationChange:
      if self.isActiveWindow():
        self._session_timer.resume()
      else:
        self._session_timer.pause()
    super().changeEvent(evt)

  def sizeHint(self):
    return QSize(650, 400)

class AboutWidget(QTextBrowser):
  def __init__(self, *args):
    try:
      html = (Settings.DATA_DIR / "about.html").open('r').read()
    except:
      html = "Amphetype v.${VERSION}<br />about.html file missing or could not be loaded!"
    html = html.replace('${VERSION}', __version__)
    super(AboutWidget, self).__init__(*args)
    self.setHtml(html)
    self.setOpenExternalLinks(True)
    #self.setMargin(40)
    self.setReadOnly(True)


def set_qt_css(fname):
  if fname == '<none>':
    app.setStyleSheet('')
  else:
    if Path(fname).is_file():
      with Path(fname).open('r') as f:
        app.setStyleSheet(f.read())
    else:
      log.warn('file not found: %s', fname)

Settings.signal_for('qt_css').connect(set_qt_css)
set_qt_css(Settings.get('qt_css'))

Settings.signal_for('qt_style').connect(app.setStyle)
app.setStyle(Settings.get('qt_style'))

