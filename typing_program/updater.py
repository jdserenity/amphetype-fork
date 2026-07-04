import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from typing_program import __version__
from typing_program.https import urlopen as https_urlopen
from typing_program.license import license_bypassed, stored_license

DEFAULT_UPDATE_API = 'https://typing-program.pages.dev/api/check-update'
APP_NAME = 'Typing Program'


class UpdateError(Exception):
  pass


class UpdateNetworkError(UpdateError):
  pass


def update_api_url():
  return os.environ.get('TYPING_PROGRAM_UPDATE_API', DEFAULT_UPDATE_API).rstrip('/')


def current_platform():
  return sys.platform


def parse_version(s):
  parts = (s or '').strip().split('.')
  if not parts or not all(p.isdigit() for p in parts):
    raise UpdateError(f'invalid version: {s!r}')
  return tuple(int(p) for p in parts)


def is_newer(available, current):
  return parse_version(available) > parse_version(current)


def is_frozen():
  return bool(getattr(sys, 'frozen', False))


def install_target_path():
  exe = Path(sys.executable).resolve()
  if sys.platform == 'darwin':
    return exe.parent.parent.parent
  return exe.parent


def check_for_update(settings, current_version=None, opener=None):
  if license_bypassed():
    raise UpdateError('updates are disabled in dev mode (--skip-license)')
  key, instance_id = stored_license(settings)
  if not key or not instance_id:
    raise UpdateError('activate your license before checking for updates')
  body = json.dumps({
    'license_key': key,
    'instance_id': instance_id,
    'platform': current_platform(),
    'current_version': current_version or __version__,
  }).encode('utf-8')
  open_fn = opener or https_urlopen
  req = urllib.request.Request(
    update_api_url(),
    data=body,
    headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
    method='POST',
  )
  try:
    with open_fn(req, timeout=60) as resp:
      raw = resp.read().decode('utf-8')
  except urllib.error.HTTPError as e:
    raw = e.read().decode('utf-8', errors='replace')
    try:
      err = json.loads(raw).get('error', raw)
    except json.JSONDecodeError:
      err = raw or f'update server error ({e.code})'
    raise UpdateNetworkError(err) from e
  except urllib.error.URLError as e:
    raise UpdateNetworkError(str(e.reason or e)) from e
  try:
    data = json.loads(raw)
  except json.JSONDecodeError as e:
    raise UpdateError('invalid response from update server') from e
  if not data.get('update_available'):
    return {'update_available': False}
  for field in ('version', 'sha256', 'download_url'):
    if not data.get(field):
      raise UpdateError(f'update server response missing {field}')
  return data


def download_file(url, dest, opener=None, progress_cb=None):
  open_fn = opener or https_urlopen
  req = urllib.request.Request(url, headers={'Accept': 'application/octet-stream'})
  try:
    with open_fn(req, timeout=600) as resp:
      total = int(resp.headers.get('Content-Length') or 0)
      done = 0
      with Path(dest).open('wb') as out:
        while True:
          chunk = resp.read(1024 * 256)
          if not chunk:
            break
          out.write(chunk)
          done += len(chunk)
          if progress_cb:
            progress_cb(done, total)
  except urllib.error.URLError as e:
    raise UpdateNetworkError(str(e.reason or e)) from e


def verify_sha256(path, expected_hex):
  h = hashlib.sha256()
  with Path(path).open('rb') as f:
    for chunk in iter(lambda: f.read(1024 * 256), b''):
      h.update(chunk)
  got = h.hexdigest().lower()
  want = (expected_hex or '').strip().lower()
  if got != want:
    raise UpdateError('download failed integrity check (hash mismatch)')


def extract_archive(archive_path, dest_dir):
  dest = Path(dest_dir)
  dest.mkdir(parents=True, exist_ok=True)
  name = Path(archive_path).name.lower()
  if name.endswith('.zip'):
    with zipfile.ZipFile(archive_path) as zf:
      zf.extractall(dest)
    return dest
  if name.endswith('.tar.gz') or name.endswith('.tgz'):
    with tarfile.open(archive_path, 'r:gz') as tf:
      tf.extractall(dest)
    return dest
  raise UpdateError(f'unsupported update archive: {archive_path}')


