"""
Capa 2 — Niche Correlation Discovery
For each market, correlate the daily Polymarket probability series
with ALL available stock tickers (not just the assigned one).
Finds unexpected/non-obvious correlations.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import pearsonr, spearmanr

SERIES_DIR = Path("data/historical/price_series_historical")
TARGETS_CSV = "data/historical/price_series_targets.csv"
STOCK_DIR = Path("data/historical/stock_prices")
OUTPUT_CSV = "outputs/research/capa2_niche_correlations.csv"

# Load targets
targets = pd.read_csv(TARGETS_CSV)
print(f"Markets: {len(targets)}")

# Load all stock prices into dict
# Stock parquets have a 'Date' column (not the index) with no timezone
stock_cache = {}
for f in STOCK_DIR.glob("*.parquet"):
    ticker = f.stem.replace("_full", "")
    try:
        df = pd.read_parquet(f)
        df['Date'] = pd.to_datetime(df['Date']).dt.normalize()  # date-only, no tz
        df = df.set_index('Date')
        series = df['Close'].resample('1D').last().dropna()
        series.index = series.index.tz_localize(None)  # ensure no tz
        stock_cache[ticker] = series
    except Exception as e:
        print(f"  WARNING: Could not load {ticker}: {e}")
print(f"Stock tickers loaded: {len(stock_cache)}")
all_tickers = list(stock_cache.keys())

results = []

for _, row in targets.iterrows():
    condition_id = str(row.get('id', row.get('condition_id', ''))).strip()
    # matched_tickers is a JSON list string like '["DJT","IWM"]'
    raw_tickers = str(row.get('matched_tickers', row.get('ticker', ''))).strip()
    # Parse assigned tickers (take first one as "primary")
    try:
        import json
        ticker_list = json.loads(raw_tickers)
        assigned_ticker = ticker_list[0].strip().upper() if ticker_list else ''
    except:
        assigned_ticker = raw_tickers.strip().upper()

    question = str(row.get('question', ''))[:80]
    category = str(row.get('event_category', row.get('category', '')))

    series_path = SERIES_DIR / f"{condition_id}.parquet"
    if not series_path.exists():
        print(f"  MISSING: {series_path.name}")
        continue

    try:
        daily_df = pd.read_parquet(series_path)
        # date column is datetime64[ms], no tz
        daily_df['date'] = pd.to_datetime(daily_df['date']).dt.normalize()
        daily = daily_df.set_index('date')['price_vwap'].resample('1D').last().dropna()
        daily.index = daily.index.tz_localize(None)
    except Exception as e:
        print(f"  ERROR loading series {condition_id}: {e}")
        continue

    if len(daily) < 20:
        continue

    # Test all tickers
    ticker_corrs = []

    for ticker, stock_series in stock_cache.items():
        # Align on common dates
        common_idx = daily.index.intersection(stock_series.index)
        if len(common_idx) < 15:
            continue

        pm_vals = daily.loc[common_idx].values
        stock_vals = stock_series.loc[common_idx].values

        # Remove any NaN
        mask = ~(np.isnan(pm_vals) | np.isnan(stock_vals))
        if mask.sum() < 15:
            continue

        pm_clean = pm_vals[mask]
        st_clean = stock_vals[mask]

        try:
            r_pearson, p_pearson = pearsonr(pm_clean, st_clean)
            r_spearman, p_spearman = spearmanr(pm_clean, st_clean)

            ticker_corrs.append({
                'ticker': ticker,
                'r_pearson': round(r_pearson, 3),
                'r_spearman': round(r_spearman, 3),
                'p_pearson': round(p_pearson, 4),
                'n_days': int(mask.sum()),
                'is_assigned': ticker == assigned_ticker,
            })
        except:
            continue

    if not ticker_corrs:
        continue

    # Sort by absolute pearson correlation
    ticker_corrs.sort(key=lambda x: abs(x['r_pearson']), reverse=True)

    for rank, tc in enumerate(ticker_corrs[:10], 1):
        is_surprise = (not tc['is_assigned']) and abs(tc['r_pearson']) > 0.4 and rank <= 5
        results.append({
            'question': question,
            'category': category,
            'assigned_ticker': assigned_ticker,
            'corr_ticker': tc['ticker'],
            'rank': rank,
            'r_pearson': tc['r_pearson'],
            'r_spearman': tc['r_spearman'],
            'p_value': tc['p_pearson'],
            'n_days': tc['n_days'],
            'is_assigned': tc['is_assigned'],
            'is_surprise': is_surprise,
            'series_start': str(daily.index[0].date()),
            'series_end': str(daily.index[-1].date()),
        })

    # Print interesting cases
    if ticker_corrs and abs(ticker_corrs[0]['r_pearson']) > 0.3:
        top_ticker = ticker_corrs[0]
        surprise_flag = "SURPRISE" if (top_ticker['ticker'] != assigned_ticker and abs(top_ticker['r_pearson']) > 0.4) else ""
        print(f"\n{question[:60]}")
        print(f"  Category: {category} | Assigned: {assigned_ticker}")
        print(f"  Top corr: {top_ticker['ticker']} r={top_ticker['r_pearson']:.3f} {surprise_flag}")
        for tc in ticker_corrs[1:4]:
            s = "SURPRISE" if (tc['ticker'] != assigned_ticker and abs(tc['r_pearson']) > 0.4) else ""
            print(f"           {tc['ticker']} r={tc['r_pearson']:.3f} {s}")

# Save and summarize
print(f"\n\n=== SUMMARY ===")
df = pd.DataFrame(results)

if len(df) > 0:
    print(f"Total market-ticker pairs tested: {len(df)}")

    surprises = df[df['is_surprise'] == True]
    print(f"Surprise correlations (non-assigned, |r|>0.4, rank<=5): {len(surprises)}")

    if len(surprises) > 0:
        print("\n=== TOP SURPRISE CORRELATIONS ===")
        print(surprises.sort_values('r_pearson', key=abs, ascending=False)[
            ['question','category','assigned_ticker','corr_ticker','r_pearson','r_spearman','n_days']
        ].head(20).to_string())

    # How often is the assigned ticker actually #1?
    top1 = df[df['rank'] == 1]
    assigned_is_top = top1[top1['is_assigned'] == True]
    print(f"\nAssigned ticker is #1 correlation in: {len(assigned_is_top)}/{len(top1)} markets ({len(assigned_is_top)/max(len(top1),1):.0%})")

    # Strongest overall correlations
    print("\n=== STRONGEST CORRELATIONS (|r| > 0.5) ===")
    strong = df[abs(df['r_pearson']) > 0.5].sort_values('r_pearson', key=abs, ascending=False)
    print(strong[['question','category','assigned_ticker','corr_ticker','r_pearson','n_days','is_assigned']].head(20).to_string())

    Path("outputs/research").mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved to {OUTPUT_CSV}")
else:
    print("No results found")
