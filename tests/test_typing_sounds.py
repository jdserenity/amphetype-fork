"""Tests for typing keystroke sounds."""

import pytest

pytest.importorskip('PyQt5')

from amphetype.typing_sounds import (
  TypingSoundPlayer,
  default_typing_error_sound_id,
  default_typing_sound_id,
  format_sound_label,
  list_sound_ids,
  resolve_sound_path,
  sounds_directory,
)


def test_sounds_directory_exists():
  d = sounds_directory()
  assert d.is_dir()


def test_list_sound_ids_filtered_by_category():
  types = list_sound_ids('type')
  errors = list_sound_ids('error')
  spaces = list_sound_ids('space')
  assert 'type-1' in types
  assert 'type-2' in types
  assert 'error-1' in errors
  assert 'space-1' in spaces
  assert 'error-1' not in types
  assert 'type-4' not in errors
  assert 'space-1' not in types


def test_resolve_sound_path_finds_wav_and_ogg():
  assert resolve_sound_path('error-1') is not None
  assert resolve_sound_path('type-1') is not None
  assert resolve_sound_path('type-1').suffix.lower() == '.wav'
  assert resolve_sound_path('') is None
  assert resolve_sound_path('missing-sound') is None


def test_default_sound_ids():
  types = list_sound_ids('type')
  errors = list_sound_ids('error')
  if 'type-1' in types:
    assert default_typing_sound_id() == 'type-1'
  else:
    assert default_typing_sound_id() in types or default_typing_sound_id() == ''
  if 'error-1' in errors:
    assert default_typing_error_sound_id() == 'error-1'


def test_format_sound_label():
  assert format_sound_label('type-1') == 'type 1'


def test_typing_sound_player_plays_float_wav_error(qapp):
  player = TypingSoundPlayer()
  player.configure('type-1', 'error-1', volume=50)
  player.play_keystroke(False, 'x')


def test_typing_sound_player_space_sound(qapp):
  player = TypingSoundPlayer()
  player.configure('type-1', '', 'space-1', 50)
  player.play_keystroke(True, ' ')
  player.play_keystroke(True, 'a')


def test_typing_sound_player_independent_type_and_error(qapp):
  player = TypingSoundPlayer()
  player.configure('type-1', '', volume=50)
  player.play_keystroke(True, 'x')
  player.play_keystroke(False, 'x')

  player.configure('', 'error-2', volume=50)
  player.play_keystroke(True, 'x')
  player.play_keystroke(False, 'x')

  player.configure('type-2', 'error-1', 'space-1', 60)
  player.play_keystroke(True, 'x')
  player.play_keystroke(False, 'x')
  player.play_keystroke(True, ' ')


def test_typing_sound_player_disabled_when_all_empty(qapp):
  player = TypingSoundPlayer()
  player.configure('', '', '', 50)
  player.play_keystroke(True, 'x')
  player.play_keystroke(False, 'x')
  player.play_keystroke(True, ' ')
