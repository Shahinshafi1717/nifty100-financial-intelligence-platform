import streamlit as st
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for p in [str(ROOT),str(ROOT/"src"),str(ROOT/"src/etl"),str(ROOT/"src/analytics"),str(ROOT/"src/analytics/screener"),str(ROOT/"src/dashboard")]:
    if p not in sys.path: sys.path.insert(0,p)
from dashboard.utils.db import load_universe_latest, load_sector_summary
from dashboard.utils.charts import sector_donut, health_score_histogram, sector_bar_kpi
import plotly.express as px
import plotly.graph_objects as go

universe  = load_universe_latest()
sector_df = load_sector_summary()

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='background:linear-gradient(90deg,#161B22,#1C2333);
     border:1px solid #30363D; border-radius:12px; padding:20px 24px; margin-bottom:20px;'>
  <h1 style='margin:0; color:#E6EDF3; border:none; font-size:26px;'>
    📊 Nifty 100 Financial Intelligence Platform
  </h1>
  <p style='margin:6px 0 0 0; color:#8B949E; font-size:13px;'>
    92 Companies &nbsp;·&nbsp; 50+ KPIs &nbsp;·&nbsp; FY2010–2024 &nbsp;·&nbsp; Production v1.0
  </p>
</div>
""", unsafe_allow_html=True)

# ── Global search ─────────────────────────────────────────────────────────────
search = st.text_input("🔍  Search any company by name or ticker...", placeholder="e.g. TCS, Infosys, HDFC...")
if search:
    results = universe[universe["company_id"].str.contains(search.upper(), na=False) |
                       universe["company_name"].str.contains(search, case=False, na=False)]
    if not results.empty:
        st.success(f"Found {len(results)} match(es)")
        show = ["company_id","company_name","broad_sector","health_score","health_band",
                "return_on_equity_pct","net_profit_margin_pct","revenue_cagr_5yr"]
        show = [c for c in show if c in results.columns]
        st.dataframe(results[show].round(1), use_container_width=True, hide_index=True)
        st.stop()
    else:
        st.warning("No company found. Try a different name.")

# ── KPI tiles ─────────────────────────────────────────────────────────────────
avg_roe    = universe["return_on_equity_pct"].clip(upper=200).median()
med_pe     = universe["pe_ratio"].median()
pct_fcf    = (universe["free_cash_flow_cr"] > 0).mean() * 100
avg_health = universe["health_score"].mean()
total_mktcap = universe["market_cap_crore"].sum() / 1e5
n_excellent = (universe["health_band"] == "Excellent").sum()
n_weak      = (universe["health_band"] == "Weak").sum()

c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
c1.metric("📈 Median ROE",      f"{avg_roe:.1f}%")
c2.metric("💰 Median P/E",      f"{med_pe:.1f}×")
c3.metric("✅ FCF Positive",    f"{pct_fcf:.0f}%")
c4.metric("🏅 Avg Health",      f"{avg_health:.1f}/100")
c5.metric("💎 Total Mkt Cap",   f"₹{total_mktcap:.0f}L Cr")
c6.metric("🟢 Excellent",       f"{n_excellent} cos")
c7.metric("🔴 Weak",            f"{n_weak} cos")

st.markdown("---")

# ── Charts row ────────────────────────────────────────────────────────────────
col1, col2 = st.columns([1, 1])
with col1:
    st.plotly_chart(sector_donut(sector_df), use_container_width=True)
with col2:
    st.plotly_chart(health_score_histogram(universe), use_container_width=True)

# ── Health bands visual ───────────────────────────────────────────────────────
st.markdown("### 🏅 Health Score Bands")
b1,b2,b3,b4 = st.columns(4)
for col, band, color, icon in [
    (b1,"Excellent","#2ECC71","🟢"),
    (b2,"Good","#F39C12","🟡"),
    (b3,"Moderate","#E67E22","🟠"),
    (b4,"Weak","#E74C3C","🔴")]:
    n = (universe["health_band"] == band).sum()
    col.markdown(f"""
    <div style='background:#161B22; border:1px solid #30363D; border-left:4px solid {color};
         border-radius:8px; padding:14px; text-align:center;'>
      <div style='font-size:24px;'>{icon}</div>
      <div style='color:#E6EDF3; font-weight:bold; font-size:20px;'>{n}</div>
      <div style='color:#8B949E; font-size:12px;'>{band} companies</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ── Sector KPI bar ────────────────────────────────────────────────────────────
st.markdown("### 🏭 Sector Performance")
kpi_opts = {"median_roe":"ROE (%)","median_npm":"Net Profit Margin (%)","avg_health":"Health Score","median_pe":"P/E (×)"}
kpi_choice = st.selectbox("Select KPI", list(kpi_opts.keys()), format_func=lambda x: kpi_opts[x])
st.plotly_chart(sector_bar_kpi(sector_df, kpi_choice, kpi_opts[kpi_choice]), use_container_width=True)

# ── Top 10 table ─────────────────────────────────────────────────────────────
st.markdown("### 🏆 Top 10 Companies by Health Score")
top10 = universe.nlargest(10,"health_score")[
    ["company_id","company_name","broad_sector","health_score","health_band",
     "return_on_equity_pct","net_profit_margin_pct","revenue_cagr_5yr","market_cap_crore"]
].copy()
top10.columns = ["Ticker","Name","Sector","Health","Band","ROE%","NPM%","RevCAGR5%","MktCap(Cr)"]
st.dataframe(top10.round(1), use_container_width=True, hide_index=True)

# ── Bottom 5 watch ────────────────────────────────────────────────────────────
st.markdown("### ⚠️ Watch List — Bottom 5 by Health Score")
bottom5 = universe.nsmallest(5,"health_score")[
    ["company_id","company_name","broad_sector","health_score","health_band",
     "return_on_equity_pct","debt_to_equity","free_cash_flow_cr"]
].copy()
bottom5.columns = ["Ticker","Name","Sector","Health","Band","ROE%","D/E","FCF(Cr)"]
st.dataframe(bottom5.round(1), use_container_width=True, hide_index=True)
