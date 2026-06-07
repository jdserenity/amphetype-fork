"""Read-ahead mode: hide upcoming words so the typist must look ahead."""

import re

WORD_RE = re.compile(r"\w+(?:['-]\w+)*")

READ_AHEAD_OFF = 0
READ_AHEAD_NORMAL = 1
READ_AHEAD_EASY = 2
READ_AHEAD_HARD = 3

HIDE_COUNT = {
  READ_AHEAD_OFF: 0,
  READ_AHEAD_EASY: 1,
  READ_AHEAD_NORMAL: 2,
  READ_AHEAD_HARD: 3,
}

READ_AHEAD_LEVEL_NORMAL = 0
READ_AHEAD_LEVEL_HARD = 1
READ_AHEAD_LEVEL_EASY = 2
READ_AHEAD_LEVEL_LABELS = ('normal', 'hard', 'easy')
READ_AHEAD_LEVEL_MODES = (READ_AHEAD_NORMAL, READ_AHEAD_HARD, READ_AHEAD_EASY)


def document_read_ahead_mode(enabled, level):
  if not enabled:
    return READ_AHEAD_OFF
  return READ_AHEAD_LEVEL_MODES[level % len(READ_AHEAD_LEVEL_MODES)]


def word_spans(text):
  return [(m.start(), m.end()) for m in WORD_RE.finditer(text)]


def current_word_index(text, pos):
  words = word_spans(text)
  if not words:
    return 0
  pos = max(0, min(pos, len(text)))
  for i, (s, e) in enumerate(words):
    if s <= pos < e:
      return i
  for i, (s, e) in enumerate(words):
    if s > pos:
      return i
  return len(words) - 1


def hidden_word_indices(text, pos, mode):
  n = HIDE_COUNT.get(mode, 0)
  if n <= 0:
    return []
  words = word_spans(text)
  wi = current_word_index(text, pos)
  return list(range(wi, min(wi + n, len(words))))


def hidden_char_indices(text, pos, mode, revealed_words=()):
  words = word_spans(text)
  hidden = set()
  for wi in hidden_word_indices(text, pos, mode):
    if wi in revealed_words:
      continue
    s, e = words[wi]
    hidden.update(range(s, e))
  return hidden


def word_index_at(text, pos):
  return current_word_index(text, pos)
