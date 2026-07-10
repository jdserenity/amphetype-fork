"""Follow mode: race a moving caret at a fixed WPM (corpus/book only).

Standard typing measure: 1 word = 5 characters, so chars/sec = wpm / 12.
"""

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS

DEFAULT_FOLLOW_WPM = 40
MIN_FOLLOW_WPM = 1
MAX_FOLLOW_WPM = 300

# Bright caret color on the dark lesson canvas (distinct from the typing cursor).
FOLLOW_CURSOR_COLOR = '#5ec8ff'


def follow_eligible(practice_mode):
  """True when follow mode may run (corpus or book)."""
  return practice_mode in (MODE_CORPUS, MODE_BOOK)


def follow_active(enabled, practice_mode):
  """True when the preference is on and the current practice mode allows it."""
  return bool(enabled) and follow_eligible(practice_mode)


def clamp_follow_wpm(wpm):
  try:
    n = int(wpm)
  except (TypeError, ValueError):
    return DEFAULT_FOLLOW_WPM
  return max(MIN_FOLLOW_WPM, min(MAX_FOLLOW_WPM, n))


def parse_follow_wpm(text, default=DEFAULT_FOLLOW_WPM):
  """Parse a typed WPM string; empty/invalid → default (then clamped)."""
  if text is None:
    return clamp_follow_wpm(default)
  s = str(text).strip()
  if not s:
    return clamp_follow_wpm(default)
  try:
    return clamp_follow_wpm(int(s))
  except ValueError:
    return clamp_follow_wpm(default)


def chars_per_second(wpm):
  """Characters per second at the given WPM (5 chars = 1 word)."""
  w = clamp_follow_wpm(wpm)
  return w / 12.0


def follow_index(elapsed_sec, wpm, text_len):
  """Match-text index the follow caret should occupy after elapsed_sec seconds."""
  if text_len <= 0 or elapsed_sec <= 0:
    return 0
  idx = int(elapsed_sec * chars_per_second(wpm))
  return min(max(0, idx), text_len)


def follow_reached_end(elapsed_sec, wpm, text_len):
  """True when the follow caret has reached or passed the end of the lesson."""
  if text_len <= 0:
    return False
  return follow_index(elapsed_sec, wpm, text_len) >= text_len


def follow_race_result(user_complete, cursor_at_end):
  """Outcome of the race: 'success', 'failure', or None if still in progress.

  Tie (both true in the same moment) counts as success — the typist finished.
  """
  if user_complete:
    return 'success'
  if cursor_at_end:
    return 'failure'
  return None


def follow_footer_state(enabled, practice_mode):
  """UI flags for the follow footer control.

  Preference can stay on while improve greys the control out; returning to
  corpus/book makes it active again without the user re-clicking.
  """
  eligible = follow_eligible(practice_mode)
  active = follow_active(enabled, practice_mode)
  return {
    'eligible': eligible,
    'active': active,
    'btn_enabled': eligible,
    'wpm_visible': active,
    'btn_active_style': active,
    'btn_greyed': (not eligible),
  }
