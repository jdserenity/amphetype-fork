"""Split a novel .txt into lesson-sized chunks (no Qt)."""

import codecs
import random
import re

# Defaults match Config.AppSettings (GUI import uses those settings live).
DEFAULT_MIN_CHARS = 220
DEFAULT_MAX_CHARS = 600
DEFAULT_BREAK_SENTENCES = False

abbreviations = set(map(str, [
  'jr', 'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', "sen", "rep", "sens", "reps", 'gov', "attys", "atty", 'supt',
  'det', 'rev', 'col', 'gen', 'lt', 'cmdr', 'adm', 'capt', 'sgt', 'cpl', 'maj',
  'dept', 'univ', 'assn', 'bros', 'inc', 'ltd', 'co', 'corp',
  'arc', 'al', 'ave', "blvd", "bld", 'cl', 'ct', 'cres', 'dr', "expy", "exp", 'dist', 'mt', 'ft',
  "fwy", "fy", "hway", "hwy", 'la', "pde", "pd", 'pl', 'plz', 'rd', 'st', 'tce',
  'Ala', 'Ariz', 'Ark', 'Cal', 'Calif', 'Col', 'Colo', 'Conn',
  'Del', 'Fed', 'Fla', 'Ga', 'Ida', 'Id', 'Ill', 'Ind', 'Ia',
  'Kan', 'Kans', 'Ken', 'Ky', 'La', 'Me', 'Md', 'Is', 'Mass',
  'Mich', 'Minn', 'Miss', 'Mo', 'Mont', 'Neb', 'Nebr', 'Nev',
  'Mex', 'Okla', 'Ok', 'Ore', 'Penna', 'Penn', 'Pa', 'Dak',
  'Tenn', 'Tex', 'Ut', 'Vt', 'Va', 'Wash', 'Wis', 'Wisc', "Wy",
  'Wyo', 'USAFA', 'Alta', 'Man', 'Ont', 'Qué', 'Sask', 'Yuk',
  'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec', 'sept',
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
  return min((a, b), key=lambda x: abs(x - idx))


def split_sentence(s, sweet_spot):
  """Generator that break sentence `s` into pieces (on spaces and linebreaks) that
  are around `sweet_spot` in length.
  """
  while len(s) > sweet_spot:
    idx = find_relative(s.replace('\n', ' '), ' ', sweet_spot)
    if idx == -1:
      break
    yield s[:idx]
    s = s[idx + 1:]
  if s:
    yield s


def to_lessons(sentences, min_chars=DEFAULT_MIN_CHARS, max_chars=DEFAULT_MAX_CHARS):
  backlog = []
  backlen = 0
  min_chars = max(min_chars, 1)
  max_chars = min(max_chars, 99999)
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


def para_split(f):
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


def pop_format(lst):
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


def mine_lessons_from_paras(paras, min_chars=DEFAULT_MIN_CHARS, max_chars=DEFAULT_MAX_CHARS,
                            break_sentences=DEFAULT_BREAK_SENTENCES, progress=None):
  lessons = []
  backlog = []
  backlen = 0
  n = len(paras) or 1
  for i, p in enumerate(paras):
    if len(backlog) > 0:
      backlog.append(None)
    parts = to_lessons(iter(p), min_chars=min_chars, max_chars=max_chars) if break_sentences else p
    for s in parts:
      backlog.append(s)
      backlen += len(s)
      if backlen >= min_chars:
        lessons.append(pop_format(backlog))
        backlen = 0
    if progress is not None:
      progress(int(100 * (i + 1) / n))
  if backlen > 0:
    lessons.append(pop_format(backlog))
  return lessons


def mine_lessons_from_file(fname, min_chars=DEFAULT_MIN_CHARS, max_chars=DEFAULT_MAX_CHARS,
                           break_sentences=DEFAULT_BREAK_SENTENCES, progress=None):
  with codecs.open(fname, "r", "utf_8_sig") as f:
    paras = para_split(f)
  return mine_lessons_from_paras(
    paras, min_chars=min_chars, max_chars=max_chars,
    break_sentences=break_sentences, progress=progress)


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
      self.lessons.append(' '.join(lesson))

  def __iter__(self):
    return iter(self.lessons)
