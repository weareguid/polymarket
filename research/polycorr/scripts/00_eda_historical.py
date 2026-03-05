"""
Phase 0: EDA completo del dataset histórico de Polymarket.

Objetivo: entender qué datos tenemos, sus limitaciones, y qué podemos analizar
para diseñar el modelo de correlaciones con stocks.

Outputs:
- Prints detallados con estadísticas
- outputs/eda_summary.md  → resumen de hallazgos
- outputs/eda_*.png       → gráficas de exploración
"""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parents[3]  # /repos/Polymarket
CSV_PATH = BASE / "data/historical/markets_historical_20260220.csv"
RELEVANT_CSV = BASE / "data/historical/relevant_markets.csv"
OUTPUT_DIR = BASE / "outputs/research/eda"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FINANCIAL_CATEGORIES = {"geopolitical", "macro", "us_politics", "corporate", "ai", "energy", "defense", "trade", "international", "commodities", "regulation"}

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "#f8f9fa",
    "axes.grid": True,
    "grid.color": "#e0e0e0",
    "font.size": 11,
})


def fmt(n):
    if n >= 1e9: return f"${n/1e9:.1f}B"
    if n >= 1e6: return f"${n/1e6:.1f}M"
    if n >= 1e3: return f"${n/1e3:.0f}K"
    return f"${n:.0f}"


# ===========================================================================
# LOAD
# ===========================================================================
print("=" * 70)
print("EDA: Historical Polymarket Dataset")
print("=" * 70)

print("\n[1] Loading full dataset...")
df_all = pd.read_csv(CSV_PATH)
df_all["volume_total"] = pd.to_numeric(df_all["volume_total"], errors="coerce").fillna(0)
df_all["volume_24h"] = pd.to_numeric(df_all["volume_24h"], errors="coerce").fillna(0)
df_all["yes_price_final"] = pd.to_numeric(df_all["yes_price_final"], errors="coerce")
df_all["no_price_final"] = pd.to_numeric(df_all["no_price_final"], errors="coerce")
df_all["liquidity"] = pd.to_numeric(df_all["liquidity"], errors="coerce").fillna(0)
df_all["start_date"] = pd.to_datetime(df_all["start_date"], utc=True, errors="coerce")
df_all["end_date"] = pd.to_datetime(df_all["end_date"], utc=True, errors="coerce")
df_all["closed_time"] = pd.to_datetime(df_all["closed_time"], utc=True, errors="coerce")
df_all["created_at"] = pd.to_datetime(df_all["created_at"], utc=True, errors="coerce")

# Market duration
df_all["duration_days"] = ((df_all["end_date"] - df_all["start_date"]).dt.total_seconds() / 86400).clip(lower=0)
df_all["avg_daily_vol"] = df_all["volume_total"] / df_all["duration_days"].replace(0, 1)

print(f"  Total rows: {len(df_all):,}")
print(f"  Date range: {df_all['start_date'].min().date()} → {df_all['start_date'].max().date()}")
print(f"  Total volume across all markets: {fmt(df_all['volume_total'].sum())}")
print(f"  Columns: {list(df_all.columns)}")

# Resolved
df_resolved = df_all[df_all["resolved"] == True]
df_open = df_all[df_all["resolved"] == False]
print(f"\n  Resolved markets: {len(df_resolved):,} ({len(df_resolved)/len(df_all)*100:.1f}%)")
print(f"  Open markets: {len(df_open):,}")


# ===========================================================================
# SECTION 2: VOLUME DISTRIBUTION
# ===========================================================================
print("\n[2] Volume distribution...")

vol_brackets = [
    ("$0 - $1K",       0, 1_000),
    ("$1K - $10K",     1_000, 10_000),
    ("$10K - $100K",   10_000, 100_000),
    ("$100K - $1M",    100_000, 1_000_000),
    ("$1M - $10M",     1_000_000, 10_000_000),
    ("$10M - $100M",   10_000_000, 100_000_000),
    ("$100M+",         100_000_000, 1e18),
]