def find_payload_root(extracted_dir, plat=None):
  root = Path(extracted_dir)
  plat = plat or current_platform()
  if plat == 'darwin':
    for p in root.rglob('*.app'):
      if p.name == f'{APP_NAME}.app':
        return p
    raise UpdateError(f'{APP_NAME}.app not found in update archive')
  for p in root.rglob(APP_NAME):
    if p.is_dir() and ((p / f'{APP_NAME}.exe').is_file() or (p / APP_NAME).is_file()):
      return p
  raise UpdateError(f'{APP_NAME} folder not found in update archive')


def _write_mac_installer(script_path, pid, target_app, staging_app):
  script = f"""#!/bin/bash
set -e
PID={pid}
TARGET={shlex_quote(str(target_app))}
STAGING={shlex_quote(str(staging_app))}
while kill -0 "$PID" 2>/dev/null; do sleep 0.5; done
sleep 1
rm -rf "$TARGET"
ditto "$STAGING" "$TARGET"
open "$TARGET"
"""
  Path(script_path).write_text(script, encoding='utf-8')
  os.chmod(script_path, 0o755)


def _write_linux_installer(script_path, pid, target_dir, staging_dir):
  script = f"""#!/bin/bash
set -e
PID={pid}
TARGET={shlex_quote(str(target_dir))}
STAGING={shlex_quote(str(staging_dir))}
while kill -0 "$PID" 2>/dev/null; do sleep 0.5; done
sleep 1
rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -a "$STAGING/." "$TARGET/"
exec "$TARGET/{APP_NAME}"
"""
  Path(script_path).write_text(script, encoding='utf-8')
  os.chmod(script_path, 0o755)


def _write_windows_installer(script_path, pid, target_dir, staging_dir):
  script = f"""$ErrorActionPreference = 'Stop'
$pidToWait = {pid}
$target = {ps_quote(str(target_dir))}
$staging = {ps_quote(str(staging_dir))}
while (Get-Process -Id $pidToWait -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 500 }}
Start-Sleep -Seconds 1
if (Test-Path $target) {{ Remove-Item -Recurse -Force $target }}
Copy-Item -Recurse $staging $target
Start-Process (Join-Path $target '{APP_NAME}.exe')
"""
  Path(script_path).write_text(script, encoding='utf-8')


def shlex_quote(s):
  if not s:
    return "''"
  if all(c.isalnum() or c in '/._-:' for c in s):
    return s
  return "'" + s.replace("'", "'\"'\"'") + "'"


def ps_quote(s):
  return "'" + s.replace("'", "''") + "'"


def launch_installer(staging_payload, work_dir=None):
  if not is_frozen():
    raise UpdateError('in-app updates only work in the installed app (not dev mode)')
  target = install_target_path()
  pid = os.getpid()
  work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix='typing-program-update-'))
  work.mkdir(parents=True, exist_ok=True)
  plat = current_platform()
  if plat == 'darwin':
    script = work / 'install-update.sh'
    _write_mac_installer(script, pid, target, staging_payload)
    subprocess.Popen([str(script)], cwd=str(work), start_new_session=True)
  elif plat == 'win32':
    script = work / 'install-update.ps1'
    _write_windows_installer(script, pid, target, staging_payload)
    subprocess.Popen(
      ['powershell', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
      cwd=str(work),
      creationflags=getattr(subprocess, 'DETACHED_PROCESS', 0),
    )
  else:
    script = work / 'install-update.sh'
    _write_linux_installer(script, pid, target, staging_payload)
    subprocess.Popen([str(script)], cwd=str(work), start_new_session=True)
  return True


def apply_downloaded_update(archive_path, sha256_hex):
  verify_sha256(archive_path, sha256_hex)
  work = Path(tempfile.mkdtemp(prefix='typing-program-update-'))
  try:
    extract_archive(archive_path, work / 'extracted')
    payload = find_payload_root(work / 'extracted')
    staging = work / 'staging'
    shutil.copytree(payload, staging, symlinks=True)
    launch_installer(staging, work_dir=work)
  except Exception:
    shutil.rmtree(work, ignore_errors=True)
    raise
  return True
