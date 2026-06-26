"""src/api/routers/health.py — Endpoint 11.16: Server health check."""
import time
from fastapi import APIRouter, Depends
from api.db import get_conn, query

router = APIRouter(prefix="/api/v1", tags=["Health"])
_START_TIME = time.time()


@router.get("/health", summary="Server health check with DB row counts")
def health_check(conn=Depends(get_conn)):
    tables = [
        "companies", "profitandloss", "balancesheet", "cashflow",
        "analysis", "documents", "prosandcons", "sectors",
        "stock_prices", "market_cap", "financial_ratios",
        "peer_groups", "computed_ratios",
    ]
    db_row_counts = {}
    for t in tables:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()
            db_row_counts[t] = row[0] if row else 0
        except Exception:
            db_row_counts[t] = -1

    return {
        "status":          "ok",
        "version":         "1.0.0",
        "uptime_seconds":  round(time.time() - _START_TIME, 1),
        "db_row_counts":   db_row_counts,
        "companies_loaded":db_row_counts.get("companies", 0) == 92,
    }
