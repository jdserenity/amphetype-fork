"""Pause-aware elapsed clock for follow-mode caret racing.

Lesson runs often cold-start with RunStats.started unset until the end, so follow
mode keeps this separate clock instead of reading run.active_elapsed().
"""


class FollowClock:
  def __init__(self, now):
    """now: zero-arg callable returning monotonic seconds (e.g. typing_program.timer)."""
    self._now = now
    self.reset()

  def reset(self):
    self._started = None
    self._pause_total = 0.0
    self._paused_at = None

  def start(self):
    if self._started is None:
      self._started = self._now()
      self._pause_total = 0.0
      self._paused_at = None

  def pause(self):
    if self._started is not None and self._paused_at is None:
      self._paused_at = self._now()

  def resume(self):
    if self._paused_at is not None:
      self._pause_total += self._now() - self._paused_at
      self._paused_at = None

  def elapsed(self):
    if self._started is None:
      return 0.0
    t = self._paused_at if self._paused_at is not None else self._now()
    return max(0.0, t - self._started - self._pause_total)