print(f"\n  Volume bracket distribution (all {len(df_all):,} markets):")
for label, lo, hi in vol_brackets:
    n = ((df_all["volume_total"] >= lo) & (df_all["volume_total"] < hi)).sum()
    vol = df_all.loc[(df_all["volume_total"] >= lo) & (df_all["volume_total"] < hi), "volume_total"].sum()
    pct = n / len(df_all) * 100
    print(f"    {label:20s}: {n:7,} markets ({pct:5.1f}%) | Volume: {fmt(vol)}")

print(f"\n  Percentiles of volume_total:")
for p in [50, 75, 90, 95, 99, 99.9]:
    val = df_all["volume_total"].quantile(p/100)
    print(f"    P{p:5.1f}: {fmt(val)}")


# ===========================================================================
# SECTION 3: DATE ANALYSIS
# ===========================================================================
print("\n[3] Date analysis...")

df_all["year_start"] = df_all["start_date"].dt.year
df_all["month_start"] = df_all["start_date"].dt.to_period("M")

print("\n  Markets created per year:")
yearly = df_all.groupby("year_start").agg(
    n_markets=("id", "count"),
    total_volume=("volume_total", "sum"),
    avg_volume=("volume_total", "mean"),
).reset_index()
for _, row in yearly.iterrows():
    print(f"    {int(row['year_start'])}: {int(row['n_markets']):6,} markets | Vol: {fmt(row['total_volume'])} | Avg: {fmt(row['avg_volume'])}")

print("\n  Volume over time (quarterly):")
df_all["quarter"] = df_all["start_date"].dt.to_period("Q")
quarterly_vol = df_all.groupby("quarter")["volume_total"].sum().reset_index()
quarterly_vol = quarterly_vol[quarterly_vol["quarter"].notna()]
for _, row in quarterly_vol.tail(12).iterrows():
    print(f"    {row['quarter']}: {fmt(row['volume_total'])}")


# ===========================================================================
# SECTION 4: OUTCOME ANALYSIS
# ===========================================================================
print("\n[4] Outcome analysis (yes_price_final)...")

df_res = df_resolved.dropna(subset=["yes_price_final"])
print(f"\n  Resolved markets with final price: {len(df_res):,}")

yes_bins = [
    ("YES resolved (>90%)",   0.90, 1.01),
    ("NO resolved (<10%)",    -0.01, 0.10),
    ("Uncertain (10-90%)",    0.10, 0.90),
]
for label, lo, hi in yes_bins:
    n = ((df_res["yes_price_final"] >= lo) & (df_res["yes_price_final"] < hi)).sum()
    pct = n / len(df_res) * 100
    print(f"    {label}: {n:,} ({pct:.1f}%)")

print(f"\n  Mean yes_price_final: {df_res['yes_price_final'].mean():.3f}")
print(f"  Median yes_price_final: {df_res['yes_price_final'].median():.3f}")


# ===========================================================================
# SECTION 5: RELEVANT MARKETS EDA
# ===========================================================================
print("\n[5] Financially relevant markets (from Phase 1 filter)...")

df_rel = pd.read_csv(RELEVANT_CSV)
df_rel["volume_total"] = pd.to_numeric(df_rel["volume_total"], errors="coerce").fillna(0)
df_rel["yes_price_final"] = pd.to_numeric(df_rel["yes_price_final"], errors="coerce")
df_rel["start_date"] = pd.to_datetime(df_rel["start_date"], utc=True, errors="coerce")
df_rel["end_date"] = pd.to_datetime(df_rel["end_date"], utc=True, errors="coerce")
df_rel["duration_days"] = ((df_rel["end_date"] - df_rel["start_date"]).dt.total_seconds() / 86400).clip(lower=1)
df_rel["avg_daily_vol"] = df_rel["volume_total"] / df_rel["duration_days"]

print(f"\n  Total relevant markets: {len(df_rel):,}")
print(f"  Total volume: {fmt(df_rel['volume_total'].sum())}")
print(f"  Date range: {df_rel['start_date'].min().date()} → {df_rel['end_date'].max().date()}")

# By category
print("\n  By category:")
cat_stats = df_rel.groupby("event_category").agg(
    n=("id", "count"),
    total_vol=("volume_total", "sum"),
    avg_vol=("volume_total", "mean"),
    median_vol=("volume_total", "median"),
).sort_values("total_vol", ascending=False)

