"""
src/reports/tearsheet.py — Company Tearsheet PDF Generator
Sprint 5 / Module 8.1

Generates 2-page company tearsheets for all 92 companies using ReportLab.
Page 1: KPI tiles, 10yr revenue & profit bar, ROE/ROCE trend line.
Page 2: BS composition stacked bar, CF bar, capital allocation, pros/cons.

Usage:
    python src/reports/tearsheet.py           # all 92 companies
    python src/reports/tearsheet.py TCS       # single company
"""

import sys
import sqlite3
import logging
from pathlib import Path
from io import BytesIO

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.graphics import renderPDF
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker

BASE_DIR    = Path(__file__).resolve().parents[2]
DB_PATH     = BASE_DIR / "data" / "nifty100.db"
REPORTS_DIR = BASE_DIR / "reports" / "tearsheets"
OUTPUT_DIR  = BASE_DIR / "output"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("tearsheet")

# ── Colour palette ─────────────────────────────────────────────────────────
C_DARK    = colors.HexColor("#0D1117")
C_CARD    = colors.HexColor("#161B22")
C_BORDER  = colors.HexColor("#30363D")
C_BLUE    = colors.HexColor("#4F8EF7")
C_GREEN   = colors.HexColor("#2ECC71")
C_RED     = colors.HexColor("#E74C3C")
C_AMBER   = colors.HexColor("#F39C12")
C_GREY    = colors.HexColor("#8B949E")
C_WHITE   = colors.white
C_TEXT    = colors.HexColor("#E6EDF3")
C_SUBTEXT = colors.HexColor("#8B949E")

PAGE_W, PAGE_H = A4          # 595 × 842 pt
MARGIN         = 1.5 * cm
UW             = PAGE_W - 2 * MARGIN   # usable width ≈ 498 pt


# ─────────────────────────────────────────────────────────────────────────────
# Style helpers
# ─────────────────────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold",
                                fontSize=18, textColor=C_WHITE, spaceAfter=4,
                                alignment=TA_LEFT),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica",
                                   fontSize=10, textColor=C_SUBTEXT, spaceAfter=8),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold",
                                  fontSize=11, textColor=C_BLUE, spaceBefore=10, spaceAfter=4),
        "kpi_label": ParagraphStyle("kpi_label", fontName="Helvetica",
                                    fontSize=8, textColor=C_SUBTEXT, alignment=TA_CENTER),
        "kpi_value": ParagraphStyle("kpi_value", fontName="Helvetica-Bold",
                                    fontSize=16, textColor=C_WHITE, alignment=TA_CENTER),
        "kpi_unit":  ParagraphStyle("kpi_unit", fontName="Helvetica",
                                    fontSize=8, textColor=C_SUBTEXT, alignment=TA_CENTER),
        "body":      ParagraphStyle("body", fontName="Helvetica",
                                    fontSize=9, textColor=C_TEXT, spaceAfter=4, leading=13),
        "small":     ParagraphStyle("small", fontName="Helvetica",
                                    fontSize=8, textColor=C_SUBTEXT, spaceAfter=2),
        "pros":      ParagraphStyle("pros", fontName="Helvetica",
                                    fontSize=8, textColor=C_GREEN, spaceAfter=2, leading=11),
        "cons":      ParagraphStyle("cons", fontName="Helvetica",
                                    fontSize=8, textColor=C_RED, spaceAfter=2, leading=11),
    }
    return styles


# ─────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(val, suffix="", decimals=1, default="—"):
    """Format a numeric value safely."""
    if val is None or (isinstance(val, float) and val != val):
        return default
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return default


def _trend_arrow(series: pd.Series) -> str:
    """Return ↑, ↓, or → based on last 3yr trend."""
    vals = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if len(vals) < 2:
        return "→"
    last3 = vals.tail(3)
    if last3.iloc[-1] > last3.iloc[0] * 1.05:
        return "↑"
    if last3.iloc[-1] < last3.iloc[0] * 0.95:
        return "↓"
    return "→"


# ─────────────────────────────────────────────────────────────────────────────
# Chart builders (ReportLab Drawing)
# ─────────────────────────────────────────────────────────────────────────────

