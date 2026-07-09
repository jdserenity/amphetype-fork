"""Block ⌫ mode: plain Backspace does nothing; only modifier+Backspace deletes.

Trains deleting whole words (Opt/Alt/Ctrl+Backspace) instead of mashing
character backspace after fast typos. Footer label: "Block ⌫".
Code name: block_bkspc. Pref key: word_delete_enabled (kept for saved settings).
"""


def allows_backspace(enabled, by_word):
  """Return True if this backspace keypress should take effect.

  When mode is off, all backspaces work. When mode is on (Block ⌫), only
  word-level backspace (by_word=True, i.e. Opt/Alt/Ctrl/Cmd+Backspace) is allowed.
  """
  if not enabled:
    return True
  return bool(by_word)
