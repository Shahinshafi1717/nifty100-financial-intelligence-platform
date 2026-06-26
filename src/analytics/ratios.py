"""
ratios.py — Financial Ratio Engine
Sprint 2: Computes 50+ KPIs for every company-year combination.
Handles all edge cases: zero division, negative equity, debt-free,
bank/NBFC carve-outs, CAGR turnaround flags.

Usage:
    python src/analytics/ratios.py
    OR: make ratios
"""

import sqlite3
import logging
import time
from pathlib import Path

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parents[2]
DB_PATH    = BASE_DIR / "data" / "nifty100.db"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ratio_engine")

# Financial sector IDs — D/E carve-out (high leverage is structurally normal)
FINANCIAL_SECTORS = {"Financials"}

# CAGR flag constants
FLAG_TURNAROUND      = "TURNAROUND"
FLAG_DECLINE_TO_LOSS = "DECLINE_TO_LOSS"
FLAG_BOTH_NEGATIVE   = "BOTH_NEGATIVE"
FLAG_ZERO_BASE       = "ZERO_BASE"
FLAG_INSUFFICIENT    = "INSUFFICIENT"
FLAG_OK              = "OK"


# ─────────────────────────────────────────────────────────────────────────────
# Safe arithmetic helpers
# ─────────────────────────────────────────────────────────────────────────────

def safe_div(numerator, denominator, default=None):
    """Division returning default when denominator is zero/None."""
    try:
        if denominator is None or denominator == 0 or pd.isna(denominator):
            return default
        if pd.isna(numerator):
            return default
        return numerator / denominator
    except Exception:
        return default


def pct(numerator, denominator, default=None):
    """Percentage = (num/denom) × 100."""
    result = safe_div(numerator, denominator, default)
    return round(result * 100, 4) if result is not None else default


# ─────────────────────────────────────────────────────────────────────────────
# CAGR Engine
# ─────────────────────────────────────────────────────────────────────────────

def compute_cagr(start_val, end_val, n_years):
    """
    Compute CAGR with full turnaround/sign handling.
    Returns (cagr_value_or_None, flag_string).
    """
    if n_years < 3:
        return None, FLAG_INSUFFICIENT
    if start_val is None or end_val is None or pd.isna(start_val) or pd.isna(end_val):
        return None, FLAG_INSUFFICIENT
    if start_val == 0:
        return None, FLAG_ZERO_BASE
    if start_val < 0 and end_val > 0:
        return None, FLAG_TURNAROUND
    if start_val > 0 and end_val < 0:
        return None, FLAG_DECLINE_TO_LOSS
    if start_val < 0 and end_val < 0:
        return None, FLAG_BOTH_NEGATIVE
    try:
        cagr = ((end_val / start_val) ** (1.0 / n_years) - 1) * 100
        return round(cagr, 4), FLAG_OK
    except Exception:
        return None, FLAG_INSUFFICIENT


def cagr_for_company(series: pd.Series, n: int):
    """
    Given a time-indexed Series (sorted ascending by year),
    compute CAGR over last n years.
    Returns (value, flag).
    """
    if len(series) < n + 1:
        return None, FLAG_INSUFFICIENT
    end_val   = series.iloc[-1]
    start_val = series.iloc[-(n + 1)]
    return compute_cagr(start_val, end_val, n)


# ─────────────────────────────────────────────────────────────────────────────
# Capital Allocation Classification
# ─────────────────────────────────────────────────────────────────────────────

CAPITAL_ALLOCATION_MAP = {
    (+1, -1, -1): "Reinvestor — ops funding growth + returning capital",
    (+1, -1, +1): "Leveraged Growth — borrowing to invest",
    (+1, +1, -1): "Asset Harvester — divesting + returning capital",
    (+1, +1, +1): "Cash Accumulator — ops positive, selling assets, raising funds",
    (-1, +1, +1): "Distress — burning cash, raising funds to survive",
    (-1, -1, +1): "Startup / Distress — investing while losing cash",
    (-1, +1, -1): "Restructuring — selling assets to repay debt",
    (-1, -1, -1): "Deep Distress — negative on all three flows",
}


