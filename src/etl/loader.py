"""
loader.py — Nifty 100 Financial Intelligence Platform
Main ETL loader: reads all 7 core Excel files, normalises fields,
runs DQ validation, and loads into SQLite (nifty100.db).

Usage:
    python src/etl/loader.py
    OR: make load
"""

import sqlite3
import logging
import time
import csv
from pathlib import Path
from datetime import datetime

import pandas as pd

from normaliser import normalize_year, normalize_ticker
from validator import run_all_validations

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).resolve().parents[2]   # project root
RAW_DIR    = BASE_DIR / "data" / "raw"
SUPP_DIR   = BASE_DIR / "data" / "supporting"
DB_PATH    = BASE_DIR / "data" / "nifty100.db"
OUTPUT_DIR = BASE_DIR / "output"
SCHEMA_SQL = BASE_DIR / "db" / "schema.sql"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AUDIT_CSV      = OUTPUT_DIR / "load_audit.csv"
FAILURES_CSV   = OUTPUT_DIR / "validation_failures.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("loader")

# Orphan company IDs discovered in source data (not in companies master)
# These rows will be rejected at DQ-03; listed here for transparency
KNOWN_ORPHAN_IDS = {
    "WIPRO", "ULTRACEMCO", "VEDL", "UNIONBANK",
    "ZYDUSLIFE", "UNITDSPR", "VBL", "ZOMATO"
}

# Special year values to drop entirely (TTM = Trailing Twelve Months, not annual)
DROP_YEAR_VALUES = {"TTM", "PARSE_ERROR"}

# Partial-year labels to drop (9-month, 15-month transitional periods)
DROP_YEAR_SUFFIXES = ("9m", "15", "9M")


# ─────────────────────────────────────────────────────────────────────────────
# Excel Readers
# ─────────────────────────────────────────────────────────────────────────────

def read_core_excel(path: Path, table_name: str) -> pd.DataFrame:
    """
    Read a core dataset Excel file using header=1 (row 0 = metadata, row 1 = headers).
    """
    logger.info("Reading %s from %s", table_name, path.name)
    df = pd.read_excel(path, header=1)
    logger.info("  Raw rows: %d | Cols: %s", len(df), list(df.columns))
    return df


def read_supp_excel(path: Path, table_name: str) -> pd.DataFrame:
    """
    Read a supplementary dataset Excel file using header=0.
    """
    logger.info("Reading %s from %s", table_name, path.name)
    df = pd.read_excel(path, header=0)
    logger.info("  Raw rows: %d | Cols: %s", len(df), list(df.columns))
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Per-Table Normalisation
# ─────────────────────────────────────────────────────────────────────────────

