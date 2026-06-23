import time
import os
import sys
import logging
import argparse
import platform
from pathlib import Path

AMPH_DIR = Path(__file__).parent
DATA_DIR = AMPH_DIR / 'data'

if not (AMPH_DIR / 'VERSION').is_file():
  raise RuntimeError(f"file {(AMPH_DIR / 'VERSION')} not found")
if not DATA_DIR.is_dir():
  raise RuntimeError(f"directory {DATA_DIR} not found")

with (AMPH_DIR / 'VERSION').open('rt') as f:
  __version__ = f.read().strip()

def _env_true(s):
  if not s:
    return False
  if s.isdigit():
    return bool(int(s))
  return True

# Hook here to parse arguments. This needs to be done before loading settings in
# QT.

def _args_and_env():

  p = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description="Advanced type training program built with Python and Qt5.",
    epilog="""Amphetype also detects the following environment variables:

AMPH_LOGFILE   specifies a file to log info/errors/warning to. If set to "-",
               stdout will be used instead. Equivalent to the "-L" argument.
AMPH_SETTINGS  specifies the settings file. Equivalent to "-s" argument.
AMPH_LOCAL     setting this to "1" is the same as specifying "-l".
""")
  p.add_argument('-l', '--local', action='store_true',
                 help=f"""uses the local data directory ({DATA_DIR}) for database and
                 settings. Useful for running a "portable" instance that stores all
                 files locally instead of in user home directory.""")
  p.add_argument('-d', '--database', metavar='DBFILE',
                 help='uses the database file %(metavar)s')
  p.add_argument('-s', '--settings', metavar='INIFILE',
                 help="uses settings file %(metavar)s")
  p.add_argument('-L', '--log', metavar='LOGFILE',
                 help="""enables logging to the given file; use "-" to log to stdout""")
  p.add_argument('-V', '--version', action='version', version=f'amphetype {__version__}')
  p.add_argument('--skip-license', action='store_true',
                 help='skip Lemon Squeezy license check (dev only)')

  # parse_known_args() because there might be QT arguments?
  args, _ = p.parse_known_args()

  args.settings = args.settings or os.environ.get('AMPH_SETTINGS')
  args.local = args.local or _env_true(os.environ.get('AMPH_LOCAL'))
  args.skip_license = args.skip_license or _env_true(os.environ.get('TYPING_PROGRAM_SKIP_LICENSE'))

  logfile = args.log or os.environ.get('AMPH_LOGFILE')
  logargs = dict(level=logging.DEBUG)
  if logfile == '-':
    logargs['stream'] = sys.stdout
  elif not logfile:
    logargs['level'] = logging.ERROR

  logging.basicConfig(format='%(asctime)s :: %(levelname)s :: %(message)s',
                      **logargs)

  return args

cli_options = _args_and_env()

# Define a timer to use.
if sys.hexversion < 0x30a0000 and platform.system() == "Windows":
  # hack hack, hackity hack
  timer = time.clock
  timer()
else:
  timer = time.perf_counter

logging.info(f'Starting Amphetype v%s on (%s, %08x)',
             __version__, platform.system(), sys.hexversion)

__all__ = (
  '__version__', # NB! Forced export of __version__.
  'AMPH_DIR',
  'DATA_DIR',
  'cli_options',
  'timer',
)
