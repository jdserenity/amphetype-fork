
from amphetype.Config import Settings, SettingsEdit
from amphetype.QtUtil import *
from amphetype.Performance import PerformanceHistory
from amphetype.StatWidgets import StringStats

from PyQt5.QtCore import *
from PyQt5.QtWidgets import QTabWidget


class PerformanceAnalysis(QWidget):
  setText = pyqtSignal('PyQt_PyObject')
  gotoText = pyqtSignal()

  def __init__(self, *args):
    super(PerformanceAnalysis, self).__init__(*args)
    self.ph = PerformanceHistory()
    self.st = StringStats()
    self.ph.setText.connect(self.setText.emit)
    self.ph.gotoText.connect(self.gotoText.emit)
    Settings.signal_for("history").connect(self.updateAll)
    subtabs = QTabWidget()
    subtabs.addTab(self.st, "Stats")
    subtabs.addTab(self.ph, "Progress")
    self.subtabs = subtabs
    self.setLayout(AmphBoxLayout([
        ["Last", SettingsEdit("history"), "days.", None, AmphButton("Update", self.updateAll)],
        (subtabs, 1),
      ]))

  def refreshSources(self):
    self.ph.refreshSources()

  def updateData(self, *args):
    self.ph.updateData(*args)

  def updateAll(self, *args):
    self.ph.updateData(*args)
    self.st.update(*args)
