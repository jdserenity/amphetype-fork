#!/usr/bin/env python3
import io, re, zipfile, urllib.request

ZIP_URL = 'https://gutenberg.net.au/MARC-FILES-PGA.zip'

def fetch_zip():
  req = urllib.request.Request(ZIP_URL, headers={'User-Agent': 'Mozilla/5.0'})
  with urllib.request.urlopen(req, timeout=60) as r:
    return r.read()

def list_mrc(data):
  zf = zipfile.ZipFile(io.BytesIO(data))
  names = [n for n in zf.namelist() if n.lower().endswith('.mrc')]
  print('ZIP_URL:', ZIP_URL)
  print('ZIP_ENTRIES:', zf.namelist())
  print('MRC_FILES:', names)
  return zf, names

def marc_fields(blob):
  # ISO 2709-ish: leader + fields; subfields after \x1f, field tags are 3 digits
  text = blob.decode('utf-8', errors='replace')
  fields = {}
  for m in re.finditer(r'\x1e(\d{3})\x1f([^\x1e\x1d]+)', text):
    tag, rest = m.group(1), m.group(2)
    subs = {}
    for sm in re.finditer(r'([a-z0-9])\x1f([^\x1f\x1e\x1d]*)', '\x1f' + rest):
      subs[sm.group(1)] = (subs.get(sm.group(1), '') + ' ' + sm.group(2)).strip()
    fields.setdefault(tag, []).append(subs)
  return fields

def find_animal_farm(zf, names):
  for name in names:
    blob = zf.read(name)
    text = blob.decode('utf-8', errors='replace')
    if 'Animal Farm' in text or 'animal farm' in text.lower():
      fields = marc_fields(blob)
      print('\nFOUND_IN:', name)
      for tag in ('100', '245', '856'):
        print(f'  {tag}:', fields.get(tag))
      # show a short raw snippet around Animal Farm
      i = text.lower().find('animal farm')
      if i >= 0:
        print('  SNIPPET:', repr(text[max(0, i-80):i+120]))
      return
  print('\nAnimal Farm not found in MARC files')

if __name__ == '__main__':
  data = fetch_zip()
  print('ZIP_BYTES:', len(data))
  zf, names = list_mrc(data)
  find_animal_farm(zf, names)
