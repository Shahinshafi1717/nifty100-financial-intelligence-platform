-- =============================================================================
-- schema.sql — Nifty 100 Financial Intelligence Platform
-- SQLite schema for all 10 tables with PK/FK constraints
-- All monetary values in Indian Rupees — Crore (Cr) unless stated
-- =============================================================================

PRAGMA foreign_keys = ON;

-- =============================================================================
-- 1. COMPANIES — Master company reference (92 records)
-- =============================================================================
CREATE TABLE IF NOT EXISTS companies (
    id               TEXT PRIMARY KEY,      -- NSE ticker — normalised uppercase
    company_logo     TEXT,
    company_name     TEXT NOT NULL,
    chart_link       TEXT,
    about_company    TEXT,
    website          TEXT,
    nse_profile      TEXT,
    bse_profile      TEXT,
    face_value       REAL,
    book_value       REAL,
    roce_percentage  REAL,
    roe_percentage   REAL
);

-- =============================================================================
-- 2. PROFITANDLOSS — Annual P&L statements (~1,276 records)
-- =============================================================================
CREATE TABLE IF NOT EXISTS profitandloss (
    id                INTEGER PRIMARY KEY,
    company_id        TEXT NOT NULL REFERENCES companies(id),
    year              TEXT NOT NULL,        -- normalised YYYY-MM
    sales             REAL,
    expenses          REAL,
    operating_profit  REAL,
    opm_percentage    REAL,
    other_income      REAL,
    interest          REAL,
    depreciation      REAL,
    profit_before_tax REAL,
    tax_percentage    REAL,
    net_profit        REAL,
    eps               REAL,
    dividend_payout   REAL,
    UNIQUE(company_id, year)
);

-- =============================================================================
-- 3. BALANCESHEET — Annual balance sheets (~1,312 records)
-- =============================================================================
CREATE TABLE IF NOT EXISTS balancesheet (
    id                INTEGER PRIMARY KEY,
    company_id        TEXT NOT NULL REFERENCES companies(id),
    year              TEXT NOT NULL,        -- normalised YYYY-MM
    equity_capital    REAL,
    reserves          REAL,
    borrowings        REAL,
    other_liabilities REAL,
    total_liabilities REAL,
    fixed_assets      REAL,
    cwip              REAL,
    investments       REAL,
    other_asset       REAL,
    total_assets      REAL,
    UNIQUE(company_id, year)
);

-- =============================================================================
-- 4. CASHFLOW — Annual cash flow statements (~1,187 records)
-- =============================================================================
CREATE TABLE IF NOT EXISTS cashflow (
    id                 INTEGER PRIMARY KEY,
    company_id         TEXT NOT NULL REFERENCES companies(id),
    year               TEXT NOT NULL,       -- normalised YYYY-MM
    operating_activity REAL,
    investing_activity REAL,
    financing_activity REAL,
    net_cash_flow      REAL,
    UNIQUE(company_id, year)
);

-- =============================================================================
-- 5. ANALYSIS — Pre-computed growth text metrics (~20 records, partial)
-- =============================================================================
CREATE TABLE IF NOT EXISTS analysis (
    id                       INTEGER PRIMARY KEY,
    company_id               TEXT NOT NULL REFERENCES companies(id),
    compounded_sales_growth  TEXT,
    compounded_profit_growth TEXT,
    stock_price_cagr         TEXT,
    roe                      TEXT
);

-- =============================================================================
-- 6. DOCUMENTS — Annual report URL repository (~1,585 records)
-- =============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(id),
    year          INTEGER,
    Annual_Report TEXT
);

-- =============================================================================
-- 7. PROSANDCONS — Qualitative investment insights (~16 records, partial)
-- =============================================================================
CREATE TABLE IF NOT EXISTS prosandcons (
    id         INTEGER PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    pros       TEXT,
    cons       TEXT
);

-- =============================================================================
-- 8. SECTORS — Company sector mapping (92 records — supplementary)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sectors (
    company_id           TEXT PRIMARY KEY REFERENCES companies(id),
    broad_sector         TEXT,
    sub_sector           TEXT,
    index_weight_pct     REAL,
    market_cap_category  TEXT
);

-- =============================================================================
-- 9. STOCK_PRICES — Monthly OHLCV price history (5,520 records — supplementary)
-- =============================================================================
CREATE TABLE IF NOT EXISTS stock_prices (
    company_id     TEXT NOT NULL REFERENCES companies(id),
    date           TEXT NOT NULL,
    open_price     REAL,
    high_price     REAL,
    low_price      REAL,
    close_price    REAL,
    volume         INTEGER,
    adjusted_close REAL,
    PRIMARY KEY (company_id, date)
);

-- =============================================================================
-- 10. FINANCIAL_RATIOS — Pre-computed KPI table (~1,184 records — supplementary)
-- =============================================================================
CREATE TABLE IF NOT EXISTS financial_ratios (
    company_id                   TEXT NOT NULL REFERENCES companies(id),
    year                         TEXT NOT NULL,
    net_profit_margin_pct        REAL,
    operating_profit_margin_pct  REAL,
    return_on_equity_pct         REAL,
    debt_to_equity               REAL,
    interest_coverage            REAL,
    asset_turnover               REAL,
    free_cash_flow_cr            REAL,
    capex_cr                     REAL,
    earnings_per_share           REAL,
    book_value_per_share         REAL,
    dividend_payout_ratio_pct    REAL,
    total_debt_cr                REAL,
    cash_from_operations_cr      REAL,
    PRIMARY KEY (company_id, year)
);

-- =============================================================================
-- 11. PEER_GROUPS — Peer comparison groups (56 records — supplementary)
-- =============================================================================
CREATE TABLE IF NOT EXISTS peer_groups (
    id              INTEGER PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    peer_group_name TEXT NOT NULL,
    is_benchmark    INTEGER DEFAULT 0       -- 1 = benchmark company for this group
);

-- =============================================================================
-- 12. MARKET_CAP — Annual valuation multiples (552 records — supplementary)
-- =============================================================================
CREATE TABLE IF NOT EXISTS market_cap (
    company_id             TEXT NOT NULL REFERENCES companies(id),
    year                   INTEGER NOT NULL,
    market_cap_crore       REAL,
    enterprise_value_crore REAL,
    pe_ratio               REAL,
    pb_ratio               REAL,
    ev_ebitda              REAL,
    dividend_yield_pct     REAL,
    PRIMARY KEY (company_id, year)
);
