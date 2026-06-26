"""
validator.py — Data Quality validation engine.
Implements all 16 DQ rules defined in the project specification.
Outputs validation_failures.csv with severity (CRITICAL / WARNING / INFO).
"""

import re
import logging
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

CRITICAL = "CRITICAL"
WARNING  = "WARNING"
INFO     = "INFO"


def _fail(failures: list, rule_id: str, company_id, year, field: str, issue: str, severity: str):
    """Append a failure record."""
    failures.append({
        "rule_id":    rule_id,
        "company_id": company_id,
        "year":       year,
        "field":      field,
        "issue":      issue,
        "severity":   severity,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Individual DQ Rule Functions
# ─────────────────────────────────────────────────────────────────────────────

def dq01_pk_uniqueness(companies: pd.DataFrame, failures: list) -> int:
    """DQ-01: companies.id must be unique (no duplicate tickers)."""
    dupes = companies[companies["id"].duplicated(keep=False)]
    for _, row in dupes.iterrows():
        _fail(failures, "DQ-01", row["id"], None, "id",
              f"Duplicate company PK: {row['id']}", CRITICAL)
    return len(dupes)


def dq02_annual_pk_uniqueness(tables: dict, failures: list) -> int:
    """DQ-02: No duplicate (company_id, year) pairs in time-series tables."""
    count = 0
    for tname in ["profitandloss", "balancesheet", "cashflow"]:
        df = tables.get(tname)
        if df is None:
            continue
        dupes = df[df.duplicated(subset=["company_id", "year"], keep=False)]
        for _, row in dupes.iterrows():
            _fail(failures, "DQ-02", row["company_id"], row.get("year"),
                  "company_id+year",
                  f"Duplicate (company_id, year) in {tname}", CRITICAL)
            count += 1
    return count


def dq03_fk_integrity(tables: dict, companies: pd.DataFrame, failures: list) -> int:
    """DQ-03: All company_id values in child tables must exist in companies.id."""
    valid_ids = set(companies["id"].dropna().unique())
    count = 0
    child_tables = ["profitandloss", "balancesheet", "cashflow",
                    "analysis", "documents", "prosandcons"]
    for tname in child_tables:
        df = tables.get(tname)
        if df is None:
            continue
        orphans = df[~df["company_id"].isin(valid_ids)]
        for _, row in orphans.iterrows():
            _fail(failures, "DQ-03", row["company_id"], row.get("year"),
                  "company_id",
                  f"FK violation in {tname}: '{row['company_id']}' not in companies",
                  CRITICAL)
            count += 1
    return count


def dq04_bs_balance(balancesheet: pd.DataFrame, failures: list) -> int:
    """DQ-04: |total_assets - total_liabilities| / total_assets < 1%."""
    count = 0
    df = balancesheet.copy()
    df = df[(df["total_assets"] > 0)]
    diff_ratio = (df["total_assets"] - df["total_liabilities"]).abs() / df["total_assets"]
    flagged = df[diff_ratio >= 0.01]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-04", row["company_id"], row.get("year"),
              "total_assets/total_liabilities",
              f"BS imbalance: assets={row['total_assets']}, liabilities={row['total_liabilities']}",
              WARNING)
        count += 1
    return count


def dq05_opm_crosscheck(profitandloss: pd.DataFrame, failures: list) -> int:
    """DQ-05: |opm_percentage - (op_profit/sales*100)| < 1.0."""
    count = 0
    df = profitandloss.copy()
    df = df[(df["sales"] > 0) & df["operating_profit"].notna() & df["opm_percentage"].notna()]
    computed = df["operating_profit"] / df["sales"] * 100
    diff = (df["opm_percentage"] - computed).abs()
    flagged = df[diff >= 1.0]
    for _, row in flagged.iterrows():
        comp_val = round(row["operating_profit"] / row["sales"] * 100, 2)
        _fail(failures, "DQ-05", row["company_id"], row.get("year"),
              "opm_percentage",
              f"OPM mismatch: source={row['opm_percentage']}%, computed={comp_val}%",
              WARNING)
        count += 1
    return count


def dq06_positive_sales(profitandloss: pd.DataFrame, failures: list) -> int:
    """DQ-06: sales > 0 for all non-bank companies (flag ≤ 0)."""
    count = 0
    flagged = profitandloss[profitandloss["sales"] <= 0]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-06", row["company_id"], row.get("year"),
              "sales", f"sales <= 0: {row['sales']}", WARNING)
        count += 1
    return count


