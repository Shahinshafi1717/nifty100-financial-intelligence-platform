"""src/api/routers/screener.py — Endpoint 11.8: Investment Screener."""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from api.db import get_conn, query

router = APIRouter(prefix="/api/v1/screener", tags=["Screener"])


@router.get("", summary="Multi-criteria investment screener")
def screener(
    min_roe:             Optional[float] = Query(None),
    max_de:              Optional[float] = Query(None),
    min_fcf:             Optional[float] = Query(None),
    min_rev_cagr_5yr:    Optional[float] = Query(None),
    min_pat_cagr_5yr:    Optional[float] = Query(None),
    max_pe:              Optional[float] = Query(None),
    max_pb:              Optional[float] = Query(None),
    min_npm:             Optional[float] = Query(None),
    min_health_score:    Optional[float] = Query(None),
    sector:              Optional[str]   = Query(None),
    market_cap_category: Optional[str]   = Query(None),
    top_n:               int             = Query(50, ge=1, le=92),
    conn=Depends(get_conn),
):
    sql = """
        SELECT cr.company_id, c.company_name, s.broad_sector, s.sub_sector,
               s.market_cap_category,
               cr.return_on_equity_pct, cr.return_on_capital_pct,
               cr.net_profit_margin_pct, cr.debt_to_equity,
               cr.interest_coverage, cr.free_cash_flow_cr,
               cr.revenue_cagr_5yr, cr.pat_cagr_5yr,
               cr.health_score, cr.health_band, cr.capital_alloc_pattern,
               mc.pe_ratio, mc.pb_ratio, mc.dividend_yield_pct, mc.market_cap_crore
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        LEFT JOIN market_cap mc ON cr.company_id = mc.company_id AND mc.year = 2024
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
    """
    params = []

    if min_roe is not None:
        sql += " AND cr.return_on_equity_pct >= ?"; params.append(min_roe)
    if max_de is not None:
        sql += " AND (cr.debt_to_equity <= ? OR cr.debt_to_equity IS NULL)"; params.append(max_de)
    if min_fcf is not None:
        sql += " AND cr.free_cash_flow_cr >= ?"; params.append(min_fcf)
    if min_rev_cagr_5yr is not None:
        sql += " AND cr.revenue_cagr_5yr >= ?"; params.append(min_rev_cagr_5yr)
    if min_pat_cagr_5yr is not None:
        sql += " AND cr.pat_cagr_5yr >= ?"; params.append(min_pat_cagr_5yr)
    if max_pe is not None:
        sql += " AND mc.pe_ratio <= ?"; params.append(max_pe)
    if max_pb is not None:
        sql += " AND mc.pb_ratio <= ?"; params.append(max_pb)
    if min_npm is not None:
        sql += " AND cr.net_profit_margin_pct >= ?"; params.append(min_npm)
    if min_health_score is not None:
        sql += " AND cr.health_score >= ?"; params.append(min_health_score)
    if sector:
        sql += " AND s.broad_sector = ?"; params.append(sector)
    if market_cap_category:
        sql += " AND s.market_cap_category = ?"; params.append(market_cap_category)

    sql += " ORDER BY cr.health_score DESC NULLS LAST"
    sql += f" LIMIT {top_n}"

    rows = query(conn, sql, tuple(params))
    return {"count": len(rows), "filters_applied": {
        "min_roe": min_roe, "max_de": max_de, "min_fcf": min_fcf,
        "min_rev_cagr_5yr": min_rev_cagr_5yr, "sector": sector,
    }, "results": rows}
