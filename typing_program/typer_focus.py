"""Keep keyboard focus on the lesson canvas so typing never needs a re-click.

Only the follow-mode WPM box may take focus away from the typer.
"""


def focus_is_follow_wpm(widget, follow_wpm_edit):
  """True if keyboard focus is on (or inside) the follow WPM editor."""
  if widget is None or follow_wpm_edit is None:
    return False
  return widget is follow_wpm_edit or follow_wpm_edit.isAncestorOf(widget)


def focus_is_typer(widget, typer):
  """True if keyboard focus is on the lesson editor (or its viewport)."""
  if widget is None or typer is None:
    return False
  return widget is typer or typer.isAncestorOf(widget)


def should_refocus_typer(new_focus, typer_window_visible, focus_inside_typer_window,
                         typer, follow_wpm_edit):
  """Whether to force focus back onto the lesson after a focus change.

  - Never steal focus while the follow WPM box is active.
  - Never steal focus when another main tab / dialog owns it
    (`focus_inside_typer_window` False and new_focus is set).
  - If focus cleared (None) while the Typer tab is visible, reclaim it.
  - If focus moved to a footer control or other chrome inside Typer, reclaim it.
  """
  if not typer_window_visible:
    return False
  if focus_is_follow_wpm(new_focus, follow_wpm_edit):
    return False
  if focus_is_typer(new_focus, typer):
    return False
  if new_focus is not None and not focus_inside_typer_window:
    return False
  return True
