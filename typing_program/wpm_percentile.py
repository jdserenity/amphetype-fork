"""Adult typing-speed percentile vs Dhakal et al. (CHI 2018).

Source: Dhakal, Feit, Kristensson & Oulasvirta, "Observations on Typing from
136 Million Keystrokes" (CHI 2018). N=168,960 online volunteers; mean 51.56 WPM,
SD 20.20. Paper reports ~26 WPM (10th percentile) and ~78 WPM (90th).
"""

import math

ADULT_WPM_MEAN = 51.56
ADULT_WPM_SD = 20.20


def adult_wpm_percentile_rank(wpm):
  """Share of adults typing slower (0–100). Normal fit matches paper deciles."""
  z = (wpm - ADULT_WPM_MEAN) / ADULT_WPM_SD
  return 100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def adult_top_percent(wpm):
  """Top X% among adults (1–99). None when wpm is missing."""
  if wpm is None:
    return None
  top = int(round(100.0 - adult_wpm_percentile_rank(wpm)))
  return max(1, min(99, top))


def format_adult_top_percent_label(wpm):
  top = adult_top_percent(wpm)
  if top is None:
    return None
  return 'Top %d%% of adults' % top
