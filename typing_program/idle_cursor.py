"""Hide the mouse pointer after a short idle period; show it again on move."""

MOUSE_CURSOR_IDLE_MS = 2000


def should_hide_mouse_cursor(idle_ms, threshold_ms=MOUSE_CURSOR_IDLE_MS):
  """True when the pointer has been still long enough to blank it."""
  return idle_ms >= threshold_ms