for cat, row in cat_stats.iterrows():
    print(f"    {cat:15s}: {int(row['n']):5,} mkts | Total: {fmt(row['total_vol'])} | Avg: {fmt(row['avg_vol'])} | Median: {fmt(row['median_vol'])}")

# Non-crypto relevant markets (these are the most useful for stock correlation)
df_fin = df_rel[df_rel["event_category"] != "crypto"].copy()
print(f"\n  Non-crypto relevant markets: {len(df_fin):,}")
print(f"  Total non-crypto volume: {fmt(df_fin['volume_total'].sum())}")

print("\n  Non-crypto by category:")
fin_stats = df_fin.groupby("event_category").agg(
    n=("id", "count"),
    total_vol=("volume_total", "sum"),
    avg_vol=("volume_total", "mean"),
).sort_values("total_vol", ascending=False)
for cat, row in fin_stats.iterrows():
    print(f"    {cat:15s}: {int(row['n']):5,} mkts | Total: {fmt(row['total_vol'])} | Avg: {fmt(row['avg_vol'])}")

# Volume distribution for non-crypto
print("\n  Volume brackets (non-crypto):")
for label, lo, hi in vol_brackets:
    n = ((df_fin["volume_total"] >= lo) & (df_fin["volume_total"] < hi)).sum()
    print(f"    {label:20s}: {n:5,} markets")


# ===========================================================================
# SECTION 6: TICKER ANALYSIS
# ===========================================================================
print("\n[6] Ticker coverage analysis...")

ticker_counts = {}
ticker_volume = {}
for _, row in df_rel.iterrows():
    try:
        tickers = json.loads(row["matched_tickers"]) if isinstance(row.get("matched_tickers"), str) else []
        for t in tickers:
            ticker_counts[t] = ticker_counts.get(t, 0) + 1
            ticker_volume[t] = ticker_volume.get(t, 0) + row["volume_total"]
    except Exception:
        pass

ticker_df = pd.DataFrame([
    {"ticker": t, "n_markets": ticker_counts[t], "total_vol": ticker_volume[t]}
    for t in ticker_counts
]).sort_values("total_vol", ascending=False)

print("\n  Top 20 tickers by total volume of related Polymarket markets:")
for _, row in ticker_df.head(20).iterrows():
    print(f"    {row['ticker']:12s}: {int(row['n_markets']):4,} markets | {fmt(row['total_vol'])} related volume")


# ===========================================================================
# SECTION 7: WHAT CAN WE ACTUALLY CORRELATE?
# ===========================================================================
print("\n[7] Data availability for correlation analysis...")

now = pd.Timestamp.now(tz="UTC")
cutoffs = {
    "All time (2021-2026)": (pd.Timestamp("2020-01-01", tz="UTC"), now),
    "Last 3 years (2023+)": (pd.Timestamp("2023-01-01", tz="UTC"), now),
    "Last 2 years (2024+)": (pd.Timestamp("2024-01-01", tz="UTC"), now),
    "Last 12 months": (now - pd.Timedelta(days=365), now),
    "Last 6 months": (now - pd.Timedelta(days=180), now),
    "Last 3 months": (now - pd.Timedelta(days=90), now),
}

print("\n  Non-crypto markets available per time window:")
for label, (start, end) in cutoffs.items():
    subset = df_fin[
        (df_fin["start_date"] >= start) &
        (df_fin["end_date"] <= end) &
        (df_fin["yes_price_final"].notna())
    ]
    with_high_vol = subset[subset["volume_total"] >= 500_000]
    print(f"\n    {label}:")
    print(f"      All resolved: {len(subset):,} markets | Vol: {fmt(subset['volume_total'].sum())}")
    print(f"      High-vol (>$500K): {len(with_high_vol):,} markets | Vol: {fmt(with_high_vol['volume_total'].sum())}")

print("\n\n  KEY FINDING: Volume_24h as proxy for daily activity")
print("  We have volume_24h at the time of snapshot (Feb 20, 2026).")
print("  For closed markets, this represents the last 24h before close (often 0).")
print("  For open markets at time of snapshot: vol_24h is recent trading activity.")

