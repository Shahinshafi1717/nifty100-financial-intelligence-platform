import streamlit as st
import sys
from pathlib import Path
ROOT = Path("D:/final_submission")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "etl"))
sys.path.insert(0, str(ROOT / "src" / "analytics"))
sys.path.insert(0, str(ROOT / "src" / "dashboard"))
from dashboard.utils.db import load_capital_allocation_summary
from dashboard.utils.charts import capital_allocation_treemap

st.title("Capital Allocation Map")
st.caption("8-pattern CFO/CFI/CFF sign analysis across all 92 companies.")

cap_df = load_capital_allocation_summary()

short_map = {
    "Reinvestor — ops funding growth + returning capital": "Reinvestor",
    "Leveraged Growth — borrowing to invest": "Leveraged Growth",
    "Distress — burning cash, raising funds to survive": "Distress",
    "Startup / Distress — investing while losing cash": "Startup/Distress",
    "Asset Harvester — divesting + returning capital": "Asset Harvester",
    "Cash Accumulator — ops positive, selling assets, raising funds": "Cash Accumulator",
    "Restructuring — selling assets to repay debt": "Restructuring",
    "Deep Distress — negative on all three flows": "Deep Distress",
    "Insufficient Data": "No Data",
}

pattern_counts = cap_df["capital_alloc_pattern"].value_counts()
st.markdown("### Pattern Distribution")
cols = st.columns(4)
for i, (pattern, count) in enumerate(pattern_counts.items()):
    short = short_map.get(pattern, pattern[:20])
    cols[i % 4].metric(short, count)

st.markdown("---")
st.plotly_chart(capital_allocation_treemap(cap_df), use_container_width=True)

st.markdown("### Companies by Pattern")
cap_df["pattern_short"] = cap_df["capital_alloc_pattern"].map(short_map).fillna(cap_df["capital_alloc_pattern"])
patterns = ["All"] + sorted(cap_df["pattern_short"].dropna().unique().tolist())
sel_pattern = st.selectbox("Filter by pattern", patterns)

if sel_pattern != "All":
    view = cap_df[cap_df["pattern_short"] == sel_pattern]
else:
    view = cap_df.copy()

show_cols = [c for c in ["company_id","company_name","broad_sector","pattern_short","free_cash_flow_cr","health_score"] if c in view.columns]
st.dataframe(view[show_cols].sort_values("health_score", ascending=False).round(1), use_container_width=True, hide_index=True)

distress = cap_df[cap_df["capital_alloc_pattern"].str.contains("Distress", na=False)]
if not distress.empty:
    st.error(f"⚠️ {len(distress)} companies show distress signals: {', '.join(distress['company_id'].tolist())}")