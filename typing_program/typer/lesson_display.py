"""Read-ahead hide + speed-heatmap paint for untyped lesson spans."""

from PyQt5.QtGui import QBrush, QTextCharFormat

from typing_program.read_ahead import hidden_char_indices, hidden_word_indices, word_index_at
from typing_program.speed_heatmap import book_return_role, char_heatmap_colors
from typing_program.typer.text_format import RETURN_CHAR, Cursor


class LessonDisplayMixin:
  def _reveal_read_ahead_word_at(self, match_index):
    if not self._read_ahead_mode or self.read_ahead_preview_pending():
      return
    wi = word_index_at(self._match_text, match_index)
    if wi in hidden_word_indices(self._match_text, match_index, self._read_ahead_mode):
      self._read_ahead_revealed.add(wi)

  def read_ahead_preview_pending(self):
    return bool(self._read_ahead_mode) and self.is_ready() and self._read_ahead_preview

  def dismiss_read_ahead_preview(self):
    if not self.read_ahead_preview_pending():
      return False
    self._read_ahead_preview = False
    self._refresh_read_ahead()
    return True

  def set_page_background(self, color):
    from PyQt5.QtGui import QColor
    self._page_bg = QColor(color)
    self.style_hidden.setForeground(QBrush(self._page_bg))
    self.style_hidden_return.setForeground(QBrush(self._page_bg))
    self._refresh_read_ahead()

  def set_read_ahead_mode(self, mode):
    self._read_ahead_mode = mode
    if self.is_ready() and mode:
      self._read_ahead_preview = True
    elif not mode:
      self._read_ahead_preview = False
    self._refresh_read_ahead()

  def _read_ahead_hidden_indices(self):
    if self._match_text is None or self.read_ahead_preview_pending():
      return set()
    pos = self._run.index if self._run is not None else 0
    return hidden_char_indices(self._match_text, pos, self._read_ahead_mode, self._read_ahead_revealed)

  def _heatmap_colors(self):
    if not self._speed_heatmap_enabled or not self._display_text:
      return []
    key = (self._display_text, self._speed_heatmap_mode, id(self._speed_heatmap_stats))
    if self._heatmap_colors_cache_key != key:
      self._heatmap_colors_cache_key = key
      self._heatmap_colors_cache = char_heatmap_colors(
        self._display_text, self._speed_heatmap_mode, self._speed_heatmap_stats, self._match_text,
        return_char=RETURN_CHAR, book_returns=self._book_auto_returns)
    return self._heatmap_colors_cache

  def _needs_untyped_style_refresh(self):
    return bool(self._read_ahead_mode)

  def _refresh_untyped_styles(self):
    if not self._needs_untyped_style_refresh():
      return
    self._refresh_read_ahead()

  def _refresh_read_ahead(self, force=False):
    if self._match_text is None:
      return
    if not force and not self._read_ahead_mode and not self._speed_heatmap_enabled and not self._book_auto_returns:
      return
    pos = self._run.index if self._run is not None else 0
    hidden = self._read_ahead_hidden_indices()
    colors = self._heatmap_colors() if self._speed_heatmap_enabled else []
    base = self._start.position()
    mi = 0; di = base
    c = Cursor(self)
    c.beginEditBlock()
    while mi < len(self._match_text):
      n = self._match_display_width(mi)
      if mi >= pos:
        for j in range(n):
          disp_i = di + j - base
          if (self._book_auto_returns and j == 0 and self._match_text[mi] == RETURN_CHAR
              and book_return_role(self._match_text, mi, RETURN_CHAR) == 'para_enter'
              and self._book_para_enter_revealed(mi)):
            break
          if (self._book_auto_returns and j == 0 and self._match_text[mi] == RETURN_CHAR
              and book_return_role(self._match_text, mi, RETURN_CHAR) == 'para_enter'):
            style = self.style_hidden_return
          elif self._read_ahead_mode and mi in hidden:
            style = self.style_hidden
          else:
            style = QTextCharFormat(self.style_untyped)
            if colors and disp_i < len(colors) and colors[disp_i] is not None:
              style.setForeground(QBrush(colors[disp_i]))
          c.setPosition(di + j)
          c.movePosition(c.NextCharacter, c.KeepAnchor)
          c.setCharFormat(style)
      di += n; mi += 1
    c.endEditBlock()

  def set_speed_heatmap(self, enabled, mode, stats):
    self._speed_heatmap_enabled = enabled
    self._speed_heatmap_mode = mode
    self._speed_heatmap_stats = stats or {}
    self._heatmap_colors_cache_key = None
    self._refresh_read_ahead(force=True)
