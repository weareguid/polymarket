"""
Phase 2A: Coarse Historical Correlation Study

For each non-crypto financially relevant market (7,575 markets, 2021-2026):
1. We know: start_date, end_date, yes_price_final (outcome), volume_total
2. We map to: related equity tickers
3. We download: daily stock price from yfinance for each ticker
4. We compute: stock returns at multiple horizons (during event, 7d post, 30d post)
5. We analyze: does the Polymarket volume/outcome predict stock direction?

Key hypotheses:
- High volume + YES resolution → stock moved UP in sector
- Low volume → noise, weak signal
- avg_daily_vol (volume/duration) is better signal than raw volume_total

Output:
- outputs/research/coarse_correlation.parquet
- outputs/research/coarse_correlation_report.md
- Plots in outputs/research/eda/
"""

import json
import warnings
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import yfinance as yf
from pathlib import Path
from datetime import datetime, timezone, timedelta
warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parents[3]
RELEVANT_CSV = BASE / "data/historical/relevant_markets.csv"
STOCK_CACHE_DIR = BASE / "data/historical/stock_prices"
OUTPUT_DIR = BASE / "outputs/research"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Focus: non-crypto markets, resolved in the past (not future)
FOCUS_CATEGORIES = {
    "us_politics", "macro", "geopolitical", "corporate",
    "ai", "defense", "international", "commodities", "energy", "trade", "regulation"
}
MIN_VOLUME = 100_000  # Focus on markets with meaningful volume
POST_DAYS = [3, 7, 14, 30]  # Return windows after event end

# Mapping: event category → what stock direction to expect when YES resolves
# (This is the hypothesis: if YES = event happened, which direction?)
DIRECTION_MAP = {
    "geopolitical": {
        "war_escalation_tickers": ["ITA", "LMT", "NOC", "GLD", "XLE"],
        "assumption": "YES = conflict/escalation → defense and oil UP"
    },
    "macro": {
        "fed_hike_tickers": ["TLT"],
        "assumption": "YES = rate change → TLT moves inversely"
    },
    "us_politics": {
        "assumption": "Complex — depends on candidate/policy"
    },
}

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "#f8f9fa",
    "axes.grid": True,
    "grid.color": "#e0e0e0",
    "font.size": 11,
})


def fmt(n):
    if abs(n) >= 1e9: return f"${n/1e9:.1f}B"
    if abs(n) >= 1e6: return f"${n/1e6:.1f}M"
    if abs(n) >= 1e3: return f"${n/1e3:.0f}K"
    return f"${n:.0f}"


# ===========================================================================
# 1. LOAD & FILTER RELEVANT MARKETS
# ===========================================================================
print("=" * 70)
print("PolyCorr Phase 2A: Coarse Historical Correlation")
print("=" * 70)

df = pd.read_csv(RELEVANT_CSV)
df["volume_total"] = pd.to_numeric(df["volume_total"], errors="coerce").fillna(0)
df["yes_price_final"] = pd.to_numeric(df["yes_price_final"], errors="coerce")
df["start_date"] = pd.to_datetime(df["start_date"], utc=True, errors="coerce")
df["end_date"] = pd.to_datetime(df["end_date"], utc=True, errors="coerce")

now = pd.Timestamp.now(tz="UTC")

# Filter: non-crypto, min volume, past events (end_date < today)
mask = (
    df["event_category"].isin(FOCUS_CATEGORIES) &
    (df["volume_total"] >= MIN_VOLUME) &
    (df["end_date"] < now) &
    df["yes_price_final"].notna() &
    df["start_date"].notna() &
    df["end_date"].notna()
)
df_work = df[mask].copy()
df_work["duration_days"] = (
    (df_work["end_date"] - df_work["start_date"]).dt.total_seconds() / 86400
).clip(lower=1)
df_work["avg_daily_vol"] = df_work["volume_total"] / df_work["duration_days"]
df_work["resolved_yes"] = df_work["yes_price_final"] >= 0.9
df_work["resolved_no"] = df_work["yes_price_final"] <= 0.1

