"""
src/reports/sector_report.py — Sector PDF Report Generator
Sprint 5 / Module 8.3

Generates one PDF per broad sector (11 total):
  - Sector header with median KPI table
  - Best/worst companies highlighted
  - Company list with key metrics

Usage:
    python src/reports/sector_report.py
"""

import sqlite3
import logging
from pathlib import Path

import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable,
)

BASE_DIR    = Path(__file__).resolve().parents[2]
DB_PATH     = BASE_DIR / "data" / "nifty100.db"
REPORTS_DIR = BASE_DIR / "reports" / "sector"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("sector_report")

# Colours
C_BLUE  = colors.HexColor("#4F8EF7")
C_GREEN = colors.HexColor("#2ECC71")
C_RED   = colors.HexColor("#E74C3C")
C_DARK  = colors.HexColor("#0D1117")
C_CARD  = colors.HexColor("#161B22")
C_BORDER= colors.HexColor("#30363D")
C_WHITE = colors.white
C_TEXT  = colors.HexColor("#E6EDF3")
C_GREY  = colors.HexColor("#8B949E")

PAGE_W, PAGE_H = A4
MARGIN = 1.5 * cm
UW     = PAGE_W - 2 * MARGIN


def _style(name, **kwargs):
    defaults = dict(fontName="Helvetica", fontSize=9,
                    textColor=C_TEXT, spaceAfter=3)
    defaults.update(kwargs)
    return ParagraphStyle(name, **defaults)


def _fmt(val, suffix="", dec=1):
    if val is None or (isinstance(val, float) and val != val):
        return "—"
    try:
        return f"{float(val):.{dec}f}{suffix}"
    except Exception:
        return "—"


def _band_colour(band):
    return {
        "Excellent": C_GREEN,
        "Good":      colors.HexColor("#F39C12"),
        "Moderate":  colors.HexColor("#E67E22"),
        "Weak":      C_RED,
    }.get(str(band), C_GREY)


