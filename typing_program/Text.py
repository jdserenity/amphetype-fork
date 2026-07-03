if __name__ == '__main__':
  import typing_program.mainwindow

import re
import codecs
import random
import textwrap
from typing_program.Config import Settings
from itertools import *
from PyQt5.QtCore import *

abbreviations = set(map(str, [
'jr', 'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', "sen","rep","sens", "reps",'gov', "attys", "atty", 'supt',
'det', 'rev', 'col','gen', 'lt', 'cmdr', 'adm', 'capt', 'sgt', 'cpl', 'maj',
'dept', 'univ', 'assn', 'bros', 'inc', 'ltd', 'co', 'corp',
'arc', 'al', 'ave', "blvd", "bld",'cl', 'ct', 'cres', 'dr', "expy", "exp", 'dist', 'mt', 'ft',
"fwy", "fy",  "hway", "hwy",'la', "pde", "pd", 'pl', 'plz', 'rd', 'st', 'tce',
'Ala' , 'Ariz', 'Ark', 'Cal', 'Calif', 'Col', 'Colo', 'Conn',
'Del', 'Fed' , 'Fla', 'Ga', 'Ida', 'Id', 'Ill', 'Ind', 'Ia',
'Kan', 'Kans', 'Ken', 'Ky' , 'La', 'Me', 'Md', 'Is', 'Mass',
'Mich', 'Minn', 'Miss', 'Mo', 'Mont', 'Neb', 'Nebr' , 'Nev',
'Mex', 'Okla', 'Ok', 'Ore', 'Penna', 'Penn', 'Pa'  , 'Dak',
'Tenn', 'Tex', 'Ut', 'Vt', 'Va', 'Wash', 'Wis', 'Wisc', "Wy",
'Wyo', 'USAFA', 'Alta' , 'Man', 'Ont', 'Qué', 'Sask', 'Yuk',
'jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec','sept',
'vs', 'etc', 'no', 'esp', 'eg', 'ie', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12',
'avg', 'viz', 'm', 'mme']))

class SentenceSplitter(object):
  sen = re.compile(r"""(?:(?: |^)[^\w. ]*(?P<pre>\w+)[^ .]*\.+|[?!]+)['"]?(?= +(?:[^ a-z]|$))|$""")

  def __init__(self, text):
    self.string = text

  def __iter__(self):
    p = [0]
    return filter(None, map(lambda x: self.pars(p, x), self.sen.finditer(self.string)))

  def pars(self, p, mat):
    if mat.group('pre') and self.isAbbreviation(mat.group('pre')):
      return None
    p.append(mat.end())
    return self.string[p[-2]:p[-1]].strip()

  def isAbbreviation(self, s):
    ls = s.lower()
    return ls in abbreviations or s in abbreviations


class LessonMiner(QObject):
  
  progress = pyqtSignal(int)
  
  def __init__(self, fname):
    super(LessonMiner, self).__init__()
    #print time.clock()
    with codecs.open(fname, "r", "utf_8_sig") as f:
      self.paras = self.para_split(f)
    self.lessons = None
    self.min_chars = Settings.get('min_chars')
    self._break_sentences = Settings.get('break_sentences')

  def doIt(self):
    self.lessons = []
    backlog = []
    backlen = 0
    i = 0
    for p in self.paras:
      if len(backlog) > 0:
        backlog.append(None)
      for s in to_lessons(iter(p)) if self._break_sentences else p:
        backlog.append(s)
        backlen += len(s)
        if backlen >= self.min_chars:
          self.lessons.append(self.popFormat(backlog))
          backlen = 0
      i += 1
      self.progress[int].emit(int(100 * i/len(self.paras)))
    if backlen > 0:
      self.lessons.append(self.popFormat(backlog))

  def popFormat(self, lst):
    ret = []
    p = []
    while len(lst) > 0:
      s = lst.pop(0)
      if s is not None:
        p.append(s)
      else:
        ret.append(' '.join(p))
        p = []
    if len(p) > 0:
      ret.append(' '.join(p))
    return '\n'.join(ret)

  def __iter__(self):
    if self.lessons is None:
      self.doIt()
    return iter(self.lessons)

  def para_split(self, f):
    p = []
    ps = []
    for l in f:
      l = l.strip()
      if l != '':
        p.append(l)
      elif len(p) > 0:
        ps.append(SentenceSplitter(" ".join(p)))
        p = []
    if len(p) > 0:
      ps.append(SentenceSplitter(" ".join(p)))
    return ps


def find_relative(s, c, idx):
  """Given a string `s` and a char/substring `c`, find a location of `c` that is
  as close as possible to `idx`.

  Returns -1 if no `c` is found in `s`.

  """
  a, b = s.find(' ', idx), s.rfind(' ', idx)
  if a == -1:
    return b
  if b == -1:
    return a
  return min((a, b), key=lambda x: abs(x-idx))


def split_sentence(s, sweet_spot):
  """Generator that break sentence `s` into pieces (on spaces and linebreaks) that
  are around `sweet_spot` in length.

  """
  while len(s) > sweet_spot:
    idx = find_relative(s.replace('\n', ' '), ' ', sweet_spot)
    if idx == -1:
      break
    yield s[:idx]
    s = s[idx+1:]
  if s:
    yield s

def to_lessons(sentences):
  backlog = []
  backlen = 0
  # Sanity/robustness.
  min_chars = max(Settings.get('min_chars'), 1)
  max_chars = min(Settings.get('max_chars'), 99999)
  if min_chars > max_chars:
    min_chars, max_chars = max_chars, min_chars

  # This is a little arbitrary, and just aesthetics, but if a sentence is so
  # long that its ratio to the "total range" exceeds the golden ratio, then it
  # will be broken up. Otherwise we prefer to leave sentences alone and treat
  # them as atomic units.
  sweet_spot = min_chars + int((max_chars - min_chars) / 1.618033988749895)

  for s in sentences:
    for part in split_sentence(s, sweet_spot):
      backlog.append(part)
      backlen += len(part)
      if backlen >= min_chars:
        yield ' '.join(backlog) # XXX: French 2-space etc.?
        backlog = []
        backlen = 0
  if backlen > 0:
    yield ' '.join(backlog) # XXX: French 2-space etc.?



class LessonGeneratorPlain(object):
  def __init__(self, words, per_lesson=12, repeats=4):
    while (0 < len(words) % per_lesson < per_lesson / 2):
      per_lesson += 1

    self.lessons = []
    wcopy = words[:]
    while wcopy:
      lesson = wcopy[0:per_lesson] * repeats
      wcopy[0:per_lesson] = []
      random.shuffle(lesson)
      self.lessons.append( #textwrap.fill(
                        ' '.join(lesson)) #, width))

  def __iter__(self):
    return iter(self.lessons)





if __name__ == '__main__':
  import sys
  for x in LessonMiner(sys.argv[1]):
    print("--%s--" % x)




