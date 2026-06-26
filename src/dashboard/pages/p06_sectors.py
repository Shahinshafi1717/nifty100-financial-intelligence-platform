import streamlit as st
import sys
from pathlib import Path
ROOT = Path("D:/final_submission")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "etl"))
sys.path.insert(0, str(ROOT / "src" / "analytics"))
sys.path.insert(0, str(ROOT / "src" / "dashboard"))
from dashboard.utils.db import load_universe_latest, load_sector_summary
from dashboard.utils.charts import sector_bubble, sector_bar_kpi

st.title("Sector Analytics")
st.caption("Sector benchmarks, relative positioning, and bubble charts.")

universe = load_universe_latest()
sector_df = load_sector_summary()

all_sectors = ["All Sectors"] + sorted(universe["broad_sector"].dropna().unique().tolist())
sel_sector = st.selectbox("Filter by Sector", all_sectors)
filtered = universe if sel_sector == "All Sectors" else universe[universe["broad_sector"] == sel_sector]

s1,s2,s3,s4 = st.columns(4)
s1.metric("Companies", len(filtered))
s2.metric("Avg ROE", f"{filtered['return_on_equity_pct'].clip(upper=200).mean():.1f}%")
s3.metric("Avg Health", f"{filtered['health_score'].mean():.1f}")
pe_mean = filtered['pe_ratio'].dropna().mean()
s4.metric("Avg P/E", f"{pe_mean:.1f}x" if pe_mean == pe_mean else "—")

st.markdown("---")
st.markdown("### Market Cap vs ROE")
st.plotly_chart(sector_bubble(filtered), use_container_width=True)

st.markdown("### Sector Median KPIs")
kpi_opts = {"median_roe":"ROE (%)","median_npm":"Net Profit Margin (%)","avg_health":"Health Score","median_pe":"P/E (x)","median_de":"D/E"}
col1, col2 = st.columns(2)
with col1:
    kpi1 = st.selectbox("KPI (left)", list(kpi_opts.keys()), format_func=lambda x: kpi_opts[x])
    st.plotly_chart(sector_bar_kpi(sector_df, kpi1, kpi_opts[kpi1]), use_container_width=True)
with col2:
    kpi2 = st.selectbox("KPI (right)", list(kpi_opts.keys()), index=1, format_func=lambda x: kpi_opts[x])
    st.plotly_chart(sector_bar_kpi(sector_df, kpi2, kpi_opts[kpi2]), use_container_width=True)

st.markdown("### Sector Summary Table")
disp = sector_df.rename(columns={"broad_sector":"Sector","company_count":"Companies","median_roe":"ROE%","median_npm":"NPM%","median_de":"D/E","median_pe":"P/E","avg_health":"Health","total_mktcap_lakh_cr":"MktCap(L Cr)"})
st.dataframe(disp.round(1), use_container_width=True, hide_index=True)

if sel_sector != "All Sectors":
    st.markdown(f"### Companies in {sel_sector}")
    show_cols = [c for c in ["company_id","company_name","sub_sector","health_score","health_band","return_on_equity_pct","net_profit_margin_pct","debt_to_equity","revenue_cagr_5yr","market_cap_crore"] if c in filtered.columns]
    st.dataframe(filtered[show_cols].sort_values("health_score",ascending=False).round(1), use_container_width=True, hide_index=True)