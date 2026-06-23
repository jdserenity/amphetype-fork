from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
  QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from amphetype.license import (
  LicenseError, LicenseNetworkError, activate, checkout_url, machine_id, save_license,
)


class LicenseDialog(QDialog):
  def __init__(self, settings, opener=None, parent=None):
    super().__init__(parent)
    self.settings = settings
    self.opener = opener
    self.setWindowTitle('Activate Typing Program')
    self.setModal(True)
    self.setMinimumWidth(420)

    title = QLabel('<b>Enter your license key</b>')
    title.setTextFormat(Qt.RichText)
    hint = QLabel(
      'You received this key by email after purchase. '
      'One license works on a few machines — reinstalls may use another activation slot.'
    )
    hint.setWordWrap(True)

    self.key_edit = QLineEdit()
    self.key_edit.setPlaceholderText('xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx')
    self.status = QLabel('')
    self.status.setWordWrap(True)

    activate_btn = QPushButton('Activate')
    activate_btn.clicked.connect(self._activate)
    buy_btn = QPushButton('Buy for $5')
    buy_btn.clicked.connect(self._buy)
    quit_btn = QPushButton('Quit')
    quit_btn.clicked.connect(self.reject)

    row = QHBoxLayout()
    row.addWidget(activate_btn)
    row.addWidget(buy_btn)
    row.addStretch(1)
    row.addWidget(quit_btn)

    layout = QVBoxLayout(self)
    layout.addWidget(title)
    layout.addWidget(hint)
    layout.addWidget(self.key_edit)
    layout.addWidget(self.status)
    layout.addLayout(row)

    self.key_edit.returnPressed.connect(self._activate)

  def _buy(self):
    QDesktopServices.openUrl(QUrl(checkout_url()))

  def _activate(self):
    key = self.key_edit.text().strip()
    if not key:
      self.status.setText('Paste your license key from the purchase email.')
      return
    self.status.setText('Activating…')
    try:
      data = activate(key, machine_id(self.settings), opener=self.opener)
      instance_id = (data.get('instance') or {}).get('id')
      save_license(self.settings, key, instance_id)
      self.accept()
    except LicenseNetworkError as e:
      self.status.setText(f'Network error — check your connection and try again. ({e})')
    except LicenseError as e:
      self.status.setText(str(e))
    except Exception as e:
      QMessageBox.warning(self, 'Activation failed', str(e))
      self.status.setText('Activation failed.')
