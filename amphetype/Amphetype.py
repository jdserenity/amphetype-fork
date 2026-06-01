
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
app.DB = DB

# After this we can do whatever we want.

import os
from pathlib import Path
from amphetype.Quizzer import Quizzer
from amphetype.StatWidgets import StringStats
from amphetype.TextManager import TextManager
from amphetype.Performance import PerformanceHistory
from amphetype.Config import GeneralOptions, TyperOptions
from amphetype.Lesson import LessonGenerator
from amphetype.WeakSpot import WeakSpotWidget
from amphetype.Widgets.Database import DatabaseWidget

from amphetype.fwidgets import FStackedWidget
from amphetype.typer import TyperWindow

from PyQt5.QtCore import *
from PyQt5.QtGui import *


class AmphetypeWindow(QMainWindow):
  def __init__(self, *args):
    super().__init__(*args)

    self.setWindowTitle("Amphetype")

    self.quitSc = QShortcut(QKeySequence('Ctrl+Q'), self)
    self.quitSc.activated.connect(QApplication.instance().quit)
    
    tabs = QTabWidget()

    quiz = Quizzer()
    tw = TyperWindow()
    quiztw = FStackedWidget([quiz, tw])
    tabs.addTab(quiztw, "Typer")
    quiztw.setCurrentIndex(Settings.get('which_typer'))
    Settings.signal_for('which_typer').connect(quiztw.setCurrentIndex)

    tm = TextManager()
    quiz.wantText.connect(tm.nextText)
    tm.setText.connect(quiz.setText)
    tm.gotoText.connect(lambda: tabs.setCurrentIndex(0))
    tabs.addTab(tm, "Sources")

    ph = PerformanceHistory()
    tm.refreshSources.connect(ph.refreshSources)
    quiz.statsChanged.connect(ph.updateData)
    ph.setText.connect(quiz.setText)
    ph.gotoText.connect(lambda: tabs.setCurrentIndex(0))
    tabs.addTab(ph, "Performance")

    st = StringStats()
    st.lessonStrings.connect(lambda x: tabs.setCurrentIndex(5))
    tabs.addTab(st, "Analysis")

    ws = WeakSpotWidget()
    ws.startLesson.connect(tm.newWeakspot)
    ws.gotoTyper.connect(lambda: tabs.setCurrentIndex(0))
    quiz.statsChanged.connect(ws.on_stats_changed)
    tw.statsChanged.connect(ws.on_stats_changed)
    tabs.addTab(ws, "Weakspot")

    lg = LessonGenerator()
    st.lessonStrings.connect(lg.addStrings)
    lg.newLessons.connect(lambda: tabs.setCurrentIndex(1))
    lg.newLessons.connect(tm.addTexts)
    quiz.wantReview.connect(lg.wantReview)
    lg.newReview.connect(tm.newReview)
    tabs.addTab(lg, "Lesson Generator")

    ph.setText.connect(tm.emit_text)
    tm.setText.connect(tw.setText)
    tw.wantText.connect(tm.nextText)
    tw.wantReview.connect(lg.wantReview)
    tw.statsChanged.connect(ph.updateData)

    dw = DatabaseWidget()
    tabs.addTab(dw, "Database")

    pw = QTabWidget()
    pw.addTab(GeneralOptions(), "General Options")
    pw.addTab(TyperOptions(), "Typer Options")
    tabs.addTab(pw, "Preferences")

    ab = AboutWidget()
    tabs.addTab(ab, "About/Help")

    self.setCentralWidget(tabs)

    tm.nextText()

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


