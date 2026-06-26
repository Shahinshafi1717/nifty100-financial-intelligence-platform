"""
utils/charts.py — Reusable Plotly chart builders for all 8 dashboard screens.
"""
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

PRIMARY = "#4F8EF7"
SUCCESS = "#2ECC71"
DANGER  = "#E74C3C"
WARNING = "#F39C12"
PURPLE  = "#9B59B6"
TEAL    = "#1ABC9C"
GREY    = "#95A5A6"
BG      = "#0E1117"
SECTOR_COLOURS = px.colors.qualitative.Plotly

CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#E0E0E0", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
)

METRIC_LABELS = {
    "return_on_equity_pct":        "ROE (%)",
    "return_on_capital_pct":       "ROCE (%)",
    "net_profit_margin_pct":       "Net Profit Margin (%)",
    "operating_profit_margin_pct": "OPM (%)",
    "debt_to_equity":              "Debt / Equity",
    "free_cash_flow_cr":           "Free Cash Flow (₹ Cr)",
    "revenue_cagr_5yr":            "Revenue CAGR 5yr (%)",
    "pat_cagr_5yr":                "PAT CAGR 5yr (%)",
    "health_score":                "Health Score",
    "interest_coverage":           "Interest Coverage (×)",
    "sales":                       "Revenue (₹ Cr)",
    "net_profit":                  "Net Profit (₹ Cr)",
    "eps":                         "EPS (₹)",
    "borrowings":                  "Borrowings (₹ Cr)",
}

RADAR_LABELS = {
    "return_on_equity_pct":        "ROE",
    "return_on_capital_pct":       "ROCE",
    "net_profit_margin_pct":       "NPM",
    "operating_profit_margin_pct": "OPM",
    "debt_to_equity":              "D/E (inv)",
    "interest_coverage":           "ICR",
    "free_cash_flow_cr":           "FCF",
    "revenue_cagr_5yr":            "Rev CAGR",
    "pat_cagr_5yr":                "PAT CAGR",
    "health_score":                "Health",
}

def sector_donut(sector_df):
    fig = go.Figure(go.Pie(
        labels=sector_df["broad_sector"], values=sector_df["company_count"],
        hole=0.55, textinfo="label+percent", textfont_size=11,
        marker=dict(colors=SECTOR_COLOURS, line=dict(color=BG, width=2)),
    ))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="Companies by Sector", font=dict(size=14), x=0.5),
        showlegend=False, height=320)
    return fig

def health_score_histogram(universe):
    fig = go.Figure(go.Histogram(
        x=universe["health_score"].dropna(), nbinsx=20,
        marker_color=PRIMARY, opacity=0.85,
    ))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="Health Score Distribution", font=dict(size=14), x=0.5),
        xaxis_title="Health Score (0–100)", yaxis_title="Companies", height=300)
    return fig

def revenue_profit_bar(pl):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=pl["year"], y=pl["sales"], name="Revenue (Cr)",
                         marker_color=PRIMARY, opacity=0.9))
    fig.add_trace(go.Bar(x=pl["year"], y=pl["net_profit"], name="Net Profit (Cr)",
                         marker_color=SUCCESS, opacity=0.9))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="Revenue & Net Profit (₹ Cr)", font=dict(size=14), x=0.5),
        barmode="group", xaxis_tickangle=-45, height=320,
        )
    return fig

def roe_roce_line(ratios):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ratios["year"], y=ratios["return_on_equity_pct"].clip(upper=200),
        name="ROE %", mode="lines+markers",
        line=dict(color=PRIMARY, width=2), marker=dict(size=6),
    ))
    fig.add_trace(go.Scatter(
        x=ratios["year"], y=ratios["return_on_capital_pct"],
        name="ROCE %", mode="lines+markers",
        line=dict(color=TEAL, width=2, dash="dash"), marker=dict(size=6),
    ))
    fig.add_hline(y=15, line_dash="dot", line_color=GREY,
                  annotation_text="15% benchmark", annotation_position="bottom right")
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="ROE vs ROCE Trend", font=dict(size=14), x=0.5),
        yaxis_title="%", xaxis_tickangle=-45, height=300)
    return fig

