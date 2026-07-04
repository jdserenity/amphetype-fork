from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
  QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout,
)

from typing_program import __version__
from typing_program.updater import (
  UpdateError,
  UpdateNetworkError,
  apply_downloaded_update,
  check_for_update,
  download_file,
  is_frozen,
)


class _UpdateWorker(QThread):
  progress = pyqtSignal(int, int)
  finished_ok = pyqtSignal()
  failed = pyqtSignal(str)

  def __init__(self, settings, update_info, parent=None):
    super().__init__(parent)
    self.settings = settings
    self.update_info = update_info
    self._archive = None

  def run(self):
    try:
      import tempfile
      from pathlib import Path
      fd, path = tempfile.mkstemp(prefix='typing-program-dl-', suffix='.zip')
      import os
      os.close(fd)
      self._archive = path
      info = self.update_info
      download_file(
        info['download_url'],
        path,
        progress_cb=lambda done, total: self.progress.emit(done, total),
      )
      apply_downloaded_update(path, info['sha256'])
      self.finished_ok.emit()
    except (UpdateError, UpdateNetworkError) as e:
      self.failed.emit(str(e))
    except Exception as e:
      self.failed.emit(str(e))


class UpdateDialog(QDialog):
  def __init__(self, settings, parent=None):
    super().__init__(parent)
    self.settings = settings
    self._worker = None
    self._update_info = None
    self.setWindowTitle('Check for updates')
    self.setMinimumWidth(420)

    self.status = QLabel(f'Current version: {__version__}')
    self.status.setWordWrap(True)
    self.notes = QLabel('')
    self.notes.setWordWrap(True)
    self.notes.hide()
    self.progress = QProgressBar()
    self.progress.hide()

    self.check_btn = QPushButton('Check for updates')
    self.check_btn.clicked.connect(self._check)
    self.update_btn = QPushButton('Install update and restart')
    self.update_btn.clicked.connect(self._install)
    self.update_btn.hide()
    close_btn = QPushButton('Close')
    close_btn.clicked.connect(self.reject)

    row = QHBoxLayout()
    row.addWidget(self.check_btn)
    row.addWidget(self.update_btn)
    row.addStretch(1)
    row.addWidget(close_btn)

    layout = QVBoxLayout(self)
    layout.addWidget(self.status)
    layout.addWidget(self.notes)
    layout.addWidget(self.progress)
    layout.addLayout(row)

    if not is_frozen():
      self.status.setText(
        f'Current version: {__version__}\n\n'
        'In-app updates work in the installed app only (not dev mode).'
      )
      self.check_btn.setEnabled(False)

  def _check(self):
    self.check_btn.setEnabled(False)
    self.update_btn.hide()
    self.notes.hide()
    self.progress.hide()
    self.status.setText('Checking for updates…')
    try:
      info = check_for_update(self.settings)
    except UpdateNetworkError as e:
      self.status.setText(f'Could not reach the update server.\n\n{e}')
      self.check_btn.setEnabled(True)
      return
    except UpdateError as e:
      self.status.setText(str(e))
      self.check_btn.setEnabled(True)
      return
    if not info.get('update_available'):
      self.status.setText(f'You are up to date ({__version__}).')
      self.check_btn.setEnabled(True)
      return
    self._update_info = info
    self.status.setText(f'Version {info["version"]} is available (you have {__version__}).')
    notes = (info.get('release_notes') or '').strip()
    if notes:
      self.notes.setText(notes)
      self.notes.show()
    self.update_btn.show()
    self.check_btn.setEnabled(True)

  def _install(self):
    if not self._update_info:
      return
    self.check_btn.setEnabled(False)
    self.update_btn.setEnabled(False)
    self.progress.setRange(0, 0)
    self.progress.show()
    self.status.setText('Downloading update…')
    self._worker = _UpdateWorker(self.settings, self._update_info, self)
    self._worker.progress.connect(self._on_progress)
    self._worker.finished_ok.connect(self._on_ready)
    self._worker.failed.connect(self._on_failed)
    self._worker.start()

  def _on_progress(self, done, total):
    if total > 0:
      self.progress.setRange(0, total)
      self.progress.setValue(done)
    self.status.setText('Downloading update…')

  def _on_ready(self):
    self.status.setText('Installing update and restarting…')
    self.progress.hide()
    from PyQt5.QtWidgets import QApplication
    QApplication.instance().quit()

  def _on_failed(self, msg):
    self.progress.hide()
    self.status.setText(f'Update failed.\n\n{msg}')
    self.check_btn.setEnabled(True)
    self.update_btn.setEnabled(True)
    QMessageBox.warning(self, 'Update failed', msg)
