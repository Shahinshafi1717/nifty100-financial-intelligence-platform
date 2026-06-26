"""
src/nlp/pros_cons_generator.py — Auto Pros/Cons Generator
Sprint 5 / Module 9.2

Generates rule-based pros and cons for all 92 companies using
KPI threshold rules. Fills the 84 companies missing from prosandcons.xlsx.
Confidence score assigned per rule trigger.

Usage:
    python src/nlp/pros_cons_generator.py
"""

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
logger = logging.getLogger("pros_cons_generator")


# ─────────────────────────────────────────────────────────────────────────────
# Rule definitions
# Each rule: (rule_id, type, condition_fn, text_template, confidence)
# condition_fn receives a dict of latest-year KPIs
# ─────────────────────────────────────────────────────────────────────────────

def _v(d, key, default=None):
    """Safe value getter with None/NaN handling."""
    v = d.get(key, default)
    if v is None or (isinstance(v, float) and v != v):
        return default
    return v


PRO_RULES = [
    (
        "PRO-01", "pro",
        lambda d: (_v(d, "return_on_equity_pct", 0) or 0) > 20,
        lambda d: f"Strong ROE of {_v(d,'return_on_equity_pct',0):.1f}% "
                  f"indicates excellent shareholder value creation.",
        90,
    ),
    (
        "PRO-02", "pro",
        lambda d: (_v(d, "is_debt_free", 0) or 0) == 1,
        lambda d: "Company is debt-free with zero borrowings, providing "
                  "strong balance sheet resilience.",
        95,
    ),
    (
        "PRO-03", "pro",
        lambda d: (_v(d, "revenue_cagr_5yr", 0) or 0) > 15,
        lambda d: f"Revenue has compounded at {_v(d,'revenue_cagr_5yr',0):.1f}% "
                  f"over 5 years, demonstrating strong growth.",
        85,
    ),
    (
        "PRO-04", "pro",
        lambda d: (_v(d, "free_cash_flow_cr", 0) or 0) > 0
                  and (_v(d, "fcf_concern_3yr", 1) or 0) == 0,
        lambda d: f"Positive free cash flow of ₹{_v(d,'free_cash_flow_cr',0):.0f} Cr "
                  f"signals strong cash generation.",
        85,
    ),
    (
        "PRO-05", "pro",
        lambda d: (_v(d, "debt_to_equity", 99) or 99) < 0.3
                  and (_v(d, "debt_to_equity", 99) or 99) > 0,
        lambda d: f"Low debt-to-equity of {_v(d,'debt_to_equity',0):.2f}× "
                  f"reflects conservative financial management.",
        80,
    ),
    (
        "PRO-06", "pro",
        lambda d: (_v(d, "operating_profit_margin_pct", 0) or 0) > 20,
        lambda d: f"Operating margin of {_v(d,'operating_profit_margin_pct',0):.1f}% "
                  f"indicates strong operational efficiency.",
        80,
    ),
    (
        "PRO-07", "pro",
        lambda d: (_v(d, "pat_cagr_5yr", 0) or 0) > 20,
        lambda d: f"Net profit has grown at {_v(d,'pat_cagr_5yr',0):.1f}% CAGR "
                  f"over 5 years, reflecting strong earnings momentum.",
        85,
    ),
    (
        "PRO-08", "pro",
        lambda d: (_v(d, "interest_coverage") is None)
                  or (_v(d, "interest_coverage", 0) or 0) > 10,
        lambda d: "Exceptional interest coverage ratio indicates "
                  "comfortable debt servicing ability.",
        75,
    ),
    (
        "PRO-09", "pro",
        lambda d: (_v(d, "cfo_to_pat_ratio", 0) or 0) > 1.0,
        lambda d: f"CFO/PAT ratio of {_v(d,'cfo_to_pat_ratio',0):.2f}× "
                  f"indicates high earnings quality with strong cash conversion.",
        80,
    ),
    (
        "PRO-10", "pro",
        lambda d: (_v(d, "health_score", 0) or 0) >= 70,
        lambda d: f"Composite Financial Health Score of "
                  f"{_v(d,'health_score',0):.0f}/100 — rated Excellent.",
        90,
    ),
    (
        "PRO-11", "pro",
        lambda d: (_v(d, "return_on_capital_pct", 0) or 0) > 20,
        lambda d: f"ROCE of {_v(d,'return_on_capital_pct',0):.1f}% "
                  f"demonstrates efficient use of capital employed.",
        80,
    ),
    (
        "PRO-12", "pro",
        lambda d: (_v(d, "revenue_cagr_10yr", 0) or 0) > 12,
        lambda d: f"Consistent 10-year revenue CAGR of "
                  f"{_v(d,'revenue_cagr_10yr',0):.1f}% reflects durable business model.",
        85,
    ),
]

