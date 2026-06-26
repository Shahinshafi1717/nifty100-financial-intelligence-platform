import streamlit as st
import sys
from pathlib import Path
ROOT = Path("D:/final_submission")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "etl"))
sys.path.insert(0, str(ROOT / "src" / "dashboard"))
from dashboard.utils.db import load_companies, load_documents
import pandas as pd
import sqlite3

st.title("Annual Reports Repository")
st.caption("1,457 annual report links from BSE India — FY2010 to FY2024.")

companies = load_companies()
options = sorted(companies["id"].tolist())
labels = {r["id"]: f"{r['id']} — {r['company_name']}" for _, r in companies.iterrows()}

c1, c2 = st.columns([2, 1])
with c1:
    ticker = st.selectbox("Select Company", options, format_func=lambda x: labels.get(x, x))
with c2:
    year_filter = st.slider("Year range", 2010, 2024, (2018, 2024))

if ticker:
    docs = load_documents(ticker)
    if docs.empty:
        st.warning(f"No annual reports found for {ticker}.")
    else:
        year_col = "Year" if "Year" in docs.columns else "year"
        docs[year_col] = pd.to_numeric(docs[year_col], errors="coerce")
        docs["Year"] = docs[year_col]
        docs = docs[docs["Year"].between(year_filter[0], year_filter[1])]
        docs = docs.sort_values("Year", ascending=False)
        st.markdown(f"### {labels.get(ticker, ticker)} — Annual Reports")
        st.caption(f"Showing {len(docs)} reports for {year_filter[0]}–{year_filter[1]}")
        for _, row in docs.iterrows():
            yr = int(row["Year"]) if pd.notna(row["Year"]) else "—"
            url = row.get("Annual_Report", "")
            col_yr, col_link, col_badge = st.columns([1, 5, 1])
            col_yr.markdown(f"**FY{yr}**")
            if url and str(url) != "nan":
                col_link.markdown(f"[Open Annual Report PDF]({url})")
                col_badge.markdown("🟢 Live")
            else:
                col_link.markdown("*URL not available*")
                col_badge.markdown("🔴 Missing")

st.markdown("---")
st.markdown("### Coverage Summary")
db_path = ROOT / "data" / "nifty100.db"
with sqlite3.connect(str(db_path)) as conn:
    coverage = pd.read_sql("""
        SELECT c.id, c.company_name, COUNT(d.id) AS total_reports,
               SUM(CASE WHEN d.Annual_Report IS NOT NULL THEN 1 ELSE 0 END) AS with_url,
               MAX(d.Year) AS latest_year
        FROM companies c
        LEFT JOIN documents d ON c.id = d.company_id
        GROUP BY c.id, c.company_name
        ORDER BY total_reports DESC
    """, conn)
coverage = coverage.rename(columns={"id":"Ticker","company_name":"Name","total_reports":"Total","with_url":"With URL","latest_year":"Latest Year"})
st.dataframe(coverage, use_container_width=True, hide_index=True, height=400)