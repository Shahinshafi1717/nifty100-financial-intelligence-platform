"""
tests/etl/test_normalise.py
Unit tests for normalize_year() and normalize_ticker().
Covers all real-world formats found in the actual Nifty 100 datasets.
Run: pytest tests/etl/test_normalise.py -v
"""

import sys
from pathlib import Path

# Allow import from src/etl
sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "etl"))

from normaliser import normalize_year, normalize_ticker


# =============================================================================
# normalize_year — Standard formats
# =============================================================================

def test_year_mar_2024():
    assert normalize_year("Mar 2024") == "2024-03"

def test_year_mar_2023():
    assert normalize_year("Mar 2023") == "2023-03"

def test_year_mar_2011():
    assert normalize_year("Mar 2011") == "2011-03"

def test_year_dec_2023():
    assert normalize_year("Dec 2023") == "2023-12"

def test_year_dec_2012():
    assert normalize_year("Dec 2012") == "2012-12"

def test_year_jun_2015():
    assert normalize_year("Jun 2015") == "2015-06"

def test_year_sep_2022():
    assert normalize_year("Sep 2022") == "2022-09"

def test_year_sep_2024():
    assert normalize_year("Sep 2024") == "2024-09"

def test_year_sep_2011():
    assert normalize_year("Sep 2011") == "2011-09"

# =============================================================================
# normalize_year — Hyphen short formats (found in cashflow.xlsx)
# =============================================================================

def test_year_mar_short_23():
    assert normalize_year("Mar-23") == "2023-03"

def test_year_mar_short_24():
    assert normalize_year("Mar-24") == "2024-03"

def test_year_mar_short_13():
    assert normalize_year("Mar-13") == "2013-03"

def test_year_mar_short_16():
    assert normalize_year("Mar-16") == "2016-03"

def test_year_dec_short_22():
    assert normalize_year("Dec-22") == "2022-12"

# =============================================================================
# normalize_year — Integer year formats (found in balancesheet.xlsx)
# =============================================================================

def test_year_integer_2024():
    assert normalize_year("2024") == "2024-03"

def test_year_integer_2013():
    assert normalize_year("2013") == "2013-03"

def test_year_integer_2018():
    assert normalize_year("2018") == "2018-03"

def test_year_half_year():
    """2024.5 = half year → September"""
    assert normalize_year("2024.5") == "2024-09"

# =============================================================================
# normalize_year — Partial-year suffix stripping (found in P&L)
# =============================================================================

def test_year_partial_9m():
    """'Mar 2016 9m' = 9-month period → strip suffix → 2016-03"""
    assert normalize_year("Mar 2016 9m") == "2016-03"

def test_year_partial_15():
    """'Mar 2023 15' = 15-month period → strip suffix → 2023-03"""
    assert normalize_year("Mar 2023 15") == "2023-03"

# =============================================================================
# normalize_year — Already normalised
# =============================================================================

def test_year_already_normalised():
    assert normalize_year("2023-03") == "2023-03"

def test_year_already_normalised_dec():
    assert normalize_year("2022-12") == "2022-12"

# =============================================================================
# normalize_year — Bad / unparseable inputs
# =============================================================================

def test_year_ttm():
    assert normalize_year("TTM") == "PARSE_ERROR"

def test_year_garbage():
    assert normalize_year("garbage") == "PARSE_ERROR"

def test_year_empty_string():
    assert normalize_year("") == "PARSE_ERROR"

def test_year_none():
    assert normalize_year(None) == "PARSE_ERROR"

def test_year_na():
    assert normalize_year("N/A") == "PARSE_ERROR"

def test_year_nan_string():
    assert normalize_year("nan") == "PARSE_ERROR"

def test_year_xyz():
    assert normalize_year("xyz") == "PARSE_ERROR"

# =============================================================================
# normalize_ticker — Standard cases
# =============================================================================

def test_ticker_tcs():
    assert normalize_ticker("TCS") == "TCS"

def test_ticker_lower():
    assert normalize_ticker("tcs") == "TCS"

def test_ticker_mixed():
    assert normalize_ticker("Tcs") == "TCS"

def test_ticker_leading_space():
    assert normalize_ticker("  TCS") == "TCS"

def test_ticker_trailing_space():
    assert normalize_ticker("TCS  ") == "TCS"

def test_ticker_both_spaces():
    assert normalize_ticker("  TCS  ") == "TCS"

# =============================================================================
# normalize_ticker — Special characters preserved
# =============================================================================

def test_ticker_hyphen():
    """BAJAJ-AUTO has a hyphen — must be preserved."""
    assert normalize_ticker("BAJAJ-AUTO") == "BAJAJ-AUTO"

def test_ticker_ampersand():
    """M&M has an ampersand — must be preserved."""
    assert normalize_ticker("M&M") == "M&M"

def test_ticker_lowercase_ampersand():
    assert normalize_ticker("m&m") == "M&M"

# =============================================================================
# normalize_ticker — Length edge cases
# =============================================================================

def test_ticker_min_length():
    """2-char ticker is valid."""
    assert normalize_ticker("LT") == "LT"

def test_ticker_max_length():
    """12-char ticker is valid."""
    assert normalize_ticker("ABCDEFGHIJKL") == "ABCDEFGHIJKL"

def test_ticker_too_short():
    """Single char → INVALID."""
    assert normalize_ticker("A") == "INVALID"

def test_ticker_too_long():
    """13 chars → INVALID."""
    assert normalize_ticker("ABCDEFGHIJKLM") == "INVALID"

# =============================================================================
# normalize_ticker — None / empty inputs
# =============================================================================

def test_ticker_none():
    assert normalize_ticker(None) == "INVALID"

def test_ticker_empty():
    assert normalize_ticker("") == "INVALID"

def test_ticker_spaces_only():
    assert normalize_ticker("   ") == "INVALID"
