"""Tests for adult typing-speed percentile (Dhakal et al., CHI 2018)."""

import math

import pytest

from typing_program.wpm_percentile import (
  ADULT_WPM_MEAN, ADULT_WPM_SD, adult_top_percent, adult_wpm_percentile_rank,
  format_adult_top_percent_label,
)


def test_adult_wpm_percentile_rank_matches_paper_deciles():
  # CHI 2018: slowest 10% < ~26 WPM; fastest 10% > ~78 WPM
  assert adult_wpm_percentile_rank(26) == pytest.approx(10.0, abs=1.5)
  assert adult_wpm_percentile_rank(78) == pytest.approx(90.0, abs=1.5)
  assert adult_wpm_percentile_rank(ADULT_WPM_MEAN) == pytest.approx(50.0, abs=1.0)


def test_adult_top_percent_is_inverse_of_rank():
  assert adult_top_percent(78) == pytest.approx(10, abs=2)
  assert adult_top_percent(26) == pytest.approx(90, abs=2)
  assert adult_top_percent(120) == 1
  assert adult_top_percent(5) == 99


def test_adult_top_percent_none_when_no_wpm():
  assert adult_top_percent(None) is None
  assert format_adult_top_percent_label(None) is None


def test_format_adult_top_percent_label():
  assert format_adult_top_percent_label(74.5) == 'Top 13% of adults'
  assert format_adult_top_percent_label(51.6) == 'Top 50% of adults'


def test_percentile_uses_normal_cdf_on_published_mean_sd():
  z = (78 - ADULT_WPM_MEAN) / ADULT_WPM_SD
  expected = 100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
  assert adult_wpm_percentile_rank(78) == pytest.approx(expected)
