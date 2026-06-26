import streamlit as st
import sys
from pathlib import Path
ROOT = Path("D:/final_submission")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "etl"))
sys.path.insert(0, str(ROOT / "src" / "analytics"))
sys.path.insert(0, str(ROOT / "src" / "dashboard"))
from dashboard.utils.db import load_companies, load_ratios_history, load_pl_history
from dashboard.utils.charts import trend_sparkline

st.title("Trend & Growth Analytics")
st.caption("10-year historical trends for any metric.")

companies = load_companies()
options = sorted(companies["id"].tolist())
labels = {r["id"]: f"{r['id']} — {r['company_name']}" for _, r in companies.iterrows()}

col_c, col_m = st.columns([1, 2])
with col_c:
    ticker = st.selectbox("Company", options, format_func=lambda x: labels.get(x, x))
with col_m:
    all_metrics = {
        "return_on_equity_pct": "ROE (%)",
        "return_on_capital_pct": "ROCE (%)",
        "net_profit_margin_pct": "Net Profit Margin (%)",
        "debt_to_equity": "Debt / Equity",
        "free_cash_flow_cr": "Free Cash Flow (Cr)",
        "revenue_cagr_5yr": "Revenue CAGR 5yr (%)",
        "pat_cagr_5yr": "PAT CAGR 5yr (%)",
        "health_score": "Health Score",
    }
    selected_metrics = st.multiselect(
        "Metrics (up to 3)", list(all_metrics.keys()),
        default=["return_on_equity_pct", "net_profit_margin_pct"],
        max_selections=3,
        format_func=lambda x: all_metrics.get(x, x)
    )

if ticker and selected_metrics:
    ratios = load_ratios_history(ticker)
    pl = load_pl_history(ticker)
    if not ratios.empty:
        if "return_on_equity_pct" in ratios.columns:
            ratios["return_on_equity_pct"] = ratios["return_on_equity_pct"].clip(upper=200)
        st.plotly_chart(
            trend_sparkline(ratios, selected_metrics,
                title=f"{ticker} — {', '.join(all_metrics[m] for m in selected_metrics)}"),
            use_container_width=True
        )
        st.markdown("#### CAGR Summary")
        cagr_cols = [c for c in ratios.columns if "cagr" in c and "flag" not in c]
        if cagr_cols:
            latest = ratios.iloc[-1][cagr_cols].to_frame("Value")
            latest.index = [c.replace("_"," ").title() for c in latest.index]
            import pandas as pd
            latest["Value"] = pd.to_numeric(latest["Value"], errors="coerce").round(2)
            st.dataframe(latest, use_container_width=True)
    else:
        st.warning("No data available for this company.")