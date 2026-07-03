import logging as log

from typing_program.QtUtil import AppButton, WWLabel
from typing_program.gutenberg.catalog import (
  catalog_notice, ensure_catalog_index, needs_catalog_update,
  rebuild_index, search_books, update_catalog,
)
from typing_program.gutenberg.fetch import estimate_import_seconds, write_book_file

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *


class _CatalogWorker(QThread):
  done = pyqtSignal(bool, str)

  def __init__(self, download=True):
    super().__init__()
    self.download = download

  def run(self):
    try:
      if self.download:
        update_catalog()
      else:
        rebuild_index()
      self.done.emit(True, '')
    except Exception as e:
      log.exception('catalog update failed')
      self.done.emit(False, str(e))


class _ImportWorker(QThread):
  done = pyqtSignal(bool, str, str, str)  # ok, source_name, path, err

  def __init__(self, region, book_id, authors, title, url=None):
    super().__init__()
    self.region = region
    self.book_id = book_id
    self.authors = authors
    self.title = title
    self.url = url

  def run(self):
    try:
      source_name, path = write_book_file(
        self.book_id, self.authors, self.title, region=self.region, url=self.url)
      self.done.emit(True, source_name, str(path), '')
    except Exception as e:
      log.exception('gutenberg import failed')
      self.done.emit(False, '', '', str(e))


def _book_key(book):
  return f"{book['region']}:{book['id']}"


class GutenbergBrowser(QWidget):
  bookReady = pyqtSignal(str, str)  # source_name, path
  busyChanged = pyqtSignal(bool)

  def __init__(self, parent=None):
    super().__init__(parent)
    self.setMinimumWidth(280)
    self._catalog_worker = None
    self._import_worker = None
    self._books = []
    self._catalog_download = True

    self._stale = WWLabel('')
    self._stale_btn = AppButton('Update', self._start_catalog_update)
    self._stale_row = QWidget()
    stale_lay = QHBoxLayout(self._stale_row)
    stale_lay.setContentsMargins(0, 0, 0, 0)
    stale_lay.addWidget(self._stale, 1)
    stale_lay.addWidget(self._stale_btn)

    self._search = QLineEdit()
    self._search.setPlaceholderText('Search Project Gutenberg…')
    self._search.returnPressed.connect(self._run_search)
    self._search_btn = AppButton('Search', self._run_search)

    self._results = QListWidget()
    self._results.itemDoubleClicked.connect(lambda _: self._import_selected())

    self._import_btn = AppButton('Import selected', self._import_selected)
    self._import_btn.setEnabled(False)
    self._results.itemSelectionChanged.connect(self._on_selection)

    self._status = WWLabel('')
    self._status.hide()

    lay = QVBoxLayout(self)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel('<b>US/AU catalog</b>'))
    lay.addWidget(self._stale_row)
    row = QHBoxLayout()
    row.addWidget(self._search, 1)
    row.addWidget(self._search_btn)
    lay.addLayout(row)
    lay.addWidget(self._results, 1)
    lay.addWidget(self._import_btn)
    lay.addWidget(self._status)

    self.refresh_catalog_notice()

  def refresh_catalog_notice(self):
    ensure_catalog_index()
    msg, secs, download = catalog_notice()
    self._catalog_download = download
    if msg:
      self._stale.setText(f'{msg} Update? (~{secs} seconds)')
      self._stale_row.show()
    else:
      self._stale_row.hide()

  def _set_busy(self, busy):
    self._search_btn.setEnabled(not busy)
    self._import_btn.setEnabled(not busy and self._results.currentItem() is not None)
    self._stale_btn.setEnabled(not busy)
    self._search.setEnabled(not busy)
    self.busyChanged.emit(busy)

  def _start_catalog_update(self):
    if self._catalog_worker and self._catalog_worker.isRunning():
      return
    self._status.setText('Updating catalog…')
    self._status.show()
    self._set_busy(True)
    self._catalog_worker = _CatalogWorker(self._catalog_download)
    self._catalog_worker.done.connect(self._on_catalog_done)
    self._catalog_worker.start()

  def _on_catalog_done(self, ok, err):
    self._set_busy(False)
    if ok:
      self._status.hide()
      self.refresh_catalog_notice()
    else:
      self._status.setText(f'Catalog update failed: {err}')
      self._status.show()

  def _run_search(self):
    if needs_catalog_update():
      self.refresh_catalog_notice()
      self._status.setText('Update the catalog before searching.')
      self._status.show()
      return
    q = self._search.text().strip()
    if not q:
      return
    self._books = search_books(q)
    self._results.clear()
    for b in self._books:
      label = b['title']
      if b['authors']:
        label += f" — {b['authors']}"
      item = QListWidgetItem(label)
      item.setData(Qt.UserRole, _book_key(b))
      self._results.addItem(item)
    self._status.setText(f'{len(self._books)} result(s)' if self._books else 'No matches.')
    self._status.show()
    self._on_selection()

  def _on_selection(self):
    busy = self._catalog_worker and self._catalog_worker.isRunning()
    busy = busy or (self._import_worker and self._import_worker.isRunning())
    self._import_btn.setEnabled(not busy and self._results.currentItem() is not None)

  def _import_selected(self):
    item = self._results.currentItem()
    if not item:
      return
    if self._import_worker and self._import_worker.isRunning():
      return
    key = item.data(Qt.UserRole)
    book = next((b for b in self._books if _book_key(b) == key), None)
    if not book:
      return
    secs = estimate_import_seconds(book['region'])
    self._status.setText(f'Importing {book["title"]}… (~{secs} seconds)')
    self._status.show()
    self._set_busy(True)
    self._import_worker = _ImportWorker(
      book['region'], book['id'], book['authors'], book['title'], book.get('url'))
    self._import_worker.done.connect(self._on_import_done)
    self._import_worker.start()

  def _on_import_done(self, ok, source_name, path, err):
    self._set_busy(False)
    if ok:
      self._status.setText(f'Imported {source_name}')
      self.bookReady.emit(source_name, path)
    else:
      self._status.setText(f'Import failed: {err}')