print(f"\n[1] Working dataset: {len(df_work):,} markets")
print(f"    Volume range: {fmt(df_work['volume_total'].min())} - {fmt(df_work['volume_total'].max())}")
print(f"    Date range: {df_work['start_date'].min().date()} → {df_work['end_date'].max().date()}")
print(f"    Resolved YES: {df_work['resolved_yes'].sum():,} ({df_work['resolved_yes'].mean()*100:.1f}%)")
print(f"    Resolved NO:  {df_work['resolved_no'].sum():,} ({df_work['resolved_no'].mean()*100:.1f}%)")

# Category breakdown
print("\n    By category:")
for cat, grp in df_work.groupby("event_category"):
    print(f"    {cat:15s}: {len(grp):4,} mkts | Vol: {fmt(grp['volume_total'].sum())} | YES: {grp['resolved_yes'].mean()*100:.0f}%")


# ===========================================================================
# 2. DOWNLOAD STOCK PRICES (CACHED)
# ===========================================================================
print("\n[2] Downloading stock prices...")

STOCK_CACHE_DIR.mkdir(parents=True, exist_ok=True)

all_tickers = set()
for row in df_work.itertuples():
    try:
        tickers = json.loads(row.matched_tickers) if isinstance(row.matched_tickers, str) else []
        all_tickers.update(tickers[:3])  # top 3 tickers per market
    except Exception:
        pass

# Exclude crypto (BTC-USD etc.) for now — focus on equities
equity_tickers = {t for t in all_tickers if not t.endswith("-USD")}
print(f"    Equity tickers needed: {sorted(equity_tickers)}")

ticker_cache = {}
for ticker in sorted(equity_tickers):
    cache_path = STOCK_CACHE_DIR / f"{ticker}_full.parquet"
    if cache_path.exists():
        df_t = pd.read_parquet(cache_path)
        if "Date" not in df_t.columns and df_t.index.name == "Date":
            df_t = df_t.reset_index()
        df_t["Date"] = pd.to_datetime(df_t["Date"], utc=True, errors="coerce")
        ticker_cache[ticker] = df_t.sort_values("Date").set_index("Date")
        print(f"    {ticker}: cached ({len(df_t)} days)")
    else:
        try:
            data = yf.download(ticker, start="2021-01-01", end="2026-03-01",
                               progress=False, auto_adjust=True)
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.droplevel(1)
                data = data.reset_index()
                data.to_parquet(cache_path, index=False)
                data["Date"] = pd.to_datetime(data["Date"], utc=True, errors="coerce")
                ticker_cache[ticker] = data.sort_values("Date").set_index("Date")
                print(f"    {ticker}: downloaded ({len(data)} days)")
            else:
                print(f"    {ticker}: EMPTY")
        except Exception as e:
            print(f"    {ticker}: ERROR {e}")


# ===========================================================================
# 3. COMPUTE RETURNS PER MARKET
# ===========================================================================
print("\n[3] Computing stock returns per market-ticker pair...")