# Check volume_24h for open vs closed markets
df_all_open_at_snapshot = df_all[df_all["resolved"] == False]
df_all_closed = df_all[df_all["resolved"] == True]
print(f"\n  Open at snapshot time: {len(df_all_open_at_snapshot):,} markets")
print(f"    volume_24h mean: {fmt(df_all_open_at_snapshot['volume_24h'].mean())}")
print(f"    volume_24h > 0: {(df_all_open_at_snapshot['volume_24h'] > 0).sum():,}")
print(f"  Closed at snapshot: {len(df_all_closed):,}")
print(f"    volume_24h mean: {fmt(df_all_closed['volume_24h'].mean())}")


# ===========================================================================
# SECTION 8: DURATION ANALYSIS
# ===========================================================================
print("\n[8] Market duration analysis (non-crypto)...")

dur_stats = df_fin["duration_days"].describe()
print(f"\n  Duration percentiles (days):")
for p in [25, 50, 75, 90, 95, 99]:
    val = df_fin["duration_days"].quantile(p/100)
    print(f"    P{p}: {val:.0f} days")

dur_brackets = [
    ("1 day",     0, 2),
    ("2-7 days",  2, 7),
    ("1-4 weeks", 7, 28),
    ("1-3 months",28, 90),
    ("3-6 months",90, 180),
    ("6-12 months",180, 365),
    ("12+ months", 365, 9999),
]
print("\n  Duration distribution (non-crypto):")
for label, lo, hi in dur_brackets:
    n = ((df_fin["duration_days"] >= lo) & (df_fin["duration_days"] < hi)).sum()
    print(f"    {label:15s}: {n:5,} markets")


# ===========================================================================
# SECTION 9: PLOT GENERATION
# ===========================================================================
print("\n[9] Generating plots...")

fig, axes = plt.subplots(2, 3, figsize=(18, 11))
fig.suptitle("PolyCorr EDA — Historical Polymarket Data (2021-2026)", fontsize=14, fontweight="bold")

# ---- Plot 1: Volume by year ----
ax1 = axes[0, 0]
yearly_plot = df_all.groupby("year_start")["volume_total"].sum() / 1e9
yearly_plot = yearly_plot.dropna()
yearly_plot.index = yearly_plot.index.astype(int)
bars = ax1.bar(yearly_plot.index, yearly_plot.values, color="#4a90d9", alpha=0.85, edgecolor="white")
ax1.set_xlabel("Year")
ax1.set_ylabel("Total Volume ($B)")
ax1.set_title("Total Polymarket Volume by Year")
for bar, val in zip(bars, yearly_plot.values):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05, f"${val:.1f}B", ha="center", fontsize=9)

# ---- Plot 2: Volume distribution (log scale) ----
ax2 = axes[0, 1]
vol_data = df_all[df_all["volume_total"] > 0]["volume_total"]
ax2.hist(np.log10(vol_data), bins=50, color="#7ec8a0", alpha=0.85, edgecolor="white")
ax2.set_xlabel("log₁₀(Volume Total $)")
ax2.set_ylabel("Number of Markets")
ax2.set_title("Volume Distribution (log scale)\nAll 411k markets")
ax2.axvline(np.log10(50_000), color="#e87070", linestyle="--", label="$50K threshold")
ax2.axvline(np.log10(1_000_000), color="#9b59b6", linestyle="--", label="$1M threshold")
ax2.legend(fontsize=9)
ax2.set_xticks([3, 4, 5, 6, 7, 8, 9])
ax2.set_xticklabels(["$1K", "$10K", "$100K", "$1M", "$10M", "$100M", "$1B"])

# ---- Plot 3: Category breakdown (non-crypto) ----
ax3 = axes[0, 2]
cat_vol = df_fin.groupby("event_category")["volume_total"].sum().sort_values(ascending=True)
colors_map = {
    "us_politics": "#4a90d9", "geopolitical": "#e87070", "macro": "#7ec8a0",
    "corporate": "#f0c060", "ai": "#9b59b6", "international": "#5dade2",
    "defense": "#e67e22", "commodities": "#95a5a6", "energy": "#2ecc71",
    "trade": "#1abc9c", "regulation": "#d35400",
}
bar_colors = [colors_map.get(cat, "#aaa") for cat in cat_vol.index]
bars3 = ax3.barh(cat_vol.index, cat_vol.values / 1e9, color=bar_colors, alpha=0.85, edgecolor="white")
ax3.set_xlabel("Total Volume ($B)")
ax3.set_title("Volume by Category (non-crypto)\n37k filtered markets")
for bar, val in zip(bars3, cat_vol.values):
    ax3.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2, f"${val/1e9:.1f}B", va="center", fontsize=8)