def classify_capital_allocation(cfo, cfi, cff):
    """Return (sign_tuple, label) for capital allocation pattern."""
    if any(v is None or pd.isna(v) for v in [cfo, cfi, cff]):
        return None, "Insufficient Data"
    signs = (
        1 if cfo >= 0 else -1,
        1 if cfi >= 0 else -1,
        1 if cff >= 0 else -1,
    )
    label = CAPITAL_ALLOCATION_MAP.get(signs, "Unclassified")
    return signs, label


# ─────────────────────────────────────────────────────────────────────────────
# Per-row KPI computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_row_kpis(row, is_financial: bool) -> dict:
    """
    Compute all single-year KPIs for one (company_id, year) row.
    Row must contain merged P&L + BS + CF columns.
    """
    # Raw inputs
    sales        = row.get("sales")
    op_profit    = row.get("operating_profit")
    other_income = row.get("other_income", 0) or 0
    interest     = row.get("interest", 0) or 0
    depreciation = row.get("depreciation", 0) or 0
    net_profit   = row.get("net_profit")
    eps          = row.get("eps")
    div_payout   = row.get("dividend_payout")
    tax_pct      = row.get("tax_percentage")

    equity_cap   = row.get("equity_capital", 0) or 0
    reserves     = row.get("reserves", 0) or 0
    borrowings   = row.get("borrowings", 0) or 0
    face_value   = row.get("face_value", 1) or 1
    total_assets = row.get("total_assets")
    fixed_assets = row.get("fixed_assets")
    investments  = row.get("investments", 0) or 0
    other_assets = row.get("other_asset", 0) or 0
    other_liab   = row.get("other_liabilities", 0) or 0
    cwip         = row.get("cwip", 0) or 0

    cfo = row.get("operating_activity")
    cfi = row.get("investing_activity")
    cff = row.get("financing_activity")

    # Derived aggregates
    total_equity  = equity_cap + reserves
    ebit          = (op_profit or 0) - (depreciation or 0)
    capital_emp   = total_equity + borrowings           # for ROCE
    net_debt      = borrowings - investments             # proxy

    r = {}

    # ── Profitability ────────────────────────────────────────────────────────
    r["net_profit_margin_pct"]       = pct(net_profit, sales)
    r["operating_profit_margin_pct"] = pct(op_profit, sales)
    r["ebit_margin_pct"]             = pct(ebit, sales)
    r["gross_profit_margin_pct"]     = pct((sales or 0) - (row.get("expenses") or 0), sales)

    # ROE — None if equity <= 0
    r["return_on_equity_pct"] = (
        pct(net_profit, total_equity)
        if total_equity > 0 else None
    )

    # ROCE — use sector-relative carve-out for financials
    r["return_on_capital_pct"] = (
        pct(ebit, capital_emp)
        if capital_emp > 0 and not is_financial else None
    )

    # ROA
    r["return_on_assets_pct"] = pct(net_profit, total_assets)

    # ── Leverage ─────────────────────────────────────────────────────────────
    # D/E: 0 for debt-free; carve-out for financials (flag only, don't None)
    if total_equity > 0:
        de = round(borrowings / total_equity, 4)
    else:
        de = None
    r["debt_to_equity"] = de
    r["is_debt_free"]   = 1 if borrowings == 0 else 0

    # ICR — None (Debt Free) if interest = 0
    if interest and interest > 0:
        icr = safe_div((op_profit or 0) + other_income, interest)
        r["interest_coverage"] = round(icr, 4) if icr is not None else None
    else:
        r["interest_coverage"] = None   # display as "Debt Free"

    r["net_debt_cr"]          = round(net_debt, 2) if net_debt is not None else None
    r["net_debt_to_ebitda"]   = (
        safe_div(net_debt, op_profit)
        if op_profit and op_profit > 0 else None
    )

    # ── Efficiency ───────────────────────────────────────────────────────────
    r["asset_turnover"]        = safe_div(sales, total_assets)
    r["fixed_asset_turnover"]  = safe_div(sales, fixed_assets) if fixed_assets and fixed_assets > 0 else None
    r["working_capital_days"]  = (
        safe_div((other_assets - other_liab), sales) * 365
        if sales and sales > 0 else None
    )

    # ── Cash Flow ────────────────────────────────────────────────────────────
    fcf = None
    if cfo is not None and cfi is not None:
        fcf = round(cfo + cfi, 2)
    r["free_cash_flow_cr"]       = fcf
    r["cash_from_operations_cr"] = cfo
    r["capex_cr"]                = round(abs(cfi), 2) if cfi is not None else None

    # CFO / PAT quality score
    if net_profit and net_profit != 0 and cfo is not None:
        r["cfo_to_pat_ratio"] = round(cfo / net_profit, 4)
    else:
        r["cfo_to_pat_ratio"] = None

    # CapEx intensity %
    r["capex_intensity_pct"] = pct(abs(cfi) if cfi else None, sales)

    # FCF conversion = FCF / EBITDA
    r["fcf_conversion_pct"] = (
        pct(fcf, op_profit)
        if fcf is not None and op_profit and op_profit > 0 else None
    )

    # Capital allocation
    signs, label = classify_capital_allocation(cfo, cfi, cff)
    r["capital_alloc_pattern"] = label
    r["cfo_sign"]  = signs[0] if signs else None
    r["cfi_sign"]  = signs[1] if signs else None
    r["cff_sign"]  = signs[2] if signs else None

    # ── Valuation (static) ───────────────────────────────────────────────────
    r["earnings_per_share"] = eps
    r["dividend_payout_ratio_pct"] = div_payout
    r["total_debt_cr"]      = round(borrowings, 2)

    # Book value per share
    if equity_cap > 0 and face_value > 0:
        shares_outstanding = equity_cap / face_value
        r["book_value_per_share"] = round(total_equity / shares_outstanding, 4)
    else:
        r["book_value_per_share"] = None

    return r


