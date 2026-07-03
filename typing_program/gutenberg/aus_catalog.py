import re

GUTINDEX_URL = 'https://www.gutenberg.org/dirs/GUTINDEX.AUS'
AUS_HOST = 'gutenberg.net.au'
URL_RE = re.compile(r'^\s*(https?://(?:www\.)?gutenberg\.net\.au/\S+)', re.I)
MONTH_YEAR_RE = re.compile(
  r'^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|'
  r'Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\s+',
  re.I,
)
BRACKET_TAIL_RE = re.compile(r'\s*\[[^\]]+\].*$')
EBOOK_ID_RE = re.compile(r'/(\d{5,8})[a-z]?\.(?:txt|html?|pdf)', re.I)


def gutindex_path(cache_dir):
  return cache_dir / 'gutindex.aus'


def _aus_id_from_url(url):
  m = EBOOK_ID_RE.search(url)
  return m.group(1) if m else None


def _prefer_txt_url(url):
  url = url.rstrip('\\').strip()
  if url.lower().endswith('.txt'):
    return url
  if url.lower().endswith('h.html'):
    return url[:-6] + '.txt'
  if url.lower().endswith('.html'):
    base = url.rsplit('.', 1)[0]
    if base.endswith('h'):
      base = base[:-1]
    return base + '.txt'
  return url


def _parse_entry_block(block):
  text = ' '.join(l.strip() for l in block if l.strip())
  if not text:
    return None, None
  text = MONTH_YEAR_RE.sub('', text)
  text = BRACKET_TAIL_RE.sub('', text).strip()
  lower = text.lower()
  if ', by ' in lower:
    i = lower.rfind(', by ')
    return text[:i].strip(), text[i + 5:].strip()
  # "Title, Author" when author looks like a name at end
  if ', ' in text:
    title, author = text.rsplit(', ', 1)
    if author and not author[0].isdigit():
      return title.strip(), author.strip()
  return text, ''


def parse_gutindex_aus(text):
  books = []
  block = []
  for line in text.splitlines():
    m = URL_RE.match(line)
    if m:
      url = m.group(1)
      if '.pdf' in url.lower():
        block = []
        continue
      title, authors = _parse_entry_block(block)
      block = []
      if not title:
        continue
      book_id = _aus_id_from_url(url)
      if not book_id:
        continue
      books.append(dict(
        region='aus', id=book_id, type='Text', title=title, language='en',
        authors=authors, url=_prefer_txt_url(url),
      ))
      continue
    s = line.strip()
    if not s or s.startswith('~') or s.startswith('***') or s.startswith('--'):
      continue
    if s.startswith('http://') or s.startswith('https://'):
      continue
    if MONTH_YEAR_RE.match(s):
      if block:
        block = [s]
      else:
        block.append(s)
    elif block:
      block.append(s)
  return _dedupe_aus(books)


def _dedupe_aus(books):
  by_id = {}
  for b in books:
    key = (b['id'], b['url'].lower())
    prev = by_id.get(b['id'])
    if prev is None or b['url'].lower().endswith('.txt'):
      by_id[b['id']] = b
  return list(by_id.values())