def get_return(stock_df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    """Safe return calculation between two dates."""
    if stock_df.empty or "Close" not in stock_df.columns:
        return None
    window = stock_df.loc[start:end, "Close"].dropna()
    if len(window) < 2:
        return None
    return float(window.iloc[-1] / window.iloc[0] - 1)


records = []
for idx, row in df_work.iterrows():
    try:
        tickers = json.loads(row["matched_tickers"]) if isinstance(row.get("matched_tickers"), str) else []
        if not tickers:
            continue
        tickers = [t for t in tickers[:3] if not t.endswith("-USD")]
        if not tickers:
            continue

        event_start = row["start_date"]
        event_end = row["end_date"]

        for ticker in tickers:
            if ticker not in ticker_cache:
                continue
            stock = ticker_cache[ticker]

            # Return DURING event
            ret_during = get_return(stock, event_start, event_end)
            # Returns AFTER event
            ret_post = {}
            for d in POST_DAYS:
                ret_post[f"ret_{d}d_post"] = get_return(
                    stock, event_end, event_end + timedelta(days=d + 5)
                )

            # Pre-event 14-day volatility (baseline noise level)
            pre_window = stock.loc[event_start - timedelta(days=20): event_start, "Close"].dropna()
            if len(pre_window) > 5:
                pre_vol = float(pre_window.pct_change().dropna().std() * (252 ** 0.5))
            else:
                pre_vol = None

            records.append({
                "market_id": row["id"],
                "question": str(row["question"])[:80],
                "ticker": ticker,
                "event_category": row["event_category"],
                "volume_total": row["volume_total"],
                "avg_daily_vol": row["avg_daily_vol"],
                "duration_days": row["duration_days"],
                "yes_price_final": row["yes_price_final"],
                "resolved_yes": row["resolved_yes"],
                "resolved_no": row["resolved_no"],
                "event_start": event_start,
                "event_end": event_end,
                "ret_during": ret_during,
                "pre_event_vol": pre_vol,
                **ret_post,
            })
    except Exception as e:
        pass

df_corr = pd.DataFrame(records)
print(f"    Generated {len(df_corr):,} market-ticker pairs")
print(f"    Pairs with ret_7d_post: {df_corr['ret_7d_post'].notna().sum():,}")

df_corr.to_parquet(OUTPUT_DIR / "coarse_correlation.parquet", index=False)
df_corr.to_csv(OUTPUT_DIR / "coarse_correlation.csv", index=False)
print(f"    Saved to outputs/research/coarse_correlation.parquet")


# ===========================================================================
# 4. ANALYSIS
# ===========================================================================
print("\n[4] Analysis...")

df_an = df_corr.dropna(subset=["ret_7d_post"]).copy()
df_an["vol_bucket"] = pd.cut(
    df_an["volume_total"],
    bins=[0, 500_000, 5_000_000, 50_000_000, 1e12],
    labels=["$100K-$500K", "$500K-$5M", "$5M-$50M", "$50M+"]
)

print("\n  A) Average 7-day post-event stock return by YES/NO resolution:")
yes_ret = df_an[df_an["resolved_yes"]]["ret_7d_post"].mean()
no_ret = df_an[df_an["resolved_no"]]["ret_7d_post"].mean()
other_ret = df_an[(~df_an["resolved_yes"]) & (~df_an["resolved_no"])]["ret_7d_post"].mean()
print(f"    YES resolved: {yes_ret*100:+.2f}%")
print(f"    NO resolved:  {no_ret*100:+.2f}%")
print(f"    Ambiguous:    {other_ret*100:+.2f}%")
print(f"    YES-NO spread: {(yes_ret-no_ret)*100:+.2f}pp")

print("\n  B) Average 7d return by volume bucket (YES resolved only):")
yes_only = df_an[df_an["resolved_yes"]]
if not yes_only.empty:
    bucket_stats = yes_only.groupby("vol_bucket")["ret_7d_post"].agg(
        mean="mean", count="count", std="std"
    )
    for bucket, row in bucket_stats.iterrows():
        t_stat = (row["mean"] / row["std"]) * (row["count"] ** 0.5) if row["std"] > 0 else 0
        print(f"    {str(bucket):15s}: {row['mean']*100:+.2f}% (n={int(row['count'])}, t={t_stat:.2f})")

print("\n  C) By category:")
cat_stats = df_an.groupby("event_category").agg(
    n=("ret_7d_post", "count"),
    yes_pct=("resolved_yes", "mean"),
    ret_7d_yes=("ret_7d_post", lambda x: x[df_an.loc[x.index, "resolved_yes"]].mean()),
    ret_7d_no=("ret_7d_post", lambda x: x[df_an.loc[x.index, "resolved_no"]].mean()),
    ret_30d_yes=("ret_30d_post", lambda x: x[df_an.loc[x.index, "resolved_yes"]].mean()),
).sort_values("ret_7d_yes", ascending=False)
print(f"    {'Category':15s}  {'N':>5}  {'YES%':>6}  {'7d YES':>8}  {'7d NO':>8}  {'30d YES':>9}")
for cat, row in cat_stats.iterrows():
    print(
        f"    {cat:15s}  {int(row['n']):5,}  {row['yes_pct']*100:5.0f}%  "
        f"{row['ret_7d_yes']*100 if pd.notna(row['ret_7d_yes']) else float('nan'):+7.2f}%  "
        f"{row['ret_7d_no']*100 if pd.notna(row['ret_7d_no']) else float('nan'):+7.2f}%  "
        f"{row['ret_30d_yes']*100 if pd.notna(row['ret_30d_yes']) else float('nan'):+8.2f}%"
    )

print("\n  D) Top individual tickers by predictive power (YES resolved, 7d post):")
ticker_stats = yes_only.groupby("ticker").agg(
    n=("ret_7d_post", "count"),
    mean_ret=("ret_7d_post", "mean"),
    std_ret=("ret_7d_post", "std"),
).reset_index()
ticker_stats["t_stat"] = ticker_stats.apply(
    lambda r: (r["mean_ret"] / r["std_ret"]) * (r["n"] ** 0.5) if r["std_ret"] > 0 and r["n"] >= 5 else 0,
    axis=1
)
ticker_stats = ticker_stats[ticker_stats["n"] >= 5].sort_values("t_stat", key=abs, ascending=False)
print(f"    {'Ticker':8s}  {'N':>4}  {'Mean 7d Ret':>11}  {'t-stat':>7}")
for _, row in ticker_stats.head(15).iterrows():
    print(f"    {row['ticker']:8s}  {int(row['n']):4,}  {row['mean_ret']*100:+10.2f}%  {row['t_stat']:+7.2f}")

print("\n  E) avg_daily_vol correlation with |ret_7d_post|:")
df_an["abs_ret_7d"] = df_an["ret_7d_post"].abs()
corr = df_an[["avg_daily_vol", "abs_ret_7d", "volume_total"]].corr()
print(f"    corr(avg_daily_vol, |ret_7d|) = {corr.loc['avg_daily_vol', 'abs_ret_7d']:.4f}")
print(f"    corr(volume_total,  |ret_7d|) = {corr.loc['volume_total', 'abs_ret_7d']:.4f}")


# ===========================================================================
# 5. PLOTS
# ===========================================================================
print("\n[5] Generating plots...")

fig, axes = plt.subplots(2, 3, figsize=(18, 11))
fig.suptitle("PolyCorr Phase 2A: Coarse Historical Correlation\nPolymarket Volume/Outcome → Stock Returns", fontsize=13, fontweight="bold")

# Plot 1: YES vs NO 7d returns by category
ax1 = axes[0, 0]
categories = cat_stats.index.tolist()
x = range(len(categories))
yes_vals = [cat_stats.loc[c, "ret_7d_yes"] * 100 if pd.notna(cat_stats.loc[c, "ret_7d_yes"]) else 0 for c in categories]
no_vals = [cat_stats.loc[c, "ret_7d_no"] * 100 if pd.notna(cat_stats.loc[c, "ret_7d_no"]) else 0 for c in categories]
width = 0.35
ax1.bar([i - width/2 for i in x], yes_vals, width, label="YES resolved", color="#7ec8a0", alpha=0.85)
ax1.bar([i + width/2 for i in x], no_vals, width, label="NO resolved", color="#e87070", alpha=0.85)
ax1.axhline(0, color="black", linewidth=0.8)
ax1.set_xticks(list(x))
ax1.set_xticklabels(categories, rotation=45, ha="right", fontsize=9)
ax1.set_ylabel("Mean 7d Stock Return (%)")
ax1.set_title("7d Post-Event Return by Category\nYES vs NO resolution")
ax1.legend()

# Plot 2: Return distribution for YES resolved high-vol markets
ax2 = axes[0, 1]
high_vol_yes = df_an[df_an["resolved_yes"] & (df_an["volume_total"] >= 1_000_000)]["ret_7d_post"]
low_vol_yes = df_an[df_an["resolved_yes"] & (df_an["volume_total"] < 1_000_000)]["ret_7d_post"]
ax2.hist(high_vol_yes.clip(-0.3, 0.3) * 100, bins=40, alpha=0.7, label=f"High-vol (≥$1M, n={len(high_vol_yes)})", color="#4a90d9", density=True)
ax2.hist(low_vol_yes.clip(-0.3, 0.3) * 100, bins=40, alpha=0.7, label=f"Low-vol (<$1M, n={len(low_vol_yes)})", color="#7ec8a0", density=True)
ax2.axvline(high_vol_yes.mean() * 100, color="#4a90d9", linestyle="--", linewidth=2)
ax2.axvline(low_vol_yes.mean() * 100, color="#2ecc71", linestyle="--", linewidth=2)
ax2.set_xlabel("7d Post-Event Stock Return (%)")
ax2.set_title("Return Distribution by Volume\n(YES resolved markets)")
ax2.legend(fontsize=9)

# Plot 3: Return by volume bucket (YES resolved)
ax3 = axes[0, 2]
bucket_data = yes_only.groupby("vol_bucket")["ret_7d_post"].mean() * 100
bucket_n = yes_only.groupby("vol_bucket")["ret_7d_post"].count()
bucket_plot = pd.DataFrame({"ret": bucket_data, "n": bucket_n}).reset_index()
bars3 = ax3.bar(range(len(bucket_plot)), bucket_plot["ret"],
                color=["#e87070" if r < 0 else "#7ec8a0" for r in bucket_plot["ret"]], alpha=0.85)
ax3.axhline(0, color="black", linewidth=0.8)
ax3.set_xticks(range(len(bucket_plot)))
ax3.set_xticklabels(bucket_plot["vol_bucket"].astype(str), rotation=30, ha="right", fontsize=9)
ax3.set_ylabel("Mean 7d Stock Return (%)")
ax3.set_title("Return vs Volume Bucket\n(YES resolved, key question: does vol predict signal?)")
for bar, (_, row) in zip(bars3, bucket_plot.iterrows()):
    ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
             f"n={int(row['n'])}", ha="center", fontsize=8)

