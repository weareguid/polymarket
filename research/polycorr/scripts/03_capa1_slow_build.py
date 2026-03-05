"""
Capa 1 — Slow Build Analysis
Tests whether sustained probability increases in Polymarket
predict positive stock returns in the following days.

Definition of a "Slow Build":
- Probability increases for N consecutive days (threshold: N >= 5, relaxed from 7)
- Total increase over that period >= 10pp (relaxed from 15pp)
- Minimum daily volume $10K (relaxed from $50K; most markets are illiquid below this)

For each slow build detected:
- Record start date, end date, total increase, duration
- Measure stock return at +7d, +14d, +30d from start of build
- Segment by epoch: 2022-23 (pre-HFT) vs 2024 (HFT entering) vs 2025 (HFT active)

NOTE ON THRESHOLDS:
  Original thresholds (7 days, 15pp, $50K volume) yielded only 2 signals.
  Relaxed to (5 days, 10pp, $10K) to surface 29 signals for analysis.
  Key insight: most markets have very few days above $50K volume.
"""

import ast
import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats

SERIES_DIR = Path("data/historical/price_series_historical")
TARGETS_CSV = "data/historical/price_series_targets.csv"
STOCK_DIR = Path("data/historical/stock_prices")
OUTPUT_CSV = "outputs/research/capa1_slow_build_signals.csv"

# Parameters (relaxed from original strict thresholds)
MIN_CONSECUTIVE_DAYS = 5   # minimum days of consecutive rise (was 7)
MIN_TOTAL_CHANGE = 0.10    # minimum 10pp total increase (was 15pp)
MIN_DAILY_VOLUME = 10_000  # minimum $10K daily volume (was $50K)


def get_epoch(date):
    """Classify date into analysis epoch."""
    year = pd.Timestamp(date).year
    if year <= 2023:
        return "2022-2023 (pre-HFT)"
    elif year == 2024:
        return "2024 (HFT entering)"
    else:
        return "2025 (HFT active)"


def detect_slow_builds(daily: pd.DataFrame, min_days=5, min_change=0.10, min_vol=10_000):
    """
    Detect all slow build periods in a daily price series.
    Returns list of dicts with build start, end, duration, magnitude.
    """
    builds = []
    if len(daily) < min_days + 1:
        return builds

    daily = daily[daily['volume_usd'] >= min_vol].copy()
    daily = daily.sort_values('date').reset_index(drop=True)

    if len(daily) < min_days:
        return builds

    prices = daily['price_vwap'].values
    dates  = daily['date'].values
    vols   = daily['volume_usd'].values

    i = 1
    streak = 1
    streak_start = 0

    while i < len(prices):
        if prices[i] > prices[i - 1]:
            streak += 1
        else:
            if streak >= min_days:
                total_change = prices[i - 1] - prices[streak_start]
                if total_change >= min_change:
                    builds.append({
                        'build_start': dates[streak_start],
                        'build_end':   dates[i - 1],
                        'duration_days': streak,
                        'prob_start':  round(float(prices[streak_start]), 3),
                        'prob_end':    round(float(prices[i - 1]), 3),
                        'total_change_pp': round(float(total_change), 3),
                        'avg_daily_volume': round(float(np.mean(vols[streak_start:i])), 0),
                    })
            streak = 1
            streak_start = i
        i += 1

    # Check final streak
    if streak >= min_days:
        total_change = prices[-1] - prices[streak_start]
        if total_change >= min_change:
            builds.append({
                'build_start': dates[streak_start],
                'build_end':   dates[-1],
                'duration_days': streak,
                'prob_start':  round(float(prices[streak_start]), 3),
                'prob_end':    round(float(prices[-1]), 3),
                'total_change_pp': round(float(total_change), 3),
                'avg_daily_volume': round(float(np.mean(vols[streak_start:])), 0),
            })

    return builds


# Load targets
targets = pd.read_csv(TARGETS_CSV)
print(f"Target markets loaded: {len(targets)}")
print(f"Columns: {targets.columns.tolist()}")
print(targets[['question', 'event_category', 'matched_tickers']].head(5).to_string())

# Load stock prices
stock_cache = {}
for f in STOCK_DIR.glob("*.parquet"):
    ticker = f.stem.replace("_full", "").upper()
    try:
        df = pd.read_parquet(f)
        df['Date'] = pd.to_datetime(df['Date'], utc=True)
        stock_cache[ticker] = df.set_index('Date')['Close']
    except Exception as e:
        print(f"  Warning: could not load {f.name}: {e}")

