"""src/api/routers/reports.py — Endpoints 11.13–11.14: Market cap & portfolio stats."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from api.db import get_conn, query, query_one

router = APIRouter(prefix="/api/v1", tags=["Reports & Valuation"])


@router.get("/market-cap/{ticker}",
            summary="Historical valuation multiples (P/E, P/B, EV/EBITDA)")
def market_cap_history(
    ticker: str,
    from_year: Optional[int] = Query(None),
    to_year:   Optional[int] = Query(None),
    conn=Depends(get_conn),
):
    ticker = ticker.upper()
    # Verify company exists
    if not query_one(conn, "SELECT id FROM companies WHERE id=?", (ticker,)):
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")

    sql = "SELECT * FROM market_cap WHERE company_id=?"
    params = [ticker]
    if from_year:
        sql += " AND year >= ?"; params.append(from_year)
    if to_year:
        sql += " AND year <= ?"; params.append(to_year)
    sql += " ORDER BY year"
    rows = query(conn, sql, tuple(params))
    if not rows:
        raise HTTPException(status_code=404,
                            detail=f"No market cap data for '{ticker}'")
    return rows


@router.get("/portfolio/stats",
            summary="Portfolio-level P10–P90 statistics for all KPIs")
def portfolio_stats(
    year: Optional[str] = Query(None, description="Year (default=latest)"),
    conn=Depends(get_conn),
):
    # Try from pre-computed table first (faster)
    rows = query(conn, "SELECT * FROM portfolio_stats", ())
    if rows:
        return {"source": "pre-computed", "stats": rows}

    # Fallback: compute on-the-fly
    kpis = ["return_on_equity_pct", "return_on_capital_pct",
            "net_profit_margin_pct", "debt_to_equity",
            "interest_coverage", "free_cash_flow_cr",
            "revenue_cagr_5yr", "pat_cagr_5yr", "health_score"]
    results = []
    for kpi in kpis:
        vals = [
            r[kpi] for r in query(conn, f"""
                SELECT {kpi} FROM computed_ratios
                WHERE year = (SELECT MAX(year) FROM computed_ratios cr2
                              WHERE cr2.company_id = computed_ratios.company_id)
                  AND {kpi} IS NOT NULL
            """, ())
            if r.get(kpi) is not None
        ]
        if vals:
            import statistics
            sorted_vals = sorted(vals)
            n = len(sorted_vals)
            def pct(p):
                idx = min(int(p/100 * n), n-1)
                return round(sorted_vals[idx], 2)
            results.append({
                "metric": kpi,
                "P10": pct(10), "P25": pct(25), "P50": pct(50),
                "P75": pct(75), "P90": pct(90),
                "mean": round(statistics.mean(vals), 2),
                "std":  round(statistics.stdev(vals), 2) if len(vals) > 1 else 0,
                "count": n,
            })
    return {"source": "computed", "stats": results}
