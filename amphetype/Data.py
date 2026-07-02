

from itertools import *
import time
import bisect
import sqlite3
import re
from amphetype.Config import Settings

# Omit generated-lesson stats from heatmap etc. Analysis/weakspot use stats_query.py.
from amphetype.stats_query import STAT_OMIT_DISCOUNTED  # noqa: F401 — re-export


def trimmed_average(total, series):
  s = 0.0
  n = 0

  start = 0
  cutoff = total // 3
  while cutoff > 0:
    cutoff -= series[start][1]
    start += 1
  if cutoff < 0:
    s += -cutoff * series[start-1][0]
    n += -cutoff

  end = len(series)-1
  cutoff = total // 3
  while cutoff > 0:
    cutoff -= series[end][1]
    end -= 1
  if cutoff < 0:
    s += -cutoff * series[end+1][0]
    n += -cutoff

  while start <= end:
    s += series[start][1] * series[start][0]
    n += series[start][1]
    start += 1

  return s/n


class Statistic(list):
  def __init__(self):
    super(Statistic, self).__init__()
    self.flawed_ = 0

  def append(self, x, flawed=False):
    bisect.insort(self, x)
    if flawed:
      self.flawed_ += 1

  def __cmp__(self, other):
    return cmp(self.median(), other.median())

  def measurement(self):
    return trimmed_average(len(self), [(x, 1) for x in self])

  def median(self):
    l = len(self)
    if l == 0:
      return None
    if l & 1:
      return self[l // 2]
    return (self[l//2] + self[l//2-1])/2.0

  def flawed(self):
    return self.flawed_





class MedianAggregate(Statistic):
  def step(self, val):
    if val is not None:
      self.append(val)

  def finalize(self):
    return self.median()

class MeanAggregate(object):
  def __init__(self):
    self.sum_ = 0.0
    self.count_ = 0

  def step(self, value, count):
    if value is not None and count is not None:
      self.sum_ += value * count
      self.count_ += count

  def finalize(self):
    return self.sum_ / self.count_ if self.count_ > 0 else None

class FirstAggregate(object):
  def __init__(self):
    self.val = None

  def step(self, val):
    if self.val is not None:
      self.val = val

  def finalize(self):
    return self.val


class AmphDatabase(sqlite3.Connection):
  def __init__(self, *args):
    super(AmphDatabase, self).__init__(*args)

    self.setRegex("")
    self.resetCounter()
    self.resetTimeGroup()
    self.create_function("counter", 0, self.counter)
    self.create_function("regex_match", 1, self.match)
    self.create_function("abbreviate", 2, self.abbreviate)
    self.create_function("time_group", 2, self.time_group)
    self.create_aggregate("agg_median", 1, MedianAggregate)
    self.create_aggregate("agg_mean", 2, MeanAggregate)
    self.create_aggregate("agg_first", 1, FirstAggregate)
    #self.create_aggregate("agg_trimavg", 2, TrimmedAverarge)
    self.create_function("ifelse", 3, lambda x, y, z: y if x is not None else z)

    try:
      self.fetchall("select * from result,source,statistic,text,mistake limit 1")
    except:
      self.newDB()
    self._ensure_migrations()

  def _ensure_migrations(self):
    cols = {r[1] for r in self.execute("pragma table_info(statistic)").fetchall()}
    if 'source' not in cols:
      self.execute('alter table statistic add column source integer')
      self.execute('''update statistic set source = (
        select r.source from result r where r.w = statistic.w limit 1
      ) where source is null''')
    rcols = {r[1] for r in self.execute("pragma table_info(result)").fetchall()}
    if 'char_count' not in rcols:
      self.execute('alter table result add column char_count integer')
    if 'duration' not in rcols:
      self.execute('alter table result add column duration real')
    from amphetype.app_meta import get_app_meta_int, set_app_meta_int
    if not get_app_meta_int(self, 'result_char_count_backfill_cleared', 0):
      self.execute('update result set char_count = null')
      set_app_meta_int(self, 'result_char_count_backfill_cleared', 1)
    # Weakspot (and other generated lessons) must not feed back into weakspot selection.
    self.execute("update source set discount = 1 where name = '<Weakspot>' and discount is null")
    from amphetype.book_mode import ensure_book_tables
    from amphetype.app_meta import ensure_app_meta
    ensure_book_tables(self)
    ensure_app_meta(self)
    self.commit()

  def resetTimeGroup(self):
    self.lasttime_ = 0.0
    self.timecnt_ = 0

  def time_group(self, d, x):
    if abs(x-self.lasttime_) >= d:
      self.timecnt_ += 1
    self.lasttime_ = x
    return self.timecnt_

  def setRegex(self, x):
    self.regex_ = re.compile(x)

  def abbreviate(self, x, n):
    if len(x) <= n:
      return x
    return x[:n-3] + "..."

  def match(self, x):
    if self.regex_.search(x):
      return 1
    return 0

  def counter(self):
    self._count += 1
    return self._count
  def resetCounter(self):
    self._count = -1

  def newDB(self):
    self.executescript("""
create table source (name text, disabled integer, discount integer);
create table text (id text primary key, source integer, text text, disabled integer);
create table result (w real, text_id text, source integer, wpm real, accuracy real, viscosity real, char_count integer, duration real);
create table statistic (w real, data text, type integer, time real, count integer, mistakes integer, viscosity real, source integer);
create table mistake (w real, target text, mistake text, count integer);
create view text_source as
  select id,s.name,text,coalesce(t.disabled,s.disabled)
    from text as t left join source as s on (t.source = s.rowid);
    """)
    self.commit()

  def executemany_(self, *args):
    super(AmphDatabase, self).executemany(*args)
  def executemany(self, *args):
    super(AmphDatabase, self).executemany(*args)
    #self.commit()

  def fetchall(self, *args):
    return self.execute(*args).fetchall()

  def fetchone(self, sql, default, *args):
    x = self.execute(sql, *args)
    g = x.fetchone()
    if g is None:
      return default
    return g

  def getSource(self, source, lesson=None):
    v = self.fetchall('select rowid,discount from source where name = ? limit 1', (source, ))
    if len(v) > 0:
      rid, disc = v[0]
      self.execute('update source set disabled = NULL where rowid = ?', (rid,))
      if lesson is not None and disc is None:
        self.execute('update source set discount = ? where rowid = ?', (lesson, rid))
      self.commit()
      return rid
    self.execute('insert into source (name,discount) values (?,?)', (source, lesson))
    return self.getSource(source)

  def getTextContext(self, textid):
    texts = sorted(DB.fetchall("""
select T.rowid,T.id,T.source,T.text
  from text as T, (select rowid,source from text where id=?) as T2
  where T.disabled is null and
    T.source = T2.source
  order by abs(T.rowid - T2.rowid) asc
  limit 3""", (textid,)))
    if textid not in [t[1] for t in texts]:
      return (None, None, None)
    if len(texts) == 1:
      return (None, texts[0][1:], None)

    if texts[0][1] == textid:
      return (None, texts[0][1:], texts[1][1:])
    if texts[-1][1] == textid:
      return (texts[-2][1:], texts[-1][1:], None)
    
    assert len(texts) == 3 and texts[1][1] == textid
    return (texts[0][1:], texts[1][1:], texts[2][1:])



dbname = Settings.get("db_name")

# GLOBAL
DB = sqlite3.connect(dbname,5,0,"DEFERRED",False,AmphDatabase)

def switchdb(nn):
  global DB
  DB.commit()
  try:
    nDB = sqlite3.connect(nn,5,0,"DEFERRED",False,AmphDatabase)
    DB = nDB
  except Exception as e:
    from PyQt5.QtGui import QMessageBox as qmb
    qmb.information(None, "Database Error", "Failed to switch to the new database:\n" + str(e))


