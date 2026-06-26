"""
engine.py — Investment Screener Engine
Sprint 3: Multi-criteria screener with 6 presets, custom filters,
composite scoring, sector-relative ranking, and Excel/CSV export.

Usage:
    python src/analytics/screener/engine.py
    OR imported by Streamlit dashboard and FastAPI.
"""

import sqlite3
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import yaml

BASE_DIR   = Path(__file__).resolve().parents[3]
DB_PATH    = BASE_DIR / "data" / "nifty100.db"
CONFIG_PATH = BASE_DIR / "config" / "screener_config.yaml"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config loader
# ─────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load screener_config.yaml."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────────────────────────────────────
# Universe loader — latest year per company, joined with market_cap & sectors
# ─────────────────────────────────────────────────────────────────────────────

def load_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Build the screening universe: latest-year computed_ratios for each company,
    joined with market_cap (year=2024), sectors, and company name.
    Winsorises extreme ROE values (BEL, HAL near-zero equity).
    """
    query = """
        SELECT
            cr.company_id,
            cr.year,
            c.company_name,
            s.broad_sector,
            s.sub_sector,
            s.market_cap_category,
            cr.return_on_equity_pct,
            cr.return_on_capital_pct,
            cr.net_profit_margin_pct,
            cr.operating_profit_margin_pct,
            cr.ebit_margin_pct,
            cr.debt_to_equity,
            cr.interest_coverage,
            cr.is_debt_free,
            cr.asset_turnover,
            cr.free_cash_flow_cr,
            cr.cash_from_operations_cr,
            cr.capex_cr,
            cr.cfo_to_pat_ratio,
            cr.capex_intensity_pct,
            cr.fcf_conversion_pct,
            cr.revenue_cagr_3yr,
            cr.revenue_cagr_5yr,
            cr.revenue_cagr_10yr,
            cr.pat_cagr_3yr,
            cr.pat_cagr_5yr,
            cr.eps_cagr_5yr,
            cr.earnings_per_share,
            cr.book_value_per_share,
            cr.dividend_payout_ratio_pct,
            cr.total_debt_cr,
            cr.health_score,
            cr.health_band,
            cr.capital_alloc_pattern,
            cr.fcf_concern_3yr,
            cr.net_debt_cr,
            mc.pe_ratio,
            mc.pb_ratio,
            mc.ev_ebitda,
            mc.dividend_yield_pct,
            mc.market_cap_crore
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        LEFT JOIN market_cap mc
               ON cr.company_id = mc.company_id AND mc.year = 2024
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
        ORDER BY cr.company_id
    """
    df = pd.read_sql(query, conn)

    # Winsorise extreme ROE (near-zero equity companies like BEL, HAL)
    cfg = load_config()
    cap = cfg.get("roe_winsorise_cap", 200.0)
    df["return_on_equity_pct"] = df["return_on_equity_pct"].clip(upper=cap)

    logger.info("Universe loaded: %d companies", len(df))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Composite score (0–100)
# ─────────────────────────────────────────────────────────────────────────────

def _scale(series: pd.Series) -> pd.Series:
    """Min-max scale to 0–100, handling constant series."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(50.0, index=series.index)
    return (series - mn) / (mx - mn) * 100.0


def compute_composite_score(df: pd.DataFrame) -> pd.Series:
    """
    Composite score 0–100.
    Profitability 35% | Cash Quality 30% | Growth 20% | Leverage 15%
    """
    d = df.copy()

    # Profitability (35%)
    roe  = _scale(d["return_on_equity_pct"].fillna(0).clip(-50, 200))
    roce = _scale(d["return_on_capital_pct"].fillna(0).clip(-50, 100))
    npm  = _scale(d["net_profit_margin_pct"].fillna(0).clip(-20, 60))
    prof = roe * 0.15 + roce * 0.10 + npm * 0.10

    # Cash Quality (30%)
    fcf_cagr = _scale(d["pat_cagr_5yr"].fillna(0).clip(-50, 100))
    cfo_pat  = _scale(d["cfo_to_pat_ratio"].fillna(0).clip(-2, 5))
    fcf_flag = (d["free_cash_flow_cr"].fillna(0) > 0).astype(float) * 100
    cash = fcf_cagr * 0.15 + cfo_pat * 0.10 + fcf_flag * 0.05

    # Growth (20%)
    rev_cagr = _scale(d["revenue_cagr_5yr"].fillna(0).clip(-20, 50))
    pat_cagr = _scale(d["pat_cagr_5yr"].fillna(0).clip(-50, 100))
    growth   = rev_cagr * 0.10 + pat_cagr * 0.10

    # Leverage (15%)
    de = d["debt_to_equity"].fillna(0).clip(0, 10)
    de_score = de.apply(lambda x:
        100 if x == 0 else 85 if x <= 0.5 else
        70  if x <= 1.0 else 50 if x <= 2.0 else
        25  if x <= 5.0 else 0)
    icr = d["interest_coverage"].fillna(999)
    icr_score = icr.apply(lambda x:
        100 if x >= 10 else 75 if x >= 5 else
        50  if x >= 3  else 25 if x >= 1.5 else 0)
    leverage = de_score * 0.10 + icr_score * 0.05

    total = (prof + cash + growth + leverage).clip(0, 100).round(2)
    return total