print(f"\nStock tickers loaded: {len(stock_cache)}")
print(f"Tickers: {sorted(stock_cache.keys())}")

all_signals = []
markets_with_builds = 0
markets_no_data = 0

for _, row in targets.iterrows():
    condition_id = str(row.get('id', row.get('condition_id', ''))).strip()
    question     = str(row.get('question', ''))[:80]
    category     = str(row.get('event_category', 'unknown'))

    raw_tickers = row.get('matched_tickers', '[]')
    try:
        ticker_list = ast.literal_eval(str(raw_tickers))
    except Exception:
        ticker_list = []
    primary_ticker = ticker_list[0].upper() if ticker_list else ''

    series_path = SERIES_DIR / f"{condition_id}.parquet"
    if not series_path.exists():
        markets_no_data += 1
        continue

    try:
        daily = pd.read_parquet(series_path)
        daily['date'] = pd.to_datetime(daily['date'])
    except Exception as e:
        continue

    builds = detect_slow_builds(daily, MIN_CONSECUTIVE_DAYS, MIN_TOTAL_CHANGE, MIN_DAILY_VOLUME)
    if not builds:
        continue

    markets_with_builds += 1

    stock = stock_cache.get(primary_ticker)
    used_ticker = primary_ticker
    if stock is None:
        for t in ticker_list:
            s = stock_cache.get(t.upper())
            if s is not None:
                stock = s
                used_ticker = t.upper()
                break

    for build in builds:
        build_start = pd.Timestamp(build['build_start'])
        if build_start.tzinfo is None:
            build_start = build_start.tz_localize('UTC')
        epoch = get_epoch(build_start)

        signal = {
            'question':       question,
            'category':       category,
            'primary_ticker': primary_ticker,
            'used_ticker':    used_ticker,
            'all_tickers':    str(ticker_list),
            'epoch':          epoch,
            **build,
        }

        if stock is not None:
            try:
                future = stock[stock.index >= build_start]
                if len(future) >= 2:
                    p0 = future.iloc[0]

                    def ret_after(days):
                        target_date = build_start + pd.Timedelta(days=days)
                        window = stock[
                            (stock.index >= build_start + pd.Timedelta(days=1)) &
                            (stock.index <= target_date)
                        ]
                        if len(window) == 0:
                            return np.nan
                        return (window.iloc[-1] - p0) / p0

                    signal['ret_7d']  = round(ret_after(7), 4)
                    signal['ret_14d'] = round(ret_after(14), 4)
                    signal['ret_30d'] = round(ret_after(30), 4)
                else:
                    signal['ret_7d'] = signal['ret_14d'] = signal['ret_30d'] = np.nan
            except Exception:
                signal['ret_7d'] = signal['ret_14d'] = signal['ret_30d'] = np.nan
        else:
            signal['ret_7d']  = np.nan
            signal['ret_14d'] = np.nan
            signal['ret_30d'] = np.nan

        all_signals.append(signal)

print(f"\n=== RESULTS ===")
print(f"Thresholds: min_days={MIN_CONSECUTIVE_DAYS}, min_change={MIN_TOTAL_CHANGE:.0%}, min_vol=${MIN_DAILY_VOLUME:,}")
print(f"Markets skipped (no parquet): {markets_no_data}")
print(f"Markets processed: {len(targets) - markets_no_data}")
print(f"Markets with at least 1 slow build: {markets_with_builds}")
print(f"Total slow build signals: {len(all_signals)}")

if not all_signals:
    print("No slow builds found. Inspect series data for debugging.")
