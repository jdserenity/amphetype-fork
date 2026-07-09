"""Sequential book typing: cached chapters, in-chapter chunks, formatted display."""

import codecs
import hashlib
import json
import re
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from typing_program.Config import Settings
from typing_program.Text import find_relative

MODE_BOOK = 'book'

_CHAPTER_HDR = re.compile(
  r'^(?:chapter|book|part)\s+(?:\d+|[IVXLCDM]+)\b',
  re.I,
)
_ROMAN_HDR = re.compile(r'^[IVXLCDM]{1,8}$')
_SECTION_NUM = re.compile(r'^\d{1,3}$')

SYSTEM_SOURCES = frozenset({'<Weakspot>', '<Reviews>', '<Lesson Generator>'})
BOOK_CACHE_VERSION = 2


def reflow_paragraphs(text):
  """Join Gutenberg-style hard wraps; keep blank-line paragraph breaks."""
  if not text or not text.strip():
    return text or ''
  text = text.replace('\r\n', '\n').replace('\r', '\n')
  paras = []
  for block in re.split(r'\n\s*\n', text):
    block = block.strip()
    if not block:
      continue
    lines = [ln.strip() for ln in block.split('\n') if ln.strip()]
    paras.append(' '.join(lines))
  return '\n\n'.join(paras)


def is_chapter_header(line):
  s = line.strip()
  if not s:
    return False
  if _CHAPTER_HDR.match(s):
    return True
  if _ROMAN_HDR.match(s):
    return True
  if _SECTION_NUM.match(s):
    return True
  return False


def split_chapters(text):
  """Split book text into (title, body) chapters."""
  if not text or not text.strip():
    return [('Start', '')]
  text = text.replace('\r\n', '\n').replace('\r', '\n')
  lines = text.split('\n')
  chapters = []
  title = None
  buf = []
  prev_blank = True
  for line in lines:
    stripped = line.strip()
    if is_chapter_header(line) and prev_blank:
      if buf:
        chapters.append((title or 'Start', reflow_paragraphs('\n'.join(buf))))
      title = stripped
      buf = [line]
    else:
      buf.append(line)
    prev_blank = not stripped
  if buf:
    chapters.append((title or 'Start', reflow_paragraphs('\n'.join(buf))))
  if not chapters:
    return [('Start', text.strip())]
  return chapters


def partition_chapter(text, min_chars, max_chars):
  """Split formatted chapter text into typing chunks (preferences min/max chars)."""
  text = text or ''
  if not text:
    return ['']
  min_chars = max(int(min_chars), 1)
  max_chars = min(int(max_chars), 99999)
  if min_chars > max_chars:
    min_chars, max_chars = max_chars, min_chars
  if len(text) <= max_chars:
    return [text]
  sweet = min_chars + int((max_chars - min_chars) / 1.618033988749895)
  chunks = []
  pos = 0
  n = len(text)
  while pos < n:
    remain = n - pos
    if remain <= max_chars:
      chunks.append(text[pos:])
      break
    window = text[pos:pos + max_chars]
    cut = _chunk_cut(window, min_chars, max_chars, sweet)
    chunks.append(text[pos:pos + cut])
    pos += cut
  return chunks if chunks else [text]


def _chunk_cut(window, min_chars, max_chars, sweet_spot):
  hi = len(window)
  lo = min(min_chars, hi)
  spot = min(sweet_spot, hi - 1)
  para = window.rfind('\n\n', lo, spot + 1)
  if para >= lo:
    return para + 2
  idx = find_relative(window[:spot + 1].replace('\n', ' '), ' ', min(spot, len(window) - 1))
  if idx >= lo:
    return idx + 1
  sp = window.rfind(' ', lo, hi)
  if sp >= lo:
    return sp + 1
  return hi


def lesson_text_id(source_id, chapter_index, chunk_index):
  raw = 'book:%d:%d:%d' % (source_id, chapter_index, chunk_index)
  return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def chunk_spec_key(min_chars, max_chars):
  return '%d:%d' % (int(min_chars), int(max_chars))


def resolve_book_path(source_name, texts_dir):
  texts_dir = Path(texts_dir)
  exact = texts_dir / source_name
  if exact.is_file():
    return exact
  for p in texts_dir.glob('*.txt'):
    if p.name == source_name or p.name.endswith(' - ' + source_name):
      return p
  return None


def source_content_key(db, source_id, source_name, texts_dir):
  path = resolve_book_path(source_name, texts_dir)
  if path is not None:
    st = path.stat()
    return 'v%d:file:%s:%d:%d' % (BOOK_CACHE_VERSION, path.name, st.st_mtime_ns, st.st_size)
  row = db.fetchone('select count(*) from text where source=?', (0,), (source_id,))
  return 'v%d:db:%d:%d' % (BOOK_CACHE_VERSION, source_id, int(row[0]))


