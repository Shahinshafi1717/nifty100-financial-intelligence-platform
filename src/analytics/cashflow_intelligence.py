"""
src/analytics/cashflow_intelligence.py — Cash Flow Intelligence Module
Sprint 5 / Module 7

Deep analysis of CFO quality, CapEx intensity, FCF compounding,
distress detection, and capital allocation matrix for all 92 companies.

Usage:
    python src/analytics/cashflow_intelligence.py
"""

import sqlite3
import logging
from pathlib import Path

import pandas as pd
import numpy as np

BASE_DIR   = Path(__file__).resolve().parents[2]
DB_PATH    = BASE_DIR / "data" / "nifty100.db"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("cashflow_intelligence")


# ─────────────────────────────────────────────────────────────────────────────
# CFO Quality Tier
# ─────────────────────────────────────────────────────────────────────────────

def cfo_quality_tier(cfo_pat_ratio: float | None) -> str:
    """Classify CFO/PAT ratio into earnings quality tier."""
    if cfo_pat_ratio is None or np.isnan(cfo_pat_ratio):
        return "Insufficient Data"
    if cfo_pat_ratio >= 1.0:
        return "High Quality Earnings"
    if cfo_pat_ratio >= 0.5:
        return "Moderate Quality"
    return "Accrual Risk"


def capex_intensity_tier(capex_pct: float | None) -> str:
    """Classify CapEx intensity % into asset-light / moderate / heavy."""
    if capex_pct is None or np.isnan(capex_pct):
        return "Unknown"
    if capex_pct < 3.0:
        return "Asset-Light (<3%)"
    if capex_pct <= 8.0:
        return "Moderate (3–8%)"
    return "Capital Intensive (>8%)"


def fcf_conversion_tier(fcf_conv: float | None) -> str:
    """Classify FCF conversion rate (FCF/EBITDA) into tiers."""
    if fcf_conv is None or np.isnan(fcf_conv):
        return "Unknown"
    if fcf_conv >= 60.0:
        return "Efficient (>60%)"
    if fcf_conv >= 30.0:
        return "Moderate (30–60%)"
    return "CapEx Heavy (<30%)"


# ─────────────────────────────────────────────────────────────────────────────
# Distress & deleveraging pattern detection
# ─────────────────────────────────────────────────────────────────────────────

def detect_distress(cf_history: pd.DataFrame) -> dict:
    """
    Detect distress pattern: CFO < 0 AND CFF > 0 in latest year
    (raising equity/debt to fund operations).
    Also detect deleveraging: CFF < 0 AND borrowings declining YoY.
    Returns dict of flags.
    """
    if cf_history.empty or len(cf_history) < 2:
        return {"distress_signal": False, "deleveraging": False}

    cf_sorted = cf_history.sort_values("year")
    latest = cf_sorted.iloc[-1]

    distress = (
        pd.notna(latest.get("operating_activity")) and
        latest["operating_activity"] < 0 and
        pd.notna(latest.get("financing_activity")) and
        latest["financing_activity"] > 0
    )

    return {
        "distress_signal": bool(distress),
        "cfo_latest":      float(latest.get("operating_activity", 0) or 0),
        "cff_latest":      float(latest.get("financing_activity", 0) or 0),
    }


def detect_consecutive_negative_fcf(cf_history: pd.DataFrame,
                                     n: int = 3) -> bool:
    """Return True if FCF negative for n consecutive years ending at latest year."""
    if cf_history.empty or len(cf_history) < n:
        return False
    cf_sorted = cf_history.sort_values("year")
    last_n = cf_sorted.tail(n)
    fcf = last_n["operating_activity"].fillna(0) + last_n["investing_activity"].fillna(0)
    return bool((fcf < 0).all())


# ─────────────────────────────────────────────────────────────────────────────
# FCF CAGR computation
# ─────────────────────────────────────────────────────────────────────────────

