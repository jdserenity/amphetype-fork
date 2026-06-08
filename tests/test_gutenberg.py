import io
import shutil
import time
from pathlib import Path

import pytest

from amphetype.gutenberg.aus_catalog import parse_gutindex_aus
from amphetype.gutenberg.catalog import (
  catalog_age_days, catalog_index_ready, catalog_notice, ensure_catalog_index,
  estimate_update_seconds, needs_catalog_update, is_catalog_stale,
  parse_catalog_csv, rebuild_index, search_books,
)
from amphetype.gutenberg.fetch import source_basename
from amphetype.gutenberg.paths import texts_dir
from amphetype.gutenberg.strip_headers import strip_aus_headers, strip_headers

FIXTURES = Path(__file__).parent / 'fixtures'


def _stage_catalog(tmp_path):
  shutil.copy(FIXTURES / 'pg_catalog_sample.csv', tmp_path / 'pg_catalog.csv')
  shutil.copy(FIXTURES / 'gutindex_aus_sample.txt', tmp_path / 'gutindex.aus')
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


def test_strip_aus_headers_removes_pga_boilerplate():
  raw = (FIXTURES / 'nineteen_eighty_four_aus_snip.txt').read_text(encoding='utf-8')
  cleaned = strip_aus_headers(raw)
  assert 'Project Gutenberg Australia' not in cleaned
  assert 'do NOT keep any eBooks in compliance' not in cleaned
  assert cleaned.startswith('PART ONE')
  assert 'It was a bright cold day in April' in cleaned


def test_strip_aus_headers_chapter_roman_numeral():
  raw = (FIXTURES / 'animal_farm_aus_snip.txt').read_text(encoding='utf-8')
  cleaned = strip_aus_headers(raw)
  assert 'Project Gutenberg Australia' not in cleaned
  assert cleaned.startswith('Chapter I')
  assert 'Mr. Jones, of the Manor Farm' in cleaned


def test_estimate_import_seconds():
  from amphetype.gutenberg.fetch import estimate_import_seconds
  assert estimate_import_seconds('us') == 10
  assert estimate_import_seconds('aus') == 10


def test_parse_catalog_csv():
  text = (FIXTURES / 'pg_catalog_sample.csv').read_text(encoding='utf-8')
  books = parse_catalog_csv(text)
  ids = {b['id'] for b in books}
  assert ids == {'1', '1342', '5200', '99999'}
  pride = next(b for b in books if b['id'] == '1342')
  assert pride['title'] == 'Pride and Prejudice'
  assert pride['region'] == 'us'
  assert 'Austen' in pride['authors']


def test_parse_gutindex_aus():
  text = (FIXTURES / 'gutindex_aus_sample.txt').read_text(encoding='utf-8')
  books = parse_gutindex_aus(text)
  titles = {b['title'] for b in books}
  assert 'Animal Farm' in titles
  assert 'Nineteen eighty-four' in titles
  orwell = next(b for b in books if b['title'] == 'Animal Farm')
  assert orwell['region'] == 'aus'
  assert orwell['url'].endswith('0100011.txt')


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
  assert hits[0]['region'] == 'us'
  assert search_books('audiobook', db_path=db) == []


def test_search_merges_us_and_aus_orwell(tmp_path):
  db = _stage_catalog(tmp_path)
  hits = search_books('orwell', db_path=db)
  titles = {h['title'] for h in hits}
  assert 'Animal Farm' in titles
  assert 'Nineteen eighty-four' in titles
  assert all(h['region'] == 'aus' for h in hits)


def test_search_prefers_us_duplicate_title(tmp_path):
  db = _stage_catalog(tmp_path)
  hits = search_books('pride and prejudice', db_path=db)
  assert len(hits) == 1
  assert hits[0]['region'] == 'us'
  assert hits[0]['id'] == '1342'


def test_rebuild_index_with_duplicate_ids(tmp_path):
  shutil.copy(FIXTURES / 'pg_catalog_dupes.csv', tmp_path / 'pg_catalog.csv')
  shutil.copy(FIXTURES / 'gutindex_aus_sample.txt', tmp_path / 'gutindex.aus')
  assert rebuild_index(cache_dir=tmp_path) >= 4


def test_needs_update_when_index_empty(tmp_path, monkeypatch):
  monkeypatch.setattr('amphetype.gutenberg.catalog.gutenberg_cache_dir', lambda: tmp_path)
  shutil.copy(FIXTURES / 'pg_catalog_sample.csv', tmp_path / 'pg_catalog.csv')
  shutil.copy(FIXTURES / 'gutindex_aus_sample.txt', tmp_path / 'gutindex.aus')
  db_path = tmp_path / 'catalog.sqlite'
  import sqlite3
  conn = sqlite3.connect(str(db_path))
  conn.execute('create table book (region text, id text, type text, title text, language text, authors text, url text)')
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
  monkeypatch.setattr('amphetype.gutenberg.catalog.gutenberg_cache_dir', lambda: tmp_path)
  assert is_catalog_stale(tmp_path) is True
  assert catalog_age_days(tmp_path) is None


def test_catalog_stale_by_age(tmp_path, monkeypatch):
  monkeypatch.setattr('amphetype.gutenberg.catalog.gutenberg_cache_dir', lambda: tmp_path)
  shutil.copy(FIXTURES / 'pg_catalog_sample.csv', tmp_path / 'pg_catalog.csv')
  shutil.copy(FIXTURES / 'gutindex_aus_sample.txt', tmp_path / 'gutindex.aus')
  old = time.time() - (8 * 86400)
  import os
  for name in ('pg_catalog.csv', 'gutindex.aus'):
    p = tmp_path / name
    os.utime(p, (old, old))
  assert is_catalog_stale(tmp_path) is True


def test_source_basename():
  assert source_basename('Austen, Jane', 'Pride and Prejudice') == 'Austen, Jane - Pride and Prejudice.txt'


def test_write_book_file(tmp_path, monkeypatch):
  from amphetype.gutenberg import fetch as gf
  from amphetype.gutenberg import paths as gp
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