# ─────────────────────────────────────────────────────────────────────────────
# FCF Yield (needs market cap)
# ─────────────────────────────────────────────────────────────────────────────

def add_fcf_yield(df: pd.DataFrame) -> pd.DataFrame:
    """Add fcf_yield_pct = FCF / market_cap × 100."""
    df = df.copy()
    mask = df["market_cap_crore"].notna() & (df["market_cap_crore"] > 0) & df["free_cash_flow_cr"].notna()
    df["fcf_yield_pct"] = None
    df.loc[mask, "fcf_yield_pct"] = (
        df.loc[mask, "free_cash_flow_cr"] / df.loc[mask, "market_cap_crore"] * 100
    ).round(4)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Sector-relative rank
# ─────────────────────────────────────────────────────────────────────────────

def add_sector_ranks(df: pd.DataFrame) -> pd.DataFrame:
    """Add sector_rank (composite score rank within broad_sector)."""
    df = df.copy()
    df["sector_rank"] = (
        df.groupby("broad_sector")["composite_score"]
        .rank(ascending=False, method="min")
        .astype("Int64")
    )
    df["sector_percentile"] = (
        df.groupby("broad_sector")["composite_score"]
        .rank(pct=True)
        .round(4) * 100
    ).round(1)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Core filter engine