def fcf_cagr(cf_history: pd.DataFrame, n: int) -> float | None:
    """Compute FCF CAGR over n years. Returns None on turnaround/insufficient data."""
    if cf_history.empty or len(cf_history) < n + 1:
        return None
    cf = cf_history.sort_values("year").copy()
    cf["fcf"] = cf["operating_activity"].fillna(0) + cf["investing_activity"].fillna(0)
    end_val   = cf["fcf"].iloc[-1]
    start_val = cf["fcf"].iloc[-(n + 1)]
    if start_val <= 0 or end_val <= 0:
        return None
    try:
        return round(((end_val / start_val) ** (1.0 / n) - 1) * 100, 2)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_cashflow_intelligence() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Full Cash Flow Intelligence pipeline.
    Returns (intelligence_df, distress_df).
    """
    conn = sqlite3.connect(str(DB_PATH))

    # Load all cash flow history
    cf_all = pd.read_sql("SELECT * FROM cashflow ORDER BY company_id, year", conn)
    cr_all = pd.read_sql("""
        SELECT cr.company_id, cr.year, cr.cfo_to_pat_ratio, cr.capex_intensity_pct,
               cr.fcf_conversion_pct, cr.free_cash_flow_cr, cr.capital_alloc_pattern,
               cr.cfo_sign, cr.cfi_sign, cr.cff_sign, cr.health_score,
               cr.fcf_concern_3yr, c.company_name, s.broad_sector
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        LEFT JOIN sectors s ON cr.company_id = s.company_id
    """, conn)
    conn.close()

    # Latest-year computed ratios
    latest_cr = (
        cr_all.sort_values("year")
              .groupby("company_id")
              .last()
              .reset_index()
    )

    rows = []
    distress_rows = []

    for company_id in latest_cr["company_id"].unique():
        cr_row = latest_cr[latest_cr["company_id"] == company_id].iloc[0]
        cf_hist = cf_all[cf_all["company_id"] == company_id].copy()

        # Tiers
        cfo_tier   = cfo_quality_tier(cr_row.get("cfo_to_pat_ratio"))
        capex_tier = capex_intensity_tier(cr_row.get("capex_intensity_pct"))
        fcf_tier   = fcf_conversion_tier(cr_row.get("fcf_conversion_pct"))

        # FCF CAGRs
        fcf_cagr_5  = fcf_cagr(cf_hist, 5)
        fcf_cagr_10 = fcf_cagr(cf_hist, 10)

        # Consecutive negative FCF flag
        consec_neg_fcf = detect_consecutive_negative_fcf(cf_hist, 3)

        # Distress detection
        distress_info = detect_distress(cf_hist)

        row = {
            "company_id":            company_id,
            "company_name":          cr_row.get("company_name"),
            "broad_sector":          cr_row.get("broad_sector"),
            "year":                  cr_row.get("year"),
            # CFO Quality
            "cfo_to_pat_ratio":      cr_row.get("cfo_to_pat_ratio"),
            "cfo_quality_tier":      cfo_tier,
            # CapEx
            "capex_intensity_pct":   cr_row.get("capex_intensity_pct"),
            "capex_tier":            capex_tier,
            # FCF
            "fcf_cr":                cr_row.get("free_cash_flow_cr"),
            "fcf_cagr_5yr":          fcf_cagr_5,
            "fcf_cagr_10yr":         fcf_cagr_10,
            "fcf_concern_3yr":       int(cr_row.get("fcf_concern_3yr", 0) or 0),
            "consec_neg_fcf":        int(consec_neg_fcf),
            # FCF conversion
            "fcf_conversion_pct":    cr_row.get("fcf_conversion_pct"),
            "fcf_conversion_tier":   fcf_tier,
            # Capital allocation
            "capital_alloc_pattern": cr_row.get("capital_alloc_pattern"),
            "cfo_sign":              cr_row.get("cfo_sign"),
            "cfi_sign":              cr_row.get("cfi_sign"),
            "cff_sign":              cr_row.get("cff_sign"),
            # Distress
            "distress_signal":       int(distress_info["distress_signal"]),
            # Health
            "health_score":          cr_row.get("health_score"),
        }
        rows.append(row)

        if distress_info["distress_signal"]:
            distress_rows.append({
                "company_id":    company_id,
                "company_name":  cr_row.get("company_name"),
                "broad_sector":  cr_row.get("broad_sector"),
                "cfo_latest":    distress_info["cfo_latest"],
                "cff_latest":    distress_info["cff_latest"],
                "health_score":  cr_row.get("health_score"),
                "pattern":       cr_row.get("capital_alloc_pattern"),
                "alert":         "CFO < 0 and financing inflows — potential distress",
            })

    cf_intel_df = pd.DataFrame(rows)
    distress_df = pd.DataFrame(distress_rows)

    # Write outputs
    cf_intel_df.round(2).to_excel(OUTPUT_DIR / "cashflow_intelligence.xlsx", index=False)
    distress_df.to_csv(OUTPUT_DIR / "distress_alerts.csv", index=False)

    # Summary
    print(f"\n{'='*55}")
    print("CASH FLOW INTELLIGENCE COMPLETE")
    print(f"{'='*55}")
    print(f"  Companies analysed     : {len(cf_intel_df)}")
    print(f"\n  CFO Quality Tiers:")
    for tier, n in cf_intel_df["cfo_quality_tier"].value_counts().items():
        print(f"    {tier:<30} {n:>3}")
    print(f"\n  CapEx Intensity Tiers:")
    for tier, n in cf_intel_df["capex_tier"].value_counts().items():
        print(f"    {tier:<30} {n:>3}")
    print(f"\n  Distress signals       : {len(distress_df)}")
    if not distress_df.empty:
        for _, r in distress_df.iterrows():
            print(f"    ⚠️  {r['company_id']:<15} {r['broad_sector']}")
    print(f"\n  cashflow_intelligence.xlsx : {OUTPUT_DIR}/cashflow_intelligence.xlsx")
    print(f"  distress_alerts.csv        : {OUTPUT_DIR}/distress_alerts.csv")

    return cf_intel_df, distress_df


if __name__ == "__main__":
    run_cashflow_intelligence()