def _bar_chart(years, series1, series2, label1, label2,
               width=UW, height=120) -> Drawing:
    """Grouped bar chart: Revenue vs Net Profit."""
    d = Drawing(width, height)

    # Background
    d.add(Rect(0, 0, width, height, fillColor=C_CARD, strokeColor=C_BORDER,
               strokeWidth=0.5))

    if not years or not series1:
        d.add(String(width / 2, height / 2, "No data",
                     textAnchor="middle", fontSize=9, fillColor=C_GREY))
        return d

    bc = VerticalBarChart()
    bc.x       = 30
    bc.y       = 20
    bc.width   = width - 50
    bc.height  = height - 35
    bc.data    = [
        [float(v) if v is not None and v == v else 0 for v in series1],
        [float(v) if v is not None and v == v else 0 for v in series2],
    ]
    bc.categoryAxis.categoryNames = [str(y)[-5:] for y in years]
    bc.categoryAxis.labels.fontSize = 7
    bc.categoryAxis.labels.fillColor = C_GREY
    bc.categoryAxis.labels.angle = 45
    bc.valueAxis.labels.fontSize  = 7
    bc.valueAxis.labels.fillColor = C_GREY
    bc.valueAxis.strokeColor      = C_BORDER
    bc.categoryAxis.strokeColor   = C_BORDER
    bc.bars[0].fillColor = C_BLUE
    bc.bars[1].fillColor = C_GREEN
    bc.bars.strokeColor  = None
    bc.groupSpacing      = 3

    d.add(bc)

    # Legend
    d.add(Rect(bc.x, height - 12, 10, 8, fillColor=C_BLUE,   strokeColor=None))
    d.add(String(bc.x + 13, height - 11, label1,
                 fontSize=7, fillColor=C_TEXT))
    d.add(Rect(bc.x + 80, height - 12, 10, 8, fillColor=C_GREEN, strokeColor=None))
    d.add(String(bc.x + 93, height - 11, label2,
                 fontSize=7, fillColor=C_TEXT))

    return d


def _line_chart(years, *series_pairs, width=UW, height=100) -> Drawing:
    """
    Line chart for 1+ series.
    series_pairs: (values_list, colour, label) tuples
    """
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=C_CARD, strokeColor=C_BORDER,
               strokeWidth=0.5))

    if not years:
        return d

    lp = LinePlot()
    lp.x      = 35
    lp.y      = 18
    lp.width  = width - 50
    lp.height = height - 30

    all_vals = []
    lp.data = []
    colours = []
    labels  = []
    for vals, col, lbl in series_pairs:
        safe = [float(v) if v is not None and str(v) != "nan" else None for v in vals]
        # Use index as x since LinePlot needs (x,y) pairs
        pts = [(i, v) for i, v in enumerate(safe) if v is not None]
        # Skip series with fewer than 2 valid points (LinePlot requires ≥2)
        if len(pts) < 2:
            continue
        lp.data.append(pts)
        colours.append(col)
        labels.append(lbl)
        all_vals.extend([v for _, v in pts])

    if not all_vals or not lp.data:
        return d

    for i, (col, lbl) in enumerate(zip(colours, labels)):
        lp.lines[i].strokeColor = col
        lp.lines[i].strokeWidth = 1.5
        marker = makeMarker("Circle")
        marker.size = 3
        marker.fillColor = col
        lp.lines[i].symbol = marker

    # Y axis range
    mn_val = min(all_vals) * 0.9
    mx_val = max(all_vals) * 1.1
    if mn_val == mx_val:
        mn_val -= 1
        mx_val += 1
    lp.yValueAxis.valueMin  = mn_val
    lp.yValueAxis.valueMax  = mx_val
    lp.yValueAxis.labels.fontSize  = 7
    lp.yValueAxis.labels.fillColor = C_GREY
    lp.yValueAxis.strokeColor      = C_BORDER

    # X axis — show year labels
    lp.xValueAxis.valueMin  = 0
    lp.xValueAxis.valueMax  = len(years) - 1
    lp.xValueAxis.strokeColor = C_BORDER
    lp.xValueAxis.labels.fontSize = 7
    lp.xValueAxis.labels.fillColor = C_GREY

    d.add(lp)

    # Reference line at y=15 for ROE/ROCE charts
    if mx_val > 15 > mn_val:
        y_15 = lp.y + (15 - mn_val) / (mx_val - mn_val) * lp.height
        d.add(Line(lp.x, y_15, lp.x + lp.width, y_15,
                   strokeColor=C_GREY, strokeDashArray=[2, 2], strokeWidth=0.5))
        d.add(String(lp.x + lp.width + 2, y_15 - 3, "15%",
                     fontSize=6, fillColor=C_GREY))

    # Legend
    x_leg = lp.x
    for i, (col, lbl) in enumerate(zip(colours, labels)):
        d.add(Rect(x_leg, height - 10, 12, 6, fillColor=col, strokeColor=None))
        d.add(String(x_leg + 14, height - 10, lbl, fontSize=7, fillColor=C_TEXT))
        x_leg += 80

    return d


