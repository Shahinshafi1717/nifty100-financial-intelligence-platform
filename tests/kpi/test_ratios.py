"""
tests/kpi/test_ratios.py
Unit tests for all KPI formulas, CAGR engine, health score,
and capital allocation classifier.
Run: pytest tests/kpi/test_ratios.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "analytics"))
from ratios import (
    safe_div, pct, compute_cagr, cagr_for_company,
    classify_capital_allocation, compute_row_kpis,
    FLAG_TURNAROUND, FLAG_DECLINE_TO_LOSS, FLAG_BOTH_NEGATIVE,
    FLAG_ZERO_BASE, FLAG_INSUFFICIENT, FLAG_OK,
)
import pandas as pd


# =============================================================================
# safe_div / pct helpers
# =============================================================================

def test_safe_div_normal():
    assert safe_div(100, 4) == 25.0

def test_safe_div_zero_denom():
    assert safe_div(100, 0) is None

def test_safe_div_none_denom():
    assert safe_div(100, None) is None

def test_safe_div_default():
    assert safe_div(100, 0, default=-1) == -1

def test_pct_normal():
    assert pct(34990, 225458) == pytest.approx(15.5193, rel=1e-3)

def test_pct_zero_denom():
    assert pct(100, 0) is None


# =============================================================================
# CAGR — normal cases
# =============================================================================

def test_cagr_normal_10pct():
    """100 → 161 over 5 years ≈ 10% CAGR."""
    val, flag = compute_cagr(100, 161.05, 5)
    assert flag == FLAG_OK
    assert abs(val - 10.0) < 0.1

def test_cagr_normal_18pct():
    val, flag = compute_cagr(100, 228.77, 5)
    assert flag == FLAG_OK
    assert abs(val - 18.0) < 0.1

def test_cagr_exact():
    val, flag = compute_cagr(1000, 1610.51, 5)
    assert flag == FLAG_OK
    assert abs(val - 10.0) < 0.01

def test_cagr_3yr():
    val, flag = compute_cagr(100, 133.1, 3)
    assert flag == FLAG_OK
    assert abs(val - 10.0) < 0.1

def test_cagr_10yr():
    val, flag = compute_cagr(100, 259.37, 10)
    assert flag == FLAG_OK
    assert abs(val - 10.0) < 0.1


# =============================================================================
# CAGR — edge cases
# =============================================================================

def test_cagr_turnaround():
    """Base negative, end positive → TURNAROUND flag, None value."""
    val, flag = compute_cagr(-100, 200, 5)
    assert val is None
    assert flag == FLAG_TURNAROUND

def test_cagr_decline_to_loss():
    """Base positive, end negative → DECLINE_TO_LOSS."""
    val, flag = compute_cagr(200, -50, 5)
    assert val is None
    assert flag == FLAG_DECLINE_TO_LOSS

def test_cagr_both_negative():
    """Both negative → BOTH_NEGATIVE."""
    val, flag = compute_cagr(-100, -200, 5)
    assert val is None
    assert flag == FLAG_BOTH_NEGATIVE

def test_cagr_zero_base():
    """Base = 0 → ZERO_BASE."""
    val, flag = compute_cagr(0, 100, 5)
    assert val is None
    assert flag == FLAG_ZERO_BASE

def test_cagr_insufficient_years():
    """n < 3 → INSUFFICIENT."""
    val, flag = compute_cagr(100, 200, 2)
    assert val is None
    assert flag == FLAG_INSUFFICIENT

def test_cagr_none_input():
    val, flag = compute_cagr(None, 100, 5)
    assert val is None
    assert flag == FLAG_INSUFFICIENT


# =============================================================================
# cagr_for_company (series-based)
# =============================================================================

def test_cagr_series_normal():
    s = pd.Series([100, 110, 121, 133.1, 146.41, 161.05])
    val, flag = cagr_for_company(s, 5)
    assert flag == FLAG_OK
    assert abs(val - 10.0) < 0.2

def test_cagr_series_insufficient():
    s = pd.Series([100, 110])
    val, flag = cagr_for_company(s, 5)
    assert flag == FLAG_INSUFFICIENT

def test_cagr_series_3yr():
    s = pd.Series([100, 110, 121, 133.1])
    val, flag = cagr_for_company(s, 3)
    assert flag == FLAG_OK
    assert abs(val - 10.0) < 0.2


# =============================================================================
# Capital allocation classifier
# =============================================================================

def test_capital_alloc_reinvestor():
    signs, label = classify_capital_allocation(cfo=500, cfi=-200, cff=-100)
    assert signs == (1, -1, -1)
    assert "Reinvestor" in label

def test_capital_alloc_distress():
    signs, label = classify_capital_allocation(cfo=-100, cfi=50, cff=200)
    assert signs == (-1, 1, 1)
    assert "Distress" in label

def test_capital_alloc_leveraged_growth():
    signs, label = classify_capital_allocation(cfo=300, cfi=-500, cff=200)
    assert signs == (1, -1, 1)
    assert "Leveraged" in label

def test_capital_alloc_none_input():
    signs, label = classify_capital_allocation(None, -200, -100)
    assert signs is None
    assert "Insufficient" in label

def test_capital_alloc_zero_cfo():
    """CFO = 0 → treated as non-negative → sign = +1."""
    signs, label = classify_capital_allocation(0, -200, -100)
    assert signs[0] == 1


# =============================================================================
# compute_row_kpis — ROE
# =============================================================================

def _make_row(**kwargs):
    """Helper: build a minimal row dict for KPI computation."""
    defaults = {
        "sales": 1000, "expenses": 700, "operating_profit": 300,
        "opm_percentage": 30, "other_income": 20, "interest": 10,
        "depreciation": 50, "profit_before_tax": 260, "tax_percentage": 25,
        "net_profit": 195, "eps": 9.75, "dividend_payout": 40,
        "equity_capital": 100, "reserves": 900, "borrowings": 0,
        "other_liabilities": 50, "total_liabilities": 1050,
        "fixed_assets": 200, "cwip": 10, "investments": 0,
        "other_asset": 840, "total_assets": 1050,
        "operating_activity": 250, "investing_activity": -100,
        "financing_activity": -50, "face_value": 10,
    }
    defaults.update(kwargs)
    return defaults

def test_roe_positive_equity():
    row = _make_row(net_profit=100, equity_capital=100, reserves=400)
    kpis = compute_row_kpis(row, False)
    assert kpis["return_on_equity_pct"] == pytest.approx(20.0, rel=1e-3)

def test_roe_negative_equity():
    """Negative equity → ROE must be None."""
    row = _make_row(net_profit=100, equity_capital=10, reserves=-200)
    kpis = compute_row_kpis(row, False)
    assert kpis["return_on_equity_pct"] is None

def test_roe_zero_equity():
    row = _make_row(net_profit=100, equity_capital=0, reserves=0)
    kpis = compute_row_kpis(row, False)
    assert kpis["return_on_equity_pct"] is None


# =============================================================================
# compute_row_kpis — D/E
# =============================================================================

def test_de_debt_free():
    row = _make_row(borrowings=0, equity_capital=100, reserves=400)
    kpis = compute_row_kpis(row, False)
    assert kpis["debt_to_equity"] == 0.0
    assert kpis["is_debt_free"] == 1

def test_de_normal():
    row = _make_row(borrowings=250, equity_capital=100, reserves=400)
    kpis = compute_row_kpis(row, False)
    assert kpis["debt_to_equity"] == pytest.approx(0.5, rel=1e-3)

def test_de_high():
    row = _make_row(borrowings=1000, equity_capital=100, reserves=100)
    kpis = compute_row_kpis(row, False)
    assert kpis["debt_to_equity"] == pytest.approx(5.0, rel=1e-3)


# =============================================================================
# compute_row_kpis — ICR
# =============================================================================

def test_icr_debt_free():
    """interest = 0 → ICR must be None (displayed as 'Debt Free')."""
    row = _make_row(interest=0, operating_profit=300, other_income=20)
    kpis = compute_row_kpis(row, False)
    assert kpis["interest_coverage"] is None
    assert kpis["is_debt_free"] == 1

def test_icr_normal():
    row = _make_row(interest=50, operating_profit=300, other_income=20)
    kpis = compute_row_kpis(row, False)
    assert kpis["interest_coverage"] == pytest.approx(6.4, rel=1e-2)

def test_icr_below_1():
    """ICR < 1 = danger zone."""
    row = _make_row(interest=500, operating_profit=300, other_income=0)
    kpis = compute_row_kpis(row, False)
    assert kpis["interest_coverage"] == pytest.approx(0.6, rel=1e-2)


# =============================================================================
# compute_row_kpis — FCF & Cash Flow
# =============================================================================

def test_fcf_positive():
    row = _make_row(operating_activity=300, investing_activity=-100)
    kpis = compute_row_kpis(row, False)
    assert kpis["free_cash_flow_cr"] == pytest.approx(200.0)

def test_fcf_negative():
    row = _make_row(operating_activity=50, investing_activity=-300)
    kpis = compute_row_kpis(row, False)
    assert kpis["free_cash_flow_cr"] == pytest.approx(-250.0)

def test_cfo_pat_quality():
    row = _make_row(operating_activity=250, net_profit=200)
    kpis = compute_row_kpis(row, False)
    assert kpis["cfo_to_pat_ratio"] == pytest.approx(1.25)

def test_capex_intensity():
    row = _make_row(investing_activity=-80, sales=1000)
    kpis = compute_row_kpis(row, False)
    assert kpis["capex_intensity_pct"] == pytest.approx(8.0, rel=1e-2)


# =============================================================================
# compute_row_kpis — Book value per share
# =============================================================================

def test_book_value_per_share():
    """equity_cap=100, reserves=900, face_value=10 → shares=10 → BVPS=100."""
    row = _make_row(equity_capital=100, reserves=900, face_value=10)
    kpis = compute_row_kpis(row, False)
    assert kpis["book_value_per_share"] == pytest.approx(100.0)


# =============================================================================
# compute_row_kpis — NPM / OPM
# =============================================================================

def test_npm():
    row = _make_row(net_profit=100, sales=500)
    kpis = compute_row_kpis(row, False)
    assert kpis["net_profit_margin_pct"] == pytest.approx(20.0)

def test_npm_negative():
    row = _make_row(net_profit=-50, sales=500)
    kpis = compute_row_kpis(row, False)
    assert kpis["net_profit_margin_pct"] == pytest.approx(-10.0)

def test_opm():
    row = _make_row(operating_profit=150, sales=500)
    kpis = compute_row_kpis(row, False)
    assert kpis["operating_profit_margin_pct"] == pytest.approx(30.0)

def test_sales_zero_npm():
    """sales = 0 → NPM must be None."""
    row = _make_row(net_profit=100, sales=0)
    kpis = compute_row_kpis(row, False)
    assert kpis["net_profit_margin_pct"] is None


# =============================================================================
# DQ rule integration tests
# =============================================================================

def test_dq04_bs_balance():
    """DQ-04: flag when |assets - liabilities| / assets >= 1%."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "etl"))
    from validator import dq04_bs_balance
    import pandas as pd
    df = pd.DataFrame([{
        "company_id": "TEST", "year": "2023-03",
        "total_assets": 1000, "total_liabilities": 1020,
    }])
    failures = []
    count = dq04_bs_balance(df, failures)
    assert count == 1
    assert failures[0]["severity"] == "WARNING"

def test_dq06_zero_sales():
    """DQ-06: flag when sales <= 0."""
    import sys
    sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "etl"))
    from validator import dq06_positive_sales
    import pandas as pd
    df = pd.DataFrame([{
        "company_id": "TEST", "year": "2023-03", "sales": 0,
    }])
    failures = []
    count = dq06_positive_sales(df, failures)
    assert count == 1
