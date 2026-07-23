from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

from typing_program.settings import *
from typing_program.layout import FBoxLayout
from typing_program.fwidgets import FStackedWidget
from typing_program.timingtuple import collect_focus_drill_stat_rows, collect_run_stat_rows
from typing_program.WeakSpot import WeakSpotLessonBuilder
from typing_program.WeakSpotLessons import (
  build_focus_lesson, build_trigram_gibberish_lesson, fetch_weak_trigram_targets,
)
from typing_program.Config import Settings
from typing_program.book_mode import (
  BOOK_MODE_FOOTER_VISIBLE, BookLessonBuilder, MODE_BOOK, format_book_progress, lesson_text_id,
  apply_cold_start_practice_mode,
  practice_mode_from_settings, practice_mode_to_settings, ensure_practice_mode_migrated,
  MODE_IMPROVE, MODE_CORPUS,
)
from typing_program.improve_mode import (
  IMPROVE_SUBMODE_LABELS, IMPROVE_SUBMODE_NORMAL, IMPROVE_SUBMODE_TRIGRAMS,
  clamp_improve_submode, fetch_improve_submode_targets, next_improve_submode,
)
from typing_program.lesson_placeholders import (
  BOOK_EMPTY_LABEL, CORPUS_EMPTY_LABEL, IMPROVE_EMPTY_LABEL, IMPROVE_SUBMODE_EMPTY_LABEL,
)
from typing_program.stats_query import (
  ALL_TIME_HIST, STAT_TYPE_WORD, analysis_min_count, fetch_word_book_sources,
  fetch_word_perfect_baselines,
)
from typing_program.read_ahead import (
  document_read_ahead_mode, READ_AHEAD_LEVEL_LABELS,
)
from typing_program.typer_focus import should_refocus_typer
from typing_program.keyboard_nav import cycle_practice_mode
from typing_program.follow_mode import (
  MAX_FOLLOW_WPM, MIN_FOLLOW_WPM,
  clamp_follow_wpm, follow_active, follow_footer_state, follow_index,
  follow_outcome_html, follow_race_result, follow_reached_end, parse_follow_wpm,
)
from typing_program.speed_heatmap import (
  MODE_LABELS, fetch_speed_stats, make_heatmap_legend, mode_stat_type,
)
from typing_program.word_progress import (
  analyze_run_progress, format_progress_html, lesson_words, progress_badges_for_run,
)
from collections import Counter
from time import time
import logging as log

from typing_program import timer
from typing_program.typer.document import LessonDocument
from typing_program.typer.follow_clock import FollowClock
from typing_program.typer.widget import TyperWidget, configure_transparent_typer
from typing_program.typer.pause_overlay import _LessonPauseOverlay
from typing_program.typer.source_attr import format_source_attribution, lesson_completion_action
from typing_program.typer.styles import (
  MODE_BTN_ACTIVE, MODE_BTN_GREYED, MODE_BTN_HOVER, MODE_BTN_INACTIVE,
  TYPER_CANVAS_DEFAULT, TYPER_CHROME_COLOR,
  _CORPUS_BTN_LABEL, _FOOTER_BTN_PAD_X, _FOOTER_ITEM_GAP, _GENERATING_BTN_LABEL,
  _IMPROVE_BTN_LABEL, _footer_btn_style, _footer_zero_margins,
)

MODE_NORMAL = MODE_CORPUS
MODE_WEAKSPOT = MODE_IMPROVE

