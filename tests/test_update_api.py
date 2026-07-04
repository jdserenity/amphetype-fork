
def parse_version(s):
  parts = (s or '').strip().split('.')
  if not parts or not all(p.isdigit() for p in parts):
    return None
  return tuple(int(p) for p in parts)


def is_newer(available, current):
  a = parse_version(available)
  b = parse_version(current)
  if a is None or b is None:
    return False
  return a > b


def platform_entry(manifest, platform):
  if not manifest:
    return None
  platforms = manifest.get('platforms') or {}
  return platforms.get(platform)


def pick_update(manifest, platform, current_version):
  if not manifest:
    return None
  latest = (manifest.get('version') or '').strip()
  if not latest or not is_newer(latest, current_version):
    return None
  entry = platform_entry(manifest, platform)
  if not entry or not entry.get('object_key') or not entry.get('sha256'):
    return None
  return {
    'version': latest,
    'sha256': entry['sha256'],
    'object_key': entry['object_key'],
    'release_notes': manifest.get('release_notes') or '',
  }


def test_parse_version():
  assert parse_version('1.2.3') == (1, 2, 3)
  assert parse_version('bad') is None


def test_is_newer():
  assert is_newer('1.3.0', '1.2.1') is True
  assert is_newer('1.2.1', '1.2.1') is False


def test_pick_update():
  manifest = {
    'version': '2.0.0',
    'release_notes': 'Hi',
    'platforms': {
      'darwin': {'object_key': 'releases/2.0.0/mac.zip', 'sha256': 'abc'},
    },
  }
  hit = pick_update(manifest, 'darwin', '1.0.0')
  assert hit['version'] == '2.0.0'
  assert hit['object_key'] == 'releases/2.0.0/mac.zip'
  assert pick_update(manifest, 'darwin', '2.0.0') is None
  assert pick_update(manifest, 'win32', '1.0.0') is None
