
import logging as log
import os.path as path
import shutil
import time
import hashlib
from pathlib import Path

from amphetype.Text import LessonMiner
from amphetype.Data import DB
from amphetype.QtUtil import *
from amphetype.Config import *
from amphetype.gutenberg.browser import GutenbergBrowser
from amphetype.gutenberg.paths import texts_dir

from PyQt5.QtCore import *
from PyQt5.QtGui import *



class SourceModel(AmphModel):
  def signature(self):
    self.hidden = 1
    return (["Source", "Length", "Results", "WPM", "Disabled"],
        [None, None, None, "%.1f", None])

  def populateData(self, idxs):
    if len(idxs) == 0:
      return list(map(list, DB.fetchall("""
      select s.rowid,s.name,t.count,r.count,r.wpm,ifelse(nullif(t.dis,t.count),'No','Yes')
          from source as s
          left join (select source,count(*) as count,count(disabled) as dis from text group by source) as t
            on (s.rowid = t.source)
          left join (select source,count(*) as count,avg(wpm) as wpm from result group by source) as r
            on (t.source = r.source)
          where s.disabled is null
          order by s.name""")))

    if len(idxs) > 1:
      return []

    r = self.rows[idxs[0]]

    return list(map(list, DB.fetchall("""select t.rowid,substr(t.text,0,40)||"...",length(t.text),r.count,r.m,ifelse(t.disabled,'Yes','No')
        from (select rowid,* from text where source = ?) as t
        left join (select text_id,count(*) as count,agg_median(wpm) as m from result group by text_id) as r
          on (t.id = r.text_id)
        order by t.rowid""", (r[0], ))))



