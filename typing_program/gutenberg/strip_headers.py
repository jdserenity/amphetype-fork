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
