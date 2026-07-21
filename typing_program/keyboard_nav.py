"""Keyboard navigation helpers for practice modes and main tabs.

Shortcuts (wired in UI):
  Tab — next improve submode (Typer, improve mode only)
  Cmd/Ctrl+Opt/Alt+← / → — previous / next selectable practice mode (improve · corpus · book when enabled)
  Cmd/Ctrl+Shift+[ / ] — previous / next main toolbar tab
"""

from typing_program.book_mode import (
  BOOK_MODE_FOOTER_VISIBLE, MODE_BOOK, MODE_CORPUS, MODE_IMPROVE,
)

# Full footer order (including modes that may be hidden via BOOK_MODE_FOOTER_VISIBLE).
PRACTICE_MODE_ORDER = (MODE_IMPROVE, MODE_CORPUS, MODE_BOOK)


def selectable_practice_modes():
  """Modes the user can pick via footer buttons or Cmd/Ctrl+Opt+← / →."""
  if BOOK_MODE_FOOTER_VISIBLE:
    return PRACTICE_MODE_ORDER
  return tuple(m for m in PRACTICE_MODE_ORDER if m != MODE_BOOK)


def cycle_practice_mode(current, delta=1):
  """Next/previous practice mode. delta +1 = forward (→), -1 = back (←)."""
  order = selectable_practice_modes()
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