class TextManager(QWidget):

  setText = pyqtSignal('PyQt_PyObject')
  gotoText = pyqtSignal()
  refreshSources = pyqtSignal()

  defaultText = ("", 0, """Welcome to Amphetype!
Amphetype is a layout-agnostic typing program that measures your speed and progress while identifying typing problems. This is just a default text since your database is empty. Go to Preferences → Sources and try importing a text. Several whole novels already come packaged with Amphetype! Later on you can generate highly customizable lessons directly from your statistics!
Good luck!""")

  def __init__(self, *args):
    super(TextManager, self).__init__(*args)

    self.diff_eval = lambda x: 1
    self.model = SourceModel()
    tv = AmphTree(self.model)
    tv.doubleClicked['QModelIndex'].connect(self.onDoubleClicked)
    tv.resizeColumnToContents(0)
    tv.setColumnWidth(0, max(300, tv.columnWidth(0) + 40))
    self.tree = tv
    
    self.progress = QProgressBar()
    self.progress.setRange(0, 100)
    self.progress.hide()

    self.gutenberg = GutenbergBrowser(self)
    self.gutenberg.bookReady.connect(self.importGutenbergBook)
    self.gutenberg.busyChanged.connect(self._gutenberg_busy)

    self.setLayout(AmphBoxLayout(
        [
          ([
            "Below you will see the different text sources used. Disabling texts or sources deactivates them so they won't be selected for typing. You can double click a text to do that particular text.\n",
            (self.tree, 1),
            self.progress,
            [AmphButton("Import Texts", self.addFiles), None,
              AmphButton("Enable All", self.enableAll),
              AmphButton("Delete Disabled", self.removeDisabled), None,
              AmphButton("Update List", self.update)],
            [AmphButton("Delete selected", self.deleteSelected), None,
              AmphButton("Toggle disabled", self.disableSelected),
              "on all selected texts that match <a href=\"http://en.wikipedia.org/wiki/Regular_expression\">regular expression</a>",
              SettingsEdit('text_regex')]
          ], 1),
          [(self.gutenberg, 1)],
        ], QBoxLayout.LeftToRight))

    Settings.signal_for("select_method").connect(self.setSelect)
    Settings.signal_for('text_force_ascii').connect(self.nextText)
    self.setSelect(Settings.get('select_method'))

  def showEvent(self, event):
    super().showEvent(event)
    self.gutenberg.refresh_catalog_notice()

  def setSelect(self, v):
    if v == 0 or v == 1:
      self.diff_eval = lambda x: 1
      self.nextText()
      return

    hist = time.time() - 86400.0 * Settings.get('history')
    tri = dict(
        DB.execute("""
          select data,agg_median(time) as wpm from statistic
          where w >= ? and type = 1
          group by data""", (hist, )).fetchall()) #[(t, (m, c)) for t, m, c in

    g = list(tri.values())
    if len(g) == 0:
      return lambda x: 1
    g.sort(reverse=True)
    expect = g[len(g)//4]
    def _func(v):
      text = v[2]
      v = 0
      s = 0.0
      for i in range(0, len(text)-2):
        t = text[i:i+3]
        if t in tri:
          s += tri[t]
        else:
          s += expect
          v +=1
      avg = s / (len(text)-2)
      return 12.0/avg

    self.diff_eval = _func
    self.nextText()

  def _gutenberg_busy(self, busy):
    self.tree.setEnabled(not busy)

  def importGutenbergBook(self, source_name, path):
    self.progress.show()
    self.progress.setValue(0)
    book_path = texts_dir() / source_name
    try:
      lm = LessonMiner(str(book_path))
    except Exception:
      log.error(f'failed to process gutenberg file {source_name}!')
      self.progress.hide()
      return
    lm.progress[int].connect(self.progress.setValue)
    self.addTexts(source_name, lm, update=False, replace=True)
    self.progress.hide()
    self.update()
    DB.commit()

  def addFiles(self):

    qf = QFileDialog(self, "Import Text From File(s)", directory=str(texts_dir()))
    qf.setNameFilters(["UTF-8 text files (*.txt)", "All files (*)"])
    qf.setFileMode(QFileDialog.ExistingFiles)
    qf.setAcceptMode(QFileDialog.AcceptOpen)

    qf.filesSelected['QStringList'].connect(self.setImpList)

    qf.show()

  def setImpList(self, files):
    self.sender().hide()
    self.progress.show()
    for x in map(str, files):
      self.progress.setValue(0)
      src = Path(x)
      dest = texts_dir() / src.name
      if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
      fname = dest.name
      try:
        lm = LessonMiner(str(dest))
      except:
        log.error(f"failed to process file {fname}!")
        continue
      lm.progress[int].emit(self.progress.setValue)
      self.addTexts(fname, lm, update=False)

    self.progress.hide()
    self.update()
    DB.commit()

  def addTexts(self, source, texts, lesson=None, update=True, replace=False):
    id = DB.getSource(source, lesson)
    if replace:
      self._clear_source_texts(id)
    r = []
    for x in texts:
      h = hashlib.sha1()
      h.update(x.encode('utf-8'))
      txt_id = h.hexdigest()
      dis = 1 if lesson == 2 else None
      try:
        DB.execute("insert into text (id,text,source,disabled) values (?,?,?,?)",
               (txt_id, x, id, dis))
        if lesson is None and dis is None:
          from amphetype.text_index import index_chunk
          index_chunk(DB, txt_id, id, x)
        r.append(txt_id)
      except Exception as e:
        pass # silently skip ...
    if update:
      self.update()
    if lesson:
      DB.commit()
    return r

  def newReview(self, review):
    q = self.addTexts("<Reviews>", [review], lesson=2, update=False)
    if q:
      v = DB.fetchone("select id,source,text from text where id = ?", self.defaultText, q)
      self.emit_text(v)
    else:
      self.nextText()

  def newWeakspot(self, lesson):
    sid = DB.getSource("<Weakspot>", 1)
    h = hashlib.sha1()
    h.update(lesson.encode('utf-8'))
    txt_id = h.hexdigest()
    try:
      DB.execute("insert into text (id,text,source,disabled) values (?,?,?,?)",
                 (txt_id, lesson, sid, 1))
      DB.commit()
    except Exception:
      pass
    v = DB.fetchone("select id,source,text from text where id = ?", self.defaultText, (txt_id,))
    self.emit_text(v)

  def update(self):
    self.refreshSources.emit()
    self.model.reset()

  def nextText(self):

    type = Settings.get('select_method')

    if type != 1:
      # Not in order
      v = DB.execute("select id,source,text from text where disabled is null order by random() limit %d" % Settings.get('num_rand')).fetchall()
      if len(v) == 0:
        v = None
      elif type == 2:
        v = min(v, key=self.diff_eval)
      elif type == 3:
        v = max(v, key=self.diff_eval)
      else:
        v = v[0] # random, just pick the first
    else:
      # Fetch in order
      lastid = (0,)
      g = DB.fetchone("""select r.text_id
        from result as r left join source as s on (r.source = s.rowid)
        where (s.discount is null) or (s.discount = 1) order by r.w desc limit 1""", None)
      if g is not None:
        lastid = DB.fetchone("select rowid from text where id = ?", lastid, g)
      v = DB.fetchone("select id,source,text from text where rowid > ? and disabled is null order by rowid asc limit 1", None, lastid)

    if v is None:
      v = self.defaultText

    self.emit_text(v)

  def _clear_source_texts(self, source_id):
    for row in DB.fetchall('select id from text where source = ?', (source_id,)):
      DB.execute('delete from result where text_id = ?', (row[0],))
    DB.execute('delete from text where source = ?', (source_id,))

  def deleteSelected(self):
    cats, texts = self.getSelected()
    if not cats and not texts:
      return
    parts = []
    if cats:
      parts.append(f'{len(cats)} source{"s" if len(cats) != 1 else ""}')
    if texts:
      parts.append(f'{len(texts)} lesson{"s" if len(texts) != 1 else ""}')
    label = ' and '.join(parts)
    if QMessageBox.question(
        self, 'Delete selected',
        f'Delete {label} and any associated typing results?\nThis cannot be undone.',
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
      return
    for sid in cats:
      self._clear_source_texts(sid)
      DB.execute('delete from result where source = ?', (sid,))
      DB.execute('delete from source where rowid = ?', (sid,))
    for tid in texts:
      row = DB.fetchone('select id, source from text where rowid = ?', None, (tid,))
      if row is None:
        continue
      DB.execute('delete from result where text_id = ?', (row[0],))
      DB.execute('delete from text where rowid = ?', (tid,))
      rest = DB.fetchall('select rowid from text where source = ? limit 1', (row[1],))
      if not rest:
        DB.execute('delete from result where source = ?', (row[1],))
        DB.execute('delete from source where rowid = ?', (row[1],))
    self.update()
    DB.commit()

  def removeUnused(self):
    DB.execute('''
      delete from source where rowid in (
        select s.rowid from source as s
          left join result as r on (s.rowid=r.source)
          left join text as t on (t.source=s.rowid)
        group by s.rowid
        having count(r.rowid) = 0 and count(t.rowid) = 0
      )''')
    DB.execute('''
      update source set disabled = 1 where rowid in (
        select s.rowid from source as s
          left join result as r on (s.rowid=r.source)
          left join text as t on (t.source=s.rowid)
        group by s.rowid
        having count(r.rowid) > 0 and count(t.rowid) = 0
      )''')
    self.refreshSources.emit()

  def removeDisabled(self):
    DB.execute('delete from text where disabled is not null')
    self.removeUnused()
    self.update()
    DB.commit()

  def enableAll(self):
    DB.execute('update text set disabled = null where disabled is not null')
    self.update()

  def disableSelected(self):
    cats, texts = self.getSelected()
    DB.setRegex(Settings.get('text_regex'))
    DB.executemany("""update text set disabled = ifelse(disabled,NULL,1)
        where rowid = ? and regex_match(text) = 1""",
             [(x, ) for x in texts])
    DB.executemany("""update text set disabled = ifelse(disabled,NULL,1)
        where source = ? and regex_match(text) = 1""",
             [(x, ) for x in cats])
    self.update()

  def getSelected(self):
    texts = []
    cats = []
    for idx in self.tree.selectedIndexes():
      if idx.column() != 0:
        continue
      if idx.parent().isValid():
        texts.append(self.model.data(idx, Qt.UserRole)[0])
      else:
        cats.append(self.model.data(idx, Qt.UserRole)[0])
    return (cats, texts)

  def onDoubleClicked(self, idx):
    p = idx.parent()
    if not p.isValid():
      return

    q = self.model.data(idx, Qt.UserRole)
    v = DB.fetchall('select id,source,text from text where rowid = ?', (q[0], ))

    self.cur = v[0] if len(v) > 0 else self.defaultText
    self.emit_text(self.cur)
    self.gotoText.emit()

  def emit_text(self, v):
    log.info("setting new text id=%s length=%d source=%s", v[0], len(v[2]), v[1])
    if Settings.get('text_force_ascii'):
      tid, tsrc, ttxt = v
      v = (tid, tsrc, force_ascii(ttxt))
    self.setText.emit(v)


_bothered = False
def force_ascii(txt):
  try:
    import translitcodec
    import codecs
    return codecs.encode(txt, 'translit/long')
  except ImportError:
    # What do we do here?
    global _bothered
    if not _bothered:
      QMessageBox.information(
        None, "Missing Module",
        "Module <code>translitcodec</code> needed to translate unicode to ascii.\nTry running <code>pip install translitcodec</code>.")
    _bothered = True
    return txt.encode('ascii', errors='replace').decode()