def generate_sector_report(sector_name: str, sector_df: pd.DataFrame,
                            all_df: pd.DataFrame) -> Path:
    """Generate a PDF for one sector."""
    safe_name = sector_name.replace("/", "_").replace(" ", "_")
    from datetime import date
    date_str  = date.today().strftime("%Y%m%d")
    out_path  = REPORTS_DIR / f"{safe_name}_report_{date_str}.pdf"

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title=f"{sector_name} Sector Report",
    )

    title_style   = _style("title", fontName="Helvetica-Bold",
                            fontSize=18, textColor=C_WHITE, spaceAfter=4)
    section_style = _style("section", fontName="Helvetica-Bold",
                            fontSize=11, textColor=C_BLUE, spaceBefore=10)
    body_style    = _style("body", fontSize=9)
    small_style   = _style("small", fontSize=7, textColor=C_GREY)

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph(f"📊 {sector_name}", title_style))
    story.append(Paragraph(
        f"Nifty 100 Sector Analysis  |  {len(sector_df)} Companies  |  {date_str}",
        _style("sub", fontSize=9, textColor=C_GREY)))
    story.append(HRFlowable(width=UW, color=C_BLUE, thickness=1.5))
    story.append(Spacer(1, 8))

    # ── Sector median KPI summary ─────────────────────────────────────────────
    story.append(Paragraph("SECTOR MEDIAN KPIs", section_style))
    med_roe  = _fmt(sector_df["return_on_equity_pct"].clip(upper=200).median(), "%")
    med_npm  = _fmt(sector_df["net_profit_margin_pct"].median(), "%")
    med_de   = _fmt(sector_df["debt_to_equity"].median())
    med_h    = _fmt(sector_df["health_score"].median(), "/100", 0)
    med_cagr = _fmt(sector_df["revenue_cagr_5yr"].median(), "%")
    med_fcf  = _fmt(sector_df["free_cash_flow_cr"].median(), " Cr", 0)

    kpi_data = [
        ["Median ROE", "Median NPM", "Median D/E", "Avg Health", "Median Rev CAGR 5yr", "Median FCF"],
        [med_roe,      med_npm,      med_de,        med_h,        med_cagr,               med_fcf],
    ]
    kpi_t = Table(kpi_data, colWidths=[UW / 6] * 6)
    kpi_t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND",    (0, 1), (-1, 1), C_CARD),
        ("TEXTCOLOR",     (0, 1), (-1, 1), C_WHITE),
        ("FONTNAME",      (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_t)
    story.append(Spacer(1, 10))

    # ── Best / Worst highlight ────────────────────────────────────────────────
    story.append(Paragraph("SECTOR RANKING BY HEALTH SCORE", section_style))
    ranked = sector_df.sort_values("health_score", ascending=False).reset_index(drop=True)
    ranked.index = ranked.index + 1

    best  = ranked.head(3)
    worst = ranked.tail(3).sort_values("health_score")

    hw_data = [["🏆 BEST IN SECTOR", "", "", "⚠️ NEEDS ATTENTION", "", ""]]
    hw_data.append(["Ticker", "Health", "Band", "Ticker", "Health", "Band"])
    max_rows = max(len(best), len(worst))
    for i in range(max_rows):
        b = best.iloc[i]  if i < len(best)  else None
        w = worst.iloc[i] if i < len(worst) else None
        hw_data.append([
            b["company_id"]   if b is not None else "",
            _fmt(b["health_score"], "/100", 0) if b is not None else "",
            str(b["health_band"])              if b is not None else "",
            w["company_id"]   if w is not None else "",
            _fmt(w["health_score"], "/100", 0) if w is not None else "",
            str(w["health_band"])              if w is not None else "",
        ])

    hw_t = Table(hw_data, colWidths=[UW*0.18, UW*0.1, UW*0.1,
                                      UW*0.18, UW*0.1, UW*0.1,
                                      UW*0.24])
    hw_t.setStyle(TableStyle([
        ("SPAN",          (0, 0), (2, 0)),
        ("SPAN",          (3, 0), (5, 0)),
        ("BACKGROUND",    (0, 0), (2, 0), C_GREEN),
        ("BACKGROUND",    (3, 0), (5, 0), C_RED),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 1), "Helvetica-Bold"),
        ("BACKGROUND",    (0, 1), (-1, 1), C_CARD),
        ("TEXTCOLOR",     (0, 1), (-1, -1), C_TEXT),
        ("BACKGROUND",    (0, 2), (-1, -1), C_DARK),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(hw_t)
    story.append(Spacer(1, 10))

    # ── Full company table ────────────────────────────────────────────────────
    story.append(Paragraph("ALL COMPANIES IN SECTOR", section_style))

    col_headers = ["#","Ticker","Name","Sub-Sector","Health","Band",
                   "ROE%","NPM%","D/E","RevCAGR5%","FCF(Cr)","Pattern"]
    col_widths  = [UW*0.03, UW*0.08, UW*0.15, UW*0.12,
                   UW*0.06, UW*0.07, UW*0.07, UW*0.07,
                   UW*0.06, UW*0.08, UW*0.08, UW*0.13]

    table_data = [col_headers]
    for rank, (_, row) in enumerate(ranked.iterrows(), 1):
        pattern = str(row.get("capital_alloc_pattern","—"))
        short_p = {
            "Reinvestor — ops funding growth + returning capital": "Reinvestor",
            "Leveraged Growth — borrowing to invest":              "Leveraged",
            "Distress — burning cash, raising funds to survive":   "Distress",
        }.get(pattern, pattern[:15])
        table_data.append([
            str(rank),
            str(row["company_id"]),
            str(row.get("company_name",""))[:18],
            str(row.get("sub_sector",""))[:14],
            _fmt(row.get("health_score"), "", 0),
            str(row.get("health_band","—")),
            _fmt(row.get("return_on_equity_pct"), "%"),
            _fmt(row.get("net_profit_margin_pct"), "%"),
            _fmt(row.get("debt_to_equity")),
            _fmt(row.get("revenue_cagr_5yr"), "%"),
            _fmt(row.get("free_cash_flow_cr"), "", 0),
            short_p,
        ])

    full_t = Table(table_data, colWidths=col_widths)
    style_cmds = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.2, C_BORDER),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("WORDWRAP",      (0, 0), (-1, -1), True),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_CARD, C_DARK]),
        ("TEXTCOLOR",     (0, 1), (-1, -1), C_TEXT),
    ]
    # Colour health band cells
    for i, (_, row) in enumerate(ranked.iterrows(), 1):
        band_col = _band_colour(row.get("health_band"))
        style_cmds.append(("TEXTCOLOR", (5, i), (5, i), band_col))
    full_t.setStyle(TableStyle(style_cmds))
    story.append(full_t)

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width=UW, color=C_BORDER, thickness=0.3))
    story.append(Paragraph(
        "Nifty 100 Financial Intelligence Platform — Internal Use Only. "
        "All monetary values in ₹ Crore unless stated.",
        _style("footer", fontSize=6, textColor=C_GREY)))

    doc.build(story)
    return out_path


def run_all_sector_reports() -> list[Path]:
    """Generate PDF reports for all 11 sectors."""
    conn = sqlite3.connect(str(DB_PATH))
    universe = pd.read_sql("""
        SELECT cr.company_id, c.company_name,
               s.broad_sector, s.sub_sector,
               cr.return_on_equity_pct, cr.net_profit_margin_pct,
               cr.debt_to_equity, cr.free_cash_flow_cr,
               cr.revenue_cagr_5yr, cr.health_score, cr.health_band,
               cr.capital_alloc_pattern
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
    """, conn)
    conn.close()

    # Winsorise ROE
    universe["return_on_equity_pct"] = universe["return_on_equity_pct"].clip(upper=200)

    generated = []
    sectors   = universe["broad_sector"].dropna().unique()
    logger.info("Generating sector reports for %d sectors...", len(sectors))

    for sector in sorted(sectors):
        sector_df = universe[universe["broad_sector"] == sector].copy()
        if sector_df.empty:
            continue
        try:
            path = generate_sector_report(sector, sector_df, universe)
            generated.append(path)
            logger.info("  ✅ %s — %d companies", sector, len(sector_df))
        except Exception as e:
            logger.error("  ❌ %s: %s", sector, e)

    print(f"\n{'='*50}")
    print("SECTOR REPORTS COMPLETE")
    print(f"{'='*50}")
    print(f"  Sectors generated : {len(generated)}")
    print(f"  Output dir        : {REPORTS_DIR}")

    return generated


if __name__ == "__main__":
    run_all_sector_reports()