def load_book_text(db, source_id, source_name, texts_dir):
  path = resolve_book_path(source_name, texts_dir)
  if path is not None:
    with codecs.open(str(path), 'r', 'utf_8_sig') as f:
      return f.read()
  rows = db.fetchall(
    'select text from text where source=? and disabled is null order by rowid',
    (source_id,),
  )
  if not rows:
    return None
  raw = '\n\n'.join((r[0] or '').replace('\r\n', '\n').replace('\r', '\n') for r in rows)
  return reflow_paragraphs(raw)


def list_book_sources(db):
  rows = db.fetchall("""
    select s.rowid, s.name
    from source as s
    where s.disabled is null
      and (s.discount is null or s.discount = 0)
      and s.name not like '<%>'
      and exists (
        select 1 from text t where t.source = s.rowid and t.disabled is null
      )
    order by s.name
  """)
  return [(r[0], r[1]) for r in rows]


def ensure_book_tables(db):
  db.execute("""
    create table if not exists book_progress (
      source integer primary key,
      chapter_index integer not null default 0,
      chunk_index integer not null default 0
    )
  """)
  db.execute("""
    create table if not exists book_lesson_done (
      source integer not null,
      chapter_index integer not null,
      chunk_index integer not null,
      completed_at real,
      primary key (source, chapter_index, chunk_index)
    )
  """)
  db.execute("""
    create table if not exists book_source_meta (
      source integer primary key,
      content_key text not null,
      chapter_count integer not null
    )
  """)
  db.execute("""
    create table if not exists book_chapter_cache (
      source integer not null,
      chapter_index integer not null,
      title text,
      body text not null,
      chunk_lengths text not null,
      spec_key text not null,
      primary key (source, chapter_index, spec_key)
    )
  """)
  _migrate_book_progress(db)
  db.commit()


def _migrate_book_progress(db):
  cols = {r[1] for r in db.execute('pragma table_info(book_progress)').fetchall()}
  if 'chapter_index' in cols:
    return
  if 'lesson_index' in cols:
    db.execute('alter table book_progress rename to book_progress_old')
    db.execute("""
      create table book_progress (
        source integer primary key,
        chapter_index integer not null default 0,
        chunk_index integer not null default 0
      )
    """)
    db.execute("""
      insert into book_progress (source, chapter_index, chunk_index)
      select source, lesson_index, 0 from book_progress_old
    """)
    db.execute('drop table book_progress_old')
  done_cols = {r[1] for r in db.execute('pragma table_info(book_lesson_done)').fetchall()}
  if 'lesson_index' in done_cols and 'chapter_index' not in done_cols:
    db.execute('alter table book_lesson_done rename to book_lesson_done_old')
    db.execute("""
      create table book_lesson_done (
        source integer not null,
        chapter_index integer not null,
        chunk_index integer not null,
        completed_at real,
        primary key (source, chapter_index, chunk_index)
      )
    """)
    db.execute("""
      insert into book_lesson_done (source, chapter_index, chunk_index, completed_at)
      select source, lesson_index, 0, completed_at from book_lesson_done_old
    """)
    db.execute('drop table book_lesson_done_old')


def get_book_progress(db, source_id):
  row = db.fetchone(
    'select chapter_index, chunk_index from book_progress where source=?',
    None,
    (source_id,),
  )
  if row is None:
    return 0, 0
  return int(row[0]), int(row[1])


def set_book_progress(db, source_id, chapter_index, chunk_index):
  db.execute("""
    insert into book_progress (source, chapter_index, chunk_index) values (?,?,?)
    on conflict(source) do update set
      chapter_index=excluded.chapter_index,
      chunk_index=excluded.chunk_index
  """, (source_id, chapter_index, chunk_index))
  db.commit()


def mark_chunk_done(db, source_id, chapter_index, chunk_index, when):
  db.execute("""
    insert into book_lesson_done (source, chapter_index, chunk_index, completed_at)
    values (?,?,?,?)
    on conflict(source, chapter_index, chunk_index) do update set completed_at=excluded.completed_at
  """, (source_id, chapter_index, chunk_index, when))
  db.commit()


def done_chunk_count(db, source_id):
  row = db.fetchone(
    'select count(*) from book_lesson_done where source=?',
    (0,),
    (source_id,),
  )
  return int(row[0])


def format_book_progress(chapter_label, chunk_index, chunk_count):
  if chunk_count <= 0:
    return chapter_label or ''
  return '%s · %d/%d' % (chapter_label, chunk_index + 1, chunk_count)


MODE_IMPROVE = 'improve'
MODE_CORPUS = 'corpus'
# Legacy aliases used in a few internal code paths.
MODE_WEAKSPOT = MODE_IMPROVE
MODE_NORMAL = MODE_CORPUS

