from typing_program.Config import Settings
from PyQt5.QtCore import *

from typing_program.lesson_miner import (  # noqa: F401 — re-exports for callers
  LessonGeneratorPlain,
  SentenceSplitter,
  abbreviations,
  find_relative,
  mine_lessons_from_file,
  mine_lessons_from_paras,
  para_split,
  pop_format,
  split_sentence,
  to_lessons,
)


class LessonMiner(QObject):

  progress = pyqtSignal(int)

  def __init__(self, fname):
    super(LessonMiner, self).__init__()
    self._fname = fname
    self.lessons = None
    self.min_chars = Settings.get('min_chars')
    self.max_chars = Settings.get('max_chars')
    self._break_sentences = Settings.get('break_sentences')
    with open(fname, 'r', encoding='utf_8_sig') as f:
      self.paras = para_split(f)

  def doIt(self):
    self.lessons = mine_lessons_from_paras(
      self.paras,
      min_chars=self.min_chars,
      max_chars=self.max_chars,
      break_sentences=self._break_sentences,
      progress=lambda p: self.progress[int].emit(p),
    )

  def popFormat(self, lst):
    return pop_format(lst)

  def __iter__(self):
    if self.lessons is None:
      self.doIt()
    return iter(self.lessons)

  def para_split(self, f):
    return para_split(f)


if __name__ == '__main__':
  import sys
  for x in LessonMiner(sys.argv[1]):
    print("--%s--" % x)