# Plot 4: Scatter avg_daily_vol vs |ret_7d|
ax4 = axes[1, 0]
sample = df_an[df_an["avg_daily_vol"].notna() & df_an["abs_ret_7d"].notna()].sample(min(2000, len(df_an)), random_state=42)
cat_colors = {"us_politics": "#4a90d9", "macro": "#7ec8a0", "geopolitical": "#e87070",
              "corporate": "#f0c060", "ai": "#9b59b6", "defense": "#e67e22",
              "international": "#5dade2", "commodities": "#95a5a6"}
colors_s = [cat_colors.get(c, "#aaa") for c in sample["event_category"]]
ax4.scatter(np.log10(sample["avg_daily_vol"].clip(lower=100)), sample["abs_ret_7d"] * 100,
            c=colors_s, alpha=0.3, s=10)
ax4.set_xlabel("log₁₀(Avg Daily Volume $)")
ax4.set_ylabel("|7d Post-Event Return| (%)")
ax4.set_title("Market Intensity vs Stock Reaction\n(colored by category)")
ax4.set_xticklabels([f"${10**x/1e3:.0f}K" if 10**x < 1e6 else f"${10**x/1e6:.0f}M" for x in ax4.get_xticks()])

# Plot 5: Top tickers
ax5 = axes[1, 1]
top_tickers_plot = ticker_stats.head(12)
ax5.barh(top_tickers_plot["ticker"],
         top_tickers_plot["mean_ret"] * 100,
         color=["#7ec8a0" if r > 0 else "#e87070" for r in top_tickers_plot["mean_ret"]],
         alpha=0.85)
