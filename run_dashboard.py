import sys
sys.path.insert(0,"src")
sys.path.insert(0,"src/etl")
sys.path.insert(0,"src/analytics")
sys.path.insert(0,"src/analytics/screener")
sys.path.insert(0,"src/dashboard")
import streamlit.web.cli as stcli
import os
os.environ["PYTHONPATH"]="src;src/etl;src/analytics;src/analytics/screener;src/dashboard"
sys.argv=["streamlit","run","src/dashboard/app.py"]
stcli.main()
