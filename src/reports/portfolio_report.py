"""
src/reports/portfolio_report.py — Portfolio Summary PDF Generator
Sprint 5 / Module 8.2

Generates one PDF containing all 92 companies, 1 page each,
with a portfolio-level summary cover page.
Trend arrows (↑ ↓ →) for 3yr direction on 4 key metrics.

Usage:
    python src/reports/portfolio_report.py
"""

import sqlite3
import logging
from datetime import date
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)

BASE_DIR    = Path(__file__).resolve().parents[2]
DB_PATH     = BASE_DIR / "data" / "nifty100.db"
REPORTS_DIR = BASE_DIR / "reports" / "portfolio"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("portfolio_report")

C_BLUE  = colors.HexColor("#4F8EF7")
C_GREEN = colors.HexColor("#2ECC71")
C_RED   = colors.HexColor("#E74C3C")
C_AMBER = colors.HexColor("#F39C12")
C_DARK  = colors.HexColor("#0D1117")
C_CARD  = colors.HexColor("#161B22")
C_BORDER= colors.HexColor("#30363D")
C_WHITE = colors.white
C_TEXT  = colors.HexColor("#E6EDF3")
C_GREY  = colors.HexColor("#8B949E")

PAGE_W, PAGE_H = A4
MARGIN = 1.5 * cm
UW     = PAGE_W - 2 * MARGIN


def _s(name, **kw):
    d = dict(fontName="Helvetica", fontSize=9, textColor=C_TEXT)
    d.update(kw)
    return ParagraphStyle(name, **d)


def _fmt(val, suffix="", dec=1):
    if val is None or (isinstance(val, float) and val != val):
        return "—"
    try:
        return f"{float(val):.{dec}f}{suffix}"
    except Exception:
        return "—"


def _arrow(series: pd.Series) -> str:
    """↑ ↓ → based on 3-year trend."""
    vals = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if len(vals) < 2:
        return "→"
    last = vals.tail(3)
    if last.iloc[-1] > last.iloc[0] * 1.05:
        return "↑"
    if last.iloc[-1] < last.iloc[0] * 0.95:
        return "↓"
    return "→"


def _band_colour(band):
    return {
        "Excellent": C_GREEN,
        "Good":      C_AMBER,
        "Moderate":  colors.HexColor("#E67E22"),
        "Weak":      C_RED,
    }.get(str(band), C_GREY)


# ─────────────────────────────────────────────────────────────────────────────
# Cover page
# ─────────────────────────────────────────────────────────────────────────────

def _cover_page(universe: pd.DataFrame) -> list:
    story = []
    date_str = date.today().strftime("%d %B %Y")

    story.append(Spacer(1, 60))
    story.append(Paragraph("NIFTY 100", _s("cov1", fontName="Helvetica-Bold",
        fontSize=28, textColor=C_BLUE, alignment=TA_CENTER)))
    story.append(Paragraph("Financial Intelligence Platform",
        _s("cov2", fontName="Helvetica", fontSize=16,
           textColor=C_GREY, alignment=TA_CENTER)))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=UW, color=C_BLUE, thickness=2))
    story.append(Spacer(1, 8))
    story.append(Paragraph("PORTFOLIO SUMMARY REPORT",
        _s("cov3", fontName="Helvetica-Bold", fontSize=14,
           textColor=C_WHITE, alignment=TA_CENTER)))
    story.append(Paragraph(date_str,
        _s("cov4", fontSize=10, textColor=C_GREY, alignment=TA_CENTER)))
    story.append(Spacer(1, 40))

    # Summary stats table
    avg_roe    = universe["return_on_equity_pct"].clip(upper=200).median()
    avg_health = universe["health_score"].mean()
    pct_fcf    = (universe["free_cash_flow_cr"] > 0).mean() * 100
    n_excellent= (universe["health_band"] == "Excellent").sum()
    n_weak     = (universe["health_band"] == "Weak").sum()

    stats = [
        ["Companies Covered",    "92"],
        ["Median ROE",           f"{avg_roe:.1f}%"],
        ["Avg Health Score",     f"{avg_health:.1f} / 100"],
        ["FCF Positive",         f"{pct_fcf:.0f}%"],
        ["Excellent Health",     f"{n_excellent} companies"],
        ["Weak Health",          f"{n_weak} companies"],
    ]
    t = Table(stats, colWidths=[UW * 0.5, UW * 0.5])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_CARD),
        ("TEXTCOLOR",     (0, 0), (-1, -1), C_TEXT),
        ("FONTNAME",      (0, 0), (0, -1),  "Helvetica-Bold"),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("ALIGN",         (1, 0), (1, -1),  "CENTER"),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [C_CARD, C_DARK]),
    ]))
    story.append(t)
    story.append(Spacer(1, 30))

    # Band distribution mini table
    story.append(Paragraph("HEALTH SCORE DISTRIBUTION",
        _s("dist_hdr", fontName="Helvetica-Bold", fontSize=11,
           textColor=C_BLUE, alignment=TA_CENTER)))
    story.append(Spacer(1, 6))
    bands = ["Excellent", "Good", "Moderate", "Weak"]
    counts = [int((universe["health_band"] == b).sum()) for b in bands]
    pcts   = [f"{c/92*100:.0f}%" for c in counts]
    band_data = [bands, counts, pcts]
    bt = Table(band_data, colWidths=[UW / 4] * 4)
    bt.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), C_GREEN),
        ("BACKGROUND",    (1, 0), (1, -1), C_AMBER),
        ("BACKGROUND",    (2, 0), (2, -1), colors.HexColor("#E67E22")),
        ("BACKGROUND",    (3, 0), (3, -1), C_RED),
        ("TEXTCOLOR",     (0, 0), (-1, -1), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTNAME",      (0, 1), (-1, 1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  10),
        ("FONTSIZE",      (0, 1), (-1, 1),  18),
        ("FONTSIZE",      (0, 2), (-1, 2),  10),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, C_DARK),
    ]))
    story.append(bt)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "This report is generated by the Nifty 100 Financial Intelligence Platform. "
        "All monetary values in ₹ Crore unless stated. For internal use only.",
        _s("disc", fontSize=7, textColor=C_GREY, alignment=TA_CENTER)))

    return story