# ─────────────────────────────────────────────────────────────────────────────
# KPI tile row
# ─────────────────────────────────────────────────────────────────────────────

def _kpi_tiles(kpis: list[tuple]) -> Table:
    """
    Build a row of KPI tiles.
    kpis: list of (label, value_str, unit_str, colour)
    """
    n = len(kpis)
    col_w = UW / n

    header_row = [Paragraph(label, _styles()["kpi_label"]) for label, _, _, _ in kpis]
    value_row  = [Paragraph(f"<b>{val}</b>", ParagraphStyle(
        "kv", fontName="Helvetica-Bold", fontSize=14,
        textColor=col, alignment=TA_CENTER))
        for _, val, _, col in kpis]
    unit_row   = [Paragraph(unit, _styles()["kpi_unit"]) for _, _, unit, _ in kpis]

    t = Table([header_row, value_row, unit_row],
              colWidths=[col_w] * n)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_CARD),
        ("GRID",       (0, 0), (-1, -1), 0.5, C_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


# ─────────────────────────────────────────────────────────────────────────────
# Data loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_company_data(conn, company_id: str) -> dict:
    """Load all data needed for a company tearsheet."""
    data = {}

    # Company master
    data["company"] = pd.read_sql("""
        SELECT c.*, s.broad_sector, s.sub_sector, s.market_cap_category
        FROM companies c LEFT JOIN sectors s ON c.id = s.company_id
        WHERE c.id = ?
    """, conn, params=(company_id,))

    # P&L history
    data["pl"] = pd.read_sql(
        "SELECT * FROM profitandloss WHERE company_id=? ORDER BY year",
        conn, params=(company_id,))

    # Balance sheet history
    data["bs"] = pd.read_sql(
        "SELECT * FROM balancesheet WHERE company_id=? ORDER BY year",
        conn, params=(company_id,))

    # Cash flow history
    data["cf"] = pd.read_sql(
        "SELECT * FROM cashflow WHERE company_id=? ORDER BY year",
        conn, params=(company_id,))

    # Computed ratios (all years)
    data["ratios"] = pd.read_sql(
        "SELECT * FROM computed_ratios WHERE company_id=? ORDER BY year",
        conn, params=(company_id,))

    # Market cap
    data["mc"] = pd.read_sql(
        "SELECT * FROM market_cap WHERE company_id=? ORDER BY year",
        conn, params=(company_id,))

    # Pros/cons (auto-generated)
    pros_path = BASE_DIR / "output" / "pros_cons_generated.csv"
    if pros_path.exists():
        pc_all = pd.read_csv(pros_path)
        data["pros_cons"] = pc_all[pc_all["company_id"] == company_id]
    else:
        data["pros_cons"] = pd.DataFrame()

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Page 1 builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_page1(data: dict, styles: dict) -> list:
    """Build Page 1: Header, KPI tiles, Revenue/Profit chart, ROE/ROCE trend."""
    story = []
    co    = data["company"]
    pl    = data["pl"]
    ratios= data["ratios"]
    mc    = data["mc"]

    if co.empty:
        story.append(Paragraph("No company data found.", styles["body"]))
        return story

    c = co.iloc[0]

    # ── Header ───────────────────────────────────────────────────────────────
    header_data = [[
        Paragraph(f"<b>{c['company_name']}</b>", styles["title"]),
        Paragraph(f"{c.get('broad_sector','—')} | {c.get('sub_sector','—')}"
                  f" | {c.get('market_cap_category','—')}",
                  ParagraphStyle("hdr_sub", fontName="Helvetica", fontSize=9,
                                 textColor=C_SUBTEXT, alignment=TA_RIGHT)),
    ]]
    hdr_t = Table(header_data, colWidths=[UW * 0.65, UW * 0.35])
    hdr_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
    ]))
    story.append(hdr_t)
    story.append(HRFlowable(width=UW, color=C_BLUE, thickness=1.5))
    story.append(Spacer(1, 6))

    # ── About ────────────────────────────────────────────────────────────────
    about = str(c.get("about_company", "")) or ""
    if about and about != "nan":
        story.append(Paragraph(about[:300] + ("…" if len(about) > 300 else ""),
                               styles["body"]))
        story.append(Spacer(1, 6))

    # ── Latest KPI tiles ─────────────────────────────────────────────────────
    story.append(Paragraph("KEY PERFORMANCE INDICATORS", styles["section"]))

    latest_r = ratios.iloc[-1].to_dict() if not ratios.empty else {}
    latest_mc= mc.iloc[-1].to_dict()     if not mc.empty     else {}
    latest_pl= pl.iloc[-1].to_dict()     if not pl.empty     else {}

    roe_val  = min(float(latest_r.get("return_on_equity_pct") or 0), 200)
    roe_col  = C_GREEN if roe_val >= 15 else (C_AMBER if roe_val >= 8 else C_RED)
    roce_val = float(latest_r.get("return_on_capital_pct") or 0)
    npm_val  = float(latest_r.get("net_profit_margin_pct") or 0)
    npm_col  = C_GREEN if npm_val >= 10 else (C_AMBER if npm_val >= 5 else C_RED)
    de_val   = float(latest_r.get("debt_to_equity") or 0)
    de_col   = C_GREEN if de_val == 0 else (C_AMBER if de_val < 1 else C_RED)
    h_score  = float(latest_r.get("health_score") or 0)
    h_col    = C_GREEN if h_score >= 70 else (C_AMBER if h_score >= 40 else C_RED)
    pe_val   = float(latest_mc.get("pe_ratio") or 0)

    kpis_row1 = [
        ("ROE",           _fmt(roe_val, "%"),  "Return on Equity",   roe_col),
        ("ROCE",          _fmt(roce_val, "%"), "Return on Capital",  C_BLUE),
        ("NPM",           _fmt(npm_val, "%"),  "Net Profit Margin",  npm_col),
        ("D/E",           _fmt(de_val) if de_val > 0 else "Debt Free",
                                               "Debt / Equity",      de_col),
        ("Health Score",  _fmt(h_score, "/100", 0),
                                               "Composite Score",    h_col),
        ("P/E",           _fmt(pe_val, "×"),   "Price/Earnings 2024",C_GREY),
    ]
    story.append(_kpi_tiles(kpis_row1))
    story.append(Spacer(1, 4))

    # Row 2: CAGR tiles
    rev5  = _fmt(latest_r.get("revenue_cagr_5yr"), "%")
    pat5  = _fmt(latest_r.get("pat_cagr_5yr"), "%")
    eps5  = _fmt(latest_r.get("eps_cagr_5yr"), "%")
    fcf   = _fmt(latest_r.get("free_cash_flow_cr"), " Cr", 0)
    cfo_q = str(latest_r.get("cfo_quality_tier", latest_r.get("cfo_to_pat_ratio", "—")))
    pat_t = str(latest_r.get("capital_alloc_pattern", "—"))[:25]

    kpis_row2 = [
        ("Rev CAGR 5yr",  rev5, "Revenue Growth",    C_BLUE),
        ("PAT CAGR 5yr",  pat5, "Profit Growth",     C_BLUE),
        ("EPS CAGR 5yr",  eps5, "EPS Growth",        C_BLUE),
        ("FCF",           fcf,  "Free Cash Flow",    C_GREEN if "−" not in fcf else C_RED),
        ("Health Band",   str(latest_r.get("health_band","—")), "", h_col),
        ("Capex Pattern", pat_t[:20], "Capital Alloc", C_GREY),
    ]
    story.append(_kpi_tiles(kpis_row2))
    story.append(Spacer(1, 8))

    # ── Revenue & Profit bar chart ────────────────────────────────────────────
    story.append(Paragraph("REVENUE & NET PROFIT (Rs. Cr)", styles["section"]))
    if not pl.empty:
        years   = pl["year"].tolist()
        revenue = pd.to_numeric(pl["sales"],      errors="coerce").tolist()
        profit  = pd.to_numeric(pl["net_profit"],  errors="coerce").tolist()
        story.append(_bar_chart(years, revenue, profit,
                                "Revenue (Cr)", "Net Profit (Cr)",
                                width=UW, height=130))
    else:
        story.append(Paragraph("No P&L data available.", styles["small"]))
    story.append(Spacer(1, 8))

    # ── ROE / ROCE trend line ─────────────────────────────────────────────────
    story.append(Paragraph("ROE vs ROCE TREND (%)", styles["section"]))
    if not ratios.empty:
        roe_ser  = pd.to_numeric(ratios["return_on_equity_pct"], errors="coerce").clip(upper=200).tolist()
        roce_ser = pd.to_numeric(ratios["return_on_capital_pct"], errors="coerce").tolist()
        yrs      = ratios["year"].tolist()
        story.append(_line_chart(
            yrs,
            (roe_ser,  C_BLUE,  "ROE %"),
            (roce_ser, C_GREEN, "ROCE %"),
            width=UW, height=100
        ))
    else:
        story.append(Paragraph("No ratio data available.", styles["small"]))

    return story


