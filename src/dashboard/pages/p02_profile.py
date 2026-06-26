import streamlit as st
import sys, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for p in [str(ROOT),str(ROOT/"src"),str(ROOT/"src/etl"),str(ROOT/"src/analytics"),str(ROOT/"src/dashboard")]:
    if p not in sys.path: sys.path.insert(0,p)
from dashboard.utils.db import (load_companies, load_pl_history, load_bs_history,
    load_cf_history, load_ratios_history, load_market_cap_history, load_documents)
from dashboard.utils.charts import revenue_profit_bar, roe_roce_line, balance_sheet_stacked, cashflow_bar, pe_trend_line, trend_sparkline

st.markdown("# 🏢 Company Profile")

companies = load_companies()
options   = sorted(companies["id"].tolist())
labels    = {r["id"]: f"{r['id']} — {r['company_name']}" for _,r in companies.iterrows()}

# ── Search + Compare ──────────────────────────────────────────────────────────
col_s, col_c = st.columns([2,2])
with col_s:
    ticker = st.selectbox("🔍 Search Company", options, format_func=lambda x: labels.get(x,x))
with col_c:
    compare_ticker = st.selectbox("⚖️ Compare With (optional)",
        ["None"] + options, format_func=lambda x: x if x=="None" else labels.get(x,x))

if not ticker: st.stop()

pl     = load_pl_history(ticker)
bs     = load_bs_history(ticker)
cf     = load_cf_history(ticker)
ratios = load_ratios_history(ticker)
mc     = load_market_cap_history(ticker)
docs   = load_documents(ticker)
company= companies[companies["id"] == ticker].iloc[0]

# ── Company header card ───────────────────────────────────────────────────────
sector  = company.get("broad_sector","—")
cat     = company.get("market_cap_category","—")
about   = str(company.get("about_company","")) or ""

st.markdown(f"""
<div style='background:linear-gradient(135deg,#161B22,#1C2333);
     border:1px solid #30363D; border-left:4px solid #4F8EF7;
     border-radius:12px; padding:20px; margin:10px 0;'>
  <div style='display:flex; justify-content:space-between; align-items:center;'>
    <div>
      <h2 style='margin:0; color:#E6EDF3;'>{company["company_name"]}</h2>
      <div style='color:#8B949E; margin-top:4px; font-size:13px;'>
        🏭 {sector} &nbsp;|&nbsp; 📌 {cat} &nbsp;|&nbsp; 🔖 {ticker}
      </div>
    </div>
    <div style='text-align:right;'>
      {'<a href="'+str(company.get("website",""))+'">🌐 Website</a>' if company.get("website") and str(company.get("website"))!="nan" else ""}
    </div>
  </div>
  {f'<p style="color:#8B949E; margin:12px 0 0 0; font-size:12px;">{about[:350]}...</p>' if about and about!="nan" else ""}
</div>
""", unsafe_allow_html=True)

# ── Latest KPI tiles ──────────────────────────────────────────────────────────
if not ratios.empty:
    lat = ratios.iloc[-1]
    def fmt(v, s="", d=1):
        return f"{float(v):.{d}f}{s}" if v is not None and str(v)!="nan" else "—"

    st.markdown("### 📌 Latest KPIs")
    k1,k2,k3,k4,k5,k6 = st.columns(6)
    roe_val = min(float(lat.get("return_on_equity_pct",0) or 0), 200)
    k1.metric("ROE",          fmt(roe_val,"%"))
    k2.metric("ROCE",         fmt(lat.get("return_on_capital_pct"),"%"))
    k3.metric("NPM",          fmt(lat.get("net_profit_margin_pct"),"%"))
    k4.metric("D/E",          "Debt Free" if float(lat.get("debt_to_equity",0) or 0)==0 else fmt(lat.get("debt_to_equity")))
    k5.metric("Health Score", fmt(lat.get("health_score"),"/100",0))
    k6.metric("FCF (₹Cr)",    fmt(lat.get("free_cash_flow_cr"),"",0))

    k7,k8,k9,k10,k11,k12 = st.columns(6)
    k7.metric("Rev CAGR 5yr",  fmt(lat.get("revenue_cagr_5yr"),"%"))
    k8.metric("PAT CAGR 5yr",  fmt(lat.get("pat_cagr_5yr"),"%"))
    k9.metric("EPS CAGR 5yr",  fmt(lat.get("eps_cagr_5yr"),"%"))
    k10.metric("CFO/PAT",      fmt(lat.get("cfo_to_pat_ratio"),"×"))
    k11.metric("Health Band",  str(lat.get("health_band","—")))
    k12.metric("Capital Pattern", str(lat.get("capital_alloc_pattern","—"))[:20])

st.markdown("---")