# ---- Plot 4: YES price final distribution ----
ax4 = axes[1, 0]
yes_data = df_fin.dropna(subset=["yes_price_final"])["yes_price_final"]
ax4.hist(yes_data, bins=30, color="#4a90d9", alpha=0.85, edgecolor="white")
ax4.axvline(0.9, color="#e87070", linestyle="--", label="YES threshold (90%)")
ax4.axvline(0.1, color="#2ecc71", linestyle="--", label="NO threshold (10%)")
ax4.set_xlabel("YES Price at Resolution")
ax4.set_ylabel("Number of Markets")
ax4.set_title("Outcome Distribution (non-crypto)\nyes_price_final")
ax4.legend(fontsize=9)
yes_pct = (yes_data >= 0.9).mean() * 100
no_pct = (yes_data <= 0.1).mean() * 100
ax4.text(0.5, 0.85, f"YES: {yes_pct:.0f}% | NO: {no_pct:.0f}%", transform=ax4.transAxes,
         ha="center", fontsize=10, bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

# ---- Plot 5: Markets over time (quarterly) ----
ax5 = axes[1, 1]
df_fin["quarter"] = df_fin["start_date"].dt.to_period("Q")
q_data = df_fin.groupby("quarter").agg(
    n=("id", "count"),
    vol=("volume_total", "sum")
).reset_index()
q_data = q_data[q_data["quarter"].notna()]
q_str = q_data["quarter"].astype(str)
ax5_twin = ax5.twinx()
bars5 = ax5.bar(range(len(q_data)), q_data["vol"]/1e9, color="#7ec8a0", alpha=0.7, label="Volume ($B)")
ax5_twin.plot(range(len(q_data)), q_data["n"], color="#e87070", linewidth=2, marker="o", markersize=4, label="# Markets")
ax5.set_xlabel("Quarter")
ax5.set_ylabel("Volume ($B)", color="#2ecc71")
ax5_twin.set_ylabel("# Markets", color="#e87070")
ax5.set_title("Non-crypto Markets Over Time\n(quarterly)")
step = max(1, len(q_data) // 8)
ax5.set_xticks(range(0, len(q_data), step))
ax5.set_xticklabels(q_str[::step], rotation=45, fontsize=8)

# ---- Plot 6: Duration vs Volume scatter (non-crypto) ----
ax6 = axes[1, 2]
sample = df_fin[df_fin["volume_total"].between(50_000, 500_000_000)].sample(min(2000, len(df_fin)), random_state=42)
scatter_colors = [colors_map.get(c, "#aaa") for c in sample["event_category"]]
ax6.scatter(sample["duration_days"].clip(0, 365), np.log10(sample["volume_total"]+1),
            c=scatter_colors, alpha=0.3, s=15)
ax6.set_xlabel("Market Duration (days, capped 365)")
ax6.set_ylabel("log₁₀(Volume $)")
ax6.set_title("Duration vs Volume (non-crypto)\nColored by category")
ax6.set_yticks([4, 5, 6, 7, 8, 9])
ax6.set_yticklabels(["$10K", "$100K", "$1M", "$10M", "$100M", "$1B"])

plt.tight_layout()
out_path = OUTPUT_DIR / "eda_overview.png"
plt.savefig(out_path, dpi=130, bbox_inches="tight")
plt.close()
print(f"  Saved: {out_path}")


# ---- Top tickers plot ----
fig2, ax = plt.subplots(figsize=(14, 8))
top_tickers = ticker_df.head(25)
equity_only = top_tickers[~top_tickers["ticker"].str.endswith("-USD")]
bars = ax.barh(equity_only["ticker"], equity_only["total_vol"]/1e9, color="#4a90d9", alpha=0.85, edgecolor="white")
ax.set_xlabel("Total Related Polymarket Volume ($B)")
ax.set_title("Top Equity Tickers by Associated Polymarket Volume\n(volume of markets where this ticker is relevant)")
for bar, (_, row) in zip(bars, equity_only.iterrows()):
    ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
            f"{fmt(row['total_vol'])} ({int(row['n_markets'])} mkts)", va="center", fontsize=8)
plt.tight_layout()
out_path2 = OUTPUT_DIR / "eda_tickers.png"
plt.savefig(out_path2, dpi=130, bbox_inches="tight")
plt.close()
print(f"  Saved: {out_path2}")


# ===========================================================================
# SECTION 10: KEY CONCLUSIONS
# ===========================================================================
print("\n" + "=" * 70)
print("KEY CONCLUSIONS FOR ML MODEL DESIGN")
print("=" * 70)

conclusions = """
1. DATA SCOPE
   ─────────────────────────────────────────────────────────────────
   ✓ 411,764 historical markets from 2021 to Feb 2026
   ✓ 37,667 financially relevant (> $50K volume, non-sport)
   ✓ 7,575 non-crypto relevant markets (the most useful for stock correlation)
   ✗ NO time-series volume data — only snapshot of volume_total at one moment
   ✗ CLOB price history only available for recent markets (~last 3-6 months)

2. WHAT WE HAVE FOR HISTORICAL ANALYSIS (2021-2024)
   ─────────────────────────────────────────────────────────────────
   • yes_price_final: resolved price (did the event happen?)
   • volume_total: lifetime total volume (proxy for total interest)
   • start_date + end_date: the window of the market
   • Questions and categories for LLM-based classification

   → Coarse correlation: did high-volume markets predicting a geopolitical
     event show stock movement in the related sector?

3. WHAT WE NEED TO ACQUIRE
   ─────────────────────────────────────────────────────────────────
   a) Stock prices (yfinance) for matching tickers — EASY, unlimited history
   b) CLOB price series for recent markets (~last 6 months) — DOABLE
   c) Daily volume snapshots (going forward from Feb 2026) — BUILDING NOW

4. BEST CANDIDATES FOR CORRELATION STUDY
   ─────────────────────────────────────────────────────────────────
   Priority 1 — us_politics: 4,022 markets, $28B+ volume, strong stock signals
   Priority 2 — macro (Fed): 446 markets, $5B+ volume, direct rate sensitivity
   Priority 3 — geopolitical: 1,628 markets, $3B+ volume, defense/energy
   Priority 4 — corporate: 552 markets, $2B+ volume, individual stocks

   Crypto markets (30k): useful separately but correlate with COIN/MSTR, not broad equities

5. KEY INSIGHT: VOLUME_TOTAL as SIGNAL STRENGTH PROXY
   ─────────────────────────────────────────────────────────────────
   Without time-series volume, we use volume_total as:
   - Total market conviction (how much people bet on this outcome)
   - Normalized by duration → avg_daily_vol = volume_total / duration_days
   - High avg_daily_vol = market was ACTIVELY traded throughout

   This is the INTENSITY metric for our coarse correlation study.

6. TIMELINE FOR FULL STUDY
   ─────────────────────────────────────────────────────────────────
   Phase A (NOW): Coarse historical study
     - 7.5k non-crypto relevant markets, 2021-2025
     - Match ticker + download yfinance → compute returns
     - Analyze: does yes_price_final * volume_total predict stock direction?

   Phase B (1 month): Recent time-series study
     - CLOB price series for Aug 2025 - Feb 2026 (recent markets)
     - Daily snapshots from our pipeline going forward
     - Test H1 (spike) and H2 (slow build) directly

   Phase C (3 months): Full forward-looking study
     - 3+ months of daily snapshot data
     - Full time-series analysis with volume velocity features
     - Proper ML with temporal validation
"""
print(conclusions)

# Save to file
with open(OUTPUT_DIR / "eda_conclusions.md", "w") as f:
    f.write("# EDA Conclusions — PolyCorr Research\n\n")
    f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n")
    f.write(conclusions)
print(f"\nConclusions saved to {OUTPUT_DIR / 'eda_conclusions.md'}")
print("\nEDA complete.")
