# Makefile — Nifty 100 Financial Intelligence Platform
# Usage: make <target>

.PHONY: load ratios screener peer cluster report dashboard api test clean all

# ─── ETL ─────────────────────────────────────────────────────────────────────
load:
	@echo ">>> Running ETL pipeline..."
	python src/etl/loader.py
	@echo ">>> Loading supplementary datasets..."
	python -c "import sys; sys.path.insert(0,'src'); \
	    from etl.loader import run_etl, load_supplementary_files, write_audit, AUDIT_CSV; \
	    import sqlite3; \
	    audit = run_etl(); \
	    conn = sqlite3.connect('data/nifty100.db'); \
	    supp = load_supplementary_files(conn); \
	    conn.close(); \
	    write_audit(audit + supp)"

# ─── Analytics ───────────────────────────────────────────────────────────────
ratios:
	@echo ">>> Computing 50+ KPIs..."
	python src/analytics/ratios.py

screener:
	@echo ">>> Running investment screener (6 presets)..."
	python src/analytics/screener/engine.py

peer:
	@echo ">>> Running peer comparison engine..."
	python src/analytics/peer.py

cluster:
	@echo ">>> Running KMeans clustering and portfolio statistics..."
	python src/analytics/clustering.py

nlp:
	@echo ">>> Running NLP parser and pros/cons generator..."
	python src/nlp/parser.py
	python src/nlp/pros_cons_generator.py

cashflow:
	@echo ">>> Running cash flow intelligence module..."
	python src/analytics/cashflow_intelligence.py

valuation:
	@echo ">>> Running valuation module..."
	python src/analytics/valuation.py

# ─── Reports ─────────────────────────────────────────────────────────────────
report:
	@echo ">>> Generating 92 company tearsheets..."
	python src/reports/tearsheet.py
	@echo ">>> Generating 10 sector reports..."
	python src/reports/sector_report.py
	@echo ">>> Generating portfolio summary..."
	python src/reports/portfolio_report.py

# ─── Apps ────────────────────────────────────────────────────────────────────
dashboard:
	@echo ">>> Starting Streamlit dashboard on http://localhost:8501"
	streamlit run src/dashboard/app.py

api:
	@echo ">>> Starting FastAPI on http://localhost:8000"
	@echo ">>> API docs at: http://localhost:8000/docs"
	cd src && uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# ─── Tests ───────────────────────────────────────────────────────────────────
test:
	@echo ">>> Running full test suite (171 tests)..."
	pytest tests/ -v --tb=short
	@echo ">>> Done. All tests must pass before commit."

# ─── Full pipeline ────────────────────────────────────────────────────────────
all: load ratios screener peer cluster nlp cashflow valuation report
	@echo ">>> Full pipeline complete."

# ─── Clean ───────────────────────────────────────────────────────────────────
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo ">>> Cleaned build artifacts (database preserved)."
