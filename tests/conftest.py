import pytest
from PyQt5.QtWidgets import QApplication
import sys

_qt_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="session")
def qapp():
  """Ensure a QApplication exists for the test session."""
  yield _qt_app
