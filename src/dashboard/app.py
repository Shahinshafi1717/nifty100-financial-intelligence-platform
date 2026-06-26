import streamlit as st
import sys
from pathlib import Path

ROOT = Path("D:/final_submission")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "etl"))
sys.path.insert(0, str(ROOT / "src" / "analytics"))
sys.path.insert(0, str(ROOT / "src" / "analytics" / "screener"))
sys.path.insert(0, str(ROOT / "src" / "dashboard"))

st.set_page_config(
    page_title="Nifty 100 Financial Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.markdown("## 📊 Nifty 100 FIP")
    st.markdown("*Financial Intelligence Platform*")
    st.markdown("---")
    page = st.radio("Navigate", [
        "🏠 Overview",
        "🏢 Company Profile",
        "🔍 Screener",
        "👥 Peer Comparison",
        "📈 Trend Analysis",
        "🏭 Sector Analysis",
        "💰 Capital Allocation",
        "📄 Annual Reports",
    ], label_visibility="collapsed")
    st.markdown("---")
    st.caption("Nifty 100 · 92 Companies · 50+ KPIs")

import importlib.util, os

def load_page(filename):
    path = str(ROOT / "src" / "dashboard" / "pages" / filename)
    spec = importlib.util.spec_from_file_location("page", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

if   page == "🏠 Overview":          load_page("p01_home.py")
elif page == "🏢 Company Profile":   load_page("p02_profile.py")
elif page == "🔍 Screener":          load_page("p03_screener.py")
elif page == "👥 Peer Comparison":   load_page("p04_peer.py")
elif page == "📈 Trend Analysis":    load_page("p05_trends.py")
elif page == "🏭 Sector Analysis":   load_page("p06_sectors.py")
elif page == "💰 Capital Allocation":load_page("p07_capital.py")
elif page == "📄 Annual Reports":    load_page("p08_documents.py")