ax5.axvline(0, color="black", linewidth=0.8)
ax5.set_xlabel("Mean 7d Return after YES resolution (%)")
ax5.set_title("Ticker Predictive Power\n(YES resolved markets, ranked by |t-stat|)")
for i, (_, row) in enumerate(top_tickers_plot.iterrows()):
    ax5.text(row["mean_ret"] * 100 + (0.1 if row["mean_ret"] > 0 else -0.1),
             i, f"t={row['t_stat']:.1f} n={int(row['n'])}", va="center", fontsize=7)

# Plot 6: Timeline — when are most high-volume events?
ax6 = axes[1, 2]
df_highvol = df_work[df_work["volume_total"] >= 1_000_000].copy()
df_highvol["end_quarter"] = df_highvol["end_date"].dt.to_period("Q")
q_counts = df_highvol.groupby(["end_quarter", "event_category"]).size().unstack(fill_value=0)
q_counts = q_counts.tail(12)
colors_cat = [cat_colors.get(c, "#aaa") for c in q_counts.columns]
q_counts.plot(kind="bar", stacked=True, ax=ax6, color=colors_cat, alpha=0.85, legend=False)
ax6.set_xlabel("Quarter")
ax6.set_xticklabels([str(q) for q in q_counts.index], rotation=45, fontsize=8)
ax6.set_ylabel("# High-Volume Markets (>$1M)")
ax6.set_title("High-Volume Financial Events Over Time\n(>$1M volume, stacked by category)")
ax6.legend(fontsize=7, loc="upper left", ncol=2)

