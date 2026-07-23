"""Keyboard navigation helpers for practice modes and main tabs.

Shortcuts (wired in UI):
  Tab — next improve submode (Typer, improve mode only)
  Cmd/Ctrl+Opt/Alt+← / → — previous / next selectable practice mode (improve · corpus · book when enabled)
  Cmd/Ctrl+Shift+[ / ] — previous / next toolbar slot (main tabs + Preferences sub-tabs as one sequence)
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


def toolbar_cycle_pos(main_index, prefs_tab_index, prefs_sub_index, prefs_count):
  """Flatten main tabs + prefs sub-tabs into one sequence position.

  Example with prefs as the last main tab and 3 sub-tabs:
  Typer=0, Performance=1, General=2, Typer Options=3, Sources=4.
  """
  before = int(prefs_tab_index)
  if int(main_index) == before:
    return before + int(prefs_sub_index)
  if int(main_index) < before:
    return int(main_index)
  return int(main_index) + int(prefs_count) - 1


def cycle_toolbar_tabs(main_index, prefs_tab_index, prefs_sub_index, prefs_count, delta=1):
  """Next/previous toolbar slot. Returns (main_index, prefs_sub_index)."""
  before = int(prefs_tab_index)
  n_prefs = int(prefs_count)
  total = before + n_prefs
  pos = cycle_index(
    toolbar_cycle_pos(main_index, prefs_tab_index, prefs_sub_index, prefs_count),
    total, delta)
  if pos < before:
    return pos, int(prefs_sub_index)
  return before, pos - before