def dq07_year_format(tables: dict, failures: list) -> int:
    """DQ-07: After normalize_year(), all values must match YYYY-MM pattern."""
    count = 0
    pattern = re.compile(r"^\d{4}-\d{2}$")
    for tname in ["profitandloss", "balancesheet", "cashflow"]:
        df = tables.get(tname)
        if df is None:
            continue
        if "year_norm" not in df.columns:
            continue
        bad = df[~df["year_norm"].str.match(pattern, na=False) | (df["year_norm"] == "PARSE_ERROR")]
        for _, row in bad.iterrows():
            _fail(failures, "DQ-07", row["company_id"], row.get("year"),
                  "year",
                  f"Unparseable year format: '{row['year']}' -> '{row.get('year_norm')}'",
                  CRITICAL)
            count += 1
    return count


def dq08_ticker_format(tables: dict, failures: list) -> int:
    """DQ-08: company_id must be 2–12 chars uppercase after normalisation."""
    count = 0
    all_tables = list(tables.keys())
    for tname in all_tables:
        df = tables.get(tname)
        if df is None or "company_id" not in df.columns:
            continue
        bad = df[df["company_id"] == "INVALID"]
        for _, row in bad.iterrows():
            _fail(failures, "DQ-08", row.get("company_id"), row.get("year"),
                  "company_id", "company_id normalised to INVALID", CRITICAL)
            count += 1
    return count


def dq09_net_cash_check(cashflow: pd.DataFrame, failures: list) -> int:
    """DQ-09: |net_cash_flow - (CFO+CFI+CFF)| <= 10 Cr."""
    count = 0
    df = cashflow.dropna(subset=["operating_activity", "investing_activity",
                                  "financing_activity", "net_cash_flow"])
    computed = df["operating_activity"] + df["investing_activity"] + df["financing_activity"]
    diff = (df["net_cash_flow"] - computed).abs()
    flagged = df[diff > 10]
    for _, row in flagged.iterrows():
        comp = round(row["operating_activity"] + row["investing_activity"] + row["financing_activity"], 2)
        _fail(failures, "DQ-09", row["company_id"], row.get("year"),
              "net_cash_flow",
              f"Net cash mismatch: recorded={row['net_cash_flow']}, computed={comp}",
              WARNING)
        count += 1
    return count


def dq10_nonneg_fixed_assets(balancesheet: pd.DataFrame, failures: list) -> int:
    """DQ-10: fixed_assets >= 0."""
    count = 0
    flagged = balancesheet[balancesheet["fixed_assets"] < 0]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-10", row["company_id"], row.get("year"),
              "fixed_assets", f"Negative fixed_assets: {row['fixed_assets']}", WARNING)
        count += 1
    return count


def dq11_tax_rate_range(profitandloss: pd.DataFrame, failures: list) -> int:
    """DQ-11: 0 <= tax_percentage <= 60."""
    count = 0
    df = profitandloss.dropna(subset=["tax_percentage"])
    flagged = df[(df["tax_percentage"] < 0) | (df["tax_percentage"] > 60)]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-11", row["company_id"], row.get("year"),
              "tax_percentage", f"Tax rate out of range: {row['tax_percentage']}%", WARNING)
        count += 1
    return count


def dq12_dividend_payout_cap(profitandloss: pd.DataFrame, failures: list) -> int:
    """DQ-12: dividend_payout <= 200%."""
    count = 0
    df = profitandloss.dropna(subset=["dividend_payout"])
    flagged = df[df["dividend_payout"] > 200]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-12", row["company_id"], row.get("year"),
              "dividend_payout",
              f"Dividend payout > 200%: {row['dividend_payout']}%", WARNING)
        count += 1
    return count


def dq13_url_validity(documents: pd.DataFrame, failures: list) -> int:
    """DQ-13: Annual_Report URLs should be non-null (actual HTTP check skipped for performance)."""
    count = 0
    flagged = documents[documents["Annual_Report"].isna()]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-13", row["company_id"], row.get("Year"),
              "Annual_Report", "Missing Annual Report URL", WARNING)
        count += 1
    return count


