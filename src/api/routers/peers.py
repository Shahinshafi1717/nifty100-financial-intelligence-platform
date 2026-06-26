"""src/api/routers/peers.py — Endpoints 11.11–11.12: Peer comparison."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from api.db import get_conn, query, query_one

router = APIRouter(prefix="/api/v1/peers", tags=["Peers"])


@router.get("/{group_name}", summary="Companies in peer group with percentile ranks")
def peer_group(
    group_name: str,
    year: Optional[str] = Query(None),
    conn=Depends(get_conn),
):
    members = query(conn, """
        SELECT pg.company_id, pg.is_benchmark, c.company_name,
               cr.return_on_equity_pct, cr.return_on_capital_pct,
               cr.net_profit_margin_pct, cr.debt_to_equity,
               cr.interest_coverage, cr.free_cash_flow_cr,
               cr.revenue_cagr_5yr, cr.pat_cagr_5yr,
               cr.health_score, cr.health_band
        FROM peer_groups pg
        JOIN companies c ON pg.company_id = c.id
        LEFT JOIN computed_ratios cr ON pg.company_id = cr.company_id
          AND cr.year = (SELECT MAX(year) FROM computed_ratios cr2
                         WHERE cr2.company_id = pg.company_id)
        WHERE pg.peer_group_name = ?
        ORDER BY cr.health_score DESC NULLS LAST
    """, (group_name,))

    if not members:
        raise HTTPException(status_code=404,
                            detail=f"Peer group '{group_name}' not found")

    # Add percentile ranks
    pct_rows = query(conn,
        "SELECT * FROM peer_percentiles WHERE peer_group_name=?",
        (group_name,))
    pct_map: dict[str, dict] = {}
    for row in pct_rows:
        cid = row["company_id"]
        if cid not in pct_map:
            pct_map[cid] = {}
        pct_map[cid][row["metric"]] = round(float(row["percentile_rank"]), 3)

    for m in members:
        m["percentile_ranks"] = pct_map.get(m["company_id"], {})

    return {
        "peer_group_name": group_name,
        "member_count":    len(members),
        "members":         members,
    }
