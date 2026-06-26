import streamlit as st
import sys, pandas as pd, io
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for p in [str(ROOT),str(ROOT/"src"),str(ROOT/"src/etl"),str(ROOT/"src/analytics"),
          str(ROOT/"src/analytics/screener"),str(ROOT/"src/dashboard")]:
    if p not in sys.path: sys.path.insert(0,p)
from dashboard.utils.db import load_universe_latest
from engine import apply_filters, compute_composite_score, add_fcf_yield, load_config

st.markdown("# 🔍 Investment Screener")
st.caption("Filter 92 Nifty 100 companies across 15+ metrics. Results update live.")

universe = load_universe_latest()
universe = add_fcf_yield(universe)
universe["composite_score"] = compute_composite_score(universe)
cfg = load_config()

# ── Preset selector ───────────────────────────────────────────────────────────
preset_names  = list(cfg["presets"].keys())
preset_labels = ["Custom Screen"] + [cfg["presets"][p]["label"] for p in preset_names]

col_pre, col_sec, col_cat = st.columns([2,2,2])
with col_pre:
    preset_choice = st.selectbox("📋 Preset Screen", preset_labels)
with col_sec:
    sectors = ["All Sectors"] + sorted(universe["broad_sector"].dropna().unique().tolist())
    sector_sel = st.selectbox("🏭 Sector", sectors)
with col_cat:
    cats = ["All"] + sorted(universe["market_cap_category"].dropna().unique().tolist())
    cat_sel = st.selectbox("📊 Market Cap Category", cats)

if preset_choice != "Custom Screen":
    preset_key = preset_names[preset_labels.index(preset_choice) - 1]
    pf = cfg["presets"][preset_key]["filters"]
    st.info(f"**{preset_choice}** — {cfg['presets'][preset_key].get('description','')[:120]}")
else:
    pf = {}

# ── Filters sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎛️ Filters")
    st.markdown("---")
    min_roe     = st.slider("Min ROE (%)",            -20.0, 100.0, float(pf.get("min_roe",-20.0)), 0.5)
    max_de      = st.slider("Max D/E",                  0.0,  10.0, float(pf.get("max_de",10.0)),   0.1)
    min_npm     = st.slider("Min Net Profit Margin (%)",-30.0, 60.0,-30.0, 0.5)
    min_fcf     = st.slider("Min FCF (₹ Cr)",        -50000.0, 100000.0, float(pf.get("min_fcf",-50000.0)), 500.0)
    min_rev_cagr= st.slider("Min Rev CAGR 5yr (%)",   -20.0,  60.0, float(pf.get("min_revenue_cagr_5yr",-20.0)), 0.5)
    min_pat_cagr= st.slider("Min PAT CAGR 5yr (%)",   -50.0, 100.0, float(pf.get("min_pat_cagr_5yr",-50.0)), 0.5)
    min_health  = st.slider("Min Health Score",           0,    100, 0)
    max_pe      = st.slider("Max P/E (×)",              0.0,  100.0, 100.0, 1.0)
    min_div     = st.slider("Min Dividend Yield (%)",   0.0,    5.0, 0.0, 0.1)
    st.markdown("---")
    top_n = st.slider("Max results", 10, 92, 50)

# ── Apply filters ─────────────────────────────────────────────────────────────
result = universe.copy()
result = result[result["return_on_equity_pct"].fillna(-999) >= min_roe]
result = result[result["debt_to_equity"].fillna(999) <= max_de]
result = result[result["net_profit_margin_pct"].fillna(-999) >= min_npm]
result = result[result["free_cash_flow_cr"].fillna(-999999) >= min_fcf]
result = result[result["revenue_cagr_5yr"].fillna(-999) >= min_rev_cagr]
result = result[result["pat_cagr_5yr"].fillna(-999) >= min_pat_cagr]
result = result[result["health_score"].fillna(0) >= min_health]
result = result[result["pe_ratio"].fillna(9999) <= max_pe]
result = result[result["dividend_yield_pct"].fillna(0) >= min_div]
if sector_sel != "All Sectors":
    result = result[result["broad_sector"] == sector_sel]
if cat_sel != "All":
    result = result[result["market_cap_category"] == cat_sel]

result = result.sort_values("composite_score", ascending=False).head(top_n).reset_index(drop=True)
result.index = result.index + 1

# ── Results header ────────────────────────────────────────────────────────────
r1,r2,r3,r4 = st.columns([3,1,1,1])
r1.markdown(f"### ✅ {len(result)} companies match your filters")
with r3:
    csv_data = result.to_csv(index=False)
    st.download_button("📥 CSV", csv_data, "screener.csv", "text/csv")
with r4:
    buf = io.BytesIO()
    result.round(2).to_excel(buf, index=False, engine="openpyxl")
    st.download_button("📥 Excel", buf.getvalue(), "screener.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── Results table ─────────────────────────────────────────────────────────────
display_cols = ["company_id","company_name","broad_sector","health_score","health_band",
    "return_on_equity_pct","return_on_capital_pct","net_profit_margin_pct",
    "debt_to_equity","interest_coverage","free_cash_flow_cr",
    "revenue_cagr_5yr","pat_cagr_5yr","pe_ratio","pb_ratio",
    "dividend_yield_pct","market_cap_crore","composite_score"]
display_cols = [c for c in display_cols if c in result.columns]
rename = {
    "company_id":"Ticker","company_name":"Name","broad_sector":"Sector",
    "health_score":"Health","health_band":"Band",
    "return_on_equity_pct":"ROE%","return_on_capital_pct":"ROCE%",
    "net_profit_margin_pct":"NPM%","debt_to_equity":"D/E",
    "interest_coverage":"ICR","free_cash_flow_cr":"FCF(Cr)",
    "revenue_cagr_5yr":"RevCAGR5%","pat_cagr_5yr":"PATCAGR5%",
    "pe_ratio":"P/E","pb_ratio":"P/B","dividend_yield_pct":"DivYld%",
    "market_cap_crore":"MktCap(Cr)","composite_score":"Score"
}
disp = result[display_cols].rename(columns=rename)

def colour_band(val):
    c = {"Excellent":"#2ECC71","Good":"#F39C12","Moderate":"#E67E22","Weak":"#E74C3C"}.get(str(val),"")
    return f"color:{c}; font-weight:bold" if c else ""

styled = disp.style.format({c:"{:.1f}" for c in disp.select_dtypes("number").columns if c in disp.columns})
if "Band" in disp.columns:
    styled = styled.map(colour_band, subset=["Band"])
st.dataframe(styled, use_container_width=True, height=500)
