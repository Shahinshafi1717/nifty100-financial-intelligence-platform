"""
utils/db.py — Shared database helpers for the Streamlit dashboard.
All queries are cached with st.cache_data (TTL=600s).
"""

import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[3]
DB_PATH  = BASE_DIR / "data" / "nifty100.db"

def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@st.cache_data(ttl=600)
def load_companies():
    with _conn() as conn:
        return pd.read_sql("""
            SELECT c.id, c.company_name, c.about_company, c.website,
                   c.face_value, c.book_value, c.roce_percentage, c.roe_percentage,
                   s.broad_sector, s.sub_sector, s.market_cap_category
            FROM companies c LEFT JOIN sectors s ON c.id = s.company_id
            ORDER BY c.company_name
        """, conn)

@st.cache_data(ttl=600)
def load_universe_latest():
    with _conn() as conn:
        return pd.read_sql("""
            SELECT cr.*, c.company_name, c.about_company,
                   s.broad_sector, s.sub_sector, s.market_cap_category,
                   mc.pe_ratio, mc.pb_ratio, mc.ev_ebitda,
                   mc.dividend_yield_pct, mc.market_cap_crore
            FROM computed_ratios cr
            JOIN companies c ON cr.company_id = c.id
            LEFT JOIN sectors s ON cr.company_id = s.company_id
            LEFT JOIN market_cap mc ON cr.company_id = mc.company_id AND mc.year = 2024
            WHERE cr.year = (
                SELECT MAX(year) FROM computed_ratios cr2 WHERE cr2.company_id = cr.company_id
            )
            ORDER BY cr.company_id
        """, conn)

@st.cache_data(ttl=600)
def load_pl_history(company_id):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM profitandloss WHERE company_id=? ORDER BY year",
                           conn, params=(company_id,))

@st.cache_data(ttl=600)
def load_bs_history(company_id):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM balancesheet WHERE company_id=? ORDER BY year",
                           conn, params=(company_id,))

@st.cache_data(ttl=600)
def load_cf_history(company_id):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM cashflow WHERE company_id=? ORDER BY year",
                           conn, params=(company_id,))

@st.cache_data(ttl=600)
def load_ratios_history(company_id):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM computed_ratios WHERE company_id=? ORDER BY year",
                           conn, params=(company_id,))

@st.cache_data(ttl=600)
def load_market_cap_history(company_id):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM market_cap WHERE company_id=? ORDER BY year",
                           conn, params=(company_id,))

@st.cache_data(ttl=600)
def load_stock_prices(company_id):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM stock_prices WHERE company_id=? ORDER BY date",
                           conn, params=(company_id,))

@st.cache_data(ttl=600)
def load_peer_group_data(group_name):
    with _conn() as conn:
        return pd.read_sql("""
            SELECT pg.company_id, pg.is_benchmark,
                   cr.return_on_equity_pct, cr.return_on_capital_pct,
                   cr.net_profit_margin_pct, cr.operating_profit_margin_pct,
                   cr.debt_to_equity, cr.interest_coverage,
                   cr.free_cash_flow_cr, cr.revenue_cagr_5yr,
                   cr.pat_cagr_5yr, cr.eps_cagr_5yr,
                   cr.health_score, cr.health_band, cr.capital_alloc_pattern,
                   c.company_name
            FROM peer_groups pg
            JOIN computed_ratios cr ON pg.company_id = cr.company_id
            JOIN companies c ON pg.company_id = c.id
            WHERE pg.peer_group_name = ?
              AND cr.year = (
                  SELECT MAX(year) FROM computed_ratios cr2
                  WHERE cr2.company_id = cr.company_id
              )
        """, conn, params=(group_name,))

@st.cache_data(ttl=600)
def load_peer_percentiles(group_name):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM peer_percentiles WHERE peer_group_name=?",
                           conn, params=(group_name,))

@st.cache_data(ttl=600)
def load_documents(company_id):
    with _conn() as conn:
        return pd.read_sql("SELECT * FROM documents WHERE company_id=? ORDER BY year DESC",
                           conn, params=(company_id,))

@st.cache_data(ttl=600)
def load_sector_summary():
    with _conn() as conn:
        return pd.read_sql("""
            SELECT s.broad_sector,
                   COUNT(DISTINCT cr.company_id) AS company_count,
                   ROUND(AVG(cr.return_on_equity_pct),1) AS median_roe,
                   ROUND(AVG(cr.net_profit_margin_pct),1) AS median_npm,
                   ROUND(AVG(cr.debt_to_equity),2) AS median_de,
                   ROUND(AVG(mc.pe_ratio),1) AS median_pe,
                   ROUND(AVG(cr.health_score),1) AS avg_health,
                   ROUND(SUM(mc.market_cap_crore)/1e5,1) AS total_mktcap_lakh_cr
            FROM computed_ratios cr
            JOIN sectors s ON cr.company_id = s.company_id
            LEFT JOIN market_cap mc ON cr.company_id = mc.company_id AND mc.year = 2024
            WHERE cr.year = (
                SELECT MAX(year) FROM computed_ratios cr2 WHERE cr2.company_id = cr.company_id
            )
            GROUP BY s.broad_sector ORDER BY company_count DESC
        """, conn)

@st.cache_data(ttl=600)
def load_all_peer_groups():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT peer_group_name FROM peer_groups ORDER BY peer_group_name"
        ).fetchall()
        return [r[0] for r in rows]

@st.cache_data(ttl=600)
def load_capital_allocation_summary():
    with _conn() as conn:
        return pd.read_sql("""
            SELECT cr.company_id, c.company_name, s.broad_sector,
                   cr.capital_alloc_pattern, cr.cfo_sign, cr.cfi_sign, cr.cff_sign,
                   cr.free_cash_flow_cr, cr.health_score
            FROM computed_ratios cr
            JOIN companies c ON cr.company_id = c.id
            LEFT JOIN sectors s ON cr.company_id = s.company_id
            WHERE cr.year = (
                SELECT MAX(year) FROM computed_ratios cr2 WHERE cr2.company_id = cr.company_id
            )
            ORDER BY cr.company_id
        """, conn)

def get_db_row_counts():
    tables = ["companies","profitandloss","balancesheet","cashflow","analysis",
              "documents","prosandcons","sectors","stock_prices","market_cap",
              "financial_ratios","peer_groups","computed_ratios"]
    counts = {}
    with _conn() as conn:
        for t in tables:
            try:
                counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                counts[t] = -1
    return counts
