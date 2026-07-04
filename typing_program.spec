# PyInstaller build recipe for Typing Program (see docs/DEPLOY.md → Packaging).
# Build: pyinstaller typing_program.spec  (run ON the OS you are shipping for)
# Output: dist/Typing Program.app (macOS), dist/Typing Program/ (Windows/Linux).

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
import certifi

ROOT = Path(SPECPATH)
PKG = ROOT / 'typing_program'
APP_NAME = 'Typing Program'

# The app locates its files with Path(__file__).parent / 'data' and reads
# typing_program/VERSION at import; if either is missing it raises at startup.
# So we copy VERSION and the whole data/ tree back into a typing_program/ folder
# inside the frozen bundle.
datas = [(str(PKG / 'VERSION'), 'typing_program'), (certifi.where(), 'certifi')]
for p in (PKG / 'data').rglob('*'):
  if p.is_file():
    datas.append((str(p), str(Path('typing_program') / p.parent.relative_to(PKG))))

hiddenimports = collect_submodules('typing_program') + ['certifi']

a = Analysis(
  [str(PKG / 'main_entry.py')],
  pathex=[str(ROOT)],
  binaries=[],
  datas=datas,
  hiddenimports=hiddenimports,
  hookspath=[],
  runtime_hooks=[],
  excludes=['tkinter'],
  noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
  pyz,
  a.scripts,
  [],
  exclude_binaries=True,
  name=APP_NAME,
  console=False,
  icon=str(ROOT / 'typing_program.ico'),
)

coll = COLLECT(
  exe,
  a.binaries,
  a.datas,
  name=APP_NAME,
)

app = BUNDLE(
  coll,
  name=f'{APP_NAME}.app',
  icon=str(ROOT / 'typing_program.ico'),
  bundle_identifier='com.typingprogram.app',
  info_plist={
    'CFBundleShortVersionString': (PKG / 'VERSION').read_text().strip(),
    'CFBundleName': APP_NAME,
    'CFBundleDisplayName': 'Typing Program That Helps You Type Better',
    'NSHighResolutionCapable': True,
  },
)
