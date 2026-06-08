
from amphetype import *

from amphetype.QtUtil import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

import pickle
import getpass
import os
import re
from pathlib import Path
import logging as log

from amphetype.settings import FSettings


def get_default_db_name():
  "Default database name is based on username."

  try:
    _user = getpass.getuser() or 'user'
  except: # Docs just say "otherwise, an exception is raised."
    _user = 'user'

  _user = re.sub('[^a-z0-9_-]', '', _user, flags=re.I) or 'user'
  return _user + '.db'


class SettingsMeta(type(QObject)):
  def __new__(cls, name, bases, ns):
    for k,v in ns['defaults'].items():
      ns['change_' + k] = pyqtSignal([type(v)])
    return super().__new__(cls, name, bases, ns)


class AmphSettings(FSettings, metaclass=SettingsMeta):
  change = pyqtSignal()
  DATA_DIR = DATA_DIR

  # Whenever types need to be checked on settings it will use the
  # types provided here, so always set a default of the type the
  # setting will have.
  defaults = {
    "typer_font": str(QFont("Arial", 18).toString()),
    "qt_style": "", # Will be set in __init__().
    "qt_css": "<none>",

    "text_force_ascii": False,
    
    "history": 30.0,
    "min_chars": 220,
    "max_chars": 600,
    "break_sentences": False,
    "lesson_stats": 0, # show text/lesson in perf -- not used anymore
    "perf_group_by": 0,
    "perf_items": 100,
    "text_regex": r"",
    "db_name": '', # Will be set in __init__().
    "select_method": 0,
    "num_rand": 50,
    "graph_what": 3,
    "req_space": True,
    "show_last": True,
    "show_xaxis": False,
    "chrono_x": False,
    "dampen_graph": False,

    "minutes_in_sitting": 60.0,
    "dampen_average": 10,
    "def_group_by": 10,

    "use_lesson_stats": False,
    "auto_review": False,

    "min_wpm": 0.0,
    "min_acc": 0.0,
    "min_lesson_wpm": 0.0,
    "min_lesson_acc": 97.0,

    "group_month": 365.0,
    "group_week": 30.0,
    "group_day": 7.0,

    "ana_which": "wpm asc",
    "ana_what": 0,
    "ana_many": 30,
    "ana_count": 1,

    "gen_copies": 3,
    "gen_take": 2,
    "gen_mix": 'c',
    #"gen_stats": False,
    "str_clear": 's',
    "str_extra": 10,
    "str_what": 'e',

    "practice_mode": 0,  # 0 = normal, 1 = book, 2 = weakspot
    "book_source_id": 0,
    "book_max_chars": 12000,
    "read_ahead_enabled": False,
  }

  typer_defaults = {
    'lenient_mode': False,
    'require_space': False,
    'overwrite_mode': True,
    'limit_backspace': False,

    'show_progress': True,
    'read_ahead_level': 0,  # 0 = normal, 1 = hard, 2 = easy (when read_ahead_enabled)

    'para_margin': 40,
    'para_lineheight': 1.0,
    'background_color': QColor('white'),

    'speed_heatmap': False,
    'speed_heatmap_mode': 0,
  }

  typer_color_defaults = {
    'inactive_bg': QColor('white'),
    'inactive_fg': QColor('#888888'),
    'untyped_bg': QColor('#ffefdc'),
    'untyped_fg': QColor('#ffffff'),
    'correct_bg': QColor('#fff6eb'),
    'correct_fg': QColor('#e8e8e8'),

    'anyerror_bg': QColor('darksalmon'),
    'anyerror_fg': QColor('#ffffff'),
    'error_bg': QColor('firebrick'),
    'error_fg': QColor('white'),
  }

  def __init__(self, *args):
    if cli_options.settings:
      super().__init__(filename=cli_options.settings)
    elif cli_options.local:
      super().__init__(filename=str(DATA_DIR / 'amphetype.ini'))
    else:
      super().__init__(appname='amphetype')

    # Set some runtime defaults here.

    if cli_options.database:
      _dbname = cli_options.database
    elif cli_options.local:
      _dbname = str(DATA_DIR / get_default_db_name())
    else:
      pth = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
      if pth:
        pth = Path(pth)
        pth.mkdir(parents=True, exist_ok=True)
      else:
        pth = DATA_DIR
      _dbname = str(pth / get_default_db_name())
    
    self.defaults['db_name'] = _dbname

    assert QApplication.instance()
    self.defaults['qt_style'] = QApplication.instance().style().objectName().lower()

    typer_defs = dict(self.typer_defaults)
    typer_defs['background_color'] = QApplication.palette().color(QPalette.Window)
    self.typer_settings = self.makeSettings('typer', typer_defs)
    self.typer_colors = self.makeSettings('colors', self.typer_color_defaults)

  def get(self, k):
    return self.value(k, self.defaults[k], type=type(self.defaults[k]))

  def getFont(self, k):
    qf = QFont()
    qf.fromString(self.get(k))
    return qf

  def getColor(self, k):
    return QColor(self.get(k))

  def set(self, k, v):
    p = self.get(k)
    if p == v:
      return
    w = v
    if isinstance(v, QColor):
      w = v.name()
    elif isinstance(v, QFont):
      w = str(v)
    self.setValue(k, v)
    self.change.emit()
    self.signal_for(k).emit(v)

  def signal_for(self, k):
    return getattr(self, 'change_' + k)