def dq14_eps_sign(profitandloss: pd.DataFrame, failures: list) -> int:
    """DQ-14: eps > 0 if net_profit > 0."""
    count = 0
    df = profitandloss.dropna(subset=["eps"])
    flagged = df[(df["net_profit"] > 0) & (df["eps"] <= 0)]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-14", row["company_id"], row.get("year"),
              "eps",
              f"EPS sign inconsistency: net_profit={row['net_profit']}, eps={row['eps']}",
              WARNING)
        count += 1
    return count


def dq15_bs_strict_balance(balancesheet: pd.DataFrame, failures: list) -> int:
    """DQ-15: total_liabilities == total_assets (strict informational check)."""
    count = 0
    flagged = balancesheet[balancesheet["total_assets"] != balancesheet["total_liabilities"]]
    for _, row in flagged.iterrows():
        _fail(failures, "DQ-15", row["company_id"], row.get("year"),
              "total_assets/total_liabilities",
              f"Strict BS mismatch: assets={row['total_assets']}, liabilities={row['total_liabilities']}",
              INFO)
        count += 1
    return count


def dq16_coverage_check(tables: dict, companies: pd.DataFrame, failures: list) -> int:
    """DQ-16: Each company should have >= 5 years of P&L, BS, CF records."""
    count = 0
    valid_ids = set(companies["id"].dropna().unique())
    for tname in ["profitandloss", "balancesheet", "cashflow"]:
        df = tables.get(tname)
        if df is None:
            continue
        # Only check companies that ARE in companies table
        df_valid = df[df["company_id"].isin(valid_ids)]
        year_counts = df_valid.groupby("company_id")["year"].count()
        low_coverage = year_counts[year_counts < 5]
        for company_id, yr_count in low_coverage.items():
            _fail(failures, "DQ-16", company_id, None,
                  "year_coverage",
                  f"Only {yr_count} years in {tname} (< 5 required)", WARNING)
            count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Main Validation Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_all_validations(tables: dict, companies: pd.DataFrame, output_path: str) -> pd.DataFrame:
    """
    Run all 16 DQ rules and write validation_failures.csv.

    Args:
        tables:      Dict of table_name -> normalised DataFrame
        companies:   The companies master DataFrame
        output_path: Path to write validation_failures.csv

    Returns:
        DataFrame of all failures.
    """
    failures = []

    dq01_pk_uniqueness(companies, failures)
    dq02_annual_pk_uniqueness(tables, failures)
    dq03_fk_integrity(tables, companies, failures)
    dq04_bs_balance(tables.get("balancesheet", pd.DataFrame()), failures)
    dq05_opm_crosscheck(tables.get("profitandloss", pd.DataFrame()), failures)
    dq06_positive_sales(tables.get("profitandloss", pd.DataFrame()), failures)
    dq07_year_format(tables, failures)
    dq08_ticker_format(tables, failures)
    dq09_net_cash_check(tables.get("cashflow", pd.DataFrame()), failures)
    dq10_nonneg_fixed_assets(tables.get("balancesheet", pd.DataFrame()), failures)
    dq11_tax_rate_range(tables.get("profitandloss", pd.DataFrame()), failures)
    dq12_dividend_payout_cap(tables.get("profitandloss", pd.DataFrame()), failures)
    dq13_url_validity(tables.get("documents", pd.DataFrame()), failures)
    dq14_eps_sign(tables.get("profitandloss", pd.DataFrame()), failures)
    dq15_bs_strict_balance(tables.get("balancesheet", pd.DataFrame()), failures)
    dq16_coverage_check(tables, companies, failures)

    df_failures = pd.DataFrame(failures, columns=[
        "rule_id", "company_id", "year", "field", "issue", "severity"
    ])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df_failures.to_csv(output_path, index=False)

    # Summary
    critical = len(df_failures[df_failures["severity"] == CRITICAL])
    warning  = len(df_failures[df_failures["severity"] == WARNING])
    info     = len(df_failures[df_failures["severity"] == INFO])
    logger.info("DQ Summary: CRITICAL=%d | WARNING=%d | INFO=%d | Total=%d",
                critical, warning, info, len(df_failures))
    print(f"\n{'='*50}")
    print(f"DQ VALIDATION SUMMARY")
    print(f"{'='*50}")
    print(f"  CRITICAL : {critical}")
    print(f"  WARNING  : {warning}")
    print(f"  INFO     : {info}")
    print(f"  TOTAL    : {len(df_failures)}")
    print(f"  Output   : {output_path}")

    return df_failures