CON_RULES = [
    (
        "CON-01", "con",
        lambda d: (_v(d, "debt_to_equity", 0) or 0) > 2.0
                  and not (_v(d, "broad_sector","") in ("Financials",)),
        lambda d: f"High debt-to-equity of {_v(d,'debt_to_equity',0):.1f}× "
                  f"raises leverage concerns.",
        85,
    ),
    (
        "CON-02", "con",
        lambda d: (_v(d, "free_cash_flow_cr", 0) or 0) < 0
                  or (_v(d, "fcf_concern_3yr", 0) or 0) == 1,
        lambda d: "Negative or deteriorating free cash flow over 3 consecutive "
                  "years raises cash generation concerns.",
        85,
    ),
    (
        "CON-03", "con",
        lambda d: (_v(d, "net_profit_margin_pct", 0) or 0) < 5
                  and (_v(d, "net_profit_margin_pct", 0) or 0) > 0,
        lambda d: f"Thin net profit margin of {_v(d,'net_profit_margin_pct',0):.1f}% "
                  f"leaves limited buffer against revenue shocks.",
        75,
    ),
    (
        "CON-04", "con",
        lambda d: (_v(d, "return_on_equity_pct", 0) or 0) < 10
                  and (_v(d, "return_on_equity_pct", 0) or 0) > 0,
        lambda d: f"ROE of {_v(d,'return_on_equity_pct',0):.1f}% is below "
                  f"the 10% threshold, indicating suboptimal capital returns.",
        75,
    ),
    (
        "CON-05", "con",
        lambda d: (_v(d, "interest_coverage") is not None)
                  and (_v(d, "interest_coverage", 99) or 99) < 2.0,
        lambda d: f"Interest coverage of {_v(d,'interest_coverage',0):.1f}× "
                  f"is below the 2× safety threshold.",
        85,
    ),
    (
        "CON-06", "con",
        lambda d: (_v(d, "revenue_cagr_5yr", 0) or 0) < 5
                  and (_v(d, "revenue_cagr_5yr_flag","") not in
                       ("TURNAROUND","INSUFFICIENT")),
        lambda d: f"Sluggish 5-year revenue CAGR of "
                  f"{_v(d,'revenue_cagr_5yr',0):.1f}% indicates slow growth.",
        70,
    ),
    (
        "CON-07", "con",
        lambda d: (_v(d, "capex_intensity_pct", 0) or 0) > 10,
        lambda d: f"High CapEx intensity of "
                  f"{_v(d,'capex_intensity_pct',0):.1f}% of revenue "
                  f"constrains free cash flow generation.",
        70,
    ),
    (
        "CON-08", "con",
        lambda d: (_v(d, "cfo_to_pat_ratio", 0) or 0) < 0.5
                  and (_v(d, "cfo_to_pat_ratio") is not None),
        lambda d: f"Low CFO/PAT ratio of {_v(d,'cfo_to_pat_ratio',0):.2f}× "
                  f"suggests accrual-based earnings rather than cash earnings.",
        80,
    ),
    (
        "CON-09", "con",
        lambda d: (_v(d, "health_score", 100) or 100) < 35,
        lambda d: f"Composite Health Score of {_v(d,'health_score',0):.0f}/100 "
                  f"indicates multiple financial weakness signals.",
        85,
    ),
    (
        "CON-10", "con",
        lambda d: (_v(d, "net_profit_margin_pct", 0) or 0) < 0,
        lambda d: f"Negative net profit margin of "
                  f"{_v(d,'net_profit_margin_pct',0):.1f}% — company is loss-making.",
        90,
    ),
    (
        "CON-11", "con",
        lambda d: (_v(d, "working_capital_days", 0) or 0) > 180,
        lambda d: f"Working capital cycle of "
                  f"{_v(d,'working_capital_days',0):.0f} days suggests "
                  f"slow collections or high inventory.",
        70,
    ),
    (
        "CON-12", "con",
        lambda d: (_v(d, "dividend_payout_ratio_pct", 0) or 0) > 100,
        lambda d: f"Dividend payout of "
                  f"{_v(d,'dividend_payout_ratio_pct',0):.0f}% exceeds earnings — "
                  f"may not be sustainable.",
        75,
    ),
]

ALL_RULES = PRO_RULES + CON_RULES


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment scorer using NLTK VADER
# ─────────────────────────────────────────────────────────────────────────────