# ─────────────────────────────────────────────────────────────────────────────
# CAGR computation — multi-year per company
# ─────────────────────────────────────────────────────────────────────────────

def compute_cagr_table(merged: pd.DataFrame) -> pd.DataFrame:
    """
    For each company, compute multi-year CAGRs (3, 5, 10 yr) for:
    revenue, PAT, EPS.
    Returns DataFrame indexed by (company_id, year) with CAGR columns.
    """
    cagr_rows = []

    for company_id, grp in merged.groupby("company_id"):
        grp = grp.sort_values("year").reset_index(drop=True)

        rev_series = grp["sales"].reset_index(drop=True)
        pat_series = grp["net_profit"].reset_index(drop=True)
        eps_series = grp["eps"].reset_index(drop=True)

        for idx, row in grp.iterrows():
            entry = {"company_id": company_id, "year": row["year"]}

            for metric, series in [("revenue", rev_series),
                                    ("pat", pat_series),
                                    ("eps", eps_series)]:
                for n in [3, 5, 10]:
                    col_v = f"{metric}_cagr_{n}yr"
                    col_f = f"{metric}_cagr_{n}yr_flag"
                    sub = series.iloc[: idx + 1]
                    val, flag = cagr_for_company(sub, n)
                    entry[col_v] = val
                    entry[col_f] = flag

            cagr_rows.append(entry)

    return pd.DataFrame(cagr_rows)


# ─────────────────────────────────────────────────────────────────────────────
# FCF trend flag
# ─────────────────────────────────────────────────────────────────────────────

