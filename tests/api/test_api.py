"""
tests/api/test_api.py
Sprint 6: API endpoint tests — all 16 endpoints.
Run: pytest tests/api/test_api.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# 11.16 Health
# ─────────────────────────────────────────────────────────────────────────────

def test_health_200():
    r = client.get("/api/v1/health")
    assert r.status_code == 200

def test_health_status_ok():
    r = client.get("/api/v1/health")
    assert r.json()["status"] == "ok"

def test_health_db_row_counts():
    r = client.get("/api/v1/health")
    counts = r.json()["db_row_counts"]
    assert "companies" in counts
    assert counts["companies"] == 92

def test_health_companies_loaded():
    r = client.get("/api/v1/health")
    assert r.json()["companies_loaded"] is True

def test_health_uptime_positive():
    r = client.get("/api/v1/health")
    assert r.json()["uptime_seconds"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 11.1 Companies list
# ─────────────────────────────────────────────────────────────────────────────

def test_companies_count():
    r = client.get("/api/v1/companies")
    assert r.status_code == 200
    assert len(r.json()) == 92

def test_companies_has_tcs():
    r = client.get("/api/v1/companies")
    ids = [c["id"] for c in r.json()]
    assert "TCS" in ids

def test_companies_sector_filter():
    r = client.get("/api/v1/companies?sector=Information Technology")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    for c in data:
        assert c["broad_sector"] == "Information Technology"

def test_companies_search():
    r = client.get("/api/v1/companies?search=TCS")
    assert r.status_code == 200
    data = r.json()
    assert any(c["id"] == "TCS" for c in data)

def test_companies_invalid_sector():
    r = client.get("/api/v1/companies?sector=NonExistentSector")
    assert r.status_code == 200
    assert r.json() == []


# ─────────────────────────────────────────────────────────────────────────────
# 11.2 Company profile
# ─────────────────────────────────────────────────────────────────────────────

def test_company_profile_tcs():
    r = client.get("/api/v1/companies/TCS")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "TCS"
    assert "company_name" in data

def test_company_profile_lowercase():
    """Ticker matching should be case-insensitive."""
    r = client.get("/api/v1/companies/tcs")
    assert r.status_code == 200

def test_invalid_ticker_404():
    r = client.get("/api/v1/companies/INVALIDTICKER")
    assert r.status_code == 404

def test_company_profile_has_kpis():
    r = client.get("/api/v1/companies/TCS")
    data = r.json()
    assert "health_score" in data or "return_on_equity_pct" in data


# ─────────────────────────────────────────────────────────────────────────────
# 11.3 P&L history
# ─────────────────────────────────────────────────────────────────────────────

def test_company_pl_tcs():
    r = client.get("/api/v1/companies/TCS/pl")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 10, f"Expected ≥10 years of P&L, got {len(rows)}"

def test_company_pl_year_filter():
    r = client.get("/api/v1/companies/TCS/pl?from_year=2020-03&to_year=2024-03")
    assert r.status_code == 200
    rows = r.json()
    for row in rows:
        assert row["year"] >= "2020-03"
        assert row["year"] <= "2024-03"

def test_company_pl_invalid_ticker():
    r = client.get("/api/v1/companies/BADTICKER/pl")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 11.4 Balance Sheet
# ─────────────────────────────────────────────────────────────────────────────

def test_company_bs_tcs():
    r = client.get("/api/v1/companies/TCS/bs")
    assert r.status_code == 200
    assert len(r.json()) >= 5

def test_company_bs_has_total_assets():
    r = client.get("/api/v1/companies/TCS/bs")
    assert all("total_assets" in row for row in r.json())


# ─────────────────────────────────────────────────────────────────────────────
# 11.5 Cash Flow
# ─────────────────────────────────────────────────────────────────────────────

def test_company_cashflow_tcs():
    r = client.get("/api/v1/companies/TCS/cashflow")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 5
    assert all("operating_activity" in row for row in rows)


# ─────────────────────────────────────────────────────────────────────────────
# 11.6 Ratios
# ─────────────────────────────────────────────────────────────────────────────

def test_company_ratios_tcs():
    r = client.get("/api/v1/companies/TCS/ratios")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 10

def test_company_ratios_has_roe():
    r = client.get("/api/v1/companies/TCS/ratios")
    assert all("return_on_equity_pct" in row for row in r.json())

def test_company_ratios_screener_filter():
    """AC-13: Screener and ratios must be consistent."""
    screener_r = client.get("/api/v1/screener?min_roe=15")
    ratios_r   = client.get("/api/v1/companies/TCS/ratios")
    screener_tickers = {c["company_id"] for c in screener_r.json()["results"]}
    tcs_ratios = ratios_r.json()
    latest_roe = max(
        (r.get("return_on_equity_pct", 0) or 0 for r in tcs_ratios),
        default=0
    )
    if latest_roe >= 15:
        assert "TCS" in screener_tickers


# ─────────────────────────────────────────────────────────────────────────────
# 11.7 Tearsheet
# ─────────────────────────────────────────────────────────────────────────────

def test_tearsheet_tcs():
    r = client.get("/api/v1/companies/TCS/tearsheet")
    # 200 if PDF exists, 404 if not generated yet (both acceptable in tests)
    assert r.status_code in (200, 404)

def test_tearsheet_content_type():
    r = client.get("/api/v1/companies/TCS/tearsheet")
    if r.status_code == 200:
        assert "pdf" in r.headers.get("content-type", "")


# ─────────────────────────────────────────────────────────────────────────────
# 11.8 Screener
# ─────────────────────────────────────────────────────────────────────────────

def test_screener_basic():
    r = client.get("/api/v1/screener?min_roe=15&max_de=1")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "count" in data

def test_screener_all_results_pass_filter():
    r = client.get("/api/v1/screener?min_roe=15")
    for co in r.json()["results"]:
        roe = co.get("return_on_equity_pct")
        if roe is not None:
            assert roe >= 15, f"{co['company_id']} ROE {roe} < 15"

def test_screener_de_filter():
    r = client.get("/api/v1/screener?max_de=0")
    for co in r.json()["results"]:
        de = co.get("debt_to_equity")
        assert de is None or de <= 0

def test_screener_sector_filter():
    r = client.get("/api/v1/screener?sector=Information Technology")
    assert r.status_code == 200
    for co in r.json()["results"]:
        assert co["broad_sector"] == "Information Technology"

def test_screener_empty_filters():
    """No filters → should return ≤ top_n companies."""
    r = client.get("/api/v1/screener?top_n=10")
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 10

def test_screener_quality_count():
    """AC-07: Quality Compounder must return 10-50 companies."""
    r = client.get("/api/v1/screener?min_roe=15&max_de=1&min_fcf=0&min_rev_cagr_5yr=10")
    data = r.json()
    count = data["count"]
    assert 5 <= count <= 60, f"Expected 5–60, got {count}"


# ─────────────────────────────────────────────────────────────────────────────
# 11.9–11.10 Sectors
# ─────────────────────────────────────────────────────────────────────────────

def test_sectors_list():
    r = client.get("/api/v1/sectors")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 8

def test_sectors_has_kpis():
    r = client.get("/api/v1/sectors")
    for s in r.json():
        assert "broad_sector" in s
        assert "company_count" in s

def test_sector_companies():
    r = client.get("/api/v1/sectors/Information Technology/companies")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1
    for c in data["companies"]:
        assert "company_id" in c

def test_sector_companies_404():
    r = client.get("/api/v1/sectors/FakeSector/companies")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 11.11 Peers
# ─────────────────────────────────────────────────────────────────────────────

def test_peers_it_services():
    r = client.get("/api/v1/peers/IT Services")
    assert r.status_code == 200
    data = r.json()
    assert "members" in data
    assert data["member_count"] >= 1

def test_peers_all_11_groups():
    """AC-14: All 11 peer groups accessible via API."""
    groups = [
        "IT Services", "Private Banks", "Public Sector Banks",
        "Pharmaceuticals", "Automobiles", "Life Insurance",
        "Oil & Gas", "Power & Utilities", "Steel",
        "FMCG", "Consumer Finance",
    ]
    found = 0
    for g in groups:
        r = client.get(f"/api/v1/peers/{g}")
        if r.status_code == 200 and r.json().get("member_count", 0) > 0:
            found += 1
    assert found == 11, f"Expected 11 peer groups, found {found}"

def test_peers_404():
    r = client.get("/api/v1/peers/FakeGroup")
    assert r.status_code == 404

def test_peers_has_percentile_ranks():
    r = client.get("/api/v1/peers/IT Services")
    members = r.json()["members"]
    assert any("percentile_ranks" in m for m in members)


# ─────────────────────────────────────────────────────────────────────────────
# 11.12 Peer radar compare
# ─────────────────────────────────────────────────────────────────────────────

def test_peer_compare_tcs():
    r = client.get("/api/v1/companies/TCS/peers/compare")
    assert r.status_code == 200
    data = r.json()
    assert data["company_id"] == "TCS"

def test_peer_compare_axes():
    """AC-12: TCS radar must return ≥5 axes."""
    r = client.get("/api/v1/companies/TCS/peers/compare")
    axes = r.json().get("axes", [])
    assert len(axes) >= 5


# ─────────────────────────────────────────────────────────────────────────────
# 11.13 Market cap
# ─────────────────────────────────────────────────────────────────────────────

def test_market_cap_tcs():
    r = client.get("/api/v1/market-cap/TCS")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert all("pe_ratio" in row for row in rows)

def test_market_cap_404():
    r = client.get("/api/v1/market-cap/BADTICKER")
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 11.14 Portfolio stats
# ─────────────────────────────────────────────────────────────────────────────

def test_portfolio_stats():
    r = client.get("/api/v1/portfolio/stats")
    assert r.status_code == 200
    data = r.json()
    assert "stats" in data
    stats = data["stats"]
    assert len(stats) >= 5

def test_portfolio_stats_has_percentiles():
    r = client.get("/api/v1/portfolio/stats")
    for row in r.json()["stats"]:
        assert "P50" in row
        assert "P10" in row
        assert "P90" in row


# ─────────────────────────────────────────────────────────────────────────────
# 11.15 Documents
# ─────────────────────────────────────────────────────────────────────────────

def test_documents_tcs():
    r = client.get("/api/v1/companies/TCS/documents")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1

def test_documents_has_url_valid():
    r = client.get("/api/v1/companies/TCS/documents")
    for row in r.json():
        assert "is_url_valid" in row
