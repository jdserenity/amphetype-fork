"""Typing keystroke sounds (bundled audio under data/sounds)."""

from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

from amphetype import DATA_DIR

AUDIO_EXTS = ('.wav', '.ogg', '.mp3')
_SOUND_PREFIXES = {'type': 'type-', 'error': 'error-', 'space': 'space-'}
_DEFAULT_TYPE_SOUND = 'type-1'
_DEFAULT_ERROR_SOUND = 'error-1'
_DEFAULT_VOLUME = 50  # QMediaPlayer 0..100


def sounds_directory():
  return DATA_DIR / 'sounds'


def _all_sound_ids():
  d = sounds_directory()
  if not d.is_dir():
    return []
  return {p.stem for p in d.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS}


def list_sound_ids(category=None):
  """Sound stems; category is 'type', 'error', 'space', or None for all."""
  ids = _all_sound_ids()
  if category is not None:
    prefix = _SOUND_PREFIXES[category]
    ids = {sid for sid in ids if sid.startswith(prefix)}
  return sorted(ids, key=lambda sid: (sid,))


def format_sound_label(sound_id):
  return sound_id.replace('-', ' ')


def resolve_sound_path(sound_id):
  """Path for a sound stem, or None if missing / disabled."""
  if not sound_id:
    return None
  d = sounds_directory()
  for ext in AUDIO_EXTS:
    p = d / f'{sound_id}{ext}'
    if p.is_file():
      return p
  return None


def default_typing_sound_id():
  if resolve_sound_path(_DEFAULT_TYPE_SOUND):
    return _DEFAULT_TYPE_SOUND
  ids = list_sound_ids('type')
  return ids[0] if ids else ''


def default_typing_error_sound_id():
  if resolve_sound_path(_DEFAULT_ERROR_SOUND):
    return _DEFAULT_ERROR_SOUND
  ids = list_sound_ids('error')
  return ids[0] if ids else ''


class _MediaBurstPlayer:
  """Overlapping short clips via a small QMediaPlayer pool (handles float/stereo WAV, OGG, etc.)."""

  def __init__(self, pool=3, volume=_DEFAULT_VOLUME):
    self._volume = volume
    self._players = [QMediaPlayer() for _ in range(pool)]
    self.set_volume(volume)
    self._i = 0

  def set_volume(self, volume):
    self._volume = max(0, min(100, int(volume)))
    for p in self._players:
      p.setVolume(self._volume)

  def play(self, path):
    p = self._players[self._i]
    self._i = (self._i + 1) % len(self._players)
    p.setVolume(self._volume)
    p.setMedia(QMediaContent(QUrl.fromLocalFile(str(path.resolve()))))
    p.play()


class TypingSoundPlayer:
  """Plays independently chosen correct-, error-, and space-keystroke sounds."""

  def __init__(self):
    self._type_player = _MediaBurstPlayer()
    self._err_player = _MediaBurstPlayer()
    self._space_player = _MediaBurstPlayer()
    self._type_path = None
    self._err_path = None
    self._space_path = None

  def configure(self, type_sound_id='', error_sound_id='', space_sound_id='', volume=_DEFAULT_VOLUME):
    self._type_path = resolve_sound_path(type_sound_id)
    self._err_path = resolve_sound_path(error_sound_id)
    self._space_path = resolve_sound_path(space_sound_id)
    self._type_player.set_volume(volume)
    self._err_player.set_volume(volume)
    self._space_player.set_volume(volume)

  def play_keystroke(self, correct=True, char=''):
    if not correct:
      path = self._err_path
      player = self._err_player
    elif char == ' ' and self._space_path:
      path = self._space_path
      player = self._space_player
    else:
      path = self._type_path
      player = self._type_player
    if path is None:
      return
    player.play(path)
