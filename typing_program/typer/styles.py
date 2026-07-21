from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

_IMPROVE_BTN_LABEL = 'improve'
_CORPUS_BTN_LABEL = 'corpus'
_GENERATING_BTN_LABEL = 'generating…'
_FOOTER_ITEM_GAP = 8
# Horizontal pad inside each mode button so spacing is part of the button
# (layout gaps between widgets show the arrow cursor — jarring).
_FOOTER_BTN_PAD_X = 4
_BADGE_FONT_PT = 13
# Two-layer greys: outer chrome lighter; lesson canvas a step darker (not near-black).
TYPER_CHROME_COLOR = QColor('#4a4a4a')
TYPER_CANVAS_DEFAULT = QColor('#383838')
# Unselected footer modes — rgb(140, 140, 140).
MODE_BTN_INACTIVE = '#8c8c8c'
MODE_BTN_ACTIVE = '#ffffff'
MODE_BTN_HOVER = '#ffffff'
MODE_BTN_GREYED = '#5a5a5a'


def _footer_zero_margins(w):
  w.setContentsMargins(0, 0, 0, 0)
  if isinstance(w, QLabel):
    w.setMargin(0)


def _footer_btn_style(active=False, greyed=False):
  if greyed:
    color = MODE_BTN_GREYED
    hover = MODE_BTN_GREYED
  else:
    color = MODE_BTN_ACTIVE if active else MODE_BTN_INACTIVE
    hover = MODE_BTN_HOVER
  return (
    'QPushButton { color: %s; border: none; background: transparent; font-size: 11px;'
    ' padding: 0px %dpx; margin: 0; min-width: 0; min-height: 0; }'
    'QPushButton:hover { color: %s; }' % (color, _FOOTER_BTN_PAD_X, hover))

