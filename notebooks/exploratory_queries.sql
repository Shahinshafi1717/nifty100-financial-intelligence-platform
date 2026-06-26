-- ============================================================================
-- exploratory_queries.sql — Nifty 100 Financial Intelligence Platform
-- Sprint 1 — Day 07: 10 exploratory queries for data quality review
-- Run after: python src/etl/loader.py
-- Usage: sqlite3 data/nifty100.db < notebooks/exploratory_queries.sql
-- ============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Q1: Row counts for all core tables — verify against load_audit.csv
-- ─────────────────────────────────────────────────────────────────────────────
SELECT 'companies'    AS table_name, COUNT(*) AS row_count FROM companies
UNION ALL
SELECT 'profitandloss',               COUNT(*) FROM profitandloss
UNION ALL
SELECT 'balancesheet',                COUNT(*) FROM balancesheet
UNION ALL
SELECT 'cashflow',                    COUNT(*) FROM cashflow
UNION ALL
SELECT 'analysis',                    COUNT(*) FROM analysis
UNION ALL
SELECT 'documents',                   COUNT(*) FROM documents
UNION ALL
SELECT 'prosandcons',                 COUNT(*) FROM prosandcons;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q2: Year coverage per company in P&L — identify companies with < 5 years
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    company_id,
    COUNT(DISTINCT year) AS year_count,
    MIN(year)            AS earliest_year,
    MAX(year)            AS latest_year,
    CASE WHEN COUNT(DISTINCT year) < 5 THEN 'LOW COVERAGE' ELSE 'OK' END AS coverage_flag
FROM profitandloss
GROUP BY company_id
ORDER BY year_count ASC
LIMIT 20;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q3: Null value counts for key P&L columns
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    SUM(CASE WHEN sales            IS NULL THEN 1 ELSE 0 END) AS null_sales,
    SUM(CASE WHEN operating_profit IS NULL THEN 1 ELSE 0 END) AS null_op_profit,
    SUM(CASE WHEN opm_percentage   IS NULL THEN 1 ELSE 0 END) AS null_opm_pct,
    SUM(CASE WHEN net_profit       IS NULL THEN 1 ELSE 0 END) AS null_net_profit,
    SUM(CASE WHEN eps              IS NULL THEN 1 ELSE 0 END) AS null_eps,
    SUM(CASE WHEN tax_percentage   IS NULL THEN 1 ELSE 0 END) AS null_tax_pct,
    SUM(CASE WHEN dividend_payout  IS NULL THEN 1 ELSE 0 END) AS null_dividend_payout,
    COUNT(*)                                                    AS total_rows
FROM profitandloss;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q4: Companies present in companies table but missing from P&L
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    c.id,
    c.company_name,
    CASE WHEN p.company_id IS NULL THEN 'MISSING FROM P&L' ELSE 'PRESENT' END AS pl_status
FROM companies c
LEFT JOIN (SELECT DISTINCT company_id FROM profitandloss) p ON c.id = p.company_id
WHERE p.company_id IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q5: Balance sheet balance check — assets vs liabilities
-- Flag rows where difference > 1% of total assets
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    company_id,
    year,
    total_assets,
    total_liabilities,
    ROUND(ABS(total_assets - total_liabilities), 2)          AS abs_diff,
    ROUND(ABS(total_assets - total_liabilities) / 
          NULLIF(total_assets, 0) * 100, 4)                  AS diff_pct,
    CASE
        WHEN ABS(total_assets - total_liabilities) /
             NULLIF(total_assets, 0) >= 0.01
        THEN 'FLAG'
        ELSE 'OK'
    END AS balance_flag
FROM balancesheet
WHERE total_assets > 0
ORDER BY diff_pct DESC NULLS LAST
LIMIT 20;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q6: Cash flow quality — companies with CFO < 0 in latest year (distress signal)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    cf.company_id,
    c.company_name,
    cf.year,
    cf.operating_activity  AS cfo,
    cf.investing_activity  AS cfi,
    cf.financing_activity  AS cff,
    cf.net_cash_flow
FROM cashflow cf
JOIN companies c ON cf.company_id = c.id
WHERE cf.operating_activity < 0
  AND cf.year = (SELECT MAX(year) FROM cashflow WHERE company_id = cf.company_id)
ORDER BY cf.operating_activity ASC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q7: Top 5 companies by revenue in latest available P&L year
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    p.company_id,
    c.company_name,
    p.year,
    p.sales           AS revenue_cr,
    p.net_profit      AS pat_cr,
    ROUND(p.net_profit * 100.0 / NULLIF(p.sales, 0), 2) AS npm_pct
FROM profitandloss p
JOIN companies c ON p.company_id = c.id
WHERE p.year = (SELECT MAX(year) FROM profitandloss WHERE company_id = p.company_id)
ORDER BY p.sales DESC
LIMIT 10;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q8: Annual report coverage — companies with missing document links
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    c.id,
    c.company_name,
    COUNT(d.id)                           AS total_docs,
    SUM(CASE WHEN d.Annual_Report IS NULL 
             THEN 1 ELSE 0 END)           AS missing_urls,
    MAX(d.Year)                           AS latest_year
FROM companies c
LEFT JOIN documents d ON c.id = d.company_id
GROUP BY c.id, c.company_name
ORDER BY missing_urls DESC, total_docs ASC
LIMIT 20;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q9: Debt distribution — how many companies are debt-free (borrowings = 0)?
-- Using latest year balance sheet
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    CASE
        WHEN borrowings = 0           THEN 'Debt-Free'
        WHEN borrowings / NULLIF(equity_capital + reserves, 0) < 0.5
                                      THEN 'Low Leverage (D/E < 0.5)'
        WHEN borrowings / NULLIF(equity_capital + reserves, 0) < 1.0
                                      THEN 'Moderate (0.5 <= D/E < 1.0)'
        WHEN borrowings / NULLIF(equity_capital + reserves, 0) < 2.0
                                      THEN 'High (1.0 <= D/E < 2.0)'
        ELSE                               'Very High (D/E >= 2.0)'
    END AS leverage_bucket,
    COUNT(*) AS company_count
FROM balancesheet
WHERE year = (SELECT MAX(year) FROM balancesheet WHERE company_id = balancesheet.company_id)
GROUP BY leverage_bucket
ORDER BY company_count DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Q10: Sample data check — 5 random companies across all tables
-- Verify data consistency: TCS, HDFCBANK, RELIANCE, INFY, TATAMOTORS
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    p.company_id,
    p.year,
    p.sales,
    p.net_profit,
    p.eps,
    b.total_assets,
    b.borrowings,
    b.equity_capital + b.reserves AS total_equity,
    cf.operating_activity         AS cfo,
    cf.net_cash_flow
FROM profitandloss p
JOIN balancesheet b  ON p.company_id = b.company_id  AND p.year = b.year
JOIN cashflow cf     ON p.company_id = cf.company_id AND p.year = cf.year
WHERE p.company_id IN ('TCS', 'HDFCBANK', 'RELIANCE', 'INFY', 'TATAMOTORS')
ORDER BY p.company_id, p.year DESC
LIMIT 25;
