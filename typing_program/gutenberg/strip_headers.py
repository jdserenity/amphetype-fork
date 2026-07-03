import re

# Boilerplate removal adapted from c-w/Gutenberg (strip_headers.py).

TEXT_START_MARKERS = (
  "*** START OF THE PROJECT GUTENBERG",
  "*** START OF THIS PROJECT GUTENBERG",
  "*END*THE SMALL PRINT",
  "This etext was prepared by",
  "E-text prepared by",
  "Produced by",
  "Distributed Proofreading Team",
)

TEXT_END_MARKERS = (
  "*** END OF THE PROJECT GUTENBERG",
  "*** END OF THIS PROJECT GUTENBERG",
)

LEGALESE_START_MARKERS = (
  "ONE SMALL PRINT",
  "SMALL PRINT!",
  "SMALL PRINT",
)

LEGALESE_END_MARKERS = (
  "SMALL PRINT!",
)


def strip_headers(text):
  lines = text.splitlines()
  out = []
  i = 0
  content_started = False
  ignore_section = False

  for line in lines:
    reset = False
    if i <= 600:
      if any(line.startswith(token) for token in TEXT_START_MARKERS):
        reset = True
      if reset:
        out = []
        content_started = True
        continue

    if content_started and (i >= 100 or len(out) >= 1):
      if any(line.startswith(token) for token in TEXT_END_MARKERS):
        break

    if any(line.startswith(token) for token in LEGALESE_START_MARKERS):
      ignore_section = True
      continue
    if any(line.startswith(token) for token in LEGALESE_END_MARKERS):
      ignore_section = False
      continue

    if not ignore_section:
      out.append(line.rstrip())
      i += 1

  return '\n'.join(out).strip() + '\n' if out else ''


_AUS_BODY_RE = re.compile(
  r'^(PART\b|Chapter\s+(?:\d+|[IVXLC]+)\b|BOOK\s+(ONE|TWO|THREE|\d+|[IVXLC]+)\b|'
  r'PROLOGUE\b|INTRODUCTION\b|PREFACE\b|LETTER\s+(?:\d+|[IVXLC]+)\b)',
  re.I,
)
_AUS_META_RE = re.compile(
  r'^(Title:|Author:|eBook No\.|Language:|Date |\* A Project Gutenberg)',
  re.I,
)
_AUS_FOOTER_RE = re.compile(r'^Project Gutenberg (of )?Australia', re.I)


def _aus_has_us_markers(text):
  return any(m in text for m in TEXT_START_MARKERS[:3])


def _aus_body_start(lines):
  for i, line in enumerate(lines):
    s = line.strip()
    if s and _AUS_BODY_RE.match(s):
      return i
  past_contact = False
  for i, line in enumerate(lines):
    s = line.strip()
    if not s:
      continue
    if 'gutenberg.net.au' in s.lower() and 'licence' not in s.lower():
      past_contact = True
      continue
    if not past_contact or _AUS_META_RE.match(s):
      continue
    return i
  return None


def _trim_aus_footer(lines):
  end = len(lines)
  for i in range(len(lines) - 1, -1, -1):
    s = lines[i].strip()
    if not s:
      end = i
      continue
    if _AUS_FOOTER_RE.match(s):
      end = i
      continue
    break
  return lines[:end]


def strip_aus_headers(text):
  if _aus_has_us_markers(text):
    cleaned = strip_headers(text)
    if cleaned.strip():
      return cleaned
  lines = text.splitlines()
  start = _aus_body_start(lines)
  if start is None:
    return text.strip() + '\n' if text.strip() else ''
  body = _trim_aus_footer(lines[start:])
  return '\n'.join(body).strip() + '\n'
