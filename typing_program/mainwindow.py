
from typing_program import *
import sys
import logging as log

# The order of the code and imports here is important (and a kludge).
# Due to being young and stupid I made the module files do weird
# initialization stuff on import, and some of them depend on each
# other.

# Init QT and set appname.
from PyQt5.QtWidgets import *
class TypingProgramApp(QApplication):
  def __init__(self, *args, **kwargs):
    super().__init__(sys.argv, *args, applicationName='Typing Program', **kwargs)


app = TypingProgramApp()

# Import Config.py; this will do argument parsing and set up the
# global var "Settings".
from typing_program.Config import Settings
app.settings = Settings

# Only AFTER settings has been initialized, import database:
from typing_program.Data import DB
from typing_program.app_meta import PREFERENCES_TAB_KEY, get_app_meta_int, set_app_meta_int
app.DB = DB

# After this we can do whatever we want.

import os
from pathlib import Path
from typing_program.TextManager import TextManager
from typing_program.PerformanceAnalysis import PerformanceAnalysis
from typing_program.Config import GeneralOptions, TyperOptions
from typing_program.Lesson import LessonGenerator

from typing_program.typer import TyperWindow
from typing_program.session_timer import FocusedSessionTimer, INTERACTION_EVENTS, SessionTimerLabel
from typing_program.fwidgets import scroll_widget
from typing_program.QtUtil import center_widget_on_screen, should_clear_focus_on_click

from PyQt5.QtCore import *
from PyQt5.QtGui import *


class MainWindow(QMainWindow):
  def __init__(self, *args):
    super().__init__(*args)

    self.setWindowTitle('Typing Program That Helps You Type Better')

    self.quitSc = QShortcut(QKeySequence('Ctrl+Q'), self)
    self.quitSc.activated.connect(QApplication.instance().quit)
    
    tabs = QTabWidget()
    self._tabs = tabs
    # No full-width pane rule through the tab strip / session clock. Pane must stay
    # transparent so TyperWindow's page background_color fills the lesson area.
    tabs.setObjectName('mainTabs')
    tabs.setDocumentMode(True)
    tabs.setStyleSheet(
      'QTabWidget#mainTabs::pane { border: none; background: transparent; }')

    tw = TyperWindow()
    tabs.addTab(tw, "Typer")

    tm = TextManager()
    tm.gotoText.connect(lambda: tabs.setCurrentIndex(0))

    pa = PerformanceAnalysis()
    pa.gotoText.connect(lambda: tabs.setCurrentIndex(0))
    tabs.addTab(pa, "Performance Analysis")
    self._perf_tab_idx = tabs.indexOf(pa)
    self._perf = pa
    tabs.currentChanged.connect(lambda i: pa.updateAll() if i == self._perf_tab_idx else None)

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
    pa.st.statsChanged.connect(pa.updateAll)
    pa.st.statsChanged.connect(tw._weakspot.on_stats_changed)
    pa.startDrill.connect(tw.start_focus_drill)
    pa.loadCorpusText.connect(tw.load_corpus_text)

    pw = QTabWidget()
    pw.addTab(scroll_widget(GeneralOptions()), "General Options")
    pw.addTab(scroll_widget(TyperOptions()), "Typer Options")
    pw.addTab(scroll_widget(tm), "Sources")
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
    self._session_timer.load_saved(DB)
    self._session_clock = SessionTimerLabel(self._session_timer, tabs)
    self._session_clock.start()
    self._session_clock.textChanged.connect(self._reposition_session_clock)
    self._session_clock.textChanged.connect(self._maybe_refresh_practice_time)
    pa.set_session_timer(self._session_timer)
    tabs.installEventFilter(self)
    app.installEventFilter(self)

    self.setCentralWidget(tabs)
    self._window_placed = False
    Settings.signal_for('show_session_timer').connect(lambda *_: self._apply_session_clock_visible())
    self._apply_session_clock_visible()
    if self.isActiveWindow():
      self._session_timer.resume()

    # Practice mode is forced to improve · normal in TyperWindow (cold start).

  def _apply_session_clock_visible(self):
    on = bool(Settings.get('show_session_timer'))
    self._session_clock.setVisible(on)
    if on:
      self._reposition_session_clock()

  def _reposition_session_clock(self):
    tabs = self._tabs
    if not self._session_clock.isVisible():
      return
    self._session_clock.adjustSize()
    bar = tabs.tabBar()
    # Vertically center on the first tab so the clock lines up with the tab labels.
    if bar.count() > 0:
      r = bar.tabRect(0)
      y = r.y() + max(0, (r.height() - self._session_clock.height()) // 2)
    else:
      y = 0
    self._session_clock.move(tabs.width() - self._session_clock.width() - 8, y)
    self._session_clock.raise_()

  def _maybe_refresh_practice_time(self):
    if self._tabs.currentIndex() != self._perf_tab_idx:
      return
    self._perf._progress._practice_lbl.setText(self._perf._progress._practice_time_text())

  def eventFilter(self, obj, evt):
    if evt.type() in INTERACTION_EVENTS:
      self._session_timer.touch()
    if evt.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick) and isinstance(evt, QMouseEvent):
      fw = QApplication.focusWidget()
      w = QApplication.widgetAt(evt.globalPos())
      if should_clear_focus_on_click(fw, w):
        fw.clearFocus()
    if obj is self._tabs and evt.type() in (QEvent.Resize, QEvent.Show):
      self._reposition_session_clock()
    return super().eventFilter(obj, evt)

  def closeEvent(self, evt):
    self._session_timer.flush_to_db(DB)
    super().closeEvent(evt)

  def showEvent(self, evt):
    super().showEvent(evt)
    if not self._window_placed:
      self.resize(self.sizeHint())
      center_widget_on_screen(self)
      self._window_placed = True
    self._reposition_session_clock()

  def changeEvent(self, evt):
    if evt.type() == QEvent.ActivationChange:
      if self.isActiveWindow():
        self._session_timer.resume()
      else:
        self._session_timer.pause()
        self._session_timer.flush_to_db(DB)
    super().changeEvent(evt)

  def sizeHint(self):
    return QSize(1100, 712)

class AboutWidget(QTextBrowser):
  def __init__(self, *args):
    try:
      html = (Settings.DATA_DIR / "about.html").open('r').read()
    except:
      html = "Typing Program v.${VERSION}<br />about.html file missing or could not be loaded!"
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

