"""
Phase 2B: Correlate Polymarket price series with stock returns.

For each market with a price series:
1. Find the associated stock ticker(s)
2. Align timestamps
3. Look for:
   - H1 (Spike): hours where YES probability jumped > 15pp
   - H2 (Slow Build): 14+ consecutive days where probability is rising (daily resampled)
4. For each signal, measure stock return in next 1d, 3d, 7d
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json

PRICE_SERIES_DIR = Path("data/historical/price_series")
INDEX_CSV = "data/historical/price_series_index.csv"
RELEVANT_MARKETS_CSV = "data/historical/relevant_markets.csv"
STOCK_PRICES_DIR = Path("data/historical/stock_prices")
OUTPUT_CSV = "outputs/research/phase2b_signals.csv"

# ---------------------------------------------------------------------------
# Load index and market metadata
# ---------------------------------------------------------------------------
idx = pd.read_csv(INDEX_CSV)
markets = pd.read_csv(RELEVANT_MARKETS_CSV)
markets["volume_total"] = pd.to_numeric(markets["volume_total"], errors="coerce").fillna(0)

idx_with_series = idx[idx["has_series"] == True].copy()
print(f"Markets with price series: {len(idx_with_series)}")

# Merge with market metadata to get ticker associations
markets_meta = markets[["id", "question", "event_category", "matched_tickers", "volume_total", "end_date"]].copy()
work = idx_with_series.merge(markets_meta, on="id", how="left")
work = work[work["matched_tickers"].notna()].copy()
print(f"Markets with series + tickers: {len(work)}")

# Parse matched_tickers (JSON array string) — take first ticker
def parse_first_ticker(t):
    try:
        tickers = json.loads(t.replace("'", '"'))
        return tickers[0] if tickers else None
    except:
        return None

work["ticker"] = work["matched_tickers"].apply(parse_first_ticker)
work = work[work["ticker"].notna()].copy()
print(f"Markets with primary ticker: {len(work)}")
print(f"Unique tickers: {work['ticker'].nunique()}")
print("\nTicker distribution:")
print(work["ticker"].value_counts().head(15))

# ---------------------------------------------------------------------------
# Load stock prices
# ---------------------------------------------------------------------------
stock_cache = {}
for f in STOCK_PRICES_DIR.glob("*.parquet"):
    ticker = f.stem.replace("_full", "")
    try:
        df = pd.read_parquet(f)
        df["Date"] = pd.to_datetime(df["Date"], utc=True)
        df = df.set_index("Date").sort_index()
        stock_cache[ticker] = df["Close"]
    except Exception as e:
        pass

print(f"\nStock tickers in cache: {len(stock_cache)}")
print("Available:", sorted(stock_cache.keys()))

# Check coverage
covered = work[work["ticker"].isin(stock_cache)]["ticker"].nunique()
work_covered = work[work["ticker"].isin(stock_cache)].copy()
print(f"\nMarkets where ticker is in stock cache: {len(work_covered)} ({len(work_covered)/len(work)*100:.0f}%)")

# ---------------------------------------------------------------------------
# Detect signals and measure returns
# ---------------------------------------------------------------------------
results = []

for _, row in work_covered.iterrows():
    market_id = row["id"]
    ticker = row["ticker"]
    question = str(row["question"])[:80]
    category = row.get("event_category", "unknown")
    volume = row.get("volume_total", 0)

    if ticker not in stock_cache:
        continue

    series_path = PRICE_SERIES_DIR / f"{market_id}.parquet"
    if not series_path.exists():
        continue

    try:
        ps = pd.read_parquet(series_path)
        ps["timestamp"] = pd.to_datetime(ps["timestamp"], utc=True)
        ps = ps.sort_values("timestamp").set_index("timestamp")

        if len(ps) < 5:
            continue

        # Daily resampled series for signal detection
        daily = ps["price"].resample("1D").last().dropna()
        if len(daily) < 3:
            continue

        stock = stock_cache[ticker]

        def get_returns(signal_date):
            """Compute forward returns for 1d, 3d, 7d after signal_date."""
            future = stock[stock.index > signal_date]
            if len(future) == 0:
                return np.nan, np.nan, np.nan
            r1 = float(future.iloc[:1].pct_change().mean()) if len(future) >= 1 else np.nan
            r3 = float((future.iloc[min(2, len(future)-1)] / future.iloc[0] - 1)) if len(future) >= 1 else np.nan
            r7 = float((future.iloc[min(6, len(future)-1)] / future.iloc[0] - 1)) if len(future) >= 1 else np.nan
            # Actually compute properly:
            # r1d = return from close on signal_date to close 1 trading day later
            prev_close = stock[stock.index <= signal_date]
            if len(prev_close) == 0:
                return np.nan, np.nan, np.nan
            base = float(prev_close.iloc[-1])
            r1 = float(future.iloc[0] / base - 1) if len(future) >= 1 and base > 0 else np.nan
            r3 = float(future.iloc[min(2, len(future)-1)] / base - 1) if len(future) >= 1 and base > 0 else np.nan
            r7 = float(future.iloc[min(6, len(future)-1)] / base - 1) if len(future) >= 1 and base > 0 else np.nan
            return r1, r3, r7

        # H1: Spike detection — single day jump > 15pp in YES probability
        daily_diff = daily.diff()
        spikes = daily_diff[daily_diff > 0.15]

        for spike_date, spike_size in spikes.items():
            r1, r3, r7 = get_returns(spike_date)
            results.append({
                "market_id": market_id,
                "question": question,
                "ticker": ticker,
                "category": category,
                "volume_total": volume,
                "signal_type": "H1_spike",
                "signal_date": str(spike_date.date()),
                "signal_magnitude": round(float(spike_size), 4),
                "price_at_signal": round(float(daily.get(spike_date, np.nan)), 4),
                "ret_1d": round(r1, 5) if not np.isnan(r1) else np.nan,
                "ret_3d": round(r3, 5) if not np.isnan(r3) else np.nan,
                "ret_7d": round(r7, 5) if not np.isnan(r7) else np.nan,
            })

        # Also detect drops > 15pp (event becoming less likely)
        drops = daily_diff[daily_diff < -0.15]
        for drop_date, drop_size in drops.items():
            r1, r3, r7 = get_returns(drop_date)
            results.append({
                "market_id": market_id,
                "question": question,
                "ticker": ticker,
                "category": category,
                "volume_total": volume,
                "signal_type": "H1_drop",
                "signal_date": str(drop_date.date()),
                "signal_magnitude": round(float(drop_size), 4),
                "price_at_signal": round(float(daily.get(drop_date, np.nan)), 4),
                "ret_1d": round(r1, 5) if not np.isnan(r1) else np.nan,
                "ret_3d": round(r3, 5) if not np.isnan(r3) else np.nan,
                "ret_7d": round(r7, 5) if not np.isnan(r7) else np.nan,
            })

        # H2: Slow build — 14+ consecutive days of rising probability
        consecutive_rising = 0
        for i in range(1, len(daily)):
            if daily_diff.iloc[i] > 0:
                consecutive_rising += 1
            else:
                consecutive_rising = 0

            if consecutive_rising == 14:
                build_date = daily.index[i]
                r7, r14, r30 = get_returns(build_date)
                build_magnitude = float(daily.iloc[i] - daily.iloc[max(0, i - 14)])
                results.append({
                    "market_id": market_id,
                    "question": question,
                    "ticker": ticker,
                    "category": category,
                    "volume_total": volume,
                    "signal_type": "H2_slow_build",
                    "signal_date": str(build_date.date()),
                    "signal_magnitude": round(build_magnitude, 4),
                    "price_at_signal": round(float(daily.iloc[i]), 4),
                    "ret_1d": round(r7, 5) if not np.isnan(r7) else np.nan,   # re-used as 7d
                    "ret_3d": round(r14, 5) if not np.isnan(r14) else np.nan,  # 14d
                    "ret_7d": round(r30, 5) if not np.isnan(r30) else np.nan,  # 30d
                })

    except Exception as e:
        continue

print(f"\nTotal signals detected: {len(results)}")

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
df_results = pd.DataFrame(results)

if len(df_results) == 0:
    print("No signals found. Exiting.")
    exit()

print("\nBreakdown by signal type:")
print(df_results["signal_type"].value_counts())

print("\nBreakdown by category:")
print(df_results["category"].value_counts())

print("\nBreakdown by ticker:")
print(df_results["ticker"].value_counts().head(15))

print("\n" + "="*60)
print("--- H1 SPIKE Analysis (YES probability jumps >15pp) ---")
print("="*60)
h1 = df_results[df_results["signal_type"] == "H1_spike"]
if len(h1) > 0:
    print(f"N spikes: {len(h1)}")
    print(f"Avg spike size: {h1['signal_magnitude'].mean():.1%}")
    print(f"Avg stock ret 1d: {h1['ret_1d'].mean():.3%}")
    print(f"Avg stock ret 3d: {h1['ret_3d'].mean():.3%}")
    print(f"Avg stock ret 7d: {h1['ret_7d'].mean():.3%}")
    print(f"% positive ret_1d: {(h1['ret_1d'] > 0).mean():.1%}")
    print(f"% positive ret_7d: {(h1['ret_7d'] > 0).mean():.1%}")
    print(f"\nBy category (H1 spikes):")
    print(h1.groupby("category")[["ret_1d", "ret_3d", "ret_7d"]].mean().sort_values("ret_7d", ascending=False).to_string())
    print(f"\nBy ticker (H1 spikes):")
    ticker_h1 = h1.groupby("ticker").agg(
        n=("ret_1d", "count"),
        avg_ret_1d=("ret_1d", "mean"),
        avg_ret_7d=("ret_7d", "mean"),
        pct_pos_7d=("ret_7d", lambda x: (x > 0).mean())
    ).sort_values("avg_ret_7d", ascending=False)
    print(ticker_h1.to_string())
    print("\nTop 10 individual spike events by signal magnitude:")
    cols = ["signal_date", "ticker", "category", "signal_magnitude", "price_at_signal", "ret_1d", "ret_3d", "ret_7d", "question"]
    print(h1.sort_values("signal_magnitude", ascending=False).head(10)[cols].to_string())

print("\n" + "="*60)
print("--- H1 DROP Analysis (YES probability drops >15pp) ---")
print("="*60)
h1d = df_results[df_results["signal_type"] == "H1_drop"]
if len(h1d) > 0:
    print(f"N drops: {len(h1d)}")
    print(f"Avg drop size: {h1d['signal_magnitude'].mean():.1%}")
    print(f"Avg stock ret 1d: {h1d['ret_1d'].mean():.3%}")
    print(f"Avg stock ret 3d: {h1d['ret_3d'].mean():.3%}")
    print(f"Avg stock ret 7d: {h1d['ret_7d'].mean():.3%}")
    print(f"% positive ret_1d: {(h1d['ret_1d'] > 0).mean():.1%}")
    print(f"By category (drops):")
    print(h1d.groupby("category")[["ret_1d", "ret_7d"]].mean().sort_values("ret_7d", ascending=False).to_string())

print("\n" + "="*60)
print("--- H2 SLOW BUILD Analysis (14 consec. days rising) ---")
print("="*60)
h2 = df_results[df_results["signal_type"] == "H2_slow_build"]
if len(h2) > 0:
    print(f"N slow builds: {len(h2)}")
    print(f"Avg build size: {h2['signal_magnitude'].mean():.1%}")
    print(f"Avg stock ret 7d: {h2['ret_1d'].mean():.3%}")
    print(f"Avg stock ret 14d: {h2['ret_3d'].mean():.3%}")
    print(f"Avg stock ret 30d: {h2['ret_7d'].mean():.3%}")
    print(h2.sort_values("signal_magnitude", ascending=False).head(10)[["signal_date", "ticker", "category", "signal_magnitude", "ret_1d", "ret_3d", "ret_7d", "question"]].to_string())
else:
    print("No slow-build signals found (need 14+ consecutive rising days).")

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
Path("outputs/research").mkdir(parents=True, exist_ok=True)
df_results.to_csv(OUTPUT_CSV, index=False)
print(f"\nResults saved to: {OUTPUT_CSV}")
print(f"Total rows: {len(df_results)}")
