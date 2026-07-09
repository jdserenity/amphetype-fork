"""Word-delete mode: block single-char backspace; only modifier+backspace deletes.

Trains deleting whole words (Opt/Alt/Ctrl+Backspace) instead of mashing
character backspace after fast typos.
"""


def allows_backspace(enabled, by_word):
  """Return True if this backspace keypress should take effect.

  When mode is off, all backspaces work. When mode is on, only word-level
  backspace (by_word=True, i.e. Opt/Alt/Ctrl/Cmd+Backspace) is allowed.
  """
  if not enabled:
    return True
  return bool(by_word)