# ─────────────────────────────────────────────────────────────────────────────
# Per-company page (1 page)
# ─────────────────────────────────────────────────────────────────────────────

def _company_page(row: pd.Series, all_ratios: pd.DataFrame) -> list:
    story = []
    ticker = row["company_id"]

    # Company header
    header_data = [[
        Paragraph(f"<b>{ticker}</b> — {str(row.get('company_name',''))[:35]}",
                  _s("ch", fontName="Helvetica-Bold", fontSize=13, textColor=C_WHITE)),
        Paragraph(f"{row.get('broad_sector','—')} | {row.get('sub_sector','—')}",
                  _s("cs", fontSize=8, textColor=C_GREY, alignment=TA_RIGHT)),
    ]]
    ht = Table(header_data, colWidths=[UW * 0.65, UW * 0.35])
    ht.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
    ]))
    story.append(ht)
    story.append(HRFlowable(width=UW, color=C_BLUE, thickness=1))
    story.append(Spacer(1, 4))

    # Trend arrows (3yr direction)
    comp_hist = all_ratios[all_ratios["company_id"] == ticker].sort_values("year")
    roe_arrow  = _arrow(comp_hist["return_on_equity_pct"])
    npm_arrow  = _arrow(comp_hist["net_profit_margin_pct"])
    fcf_arrow  = _arrow(comp_hist["free_cash_flow_cr"])
    rev_arrow  = _arrow(comp_hist["revenue_cagr_5yr"])

    def _arrow_col(a):
        return C_GREEN if a == "↑" else (C_RED if a == "↓" else C_GREY)

    # 6-column KPI grid
    def _kpi_cell(label, value, arrow=None):
        arrow_str = f" {arrow}" if arrow else ""
        return [
            Paragraph(label, _s("kl", fontSize=7, textColor=C_GREY, alignment=TA_CENTER)),
            Paragraph(f"<b>{value}{arrow_str}</b>",
                      _s("kv", fontName="Helvetica-Bold", fontSize=11,
                         textColor=C_WHITE, alignment=TA_CENTER)),
        ]

    band = str(row.get("health_band","—"))
    band_c = _band_colour(band)
    roe_v  = min(float(row.get("return_on_equity_pct") or 0), 200)
    de_v   = float(row.get("debt_to_equity") or 0)

    kpi_labels = ["ROE",         "NPM",         "D/E",       "Health",         "FCF (Cr)",           "Rev CAGR 5yr"]
    kpi_vals   = [_fmt(roe_v,"%"), _fmt(row.get("net_profit_margin_pct"),"%"),
                  "0 (Debt Free)" if de_v == 0 else _fmt(de_v),
                  _fmt(row.get("health_score"),"/100",0),
                  _fmt(row.get("free_cash_flow_cr"),"",0),
                  _fmt(row.get("revenue_cagr_5yr"),"%")]
    kpi_arrows = [roe_arrow, npm_arrow, None, None, fcf_arrow, rev_arrow]

    kpi_row1 = [Paragraph(lbl, _s(f"kl{i}", fontSize=7, textColor=C_GREY, alignment=TA_CENTER))
                for i, lbl in enumerate(kpi_labels)]
    kpi_row2 = []
    for val, arrow in zip(kpi_vals, kpi_arrows):
        arrow_str = f" {arrow}" if arrow else ""
        arr_col   = _arrow_col(arrow) if arrow else C_WHITE
        kpi_row2.append(Paragraph(f"<b>{val}{arrow_str}</b>",
                          _s("kv2", fontName="Helvetica-Bold", fontSize=12,
                             textColor=arr_col, alignment=TA_CENTER)))

    kpi_t = Table([kpi_row1, kpi_row2], colWidths=[UW / 6] * 6)
    kpi_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_CARD),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(kpi_t)
    story.append(Spacer(1, 5))

    # Secondary metrics table
    sec_data = [
        ["ROCE %",        "PAT CAGR 5yr",  "EPS CAGR 5yr",  "ICR",
         "CapEx Int %",   "Health Band",   "Capital Pattern"],
        [_fmt(row.get("return_on_capital_pct"),"%"),
         _fmt(row.get("pat_cagr_5yr"),"%"),
         _fmt(row.get("eps_cagr_5yr"),"%"),
         "Debt Free" if de_v == 0 else _fmt(row.get("interest_coverage")),
         _fmt(row.get("capex_intensity_pct"),"%"),
         band,
         str(row.get("capital_alloc_pattern","—"))[:22]],
    ]
    sec_t = Table(sec_data, colWidths=[UW/7]*7)
    sec_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1C2333")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_GREY),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND",    (0, 1), (-1, 1), C_DARK),
        ("TEXTCOLOR",     (0, 1), (-1, 1), C_TEXT),
        ("FONTNAME",      (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.2, C_BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        # Colour the band cell
        ("TEXTCOLOR",     (5, 1), (5, 1), band_c),
    ]))
    story.append(sec_t)
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width=UW, color=C_BORDER, thickness=0.3))

    return story


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_portfolio_report() -> Path:
    """Generate full portfolio summary PDF."""
    conn = sqlite3.connect(str(DB_PATH))
    universe = pd.read_sql("""
        SELECT cr.company_id, c.company_name, s.broad_sector, s.sub_sector,
               cr.return_on_equity_pct, cr.return_on_capital_pct,
               cr.net_profit_margin_pct, cr.debt_to_equity,
               cr.interest_coverage, cr.free_cash_flow_cr,
               cr.revenue_cagr_5yr, cr.pat_cagr_5yr, cr.eps_cagr_5yr,
               cr.health_score, cr.health_band, cr.capital_alloc_pattern,
               cr.capex_intensity_pct
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
        ORDER BY s.broad_sector, cr.company_id
    """, conn)
    all_ratios = pd.read_sql("SELECT * FROM computed_ratios", conn)
    conn.close()

    universe["return_on_equity_pct"] = universe["return_on_equity_pct"].clip(upper=200)

    date_str  = date.today().strftime("%Y%m%d")
    out_path  = REPORTS_DIR / f"portfolio_summary_{date_str}.pdf"

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title="Nifty 100 Portfolio Summary",
    )

    story = []

    # Cover page
    story.extend(_cover_page(universe))
    story.append(PageBreak())

    # One section per company (packed tightly, ~4 per page)
    companies_on_page = 0
    for i, (_, row) in enumerate(universe.iterrows()):
        story.extend(_company_page(row, all_ratios))
        companies_on_page += 1
        # 4 companies per page, then page break
        if companies_on_page == 4 and i < len(universe) - 1:
            story.append(PageBreak())
            companies_on_page = 0

    doc.build(story)
    logger.info("Portfolio summary written: %s", out_path)

    print(f"\n{'='*50}")
    print("PORTFOLIO REPORT COMPLETE")
    print(f"{'='*50}")
    print(f"  Companies    : {len(universe)}")
    print(f"  Output       : {out_path}")

    return out_path


if __name__ == "__main__":
    run_portfolio_report()
