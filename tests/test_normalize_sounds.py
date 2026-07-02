"""Regression tests for peak-normalized typing sounds."""

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOUNDS_DIR = ROOT / 'data' / 'sounds'
_SCRIPT = ROOT / 'scripts' / 'normalize_typing_sounds.py'

_spec = importlib.util.spec_from_file_location('normalize_typing_sounds', _SCRIPT)
_norm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_norm)


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg required')
def test_bundled_sounds_peak_normalized():
  files = [p for p in SOUNDS_DIR.iterdir() if p.is_file() and p.suffix.lower() in _norm.AUDIO_EXTS]
  assert files, 'expected bundled sounds under data/sounds'
  for path in files:
    peak = _norm.measure_peak_db(path)
    assert _norm.TARGET_PEAK_DB - 1.5 <= peak <= _norm.TARGET_PEAK_DB + 0.5, (
      f'{path.name} peak {peak:.1f} dB, expected near {_norm.TARGET_PEAK_DB} dB'
    )


def test_gain_db_for_peak_silent():
  assert _norm.gain_db_for_peak(-91.0) is None


def test_gain_db_for_peak_target():
  assert _norm.gain_db_for_peak(-12.0) == pytest.approx(6.0)


def test_cleanup_audio_filter_includes_trim_and_fade():
  af = _norm.cleanup_audio_filter()
  assert 'silenceremove' in af
  assert 'afade' in af
  assert 'highpass' in af


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg required')
def test_bundled_error_sound_is_short():
  src = SOUNDS_DIR / 'error-1.wav'
  if not src.is_file():
    pytest.skip('error-1.wav not bundled')
  assert _norm.measure_duration_sec(src) < 0.15


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg required')
def test_trim_shortens_padded_sample(tmp_path):
  src = SOUNDS_DIR / 'type-1.wav'
  if not src.is_file():
    pytest.skip('type-1.wav not bundled')
  padded = tmp_path / 'padded.wav'
  _norm._run_ffmpeg([
    'ffmpeg', '-hide_banner', '-y', '-i', str(src),
    '-af', 'apad=pad_dur=0.4', '-c:a', 'pcm_s16le', str(padded),
  ])
  before = _norm.measure_duration_sec(padded)
  _norm.normalize_file(padded)
  after = _norm.measure_duration_sec(padded)
  assert before > 0.3
  assert after < before * 0.6