plt.tight_layout()
out_plot = OUTPUT_DIR / "eda" / "coarse_correlation.png"
plt.savefig(out_plot, dpi=130, bbox_inches="tight")
plt.close()
print(f"    Saved: {out_plot}")


# ===========================================================================
# 6. REPORT
# ===========================================================================
report = f"""# PolyCorr Phase 2A: Coarse Historical Correlation Report
*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*

## Dataset
- **Markets analyzed:** {len(df_work):,} non-crypto financially relevant markets
- **Market-ticker pairs:** {len(df_corr):,}
- **Pairs with complete return data:** {len(df_an):,}
- **Period:** {df_work['start_date'].min().date()} → {df_work['end_date'].max().date()}

## Key Findings

### 1. YES vs NO Resolution → Stock Direction
| Resolution | Mean 7d Post Return |
|------------|---------------------|
| YES | {yes_ret*100:+.2f}% |
| NO | {no_ret*100:+.2f}% |
| **Spread** | **{(yes_ret-no_ret)*100:+.2f}pp** |

**Interpretation:** {"✅ YES-resolved markets show higher post-event stock returns — Polymarket has directional signal" if yes_ret > no_ret else "⚠️ No clear directional advantage for YES-resolved markets — needs more investigation"}

### 2. Volume → Signal Strength
- corr(avg_daily_vol, |ret_7d|) = {corr.loc['avg_daily_vol', 'abs_ret_7d']:.4f}
- corr(volume_total,  |ret_7d|) = {corr.loc['volume_total', 'abs_ret_7d']:.4f}

**Interpretation:** {"✅ Positive correlation — higher volume markets show stronger stock reactions" if corr.loc['avg_daily_vol', 'abs_ret_7d'] > 0 else "⚠️ Weak or negative correlation — volume alone doesn't predict reaction magnitude"}

### 3. Best Categories for Correlation
{cat_stats[['n', 'yes_pct', 'ret_7d_yes', 'ret_7d_no']].to_string()}

### 4. Limitations of Coarse Analysis
- No time-series volume → can't test spike vs slow-build hypotheses
- `yes_price_final` tells us outcome but not the PATH of probability
- Stock return timing is imprecise (markets last days to months)
- No control for market regime (bull vs bear environment)

## Next Steps
1. **Phase 2B:** CLOB price series for recent markets → test H1/H2 directly
2. **Phase 3:** Build daily volume snapshots → 3-month dataset for time-series ML
3. **Key question:** Does the TIMING of volume within a market (spike vs build) predict stock return better than total volume?
"""

report_path = OUTPUT_DIR / "eda" / "coarse_correlation_report.md"
with open(report_path, "w") as f:
    f.write(report)
print(f"    Report saved: {report_path}")

print("\n=== Phase 2A Complete ===")
