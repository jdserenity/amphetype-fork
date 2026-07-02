#!/usr/bin/env python3
"""Clean and peak-normalize keystroke sounds in data/sounds/.

Trims leading/trailing silence, applies a short fade-out, high-passes rumble,
then peak-normalizes to a common level.

  python scripts/normalize_typing_sounds.py

Requires ffmpeg on PATH. Re-run after adding new sound files.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOUNDS_DIR = ROOT / 'data' / 'sounds'
AUDIO_EXTS = {'.wav', '.ogg', '.mp3'}
TARGET_PEAK_DB = -6.0
SILENT_PEAK_THRESHOLD = -70.0
FADE_OUT_SEC = 0.012
TRIM_THRESHOLD_DB = -45
TRIM_MIN_SILENCE_SEC = 0.003
HIGHPASS_HZ = 100


def cleanup_audio_filter():
  """ffmpeg -af chain: trim silence tails, fade out, drop low rumble."""
  t = TRIM_THRESHOLD_DB
  s = TRIM_MIN_SILENCE_SEC
  f = FADE_OUT_SEC
  hp = HIGHPASS_HZ
  return (
    f'highpass=f={hp},'
    f'silenceremove=start_periods=1:start_silence={s}:start_threshold={t}dB:'
    f'stop_periods=-1:stop_silence={s}:stop_threshold={t}dB,'
    f'areverse,silenceremove=start_periods=1:start_silence={s}:start_threshold={t}dB,areverse,'
    f'areverse,afade=t=in:st=0:d={f},areverse'
  )


def measure_peak_db(path):
  p = subprocess.run(
    ['ffmpeg', '-hide_banner', '-i', str(path), '-af', 'volumedetect', '-f', 'null', '-'],
    capture_output=True, text=True)
  if p.returncode != 0:
    raise RuntimeError(f'ffmpeg failed for {path}:\n{p.stderr}')
  m = re.search(r'max_volume:\s*([-\d.]+)\s*dB', p.stderr)
  if not m:
    raise RuntimeError(f'no peak measurement for {path}')
  return float(m.group(1))


def measure_duration_sec(path):
  p = subprocess.run(
    ['ffprobe', '-hide_banner', '-show_entries', 'format=duration',
     '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
    capture_output=True, text=True)
  if p.returncode != 0:
    raise RuntimeError(f'ffprobe failed for {path}:\n{p.stderr}')
  return float(p.stdout.strip())


def gain_db_for_peak(current_peak_db, target=TARGET_PEAK_DB):
  if current_peak_db <= SILENT_PEAK_THRESHOLD:
    return None
  return target - current_peak_db


def _run_ffmpeg(cmd):
  p = subprocess.run(cmd, capture_output=True, text=True)
  if p.returncode != 0:
    raise RuntimeError(p.stderr)


def normalize_file(path, target=TARGET_PEAK_DB, dry_run=False):
  before_dur = measure_duration_sec(path)
  if dry_run:
    print(f'proc {path.name}: {before_dur * 1000:.0f} ms')
    return True
  tmp = path.with_name(f'{path.stem}.norm.tmp.wav')
  tmp2 = path.with_name(f'{path.stem}.norm.tmp2.wav')
  try:
    _run_ffmpeg([
      'ffmpeg', '-hide_banner', '-y', '-i', str(path),
      '-af', cleanup_audio_filter(), '-c:a', 'pcm_s16le', str(tmp),
    ])
    peak = measure_peak_db(tmp)
    gain = gain_db_for_peak(peak, target)
    if gain is None:
      print(f'skip {path.name}: near-silent after trim (peak {peak:.1f} dB)')
      return False
    _run_ffmpeg([
      'ffmpeg', '-hide_banner', '-y', '-i', str(tmp),
      '-af', f'volume={gain:.4f}dB', '-c:a', 'pcm_s16le', str(tmp2),
    ])
    after_dur = measure_duration_sec(tmp2)
    new_peak = measure_peak_db(tmp2)
    final = path.with_suffix('.wav')
    if final.exists() and final != path:
      final.unlink()
    tmp2.replace(final)
    if path != final and path.exists():
      path.unlink(missing_ok=True)
    print(
      f'ok   {final.name}: {before_dur * 1000:.0f} ms → {after_dur * 1000:.0f} ms,'
      f' peak {new_peak:.1f} dB'
    )
    return True
  finally:
    tmp.unlink(missing_ok=True)
    tmp2.unlink(missing_ok=True)


def main(argv=None):
  if not shutil.which('ffmpeg'):
    print('ffmpeg not found on PATH', file=sys.stderr)
    return 1
  dry_run = '--dry-run' in (argv or sys.argv[1:])
  if not SOUNDS_DIR.is_dir():
    print(f'missing {SOUNDS_DIR}', file=sys.stderr)
    return 1
  files = sorted(p for p in SOUNDS_DIR.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS)
  if not files:
    print(f'no audio files in {SOUNDS_DIR}')
    return 0
  changed = 0
  for path in files:
    if normalize_file(path, dry_run=dry_run):
      changed += 1
  print(
    f'done ({changed} file{"s" if changed != 1 else ""} processed,'
    f' trim + {int(FADE_OUT_SEC * 1000)} ms fade, target peak {TARGET_PEAK_DB} dB)'
  )
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