def normalise_companies(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise companies master table."""
    df = df.copy()
    df["id"] = df["id"].apply(normalize_ticker)
    # Strip embedded newlines from company_name
    df["company_name"] = df["company_name"].astype(str).str.replace(r"\n", " ", regex=True).str.strip()
    return df


def _normalise_timeseries(df: pd.DataFrame, table_name: str,
                           valid_ids: set) -> tuple[pd.DataFrame, list]:
    """
    Common normalisation for P&L, Balance Sheet, Cash Flow tables:
      1. Normalise company_id
      2. Normalise year
      3. Drop orphan company_ids
      4. Drop unparseable / partial year rows
      5. Deduplicate (company_id, year) — keep last
    Returns (cleaned_df, rejected_rows)
    """
    df = df.copy()
    rejected = []

    # 1. Normalise ticker
    df["company_id"] = df["company_id"].apply(normalize_ticker)

    # 2. Normalise year — store original for logging
    df["year_raw"] = df["year"].astype(str)
    df["year_norm"] = df["year_raw"].apply(normalize_year)

    # 3. Drop orphan company_ids
    orphan_mask = ~df["company_id"].isin(valid_ids)
    orphans = df[orphan_mask].copy()
    for _, row in orphans.iterrows():
        rejected.append({
            "table": table_name,
            "company_id": row["company_id"],
            "year_raw": row["year_raw"],
            "reason": f"FK violation — company_id '{row['company_id']}' not in companies",
        })
    df = df[~orphan_mask]

    # 4. Drop unparseable / TTM / partial year rows
    bad_year_mask = (df["year_norm"].isin(DROP_YEAR_VALUES))
    bad_rows = df[bad_year_mask].copy()
    for _, row in bad_rows.iterrows():
        rejected.append({
            "table": table_name,
            "company_id": row["company_id"],
            "year_raw": row["year_raw"],
            "reason": f"Unparseable or excluded year: '{row['year_raw']}' -> '{row['year_norm']}'",
        })
    df = df[~bad_year_mask]

    # 5. Replace year column with normalised value
    df["year"] = df["year_norm"]
    df = df.drop(columns=["year_raw", "year_norm"])

    # 6. Deduplicate (company_id, year) — keep last occurrence
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["company_id", "year"], keep="last")
    duped = before_dedup - len(df)
    if duped > 0:
        logger.warning("  %s: removed %d duplicate (company_id, year) rows", table_name, duped)

    return df, rejected


def normalise_profitandloss(df: pd.DataFrame, valid_ids: set) -> tuple[pd.DataFrame, list]:
    return _normalise_timeseries(df, "profitandloss", valid_ids)


def normalise_balancesheet(df: pd.DataFrame, valid_ids: set) -> tuple[pd.DataFrame, list]:
    # Fix negative fixed_assets (coerce to 0 per DQ-10)
    df = df.copy()
    neg_fa = df["fixed_assets"] < 0
    if neg_fa.any():
        logger.warning("  balancesheet: coercing %d negative fixed_assets to 0", neg_fa.sum())
        df.loc[neg_fa, "fixed_assets"] = 0
    return _normalise_timeseries(df, "balancesheet", valid_ids)


def normalise_cashflow(df: pd.DataFrame, valid_ids: set) -> tuple[pd.DataFrame, list]:
    df, rejected = _normalise_timeseries(df, "cashflow", valid_ids)
    # Recompute net_cash_flow where mismatch > 10 Cr (DQ-09 fix)
    mask = df[["operating_activity", "investing_activity", "financing_activity", "net_cash_flow"]].notna().all(axis=1)
    computed = df.loc[mask, "operating_activity"] + df.loc[mask, "investing_activity"] + df.loc[mask, "financing_activity"]
    mismatch = (df.loc[mask, "net_cash_flow"] - computed).abs() > 10
    if mismatch.any():
        logger.warning("  cashflow: recomputing net_cash_flow for %d rows with mismatch > 10 Cr", mismatch.sum())
        df.loc[mask & mismatch.reindex(df.index, fill_value=False), "net_cash_flow"] = computed[mismatch]
    return df, rejected


def normalise_analysis(df: pd.DataFrame, valid_ids: set) -> tuple[pd.DataFrame, list]:
    df = df.copy()
    rejected = []
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    orphan_mask = ~df["company_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        rejected.append({"table": "analysis", "company_id": row["company_id"],
                         "year_raw": None, "reason": "FK violation"})
    return df[~orphan_mask], rejected


def normalise_documents(df: pd.DataFrame, valid_ids: set) -> tuple[pd.DataFrame, list]:
    df = df.copy()
    rejected = []
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    orphan_mask = ~df["company_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        rejected.append({"table": "documents", "company_id": row["company_id"],
                         "year_raw": None, "reason": "FK violation"})
    df = df[~orphan_mask]
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    return df, rejected


def normalise_prosandcons(df: pd.DataFrame, valid_ids: set) -> tuple[pd.DataFrame, list]:
    df = df.copy()
    rejected = []
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    orphan_mask = ~df["company_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        rejected.append({"table": "prosandcons", "company_id": row["company_id"],
                         "year_raw": None, "reason": "FK violation"})
    return df[~orphan_mask], rejected


# ─────────────────────────────────────────────────────────────────────────────
# SQLite Helpers
# ─────────────────────────────────────────────────────────────────────────────

def init_db(db_path: Path, schema_path: Path) -> sqlite3.Connection:
    """Create SQLite DB and run schema.sql."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = schema_path.read_text()
    conn.executescript(schema_sql)
    conn.commit()
    logger.info("Database initialised: %s", db_path)
    return conn


def load_table(conn: sqlite3.Connection, df: pd.DataFrame,
               table_name: str, if_exists: str = "append") -> int:
    """Write DataFrame to SQLite table. Returns rows written."""
    df.to_sql(table_name, conn, if_exists=if_exists, index=False)
    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    logger.info("  Loaded %s: %d rows in DB", table_name, count)
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Load Audit
# ─────────────────────────────────────────────────────────────────────────────

def write_audit(audit_rows: list):
    """Write load_audit.csv."""
    fieldnames = ["table", "source_file", "rows_in", "rows_out",
                  "rows_rejected", "status", "timestamp", "runtime_s"]
    with open(AUDIT_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(audit_rows)
    logger.info("Audit written: %s", AUDIT_CSV)


# ─────────────────────────────────────────────────────────────────────────────
# Main ETL Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_etl():
    """Full ETL pipeline for all 7 core datasets."""
    overall_start = time.time()
    audit_rows = []
    all_rejected = []

    logger.info("=" * 60)
    logger.info("NIFTY 100 ETL — Starting full load")
    logger.info("=" * 60)

    # ── Init DB ──────────────────────────────────────────────────────────────
    conn = init_db(DB_PATH, SCHEMA_SQL)

    # Clear existing data for idempotent re-runs
    tables_order = [
        "financial_ratios", "peer_groups", "market_cap", "stock_prices",
        "sectors", "prosandcons", "documents", "analysis",
        "cashflow", "balancesheet", "profitandloss", "companies"
    ]
    for t in tables_order:
        try:
            conn.execute(f"DELETE FROM {t}")
        except Exception:
            pass
    conn.commit()

    # ── 1. COMPANIES (must load first — parent table) ─────────────────────
    t0 = time.time()
    raw_companies = read_core_excel(RAW_DIR / "companies.xlsx", "companies")
    rows_in = len(raw_companies)
    companies = normalise_companies(raw_companies)
    # Drop any INVALID tickers
    companies = companies[companies["id"] != "INVALID"]
    rows_out = load_table(conn, companies, "companies", if_exists="append")
    conn.commit()
    audit_rows.append({
        "table": "companies", "source_file": "companies.xlsx",
        "rows_in": rows_in, "rows_out": rows_out,
        "rows_rejected": rows_in - rows_out,
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)
    })

    valid_ids = set(companies["id"].unique())
    logger.info("  Valid company IDs loaded: %d", len(valid_ids))

    # ── 2. PROFIT & LOSS ──────────────────────────────────────────────────
    t0 = time.time()
    raw_pl = read_core_excel(RAW_DIR / "profitandloss.xlsx", "profitandloss")
    rows_in = len(raw_pl)
    pl, rejected = normalise_profitandloss(raw_pl, valid_ids)
    all_rejected.extend(rejected)
    rows_out = load_table(conn, pl, "profitandloss", if_exists="append")
    conn.commit()
    audit_rows.append({
        "table": "profitandloss", "source_file": "profitandloss.xlsx",
        "rows_in": rows_in, "rows_out": rows_out,
        "rows_rejected": len(rejected),
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)
    })

    # ── 3. BALANCE SHEET ─────────────────────────────────────────────────
    t0 = time.time()
    raw_bs = read_core_excel(RAW_DIR / "balancesheet.xlsx", "balancesheet")
    rows_in = len(raw_bs)
    bs, rejected = normalise_balancesheet(raw_bs, valid_ids)
    all_rejected.extend(rejected)
    rows_out = load_table(conn, bs, "balancesheet", if_exists="append")
    conn.commit()
    audit_rows.append({
        "table": "balancesheet", "source_file": "balancesheet.xlsx",
        "rows_in": rows_in, "rows_out": rows_out,
        "rows_rejected": len(rejected),
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)
    })

    # ── 4. CASH FLOW ─────────────────────────────────────────────────────
    t0 = time.time()
    raw_cf = read_core_excel(RAW_DIR / "cashflow.xlsx", "cashflow")
    rows_in = len(raw_cf)
    cf, rejected = normalise_cashflow(raw_cf, valid_ids)
    all_rejected.extend(rejected)
    rows_out = load_table(conn, cf, "cashflow", if_exists="append")
    conn.commit()
    audit_rows.append({
        "table": "cashflow", "source_file": "cashflow.xlsx",
        "rows_in": rows_in, "rows_out": rows_out,
        "rows_rejected": len(rejected),
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)
    })

    # ── 5. ANALYSIS ───────────────────────────────────────────────────────
    t0 = time.time()
    raw_an = read_core_excel(RAW_DIR / "analysis.xlsx", "analysis")
    rows_in = len(raw_an)
    an, rejected = normalise_analysis(raw_an, valid_ids)
    all_rejected.extend(rejected)
    rows_out = load_table(conn, an, "analysis", if_exists="append")
    conn.commit()
    audit_rows.append({
        "table": "analysis", "source_file": "analysis.xlsx",
        "rows_in": rows_in, "rows_out": rows_out,
        "rows_rejected": len(rejected),
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)
    })

    # ── 6. DOCUMENTS ─────────────────────────────────────────────────────
    t0 = time.time()
    raw_doc = read_core_excel(RAW_DIR / "documents.xlsx", "documents")
    rows_in = len(raw_doc)
    doc, rejected = normalise_documents(raw_doc, valid_ids)
    all_rejected.extend(rejected)
    rows_out = load_table(conn, doc, "documents", if_exists="append")
    conn.commit()
    audit_rows.append({
        "table": "documents", "source_file": "documents.xlsx",
        "rows_in": rows_in, "rows_out": rows_out,
        "rows_rejected": len(rejected),
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)
    })

    # ── 7. PROS & CONS ───────────────────────────────────────────────────
    t0 = time.time()
    raw_pc = read_core_excel(RAW_DIR / "prosandcons.xlsx", "prosandcons")
    rows_in = len(raw_pc)
    pc, rejected = normalise_prosandcons(raw_pc, valid_ids)
    all_rejected.extend(rejected)
    rows_out = load_table(conn, pc, "prosandcons", if_exists="append")
    conn.commit()
    audit_rows.append({
        "table": "prosandcons", "source_file": "prosandcons.xlsx",
        "rows_in": rows_in, "rows_out": rows_out,
        "rows_rejected": len(rejected),
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)
    })

    # ── Run FK check ──────────────────────────────────────────────────────
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_violations:
        logger.error("FK CHECK FAILED: %d violations!", len(fk_violations))
        for v in fk_violations:
            logger.error("  %s", v)
    else:
        logger.info("FK CHECK PASSED — 0 violations")

    # ── DQ Validation ─────────────────────────────────────────────────────
    tables_for_dq = {
        "profitandloss": pl,
        "balancesheet":  bs,
        "cashflow":      cf,
        "analysis":      an,
        "documents":     doc,
        "prosandcons":   pc,
    }
    # Add year_norm for DQ-07 (year format check after normalisation)
    for tname, df_t in [("profitandloss", pl), ("balancesheet", bs), ("cashflow", cf)]:
        df_t_copy = df_t.copy()
        df_t_copy["year_norm"] = df_t_copy["year"]  # already normalised
        tables_for_dq[tname] = df_t_copy

    run_all_validations(tables_for_dq, companies, str(FAILURES_CSV))

    # ── Write audit ───────────────────────────────────────────────────────
    write_audit(audit_rows)

    # ── Final Summary ──────────────────────────────────────────────────────
    total_time = round(time.time() - overall_start, 2)
    logger.info("=" * 60)
    logger.info("ETL COMPLETE in %.2fs", total_time)
    logger.info("DB: %s", DB_PATH)

    print("\n" + "=" * 60)
    print("LOAD AUDIT SUMMARY")
    print("=" * 60)
    print(f"{'Table':<20} {'In':>6} {'Out':>6} {'Rejected':>8}")
    print("-" * 45)
    for row in audit_rows:
        print(f"{row['table']:<20} {row['rows_in']:>6} {row['rows_out']:>6} {row['rows_rejected']:>8}")
    print("=" * 60)
    print(f"Total runtime: {total_time}s")
    print(f"Audit CSV   : {AUDIT_CSV}")
    print(f"Failures CSV: {FAILURES_CSV}")
    print(f"Database    : {DB_PATH}")

    conn.close()
    return audit_rows