# ─────────────────────────────────────────────────────────────────────────────
# Page 2 builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_page2(data: dict, styles: dict) -> list:
    """Build Page 2: BS composition, CF bar, Pros/Cons."""
    story = []
    bs    = data["bs"]
    cf    = data["cf"]
    pc    = data["pros_cons"]
    ratios= data["ratios"]
    co    = data["company"]

    if not co.empty:
        c = co.iloc[0]
        story.append(Paragraph(
            f"<b>{c['company_name']}</b> — Continued",
            ParagraphStyle("pg2_hdr", fontName="Helvetica-Bold",
                           fontSize=13, textColor=C_BLUE)
        ))
        story.append(HRFlowable(width=UW, color=C_BORDER, thickness=0.5))
        story.append(Spacer(1, 6))

    # ── Balance sheet stacked bar ─────────────────────────────────────────────
    story.append(Paragraph("BALANCE SHEET COMPOSITION (Rs. Cr)", styles["section"]))
    if not bs.empty:
        yrs    = bs["year"].tolist()
        equity = (pd.to_numeric(bs["equity_capital"], errors="coerce").fillna(0) +
                  pd.to_numeric(bs["reserves"], errors="coerce").fillna(0)).tolist()
        borrow = pd.to_numeric(bs["borrowings"], errors="coerce").fillna(0).tolist()
        story.append(_bar_chart(yrs, equity, borrow,
                                "Equity (Cr)", "Borrowings (Cr)",
                                width=UW, height=110))
    story.append(Spacer(1, 8))

    # ── Cash flow bar ─────────────────────────────────────────────────────────
    story.append(Paragraph("CASH FLOW (Rs. Cr)", styles["section"]))
    if not cf.empty:
        yrs = cf["year"].tolist()
        cfo = pd.to_numeric(cf["operating_activity"], errors="coerce").tolist()
        cfi = pd.to_numeric(cf["investing_activity"], errors="coerce").tolist()
        story.append(_line_chart(
            yrs,
            (cfo, C_GREEN, "CFO"),
            (cfi, C_RED,   "CFI"),
            width=UW, height=100
        ))
    story.append(Spacer(1, 8))

    # ── Capital allocation & health summary table ─────────────────────────────
    story.append(Paragraph("FINANCIAL SUMMARY", styles["section"]))
    if not ratios.empty:
        lat = ratios.iloc[-1]
        summary_data = [
            ["Metric", "Value", "Metric", "Value"],
            ["Health Score",     _fmt(lat.get("health_score"), "/100", 0),
             "Health Band",      str(lat.get("health_band","—"))],
            ["Asset Turnover",   _fmt(lat.get("asset_turnover")),
             "CFO/PAT Ratio",    _fmt(lat.get("cfo_to_pat_ratio"))],
            ["CapEx Intensity",  _fmt(lat.get("capex_intensity_pct"), "%"),
             "FCF Conversion",   _fmt(lat.get("fcf_conversion_pct"), "%")],
            ["Net Debt (Cr)",    _fmt(lat.get("net_debt_cr"), "", 0),
             "Capital Pattern",  str(lat.get("capital_alloc_pattern","—"))[:30]],
            ["Rev CAGR 10yr",   _fmt(lat.get("revenue_cagr_10yr"), "%"),
             "EPS CAGR 5yr",    _fmt(lat.get("eps_cagr_5yr"), "%")],
        ]
        t = Table(summary_data, colWidths=[UW*0.25, UW*0.25, UW*0.25, UW*0.25])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  C_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  C_WHITE),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("BACKGROUND",    (0, 1), (-1, -1), C_CARD),
            ("TEXTCOLOR",     (0, 1), (-1, -1), C_TEXT),
            ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_CARD, C_DARK]),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("WORDWRAP",      (0, 0), (-1, -1), True),
        ]))
        story.append(t)
    story.append(Spacer(1, 8))

    # ── Pros & Cons ───────────────────────────────────────────────────────────
    story.append(Paragraph("INVESTMENT INSIGHTS", styles["section"]))
    if not pc.empty:
        pros = pc[pc["type"] == "pro"].head(4)["text"].tolist()
        cons = pc[pc["type"] == "con"].head(4)["text"].tolist()
        pc_data = [[
            Paragraph("<b>✓ STRENGTHS</b>", ParagraphStyle("pro_hdr",
                fontName="Helvetica-Bold", fontSize=9, textColor=C_GREEN)),
            Paragraph("<b>✗ RISKS</b>", ParagraphStyle("con_hdr",
                fontName="Helvetica-Bold", fontSize=9, textColor=C_RED)),
        ]]
        max_rows = max(len(pros), len(cons))
        for i in range(max_rows):
            p_text = f"• {pros[i][:120]}" if i < len(pros) else ""
            c_text = f"• {cons[i][:120]}" if i < len(cons) else ""
            pc_data.append([
                Paragraph(p_text, styles["pros"]),
                Paragraph(c_text, styles["cons"]),
            ])
        pc_table = Table(pc_data, colWidths=[UW * 0.5, UW * 0.5])
        pc_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  C_DARK),
            ("BACKGROUND",    (0, 1), (-1, -1), C_CARD),
            ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("WORDWRAP",      (0, 0), (-1, -1), True),
        ]))
        story.append(pc_table)
    else:
        story.append(Paragraph("Pros/Cons data not yet available. "
                               "Run pros_cons_generator.py first.",
                               styles["small"]))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width=UW, color=C_BORDER, thickness=0.3))
    story.append(Paragraph(
        "Nifty 100 Financial Intelligence Platform — Internal Use Only. "
        "All values in Rs. Crore unless stated. Simulated market data labelled accordingly.",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=6,
                       textColor=C_SUBTEXT, alignment=TA_CENTER)
    ))
    return story


