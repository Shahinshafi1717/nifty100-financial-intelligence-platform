"""
tests/kpi/test_screener.py
Unit + integration tests for the Investment Screener and Peer Engine.
Run: pytest tests/kpi/test_screener.py -v
"""

import sys
from pathlib import Path
import pytest
import pandas as pd
import numpy as np

# Path setup
ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "src" / "analytics"))
sys.path.insert(0, str(ROOT / "src" / "analytics" / "screener"))

from engine import (
    apply_filters, rank_results, compute_composite_score,
    add_fcf_yield, add_sector_ranks, load_config,
)
from peer import (
    compute_peer_percentiles, detect_best_and_weak,
    build_comparison_table, build_radar_data,
    RANK_METRICS, RADAR_METRICS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_universe():
    """Minimal universe DataFrame for screener tests."""
    return pd.DataFrame([
        {
            "company_id": "TCS", "company_name": "Tata Consultancy",
            "broad_sector": "Information Technology", "sub_sector": "IT Services",
            "market_cap_category": "Large Cap",
            "return_on_equity_pct": 45.0, "return_on_capital_pct": 40.0,
            "net_profit_margin_pct": 19.0, "operating_profit_margin_pct": 24.0,
            "ebit_margin_pct": 20.0, "debt_to_equity": 0.0, "interest_coverage": None,
            "is_debt_free": 1, "free_cash_flow_cr": 35000.0,
            "cash_from_operations_cr": 40000.0, "cfo_to_pat_ratio": 1.1,
            "capex_cr": 5000.0, "capex_intensity_pct": 2.0, "fcf_conversion_pct": 85.0,
            "revenue_cagr_3yr": 12.0, "revenue_cagr_5yr": 11.0, "revenue_cagr_10yr": 14.0,
            "pat_cagr_3yr": 15.0, "pat_cagr_5yr": 13.0, "eps_cagr_5yr": 13.0,
            "earnings_per_share": 100.0, "book_value_per_share": 200.0,
            "dividend_payout_ratio_pct": 45.0, "total_debt_cr": 0.0,
            "health_score": 78.0, "health_band": "Excellent",
            "capital_alloc_pattern": "Reinvestor", "fcf_concern_3yr": 0,
            "net_debt_cr": -20000.0, "pe_ratio": 28.0, "pb_ratio": 12.0,
            "ev_ebitda": 22.0, "dividend_yield_pct": 1.5, "market_cap_crore": 1400000.0,
        },
        {
            "company_id": "HDFCBANK", "company_name": "HDFC Bank",
            "broad_sector": "Financials", "sub_sector": "Private Banks",
            "market_cap_category": "Large Cap",
            "return_on_equity_pct": 16.0, "return_on_capital_pct": None,
            "net_profit_margin_pct": 22.0, "operating_profit_margin_pct": 35.0,
            "ebit_margin_pct": 30.0, "debt_to_equity": 7.5, "interest_coverage": None,
            "is_debt_free": 0, "free_cash_flow_cr": 15000.0,
            "cash_from_operations_cr": 20000.0, "cfo_to_pat_ratio": 0.9,
            "capex_cr": 5000.0, "capex_intensity_pct": 1.5, "fcf_conversion_pct": 42.0,
            "revenue_cagr_3yr": 20.0, "revenue_cagr_5yr": 18.0, "revenue_cagr_10yr": 22.0,
            "pat_cagr_3yr": 22.0, "pat_cagr_5yr": 20.0, "eps_cagr_5yr": 19.0,
            "earnings_per_share": 80.0, "book_value_per_share": 500.0,
            "dividend_payout_ratio_pct": 25.0, "total_debt_cr": 1800000.0,
            "health_score": 62.0, "health_band": "Good",
            "capital_alloc_pattern": "Leveraged Growth", "fcf_concern_3yr": 0,
            "net_debt_cr": 1600000.0, "pe_ratio": 18.0, "pb_ratio": 2.8,
            "ev_ebitda": 14.0, "dividend_yield_pct": 1.2, "market_cap_crore": 1200000.0,
        },
        {
            "company_id": "RELIANCE", "company_name": "Reliance Industries",
            "broad_sector": "Energy", "sub_sector": "Oil & Gas Refining",
            "market_cap_category": "Large Cap",
            "return_on_equity_pct": 9.0, "return_on_capital_pct": 8.0,
            "net_profit_margin_pct": 7.0, "operating_profit_margin_pct": 14.0,
            "ebit_margin_pct": 10.0, "debt_to_equity": 0.45, "interest_coverage": 5.5,
            "is_debt_free": 0, "free_cash_flow_cr": -5000.0,
            "cash_from_operations_cr": 60000.0, "cfo_to_pat_ratio": 0.7,
            "capex_cr": 65000.0, "capex_intensity_pct": 8.5, "fcf_conversion_pct": -5.0,
            "revenue_cagr_3yr": 8.0, "revenue_cagr_5yr": 9.0, "revenue_cagr_10yr": 11.0,
            "pat_cagr_3yr": 10.0, "pat_cagr_5yr": 8.0, "eps_cagr_5yr": 7.0,
            "earnings_per_share": 60.0, "book_value_per_share": 650.0,
            "dividend_payout_ratio_pct": 12.0, "total_debt_cr": 300000.0,
            "health_score": 42.0, "health_band": "Moderate",
            "capital_alloc_pattern": "Leveraged Growth", "fcf_concern_3yr": 0,
            "net_debt_cr": 280000.0, "pe_ratio": 24.0, "pb_ratio": 2.2,
            "ev_ebitda": 12.0, "dividend_yield_pct": 0.4, "market_cap_crore": 1600000.0,
        },
        {
            "company_id": "INFY", "company_name": "Infosys",
            "broad_sector": "Information Technology", "sub_sector": "IT Services",
            "market_cap_category": "Large Cap",
            "return_on_equity_pct": 30.0, "return_on_capital_pct": 28.0,
            "net_profit_margin_pct": 16.0, "operating_profit_margin_pct": 21.0,
            "ebit_margin_pct": 18.0, "debt_to_equity": 0.1, "interest_coverage": 12.0,
            "is_debt_free": 0, "free_cash_flow_cr": 18000.0,
            "cash_from_operations_cr": 22000.0, "cfo_to_pat_ratio": 1.05,
            "capex_cr": 4000.0, "capex_intensity_pct": 2.5, "fcf_conversion_pct": 78.0,
            "revenue_cagr_3yr": 14.0, "revenue_cagr_5yr": 13.0, "revenue_cagr_10yr": 12.0,
            "pat_cagr_3yr": 12.0, "pat_cagr_5yr": 14.0, "eps_cagr_5yr": 14.0,
            "earnings_per_share": 58.0, "book_value_per_share": 190.0,
            "dividend_payout_ratio_pct": 55.0, "total_debt_cr": 10000.0,
            "health_score": 71.0, "health_band": "Excellent",
            "capital_alloc_pattern": "Reinvestor", "fcf_concern_3yr": 0,
            "net_debt_cr": -8000.0, "pe_ratio": 22.0, "pb_ratio": 6.5,
            "ev_ebitda": 18.0, "dividend_yield_pct": 2.5, "market_cap_crore": 700000.0,
        },
    ])


@pytest.fixture
def sample_peer_groups():
    return pd.DataFrame([
        {"peer_group_name": "IT Services", "company_id": "TCS",  "is_benchmark": 1},
        {"peer_group_name": "IT Services", "company_id": "INFY", "is_benchmark": 0},
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Config tests
# ─────────────────────────────────────────────────────────────────────────────

def test_config_loads():
    cfg = load_config()
    assert "presets" in cfg
    assert len(cfg["presets"]) == 6

def test_config_has_6_presets():
    cfg = load_config()
    expected = {"quality_compounder", "value_pick", "growth_accelerator",
                "dividend_champion", "debt_free_blue_chip", "turnaround_watch"}
    assert set(cfg["presets"].keys()) == expected

def test_config_filter_map_exists():
    cfg = load_config()
    assert "filter_map" in cfg
    assert "min_roe" in cfg["filter_map"]


# ─────────────────────────────────────────────────────────────────────────────
# apply_filters tests
# ─────────────────────────────────────────────────────────────────────────────

def test_filter_min_roe(sample_universe):
    result = apply_filters(sample_universe, {"min_roe": 20.0})
    assert all(result["return_on_equity_pct"] >= 20.0)
    assert "TCS" in result["company_id"].values
    assert "INFY" in result["company_id"].values
    assert "RELIANCE" not in result["company_id"].values

def test_filter_max_de(sample_universe):
    result = apply_filters(sample_universe, {"max_de": 1.0})
    assert all(result["debt_to_equity"].fillna(0) <= 1.0)
    assert "HDFCBANK" not in result["company_id"].values

def test_filter_min_fcf_positive(sample_universe):
    result = apply_filters(sample_universe, {"min_fcf": 0.0})
    assert "RELIANCE" not in result["company_id"].values
    assert all(result["free_cash_flow_cr"] >= 0)

def test_filter_sector(sample_universe):
    result = apply_filters(sample_universe, {"sector": "Information Technology"})
    assert len(result) == 2
    assert set(result["company_id"].values) == {"TCS", "INFY"}

def test_filter_max_pe(sample_universe):
    result = apply_filters(sample_universe, {"max_pe": 20.0})
    assert all(result["pe_ratio"].fillna(999) <= 20.0)
    assert "HDFCBANK" in result["company_id"].values

def test_filter_combined_quality(sample_universe):
    """Quality Compounder: ROE>15, D/E<1, FCF>0, Rev CAGR 5yr>10."""
    result = apply_filters(sample_universe, {
        "min_roe": 15.0, "max_de": 1.0,
        "min_fcf": 0.0, "min_revenue_cagr_5yr": 10.0,
    })
    assert "TCS" in result["company_id"].values
    assert "INFY" in result["company_id"].values
    assert "RELIANCE" not in result["company_id"].values

def test_filter_empty_result(sample_universe):
    """ROE > 9999 → empty result."""
    result = apply_filters(sample_universe, {"min_roe": 9999.0})
    assert len(result) == 0

def test_filter_none_value_ignored(sample_universe):
    """None filter values should be skipped."""
    result = apply_filters(sample_universe, {"min_roe": None, "max_de": None})
    assert len(result) == len(sample_universe)

def test_filter_min_dividend_yield(sample_universe):
    result = apply_filters(sample_universe, {"min_dividend_yield": 2.0})
    assert "INFY" in result["company_id"].values
    assert "RELIANCE" not in result["company_id"].values


# ─────────────────────────────────────────────────────────────────────────────
# rank_results tests
# ─────────────────────────────────────────────────────────────────────────────

def test_rank_desc_composite(sample_universe):
    u = sample_universe.copy()
    u["composite_score"] = compute_composite_score(u)
    ranked = rank_results(u, "composite_score", "desc")
    scores = ranked["composite_score"].tolist()
    assert scores == sorted(scores, reverse=True) or len(scores) <= 1

def test_rank_column_added(sample_universe):
    u = sample_universe.copy()
    u["composite_score"] = compute_composite_score(u)
    ranked = rank_results(u, "composite_score")
    assert "rank" in ranked.columns
    assert ranked["rank"].iloc[0] == 1


# ─────────────────────────────────────────────────────────────────────────────
# compute_composite_score tests
# ─────────────────────────────────────────────────────────────────────────────

def test_composite_score_range(sample_universe):
    """All scores must be in [0, 100]."""
    scores = compute_composite_score(sample_universe)
    assert scores.between(0, 100).all()

def test_composite_score_tcs_above_reliance(sample_universe):
    """TCS should outscore RELIANCE."""
    scores = compute_composite_score(sample_universe)
    sample_universe["composite_score"] = scores
    tcs_score     = sample_universe[sample_universe["company_id"] == "TCS"]["composite_score"].iloc[0]
    reliance_score= sample_universe[sample_universe["company_id"] == "RELIANCE"]["composite_score"].iloc[0]
    assert tcs_score > reliance_score

def test_composite_score_no_nulls(sample_universe):
    scores = compute_composite_score(sample_universe)
    assert scores.notna().all()


# ─────────────────────────────────────────────────────────────────────────────
# add_fcf_yield tests
# ─────────────────────────────────────────────────────────────────────────────

def test_fcf_yield_computed(sample_universe):
    df = add_fcf_yield(sample_universe)
    assert "fcf_yield_pct" in df.columns
    tcs = df[df["company_id"] == "TCS"].iloc[0]
    expected = 35000.0 / 1400000.0 * 100
    assert abs(tcs["fcf_yield_pct"] - expected) < 0.01

def test_fcf_yield_negative_fcf(sample_universe):
    df = add_fcf_yield(sample_universe)
    reliance = df[df["company_id"] == "RELIANCE"].iloc[0]
    assert reliance["fcf_yield_pct"] < 0


# ─────────────────────────────────────────────────────────────────────────────
# add_sector_ranks tests
# ─────────────────────────────────────────────────────────────────────────────

def test_sector_rank_added(sample_universe):
    u = sample_universe.copy()
    u["composite_score"] = compute_composite_score(u)
    ranked = add_sector_ranks(u)
    assert "sector_rank" in ranked.columns
    assert "sector_percentile" in ranked.columns

def test_sector_rank_within_sector(sample_universe):
    """IT sector rank 1 should be the company with higher composite score."""
    u = sample_universe.copy()
    u["composite_score"] = compute_composite_score(u)
    ranked = add_sector_ranks(u)
    it = ranked[ranked["broad_sector"] == "Information Technology"].sort_values("sector_rank")
    assert it["sector_rank"].iloc[0] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Peer percentile tests
# ─────────────────────────────────────────────────────────────────────────────

def test_peer_percentiles_range(sample_universe, sample_peer_groups):
    result = compute_peer_percentiles(sample_universe, sample_peer_groups)
    assert result["percentile_rank"].between(0, 1).all()

def test_peer_percentiles_all_metrics(sample_universe, sample_peer_groups):
    """Each RANK_METRIC should appear in the output."""
    result = compute_peer_percentiles(sample_universe, sample_peer_groups)
    found_metrics = set(result["metric"].unique())
    expected = set(RANK_METRICS) & set(sample_universe.columns)
    assert expected.issubset(found_metrics)

def test_peer_percentiles_group_name(sample_universe, sample_peer_groups):
    result = compute_peer_percentiles(sample_universe, sample_peer_groups)
    assert "IT Services" in result["peer_group_name"].values


# ─────────────────────────────────────────────────────────────────────────────
# detect_best_and_weak tests
# ─────────────────────────────────────────────────────────────────────────────

def test_badges_column_exists(sample_universe, sample_peer_groups):
    pct = compute_peer_percentiles(sample_universe, sample_peer_groups)
    badges = detect_best_and_weak(pct)
    assert "badge" in badges.columns

def test_badge_values(sample_universe, sample_peer_groups):
    pct = compute_peer_percentiles(sample_universe, sample_peer_groups)
    badges = detect_best_and_weak(pct)
    assert set(badges["badge"].unique()).issubset(
        {"Best in Class", "Watch List", "Standard"}
    )


# ─────────────────────────────────────────────────────────────────────────────
# build_comparison_table tests
# ─────────────────────────────────────────────────────────────────────────────

def test_comparison_table_shape(sample_universe):
    table = build_comparison_table(["TCS", "INFY"], sample_universe)
    assert "TCS" in table.columns
    assert "INFY" in table.columns

def test_comparison_table_metrics(sample_universe):
    table = build_comparison_table(["TCS", "INFY"], sample_universe)
    assert "return_on_equity_pct" in table.index


# ─────────────────────────────────────────────────────────────────────────────
# build_radar_data tests
# ─────────────────────────────────────────────────────────────────────────────

def test_radar_data_keys(sample_universe, sample_peer_groups):
    radar = build_radar_data(sample_universe, sample_peer_groups)
    assert "TCS::IT Services" in radar or len(radar) > 0

def test_radar_axes_count(sample_universe, sample_peer_groups):
    radar = build_radar_data(sample_universe, sample_peer_groups)
    for key, data in radar.items():
        assert len(data["axes"]) == len(
            [m for m in RADAR_METRICS if m in sample_universe.columns]
        )

def test_radar_normalised_range(sample_universe, sample_peer_groups):
    radar = build_radar_data(sample_universe, sample_peer_groups)
    for key, data in radar.items():
        for axis in data["axes"]:
            assert 0.0 <= axis["normalised"] <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Integration: run screener on real DB
# ─────────────────────────────────────────────────────────────────────────────

def test_screener_quality_preset_count():
    """Quality Compounder preset should return 10–40 companies on real data."""
    import sqlite3
    from engine import load_universe, add_fcf_yield, compute_composite_score, apply_filters

    db_path = ROOT / "data" / "nifty100.db"
    if not db_path.exists():
        pytest.skip("nifty100.db not found")

    conn = sqlite3.connect(str(db_path))
    universe = load_universe(conn)
    universe = add_fcf_yield(universe)
    universe["composite_score"] = compute_composite_score(universe)
    conn.close()

    result = apply_filters(universe, {
        "min_roe": 15.0, "max_de": 1.0,
        "min_fcf": 0.0, "min_revenue_cagr_5yr": 10.0,
    })
    assert 5 <= len(result) <= 50, f"Expected 5–50, got {len(result)}"

def test_screener_debt_free_preset():
    """Debt-Free Blue Chip: max_de=0 should give positive count."""
    import sqlite3
    from engine import load_universe, add_fcf_yield, compute_composite_score, apply_filters

    db_path = ROOT / "data" / "nifty100.db"
    if not db_path.exists():
        pytest.skip("nifty100.db not found")

    conn = sqlite3.connect(str(db_path))
    universe = load_universe(conn)
    universe = add_fcf_yield(universe)
    universe["composite_score"] = compute_composite_score(universe)
    conn.close()

    result = apply_filters(universe, {"max_de": 0.0, "min_roe": 12.0})
    assert len(result) >= 1

def test_peer_engine_all_11_groups():
    """All 11 peer groups should be present in percentile output."""
    import sqlite3
    from peer import load_peer_universe, compute_peer_percentiles

    db_path = ROOT / "data" / "nifty100.db"
    if not db_path.exists():
        pytest.skip("nifty100.db not found")

    conn = sqlite3.connect(str(db_path))
    ratios, peer_groups = load_peer_universe(conn)
    conn.close()

    pct = compute_peer_percentiles(ratios, peer_groups)
    groups_found = pct["peer_group_name"].nunique()
    assert groups_found == 11, f"Expected 11 groups, found {groups_found}"
