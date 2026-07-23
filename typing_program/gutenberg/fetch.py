import re
import urllib.error

from typing_program.gutenberg.paths import texts_dir
from typing_program.https import urlopen as https_urlopen
from typing_program.gutenberg.strip_headers import strip_headers

TEXT_URL = 'https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt'
_BAD_CHARS = re.compile(r'[\\/:*?"<>|]+')


def estimate_import_seconds():
  return 10 # 🤦‍♂️


def text_url(book_id):
  return TEXT_URL.format(id=int(book_id))


def source_basename(authors, title):
  author = (authors or 'Unknown').split(';')[0].strip() or 'Unknown'
  name = f'{author} - {title}.txt'
  return _BAD_CHARS.sub('', name).strip() or f'Gutenberg {title}.txt'


def _decode_bytes(raw):
  for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
    try:
      return raw.decode(enc)
    except UnicodeDecodeError:
      pass
  raise RuntimeError('Could not decode ebook text')


def _fetch_url(url, opener=None):
  open_fn = opener or https_urlopen
  try:
    with open_fn(url, timeout=120) as resp:
      return resp.read()
  except urllib.error.HTTPError as e:
    raise RuntimeError(f'Could not download {url} ({e.code})') from e
  except urllib.error.URLError as e:
    raise RuntimeError(f'Could not download {url} ({e.reason})') from e


def download_book_text(book_id, opener=None):
  raw = _fetch_url(text_url(book_id), opener=opener)
  text = _decode_bytes(raw)
  cleaned = strip_headers(text)
  if not cleaned.strip():
    raise RuntimeError(f'ebook #{book_id} has no text after cleaning')
  return cleaned


def write_book_file(book_id, authors, title, text=None, opener=None):
  if text is None:
    text = download_book_text(book_id, opener=opener)
  fname = source_basename(authors, title)
  path = texts_dir() / fname
  with path.open('w', encoding='utf-8', newline='\n') as f:
    f.write(text)
  return fname, path