# ── KPI Comparison ────────────────────────────────────────────────────────────
if compare_ticker != "None":
    st.markdown(f"### ⚖️ Comparison: {ticker} vs {compare_ticker}")
    ratios2 = load_ratios_history(compare_ticker)
    if not ratios.empty and not ratios2.empty:
        lat1 = ratios.iloc[-1]
        lat2 = ratios2.iloc[-1]
        comp_metrics = ["return_on_equity_pct","return_on_capital_pct",
                        "net_profit_margin_pct","debt_to_equity",
                        "free_cash_flow_cr","revenue_cagr_5yr",
                        "pat_cagr_5yr","health_score"]
        comp_labels  = ["ROE%","ROCE%","NPM%","D/E","FCF(Cr)","RevCAGR5%","PATCAGR5%","Health"]
        comp_df = pd.DataFrame({
            "Metric":    comp_labels,
            ticker:      [round(float(lat1.get(m,0) or 0),2) for m in comp_metrics],
            compare_ticker:[round(float(lat2.get(m,0) or 0),2) for m in comp_metrics],
        })
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

# ── Charts tabs ───────────────────────────────────────────────────────────────
st.markdown("### 📊 Financial Charts")
tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs(
    ["📈 Revenue & Profit","📊 ROE / ROCE","🏦 Balance Sheet","💸 Cash Flow","💹 Valuation","📋 Raw Data"])

with tab1:
    if not pl.empty:
        st.plotly_chart(revenue_profit_bar(pl), use_container_width=True)
        # EPS trend
        if "eps" in pl.columns:
            import plotly.graph_objects as go
            fig = go.Figure(go.Scatter(x=pl["year"], y=pd.to_numeric(pl["eps"],errors="coerce"),
                mode="lines+markers", fill="tozeroy",
                line=dict(color="#2ECC71",width=2), fillcolor="rgba(46,204,113,0.1)"))
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#E0E0E0"), title="EPS Trend (₹)", height=220,
                margin=dict(l=40,r=20,t=40,b=40))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No P&L data available.")

with tab2:
    if not ratios.empty:
        ratios_clip = ratios.copy()
        ratios_clip["return_on_equity_pct"] = ratios_clip["return_on_equity_pct"].clip(upper=200)
        st.plotly_chart(roe_roce_line(ratios_clip), use_container_width=True)
        # OPM trend
        if "operating_profit_margin_pct" in ratios_clip.columns:
            st.plotly_chart(trend_sparkline(ratios_clip,
                ["operating_profit_margin_pct","net_profit_margin_pct"],
                "Margin Trends (%)"), use_container_width=True)
    else:
        st.warning("No ratio data.")

with tab3:
    if not bs.empty:
        st.plotly_chart(balance_sheet_stacked(bs), use_container_width=True)
    else:
        st.warning("No balance sheet data.")

with tab4:
    if not cf.empty:
        st.plotly_chart(cashflow_bar(cf), use_container_width=True)
        # FCF trend
        cf_copy = cf.copy()
        cf_copy["fcf"] = cf_copy["operating_activity"].fillna(0) + cf_copy["investing_activity"].fillna(0)
        import plotly.graph_objects as go
        colors = ["#2ECC71" if v>=0 else "#E74C3C" for v in cf_copy["fcf"]]
        fig = go.Figure(go.Bar(x=cf_copy["year"], y=cf_copy["fcf"],
            marker_color=colors, name="FCF"))
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#E0E0E0"), title="Free Cash Flow (₹ Cr)",
            height=220, margin=dict(l=40,r=20,t=40,b=40))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No cash flow data.")

with tab5:
    if not mc.empty:
        st.plotly_chart(pe_trend_line(mc, ticker), use_container_width=True)
        v1,v2,v3,v4 = st.columns(4)
        lmc = mc.iloc[-1]
        v1.metric("P/E (2024)",     f"{lmc.get('pe_ratio',0):.1f}×")
        v2.metric("P/B (2024)",     f"{lmc.get('pb_ratio',0):.2f}×")
        v3.metric("EV/EBITDA",      f"{lmc.get('ev_ebitda',0):.1f}×")
        v4.metric("Dividend Yield", f"{lmc.get('dividend_yield_pct',0):.2f}%")
    else:
        st.info("No valuation data available.")

with tab6:
    t1,t2,t3 = st.tabs(["P&L","Balance Sheet","Cash Flow"])
    with t1:
        if not pl.empty: st.dataframe(pl.drop(columns=["id"],errors="ignore"), use_container_width=True)
    with t2:
        if not bs.empty: st.dataframe(bs.drop(columns=["id"],errors="ignore"), use_container_width=True)
    with t3:
        if not cf.empty: st.dataframe(cf.drop(columns=["id"],errors="ignore"), use_container_width=True)

# ── Annual reports quick links ────────────────────────────────────────────────
if not docs.empty:
    st.markdown("### 📄 Recent Annual Reports")
    recent = docs.head(5)
    cols = st.columns(5)
    for i, (_, row) in enumerate(recent.iterrows()):
        yr  = int(row["Year"]) if pd.notna(row.get("Year")) else "—"
        url = row.get("Annual_Report","")
        if url and str(url) != "nan":
            cols[i].markdown(f"[📥 FY{yr}]({url})")
        else:
            cols[i].markdown(f"~~FY{yr}~~")
