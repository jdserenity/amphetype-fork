# Build Typing Program one-folder bundle on Windows, then wrap in .zip for distribution.
# Run on Windows only. Output: dist/Typing Program-win.zip
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if ($env:OS -ne 'Windows_NT') {
  Write-Error 'build-windows.ps1 must run on Windows (PyInstaller builds for the host OS).'
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Error 'uv not found. Install it first: https://docs.astral.sh/uv/'
}

uv venv venv --python 3.11
& .\venv\Scripts\Activate.ps1

uv pip install -r requirements.txt
uv pip install -e .
uv pip install pyinstaller pillow

pyinstaller typing_program.spec --noconfirm --clean

python scripts/release_archive.py windows
