import csv
import gzip
import io
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

from amphetype.gutenberg.aus_catalog import GUTINDEX_URL, gutindex_path, parse_gutindex_aus
from amphetype.gutenberg.paths import gutenberg_cache_dir

CATALOG_URL = 'https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv.gz'
CATALOG_STALE_DAYS = 7
COMPRESSED_CATALOG_BYTES = 5_300_000
GUTINDEX_BYTES = 2_000_000
RECORD_RE = re.compile(r'^\d+,')


def catalog_csv_path(cache_dir=None):
  return (cache_dir or gutenberg_cache_dir()) / 'pg_catalog.csv'


def catalog_db_path(cache_dir=None):
  return (cache_dir or gutenberg_cache_dir()) / 'catalog.sqlite'


def estimate_update_seconds():
  return max(5, round((COMPRESSED_CATALOG_BYTES + GUTINDEX_BYTES) / (500 * 1024)))


def _catalog_mtimes(cache_dir):
  cache_dir = cache_dir or gutenberg_cache_dir()
  times = []
  for p in (catalog_csv_path(cache_dir), gutindex_path(cache_dir)):
    if p.is_file():
      times.append(p.stat().st_mtime)
  return times


def catalog_age_days(cache_dir=None):
  times = _catalog_mtimes(cache_dir)
  if not times:
    return None
  return (time.time() - min(times)) / 86400.0


def catalog_missing(cache_dir=None):
  cache_dir = cache_dir or gutenberg_cache_dir()
  return not catalog_csv_path(cache_dir).is_file() or not gutindex_path(cache_dir).is_file()


def catalog_index_ready(cache_dir=None):
  path = catalog_db_path(cache_dir)
  if not path.is_file():
    return False
  conn = sqlite3.connect(str(path))
  try:
    n = conn.execute('select count(*) from book').fetchone()[0]
    return n > 0
  except sqlite3.Error:
    return False
  finally:
    conn.close()


def is_catalog_stale(cache_dir=None):
  age = catalog_age_days(cache_dir)
  return age is None or age > CATALOG_STALE_DAYS


def needs_catalog_update(cache_dir=None):
  if catalog_missing(cache_dir):
    return True
  if not catalog_index_ready(cache_dir):
    return True
  return is_catalog_stale(cache_dir)


def estimate_rebuild_seconds(cache_dir=None):
  cache_dir = cache_dir or gutenberg_cache_dir()
  total = 0
  for p in (catalog_csv_path(cache_dir), gutindex_path(cache_dir)):
    if p.is_file():
      total += p.stat().st_size
  if not total:
    return estimate_update_seconds()
  return max(2, round(total / (5 * 1024 * 1024)))


def catalog_notice(cache_dir=None):
  cache_dir = cache_dir or gutenberg_cache_dir()
  if catalog_missing(cache_dir):
    return 'No book catalog yet.', estimate_update_seconds(), True
  if not catalog_index_ready(cache_dir):
    return 'Search index missing.', estimate_rebuild_seconds(cache_dir), False
  if is_catalog_stale(cache_dir):
    return 'Catalog is more than 1 week old.', estimate_update_seconds(), True
  return None, 0, True


def ensure_catalog_index(cache_dir=None):
  cache_dir = cache_dir or gutenberg_cache_dir()
  if catalog_missing(cache_dir) or catalog_index_ready(cache_dir):
    return catalog_index_ready(cache_dir)
  try:
    rebuild_index(cache_dir=cache_dir)
    return True
  except Exception:
    return False


def _split_records(text):
  records = []
  current = None
  for line in text.splitlines():
    if RECORD_RE.match(line):
      if current is not None:
        records.append(current)
      current = line
    elif current is not None:
      current += '\n' + line
  if current is not None:
    records.append(current)
  return records


def parse_catalog_csv(text):
  books = []
  for rec in _split_records(text):
    try:
      row = next(csv.reader(io.StringIO(rec)))
    except (csv.Error, StopIteration):
      continue
    if len(row) < 5:
      continue
    try:
      book_id = str(int(row[0]))
    except ValueError:
      continue
    typ = row[1].strip()
    title = row[3].strip()
    language = row[4].strip()
    authors = row[5].strip() if len(row) > 5 else ''
    if not title:
      continue
    books.append(dict(region='us', id=book_id, type=typ, title=title, language=language, authors=authors, url=None))
  return _dedupe_region_ids(books)


def _dedupe_region_ids(books):
  by_id = {}
  for b in books:
    by_id[b['id']] = b
  return list(by_id.values())


