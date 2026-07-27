"""Normalize typographic quotes/apostrophes to plain keyboard ' and "."""

# Curly / typographic singles → '
# Curly / typographic doubles → "
_QUOTE_MAP = str.maketrans({
  '\u2018': "'",  # ‘ left single
  '\u2019': "'",  # ’ right single / apostrophe
  '\u201A': "'",  # ‚ low-9 single
  '\u201B': "'",  # ‛ high-reversed-9 single
  '\u2032': "'",  # ′ prime (often used as apostrophe)
  '\u02BC': "'",  # ʼ modifier letter apostrophe
  '\u201C': '"',  # “ left double
  '\u201D': '"',  # ” right double
  '\u201E': '"',  # „ low-9 double
  '\u201F': '"',  # ‟ high-reversed-9 double
  '\u2033': '"',  # ″ double prime
  '\u00AB': '"',  # « left guillemet
  '\u00BB': '"',  # » right guillemet
})


def normalize_quotes(txt):
  """Return text with fancy quotes/apostrophes folded to ASCII ' and " only.

  Accents and other Unicode are left alone (café stays café).
  """
  if not txt:
    return ''
  return txt.translate(_QUOTE_MAP)