class SettingsColor(AmphButton):
  def __init__(self, key, text):
    self.key_ = key
    super().__init__(f'{text} {Settings.get(key)}', self.pickColor)
    self.updateIcon()

  def pickColor(self):
    color = QColorDialog.getColor(Settings.getColor(self.key_), self)
    if not color.isValid():
      return
    Settings.set(self.key_, str(color.name()))
    self.updateIcon()

  def updateIcon(self):
    pix = QPixmap(64, 32)
    c = Settings.getColor(self.key_)
    pix.fill(c)
    self.setText(Settings.get(self.key_))
    self.setIcon(QIcon(pix))



# TODO: XXX. Perhaps input and format numbers in locale? Possible
# problems: innumerable. Many (I, for one) will probably want to input
# things as if in plain C locale and be annoyed if their Uruk-hai
# locale interferes/invalidates their input. Would be a misfeature
# until locale-switching is also in place.

# Unrelated: "I am writing a class to represent money, and one issue
# I've been running into is that "1.50" != str(1.50). str(1.50) equals
# 1.5, and all of a sudden, POOF. 45 cents have vanished and the
# amount is now 1 dollar and 5 cents." -StackOverflow user.

# LOCALE = QLocale()

# def float_to_string(val):
#   if round(val, 6) == int(val):
#     return LOCALE.toString(val, precision=1)
#   else:
#     return LOCALE.toString(val)

# def SettingsEdit(setting):
#   "Suitable QLineEdit() for given type and implied locale"
#   val = Settings.get(setting)
#   if isinstance(val, float):
#     pass
#   elif isinstance(val, int):
#     pass
#   else:
#     pass

# Set validators, QDoubleValidator, QIntValidator?

class SettingsEdit(AmphEdit):
  def __init__(self, setting):
    val = Settings.get(setting)
    self.setting = setting
    if isinstance(val, float):
      self.fmt = lambda x: str(round(x, 6))
      self.conv = float
    elif isinstance(val, int):
      self.fmt = str
      self.conv = int
    elif isinstance(val, str):
      self.fmt = lambda x: x
      self.conv = lambda x: x
    else:
      raise RuntimeError(f"instantiated with unknown type {type(val)}")

    super(SettingsEdit, self).__init__(self.fmt(val), self.updateVal)
    Settings.signal_for(setting).connect(lambda x: self.setText(self.fmt(x)))

  def updateVal(self):
    try:
      v = self.conv(self.text())
    except ValueError as err:
      QMessageBox.warning(self, "String Conversion Error", f"Couldn't convert setting value:\n{err}")
    else:
      Settings.set(self.setting, v)

class SettingsCombo(QComboBox):
  def __init__(self, setting, lst, *args):
    super(SettingsCombo, self).__init__(*args)

    prev = Settings.get(setting)
    self.idx2item = []
    for i in range(len(lst)):
      if isinstance(lst[i], str):
        # not a tuple, use index as key
        k, v = i, lst[i]
      else:
        k, v = lst[i]
      self.addItem(v)
      self.idx2item.append(k)
      if k == prev:
        self.setCurrentIndex(i)

    self.activated[int].connect(lambda x: Settings.set(setting, self.idx2item[x]))

    #self.connect(Settings, SIGNAL("change_" + setting),
    #      lambda x: self.setCurrentIndex(self.item2idx[x]))

