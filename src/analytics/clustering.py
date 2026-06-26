"""
src/analytics/clustering.py — Statistical Analysis & Clustering Module
Sprint 6 / Module 10

KMeans clustering (5 clusters), cluster profiling, correlation matrix,
outlier detection (Z-score), portfolio-level statistics (P10-P90).

Usage:
    python src/analytics/clustering.py
"""

import sqlite3
import logging
from pathlib import Path

import pandas as pd
import numpy as np

BASE_DIR   = Path(__file__).resolve().parents[2]
DB_PATH    = BASE_DIR / "data" / "nifty100.db"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("clustering")

# Features for KMeans clustering
CLUSTER_FEATURES = [
    "return_on_equity_pct",
    "debt_to_equity",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "operating_profit_margin_pct",
]

# 10 core KPIs for portfolio statistics
PORTFOLIO_KPIS = [
    "return_on_equity_pct",
    "return_on_capital_pct",
    "net_profit_margin_pct",
    "debt_to_equity",
    "interest_coverage",
    "asset_turnover",
    "free_cash_flow_cr",
    "revenue_cagr_5yr",
    "pat_cagr_5yr",
    "health_score",
]

# Descriptive cluster labels (assigned after profiling)
CLUSTER_LABELS = {
    0: "High-Quality Growth",
    1: "Defensive Dividend",
    2: "Leveraged Value",
    3: "Cyclical / Capital Intensive",
    4: "Turnaround / Weak",
}


def load_universe(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load latest-year computed_ratios for all companies."""
    df = pd.read_sql("""
        SELECT cr.company_id, c.company_name, s.broad_sector,
               cr.return_on_equity_pct, cr.return_on_capital_pct,
               cr.net_profit_margin_pct, cr.operating_profit_margin_pct,
               cr.debt_to_equity, cr.interest_coverage, cr.asset_turnover,
               cr.free_cash_flow_cr, cr.revenue_cagr_5yr, cr.pat_cagr_5yr,
               cr.eps_cagr_5yr, cr.health_score, cr.health_band,
               cr.capital_alloc_pattern, cr.cfo_to_pat_ratio
        FROM computed_ratios cr
        JOIN companies c ON cr.company_id = c.id
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
    """, conn)
    # Winsorise extreme ROE
    df["return_on_equity_pct"] = df["return_on_equity_pct"].clip(upper=200)
    return df


def run_kmeans_clustering(df: pd.DataFrame, n_clusters: int = 5) -> pd.DataFrame:
    """
    Run KMeans clustering on CLUSTER_FEATURES.
    Returns df with cluster_id and cluster_name columns added.
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans

    df = df.copy()
    # Only cluster companies with all features available
    feat_df = df[CLUSTER_FEATURES].copy()
    for col in CLUSTER_FEATURES:
        feat_df[col] = pd.to_numeric(feat_df[col], errors="coerce")

    # Fill missing with column median for clustering
    medians = feat_df.median()
    feat_df = feat_df.fillna(medians)

    # Winsorise D/E at 10 for non-financial
    feat_df["debt_to_equity"] = feat_df["debt_to_equity"].clip(upper=10)

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(feat_df)

    # KMeans with fixed seed for reproducibility
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)

    df["cluster_id"]           = labels
    df["distance_from_centroid"] = np.min(km.transform(X_scaled), axis=1).round(4)

    # Elbow method SSE (for logging)
    logger.info("KMeans inertia (SSE): %.2f", km.inertia_)

    # Profile clusters: compute mean ROE per cluster to assign descriptive labels
    cluster_profiles = df.groupby("cluster_id")["return_on_equity_pct"].mean()
    roe_ranked = cluster_profiles.rank(ascending=False)

    # Assign labels based on relative quality ordering
    # Top ROE cluster = High-Quality Growth, Bottom = Turnaround/Weak
    label_map = {}
    sorted_clusters = cluster_profiles.sort_values(ascending=False).index.tolist()
    label_names = [
        "High-Quality Growth",
        "Defensive Dividend",
        "Cyclical / Capital Intensive",
        "Leveraged Value",
        "Turnaround / Weak",
    ]
    for i, cluster_id in enumerate(sorted_clusters):
        label_map[cluster_id] = label_names[min(i, len(label_names) - 1)]

    df["cluster_name"] = df["cluster_id"].map(label_map)
    return df


def compute_cluster_profiles(clustered_df: pd.DataFrame) -> pd.DataFrame:
    """Mean/median of each feature per cluster."""
    numeric_cols = CLUSTER_FEATURES + ["health_score", "free_cash_flow_cr"]
    numeric_cols = [c for c in numeric_cols if c in clustered_df.columns]

    profiles = clustered_df.groupby(["cluster_id", "cluster_name"])[numeric_cols].agg(
        ["mean", "median"]
    ).round(2)
    profiles.columns = ["_".join(c) for c in profiles.columns]
    return profiles.reset_index()