# ─────────────────────────────────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    Apply threshold filters to the universe DataFrame.

    filters dict keys match screener_config.yaml filter_map:
        min_roe, max_de, min_fcf, min_revenue_cagr_5yr,
        min_pat_cagr_5yr, max_pe, max_pb, min_dividend_yield,
        max_dividend_payout, sector, min_health_score, etc.
    """
    cfg = load_config()
    fmap = cfg.get("filter_map", {})

    result = df.copy()

    for param, value in filters.items():
        if value is None:
            continue

        # Sector / category string filters
        if param == "sector":
            result = result[result["broad_sector"].str.lower() == str(value).lower()]
            continue
        if param == "market_cap_category":
            result = result[result["market_cap_category"].str.lower() == str(value).lower()]
            continue

        # Numeric filters
        col = fmap.get(param)
        if col is None or col not in result.columns:
            logger.warning("Filter param '%s' → column '%s' not found, skipping", param, col)
            continue

        numeric_col = pd.to_numeric(result[col], errors="coerce")

        if param.startswith("min_"):
            result = result[numeric_col.fillna(-999999) >= float(value)]
        elif param.startswith("max_"):
            result = result[numeric_col.fillna(999999) <= float(value)]

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Ranking engine
# ─────────────────────────────────────────────────────────────────────────────

def rank_results(df: pd.DataFrame, metric: str, order: str = "desc") -> pd.DataFrame:
    """Rank filtered results by specified metric."""
    ascending = (order == "asc")
    sort_col = metric if metric in df.columns else "composite_score"
    numeric = pd.to_numeric(df[sort_col], errors="coerce")
    df = df.copy()
    df["_sort_val"] = numeric
    df = df.sort_values("_sort_val", ascending=ascending, na_position="last")
    df = df.drop(columns=["_sort_val"])
    df["rank"] = range(1, len(df) + 1)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Run all 6 presets
# ─────────────────────────────────────────────────────────────────────────────

def run_all_presets(universe: pd.DataFrame, config: dict) -> dict[str, pd.DataFrame]:
    """Run all 6 preset screeners. Returns dict of preset_name -> result_df."""
    results = {}
    presets = config.get("presets", {})

    for preset_name, preset_cfg in presets.items():
        filters   = preset_cfg.get("filters", {})
        rank_col  = preset_cfg.get("ranking_metric", "composite_score")
        rank_ord  = preset_cfg.get("ranking_order", "desc")

        filtered = apply_filters(universe, filters)
        ranked   = rank_results(filtered, rank_col, rank_ord)
        results[preset_name] = ranked

        logger.info("Preset '%s': %d companies", preset_name, len(ranked))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Trend filter — consecutive improvement over N years
# ─────────────────────────────────────────────────────────────────────────────

def filter_consecutive_improvement(
    conn: sqlite3.Connection, metric_col: str, n_years: int = 3
) -> pd.DataFrame:
    """
    Return companies where metric_col improved consecutively for n_years.
    Uses full computed_ratios history (not just latest year).
    """
    df = pd.read_sql(
        f"SELECT company_id, year, {metric_col} FROM computed_ratios ORDER BY company_id, year",
        conn
    )
    passing = []
    for company_id, grp in df.groupby("company_id"):
        grp = grp.sort_values("year").reset_index(drop=True)
        vals = pd.to_numeric(grp[metric_col], errors="coerce").dropna()
        if len(vals) < n_years + 1:
            continue
        last_n = vals.iloc[-(n_years + 1):]
        if all(last_n.iloc[i] < last_n.iloc[i + 1] for i in range(len(last_n) - 1)):
            passing.append(company_id)

    return df[df["company_id"].isin(passing)][["company_id"]].drop_duplicates()


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

DISPLAY_COLS = [
    "rank", "company_id", "company_name", "broad_sector", "sub_sector",
    "return_on_equity_pct", "return_on_capital_pct", "net_profit_margin_pct",
    "debt_to_equity", "interest_coverage", "is_debt_free",
    "free_cash_flow_cr", "cfo_to_pat_ratio",
    "revenue_cagr_3yr", "revenue_cagr_5yr", "pat_cagr_5yr",
    "pe_ratio", "pb_ratio", "dividend_yield_pct", "fcf_yield_pct",
    "health_score", "health_band", "composite_score",
    "capital_alloc_pattern", "market_cap_crore",
]


def export_screener_results(
    results: dict[str, pd.DataFrame], output_path: Path
) -> None:
    """Export all preset results to a multi-sheet Excel file."""
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for preset_name, df in results.items():
            if df.empty:
                continue
            cols = [c for c in DISPLAY_COLS if c in df.columns]
            sheet_df = df[cols].copy()

            # Round numeric columns
            for col in sheet_df.select_dtypes(include="number").columns:
                sheet_df[col] = sheet_df[col].round(2)

            # Sheet name max 31 chars
            sheet_name = preset_name[:31]
            sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Basic column width formatting
            ws = writer.sheets[sheet_name]
            for col_cells in ws.columns:
                max_len = max(
                    (len(str(cell.value)) for cell in col_cells if cell.value),
                    default=10
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 30)

    logger.info("Screener output written: %s", output_path)


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_screener() -> dict:
    """Full screener pipeline. Returns results dict."""
    import time
    t0 = time.time()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("=" * 55)
    logger.info("SCREENER ENGINE — Starting")
    logger.info("=" * 55)

    conn    = sqlite3.connect(str(DB_PATH))
    config  = load_config()

    # Build universe
    universe = load_universe(conn)
    universe = add_fcf_yield(universe)
    universe["composite_score"] = compute_composite_score(universe)
    universe = add_sector_ranks(universe)

    # Run all presets
    results = run_all_presets(universe, config)

    # Export to Excel
    out_path = OUTPUT_DIR / "screener_output.xlsx"
    export_screener_results(results, out_path)

    # Also export universe CSV
    universe_cols = [c for c in DISPLAY_COLS if c in universe.columns]
    universe[universe_cols].to_csv(OUTPUT_DIR / "universe_latest.csv", index=False)

    conn.close()
    elapsed = round(time.time() - t0, 2)

    print(f"\n{'='*55}")
    print("SCREENER RESULTS")
    print(f"{'='*55}")
    presets = config.get("presets", {})
    for name, df in results.items():
        label = presets.get(name, {}).get("label", name)
        print(f"  {label:<30} {len(df):>3} companies")
    print(f"\n  Output : {out_path}")
    print(f"  Runtime: {elapsed}s")

    logger.info("SCREENER COMPLETE in %.2fs", elapsed)
    return results


if __name__ == "__main__":
    run_screener()