def score_sentiment(text: str) -> float:
    """Return VADER compound sentiment score (-1 to 1)."""
    try:
        from nltk.sentiment import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
        return round(sia.polarity_scores(text)["compound"], 3)
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Main generator
# ─────────────────────────────────────────────────────────────────────────────

def run_pros_cons_generator(confidence_threshold: int = 70) -> pd.DataFrame:
    """
    Generate pros and cons for all 92 companies.
    Only outputs entries with confidence >= confidence_threshold.
    """
    conn = sqlite3.connect(str(DB_PATH))

    # Load latest-year KPIs for all companies
    universe = pd.read_sql("""
        SELECT cr.*, s.broad_sector, s.sub_sector
        FROM computed_ratios cr
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
    """, conn)

    # Load existing prosandcons (to supplement, not replace)
    existing = pd.read_sql("SELECT company_id, pros, cons FROM prosandcons", conn)
    conn.close()

    existing_companies = set(existing["company_id"].unique())
    logger.info("Universe: %d companies | Existing pros/cons: %d companies",
                len(universe), len(existing_companies))

    rows = []
    for _, kpi_row in universe.iterrows():
        company_id = kpi_row["company_id"]
        kpi_dict   = kpi_row.to_dict()

        for (rule_id, entry_type, condition_fn, text_fn, confidence) in ALL_RULES:
            if confidence < confidence_threshold:
                continue
            try:
                triggered = condition_fn(kpi_dict)
            except Exception:
                triggered = False

            if not triggered:
                continue

            try:
                text = text_fn(kpi_dict)
            except Exception:
                continue

            sentiment = score_sentiment(text)
            rows.append({
                "company_id":       company_id,
                "type":             entry_type,
                "rule_id":          rule_id,
                "text":             text,
                "confidence_pct":   confidence,
                "sentiment_score":  sentiment,
                "source":           "auto_generated",
            })

    # Add source=manual rows from existing prosandcons
    for _, row in existing.iterrows():
        if pd.notna(row.get("pros")) and str(row["pros"]).strip():
            rows.append({
                "company_id":     row["company_id"],
                "type":           "pro",
                "rule_id":        "MANUAL",
                "text":           str(row["pros"]),
                "confidence_pct": 100,
                "sentiment_score": score_sentiment(str(row["pros"])),
                "source":          "manual",
            })
        if pd.notna(row.get("cons")) and str(row["cons"]).strip():
            rows.append({
                "company_id":     row["company_id"],
                "type":           "con",
                "rule_id":        "MANUAL",
                "text":           str(row["cons"]),
                "confidence_pct": 100,
                "sentiment_score": score_sentiment(str(row["cons"])),
                "source":          "manual",
            })

    result_df = pd.DataFrame(rows)

    # Validate: every company must have at least 1 pro and 1 con
    if not result_df.empty:
        coverage = result_df.groupby("company_id")["type"].apply(
            lambda x: set(x)
        )
        missing_pro  = [c for c, types in coverage.items() if "pro"  not in types]
        missing_con  = [c for c, types in coverage.items() if "con"  not in types]

        if missing_pro:
            logger.warning("Missing pros for: %s", missing_pro)
        if missing_con:
            logger.warning("Missing cons for: %s", missing_con)

        companies_covered = result_df["company_id"].nunique()
        logger.info("Coverage: %d companies | %d pros | %d cons",
                    companies_covered,
                    len(result_df[result_df["type"] == "pro"]),
                    len(result_df[result_df["type"] == "con"]))
    else:
        companies_covered = 0

    result_df.to_csv(OUTPUT_DIR / "pros_cons_generated.csv", index=False)
    logger.info("pros_cons_generated.csv written: %d rows", len(result_df))

    print(f"\n{'='*50}")
    print("PROS/CONS GENERATOR COMPLETE")
    print(f"{'='*50}")
    print(f"  Companies covered : {companies_covered} / {len(universe)}")
    if not result_df.empty:
        print(f"  Total entries     : {len(result_df)}")
        print(f"  Pros              : {len(result_df[result_df['type']=='pro'])}")
        print(f"  Cons              : {len(result_df[result_df['type']=='con'])}")
        print(f"  Auto-generated    : {len(result_df[result_df['source']=='auto_generated'])}")
        print(f"  Manual (original) : {len(result_df[result_df['source']=='manual'])}")
    print(f"  Output : {OUTPUT_DIR}/pros_cons_generated.csv")

    return result_df


if __name__ == "__main__":
    run_pros_cons_generator()