def balance_sheet_stacked(bs):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=bs["year"],
                         y=(bs["equity_capital"] + bs["reserves"].fillna(0)),
                         name="Equity", marker_color=SUCCESS))
    fig.add_trace(go.Bar(x=bs["year"], y=bs["borrowings"].fillna(0),
                         name="Borrowings", marker_color=DANGER))
    fig.add_trace(go.Bar(x=bs["year"], y=bs["other_liabilities"].fillna(0),
                         name="Other Liabilities", marker_color=GREY))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="Balance Sheet Composition (₹ Cr)", font=dict(size=14), x=0.5),
        barmode="stack", xaxis_tickangle=-45, height=300)
    return fig

def cashflow_bar(cf):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=cf["year"], y=cf["operating_activity"],
                         name="CFO", marker_color=SUCCESS))
    fig.add_trace(go.Bar(x=cf["year"], y=cf["investing_activity"],
                         name="CFI", marker_color=DANGER))
    fig.add_trace(go.Bar(x=cf["year"], y=cf["financing_activity"],
                         name="CFF", marker_color=WARNING))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="Cash Flow Statement (₹ Cr)", font=dict(size=14), x=0.5),
        barmode="group", xaxis_tickangle=-45, height=300)
    return fig

def peer_radar(group_df, selected_company):
    metrics = [m for m in RADAR_LABELS if m in group_df.columns]
    labels  = [RADAR_LABELS[m] for m in metrics]

    def norm(series, invert=False):
        s = pd.to_numeric(series, errors="coerce").fillna(0)
        mn, mx = s.min(), s.max()
        if mx == mn:
            return pd.Series([50.0]*len(s), index=s.index)
        n = (s - mn) / (mx - mn) * 100
        return (100 - n) if invert else n

    norm_df = group_df[["company_id"] + metrics].copy()
    for m in metrics:
        norm_df[m] = norm(group_df[m], invert=(m == "debt_to_equity"))

    group_avg = norm_df[metrics].mean().tolist()
    row = norm_df[norm_df["company_id"] == selected_company]
    if row.empty:
        return go.Figure()
    company_vals = row[metrics].iloc[0].tolist()

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=group_avg + [group_avg[0]], theta=labels + [labels[0]],
        fill="toself", fillcolor="rgba(149,165,166,0.15)",
        line=dict(color=GREY, width=1.5), name="Group Avg",
    ))
    fig.add_trace(go.Scatterpolar(
        r=company_vals + [company_vals[0]], theta=labels + [labels[0]],
        fill="toself", fillcolor="rgba(79,142,247,0.2)",
        line=dict(color=PRIMARY, width=2), name=selected_company,
    ))
    fig.update_layout(**CHART_LAYOUT,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(visible=True, range=[0,100],
                            gridcolor="#2A3547", tickfont=dict(size=9)),
            angularaxis=dict(gridcolor="#2A3547"),
        ),
        title=dict(text=f"{selected_company} vs Peer Group",
                   font=dict(size=14), x=0.5),
        height=400)
    return fig

def trend_sparkline(history_df, metrics, title="10-Year Trend"):
    colours = [PRIMARY, TEAL, SUCCESS, WARNING, PURPLE]
    fig = go.Figure()
    for i, metric in enumerate(metrics):
        if metric not in history_df.columns:
            continue
        col   = pd.to_numeric(history_df[metric], errors="coerce")
        label = METRIC_LABELS.get(metric, metric)
        fig.add_trace(go.Scatter(
            x=history_df["year"], y=col, name=label,
            mode="lines+markers",
            line=dict(color=colours[i % len(colours)], width=2),
            marker=dict(size=5),
        ))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text=title, font=dict(size=14), x=0.5),
        xaxis_tickangle=-45, height=340,
        )
    return fig

