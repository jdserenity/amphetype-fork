"""Book-mode typing: soft newlines, paragraph Enter, auto-consume returns."""

from typing_program.speed_heatmap import book_return_role
from typing_program.typer.text_format import RETURN_CHAR, Cursor


class BookTypingMixin:
  def _book_plain_display(self, text):
    import re
    return re.sub(r'\n\n+', '\n', (text or '').replace('\r\n', '\n').replace('\r', '\n'))

  def set_book_chapter(self, full_text, chunks, chunk_index, auto_returns=True):
    self._book_auto_returns = auto_returns
    self._book_chunks = chunks
    self._book_chunk_index = int(chunk_index)
    before = self._book_plain_display(''.join(chunks[:chunk_index]))
    active = chunks[chunk_index]
    after = self._book_plain_display(''.join(chunks[chunk_index + 1:]))
    self.set_text(active, prologue=before, epilogue=after, book_mode=True)

  def advance_book_chunk(self):
    if not self.has_next_book_chunk():
      return False
    self.set_book_chapter(
      ''.join(self._book_chunks), self._book_chunks, self._book_chunk_index + 1, self._book_auto_returns)
    return True

  def has_next_book_chunk(self):
    return bool(self._book_chunks) and self._book_chunk_index + 1 < len(self._book_chunks)

  def _make_display_text(self, match_text):
    if self._book_auto_returns:
      out = []; i = 0
      while i < len(match_text):
        if match_text[i] == RETURN_CHAR:
          role = book_return_role(match_text, i, RETURN_CHAR)
          if role == 'soft_nl':
            out.append('\n'); i += 1
          elif role == 'para_enter':
            out.append(RETURN_CHAR + '\n'); i += 1
            while i < len(match_text) and book_return_role(match_text, i, RETURN_CHAR) == 'para_tail':
              i += 1
          else:
            i += 1
        else:
          out.append(match_text[i]); i += 1
      return ''.join(out)
    return match_text.replace(RETURN_CHAR, RETURN_CHAR + '\n')

  def _match_display_width(self, mi):
    if mi >= len(self._match_text):
      return 0
    if self._match_text[mi] == RETURN_CHAR:
      if self._book_auto_returns:
        role = book_return_role(self._match_text, mi, RETURN_CHAR)
        if role == 'soft_nl':
          return 1
        if role == 'para_enter':
          return 2
        return 0
      return 2
    return 1

  def _display_span(self, mi):
    base = self._start.position()
    di = base
    for i in range(mi):
      di += self._match_display_width(i)
    n = self._match_display_width(mi)
    return di, n

  def _style_match_index(self, mi, style):
    di, n = self._display_span(mi)
    c = Cursor(self)
    for j in range(n):
      c.setPosition(di + j)
      c.movePosition(c.NextCharacter, c.KeepAnchor)
      c.setCharFormat(style)

  def _cursor_to_match_index(self, mi):
    if mi >= len(self._match_text):
      self.cursor.setPosition(self._end.position())
      return
    self.cursor.setPosition(self._display_span(mi)[0])

  def _consume_auto_returns(self):
    while self._run and not self._run.is_complete() and self._run.current and self._run.current.char == RETURN_CHAR:
      mi = self._run.index
      if self._book_auto_returns and book_return_role(self._match_text, mi, RETURN_CHAR) == 'para_enter':
        break
      self._run.visit(True)
      self._run.advance(True)
      self._style_match_index(mi, self.style_correct)
      self._cursor_to_match_index(self._run.index)
      self.progress.emit(self._run.index)

  def _consume_trailing_whitespace(self):
    """Auto-complete trailing whitespace so the last letter ends the lesson."""
    while self._run and not self._run.is_complete() and self._run.current:
      rest = self._match_text[self._run.index:]
      if not rest or not all(c.isspace() for c in rest):
        break
      mi = self._run.index
      self._run.visit(True)
      self._run.advance(True)
      self._style_match_index(mi, self.style_correct)
      self._cursor_to_match_index(self._run.index)
      self.progress.emit(mi)

  def _book_para_enter_index(self):
    if not self._book_auto_returns or not self._run or not self._run.current:
      return None
    mi = self._run.index
    if self._run.current.char != RETURN_CHAR:
      return None
    if book_return_role(self._match_text, mi, RETURN_CHAR) != 'para_enter':
      return None
    return mi

  def _book_para_enter_revealed(self, mi):
    if self._book_para_enter_index() != mi:
      return False
    di, _ = self._display_span(mi)
    if self.characterAt(di) != RETURN_CHAR:
      return True
    return self._first_error is not None and self._first_error.position() == di

  def _book_para_enter_glyph_replaced(self, mi):
    return self._book_para_enter_revealed(mi)

  def _restore_book_para_enter_untyped(self, mi):
    di, _ = self._display_span(mi)
    c = Cursor(self, position=di)
    c.setPosition(di + 1, c.KeepAnchor)
    c.insertText(RETURN_CHAR, self.style_hidden_return)
    self._cursor_to_match_index(mi)

  def _finish_book_insert(self):
    if self.is_finished():
      self.completed.emit(self._run)
    else:
      self._refresh_untyped_styles()
      self.sig_position.emit(self.cursor)

  def _insert_book_para_enter(self, char, lenient=False):
    """Type (or recover) the hidden paragraph break — only the first display glyph is mutable."""
    mi = self._book_para_enter_index()
    assert mi is not None
    correct = char == RETURN_CHAR
    di, _ = self._display_span(mi)
    c = Cursor(self, position=di)
    c.setPosition(di + 1, c.KeepAnchor)

    if self._first_error is not None:
      if not correct:
        self._reveal_read_ahead_word_at(mi)
        self._run.visit(False)
        c.insertText(RETURN_CHAR, self.style_error)
        self._finish_book_insert()
        self.key_typed.emit(False)
        return
      self._run.visit(True)
      self.progress.emit(mi)
      c.insertText(RETURN_CHAR, self.style_hidden_return)
      self._first_error = None
      self._run.advance(True)
      self._cursor_to_match_index(self._run.index)
      self._consume_auto_returns()
      self._consume_trailing_whitespace()
      self._finish_book_insert()
      self.key_typed.emit(True)
      return

    if not correct:
      self._reveal_read_ahead_word_at(mi)
      self._run.visit(False)
      self._run.current.errors += char
      if not lenient:
        self._first_error = Cursor(self, position=di, fixed=True)
      c.insertText(RETURN_CHAR, self.style_error)
      self._cursor_to_match_index(mi)
      self._finish_book_insert()
      self.key_typed.emit(False)
      return

    self._run.visit(True)
    self.progress.emit(mi)
    c.insertText(RETURN_CHAR, self.style_hidden_return)
    self._run.advance(True)
    self._cursor_to_match_index(self._run.index)
    self._consume_auto_returns()
    self._consume_trailing_whitespace()
    self._finish_book_insert()
    self.key_typed.emit(True)
