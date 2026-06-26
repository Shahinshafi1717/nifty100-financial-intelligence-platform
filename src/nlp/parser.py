"""
src/nlp/parser.py — Analysis text parser & CAGR cross-validator.
Sprint 5 / Module 9.1 + 9.5

Parses compounded_sales_growth, compounded_profit_growth,
stock_price_cagr, roe strings from analysis.xlsx into structured numbers.
Cross-validates parsed values against Ratio Engine computed CAGR.

Usage:
    python src/nlp/parser.py
"""

import re
import sqlite3
import logging
from pathlib import Path

import pandas as pd

BASE_DIR   = Path(__file__).resolve().parents[2]
DB_PATH    = BASE_DIR / "data" / "nifty100.db"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("nlp.parser")

# Pattern: "10 Years: 21%" or "5 Years: 6%" or "3 Years: 8%"
CAGR_PATTERN = re.compile(r"(\d+)\s*[Yy]ears?\s*:?\s*([\d.]+)\s*%", re.IGNORECASE)


def parse_cagr_text(raw_text: str) -> list[tuple[int, float]]:
    """
    Extract all (period_years, value_pct) pairs from a text field.
    Returns list of (n_years, cagr_value) tuples.

    Examples:
        "10 Years: 21%"      -> [(10, 21.0)]
        "5 Years: 6%"        -> [(5, 6.0)]
        "3 Years: 8%"        -> [(3, 8.0)]
    """
    if not raw_text or pd.isna(raw_text):
        return []
    results = []
    for match in CAGR_PATTERN.finditer(str(raw_text)):
        years = int(match.group(1))
        value = float(match.group(2))
        results.append((years, value))
    return results


def parse_all_analysis(analysis_df: pd.DataFrame) -> pd.DataFrame:
    """
    Parse all four text columns in analysis table into long-format rows.
    Returns DataFrame: company_id, metric_type, period_years, value_pct
    """
    rows = []
    metric_cols = {
        "compounded_sales_growth":  "revenue_cagr",
        "compounded_profit_growth": "pat_cagr",
        "stock_price_cagr":         "stock_price_cagr",
        "roe":                      "roe_period",
    }

    for _, row in analysis_df.iterrows():
        company_id = row["company_id"]
        for col, metric_name in metric_cols.items():
            raw = row.get(col, "")
            pairs = parse_cagr_text(raw)
            for (years, value) in pairs:
                rows.append({
                    "company_id":   company_id,
                    "metric_type":  metric_name,
                    "period_years": years,
                    "value_pct":    value,
                    "raw_text":     str(raw)[:100],
                })

    return pd.DataFrame(rows)


def cross_validate_cagr(parsed_df: pd.DataFrame,
                        computed_ratios: pd.DataFrame,
                        divergence_threshold: float = 5.0) -> pd.DataFrame:
    """
    Compare parsed analysis.xlsx CAGR values against Ratio Engine computed CAGR.
    Flags rows where absolute difference > divergence_threshold %.

    Returns DataFrame of divergences.
    """
    # Map metric_type -> computed_ratios column
    col_map = {
        "revenue_cagr": {3: "revenue_cagr_3yr", 5: "revenue_cagr_5yr", 10: "revenue_cagr_10yr"},
        "pat_cagr":     {3: "pat_cagr_3yr",     5: "pat_cagr_5yr",     10: "pat_cagr_10yr"},
    }

    # Get latest-year computed ratios per company
    latest = (
        computed_ratios
        .sort_values("year")
        .groupby("company_id")
        .last()
        .reset_index()
    )

    divergences = []
    for _, row in parsed_df.iterrows():
        metric = row["metric_type"]
        years  = int(row["period_years"])
        parsed_val = row["value_pct"]
        company_id = row["company_id"]

        if metric not in col_map:
            continue
        if years not in col_map[metric]:
            continue

        col = col_map[metric][years]
        comp_row = latest[latest["company_id"] == company_id]
        if comp_row.empty:
            continue

        computed_val = comp_row.iloc[0].get(col)
        if computed_val is None or pd.isna(computed_val):
            continue

        diff = abs(parsed_val - float(computed_val))
        divergences.append({
            "company_id":    company_id,
            "metric_type":   metric,
            "period_years":  years,
            "parsed_value":  parsed_val,
            "computed_value":round(float(computed_val), 2),
            "abs_difference":round(diff, 2),
            "flagged":       diff > divergence_threshold,
        })

    return pd.DataFrame(divergences)


def run_parser() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Full parser pipeline."""
    conn = sqlite3.connect(str(DB_PATH))
    analysis_df = pd.read_sql("SELECT * FROM analysis", conn)
    computed_df = pd.read_sql(
        "SELECT company_id, year, revenue_cagr_3yr, revenue_cagr_5yr, "
        "revenue_cagr_10yr, pat_cagr_3yr, pat_cagr_5yr, pat_cagr_10yr "
        "FROM computed_ratios", conn
    )
    conn.close()

    logger.info("Parsing %d analysis rows...", len(analysis_df))
    parsed = parse_all_analysis(analysis_df)
    logger.info("Parsed %d CAGR entries from %d companies",
                len(parsed), parsed["company_id"].nunique() if not parsed.empty else 0)

    # Write parsed CSV
    parsed.to_csv(OUTPUT_DIR / "analysis_parsed.csv", index=False)

    # Cross-validate
    cross_val = cross_validate_cagr(parsed, computed_df)
    cross_val.to_csv(OUTPUT_DIR / "cross_validation.csv", index=False)

    flagged = cross_val[cross_val["flagged"]] if not cross_val.empty else pd.DataFrame()
    logger.info("Cross-validation: %d comparisons, %d flagged (>5%% divergence)",
                len(cross_val), len(flagged))

    print(f"\n{'='*50}")
    print("NLP PARSER COMPLETE")
    print(f"{'='*50}")
    print(f"  Parsed entries   : {len(parsed)}")
    print(f"  Companies covered: {parsed['company_id'].nunique() if not parsed.empty else 0}")
    print(f"  Cross-validations: {len(cross_val)}")
    print(f"  Flagged (>5%%)    : {len(flagged)}")
    if not flagged.empty:
        print(f"\n  Flagged divergences:")
        for _, r in flagged.iterrows():
            print(f"    {r['company_id']} {r['metric_type']} {r['period_years']}yr: "
                  f"parsed={r['parsed_value']}% computed={r['computed_value']}% "
                  f"diff={r['abs_difference']}%")

    return parsed, cross_val


if __name__ == "__main__":
    run_parser()