def sector_bubble(universe):
    df = universe.dropna(subset=["return_on_equity_pct","market_cap_crore"]).copy()
    df["return_on_equity_pct"] = df["return_on_equity_pct"].clip(upper=100)
    fig = px.scatter(df, x="market_cap_crore", y="return_on_equity_pct",
        size="market_cap_crore", color="broad_sector",
        hover_name="company_id",
        hover_data={"company_name": True, "health_score": True, "market_cap_crore": ":.0f"},
        size_max=40, color_discrete_sequence=SECTOR_COLOURS)
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="Market Cap vs ROE by Sector", font=dict(size=14), x=0.5),
        xaxis_title="Market Cap (₹ Cr)", yaxis_title="ROE (%)", height=420)
    return fig

def sector_bar_kpi(sector_df, kpi, label):
    df = sector_df.dropna(subset=[kpi]).sort_values(kpi, ascending=True)
    colours = [SUCCESS if v >= 0 else DANGER for v in df[kpi]]
    fig = go.Figure(go.Bar(
        x=df[kpi], y=df["broad_sector"], orientation="h",
        marker_color=colours,
        text=df[kpi].round(1).astype(str), textposition="outside",
    ))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text=f"Sector Median — {label}", font=dict(size=14), x=0.5),
        xaxis_title=label, height=340)
    return fig

def capital_allocation_treemap(cap_df):
    df = cap_df.dropna(subset=["capital_alloc_pattern"]).copy()
    df["health_score"] = df["health_score"].fillna(50)
    short_map = {
        "Reinvestor — ops funding growth + returning capital": "Reinvestor",
        "Leveraged Growth — borrowing to invest":              "Leveraged Growth",
        "Distress — burning cash, raising funds to survive":   "Distress",
        "Startup / Distress — investing while losing cash":    "Startup/Distress",
        "Asset Harvester — divesting + returning capital":     "Asset Harvester",
        "Cash Accumulator — ops positive, selling assets, raising funds": "Cash Accumulator",
        "Restructuring — selling assets to repay debt":        "Restructuring",
        "Deep Distress — negative on all three flows":         "Deep Distress",
        "Insufficient Data":                                   "No Data",
    }
    df["pattern_short"] = df["capital_alloc_pattern"].map(short_map).fillna(
        df["capital_alloc_pattern"])
    fig = px.treemap(df, path=["pattern_short", "company_id"],
        values="health_score", color="health_score",
        color_continuous_scale=["#E74C3C","#F39C12","#2ECC71"],
        range_color=[0,100], color_continuous_midpoint=50,
        hover_data={"broad_sector": True, "capital_alloc_pattern": True})
    fig.update_traces(textinfo="label", textfont_size=11)
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="Capital Allocation Map — 92 Companies",
                   font=dict(size=14), x=0.5),
        height=480,
        coloraxis_colorbar=dict(title="Health Score"))
    return fig

def pe_trend_line(mc, company_id):
    fig = go.Figure(go.Scatter(
        x=mc["year"].astype(str), y=mc["pe_ratio"],
        mode="lines+markers",
        line=dict(color=PRIMARY, width=2), marker=dict(size=7),
        fill="tozeroy", fillcolor="rgba(79,142,247,0.1)",
    ))
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text=f"{company_id} — P/E Trend", font=dict(size=14), x=0.5),
        yaxis_title="P/E Ratio (×)", xaxis_title="Year", height=280)
    return fig

def pb_roe_scatter(universe):
    df = universe.dropna(subset=["pb_ratio","return_on_equity_pct"]).copy()
    df["return_on_equity_pct"] = df["return_on_equity_pct"].clip(upper=100)
    fig = px.scatter(df, x="pb_ratio", y="return_on_equity_pct",
        size="market_cap_crore", color="broad_sector",
        hover_name="company_id",
        hover_data={"company_name": True, "health_score": True},
        size_max=35, color_discrete_sequence=SECTOR_COLOURS)
    fig.update_layout(**CHART_LAYOUT,
        title=dict(text="P/B vs ROE — All Companies", font=dict(size=14), x=0.5),
        xaxis_title="Price / Book (×)", yaxis_title="ROE (%)", height=400)
    return fig
