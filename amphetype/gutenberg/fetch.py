import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

from amphetype.gutenberg.paths import texts_dir
from amphetype.gutenberg.strip_headers import strip_aus_headers, strip_headers

TEXT_URL = 'https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt'
_BAD_CHARS = re.compile(r'[\\/:*?"<>|]+')
def estimate_import_seconds(region='us'):
  return 10


class _HTMLText(HTMLParser):
  def __init__(self):
    super().__init__()
    self._bits = []
    self._skip = False

  def handle_starttag(self, tag, attrs):
    t = tag.lower()
    if t in ('script', 'style'):
      self._skip = True
    elif t in ('p', 'br', 'div', 'h1', 'h2', 'h3', 'li', 'tr'):
      self._bits.append('\n')

  def handle_endtag(self, tag):
    if tag.lower() in ('script', 'style'):
      self._skip = False

  def handle_data(self, data):
    if not self._skip:
      self._bits.append(data)

  def text(self):
    return re.sub(r'\n{3,}', '\n\n', ''.join(self._bits))


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


def html_to_text(html):
  p = _HTMLText()
  p.feed(html)
  return p.text()


def _fetch_url(url, opener=None):
  open_fn = opener or urllib.request.urlopen
  try:
    with open_fn(url, timeout=120) as resp:
      return resp.read()
  except urllib.error.HTTPError as e:
    raise RuntimeError(f'Could not download {url} ({e.code})') from e
  except urllib.error.URLError as e:
    raise RuntimeError(f'Could not download {url} ({e.reason})') from e


def download_us_book_text(book_id, opener=None):
  raw = _fetch_url(text_url(book_id), opener=opener)
  text = _decode_bytes(raw)
  cleaned = strip_headers(text)
  if not cleaned.strip():
    raise RuntimeError(f'US ebook #{book_id} has no text after cleaning')
  return cleaned


def _aus_candidate_urls(url):
  url = url.strip()
  urls = [url]
  if url.lower().endswith('.txt'):
    base = url[:-4]
    urls.append(base + 'h.html')
    urls.append(base + '.html')
  return urls


def download_aus_book_text(url, opener=None):
  last_err = None
  for u in _aus_candidate_urls(url):
    try:
      raw = _fetch_url(u, opener=opener)
    except RuntimeError as e:
      last_err = e
      continue
    text = html_to_text(_decode_bytes(raw)) if u.lower().endswith(('.html', '.htm')) else _decode_bytes(raw)
    cleaned = strip_aus_headers(text)
    if cleaned.strip():
      return cleaned
    last_err = RuntimeError(f'AUS ebook at {u} has no text after cleaning')
  raise last_err or RuntimeError(f'Could not download AUS ebook from {url}')


def download_book_text(book_id, region='us', url=None, opener=None):
  if region == 'aus':
    if not url:
      raise RuntimeError('AUS ebook URL missing')
    return download_aus_book_text(url, opener=opener)
  return download_us_book_text(book_id, opener=opener)


def write_book_file(book_id, authors, title, region='us', url=None, text=None, opener=None):
  if text is None:
    text = download_book_text(book_id, region=region, url=url, opener=opener)
  fname = source_basename(authors, title)
  path = texts_dir() / fname
  with path.open('w', encoding='utf-8', newline='\n') as f:
    f.write(text)
  return fname, path
