"""
src/api/routers/companies.py
Endpoints 11.1 – 11.7: company list, profile, P&L, BS, CF, ratios, tearsheet.
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from api.db import get_conn, query, query_one

router = APIRouter(prefix="/api/v1/companies", tags=["Companies"])

BASE_DIR    = Path(__file__).resolve().parents[3]
TEARSHEETS  = BASE_DIR / "reports" / "tearsheets"


# ── 11.1 List all companies ──────────────────────────────────────────────────
@router.get("", summary="List all 92 companies")
def list_companies(
    sector: Optional[str] = Query(None, description="Filter by broad_sector"),
    market_cap_category: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by name or ticker"),
    conn=Depends(get_conn),
):
    sql = """
        SELECT c.id, c.company_name, s.broad_sector, s.sub_sector,
               s.market_cap_category,
               cr.return_on_equity_pct, cr.return_on_capital_pct,
               cr.health_score, cr.health_band
        FROM companies c
        LEFT JOIN sectors s ON c.id = s.company_id
        LEFT JOIN computed_ratios cr ON c.id = cr.company_id
          AND cr.year = (SELECT MAX(year) FROM computed_ratios cr2
                         WHERE cr2.company_id = c.id)
        WHERE 1=1
    """
    params = []
    if sector:
        sql += " AND s.broad_sector = ?"
        params.append(sector)
    if market_cap_category:
        sql += " AND s.market_cap_category = ?"
        params.append(market_cap_category)
    if search:
        sql += " AND (c.id LIKE ? OR c.company_name LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    sql += " ORDER BY c.id"
    return query(conn, sql, tuple(params))


# ── 11.2 Full company profile ─────────────────────────────────────────────────
@router.get("/{ticker}", summary="Full company profile with latest KPIs")
def company_profile(ticker: str, conn=Depends(get_conn)):
    ticker = ticker.upper()
    row = query_one(conn, """
        SELECT c.*, s.broad_sector, s.sub_sector, s.market_cap_category,
               cr.return_on_equity_pct, cr.return_on_capital_pct,
               cr.net_profit_margin_pct, cr.debt_to_equity,
               cr.interest_coverage, cr.free_cash_flow_cr,
               cr.revenue_cagr_5yr, cr.pat_cagr_5yr,
               cr.health_score, cr.health_band, cr.capital_alloc_pattern,
               mc.pe_ratio, mc.pb_ratio, mc.ev_ebitda, mc.dividend_yield_pct,
               mc.market_cap_crore
        FROM companies c
        LEFT JOIN sectors s ON c.id = s.company_id
        LEFT JOIN computed_ratios cr ON c.id = cr.company_id
          AND cr.year = (SELECT MAX(year) FROM computed_ratios cr2
                         WHERE cr2.company_id = c.id)
        LEFT JOIN market_cap mc ON c.id = mc.company_id AND mc.year = 2024
        WHERE c.id = ?
    """, (ticker,))
    if not row:
        raise HTTPException(status_code=404, detail=f"Company '{ticker}' not found")
    return row


# ── 11.3 P&L history ─────────────────────────────────────────────────────────
@router.get("/{ticker}/pl", summary="P&L history for a company")
def company_pl(
    ticker: str,
    from_year: Optional[str] = Query(None, example="2018-03"),
    to_year:   Optional[str] = Query(None, example="2024-03"),
    conn=Depends(get_conn),
):
    ticker = ticker.upper()
    _check_exists(ticker, conn)
    sql = "SELECT * FROM profitandloss WHERE company_id=?"
    params = [ticker]
    if from_year:
        sql += " AND year >= ?"; params.append(from_year)
    if to_year:
        sql += " AND year <= ?"; params.append(to_year)
    sql += " ORDER BY year"
    return query(conn, sql, tuple(params))


# ── 11.4 Balance sheet history ────────────────────────────────────────────────
@router.get("/{ticker}/bs", summary="Balance sheet history")
def company_bs(
    ticker: str,
    from_year: Optional[str] = None,
    to_year:   Optional[str] = None,
    conn=Depends(get_conn),
):
    ticker = ticker.upper()
    _check_exists(ticker, conn)
    sql = "SELECT * FROM balancesheet WHERE company_id=?"
    params = [ticker]
    if from_year:
        sql += " AND year >= ?"; params.append(from_year)
    if to_year:
        sql += " AND year <= ?"; params.append(to_year)
    sql += " ORDER BY year"
    return query(conn, sql, tuple(params))


# ── 11.5 Cash flow history ────────────────────────────────────────────────────
@router.get("/{ticker}/cashflow", summary="Cash flow history")
def company_cashflow(
    ticker: str,
    from_year: Optional[str] = None,
    to_year:   Optional[str] = None,
    conn=Depends(get_conn),
):
    ticker = ticker.upper()
    _check_exists(ticker, conn)
    sql = "SELECT * FROM cashflow WHERE company_id=?"
    params = [ticker]
    if from_year:
        sql += " AND year >= ?"; params.append(from_year)
    if to_year:
        sql += " AND year <= ?"; params.append(to_year)
    sql += " ORDER BY year"
    return query(conn, sql, tuple(params))


# ── 11.6 Computed ratios ──────────────────────────────────────────────────────
@router.get("/{ticker}/ratios", summary="All computed KPIs per year")
def company_ratios(
    ticker: str,
    year: Optional[str] = Query(None, description="Filter by year (YYYY-MM)"),
    conn=Depends(get_conn),
):
    ticker = ticker.upper()
    _check_exists(ticker, conn)
    sql = "SELECT * FROM computed_ratios WHERE company_id=?"
    params = [ticker]
    if year:
        sql += " AND year = ?"; params.append(year)
    sql += " ORDER BY year"
    rows = query(conn, sql, tuple(params))
    if not rows:
        raise HTTPException(status_code=404,
                            detail=f"No ratio data for '{ticker}'")
    return rows


# ── 11.7 Tearsheet PDF ────────────────────────────────────────────────────────
@router.get("/{ticker}/tearsheet", summary="Download pre-generated tearsheet PDF")
def company_tearsheet(ticker: str, conn=Depends(get_conn)):
    ticker = ticker.upper()
    _check_exists(ticker, conn)
    pdf_path = TEARSHEETS / f"{ticker}_tearsheet.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404,
                            detail=f"Tearsheet for '{ticker}' not yet generated")
    return FileResponse(str(pdf_path), media_type="application/pdf",
                        filename=f"{ticker}_tearsheet.pdf")


# ── 11.12 Peer radar data ─────────────────────────────────────────────────────
@router.get("/{ticker}/peers/compare", summary="Radar data vs peer group average")
def peer_compare(
    ticker: str,
    year: Optional[str] = Query(None),
    conn=Depends(get_conn),
):
    ticker = ticker.upper()
    _check_exists(ticker, conn)

    # Find peer group
    group = query_one(conn,
        "SELECT peer_group_name FROM peer_groups WHERE company_id=? LIMIT 1",
        (ticker,))
    if not group:
        return {"company_id": ticker, "message": "Not in any peer group",
                "axes": []}

    group_name = group["peer_group_name"]
    members    = query(conn,
        "SELECT company_id FROM peer_groups WHERE peer_group_name=?",
        (group_name,))
    member_ids = [m["company_id"] for m in members]

    radar_metrics = [
        "return_on_equity_pct", "return_on_capital_pct",
        "net_profit_margin_pct", "operating_profit_margin_pct",
        "debt_to_equity", "interest_coverage",
        "free_cash_flow_cr", "revenue_cagr_5yr",
    ]
    placeholders = ",".join("?" * len(member_ids))
    group_sql = f"""
        SELECT company_id, {', '.join(radar_metrics)}
        FROM computed_ratios
        WHERE company_id IN ({placeholders})
          AND year = (SELECT MAX(year) FROM computed_ratios cr2
                      WHERE cr2.company_id = computed_ratios.company_id)
    """
    group_rows = query(conn, group_sql, tuple(member_ids))
    if not group_rows:
        return {"company_id": ticker, "peer_group": group_name, "axes": []}

    import statistics
    axes = []
    for m in radar_metrics:
        all_vals = [float(r[m]) for r in group_rows
                    if r.get(m) is not None]
        company_val = next((float(r[m]) for r in group_rows
                            if r["company_id"] == ticker and r.get(m) is not None),
                           None)
        avg_val = statistics.mean(all_vals) if all_vals else None

        # Normalise 0-100
        if all_vals and company_val is not None:
            mn, mx = min(all_vals), max(all_vals)
            if mx != mn:
                norm = (company_val - mn) / (mx - mn) * 100
                if m == "debt_to_equity":
                    norm = 100 - norm
                norm = max(0, min(100, round(norm, 1)))
            else:
                norm = 50.0
        else:
            norm = None

        axes.append({
            "metric":      m,
            "company_val": round(company_val, 2) if company_val is not None else None,
            "group_avg":   round(avg_val, 2) if avg_val is not None else None,
            "normalised":  norm,
        })

    return {
        "company_id":   ticker,
        "peer_group":   group_name,
        "member_count": len(member_ids),
        "axes":         axes,
    }


# ── 11.15 Documents ───────────────────────────────────────────────────────────
@router.get("/{ticker}/documents", summary="Annual report links")
def company_documents(
    ticker: str,
    from_year: Optional[int] = None,
    to_year:   Optional[int] = None,
    conn=Depends(get_conn),
):
    ticker = ticker.upper()
    _check_exists(ticker, conn)
    sql = "SELECT * FROM documents WHERE company_id=?"
    params = [ticker]
    if from_year:
        sql += " AND Year >= ?"; params.append(from_year)
    if to_year:
        sql += " AND Year <= ?"; params.append(to_year)
    sql += " ORDER BY Year DESC"
    rows = query(conn, sql, tuple(params))
    for r in rows:
        r["is_url_valid"] = bool(r.get("Annual_Report"))
    return rows


# ── Helper ────────────────────────────────────────────────────────────────────
def _check_exists(ticker: str, conn) -> None:
    row = query_one(conn, "SELECT id FROM companies WHERE id=?", (ticker,))
    if not row:
        raise HTTPException(status_code=404,
                            detail=f"Company '{ticker}' not found")