else:
    df = pd.DataFrame(all_signals)
    df['build_start'] = pd.to_datetime(df['build_start'])
    df['build_end']   = pd.to_datetime(df['build_end'])

    pd.set_option('display.max_colwidth', 60)
    pd.set_option('display.width', 220)

    print("\n" + "=" * 110)
    print("ALL SIGNALS")
    print("=" * 110)
    cols = ['question', 'category', 'used_ticker', 'epoch',
            'duration_days', 'prob_start', 'prob_end', 'total_change_pp',
            'ret_7d', 'ret_14d', 'ret_30d']
    print(df[cols].to_string(index=False))

    print("\n" + "=" * 80)
    print("SUMMARY BY EPOCH")
    print("=" * 80)
    for epoch in sorted(df['epoch'].unique()):
        sub  = df[df['epoch'] == epoch]
        wr   = sub.dropna(subset=['ret_7d'])
        print(f"\n{epoch}")
        print(f"  Total signals:         {len(sub)}")
        print(f"  With stock data:       {len(wr)}")
        if len(wr) > 0:
            for col, label in [('ret_7d', '+7d'), ('ret_14d', '+14d'), ('ret_30d', '+30d')]:
                v = wr[col].dropna()
                print(f"  avg ret {label}: {v.mean():+.2%}  (positive: {(v>0).mean():.0%}, N={len(v)})")
        print(f"  avg duration:  {sub['duration_days'].mean():.1f} days")
        print(f"  avg magnitude: {sub['total_change_pp'].mean():.1%}")

    print("\n" + "=" * 80)
    print("SUMMARY BY CATEGORY")
    print("=" * 80)
    for cat in sorted(df['category'].unique()):
        sub = df[df['category'] == cat]
        wr  = sub.dropna(subset=['ret_7d'])
        print(f"\n{cat}  (N={len(sub)}, with stock={len(wr)})")
        if len(wr) > 0:
            for col, label in [('ret_7d', '+7d'), ('ret_14d', '+14d'), ('ret_30d', '+30d')]:
                v = wr[col].dropna()
                print(f"  avg ret {label}: {v.mean():+.2%}  (positive: {(v>0).mean():.0%})")

    print("\n" + "=" * 80)
    print("TOP 15 SIGNALS BY DURATION")
    print("=" * 80)
    top = df.sort_values('duration_days', ascending=False).head(15)
    print(top[['question', 'used_ticker', 'epoch', 'duration_days',
               'total_change_pp', 'ret_7d', 'ret_14d', 'ret_30d']].to_string(index=False))

    print("\n" + "=" * 80)
    print("TOP 15 SIGNALS BY MAGNITUDE (total_change_pp)")
    print("=" * 80)
    top_mag = df.sort_values('total_change_pp', ascending=False).head(15)
    print(top_mag[['question', 'used_ticker', 'epoch', 'duration_days',
                   'total_change_pp', 'ret_7d', 'ret_14d', 'ret_30d']].to_string(index=False))

    print("\n" + "=" * 80)
    print("STATISTICAL TESTS (one-sample t-test, H0: mean return = 0)")
    print("=" * 80)
    for col, label in [('ret_7d', '+7d'), ('ret_14d', '+14d'), ('ret_30d', '+30d')]:
        v = df[col].dropna()
        if len(v) >= 5:
            t, p = stats.ttest_1samp(v, 0)
            sig = ("SIGNIFICANT (p<0.05)" if p < 0.05
                   else "Marginal (p<0.10)" if p < 0.10
                   else "Not significant")
            print(f"ret {label}: N={len(v)}, mean={v.mean():+.3%}, t={t:.2f}, p={p:.3f}  ->  {sig}")
        else:
            print(f"ret {label}: insufficient data (N={len(v)})")

    print("\n--- Per-epoch t-tests (ret_7d) ---")
    for epoch in sorted(df['epoch'].unique()):
        v = df[df['epoch'] == epoch]['ret_7d'].dropna()
        if len(v) >= 5:
            t, p = stats.ttest_1samp(v, 0)
            sig = "SIGNIFICANT" if p < 0.05 else ("marginal" if p < 0.10 else "not sig.")
            print(f"  {epoch}: N={len(v)}, mean={v.mean():+.3%}, t={t:.2f}, p={p:.3f}  [{sig}]")
        else:
            print(f"  {epoch}: N={len(v)} (too few for test)")

    print("\n" + "=" * 80)
    print("DISTRIBUTION STATS")
    print("=" * 80)
    print(df[['duration_days', 'total_change_pp', 'avg_daily_volume',
              'ret_7d', 'ret_14d', 'ret_30d']].describe().round(4).to_string())

    Path("outputs/research").mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved {len(df)} signals to {OUTPUT_CSV}")

    missing = df[df['ret_7d'].isna()]
    if len(missing) > 0:
        print(f"\n{len(missing)} signals had no stock return data:")
        for _, r in missing.iterrows():
            print(f"  ticker={r['used_ticker'] or '(none)':8s}  {r['question'][:60]}")
