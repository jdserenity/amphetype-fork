from PyQt5.QtCore import QRect

from amphetype.QtUtil import centered_frame_origin


def test_centered_frame_origin():
  screen = QRect(0, 25, 1920, 1055)  # usable area below a menu bar
  x, y = centered_frame_origin(screen, 650, 400)
  assert x == (1920 - 650) // 2
  assert y == 25 + (1055 - 400) // 2
  assert x + 650 // 2 == screen.x() + screen.width() // 2
  assert y + 400 // 2 == screen.y() + screen.height() // 2


def test_centered_frame_origin_offset_screen():
  screen = QRect(100, 50, 800, 600)
  x, y = centered_frame_origin(screen, 200, 100)
  assert x == screen.x() + (screen.width() - 200) // 2
  assert y == screen.y() + (screen.height() - 100) // 2
