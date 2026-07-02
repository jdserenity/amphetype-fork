"""Typing keystroke sounds (bundled audio under data/sounds)."""

from PyQt5.QtCore import QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer, QSoundEffect

from amphetype import DATA_DIR

AUDIO_EXTS = ('.wav', '.ogg', '.mp3')
_DEFAULT_TYPE_SOUND = 'type-1'
_DEFAULT_ERROR_SOUND = 'error-1'
# QSoundEffect 0..1; QMediaPlayer 0..100
_WAV_VOLUME = 0.22
_OGG_VOLUME = 22


def sounds_directory():
  return DATA_DIR / 'sounds'


def list_sound_ids():
  """Sorted stems of discoverable audio files (e.g. type-1, error-2)."""
  d = sounds_directory()
  if not d.is_dir():
    return []
  ids = {p.stem for p in d.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS}
  return sorted(ids, key=_sound_sort_key)


def _sound_sort_key(sid):
  if sid.startswith('type-'):
    return (0, sid)
  if sid.startswith('error-'):
    return (1, sid)
  return (2, sid)


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
  ids = list_sound_ids()
  return ids[0] if ids else ''


def default_typing_error_sound_id():
  if resolve_sound_path(_DEFAULT_ERROR_SOUND):
    return _DEFAULT_ERROR_SOUND
  return ''


class _OggBurstPlayer:
  """Low-overlap OGG playback via a small QMediaPlayer pool."""

  def __init__(self, pool=3, volume=_OGG_VOLUME):
    self._players = [QMediaPlayer() for _ in range(pool)]
    for p in self._players:
      p.setVolume(volume)
    self._i = 0

  def play(self, path):
    p = self._players[self._i]
    self._i = (self._i + 1) % len(self._players)
    p.setMedia(QMediaContent(QUrl.fromLocalFile(str(path.resolve()))))
    p.play()


class TypingSoundPlayer:
  """Plays independently chosen correct- and error-keystroke sounds."""

  def __init__(self):
    self._type_wav = QSoundEffect()
    self._err_wav = QSoundEffect()
    self._type_wav.setVolume(_WAV_VOLUME)
    self._err_wav.setVolume(_WAV_VOLUME)
    self._type_ogg = _OggBurstPlayer()
    self._err_ogg = _OggBurstPlayer()
    self._type_path = None
    self._err_path = None

  def configure(self, type_sound_id='', error_sound_id=''):
    self._type_path = resolve_sound_path(type_sound_id)
    self._err_path = resolve_sound_path(error_sound_id)
    self._bind_effect(self._type_wav, self._type_path)
    self._bind_effect(self._err_wav, self._err_path)

  def play_keystroke(self, correct=True):
    path = self._type_path if correct else self._err_path
    if path is None:
      return
    self._play_path(path, self._type_wav if correct else self._err_wav,
                    self._type_ogg if correct else self._err_ogg)

  def _bind_effect(self, effect, path):
    if path is None or path.suffix.lower() != '.wav':
      effect.setSource(QUrl())
      return
    effect.setSource(QUrl.fromLocalFile(str(path.resolve())))

  def _play_path(self, path, wav_fx, ogg_player):
    if path.suffix.lower() == '.wav':
      if not wav_fx.source().isEmpty():
        wav_fx.play()
      return
    ogg_player.play(path)