# ─────────────────────────────────────────────────────────────────────────────
# Main tearsheet generator
# ─────────────────────────────────────────────────────────────────────────────

def generate_tearsheet(company_id: str, conn: sqlite3.Connection) -> Path:
    """Generate a 2-page PDF tearsheet for one company. Returns output path."""
    data   = _load_company_data(conn, company_id)
    styles = _styles()

    out_path = REPORTS_DIR / f"{company_id}_tearsheet.pdf"

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title=f"{company_id} — Financial Tearsheet",
        author="Nifty 100 Financial Intelligence Platform",
    )

    story = []
    story.extend(_build_page1(data, styles))
    story.append(PageBreak())
    story.extend(_build_page2(data, styles))

    doc.build(story)
    return out_path


def run_all_tearsheets(tickers: list[str] | None = None) -> list[Path]:
    """Generate tearsheets for all companies (or a subset)."""
    conn = sqlite3.connect(str(DB_PATH))

    if tickers is None:
        rows = conn.execute("SELECT id FROM companies ORDER BY id").fetchall()
        tickers = [r[0] for r in rows]

    generated = []
    failed    = []

    logger.info("Generating %d tearsheets...", len(tickers))
    for i, ticker in enumerate(tickers, 1):
        try:
            path = generate_tearsheet(ticker, conn)
            generated.append(path)
            if i % 10 == 0 or i == len(tickers):
                logger.info("  Progress: %d / %d", i, len(tickers))
        except Exception as e:
            logger.error("  Failed %s: %s", ticker, e)
            failed.append(ticker)

    conn.close()

    print(f"\n{'='*50}")
    print("TEARSHEET GENERATOR COMPLETE")
    print(f"{'='*50}")
    print(f"  Generated : {len(generated)} PDFs")
    print(f"  Failed    : {len(failed)}")
    if failed:
        print(f"  Failed IDs: {failed}")
    print(f"  Output dir: {REPORTS_DIR}")

    return generated


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single company mode
        ticker = sys.argv[1].upper()
        conn   = sqlite3.connect(str(DB_PATH))
        path   = generate_tearsheet(ticker, conn)
        conn.close()
        print(f"Tearsheet written: {path}")
    else:
        run_all_tearsheets()
