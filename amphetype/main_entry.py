"""Entry script for the frozen (PyInstaller) build. Mirrors the `amphetype`
console script, which calls amphetype.main:main_normal."""

import sys

from amphetype.main import main_normal

if __name__ == '__main__':
  sys.exit(main_normal())