if __name__ == "__main__":
    run_etl()


# =============================================================================
# SUPPLEMENTARY FILE LOADERS  (added Sprint 1 Day 05 — supp datasets)
# =============================================================================

def load_supplementary_files(conn: sqlite3.Connection) -> list:
    """
    Load all 5 supplementary datasets into SQLite.
    Supplementary files use header=0 (no metadata row).
    Returns list of audit rows.
    """
    audit_rows = []
    companies_ids = set(
        r[0] for r in conn.execute("SELECT id FROM companies").fetchall()
    )

    # ── sectors ──────────────────────────────────────────────────────────────
    t0 = time.time()
    df = pd.read_excel(SUPP_DIR / "sectors.xlsx", header=0)
    rows_in = len(df)
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    df = df[df["company_id"].isin(companies_ids)]
    df = df.drop_duplicates(subset=["company_id"], keep="last")
    cols = ["company_id", "broad_sector", "sub_sector",
            "index_weight_pct", "market_cap_category"]
    conn.execute("DELETE FROM sectors")
    df[cols].to_sql("sectors", conn, if_exists="append", index=False)
    conn.commit()
    rows_out = conn.execute("SELECT COUNT(*) FROM sectors").fetchone()[0]
    audit_rows.append({"table": "sectors", "source_file": "sectors.xlsx",
        "rows_in": rows_in, "rows_out": rows_out, "rows_rejected": rows_in - rows_out,
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)})
    logger.info("Loaded sectors: %d rows", rows_out)

    # ── stock_prices ─────────────────────────────────────────────────────────
    t0 = time.time()
    df = pd.read_excel(SUPP_DIR / "stock_prices.xlsx", header=0)
    rows_in = len(df)
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    df = df[df["company_id"].isin(companies_ids)]
    df = df.drop_duplicates(subset=["company_id", "date"], keep="last")
    cols = ["company_id", "date", "open_price", "high_price",
            "low_price", "close_price", "volume", "adjusted_close"]
    conn.execute("DELETE FROM stock_prices")
    df[cols].to_sql("stock_prices", conn, if_exists="append", index=False)
    conn.commit()
    rows_out = conn.execute("SELECT COUNT(*) FROM stock_prices").fetchone()[0]
    audit_rows.append({"table": "stock_prices", "source_file": "stock_prices.xlsx",
        "rows_in": rows_in, "rows_out": rows_out, "rows_rejected": rows_in - rows_out,
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)})
    logger.info("Loaded stock_prices: %d rows", rows_out)

    # ── market_cap ───────────────────────────────────────────────────────────
    t0 = time.time()
    df = pd.read_excel(SUPP_DIR / "market_cap.xlsx", header=0)
    rows_in = len(df)
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    df = df[df["company_id"].isin(companies_ids)]
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["year"])
    df = df.drop_duplicates(subset=["company_id", "year"], keep="last")
    cols = ["company_id", "year", "market_cap_crore", "enterprise_value_crore",
            "pe_ratio", "pb_ratio", "ev_ebitda", "dividend_yield_pct"]
    conn.execute("DELETE FROM market_cap")
    df[cols].to_sql("market_cap", conn, if_exists="append", index=False)
    conn.commit()
    rows_out = conn.execute("SELECT COUNT(*) FROM market_cap").fetchone()[0]
    audit_rows.append({"table": "market_cap", "source_file": "market_cap.xlsx",
        "rows_in": rows_in, "rows_out": rows_out, "rows_rejected": rows_in - rows_out,
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)})
    logger.info("Loaded market_cap: %d rows", rows_out)

    # ── financial_ratios (pre-computed — deduplicate, normalise year) ────────
    t0 = time.time()
    df = pd.read_excel(SUPP_DIR / "financial_ratios.xlsx", header=0)
    rows_in = len(df)
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    df = df[df["company_id"].isin(companies_ids)]
    df["year"] = df["year"].astype(str).apply(normalize_year)
    df = df[df["year"] != "PARSE_ERROR"]
    df = df.drop_duplicates(subset=["company_id", "year"], keep="last")
    cols = ["company_id", "year", "net_profit_margin_pct", "operating_profit_margin_pct",
            "return_on_equity_pct", "debt_to_equity", "interest_coverage",
            "asset_turnover", "free_cash_flow_cr", "capex_cr", "earnings_per_share",
            "book_value_per_share", "dividend_payout_ratio_pct",
            "total_debt_cr", "cash_from_operations_cr"]
    conn.execute("DELETE FROM financial_ratios")
    df[cols].to_sql("financial_ratios", conn, if_exists="append", index=False)
    conn.commit()
    rows_out = conn.execute("SELECT COUNT(*) FROM financial_ratios").fetchone()[0]
    audit_rows.append({"table": "financial_ratios", "source_file": "financial_ratios.xlsx",
        "rows_in": rows_in, "rows_out": rows_out, "rows_rejected": rows_in - rows_out,
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)})
    logger.info("Loaded financial_ratios (pre-computed): %d rows", rows_out)

    # ── peer_groups ──────────────────────────────────────────────────────────
    t0 = time.time()
    df = pd.read_excel(SUPP_DIR / "peer_groups.xlsx", header=0)
    rows_in = len(df)
    df["company_id"] = df["company_id"].apply(normalize_ticker)
    df = df[df["company_id"].isin(companies_ids)]
    df["is_benchmark"] = df["is_benchmark"].astype(bool).astype(int)
    df = df.drop_duplicates(subset=["peer_group_name", "company_id"], keep="last")
    cols = ["peer_group_name", "company_id", "is_benchmark"]
    conn.execute("DELETE FROM peer_groups")
    df[cols].to_sql("peer_groups", conn, if_exists="append", index=False)
    conn.commit()
    rows_out = conn.execute("SELECT COUNT(*) FROM peer_groups").fetchone()[0]
    audit_rows.append({"table": "peer_groups", "source_file": "peer_groups.xlsx",
        "rows_in": rows_in, "rows_out": rows_out, "rows_rejected": rows_in - rows_out,
        "status": "OK", "timestamp": datetime.now().isoformat(),
        "runtime_s": round(time.time() - t0, 2)})
    logger.info("Loaded peer_groups: %d rows", rows_out)

    return audit_rows


if __name__ == "__main__":
    pass  # run_etl() called above already; supp loaded separately