def compute_correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation of 10 KPIs across all companies."""
    kpi_cols = [c for c in PORTFOLIO_KPIS if c in df.columns]
    corr = df[kpi_cols].apply(pd.to_numeric, errors="coerce").corr(method="pearson")
    return corr.round(4)


def detect_outliers(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Z-score outlier detection per metric per sector.
    |Z| > 3 → 'Outlier' flag.
    """
    df = pd.read_sql("""
        SELECT cr.company_id, s.broad_sector,
               cr.return_on_equity_pct, cr.net_profit_margin_pct,
               cr.debt_to_equity, cr.revenue_cagr_5yr, cr.health_score
        FROM computed_ratios cr
        LEFT JOIN sectors s ON cr.company_id = s.company_id
        WHERE cr.year = (
            SELECT MAX(year) FROM computed_ratios cr2
            WHERE cr2.company_id = cr.company_id
        )
    """, conn)
    df["return_on_equity_pct"] = df["return_on_equity_pct"].clip(upper=200)

    metrics = ["return_on_equity_pct", "net_profit_margin_pct",
               "debt_to_equity", "revenue_cagr_5yr", "health_score"]
    rows = []
    for metric in metrics:
        for sector, grp in df.groupby("broad_sector"):
            vals = pd.to_numeric(grp[metric], errors="coerce").dropna()
            if len(vals) < 3:
                continue
            mean, std = vals.mean(), vals.std()
            if std == 0:
                continue
            for idx in grp.index:
                raw = grp.loc[idx, metric]
                if pd.isna(raw):
                    continue
                z = abs((float(raw) - mean) / std)
                if z > 3:
                    rows.append({
                        "company_id":   grp.loc[idx, "company_id"],
                        "metric":       metric,
                        "value":        round(float(raw), 2),
                        "z_score":      round(z, 2),
                        "sector":       sector,
                        "sector_mean":  round(mean, 2),
                        "sector_std":   round(std, 2),
                    })

    return pd.DataFrame(rows)


def compute_portfolio_stats(df: pd.DataFrame) -> pd.DataFrame:
    """P10/P25/P50/P75/P90 percentile table for all 10 KPIs."""
    kpi_cols = [c for c in PORTFOLIO_KPIS if c in df.columns]
    stats_rows = []
    for col in kpi_cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        stats_rows.append({
            "metric": col,
            "P10":    round(series.quantile(0.10), 2),
            "P25":    round(series.quantile(0.25), 2),
            "P50":    round(series.quantile(0.50), 2),
            "P75":    round(series.quantile(0.75), 2),
            "P90":    round(series.quantile(0.90), 2),
            "mean":   round(series.mean(), 2),
            "std":    round(series.std(), 2),
            "count":  int(series.count()),
        })
    return pd.DataFrame(stats_rows)


def run_clustering_module() -> dict:
    """Full clustering and statistical analysis pipeline."""
    import time
    t0 = time.time()
    conn = sqlite3.connect(str(DB_PATH))

    universe = load_universe(conn)
    logger.info("Universe loaded: %d companies", len(universe))

    # ── KMeans clustering ─────────────────────────────────────────────────────
    logger.info("Running KMeans (k=5)...")
    clustered = run_kmeans_clustering(universe, n_clusters=5)

    cluster_labels_df = clustered[[
        "company_id", "cluster_id", "cluster_name",
        "distance_from_centroid", "broad_sector"
    ]].copy()
    cluster_labels_df.to_csv(OUTPUT_DIR / "cluster_labels.csv", index=False)

    # ── Cluster profiles ─────────────────────────────────────────────────────
    profiles = compute_cluster_profiles(clustered)
    profiles.to_csv(OUTPUT_DIR / "cluster_profiles.csv", index=False)

    # ── Correlation matrix ────────────────────────────────────────────────────
    logger.info("Computing correlation matrix...")
    corr = compute_correlation_matrix(universe)
    corr.to_csv(OUTPUT_DIR / "correlation_matrix.csv")
    logger.info("Correlation matrix: %s", corr.shape)

    # ── Outlier detection ─────────────────────────────────────────────────────
    logger.info("Detecting outliers (Z>3)...")
    outliers = detect_outliers(conn)
    outliers.to_csv(OUTPUT_DIR / "outlier_report.csv", index=False)

    # ── Portfolio statistics ──────────────────────────────────────────────────
    logger.info("Computing portfolio statistics...")
    port_stats = compute_portfolio_stats(universe)
    port_stats.to_csv(OUTPUT_DIR / "portfolio_stats.csv", index=False)

    # Write clustered data to SQLite for API
    clustered.to_sql("company_clusters", conn, if_exists="replace", index=False)
    port_stats.to_sql("portfolio_stats", conn, if_exists="replace", index=False)

    conn.close()
    elapsed = round(time.time() - t0, 2)

    print(f"\n{'='*55}")
    print("CLUSTERING MODULE COMPLETE")
    print(f"{'='*55}")
    print(f"\n  Cluster Distribution:")
    for name, grp in cluster_labels_df.groupby("cluster_name"):
        print(f"    {name:<32} {len(grp):>3} companies")
    print(f"\n  Outliers detected  : {len(outliers)}")
    print(f"  Portfolio stats    : {len(port_stats)} KPIs")
    print(f"  Runtime            : {elapsed}s")
    print(f"\n  cluster_labels.csv   : {OUTPUT_DIR}/cluster_labels.csv")
    print(f"  cluster_profiles.csv : {OUTPUT_DIR}/cluster_profiles.csv")
    print(f"  correlation_matrix.csv: {OUTPUT_DIR}/correlation_matrix.csv")
    print(f"  outlier_report.csv   : {OUTPUT_DIR}/outlier_report.csv")
    print(f"  portfolio_stats.csv  : {OUTPUT_DIR}/portfolio_stats.csv")

    return {
        "cluster_labels": cluster_labels_df,
        "profiles":       profiles,
        "correlation":    corr,
        "outliers":       outliers,
        "portfolio_stats":port_stats,
    }


if __name__ == "__main__":
    run_clustering_module()
