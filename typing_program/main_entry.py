"""Entry script for the frozen (PyInstaller) build. Mirrors the `typing-program`
console script, which calls typing_program.main:main_normal."""

import sys

from typing_program.main import main_normal

if __name__ == '__main__':
  sys.exit(main_normal())