_LEGACY_PRACTICE_MODE = {0: 0, 1: 1, 2: 0}  # old normal/weakspot → improve; book unchanged


def ensure_practice_mode_migrated(settings):
  if settings.contains('practice_mode_v3'):
    return
  if settings.contains('practice_mode_v2'):
    if settings.contains('practice_mode') and int(settings.value('practice_mode')) == 2:
      settings.set('practice_mode', 0)
    settings.set('practice_mode_v3', True)
    return
  if not settings.contains('practice_mode'):
    settings.set('practice_mode_v2', True)
    settings.set('practice_mode_v3', True)
    return
  old = int(settings.value('practice_mode'))
  settings.set('practice_mode', _LEGACY_PRACTICE_MODE.get(old, 0))
  settings.set('practice_mode_v2', True)
  settings.set('practice_mode_v3', True)


def practice_mode_from_settings(val):
  v = int(val)
  if v == 2:
    return MODE_CORPUS
  if v == 1:
    return MODE_BOOK
  return MODE_IMPROVE


def practice_mode_to_settings(mode):
  if mode == MODE_CORPUS:
    return 2
  if mode == MODE_BOOK:
    return 1
  return 0


def apply_cold_start_practice_mode(settings, typer_settings):
  """Every app launch starts on improve · normal, not last session's mode/submode.

  settings: AppSettings (practice_mode). typer_settings: FSettings group with improve_submode.
  """
  settings.set('practice_mode', practice_mode_to_settings(MODE_IMPROVE))
  typer_settings('improve_submode').set(0)


def _chunks_from_lengths(body, lengths):
  chunks = []
  pos = 0
  for ln in lengths:
    chunks.append(body[pos:pos + ln])
    pos += ln
  return chunks


def _lengths_from_chunks(chunks):
  return [len(c) for c in chunks]


class BookCatalog(object):
  """Cached chapter bodies + chunk lists per source."""

  def __init__(self, db, texts_dir):
    self._db = db
    self._texts_dir = Path(texts_dir)
    self._mem = {}  # source_id -> (content_key, spec_key, chapters)

  def invalidate(self, source_id=None):
    if source_id is None:
      self._mem.clear()
      return
    self._mem.pop(source_id, None)

  def chapter_count(self, source_id, source_name):
    return len(self.chapters(source_id, source_name))

  def chapters(self, source_id, source_name, min_chars=None, max_chars=None):
    min_chars = int(min_chars if min_chars is not None else Settings.get('min_chars'))
    max_chars = int(max_chars if max_chars is not None else Settings.get('max_chars'))
    spec = chunk_spec_key(min_chars, max_chars)
    ckey = source_content_key(self._db, source_id, source_name, self._texts_dir)
    cached = self._mem.get(source_id)
    if cached and cached[0] == ckey and cached[1] == spec:
      return cached[2]
    chapters = self._load_cached(source_id, ckey, spec, min_chars, max_chars)
    if chapters is None:
      chapters = self._build_and_store(source_id, source_name, ckey, spec, min_chars, max_chars)
    self._mem[source_id] = (ckey, spec, chapters)
    return chapters

  def _load_cached(self, source_id, content_key, spec_key, min_chars, max_chars):
    meta = self._db.fetchone(
      'select content_key, chapter_count from book_source_meta where source=?',
      None,
      (source_id,),
    )
    if not meta or meta[0] != content_key:
      return None
    rows = self._db.fetchall("""
      select chapter_index, title, body, chunk_lengths
      from book_chapter_cache
      where source=? and spec_key=?
      order by chapter_index
    """, (source_id, spec_key))
    if len(rows) != int(meta[1]):
      return None
    out = []
    for ci, title, body, clen in rows:
      lengths = json.loads(clen)
      chunks = _chunks_from_lengths(body, lengths)
      assert ''.join(chunks) == body
      out.append({'index': ci, 'title': title, 'body': body, 'chunks': chunks})
    return out

  def _build_and_store(self, source_id, source_name, content_key, spec_key, min_chars, max_chars):
    raw = load_book_text(self._db, source_id, source_name, self._texts_dir)
    if not raw:
      return None
    split = split_chapters(raw)
    self._db.execute('delete from book_chapter_cache where source=?', (source_id,))
    chapters = []
    for ci, (title, body) in enumerate(split):
      chunks = partition_chapter(body, min_chars, max_chars)
      assert ''.join(chunks) == body
      lengths = json.dumps(_lengths_from_chunks(chunks))
      self._db.execute("""
        insert into book_chapter_cache
        (source, chapter_index, title, body, chunk_lengths, spec_key)
        values (?,?,?,?,?,?)
      """, (source_id, ci, title, body, lengths, spec_key))
      chapters.append({'index': ci, 'title': title, 'body': body, 'chunks': chunks})
    self._db.execute("""
      insert into book_source_meta (source, content_key, chapter_count) values (?,?,?)
      on conflict(source) do update set content_key=excluded.content_key, chapter_count=excluded.chapter_count
    """, (source_id, content_key, len(chapters)))
    self._db.commit()
    return chapters


