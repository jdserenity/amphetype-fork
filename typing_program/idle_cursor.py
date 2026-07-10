"""Hide the mouse pointer after a short idle period; show it again on move."""

MOUSE_CURSOR_IDLE_MS = 2000


def should_hide_mouse_cursor(idle_ms, threshold_ms=MOUSE_CURSOR_IDLE_MS):
  """True when the pointer has been still long enough to blank it."""
  return idle_ms >= threshold_ms


def should_apply_idle_blank(pointer_still_over_canvas, idle_ms=None, threshold_ms=MOUSE_CURSOR_IDLE_MS):
  """Blank only while the pointer is still on the lesson canvas.

  If the timer fires after the user has already left for the footer (or the
  hide slot was already queued), do not apply BlankCursor — that would fight
  PointingHandCursor on the mode buttons.
  """
  if not pointer_still_over_canvas:
    return False
  if idle_ms is None:
    return True
  return should_hide_mouse_cursor(idle_ms, threshold_ms)