def _load_books(cache_dir):
  cache_dir = Path(cache_dir)
  us = parse_catalog_csv(catalog_csv_path(cache_dir).read_text(encoding='utf-8'))
  gut = gutindex_path(cache_dir).read_text(encoding='utf-8', errors='replace')
  aus = parse_gutindex_aus(gut)
  books = us + aus
  if not books:
    raise RuntimeError('catalog files produced no books')
  return books


def rebuild_index(cache_dir=None, csv_path=None, gutindex_path_arg=None, db_path=None):
  cache_dir = Path(cache_dir or gutenberg_cache_dir())
  if csv_path is None and gutindex_path_arg is None:
    books = _load_books(cache_dir)
  else:
    books = []
    if csv_path:
      books.extend(parse_catalog_csv(Path(csv_path).read_text(encoding='utf-8')))
    if gutindex_path_arg:
      books.extend(parse_gutindex_aus(Path(gutindex_path_arg).read_text(encoding='utf-8', errors='replace')))
    if not books:
      raise RuntimeError('catalog files produced no books')
  db_path = Path(db_path or catalog_db_path(cache_dir))
  tmp = db_path.with_suffix('.tmp.sqlite')
  if tmp.is_file():
    tmp.unlink()
  conn = sqlite3.connect(str(tmp))
  try:
    conn.execute('''create table book (
      region text not null,
      id text not null,
      type text not null,
      title text not null,
      language text,
      authors text,
      url text,
      primary key (region, id)
    )''')
    conn.execute('create index book_title on book(title)')
    conn.executemany(
      'insert into book (region, id, type, title, language, authors, url) values (?, ?, ?, ?, ?, ?, ?)',
      [(b['region'], b['id'], b['type'], b['title'], b['language'], b['authors'], b['url']) for b in books],
    )
    conn.commit()
  except Exception:
    conn.close()
    tmp.unlink(missing_ok=True)
    raise
  else:
    conn.close()
  if db_path.is_file():
    db_path.unlink()
  tmp.rename(db_path)
  return len(books)


def update_catalog(cache_dir=None, opener=None):
  cache_dir = cache_dir or gutenberg_cache_dir()
  open_fn = opener or urllib.request.urlopen
  with open_fn(CATALOG_URL, timeout=180) as resp:
    catalog_csv_path(cache_dir).write_bytes(gzip.decompress(resp.read()))
  with open_fn(GUTINDEX_URL, timeout=180) as resp:
    gutindex_path(cache_dir).write_bytes(resp.read())
  return rebuild_index(cache_dir=cache_dir)


def _norm_title(title):
  t = (title or '').lower()
  t = re.sub(r'[^a-z0-9]+', ' ', t)
  t = re.sub(r'\s+', ' ', t).strip()
  if t.startswith('the '):
    t = t[3:]
  return t


def _norm_author(authors):
  a = (authors or '').split(';')[0].strip().lower()
  if ',' in a:
    return re.sub(r'[^a-z]+', '', a.split(',')[0])
  parts = re.sub(r'[^a-z\s]+', ' ', a).split()
  return parts[-1] if parts else ''


def _dup_key(title, authors):
  return _norm_title(title), _norm_author(authors)


def _merge_search_results(rows, limit):
  out = []
  keys = {}
  for region, book_id, title, authors, url in rows:
    key = _dup_key(title, authors)
    if key in keys:
      if region == 'us' and keys[key] != 'us':
        out = [r for r in out if _dup_key(r['title'], r['authors']) != key]
        keys[key] = 'us'
      else:
        continue
    else:
      keys[key] = region
    out.append(dict(region=region, id=book_id, title=title, authors=authors or '', url=url))
    if len(out) >= limit:
      break
  return out


def _search_conn(db_path=None):
  path = Path(db_path or catalog_db_path())
  if not path.is_file():
    return None
  return sqlite3.connect(str(path))


def search_books(query, limit=50, db_path=None):
  q = (query or '').strip()
  if not q:
    return []
  conn = _search_conn(db_path)
  if conn is None:
    return []
  try:
    like = f'%{q}%'
    rows = conn.execute(
      '''select region, id, title, authors, url from book
         where type = 'Text' and (title like ? collate nocase or authors like ? collate nocase)
         order by case region when 'us' then 0 else 1 end, title
         limit ?''',
      (like, like, max(limit * 4, limit)),
    ).fetchall()
    return _merge_search_results(rows, limit)
  finally:
    conn.close()