class BookLessonBuilder(QObject):
  lessonReady = pyqtSignal('PyQt_PyObject')
  progressChanged = pyqtSignal(str)
  sourcesChanged = pyqtSignal()

  def __init__(self, db, parent=None):
    super(BookLessonBuilder, self).__init__(parent)
    self._db = db
    self._catalog = BookCatalog(db, Settings.DATA_DIR / 'texts')
    self._source_id = int(Settings.get('book_source_id') or 0)
    ensure_book_tables(db)
    for k in ('min_chars', 'max_chars', 'book_source_id'):
      Settings.signal_for(k).connect(self._on_settings_change)

  def _on_settings_change(self, *_):
    self._catalog.invalidate()
    self._source_id = int(Settings.get('book_source_id') or 0)

  def invalidate_cache(self):
    self._catalog.invalidate()

  def available_sources(self):
    return list_book_sources(self._db)

  def set_source_id(self, source_id):
    source_id = int(source_id)
    if source_id == self._source_id:
      return
    self._source_id = source_id
    Settings.set('book_source_id', source_id)
    self.sourcesChanged.emit()

  def current_source_id(self):
    return self._source_id

  def _pick_source_id(self):
    sources = self.available_sources()
    if not sources:
      return None
    ids = [s[0] for s in sources]
    if self._source_id in ids:
      return self._source_id
    return sources[0][0]

  def request_lesson(self, advance_chapter=False):
    source_id = self._pick_source_id()
    if source_id is None:
      self.lessonReady.emit(None)
      return
    if source_id != self._source_id:
      self._source_id = source_id
      Settings.set('book_source_id', source_id)
    name_row = self._db.fetchone('select name from source where rowid=?', (None,), (source_id,))
    if not name_row:
      self.lessonReady.emit(None)
      return
    name = name_row[0]
    chapters = self._catalog.chapters(source_id, name)
    if not chapters:
      self.lessonReady.emit(None)
      return
    ci, ck = get_book_progress(self._db, source_id)
    if advance_chapter:
      ci = min(ci + 1, len(chapters) - 1)
      ck = 0
      set_book_progress(self._db, source_id, ci, ck)
    if ci >= len(chapters):
      ci = len(chapters) - 1
      ck = 0
    ch = chapters[ci]
    chunks = ch['chunks']
    if ck >= len(chunks):
      ck = len(chunks) - 1
    done = done_chunk_count(self._db, source_id)
    total_chunks = sum(len(c['chunks']) for c in chapters)
    prog = format_book_progress(ch['title'], ck, len(chunks))
    self.progressChanged.emit(prog)
    tid = lesson_text_id(source_id, ci, ck)
    meta = {
      'chapter_index': ci,
      'chunk_index': ck,
      'chapter_count': len(chapters),
      'chunk_count': len(chunks),
      'title': ch['title'],
      'book_name': name,
      'full_text': ch['body'],
      'chunks': chunks,
      'done_chunks': done,
      'total_chunks': total_chunks,
    }
    self.lessonReady.emit((tid, source_id, meta))

  def on_chunk_completed(self, source_id, chapter_index, chunk_index, when):
    mark_chunk_done(self._db, source_id, chapter_index, chunk_index, when)
    name = self._db.fetchone('select name from source where rowid=?', (None,), (source_id,))
    if not name:
      return
    chapters = self._catalog.chapters(source_id, name[0])
    ci, ck = chapter_index, chunk_index + 1
    if ci < len(chapters) and ck >= len(chapters[ci]['chunks']):
      ci += 1
      ck = 0
    if ci >= len(chapters):
      ci = len(chapters) - 1
      ck = max(0, len(chapters[ci]['chunks']) - 1)
    set_book_progress(self._db, source_id, ci, ck)
    if chapters:
      ch = chapters[min(ci, len(chapters) - 1)]
      cki = min(ck, len(ch['chunks']) - 1)
      self.progressChanged.emit(format_book_progress(ch['title'], cki, len(ch['chunks'])))

  def source_menu_entries(self):
    entries = []
    for sid, name in self.available_sources():
      try:
        nch = self._catalog.chapter_count(sid, name)
        ci, _ = get_book_progress(self._db, sid)
        label = '%s (ch. %d/%d)' % (name, min(ci + 1, max(nch, 1)), max(nch, 1))
      except Exception:
        label = name
      entries.append((sid, name, label))
    return entries