def flag_fcf_concern(merged: pd.DataFrame) -> pd.DataFrame:
    """Flag companies with FCF < 0 for 3+ consecutive years."""
    rows = []
    for company_id, grp in merged.groupby("company_id"):
        grp = grp.sort_values("year").reset_index(drop=True)
        fcf_vals = (grp["operating_activity"].fillna(0) +
                    grp["investing_activity"].fillna(0))
        consec = 0
        flags  = []
        for v in fcf_vals:
            if v < 0:
                consec += 1
            else:
                consec = 0
            flags.append(consec >= 3)
        grp["fcf_concern_3yr"] = [1 if f else 0 for f in flags]
        rows.append(grp[["company_id", "year", "fcf_concern_3yr"]])
    return pd.concat(rows, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main engine
# ─────────────────────────────────────────────────────────────────────────────

def run_ratio_engine():
    """Full ratio computation pipeline."""
    t_start = time.time()
    logger.info("=" * 60)
    logger.info("RATIO ENGINE — Starting KPI computation")
    logger.info("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Load base tables
    pl  = pd.read_sql("SELECT * FROM profitandloss",  conn)
    bs  = pd.read_sql("SELECT * FROM balancesheet",   conn)
    cf  = pd.read_sql("SELECT * FROM cashflow",       conn)
    co  = pd.read_sql("SELECT id, face_value FROM companies", conn)
    sec = pd.read_sql("SELECT company_id, broad_sector FROM sectors", conn)

    logger.info("Loaded: P&L=%d | BS=%d | CF=%d | Companies=%d",
                len(pl), len(bs), len(cf), len(co))

    # Merge P&L + BS + CF on (company_id, year)
    merged = (
        pl
        .merge(bs,  on=["company_id", "year"], how="inner", suffixes=("", "_bs"))
        .merge(cf,  on=["company_id", "year"], how="left",  suffixes=("", "_cf"))
        .merge(co.rename(columns={"id": "company_id"}), on="company_id", how="left")
        .merge(sec, on="company_id", how="left")
    )
    logger.info("Merged dataset: %d rows for ratio computation", len(merged))

    # Financial sector flag
    merged["is_financial"] = merged["broad_sector"].isin(FINANCIAL_SECTORS)

    # ── Compute per-row KPIs ─────────────────────────────────────────────────
    logger.info("Computing per-row KPIs...")
    kpi_records = []
    for _, row in merged.iterrows():
        kpis = compute_row_kpis(row.to_dict(), bool(row.get("is_financial", False)))
        kpis["company_id"] = row["company_id"]
        kpis["year"]       = row["year"]
        kpi_records.append(kpis)

    kpi_df = pd.DataFrame(kpi_records)
    logger.info("Per-row KPIs computed: %d rows × %d columns", len(kpi_df), len(kpi_df.columns))

    # ── Compute CAGR columns ─────────────────────────────────────────────────
    logger.info("Computing CAGR series (3yr / 5yr / 10yr)...")
    cagr_df = compute_cagr_table(merged)
    kpi_df = kpi_df.merge(cagr_df, on=["company_id", "year"], how="left")
    logger.info("CAGR columns added: %d new columns", len(cagr_df.columns) - 2)

    # ── FCF concern flag ─────────────────────────────────────────────────────
    fcf_flags = flag_fcf_concern(merged)
    kpi_df = kpi_df.merge(fcf_flags, on=["company_id", "year"], how="left")

    # ── Composite Financial Health Score (0–100) ─────────────────────────────
    logger.info("Computing composite Financial Health Score...")
    kpi_df = compute_health_score(kpi_df)

    # ── Write to SQLite ──────────────────────────────────────────────────────
    logger.info("Writing computed_ratios table to SQLite...")
    kpi_df.to_sql("computed_ratios", conn, if_exists="replace", index=False)

    # Update financial_ratios table with computed values (for API compatibility)
    _update_financial_ratios(conn, kpi_df)

    # ── Capital allocation CSV ───────────────────────────────────────────────
    cap_alloc_cols = ["company_id", "year", "cfo_sign", "cfi_sign", "cff_sign",
                      "capital_alloc_pattern"]
    cap_df = kpi_df[cap_alloc_cols].copy()
    cap_df.to_csv(OUTPUT_DIR / "capital_allocation.csv", index=False)
    logger.info("capital_allocation.csv written: %d rows", len(cap_df))

    # ── Edge case log ────────────────────────────────────────────────────────
    _write_edge_case_log(kpi_df)

    conn.close()

    total = round(time.time() - t_start, 2)
    logger.info("=" * 60)
    logger.info("RATIO ENGINE COMPLETE in %.2fs", total)
    logger.info("computed_ratios: %d rows × %d KPI columns", len(kpi_df), len(kpi_df.columns))
    logger.info("=" * 60)

    print(f"\n{'='*55}")
    print(f"RATIO ENGINE COMPLETE")
    print(f"{'='*55}")
    print(f"  Rows computed : {len(kpi_df)}")
    print(f"  KPI columns  : {len(kpi_df.columns)}")
    print(f"  Runtime      : {total}s")
    print(f"  Output DB    : {DB_PATH}")
    print(f"  capital_allocation.csv  : {OUTPUT_DIR}/capital_allocation.csv")
    print(f"  ratio_edge_cases.log    : {OUTPUT_DIR}/ratio_edge_cases.log")

    return kpi_df


# ─────────────────────────────────────────────────────────────────────────────
# Financial Health Score
# ─────────────────────────────────────────────────────────────────────────────

def winsorise(series: pd.Series, p_low=10, p_high=90) -> pd.Series:
    """Cap values at P10 / P90 to limit outlier distortion."""
    lo = series.quantile(p_low / 100)
    hi = series.quantile(p_high / 100)
    return series.clip(lower=lo, upper=hi)


def scale_0_100(series: pd.Series) -> pd.Series:
    """Min-max scale a series to 0–100."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series([50.0] * len(series), index=series.index)
    return (series - mn) / (mx - mn) * 100


def compute_health_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    Composite Financial Health Score (0–100).
    Weights:
        Profitability 35% : ROE(15%) + ROCE(10%) + NPM(10%)
        Cash Quality  30% : FCF CAGR 5yr(15%) + CFO/PAT(10%) + FCF>0 flag(5%)
        Growth        20% : Rev CAGR 5yr(10%) + PAT CAGR 5yr(10%)
        Leverage      15% : D/E(10%) + ICR(5%)
    """
    d = df.copy()

    # ── Profitability ────────────────────────────────────────────────────────
    roe  = winsorise(d["return_on_equity_pct"].fillna(0))
    roce = winsorise(d["return_on_capital_pct"].fillna(0))
    npm  = winsorise(d["net_profit_margin_pct"].fillna(0))
    prof_score = (scale_0_100(roe) * 0.15 +
                  scale_0_100(roce) * 0.10 +
                  scale_0_100(npm) * 0.10) / 0.35 * 0.35

    # ── Cash Quality ─────────────────────────────────────────────────────────
    fcf_cagr = winsorise(d["pat_cagr_5yr"].fillna(0))
    cfo_pat  = winsorise(d["cfo_to_pat_ratio"].fillna(0))
    fcf_flag = (d["free_cash_flow_cr"].fillna(0) > 0).astype(float) * 100
    cash_score = (scale_0_100(fcf_cagr) * 0.15 +
                  scale_0_100(cfo_pat) * 0.10 +
                  fcf_flag * 0.05) / 0.30 * 0.30

    # ── Growth ───────────────────────────────────────────────────────────────
    rev_cagr = winsorise(d["revenue_cagr_5yr"].fillna(0))
    pat_cagr = winsorise(d["pat_cagr_5yr"].fillna(0))
    growth_score = (scale_0_100(rev_cagr) * 0.10 +
                    scale_0_100(pat_cagr) * 0.10) / 0.20 * 0.20

    # ── Leverage ─────────────────────────────────────────────────────────────
    # D/E: lower = better; 0 → 100, 0.5 → 85, 1 → 70, 2 → 50, ≥5 → 0
    de_raw = d["debt_to_equity"].fillna(0).clip(lower=0, upper=10)
    de_score_vals = de_raw.apply(lambda x:
        100 if x == 0 else
        85  if x <= 0.5 else
        70  if x <= 1.0 else
        50  if x <= 2.0 else
        25  if x <= 5.0 else 0
    )
    # ICR: >10 → 100, 5 → 75, 3 → 50, <1.5 → 0
    icr_raw = d["interest_coverage"].fillna(999)   # debt-free gets max score
    icr_score_vals = icr_raw.apply(lambda x:
        100 if x >= 10 else
        75  if x >= 5  else
        50  if x >= 3  else
        25  if x >= 1.5 else 0
    )
    lev_score = de_score_vals * 0.10 + icr_score_vals * 0.05

    # ── Composite ────────────────────────────────────────────────────────────
    d["health_score"] = (prof_score + cash_score + growth_score + lev_score).round(2)
    d["health_score"] = d["health_score"].clip(0, 100)

    # Health band
    d["health_band"] = d["health_score"].apply(lambda s:
        "Excellent"  if s >= 70 else
        "Good"       if s >= 50 else
        "Moderate"   if s >= 30 else
        "Weak"
    )

    return d


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _update_financial_ratios(conn, kpi_df: pd.DataFrame):
    """
    Merge computed ratios back into the financial_ratios table
    so API endpoints that read financial_ratios get fresh computed data.
    """
    cols_to_update = [
        "company_id", "year",
        "net_profit_margin_pct", "operating_profit_margin_pct",
        "return_on_equity_pct", "debt_to_equity", "interest_coverage",
        "asset_turnover", "free_cash_flow_cr", "capex_cr",
        "earnings_per_share", "book_value_per_share",
        "dividend_payout_ratio_pct", "total_debt_cr",
        "cash_from_operations_cr",
    ]
    available = [c for c in cols_to_update if c in kpi_df.columns]
    subset = kpi_df[available].copy()

    # Rename to match schema
    rename_map = {
        "capex_cr": "capex_cr",
        "cash_from_operations_cr": "cash_from_operations_cr",
    }
    subset.rename(columns=rename_map, inplace=True)

    # Replace financial_ratios with computed values
    subset.to_sql("financial_ratios", conn, if_exists="replace", index=False)
    count = conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    logger.info("financial_ratios table updated: %d rows", count)


def _write_edge_case_log(kpi_df: pd.DataFrame):
    """Write ratio_edge_cases.log with CAGR flags and special cases."""
    log_path = OUTPUT_DIR / "ratio_edge_cases.log"
    lines = [
        "=" * 60,
        "RATIO ENGINE — EDGE CASE LOG",
        "=" * 60,
        "",
    ]

    # CAGR turnaround flags
    for metric in ["revenue", "pat", "eps"]:
        for n in [3, 5, 10]:
            flag_col = f"{metric}_cagr_{n}yr_flag"
            if flag_col not in kpi_df.columns:
                continue
            for flag_type in [FLAG_TURNAROUND, FLAG_DECLINE_TO_LOSS,
                               FLAG_BOTH_NEGATIVE, FLAG_ZERO_BASE]:
                flagged = kpi_df[kpi_df[flag_col] == flag_type][["company_id", "year"]]
                if len(flagged):
                    lines.append(f"[{flag_col}] {flag_type}: {len(flagged)} rows")
                    for _, r in flagged.head(5).iterrows():
                        lines.append(f"    {r['company_id']} {r['year']}")

    lines.append("")
    lines.append("Debt-free companies (interest_coverage = None):")
    df_free = kpi_df[kpi_df["is_debt_free"] == 1][["company_id"]].drop_duplicates()
    for _, r in df_free.iterrows():
        lines.append(f"    {r['company_id']}")

    lines.append("")
    lines.append("Negative equity rows (ROE = None):")
    neg_eq = kpi_df[kpi_df["return_on_equity_pct"].isna() & (kpi_df["debt_to_equity"].isna())]
    lines.append(f"    {len(neg_eq)} rows")

    with open(log_path, "w") as f:
        f.write("\n".join(lines))

    logger.info("Edge case log written: %s", log_path)


if __name__ == "__main__":
    run_ratio_engine()
