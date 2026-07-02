#!/usr/bin/env python3
"""Peak-normalize keystroke sounds in data/sounds/ to a common level.

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


def gain_db_for_peak(current_peak_db, target=TARGET_PEAK_DB):
  if current_peak_db <= SILENT_PEAK_THRESHOLD:
    return None
  return target - current_peak_db


def normalize_file(path, target=TARGET_PEAK_DB, dry_run=False):
  peak = measure_peak_db(path)
  gain = gain_db_for_peak(peak, target)
  if gain is None:
    print(f'skip {path.name}: near-silent (peak {peak:.1f} dB)')
    return False
  if abs(gain) < 0.05:
    print(f'ok   {path.name}: peak {peak:.1f} dB (already near target)')
    return False
  print(f'norm {path.name}: peak {peak:.1f} dB → gain {gain:+.1f} dB')
  if dry_run:
    return True
  tmp = path.with_name(f'{path.stem}.norm.tmp{path.suffix}')
  ext = path.suffix.lower()
  gain_af = ['-af', f'volume={gain:.4f}dB']
  if ext == '.ogg':
    # Vorbis encoder is unavailable on many ffmpeg builds; store as WAV instead.
    tmp = path.with_name(f'{path.stem}.norm.tmp.wav')
    out_args = gain_af + ['-c:a', 'pcm_s16le']
  elif ext == '.wav':
    out_args = gain_af + ['-c:a', 'pcm_s16le']
  else:
    out_args = gain_af
  cmd = ['ffmpeg', '-hide_banner', '-y', '-i', str(path)] + out_args + [str(tmp)]
  p = subprocess.run(cmd, capture_output=True, text=True)
  if p.returncode != 0:
    tmp.unlink(missing_ok=True)
    raise RuntimeError(f'normalize failed for {path}:\n{p.stderr}')
  new_peak = measure_peak_db(tmp)
  if ext == '.ogg':
    final = path.with_suffix('.wav')
    if final.exists() and final != path:
      final.unlink()
    tmp.replace(final)
    path.unlink(missing_ok=True)
    print(f'     {path.name} → {final.name}: peak {new_peak:.1f} dB')
  else:
    tmp.replace(path)
    print(f'     {path.name}: new peak {new_peak:.1f} dB')
  return True


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
  print(f'done ({changed} file{"s" if changed != 1 else ""} adjusted, target peak {TARGET_PEAK_DB} dB)')
  return 0


if __name__ == '__main__':
  raise SystemExit(main())
