"""Auto-review after a corpus text: turn slow/mistyped words into a follow-up lesson."""

import random

from PyQt5.QtCore import QObject, pyqtSignal

# Same defaults the old Lesson Generator used for auto_review.
REVIEW_COPIES = 3
REVIEW_TAKE = 2
REVIEW_MIX = 'c'  # 'c' concatenate, 'm' mingle/shuffle within each batch


def build_review_sentences(words, copies=REVIEW_COPIES, take=REVIEW_TAKE, mix=REVIEW_MIX, rng=None):
  """Split words into batches, optionally shuffle each batch, repeat `copies` times."""
  words = list(words)
  if take == 0:
    take = len(words) or 1
  if rng is None:
    rng = random
  sentences = []
  while words:
    batch = words[:take] * copies
    words[:take] = []
    if mix == 'm':
      rng.shuffle(batch)
    sentences.append(' '.join(batch))
  return sentences


def build_review_text(words, **kwargs):
  return ' '.join(build_review_sentences(words, **kwargs))


class AutoReview(QObject):
  """Receives Typer.wantReview word lists; emits lesson text for TextManager.newReview."""
  newReview = pyqtSignal(str)

  def wantReview(self, words):
    self.newReview.emit(build_review_text(words))
