"""Typer practice tab: lesson document, editor widget, and window chrome."""

from typing_program.book_mode import MODE_BOOK, MODE_CORPUS, MODE_IMPROVE

from typing_program.typer.document import (
  RETURN_CHAR, PARA_SEP, LINE_SEP, _NO_FILL_STYLE_ATTRS,
  Cursor, LessonDocument, text_style, block_style, text_props,
)
from typing_program.typer.pause_overlay import _LessonPauseOverlay
from typing_program.typer.source_attr import (
  format_source_attribution, lesson_completion_action, _display_source_name,
)
from typing_program.typer.styles import (
  MODE_BTN_ACTIVE, MODE_BTN_GREYED, MODE_BTN_HOVER, MODE_BTN_INACTIVE,
  TYPER_CANVAS_DEFAULT, TYPER_CHROME_COLOR,
  _BADGE_FONT_PT, _CORPUS_BTN_LABEL, _FOOTER_BTN_PAD_X, _FOOTER_ITEM_GAP,
  _GENERATING_BTN_LABEL, _IMPROVE_BTN_LABEL,
  _footer_btn_style, _footer_zero_margins,
)
from typing_program.typer.widget import TyperWidget, configure_transparent_typer
from typing_program.typer.window import TyperWindow, MODE_NORMAL, MODE_WEAKSPOT

__all__ = [
  'RETURN_CHAR', 'PARA_SEP', 'LINE_SEP', '_NO_FILL_STYLE_ATTRS',
  'Cursor', 'LessonDocument', 'text_style', 'block_style', 'text_props',
  '_LessonPauseOverlay',
  'format_source_attribution', 'lesson_completion_action', '_display_source_name',
  'MODE_BTN_ACTIVE', 'MODE_BTN_GREYED', 'MODE_BTN_HOVER', 'MODE_BTN_INACTIVE',
  'TYPER_CANVAS_DEFAULT', 'TYPER_CHROME_COLOR',
  '_BADGE_FONT_PT', '_CORPUS_BTN_LABEL', '_FOOTER_BTN_PAD_X', '_FOOTER_ITEM_GAP',
  '_GENERATING_BTN_LABEL', '_IMPROVE_BTN_LABEL',
  '_footer_btn_style', '_footer_zero_margins',
  'TyperWidget', 'configure_transparent_typer',
  'TyperWindow', 'MODE_NORMAL', 'MODE_WEAKSPOT',
  'MODE_BOOK', 'MODE_CORPUS', 'MODE_IMPROVE',
]
