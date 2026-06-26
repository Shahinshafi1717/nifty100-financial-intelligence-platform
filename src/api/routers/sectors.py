"""src/api/routers/sectors.py — Endpoints 11.9–11.10: Sector analytics."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from api.db import get_conn, query, query_one

router = APIRouter(prefix="/api/v1/sectors", tags=["Sectors"])


@router.get("", summary="All sectors with company count and median KPIs")
def list_sectors(conn=Depends(get_conn)):
    return query(conn, """
        SELECT s.broad_sector,
               COUNT(DISTINCT cr.company_id)          AS company_count,
               ROUND(AVG(cr.return_on_equity_pct),1)  AS median_roe,
               ROUND(AVG(cr.net_profit_margin_pct),1) AS median_npm,
               ROUND(AVG(cr.debt_to_equity),2)        AS median_de,
               ROUND(AVG(mc.pe_ratio),1)              AS median_pe,
               ROUND(AVG(cr.health_score),1)          AS avg_health
        FROM computed_ratios cr
        JOIN sectors s ON cr.company_id = s.company_id
        LEFT JOIN market_cap mc ON cr.company_id = mc.company_id AND mc.year = 2024
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
        GROUP BY s.broad_sector
        ORDER BY company_count DESC
    """)


@router.get("/{sector}/companies",
            summary="All companies in a sector with KPI summary")
def sector_companies(
    sector: str,
    year: Optional[str] = Query(None, description="Filter by year (default=latest)"),
    conn=Depends(get_conn),
):
    rows = query(conn, """
        SELECT cr.company_id, c.company_name, s.sub_sector,
               cr.return_on_equity_pct, cr.net_profit_margin_pct,
               cr.debt_to_equity, cr.free_cash_flow_cr,
               cr.revenue_cagr_5yr, cr.health_score, cr.health_band,
               mc.pe_ratio, mc.market_cap_crore
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        JOIN sectors s ON cr.company_id = s.company_id
        LEFT JOIN market_cap mc ON cr.company_id = mc.company_id AND mc.year = 2024
        WHERE s.broad_sector = ?
          AND cr.year = (
              SELECT MAX(year) FROM computed_ratios cr2
              WHERE cr2.company_id = cr.company_id
          )
        ORDER BY cr.health_score DESC NULLS LAST
    """, (sector,))

    if not rows:
        raise HTTPException(status_code=404,
                            detail=f"Sector '{sector}' not found or has no data")
    return {"sector": sector, "count": len(rows), "companies": rows}
