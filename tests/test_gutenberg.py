import io
import shutil
import time
from pathlib import Path

from typing_program.gutenberg.catalog import (
  catalog_age_days, catalog_index_ready, catalog_notice, ensure_catalog_index,
  estimate_update_seconds, needs_catalog_update, is_catalog_stale,
  parse_catalog_csv, rebuild_index, search_books,
)
from typing_program.gutenberg.fetch import source_basename
from typing_program.gutenberg.paths import texts_dir
from typing_program.gutenberg.strip_headers import strip_headers

FIXTURES = Path(__file__).parent / 'fixtures'


def _stage_catalog(tmp_path):
  shutil.copy(FIXTURES / 'pg_catalog_sample.csv', tmp_path / 'pg_catalog.csv')
  db = tmp_path / 'catalog.sqlite'
  rebuild_index(cache_dir=tmp_path, db_path=db)
  return db


def test_estimate_update_seconds():
  secs = estimate_update_seconds()
  assert secs >= 5


def test_strip_headers_removes_boilerplate():
  raw = (FIXTURES / 'metamorphosis_snip.txt').read_text(encoding='utf-8')
  cleaned = strip_headers(raw)
  assert 'START OF THIS PROJECT GUTENBERG' not in cleaned
  assert 'END OF THIS PROJECT GUTENBERG' not in cleaned
  assert 'Gregor Samsa' in cleaned


def test_estimate_import_seconds():
  from typing_program.gutenberg.fetch import estimate_import_seconds
  assert estimate_import_seconds() == 10


def test_parse_catalog_csv():
  text = (FIXTURES / 'pg_catalog_sample.csv').read_text(encoding='utf-8')
  books = parse_catalog_csv(text)
  ids = {b['id'] for b in books}
  assert ids == {'1', '1342', '5200', '99999'}
  pride = next(b for b in books if b['id'] == '1342')
  assert pride['title'] == 'Pride and Prejudice'
  assert 'Austen' in pride['authors']


def test_parse_catalog_csv_dedupes_ids():
  text = (FIXTURES / 'pg_catalog_dupes.csv').read_text(encoding='utf-8')
  books = parse_catalog_csv(text)
  assert len(books) == 1
  assert books[0]['title'] == 'Metamorphosis'


def test_rebuild_index_and_search(tmp_path):
  db = _stage_catalog(tmp_path)
  hits = search_books('kafka', db_path=db)
  assert len(hits) == 1
  assert hits[0]['id'] == '5200'
  assert hits[0]['title'] == 'Metamorphosis'
  assert search_books('audiobook', db_path=db) == []


def test_search_pride_and_prejudice(tmp_path):
  db = _stage_catalog(tmp_path)
  hits = search_books('pride and prejudice', db_path=db)
  assert len(hits) == 1
  assert hits[0]['id'] == '1342'


def test_rebuild_index_with_duplicate_ids(tmp_path):
  shutil.copy(FIXTURES / 'pg_catalog_dupes.csv', tmp_path / 'pg_catalog.csv')
  assert rebuild_index(cache_dir=tmp_path) == 1


def test_needs_update_when_index_empty(tmp_path, monkeypatch):
  monkeypatch.setattr('typing_program.gutenberg.catalog.gutenberg_cache_dir', lambda: tmp_path)
  shutil.copy(FIXTURES / 'pg_catalog_sample.csv', tmp_path / 'pg_catalog.csv')
  db_path = tmp_path / 'catalog.sqlite'
  import sqlite3
  conn = sqlite3.connect(str(db_path))
  conn.execute('create table book (id text, type text, title text, language text, authors text)')
  conn.commit(); conn.close()
  assert catalog_index_ready(tmp_path) is False
  assert needs_catalog_update(tmp_path) is True
  msg, secs, download = catalog_notice(tmp_path)
  assert msg == 'Search index missing.'
  assert download is False
  assert ensure_catalog_index(tmp_path) is True
  assert catalog_index_ready(tmp_path) is True
  assert search_books('kafka', db_path=db_path) != []


def test_catalog_stale_when_missing(tmp_path, monkeypatch):
  monkeypatch.setattr('typing_program.gutenberg.catalog.gutenberg_cache_dir', lambda: tmp_path)
  assert is_catalog_stale(tmp_path) is True
  assert catalog_age_days(tmp_path) is None


def test_catalog_stale_by_age(tmp_path, monkeypatch):
  monkeypatch.setattr('typing_program.gutenberg.catalog.gutenberg_cache_dir', lambda: tmp_path)
  shutil.copy(FIXTURES / 'pg_catalog_sample.csv', tmp_path / 'pg_catalog.csv')
  old = time.time() - (8 * 86400)
  import os
  os.utime(tmp_path / 'pg_catalog.csv', (old, old))
  assert is_catalog_stale(tmp_path) is True


def test_source_basename():
  assert source_basename('Austen, Jane', 'Pride and Prejudice') == 'Austen, Jane - Pride and Prejudice.txt'


def test_write_book_file(tmp_path, monkeypatch):
  from typing_program.gutenberg import fetch as gf
  from typing_program.gutenberg import paths as gp
  monkeypatch.setattr(gp, 'DATA_DIR', tmp_path)
  raw = (FIXTURES / 'metamorphosis_snip.txt').read_text(encoding='utf-8')

  def fake_open(url, timeout=120):
    return io.BytesIO(raw.encode('utf-8'))

  source, path = gf.write_book_file('5200', 'Kafka, Franz', 'Metamorphosis', opener=fake_open)
  assert source == 'Kafka, Franz - Metamorphosis.txt'
  assert path == texts_dir() / source
  assert path.is_file()
  text = path.read_text(encoding='utf-8')
  assert 'Gregor Samsa' in text
  assert 'START OF THIS PROJECT GUTENBERG' not in text
