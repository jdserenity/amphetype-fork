# PyInstaller build recipe for Amphetype (see docs/DEPLOY.md → Packaging).
# Build: pyinstaller amphetype.spec  (run ON the OS you are shipping for)
# Output: dist/Amphetype.app (macOS), dist/Amphetype/ (Windows/Linux).

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)
PKG = ROOT / 'amphetype'

# The app locates its files with Path(__file__).parent / 'data' and reads
# amphetype/VERSION at import; if either is missing it raises at startup.
# So we copy VERSION and the whole data/ tree back into an amphetype/ folder
# inside the frozen bundle.
datas = [(str(PKG / 'VERSION'), 'amphetype')]
for p in (PKG / 'data').rglob('*'):
  if p.is_file():
    datas.append((str(p), str(Path('amphetype') / p.parent.relative_to(PKG))))

hiddenimports = collect_submodules('amphetype')

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
  name='Amphetype',
  console=False,
  icon=str(ROOT / 'amphetype.ico'),
)

coll = COLLECT(
  exe,
  a.binaries,
  a.datas,
  name='Amphetype',
)

app = BUNDLE(
  coll,
  name='Amphetype.app',
  icon=str(ROOT / 'amphetype.ico'),
  bundle_identifier='com.typingprogram.amphetype',
  info_plist={
    'CFBundleShortVersionString': (PKG / 'VERSION').read_text().strip(),
    'NSHighResolutionCapable': True,
  },
)
