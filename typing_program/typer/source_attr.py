from typing_program.book_mode import MODE_BOOK, MODE_IMPROVE

def lesson_completion_action(mode, is_lesson, auto_review, has_review_words, focus_drill=False):
  """What to do after a typing session ends."""
  if focus_drill:
    return 'focus_repeat'
  if mode == MODE_BOOK:
    return 'book_next'
  if mode == MODE_IMPROVE:
    return 'improve_next'
  if not is_lesson and auto_review and has_review_words:
    return 'review'
  return 'normal_next'


_SOURCE_FILE_EXTS = ('.txt', '.text', '.md', '.markdown', '.epub', '.html', '.htm', '.rtf', '.pdf')

def _display_source_name(source_name):
  name = source_name.strip()
  lower = name.lower()
  for ext in _SOURCE_FILE_EXTS:
    if lower.endswith(ext):
      return name[: -len(ext)].rstrip()
  return name

def format_source_attribution(source_name):
  """Footer line for novel sources, e.g. '— Pride and Prejudice'. Empty for system sources."""
  if not source_name:
    return ''
  name = _display_source_name(source_name)
  if not name or (name.startswith('<') and name.endswith('>')):
    return ''
  return f'— {name}'
