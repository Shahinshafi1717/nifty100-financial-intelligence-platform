"""
src/api/main.py — Nifty 100 Financial Intelligence Platform REST API
16 endpoints across 5 routers. OpenAPI docs at /docs.

Usage:
    uvicorn src.api.main:app --port 8000 --reload
    OR: make api
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import companies, screener, sectors, peers, reports, health

app = FastAPI(
    title="Nifty 100 Financial Intelligence API",
    description=(
        "REST API for the Nifty 100 Financial Intelligence Platform. "
        "Provides access to fundamental analysis data for 92 Nifty 100 companies, "
        "50+ computed KPIs, investment screener, sector benchmarks, and peer comparison."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name":  "Data Analytics Division",
        "email": "analytics@internal.com",
    },
    license_info={
        "name": "Confidential — Internal Use Only",
    },
)

# CORS — allow Streamlit dashboard on localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501",
                   "http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(companies.router)
app.include_router(screener.router)
app.include_router(sectors.router)
app.include_router(peers.router)
app.include_router(reports.router)
app.include_router(health.router)


@app.get("/", tags=["Root"])
def root():
    return {
        "message":  "Nifty 100 Financial Intelligence API",
        "version":  "1.0.0",
        "docs":     "/docs",
        "health":   "/api/v1/health",
        "endpoints": 16,
    }
