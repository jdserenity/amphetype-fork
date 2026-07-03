


from itertools import *
import random
import time
import codecs
from typing_program.Data import DB

try:
  import editdistance
except ImportError:
  from typing_program.fake_imports import editdistance

import typing_program.Text as Text
from typing_program.Config import *
from typing_program.QtUtil import *


class StringListWidget(QTextEdit):
  updated = pyqtSignal()
  
  def __init__(self, *args):
    super(StringListWidget, self).__init__(*args)
    self.setWordWrapMode(QTextOption.WordWrap)
    self.setAcceptRichText(False)
    self.delayflag = 0
    self.textChanged.connect(self.onTextChanged)

  def addList(self, lst):
    self.append(' '.join(lst))

  def getList(self):
    return str(self.toPlainText()).split()

  def addFromTyped(self):
    words = [x[0] for x in DB.fetchall('select distinct data from statistic where type = 2 order by random()')]
    self.filterWords(words)

  def addFromFile(self):
    if getattr(self, '_filedialog', None):
      self._filedialog.show()
      return

    qf = QFileDialog(self, "Select Word File", directory=str(Settings.DATA_DIR / 'wordlists'))
    qf.setNameFilters(["All files (*)"])
    qf.setFileMode(QFileDialog.ExistingFile)
    qf.setAcceptMode(QFileDialog.AcceptOpen)
    qf.fileSelected['QString'].connect(self.reallyAddFromFile)
    qf.show()
    self._filedialog = qf

  def reallyAddFromFile(self, fname):
    self._filedialog.close()
    if fname == '':
      return
    try:
      with open(fname, "r", encoding="utf-8-sig") as f:
        words = f.read().split()
    except Exception as e:
      QMessageBox.warning(self, f"Couldn't read file: {fname}", str(e))
      return
    random.shuffle(words)
    self.filterWords(words)

  def filterWords(self, words):
    n = Settings.get('str_extra')
    w = Settings.get('str_what')
    if w == 'r': # random
      pass
    else:
      control = self.getList()
      if len(control) == 0:
        return

      for word in words:
        pass
      if w == 'e': # encompassing
        words = (word for word in words if any(c in word for c in control))
      else: # similar
        words = filter(
          lambda word: min(editdistance.eval(word,c) / max(len(word), len(c), 1) for c in control) < .26,
          words)

    if Settings.get('str_clear') == 'r': # replace = clear
      self.clear()

    self.addList(islice(words, n))

  def onTextChanged(self):
    if self.delayflag > 0:
      self.delayflag += 1
      return

    self.updated.emit()
    self.delayflag = 1
    QTimer.singleShot(500, self.revertFlag)

  def revertFlag(self):
    if self.delayflag > 1:
      self.updated.emit()
    self.delayflag = 0

class LessonGenerator(QWidget):
  newLessons = pyqtSignal([str, 'PyQt_PyObject', int])
  newReview = pyqtSignal(str)
  
  def __init__(self, *args):
    super(LessonGenerator, self).__init__(*args)

    self.strings = StringListWidget()
    self.sample = QTextEdit()
    self.sample.setWordWrapMode(QTextOption.WordWrap)
    self.sample.setAcceptRichText(False)
    self.les_name = QLineEdit()

    self.setLayout(AppBoxLayout([
      ["Welcome to the Typing Program automatic lesson generator!"],
      ["You can retrieve a list of words/keys/trigrams to practice from the Analysis tab, import from an external file, or even type in your own (separated by space).\n"],
      10,
      ["In generating lessons, I will make", SettingsEdit("gen_copies"),
        "copies the list below and divide them into sublists of size",
        SettingsEdit("gen_take"), "(0 for all).", None],
      ["I will then", SettingsCombo("gen_mix", [('c',"concatenate"), ('m',"commingle")]),
        "corresponding sublists into atomic building blocks which are fashioned into lessons according to your lesson size preferences.",  None],
      [
        ([
          (self.strings, 1),
          [SettingsCombo('str_clear', [('s', "Supplement"), ('r', "Replace")]), "list with",
            SettingsEdit("str_extra"),
            SettingsCombo('str_what', [('e','encompassing'), ('s','similar'), ('r','random')]),
            "words from", AppButton("a file", self.strings.addFromFile),
            "or", AppButton("analysis database", self.strings.addFromTyped), None]
        ], 1),
        ([
          "Lessons (separated by empty lines):",
          (self.sample, 1),
          [None, AppButton("Add to Sources", self.acceptLessons), "with name", self.les_name]
        ], 1)
      ]
    ]))

    Settings.signal_for("gen_take").connect(self.generatePreview)
    Settings.signal_for("gen_copies").connect(self.generatePreview)
    Settings.signal_for("gen_mix").connect(self.generatePreview)
    self.strings.updated.connect(self.generatePreview)


  def wantReview(self, words):
    sentences = self.generateLesson(words)
    self.newReview.emit(' '.join(sentences))

  def generatePreview(self):
    words = self.strings.getList()
    sentences = self.generateLesson(words)
    self.sample.clear()
    for x in Text.to_lessons(sentences):
      self.sample.append(x + "\n\n")

  def generateLesson(self, words):
    copies = Settings.get('gen_copies')
    take = Settings.get('gen_take') or len(words)
    mix = Settings.get('gen_mix')

    sentences = []
    while len(words) > 0:
      sen = words[:take] * copies
      words[:take] = []

      if mix == 'm': # mingle
        random.shuffle(sen)
      sentences.append(' '.join(sen))
    return sentences

  def acceptLessons(self, name=None):
    name = str(self.les_name.text())
    if len(name.strip()) == 0:
      name = "<Lesson %s>" % time.strftime("%y-%m-%d %H:%M")

    lessons = [_f for _f in [x.strip() for x in str(self.sample.toPlainText()).split("\n\n")] if _f]

    if len(lessons) == 0:
      QMessageBox.information(self, "No Lessons", "Generate some lessons before you try to add them!")
      return

    self.newLessons.emit(name, lessons, 1)

  def addStrings(self, *args):
    self.strings.addList(*args)

