import sys
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

_qt_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(scope="session")
def qapp():
  """Ensure a QApplication exists for the test session."""
  yield _qt_app