class SettingsCheckBox(QCheckBox):
  def __init__(self, setting, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.setCheckState(Qt.Checked if Settings.get(setting) else Qt.Unchecked)
    self.stateChanged[int].connect(lambda x: Settings.set(setting, True if x == Qt.Checked else False))


def find_css_files():
  # XXX: cleanup / make consistent.
  places = [
    QStandardPaths.AppLocalDataLocation,
    QStandardPaths.AppDataLocation,
    QStandardPaths.AppConfigLocation,
    Settings.DATA_DIR / 'css',
  ]
  res = set()
  for p in places:
    if not isinstance(p, Path):
      pth = QStandardPaths.locate(p, 'css', QStandardPaths.LocateDirectory)
      if not pth:
        continue
      p = Path(pth)
    # print(f"scanning dir {p}")
    for f in list(p.glob('*.qss')) + list(p.glob('*.stylesheet')) + list(p.glob('*.css')):
      res.add(str(f))

  return set(res)
 


class SelectCSSBox(QComboBox):
  def __init__(self, *args):
    super().__init__(*args)

    Settings.signal_for('qt_css').connect(self.refresh)
    self.activated[int].connect(self.setIdx)
    self.refresh()

  def setIdx(self, idx):
    if idx == 0:
      Settings.set('qt_css', '<none>')
    elif idx <= len(self._files):
      Settings.set('qt_css', self._files[idx-1])
    else:
      # <select file>
      qf = QFileDialog(self, "Select CSS Theme")
      qf.setNameFilters(["QT CSS stylesheet (*.qss *.css *.stylesheet)", "All files (*)"])
      qf.setFileMode(QFileDialog.ExistingFile)
      qf.setAcceptMode(QFileDialog.AcceptOpen)
      qf.fileSelected['QString'].connect(self.setCustomCSS)
      qf.show()

  def setCustomCSS(self, fname):
    Settings.set('qt_css', fname)

  def refresh(self):
    cur = Settings.get('qt_css')
    _files = find_css_files()
    if cur not in _files and cur != '<none>':
      _files.add(cur)
    self._files = sorted(_files)
    
    self.clear()
    self.addItem('<none>')
    self.setCurrentIndex(0)
    for i,v in enumerate(self._files):
      self.addItem(v)
      if v == cur:
        self.setCurrentIndex(i+1)
    self.addItem('<select file...>')







from amphetype.layout import FBoxLayout

class TyperInputOptions(QGroupBox):
  def __init__(self, S, *args, **kwargs):
    super().__init__(*args, title='Input Mode', flat=False, **kwargs)
    self.setLayout(FBoxLayout([
      "Hover over these options for more information.",
      QCheckBox('Overwrite mode',
                checked=S['overwrite_mode'],
                toggled=S('overwrite_mode').set,
                toolTip="""In <b>overwrite mode</b> input will overwrite text in the buffer, no matter if correct or not. If turned off (insert mode) input will work more like real-world typing, but might be more distracting."""),
      QCheckBox("Lenient mode (NB! Read tooltip!)",
                checked=S['lenient_mode'], toggled=S('lenient_mode').set,
                toolTip="""In <b>lenient mode</b> past errors will not
                block further progress.
                This means you can complete texts without fully matching it.<br />


                Note that combining this with <b>overwrite mode</b> means you can
                skip text input without having to type any of the letters.
                (last letter of the entire text <i>must</i> be typed correctly though).
                For example the text might expect "this" but you type "tihd" and then continue as normal.
                In normal circumstances these mistyped "garbage" words will <b>NOT</b> be included in your statistics!
                This will <b>skew your statistics</b>, because errors normally have the biggest impact
                on typing speed.
                This means that less statistical data will be collected.<br />

                It's thus recommended to not combine this with <i>overwrite mode</i> unless you have a strong preference."""),
      QCheckBox('Wait for <SPACE> before start',
                checked=S['require_space'], toggled=S('require_space').set,
                toolTip="""Require user to press <i>spacebar</i> before accepting input. Note that turning this off means that the first letter, word, and trigraph of every lesson cannot be timed with 100% accuracy (a median will be used)."""),
      QCheckBox('Prevent backspacing over correct input',
                checked=S['limit_backspace'], toggled=S('limit_backspace').set,
                toolTip="""Turning this on will prevent backspace from going back over any correct input. Works best for overwrite mode."""),
      ]))

class TyperOptions(QWidget):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    S = Settings.typer_settings
    C = Settings.typer_colors
    self.setLayout(FBoxLayout([
      "These options apply to the inline typer (the default).",
      "Most options under <i>General Options</i> also affect it.",
      QCheckBox('Show progress bar while typing',
                checked=S['show_progress'], toggled=S('show_progress').set),
      ["Page background (behind lesson)", S('background_color').button(), None],
      ['Paragraph margin (px)', S('para_margin').spin_box(0, 100), None],
      ['Line spacing', S('para_lineheight').spin_box(0.6, 4.0, 0.05), None],
      TyperInputOptions(S),
      TyperColors(C),
      None,
    ]))

class TyperColors(QGroupBox):
  def __init__(self, S, *args, **kwargs):
    super().__init__(*args, title='Text Colors', flat=False, **kwargs)
    self.setLayout(FBoxLayout([
      [("Inactive surrounding text", 1),
       S('inactive_fg').button('Text'),
       S('inactive_bg').button('Background'),
       (None, 2)],
      [("Text to be typed", 1),
       S('untyped_fg').button('Text'),
       S('untyped_bg').button('Background'),
       (None, 2)],
      [("Correctly typed", 1),
       S('correct_fg').button('Text'),
       S('correct_bg').button('Background'),
       (None, 2)],
      [("Errors", 1),
       S('error_fg').button('Text'),
       S('error_bg').button('Background'),
       (None, 2)],
      [("Blocking errors (non-lenient)", 1),
       S('anyerror_fg').button('Text'),
       S('anyerror_bg').button('Background'),
       (None, 2)],
      ]))



class GeneralOptions(QWidget):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

    self.font_lbl = QLabel()
    self.style_box = SettingsCombo('qt_style', [(x.lower(), x.lower()) for x in QStyleFactory.keys()])

    self.setLayout(AmphBoxLayout([
      ["Typer font is", self.font_lbl, AmphButton("Change...", self.setFont), None],
      None,
      [SettingsCheckBox("text_force_ascii", 'Force unicode to plain ASCII'), ('(‘fancy’ “quotes” → "normal" quotes, <code>æ</code> → <code>ae</code>, etc.)', 1)],
      SettingsCheckBox('auto_review', "Automatically review slow and mistyped words after texts."),
      SettingsCheckBox('show_last', "Show last result(s) above text in the Typer."),
      SettingsCheckBox('use_lesson_stats', "Save key/trigram/word statistics from generated lessons."),
      SettingsCheckBox('req_space', "Make SPACE mandatory before each session",
                        toolTip="""This is generally recommended because otherwise the timing of the very first character has to be inferred artificially (a median is used)."""),
      None,
      ["Data is considered too old to be included in analysis after",
        SettingsEdit("history"), "days.", None],
      ["Try to limit texts and lessons to between", SettingsEdit("min_chars"),
        "and", SettingsEdit("max_chars"), "characters.", None],
      [SettingsCheckBox('break_sentences', "Break long sentences when importing external text."), None],
      ["Selection method for new lessons:",
        SettingsCombo('select_method', ['Random', 'In Order', 'Difficult', 'Easy']), None],
      "(In order selects the next text after the one you completed last. Easy/difficult estimates your WPM for a random sample and picks the fastest/slowest.)\n",
      ["When selecting easy/difficult texts, pick the best from a sample of",
        SettingsEdit('num_rand'), "texts.", None],
      ["When grouping by sitting on the Performance Analysis tab, consider results more than",
        SettingsEdit('minutes_in_sitting'), "minutes away to be part of a different sitting.", None],
      ["Group by", SettingsEdit('def_group_by'), "results when displaying last scores and showing last results on the Typer tab.", None],
      ["When smoothing out the graph, display a running average of", SettingsEdit('dampen_average'), "values", None],
      None,
      ["QT5 style is", self.style_box, 'and CSS theme is', SelectCSSBox(), None],
    ]))

    self.updateFont()

  def setFont(self):
    font, ok = QFontDialog.getFont(Settings.getFont('typer_font'), self)
    Settings.set("typer_font", str(font.toString()))
    self.updateFont()

  def updateFont(self):
    self.font_lbl.setText(Settings.get("typer_font"))
    qf = Settings.getFont('typer_font')
    self.font_lbl.setFont(qf)


# TODO: remove this
Settings = AmphSettings()

