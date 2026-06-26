"""
valuation.py — Valuation & Market Data Module (Sprint 4 / Module 6)
P/E trends, P/B vs ROE scatter, EV/EBITDA comparison,
FCF yield, dividend yield ranking, overvaluation flags.

Usage:
    python src/analytics/valuation.py
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
logger = logging.getLogger("valuation")


def run_valuation_module() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute valuation flags and produce:
      - valuation_summary.xlsx  (all 92 companies)
      - valuation_flags.csv     (Caution / Discount flagged companies)
    Returns (summary_df, flags_df).
    """
    conn = sqlite3.connect(str(DB_PATH))

    # Load market_cap + computed_ratios + sectors
    mc = pd.read_sql("SELECT * FROM market_cap", conn)
    cr = pd.read_sql("""
        SELECT cr.company_id, cr.year, c.company_name,
               cr.return_on_equity_pct, cr.net_profit_margin_pct,
               cr.free_cash_flow_cr, cr.health_score, cr.health_band,
               cr.revenue_cagr_5yr, cr.pat_cagr_5yr,
               s.broad_sector
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
    """, conn)

    # Merge latest computed_ratios with market_cap year=2024
    mc_2024 = mc[mc["year"] == 2024].copy()
    summary = cr.merge(mc_2024, on="company_id", how="left")

    # ── FCF Yield ─────────────────────────────────────────────────────────────
    mask = summary["market_cap_crore"].notna() & (summary["market_cap_crore"] > 0)
    summary["fcf_yield_pct"] = None
    summary.loc[mask, "fcf_yield_pct"] = (
        summary.loc[mask, "free_cash_flow_cr"] /
        summary.loc[mask, "market_cap_crore"] * 100
    ).round(3)

    # ── Sector median P/E ─────────────────────────────────────────────────────
    sector_pe = (
        summary.groupby("broad_sector")["pe_ratio"]
        .median().rename("sector_median_pe").reset_index()
    )
    summary = summary.merge(sector_pe, on="broad_sector", how="left")

    # ── EV/EBITDA vs sector median ────────────────────────────────────────────
    sector_ev = (
        summary.groupby("broad_sector")["ev_ebitda"]
        .median().rename("sector_median_ev_ebitda").reset_index()
    )
    summary = summary.merge(sector_ev, on="broad_sector", how="left")
    summary["ev_ebitda_vs_sector_pct"] = (
        (summary["ev_ebitda"] - summary["sector_median_ev_ebitda"])
        / summary["sector_median_ev_ebitda"].replace(0, np.nan) * 100
    ).round(1)

    # ── 5-year median P/E per company ─────────────────────────────────────────
    pe_5yr = (
        mc.groupby("company_id")["pe_ratio"]
        .median().rename("pe_5yr_median").reset_index()
    )
    summary = summary.merge(pe_5yr, on="company_id", how="left")

    # ── Overvaluation flags ───────────────────────────────────────────────────
    # Caution:  current P/E > sector median × 1.5
    # Discount: current P/E < sector median × 0.7
    def _flag(row):
        pe  = row.get("pe_ratio")
        med = row.get("sector_median_pe")
        if pd.isna(pe) or pd.isna(med) or med == 0:
            return "Neutral"
        if pe > med * 1.5:
            return "Caution"
        if pe < med * 0.7:
            return "Discount"
        return "Neutral"

    summary["valuation_flag"] = summary.apply(_flag, axis=1)

    # ── Dividend yield ranker ─────────────────────────────────────────────────
    summary["div_yield_rank"] = summary["dividend_yield_pct"].rank(
        ascending=False, na_option="bottom", method="min"
    ).astype("Int64")

    # ── Write outputs ─────────────────────────────────────────────────────────
    export_cols = [
        "company_id","company_name","broad_sector",
        "pe_ratio","pb_ratio","ev_ebitda","dividend_yield_pct",
        "market_cap_crore","enterprise_value_crore",
        "return_on_equity_pct","net_profit_margin_pct",
        "free_cash_flow_cr","fcf_yield_pct",
        "health_score","health_band",
        "revenue_cagr_5yr","pat_cagr_5yr",
        "sector_median_pe","pe_5yr_median",
        "ev_ebitda_vs_sector_pct","valuation_flag","div_yield_rank",
    ]
    export_cols = [c for c in export_cols if c in summary.columns]
    out_df = summary[export_cols].sort_values("health_score", ascending=False)

    out_df.round(2).to_excel(OUTPUT_DIR / "valuation_summary.xlsx", index=False)
    logger.info("valuation_summary.xlsx written: %d rows", len(out_df))

    flags_df = out_df[out_df["valuation_flag"].isin(["Caution","Discount"])].copy()
    flags_df[["company_id","company_name","broad_sector",
              "pe_ratio","sector_median_pe","valuation_flag"]].to_csv(
        OUTPUT_DIR / "valuation_flags.csv", index=False
    )
    logger.info("valuation_flags.csv: %d flagged companies", len(flags_df))

    # ── Write historical P/E to SQLite ────────────────────────────────────────
    mc.to_sql("market_cap", conn, if_exists="replace", index=False)

    conn.close()

    print(f"\n{'='*50}")
    print("VALUATION MODULE COMPLETE")
    print(f"{'='*50}")
    print(f"  Companies analysed : {len(out_df)}")
    caution  = (flags_df["valuation_flag"] == "Caution").sum()
    discount = (flags_df["valuation_flag"] == "Discount").sum()
    print(f"  Caution flags      : {caution}")
    print(f"  Discount flags     : {discount}")
    print(f"  valuation_summary.xlsx : {OUTPUT_DIR}/valuation_summary.xlsx")
    print(f"  valuation_flags.csv    : {OUTPUT_DIR}/valuation_flags.csv")

    return out_df, flags_df


if __name__ == "__main__":
    run_valuation_module()
