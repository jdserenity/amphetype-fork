"""Tests for typing keystroke sounds."""

import pytest

pytest.importorskip('PyQt5')

from amphetype.typing_sounds import (
  TypingSoundPlayer,
  default_typing_sound_id,
  format_sound_label,
  list_sound_ids,
  paired_error_sound_id,
  resolve_sound_path,
  sounds_directory,
)


def test_sounds_directory_exists():
  d = sounds_directory()
  assert d.is_dir()


def test_list_sound_ids_includes_bundled_samples():
  ids = list_sound_ids()
  assert 'type-1' in ids
  assert 'type-3' in ids
  assert 'error-1' in ids


def test_resolve_sound_path_finds_wav_and_ogg():
  assert resolve_sound_path('type-1') is not None
  assert resolve_sound_path('type-1').suffix.lower() == '.wav'
  assert resolve_sound_path('type-3') is not None
  assert resolve_sound_path('type-3').suffix.lower() == '.ogg'
  assert resolve_sound_path('') is None
  assert resolve_sound_path('missing-sound') is None


def test_paired_error_sound_id():
  assert paired_error_sound_id('type-1') == 'error-1'
  assert paired_error_sound_id('type-3') is None
  assert paired_error_sound_id('error-1') is None


def test_default_typing_sound_id():
  assert default_typing_sound_id() == 'type-1'


def test_format_sound_label():
  assert format_sound_label('type-1') == 'type 1'


def test_typing_sound_player_disabled_when_empty(qapp):
  player = TypingSoundPlayer()
  player.configure('')
  player.play_keystroke()  # should not raise


def test_typing_sound_player_configures_type_sound(qapp):
  player = TypingSoundPlayer()
  player.configure('type-1')
  player.play_keystroke(True)
  player.play_keystroke(False)