class TyperWindow(QWidget):
  wantReview = pyqtSignal('PyQt_PyObject')
  wantText = pyqtSignal()
  needWeakspotLesson = pyqtSignal(str)
  statsChanged = pyqtSignal()
  
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.setObjectName('TyperWindow')
    # Required for background-color in stylesheets on QWidget (macOS/Qt otherwise
    # ignores the fill once the widget is reparented into the tab pane).
    self.setAttribute(Qt.WA_StyledBackground, True)

    app = QApplication.instance()
    self._settings = app.settings
    self.S = app.settings.typer_settings
    self.DB = app.DB

    self._current_lesson = None
    self._read_ahead_on = False
    self._read_ahead_level = 0
    self._mode = MODE_IMPROVE
    self._improve_submode = 0
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._focus_drill_from_pa = False
    self._awaiting_next = False
    self._pending_action = None
    self._pending_now = None
    self._pending_review_words = None
    self._weakspot = WeakSpotLessonBuilder(self)
    self._weakspot.lessonReady.connect(self._on_weakspot_lesson)
    self._weakspot.busyChanged.connect(self._on_weakspot_busy)
    self._book = BookLessonBuilder(self.DB, self)
    self._book.lessonReady.connect(self._on_book_lesson)
    self._book.progressChanged.connect(self._on_book_progress)
    self._book_meta = None
    self._typer = TyperWidget(self.S)
    self._typer._on_tab_nav = self.cycle_improve_submode
    hack = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Ignored)
    self._label = QLabel(wordWrap=True, sizePolicy=hack)
    self._prog = QProgressBar()
    self._prog.setTextVisible(False)
    self._prog.setValue(0)
    self._progw = FStackedWidget([QLabel('Type like the wind!'), self._prog])
    self._prog_layout = FStackedWidget([self._label, self._progw])

    self.S('show_progress').bind_value(self._on_show_progress_pref, call=True)
    self.S('require_space').bind_change(lambda: self.updateLabel())

    # I am so confused. Settings system must have gone through 3 totally different paradigms.
    self._settings.signal_for("typer_font").connect(self.updateFont)

    doc = LessonDocument(self._settings.getFont('typer_font'))

    for var in self._settings.typer_colors:
      var.onChange.connect(doc.onColor)
      doc.onColor(var)
    for vname in ['para_lineheight', 'para_margin']:
      var = self._settings.typer_settings(vname)
      var.onChange.connect(doc.onColor)
      doc.onColor(var)

    # Progress strip is shown before the first keystroke (empty bar), not only after start.
    doc.started.connect(self._show_progress_strip)
    doc.started.connect(self._on_lesson_started)
    doc.progress.connect(self._prog.setValue)
    doc.ready.connect(self.typingReady)
    doc.ready.connect(self._on_lesson_ready)
    doc.completed.connect(self.typingDone)
    doc.follow_lost.connect(self.typingFollowLost)
    doc.paused.connect(self._on_lesson_paused)
    doc.resumed.connect(self._on_lesson_resumed)

    self._typer.setLesson(doc)
    self._doc = doc

    # Canvas = darker lesson page (background_color), same rect as the pause overlay.
    # Outer TyperWindow stays chrome gray. TyperWidget is transparent on the canvas.
    self._pause_overlay = _LessonPauseOverlay(None)
    self._pause_overlay.continueClicked.connect(self._doc.resume)
    self._pause_overlay.restartClicked.connect(self._restart_lesson)
    self._pause_overlay.newClicked.connect(self._new_lesson)
    self._canvas = QWidget()
    self._canvas.setObjectName('TyperCanvas')
    self._canvas.setAttribute(Qt.WA_StyledBackground, True)
    self._canvas.setLayout(FBoxLayout([self._typer]))
    self._pause_overlay.setParent(self._canvas)
    self._typer._pause_overlay = self._pause_overlay
    self._canvas.installEventFilter(self)

    self._source_lbl = QLabel(wordWrap=True)
    self._source_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    # Book/corpus titles usually wrap to two footer lines and shrink the canvas.
    # Reserve that height in improve too (Minimum policy — minHeight alone is ignored).
    self._source_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    self._source_lbl.setMinimumHeight(2 * self._source_lbl.fontMetrics().height())
    self._source_lbl.installEventFilter(self)
    self._book_prog_text = ''

    self._mode_btn_style = (
      'QPushButton { color: %s; border: none; background: transparent; font-size: 11px;'
      ' padding: 0px %dpx; margin: 0; min-width: 0; min-height: 0; }'
      'QPushButton:hover { color: %s; }'
      'QPushButton[activeMode="true"] { color: %s; }' % (
        MODE_BTN_INACTIVE, _FOOTER_BTN_PAD_X, MODE_BTN_HOVER, MODE_BTN_ACTIVE))

    self._btn_improve = self._make_footer_btn(_IMPROVE_BTN_LABEL, slot=self._on_improve_click)
    self._btn_book = self._make_footer_btn('book', slot=lambda: self.set_practice_mode(MODE_BOOK))
    if not BOOK_MODE_FOOTER_VISIBLE:
      self._btn_book.setVisible(False)
    self._btn_corpus = self._make_footer_btn(_CORPUS_BTN_LABEL, slot=self._on_corpus_click)
    self._btn_read_ahead = self._make_footer_btn('read ahead', slot=self.toggle_read_ahead)
    self._btn_read_ahead_level = self._make_footer_btn('normal', slot=self.cycle_read_ahead_level)
    self._btn_block_bkspc = self._make_footer_btn('Block ⌫', slot=self.toggle_block_bkspc)
    self._btn_improve_level = self._make_footer_btn('normal', slot=self.cycle_improve_submode)
    self._btn_follow = self._make_footer_btn('follow', mode_style=False, slot=self._toggleFollow)
    self._follow_wpm_panel = self._make_follow_wpm_panel()
    self._btn_heatmap = self._make_footer_btn('heatmap', mode_style=False, slot=self._toggleHeatmap)
    self._btn_heatmap_kind = self._make_footer_btn('', mode_style=False, slot=self._cycleHeatmapMode)
    self._weakspot_generating = False

    self._heatmap_legend = make_heatmap_legend()
    self._heatmap_panel = QWidget()
    self._heatmap_panel.setFocusPolicy(Qt.NoFocus)
    hp_lay = QHBoxLayout(self._heatmap_panel)
    hp_lay.setContentsMargins(0, 0, 0, 0)
    hp_lay.setSpacing(0)
    hp_lay.addWidget(self._btn_heatmap_kind, 0)
    hp_lay.addWidget(self._heatmap_legend, 0)

    # Spacing lives in button padding (not layout gaps) so the hand cursor
    # never drops to arrow between mode labels.
    self._footer_controls = QWidget()
    self._footer_controls.setFocusPolicy(Qt.NoFocus)
    controls_lay = QHBoxLayout(self._footer_controls)
    controls_lay.setContentsMargins(0, 0, 0, 0)
    controls_lay.setSpacing(0)
    self._heatmap_panel.setVisible(False)
    self._follow_wpm_panel.setVisible(False)
    for w in (self._btn_improve, self._btn_improve_level, self._btn_corpus, self._btn_book,
              self._btn_read_ahead, self._btn_read_ahead_level, self._btn_block_bkspc,
              self._btn_heatmap, self._heatmap_panel, self._btn_follow, self._follow_wpm_panel):
      controls_lay.addWidget(w)

    mode_row = QWidget()
    mode_row.setFocusPolicy(Qt.NoFocus)
    mode_lay = QHBoxLayout(mode_row)
    mode_lay.setContentsMargins(0, 0, 0, 0)
    mode_lay.setSpacing(_FOOTER_ITEM_GAP)
    # Footer: [improve · corpus · … · follow] · stretch · source title
    mode_lay.addWidget(self._footer_controls, 0)
    mode_lay.addStretch(1)
    mode_lay.addWidget(self._source_lbl)

    self._follow_timer = QTimer(self)
    self._follow_timer.setInterval(50)
    self._follow_timer.timeout.connect(self._on_follow_tick)
    self._follow_racing = False
    self._follow_race_outcome = None
    self._follow_clock = FollowClock(timer)

    self.S('speed_heatmap').bind_value(self._onHeatmapSetting, call=True)
    self.S('speed_heatmap_mode').bind_value(self._onHeatmapSetting, call=True)
    self.S('word_delete_enabled').bind_value(self._onBlockBkspcSetting, call=True)
    self.S('follow_mode').bind_value(self._onFollowSetting, call=True)
    self.S('follow_wpm').bind_value(self._onFollowWpmSetting, call=True)

    self.setLayout(FBoxLayout([
      (self._prog_layout, 0),
      (self._canvas, 100),
      (mode_row, 0),
      ]))

    self.S('background_color').bind_value(self._applyBackground, call=True)
    self.statsChanged.connect(self._weakspot.on_stats_changed)
    ensure_practice_mode_migrated(self._settings)
    # Cold start always Typer at improve · normal (ignore last session's mode).
    apply_cold_start_practice_mode(self._settings, self.S)
    self.S('improve_submode').bind_value(self._onImproveSubmodeSetting, call=True)
    self._apply_practice_mode_from_settings()
    self._apply_read_ahead_from_settings()
    self._refresh_follow_footer()
    self._install_keyboard_nav()
    self._install_typer_focus_guard()

  def _install_typer_focus_guard(self):
    """Lesson keeps keyboard focus; only the follow WPM box may steal it."""
    for w in (self, self._canvas, self._label, self._prog, self._progw,
              self._source_lbl, self._heatmap_legend, self._heatmap_panel,
              self._follow_wpm_panel):
      w.setFocusPolicy(Qt.NoFocus)
    # Child timer dies with this widget — avoids singleShot callbacks after teardown.
    self._typer_refocus_timer = QTimer(self)
    self._typer_refocus_timer.setSingleShot(True)
    self._typer_refocus_timer.timeout.connect(self._ensure_typer_focus)
    app = QApplication.instance()
    if app is None:
      return
    slot = self._on_app_focus_changed
    app.focusChanged.connect(slot)
    def _disconnect(*_args):
      try:
        app.focusChanged.disconnect(slot)
      except (TypeError, RuntimeError):
        pass
    self.destroyed.connect(_disconnect)

  def _focus_inside_typer_window(self, widget):
    return widget is not None and (widget is self or self.isAncestorOf(widget))

  def _on_app_focus_changed(self, _old, new):
    try:
      visible = self.isVisible()
      inside = self._focus_inside_typer_window(new)
      edit = getattr(self, '_follow_wpm_edit', None)
      typer = self._typer
    except RuntimeError:
      return  # TyperWindow already destroyed (app focusChanged during teardown)
    if not should_refocus_typer(new, visible, inside, typer, edit):
      return
    # Defer so button clicks finish before we reclaim focus.
    self._typer_refocus_timer.start(0)

  def _ensure_typer_focus(self):
    try:
      edit = getattr(self, '_follow_wpm_edit', None)
      if edit is not None and edit.hasFocus():
        return
      if not self.isVisible():
        return
      self._typer.setFocus(Qt.OtherFocusReason)
    except RuntimeError:
      return

  def _install_keyboard_nav(self):
    """Cmd/Ctrl+Opt/Alt+←→ cycle practice mode. Tab cycles submode (TyperWidget).

    QKeySequence 'Ctrl' is Command on macOS, 'Alt' is Option. Tab is not a
    QShortcut — QTextEdit would otherwise swallow it or double-fire.
    """
    self._sc_submode = None  # Tab via TyperWidget._on_tab_nav → cycle_improve_submode
    self._sc_mode_next = QShortcut(QKeySequence('Ctrl+Alt+Right'), self)
    self._sc_mode_next.setContext(Qt.WidgetWithChildrenShortcut)
    self._sc_mode_next.activated.connect(lambda: self._cycle_practice_mode(1))
    self._sc_mode_prev = QShortcut(QKeySequence('Ctrl+Alt+Left'), self)
    self._sc_mode_prev.setContext(Qt.WidgetWithChildrenShortcut)
    self._sc_mode_prev.activated.connect(lambda: self._cycle_practice_mode(-1))

  def _cycle_practice_mode(self, delta):
    self.set_practice_mode(cycle_practice_mode(self._mode, delta))

  def _make_footer_btn(self, label='', *, mode_style=True, slot=None):
    b = QPushButton(label, flat=True)
    b.setFocusPolicy(Qt.NoFocus)
    b.setCursor(Qt.PointingHandCursor)
    b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
    _footer_zero_margins(b)
    if mode_style:
      b.setStyleSheet(self._mode_btn_style)
    if slot is not None:
      b.clicked.connect(slot)
    return b

  def _polish_mode_btn(self, btn):
    btn.style().unpolish(btn)
    btn.style().polish(btn)

  def _set_mode_btn_active(self, btn, active):
    btn.setStyleSheet(self._mode_btn_style)
    btn.setProperty('activeMode', active)
    self._polish_mode_btn(btn)
    btn.setCursor(Qt.PointingHandCursor)

  def _clear_focus_drill(self):
    self._focus_drill = None
    self._focus_drill_wpm = {}
    self._focus_drill_from_pa = False

  def _load_for_mode(self, mode):
    """Load a lesson for improve / book / corpus (invalidate book cache when needed)."""
    if mode in (MODE_WEAKSPOT, MODE_IMPROVE):
      self._load_improve_lesson()
    elif mode == MODE_BOOK:
      self._book.invalidate_cache()
      self._book.request_lesson(advance_chapter=False)
    else:
      self._set_improve_footer_busy(False)
      self.wantText.emit()

  def _activate_loaded_lesson(self, text_len, center=True, focus=True):
    """Shared chrome after a lesson body is in the document."""
    if center:
      self._schedule_typing_center()
    else:
      self._typer._pin_typing_center = False
    self._refreshHeatmap()
    if focus:
      self._typer.setFocus()
    self._prog.setMaximum(max(1, text_len))
    self._prog.setValue(0)
    self._show_progress_strip()

  def _refresh_book_btn(self):
    if self._mode == MODE_BOOK and self._book_prog_text:
      self._btn_book.setText('book · ' + self._book_prog_text)
    else:
      self._btn_book.setText('book')

  def _apply_read_ahead_from_settings(self):
    enabled = bool(self._settings.get('read_ahead_enabled'))
    level = self.S['read_ahead_level']
    self._set_read_ahead_ui(enabled, level, refresh_doc=True)

  def _onImproveSubmodeSetting(self, level):
    self._set_improve_submode_ui(level)

  def cycle_improve_submode(self):
    if self._mode != MODE_IMPROVE:
      return
    level = next_improve_submode(
      self._improve_submode, self.DB, ALL_TIME_HIST, Settings.get('analysis_count'))
    self._focus_drill_from_pa = False
    self.S('improve_submode').set(level)
    self._load_improve_lesson()

  def _set_improve_submode_ui(self, level):
    self._improve_submode = level
    visible = self._mode == MODE_IMPROVE
    self._btn_improve_level.setText(IMPROVE_SUBMODE_LABELS[level])
    self._btn_improve_level.setVisible(visible)
    if visible:
      self._set_mode_btn_active(self._btn_improve_level, True)

  def _load_improve_lesson(self):
    # Drop empty oblivion (and any other unavailable saved index) before loading.
    submode = clamp_improve_submode(
      self._improve_submode, self.DB, ALL_TIME_HIST, Settings.get('analysis_count'))
    if submode != self._improve_submode:
      self._improve_submode = submode
      self._set_improve_submode_ui(submode)
      self.S('improve_submode').set(submode)
    if submode == IMPROVE_SUBMODE_NORMAL:
      self._clear_focus_drill()
      self._weakspot.request_next_lesson(force=True)
      return
    if submode == IMPROVE_SUBMODE_TRIGRAMS:
      self._clear_focus_drill()
      targets = fetch_weak_trigram_targets(
        self.DB, ALL_TIME_HIST, Settings.get('analysis_count'), Settings.get('analysis_many'))
      if not targets:
        self._show_idle_placeholder(IMPROVE_SUBMODE_EMPTY_LABEL)
        return
      lesson = build_trigram_gibberish_lesson(
        targets, min_chars=Settings.get('min_chars'), max_chars=Settings.get('max_chars'))
      if not lesson:
        self._show_idle_placeholder(IMPROVE_SUBMODE_EMPTY_LABEL)
        return
      self._set_improve_footer_busy(False)
      self.needWeakspotLesson.emit(lesson)
      return
    targets = fetch_improve_submode_targets(
      self.DB, submode, ALL_TIME_HIST, Settings.get('analysis_count'))
    if not targets:
      self._show_idle_placeholder(IMPROVE_SUBMODE_EMPTY_LABEL)
      return
    self._start_focus_drill(targets, from_pa=False)

  def toggle_read_ahead(self):
    enabled = not self._read_ahead_on
    self._settings.set('read_ahead_enabled', enabled)
    self._set_read_ahead_ui(enabled, self._read_ahead_level, refresh_doc=True)

  def cycle_read_ahead_level(self):
    if not self._read_ahead_on:
      return
    level = (self._read_ahead_level + 1) % len(READ_AHEAD_LEVEL_LABELS)
    self.S('read_ahead_level').set(level)
    self._set_read_ahead_ui(True, level, refresh_doc=True)

  def _set_read_ahead_ui(self, enabled, level, refresh_doc=False):
    self._read_ahead_on = enabled
    self._read_ahead_level = level
    self._set_mode_btn_active(self._btn_read_ahead, enabled)
    self._btn_read_ahead_level.setText(READ_AHEAD_LEVEL_LABELS[level])
    self._btn_read_ahead_level.setVisible(enabled)
    if enabled:
      self._set_mode_btn_active(self._btn_read_ahead_level, True)
    if refresh_doc:
      self._doc.set_read_ahead_mode(document_read_ahead_mode(enabled, level))

  def toggle_block_bkspc(self):
    self.S('word_delete_enabled').set(not self.S('word_delete_enabled').get())

  def _onBlockBkspcSetting(self, *_):
    on = bool(self.S('word_delete_enabled').get())
    self._set_mode_btn_active(self._btn_block_bkspc, on)

  def updateFont(self):
    self._doc.setDefaultFont(self._settings.getFont('typer_font'))

  def _toggleHeatmap(self):
    self.S('speed_heatmap').set(not self.S('speed_heatmap').get())

  def _cycleHeatmapMode(self):
    mode = (self.S('speed_heatmap_mode').get() + 1) % len(MODE_LABELS)
    self.S('speed_heatmap_mode').set(mode)

  def _style_heatmap_footer_btn(self, btn, on):
    btn.setStyleSheet(_footer_btn_style(on))
    btn.setCursor(Qt.PointingHandCursor)

  def _onHeatmapSetting(self, *_):
    on = bool(self.S('speed_heatmap').get())
    mode = int(self.S('speed_heatmap_mode').get())
    self._style_heatmap_footer_btn(self._btn_heatmap, on)
    self._heatmap_panel.setVisible(on)
    self._btn_heatmap_kind.setText(MODE_LABELS[mode])
    self._style_heatmap_footer_btn(self._btn_heatmap_kind, on)
    self._refreshHeatmap()

  def _toggleFollow(self):
    if not follow_footer_state(True, self._mode)['eligible']:
      return
    self.S('follow_mode').set(not self.S('follow_mode').get())

  def _make_follow_wpm_panel(self):
    """Minimal − N + stepper matching the footer (no chrome box)."""
    panel = QWidget()
    lay = QHBoxLayout(panel)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    btn_style = (
      'QPushButton { color: %s; border: none; background: transparent; font-size: 11px;'
      ' padding: 0; margin: 0; min-width: 0; min-height: 0; }'
      'QPushButton:hover { color: %s; }' % (MODE_BTN_ACTIVE, MODE_BTN_HOVER))
    self._follow_wpm_down = QPushButton('−', flat=True)
    self._follow_wpm_up = QPushButton('+', flat=True)
    for b in (self._follow_wpm_down, self._follow_wpm_up):
      b.setFocusPolicy(Qt.NoFocus)
      b.setStyleSheet(btn_style)
      b.setCursor(Qt.PointingHandCursor)
      b.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
      b.setFixedWidth(14)
      _footer_zero_margins(b)
    self._follow_wpm_edit = QLineEdit()
    self._follow_wpm_edit.setAlignment(Qt.AlignCenter)
    self._follow_wpm_edit.setFixedWidth(28)
    self._follow_wpm_edit.setMaxLength(3)
    self._follow_wpm_edit.setFocusPolicy(Qt.ClickFocus)
    self._follow_wpm_edit.setToolTip('Follow caret speed (WPM)')
    self._follow_wpm_edit.setStyleSheet(
      'QLineEdit { color: %s; background: transparent; border: none;'
      ' font-size: 11px; padding: 0; margin: 0; selection-background-color: #555; }'
      % MODE_BTN_ACTIVE)
    self._follow_wpm_edit.setText(str(clamp_follow_wpm(self.S('follow_wpm').get())))
    self._follow_wpm_edit.setValidator(QIntValidator(MIN_FOLLOW_WPM, MAX_FOLLOW_WPM, self))
    self._follow_wpm_down.clicked.connect(lambda: self._nudge_follow_wpm(-1))
    self._follow_wpm_up.clicked.connect(lambda: self._nudge_follow_wpm(1))
    self._follow_wpm_edit.textChanged.connect(self._on_follow_wpm_text)
    self._follow_wpm_edit.installEventFilter(self)
    lay.addWidget(self._follow_wpm_down, 0)
    lay.addWidget(self._follow_wpm_edit, 0)
    lay.addWidget(self._follow_wpm_up, 0)
    return panel

  def _nudge_follow_wpm(self, delta):
    wpm = clamp_follow_wpm(int(self.S('follow_wpm').get()) + delta)
    self.S('follow_wpm').set(wpm)
    self._sync_follow_wpm_edit(wpm)

  def _sync_follow_wpm_edit(self, wpm):
    text = str(clamp_follow_wpm(wpm))
    if self._follow_wpm_edit.text() != text:
      self._follow_wpm_edit.blockSignals(True)
      self._follow_wpm_edit.setText(text)
      self._follow_wpm_edit.blockSignals(False)

  def _on_follow_wpm_text(self, text):
    # Live: whatever number is in the box is the speed (empty → keep last until valid).
    s = (text or '').strip()
    if not s:
      return
    wpm = parse_follow_wpm(s, default=int(self.S('follow_wpm').get()))
    if wpm != int(self.S('follow_wpm').get()):
      self.S('follow_wpm').set(wpm)

  def _blur_follow_wpm(self):
    """Commit the box and return focus to the lesson canvas."""
    wpm = parse_follow_wpm(self._follow_wpm_edit.text(), default=int(self.S('follow_wpm').get()))
    self.S('follow_wpm').set(wpm)
    self._sync_follow_wpm_edit(wpm)
    self._typer.setFocus()

  def _onFollowSetting(self, *_):
    self._refresh_follow_footer()

  def _onFollowWpmSetting(self, *_):
    self._sync_follow_wpm_edit(self.S('follow_wpm').get())
    # Live WPM: next tick uses the new value; no Enter required.
    if self._follow_racing:
      self._on_follow_tick()

  def _refresh_follow_footer(self):
    enabled = bool(self.S('follow_mode').get())
    st = follow_footer_state(enabled, self._mode)
    self._btn_follow.setEnabled(st['btn_enabled'])
    self._btn_follow.setStyleSheet(
      _footer_btn_style(active=st['btn_active_style'], greyed=st['btn_greyed']))
    self._btn_follow.setCursor(Qt.PointingHandCursor if st['btn_enabled'] else Qt.ArrowCursor)
    self._follow_wpm_panel.setVisible(st['wpm_visible'])
    if st['active']:
      self._arm_follow_race()
    else:
      self._stop_follow_race(clear_caret=True)

  def _follow_is_active(self):
    return follow_active(self.S('follow_mode').get(), self._mode)

  def _arm_follow_race(self):
    """Show the follow caret at the start; timer runs once the lesson starts."""
    if not self._follow_is_active() or not self._doc._match_text:
      self._typer.set_follow_cursor_index(None)
      return
    self._follow_race_outcome = None
    self._typer.set_follow_cursor_index(0)
    if self._doc.is_running() and not self._doc.is_paused():
      self._follow_clock.start()
      self._follow_racing = True
      if not self._follow_timer.isActive():
        self._follow_timer.start()
      self._on_follow_tick()
    else:
      self._follow_racing = False
      self._follow_timer.stop()
      self._follow_clock.reset()

  def _stop_follow_race(self, clear_caret=False):
    self._follow_racing = False
    self._follow_timer.stop()
    self._follow_clock.reset()
    if clear_caret:
      self._typer.set_follow_cursor_index(None)

  def _on_follow_tick(self):
    if not self._follow_racing or not self._follow_is_active():
      self._stop_follow_race(clear_caret=not self._follow_is_active())
      return
    text = self._doc._match_text or ''
    if not self._doc._run or not text:
      return
    if self._doc.is_paused():
      return
    wpm = int(self.S('follow_wpm').get())
    elapsed = self._follow_clock.elapsed()
    idx = follow_index(elapsed, wpm, len(text))
    self._typer.set_follow_cursor_index(idx)
    user_done = bool(self._doc._run.is_complete())
    cursor_done = follow_reached_end(elapsed, wpm, len(text))
    outcome = follow_race_result(user_done, cursor_done)
    if outcome == 'failure':
      self._follow_race_outcome = 'failure'
      self._stop_follow_race(clear_caret=False)
      self._doc.lose_follow_race()
    elif outcome == 'success':
      self._follow_race_outcome = 'success'
      self._stop_follow_race(clear_caret=False)

  def _heatmapStats(self):
    mode = self.S('speed_heatmap_mode').get()
    stats = fetch_speed_stats(self.DB, hist_cutoff=0, stat_type=mode_stat_type(mode))
    if self._focus_drill and self._focus_drill_wpm:
      stats = dict(stats)
      for kind, data in self._focus_drill:
        wpm = self._focus_drill_wpm.get(data)
        if wpm is not None:
          prev = stats.get(data) or {}
          stats[data] = {**prev, 'wpm': wpm}
    return stats

  def _refreshHeatmap(self):
    self._doc.set_speed_heatmap(
      self.S('speed_heatmap').get(),
      self.S('speed_heatmap_mode').get(),
      self._heatmapStats())

  def _paint_solid_bg(self, widget, selector, color):
    """Solid fill that survives tab reparent on macOS (needs WA_StyledBackground)."""
    qcolor = color if isinstance(color, QColor) else QColor(color)
    name = qcolor.name()
    widget.setAttribute(Qt.WA_StyledBackground, True)
    pal = widget.palette()
    pal.setColor(QPalette.Window, qcolor)
    pal.setColor(QPalette.Base, qcolor)
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)
    widget.setStyleSheet('%s { background-color: %s; }' % (selector, name))
    # Re-assert after setStyleSheet (polish can clear these).
    widget.setAttribute(Qt.WA_StyledBackground, True)
    widget.setAutoFillBackground(True)

  def _applyBackground(self, color):
    """Two layers — do not collapse them into one color.

    1. TyperWindow (chrome around the lesson): system window gray — footer,
       margins, area outside the pause rectangle.
    2. TyperCanvas (lesson page): user background_color — same rectangle as the
       ESC pause overlay; darker than chrome, lighter than the pause dim.

    The lesson QTextEdit stays transparent on the canvas. Main tab ::pane must
    stay transparent so neither layer is covered.
    """
    if hasattr(color, 'name'):
      page = color
    else:
      page = QColor(color)
    self._paint_solid_bg(self, 'TyperWindow', TYPER_CHROME_COLOR)
    self._paint_solid_bg(self._canvas, 'QWidget#TyperCanvas', page)
    configure_transparent_typer(self._typer)
    self._doc.set_page_background(page)

  def eventFilter(self, obj, evt):
    if obj is self._canvas and evt.type() == QEvent.Resize:
      self._pause_overlay.setGeometry(self._canvas.rect())
    if getattr(self, '_follow_wpm_edit', None) is obj and evt.type() == QEvent.KeyPress:
      if evt.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Escape):
        self._blur_follow_wpm()
        return True
    if obj is self._source_lbl and self._mode == MODE_BOOK:
      if evt.type() == QEvent.MouseButtonRelease and evt.button() == Qt.LeftButton:
        self._show_book_menu()
        return True
    return super().eventFilter(obj, evt)

  def showEvent(self, evt):
    # Re-apply after tab reparent/style polish so the page fill cannot be lost.
    self._applyBackground(self.S['background_color'])
    self._typer.setFocus()
    if self._typer._pin_typing_center:
      QTimer.singleShot(0, self._typer._center_typing_when_ready)
    return super().showEvent(evt)

  def _on_lesson_started(self):
    self._typer._pin_typing_center = False
    if self._follow_is_active():
      self._follow_clock.start()
      self._follow_racing = True
      self._follow_race_outcome = None
      if not self._follow_timer.isActive():
        self._follow_timer.start()
      self._on_follow_tick()

  def _on_lesson_paused(self):
    self._follow_clock.pause()
    self._pause_overlay.setGeometry(self._canvas.rect())
    self._pause_overlay.show()
    self._pause_overlay.raise_()
    self._typer.updateStatus()

  def _on_lesson_resumed(self):
    self._follow_clock.resume()
    self._pause_overlay.hide()
    self._typer.updateStatus()
    self._typer.setFocus()
    if self._follow_is_active() and self._doc.is_running():
      self._follow_racing = True
      if not self._follow_timer.isActive():
        self._follow_timer.start()

  def _restart_lesson(self):
    self._pause_overlay.hide()
    self._stop_follow_race(clear_caret=False)
    self._doc.reset()
    if self._follow_is_active():
      self._arm_follow_race()
    self._typer.setFocus()

  def _new_lesson(self):
    self._pause_overlay.hide()
    if self._doc.is_paused():
      self._doc.resume()
    self._request_new_lesson()
    self._typer.setFocus()

  def _request_new_lesson(self):
    """Load a fresh exercise for the current practice mode."""
    if self._mode in (MODE_WEAKSPOT, MODE_IMPROVE) and self._focus_drill:
      # Auto improve drills re-sample targets; PA drills keep the chosen targets.
      if self._focus_drill_from_pa:
        if not self._emit_focus_lesson(self._focus_drill):
          self.updateLabel('Could not rebuild focus drill for those targets.')
      else:
        self._load_improve_lesson()
      return
    self._load_for_mode(self._mode)

  def _schedule_typing_center(self):
    self._typer.setTextCursor(self._doc.cursor)
    self._typer._pin_typing_center = True
    QTimer.singleShot(0, self._typer._center_typing_when_ready)

  def _on_show_progress_pref(self, on):
    self._progw.setCurrentIndex(1 if on else 0)
    # Prefer the progress strip over an empty status label when the pref is on.
    if on and not self._awaiting_next and not (self._label.text() or '').strip():
      self._prog_layout.setCurrentIndex(1)

  def _show_progress_strip(self):
    """Top area: empty or live progress bar (or wind text if progress pref is off)."""
    self._prog_layout.setCurrentIndex(1)
    self._progw.setCurrentIndex(1 if self.S['show_progress'] else 0)

  def _show_result_label(self):
    """Top area: post-lesson summary / prompts."""
    self._prog_layout.setCurrentIndex(0)

  def typingReady(self, text):
    self._pause_overlay.hide()
    self._prog.setMaximum(max(1, len(text)))
    self._prog.setValue(0)
    self._show_progress_strip()
    if self._follow_is_active():
      self._arm_follow_race()
    else:
      self._typer.set_follow_cursor_index(None)

  def setDefaultText(self):
    log.error("setDefaultText() NOT IMPLEMENTED")
    print("setDefaultText() NOT IMPLEMENTED")

  def setText(self, txt):
    body = (txt[2] or '').strip()
    if self._mode == MODE_CORPUS and not body:
      self._show_idle_placeholder(CORPUS_EMPTY_LABEL)
      return
    self._current_lesson = txt
    textid, srcid, _ = txt
    self._update_source_label(srcid)
    pre, _, post = self.DB.getTextContext(textid)

    # Only show real surrounding context from the same source. Never insert ugly placeholder labels.
    prologue = (pre[2] + '\n') if pre is not None else ''
    epilogue = ('\n' + post[2]) if post is not None else ''

    self._doc.set_text(txt[2], prologue=prologue, epilogue=epilogue)
    self._activate_loaded_lesson(len(txt[2] or ''), center=(self._mode == MODE_CORPUS))

  def _update_source_label(self, srcid):
    row = self.DB.fetchone('select name from source where rowid=?', (None,), (srcid,))
    text = format_source_attribution(row[0] if row else '')
    self._source_lbl.setText(text)
    # Keep visible even when empty so improve/corpus canvas height stays aligned.
    self._source_lbl.setVisible(True)

  def _update_book_footer(self, meta=None):
    if meta is None:
      meta = self._book_meta or {}
    prog = format_book_progress(
      meta.get('title') or '', meta.get('chunk_index', 0), meta.get('chunk_count', 0))
    self._book_prog_text = prog
    self._refresh_book_btn()
    book = meta.get('book_name') or ''
    self._source_lbl.setText(format_source_attribution(book))
    self._source_lbl.setVisible(True)
    self._source_lbl.setCursor(Qt.PointingHandCursor if book else Qt.ArrowCursor)

  def _show_book_menu(self):
    menu = QMenu(self)
    cur = self._book.current_source_id()
    for sid, _, label in self._book.source_menu_entries():
      act = menu.addAction(label)
      act.setCheckable(True)
      act.setChecked(sid == cur)
      act.triggered.connect(lambda _=False, s=sid: self._select_book(s))
    menu.exec_(self._source_lbl.mapToGlobal(QPoint(0, self._source_lbl.height())))

  def _select_book(self, source_id):
    self._book.set_source_id(int(source_id))
    self._book.request_lesson(advance_chapter=False)

  def _on_book_progress(self, msg):
    if self._mode == MODE_BOOK:
      self._book_prog_text = msg
      self._refresh_book_btn()

  def _show_idle_placeholder(self, msg):
    self._pause_overlay.hide()
    self._stop_follow_race(clear_caret=True)
    self._current_lesson = None
    self._book_meta = None
    self._doc.set_idle_message(msg)
    self._source_lbl.clear()
    self._source_lbl.setVisible(True)
    self._source_lbl.setCursor(Qt.ArrowCursor)
    self._typer.setReadOnly(True)
    self._typer._pin_typing_center = False
    self._prog.setValue(0)
    self._prog.setMaximum(1)
    self._show_progress_strip()
    self.updateLabel()

  def _on_book_lesson(self, lesson):
    if self._mode != MODE_BOOK:
      return
    if not lesson:
      self._show_idle_placeholder(BOOK_EMPTY_LABEL)
      return
    tid, srcid, meta = lesson
    body = meta['full_text']
    chunks = meta['chunks']
    if self._settings.get('text_force_ascii'):
      from typing_program.TextManager import force_ascii
      body = force_ascii(body)
      chunks = [force_ascii(c) for c in chunks]
      meta = dict(meta, full_text=body, chunks=chunks)
    self._book_meta = meta
    active = chunks[meta['chunk_index']]
    self._current_lesson = (tid, srcid, active)
    self._update_book_footer(meta)
    self._doc.set_book_chapter(body, chunks, meta['chunk_index'], auto_returns=True)
    self._activate_loaded_lesson(len(active), center=True)

  def _apply_practice_mode_from_settings(self):
    mode = practice_mode_from_settings(self._settings.get('practice_mode'))
    self._set_mode_ui(mode, load=False)
    # Cold start is improve; do not emit wantText for corpus here.
    if mode in (MODE_IMPROVE, MODE_BOOK):
      self._load_for_mode(mode)

  def _on_improve_click(self):
    if self._mode == MODE_IMPROVE and (self._focus_drill or self._improve_submode != IMPROVE_SUBMODE_NORMAL):
      self._exit_focus_drill()
      return
    self.set_practice_mode(MODE_IMPROVE)

  def _on_corpus_click(self):
    if self._mode == MODE_CORPUS:
      self._set_improve_footer_busy(False)
      self.wantText.emit()
      return
    self.set_practice_mode(MODE_CORPUS)

  def _exit_focus_drill(self):
    self._clear_focus_drill()
    if self._improve_submode != IMPROVE_SUBMODE_NORMAL:
      self.S('improve_submode').set(IMPROVE_SUBMODE_NORMAL)
    self._weakspot.request_next_lesson(force=True)

  def load_corpus_text(self, v):
    """Open a corpus chunk in corpus mode (from Performance Analysis Find in corpus)."""
    self._clear_focus_drill()
    self._settings.set('practice_mode', practice_mode_to_settings(MODE_CORPUS))
    self._set_mode_ui(MODE_CORPUS, load=False)
    self.setText(v)

  def _emit_focus_lesson(self, targets):
    wl = str(Settings.DATA_DIR / 'wordlists' / 'words-20.txt')
    lesson = build_focus_lesson(
      targets, wordlist_path=wl,
      min_chars=Settings.get('focus_min_chars'),
      max_chars=Settings.get('focus_max_chars'))
    if not lesson:
      return False
    self._set_improve_footer_busy(False)
    self.needWeakspotLesson.emit(lesson)
    return True

  def _start_focus_drill(self, targets, from_pa=False):
    self._focus_drill = [(t[0], t[1]) for t in targets]
    self._focus_drill_wpm = {}
    self._focus_drill_from_pa = from_pa
    for t in targets:
      if len(t) > 2 and t[2] is not None:
        self._focus_drill_wpm[t[1]] = t[2]
    if not self._emit_focus_lesson(self._focus_drill):
      self._clear_focus_drill()
      self.updateLabel('Could not build a drill for those targets.')
      return False
    return True

  def start_focus_drill(self, targets):
    """Start improve focus drill on specific type targets from Performance Analysis."""
    self._settings.set('practice_mode', practice_mode_to_settings(MODE_IMPROVE))
    self._set_mode_ui(MODE_IMPROVE, load=False)
    if not self._start_focus_drill(targets, from_pa=True):
      return

  def set_practice_mode(self, mode):
    if mode == self._mode:
      return
    self._clear_focus_drill()
    self._settings.set('practice_mode', practice_mode_to_settings(mode))
    self._set_mode_ui(mode, load=True)

  def _set_mode_ui(self, mode, load):
    self._mode = mode
    for btn, m in ((self._btn_improve, MODE_IMPROVE), (self._btn_corpus, MODE_CORPUS), (self._btn_book, MODE_BOOK)):
      self._set_mode_btn_active(btn, mode == m)
    self._set_improve_submode_ui(self._improve_submode)
    self._refresh_book_btn()
    self._refresh_follow_footer()
    if self._current_lesson and mode == MODE_CORPUS:
      self._source_lbl.setCursor(Qt.ArrowCursor)
      self._update_source_label(self._current_lesson[1])
    elif mode == MODE_BOOK and self._book_meta:
      self._update_book_footer()
    else:
      self._source_lbl.clear()
      self._source_lbl.setVisible(True)
      self._source_lbl.setCursor(Qt.ArrowCursor)
    if load:
      self._load_for_mode(mode)

  def _set_improve_footer_busy(self, busy):
    self._weakspot_generating = busy
    if busy and self._mode == MODE_IMPROVE:
      self._btn_improve.setText(_GENERATING_BTN_LABEL)
      self._btn_improve.setEnabled(False)
    else:
      self._btn_improve.setText(_IMPROVE_BTN_LABEL)
      self._btn_improve.setEnabled(True)

  def _on_weakspot_busy(self, busy):
    self._set_improve_footer_busy(busy)

  def _on_weakspot_lesson(self, lesson):
    if self._mode != MODE_IMPROVE:
      return
    if not lesson:
      self._show_idle_placeholder(IMPROVE_EMPTY_LABEL)
      return
    self._set_improve_footer_busy(False)
    self.needWeakspotLesson.emit(lesson)

  def _on_lesson_ready(self, match_text):
    self._load_word_baselines(match_text)
    if self._awaiting_next and self._doc.is_ready():
      self._clear_awaiting()
      self.updateLabel()

  def _load_word_baselines(self, match_text):
    words = lesson_words(match_text)
    self._doc.set_word_baselines(fetch_word_perfect_baselines(self.DB, words))
    self._doc.set_word_prior_sources(fetch_word_book_sources(self.DB, words))

  def _clear_awaiting(self):
    self._awaiting_next = False
    self._pending_action = None
    self._pending_now = None
    self._pending_review_words = None
    self._typer.set_awaiting_enter(None)

  def _show_progress_summary(self, run, stats_saved=True):
    baselines = self._doc._word_baselines
    match_text = self._doc._match_text
    # Improve modes (normal + focus drills) never gather counted word samples, so they
    # cannot mint "new common words" for the analysis pool — hide that feedback entirely.
    show_new_common = self._mode != MODE_IMPROVE
    min_books = analysis_min_count(STAT_TYPE_WORD, Settings.get('analysis_count'))
    srcid = None
    if self._current_lesson is not None:
      srcid = self._current_lesson[1]
    progress = analyze_run_progress(
      run, baselines, match_text,
      prior_sources=self._doc._word_prior_sources, run_source_id=srcid,
      min_books=min_books, include_new_common=show_new_common)
    if show_new_common:
      self._doc.apply_new_word_styles(run, progress.new_words)
    self._doc.apply_improved_word_styles(run, baselines)
    self._doc.set_progress_badges(progress_badges_for_run(run, baselines, match_text))
    self._awaiting_next = True
    self._typer.set_awaiting_enter(self._continue_lesson)
    msg = format_progress_html(progress, stats_saved=stats_saved)
    banner = follow_outcome_html(self._follow_race_outcome)
    if banner:
      msg = banner + '<br />' + msg
    self.updateLabel(msg)

  def _continue_lesson(self):
    action = self._pending_action
    now = self._pending_now
    review_words = self._pending_review_words
    self._clear_awaiting()
    self.updateLabel()
    if action == 'focus_repeat':
      if self._focus_drill and self._focus_drill_from_pa:
        if not self._emit_focus_lesson(self._focus_drill):
          self.updateLabel('Could not rebuild focus drill for those targets.')
      elif self._focus_drill:
        # New random 5 from the bottom 20 (or smaller pool) each finish.
        self._load_improve_lesson()
      else:
        self.setText(self._current_lesson)
      return
    if action == 'book_chunk' and self._mode == MODE_BOOK and self._book_meta is not None:
      m = self._book_meta
      srcid = self._current_lesson[1]
      if self._doc.advance_book_chunk():
        m = dict(m, chunk_index=m['chunk_index'] + 1)
        self._book_meta = m
        active = m['chunks'][m['chunk_index']]
        tid = lesson_text_id(srcid, m['chapter_index'], m['chunk_index'])
        self._current_lesson = (tid, srcid, active)
        self._update_book_footer(m)
        self._activate_loaded_lesson(len(active), center=True, focus=False)
      return
    if action == 'book_next':
      self._book.request_lesson(advance_chapter=False)
    elif action == 'improve_next':
      self._weakspot.invalidate_cache()
      self._load_improve_lesson()
    elif action == 'review' and review_words:
      review_words.sort(key=lambda x: (x[4], x[0]), reverse=True)
      u = sum(x[4] != 0 for x in review_words)
      u += (len(review_words) - u) // 4
      self.wantReview.emit([x[6] for x in review_words[:u]])
    elif action == 'normal_next':
      self.wantText.emit()

  def updateLabel(self, msg=None):
    text = []
    if msg is not None:
      text.append('<big><b>' + msg + '</b></big>')
    if self._awaiting_next:
      text.append("Press ENTER to start the next exercise.")
    self._label.setText('<br />'.join(text) if text else '')
    if text:
      self._show_result_label()

  def _insert_statistic_rows(self, rows):
    """Write statistic rows and refresh heatmap/listeners. Returns True if any rows written."""
    if not rows:
      return False
    self.DB.executemany_('''
    insert into statistic
    (time,viscosity,w,count,mistakes,type,data,source)
    values (?,?,?,?,?,?,?,?)
    ''', rows)
    self.DB.commit()
    self.statsChanged.emit()
    self._refreshHeatmap()
    return True

  def _should_write_lesson_stats(self, srcid):
    is_lesson = self.DB.fetchone("select discount from source where rowid=?", (None,), (srcid, ))[0]
    write_stats = self._mode not in (MODE_IMPROVE,) and (not is_lesson or self._settings.get('use_lesson_stats'))
    return is_lesson, write_stats

  def _pending_after_book_chunk(self, srcid, now, fallback_action):
    """Persist book place and set _pending_action. Returns True if mid-chapter chunk remains."""
    if self._mode == MODE_BOOK and self._book_meta is not None:
      m = self._book_meta
      # Always persist place on every finished chunk (not only chapter ends).
      self._book.on_chunk_completed(srcid, m['chapter_index'], m['chunk_index'], now)
      if self._doc.has_next_book_chunk():
        self._pending_action = 'book_chunk'
        return True
      self._pending_action = 'book_next'
      return False
    self._pending_action = fallback_action
    return False

  def typingFailed(self, txt):
    self.updateLabel(txt)

  def typingFollowLost(self, run):
    """Follow caret reached the end before the typist finished."""
    self._pause_overlay.hide()
    self._stop_follow_race(clear_caret=False)
    self._follow_race_outcome = 'failure'
    self._show_result_label()
    self._typer.updateStatus()

    if self._current_lesson is None:
      log.error("follow lost with no lesson started?")
      return

    now = time()
    med_char = run.median_timing
    stats_saved = False
    textid, srcid, _ = self._current_lesson
    if med_char:
      vals = collect_run_stat_rows(run, med_char, now, srcid)
      _is_lesson, write_stats = self._should_write_lesson_stats(srcid)
      if write_stats and vals:
        stats_saved = self._insert_statistic_rows(vals)

    # Book place still advances on follow failure (same as a finished chunk).
    self._pending_after_book_chunk(srcid, now, 'normal_next')
    self._pending_now = now
    self._pending_review_words = None
    self._show_progress_summary(run, stats_saved=stats_saved)

  def typingDone(self, run):
    self._stop_follow_race(clear_caret=False)
    if self._follow_is_active() and self._follow_race_outcome is None:
      self._follow_race_outcome = 'success'
    self._show_result_label()

    # Various sanity tests.
    if self._current_lesson is None:
      log.error("typing done with no lesson started?")
      return

    med_char = run.median_timing

    if run.per_sec is None or run.visc is None or not med_char:
      return self.typingFailed("Invalid run? (no stats found)")
    if run.per_sec < 1e-6:
      log.error("run seems to be ~0.0 duration: %s", run)
      return self.typingFailed("Invalid run? (~0 duration)")

    if self._focus_drill:
      now = time()
      ws_src = self.DB.getSource('<Weakspot>', lesson=1)
      drill_rows = collect_focus_drill_stat_rows(run, med_char, now, self._focus_drill)
      if drill_rows:
        rows = [(t, vis, w, c, m, tp, data, ws_src) for t, vis, w, c, m, tp, data in drill_rows]
        self._insert_statistic_rows(rows)
      self._pending_action = 'focus_repeat'
      self._show_progress_summary(run, stats_saved=bool(drill_rows))
      return

    now = time()
    textid, srcid, _ = self._current_lesson
    _, visc, acc = run.result(accuracy=True)
    duration = run.active_duration()
    wpm = (len(run) / duration * 12.0) if duration else 0.0

    self.DB.execute('''
    insert into result
    (w, text_id, source, wpm, accuracy, viscosity, char_count, duration)
    values (?,?,?, ?,?,?,?,?)
    ''', (now, textid, srcid,
          wpm, acc, visc, len(run), duration))

    self.DB.commit()
    # type (0: char, 1: trigram, 2: word)

    vals = collect_run_stat_rows(run, med_char, now, srcid)

    is_lesson, write_stats = self._should_write_lesson_stats(srcid)

    if self._mode == MODE_IMPROVE:
      ws_src = self.DB.getSource('<Weakspot>', lesson=1)
      # Keep real count/mistakes so drills raise perfect rate; discounted source
      # still blocks inventing new known words (corpus floor only).
      drill_vals = [(t, vis, w, c, m, tp, data, ws_src) for t, vis, w, c, m, tp, data, _s in vals]
      self.DB.executemany_('''
      insert into statistic
      (time,viscosity,w,count,mistakes,type,data,source)
      values (?,?,?,?,?,?,?,?)
      ''', drill_vals)
    elif write_stats:
      self.DB.executemany_('''
      insert into statistic
      (time,viscosity,w,count,mistakes,type,data,source)
      values (?,?,?,?,?,?,?,?)
      ''', vals)

      mistakes = Counter((c.char, e) for c in run if c.mistakes > 0 for e in c.errors)
      self.DB.executemany_('''
      insert into mistake
      (w,target,mistake,count)
      values (?,?,?,?)
      ''', [(now, k[0], k[1], v) for k, v in mistakes.items()])

    self.DB.commit()
    self.statsChanged.emit()
    self._refreshHeatmap()

    review_words = [x for x in vals if x[5] == 2] if not is_lesson else []
    action = lesson_completion_action(
      self._mode, bool(is_lesson), self._settings.get('auto_review'), bool(review_words),
      focus_drill=bool(self._focus_drill))

    self._pending_now = now
    self._pending_review_words = review_words if action == 'review' else None

    if self._pending_after_book_chunk(srcid, now, action):
      self._show_progress_summary(run, stats_saved=True)
      return

    self._show_progress_summary(run, stats_saved=True)

