"""
normaliser.py — Year and Ticker normalisation functions.
Handles all real-world year formats found in the Nifty 100 datasets.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Month abbreviation to zero-padded month number
MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def normalize_year(raw: str) -> str:
    """
    Convert any year label found in the datasets into YYYY-MM format.

    Supported input formats (discovered from actual data inspection):
        'Mar 2024'      -> '2024-03'
        'Mar-24'        -> '2024-03'
        'Mar-2024'      -> '2024-03'
        'Dec 2023'      -> '2023-12'
        'Jun 2015'      -> '2015-06'
        'Sep 2022'      -> '2022-09'
        'Mar 2016 9m'   -> '2016-03'   (partial-year suffix stripped)
        'Mar 2023 15'   -> '2023-03'   (partial-year suffix stripped)
        '2024'          -> '2024-03'   (integer year → assume March FY close)
        '2024.5'        -> '2024-09'   (half-year → September)
        'TTM'           -> 'PARSE_ERROR'
        'garbage'       -> 'PARSE_ERROR'

    Returns:
        Normalised string in 'YYYY-MM' format, or 'PARSE_ERROR' on failure.
    """
    if raw is None:
        return "PARSE_ERROR"

    raw_str = str(raw).strip()

    # --- Handle special / known-bad values ---
    if raw_str.upper() in ("TTM", "N/A", "NA", "", "NAN"):
        logger.warning("normalize_year: special/unparseable value '%s'", raw_str)
        return "PARSE_ERROR"

    # --- Handle pure numeric year (e.g. '2024', '2013') ---
    if re.fullmatch(r"\d{4}", raw_str):
        return f"{raw_str}-03"

    # --- Handle half-year float (e.g. '2024.5') ---
    half_match = re.fullmatch(r"(\d{4})\.5", raw_str)
    if half_match:
        return f"{half_match.group(1)}-09"

    # --- Strip trailing partial-year suffixes (e.g. '9m', '15', '12m') ---
    # Examples: 'Mar 2016 9m', 'Mar 2023 15'
    cleaned = re.sub(r"\s+\d{1,2}[mM]?$", "", raw_str).strip()

    # --- Format: 'Mar 2024' / 'Dec 2012' / 'Jun 2015' / 'Sep 2022' ---
    m = re.fullmatch(r"([A-Za-z]{3})\s+(\d{4})", cleaned)
    if m:
        month_abbr = m.group(1).lower()
        year = m.group(2)
        month_num = MONTH_MAP.get(month_abbr)
        if month_num:
            return f"{year}-{month_num}"
        logger.warning("normalize_year: unknown month abbreviation '%s' in '%s'", month_abbr, raw_str)
        return "PARSE_ERROR"

    # --- Format: 'Mar-24' / 'Dec-22' (2-digit year) ---
    m = re.fullmatch(r"([A-Za-z]{3})-(\d{2})", cleaned)
    if m:
        month_abbr = m.group(1).lower()
        year_2d = int(m.group(2))
        # 2-digit year: 00-29 -> 2000s, 30-99 -> 1900s (data is 2010-2024)
        year = 2000 + year_2d if year_2d < 30 else 1900 + year_2d
        month_num = MONTH_MAP.get(month_abbr)
        if month_num:
            return f"{year}-{month_num}"
        logger.warning("normalize_year: unknown month abbreviation '%s' in '%s'", month_abbr, raw_str)
        return "PARSE_ERROR"

    # --- Format: 'Mar-2024' (4-digit year with hyphen) ---
    m = re.fullmatch(r"([A-Za-z]{3})-(\d{4})", cleaned)
    if m:
        month_abbr = m.group(1).lower()
        year = m.group(2)
        month_num = MONTH_MAP.get(month_abbr)
        if month_num:
            return f"{year}-{month_num}"
        return "PARSE_ERROR"

    # --- Already normalised 'YYYY-MM' ---
    if re.fullmatch(r"\d{4}-\d{2}", cleaned):
        return cleaned

    logger.warning("normalize_year: unrecognised format '%s'", raw_str)
    return "PARSE_ERROR"


def normalize_ticker(raw) -> str:
    """
    Normalise a company ticker / company_id to uppercase stripped string.

    Rules:
        - Strip leading/trailing whitespace
        - Convert to UPPERCASE
        - Preserve hyphens (e.g. BAJAJ-AUTO) and ampersands (e.g. M&M)
        - Return 'INVALID' if None, empty, or length out of range (2–12 chars)

    Returns:
        Normalised ticker string, or 'INVALID' if input is unusable.
    """
    if raw is None:
        return "INVALID"

    normalised = str(raw).strip().upper()

    if len(normalised) == 0:
        return "INVALID"

    if not (2 <= len(normalised) <= 12):
        logger.warning("normalize_ticker: length out of range for '%s' (len=%d)", normalised, len(normalised))
        return "INVALID"

    return normalised
