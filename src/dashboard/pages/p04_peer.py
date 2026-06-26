import streamlit as st
import sys
from pathlib import Path
ROOT = Path("D:/final_submission")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "etl"))
sys.path.insert(0, str(ROOT / "src" / "analytics"))
sys.path.insert(0, str(ROOT / "src" / "dashboard"))
from dashboard.utils.db import load_all_peer_groups, load_peer_group_data, load_peer_percentiles
from dashboard.utils.charts import peer_radar

st.title("Peer Comparison Engine")
groups = load_all_peer_groups()
group = st.selectbox("Select Peer Group", groups)
grp_df = load_peer_group_data(group)

if grp_df.empty:
    st.warning("No data for this peer group.")
else:
    companies_in_group = grp_df["company_id"].tolist()
    selected = st.selectbox("Focus company", companies_in_group)
    col_r, col_t = st.columns([1, 1])
    with col_r:
        st.plotly_chart(peer_radar(grp_df, selected), use_container_width=True)
    with col_t:
        st.markdown(f"#### {group} — Comparison")
        show_cols = [c for c in ["company_id","company_name","health_score","health_band","return_on_equity_pct","return_on_capital_pct","net_profit_margin_pct","debt_to_equity","revenue_cagr_5yr","pat_cagr_5yr"] if c in grp_df.columns]
        st.dataframe(grp_df[show_cols].round(1), use_container_width=True, hide_index=True)
    st.markdown("#### Percentile Rankings")
    pct_df = load_peer_percentiles(group)
    if not pct_df.empty:
        pivot = pct_df.pivot_table(index="company_id", columns="metric", values="percentile_rank").round(2)
        st.dataframe(pivot.style.background_gradient(cmap="RdYlGn", axis=None, vmin=0, vmax=1), use_container_width=True)