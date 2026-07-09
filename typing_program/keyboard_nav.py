"""Keyboard navigation helpers for practice modes and main tabs.

Shortcuts (wired in UI):
  Tab — next improve submode (Typer, improve mode only)
  Cmd/Ctrl+Opt/Alt+← / → — previous / next practice mode (improve · corpus · book)
  Opt/Alt+Cmd/Ctrl+[ / ] — previous / next main toolbar tab
"""

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE

# Same order as the Typer footer mode buttons.
PRACTICE_MODE_ORDER = (MODE_IMPROVE, MODE_CORPUS, MODE_BOOK)


def cycle_practice_mode(current, delta=1):
  """Next/previous practice mode. delta +1 = forward (→), -1 = back (←)."""
  order = PRACTICE_MODE_ORDER
  try:
    i = order.index(current)
  except ValueError:
    i = 0
  return order[(i + int(delta)) % len(order)]


def cycle_index(current, count, delta=1):
  """Cycle a 0-based index (main tabs, etc.). Returns 0 if count <= 0."""
  n = int(count)
  if n <= 0:
    return 0
  return (int(current) + int(delta)) % n
