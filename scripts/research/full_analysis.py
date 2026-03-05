import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path

db = pd.read_parquet('data/historical/correlation_db.parquet')
markets_meta = pd.read_csv('data/historical/relevant_markets.csv')
markets_meta['end_date'] = pd.to_datetime(markets_meta['end_date'], errors='coerce')

print(f"DB: {len(db):,} rows | {db['market_id'].nunique()} markets | {db['ticker'].nunique()} tickers")

# Focus: lag=0, exclude pre_2022 noise, enough data
clean = db[
    (db['lag_days'] == 0) &
    (db['epoch'].isin(['2022_2023', '2024', '2025'])) &
    (db['n_overlap_days'] >= 30)
].copy()

print(f"\nClean subset: {len(clean):,} rows, {clean['market_id'].nunique()} markets")

# ===== ANALYSIS 1: Which tickers appear consistently across categories? =====
print("\n\n=== ANALYSIS 1: Cross-category consistency ===")
# For each ticker: how many DIFFERENT categories does it appear in top-5?
ticker_cats = clean[clean['rank_by_abs_pearson'] <= 5].groupby('ticker')['event_category'].nunique()
ticker_markets = clean[clean['rank_by_abs_pearson'] <= 5].groupby('ticker')['market_id'].nunique()
ticker_avg_r = clean[clean['rank_by_abs_pearson'] <= 5].groupby('ticker')['abs_pearson'].mean()

cross_cat = pd.DataFrame({
    'n_categories': ticker_cats,
    'n_markets_top5': ticker_markets,
    'avg_abs_r': ticker_avg_r
}).sort_values(['n_categories', 'n_markets_top5'], ascending=False).head(25)

print(cross_cat.to_string())

# ===== ANALYSIS 2: Statistical significance by category x ticker =====
print("\n\n=== ANALYSIS 2: Statistically significant signals (p<0.05, N>=50) ===")
sig = clean[
    (clean['pearson_p'] < 0.05) &
    (clean['n_overlap_days'] >= 50)
].copy()

sig_summary = sig.groupby(['event_category', 'ticker']).agg(
    n_markets=('market_id', 'nunique'),
    avg_r=('pearson_r', 'mean'),
    avg_abs_r=('abs_pearson', 'mean'),
    pct_top5=('rank_by_abs_pearson', lambda x: (x <= 5).mean()),
).reset_index()

sig_summary = sig_summary[sig_summary['n_markets'] >= 3].sort_values('avg_abs_r', ascending=False)
print(sig_summary.head(30).to_string())

# ===== ANALYSIS 3: Epoch comparison - does signal persist over time? =====
print("\n\n=== ANALYSIS 3: Signal strength by epoch ===")
epoch_analysis = clean.groupby(['ticker', 'epoch']).agg(
    n_markets=('market_id', 'nunique'),
    avg_abs_r=('abs_pearson', 'mean'),
    pct_top5=('rank_by_abs_pearson', lambda x: (x <= 5).mean()),
).reset_index()

# Tickers that appear in BOTH 2024 AND 2025 with avg|r| > 0.1
in_2024 = set(epoch_analysis[(epoch_analysis['epoch']=='2024') & (epoch_analysis['avg_abs_r']>0.1)]['ticker'])
in_2025 = set(epoch_analysis[(epoch_analysis['epoch']=='2025') & (epoch_analysis['avg_abs_r']>0.1)]['ticker'])
consistent = in_2024 & in_2025

print(f"\nTickers with avg|r|>0.1 in BOTH 2024 AND 2025: {len(consistent)}")
consistent_df = epoch_analysis[
    (epoch_analysis['ticker'].isin(consistent)) &
    (epoch_analysis['epoch'].isin(['2024','2025']))
].pivot_table(index='ticker', columns='epoch', values='avg_abs_r').dropna()
consistent_df['avg'] = consistent_df.mean(axis=1)
print(consistent_df.sort_values('avg', ascending=False).head(20).to_string())

# ===== ANALYSIS 4: Capa 1 (Slow Build) with all 813 markets =====
print("\n\n=== ANALYSIS 4: Capa 1 (Slow Build) with all markets ===")

# Load all price series, detect slow build periods
price_dir = Path('data/historical/price_series_historical')
stock_dir = Path('data/historical/stock_prices')

# Load stocks
stocks = {}
for f in stock_dir.glob('*_full.parquet'):
    ticker = f.stem.replace('_full', '')
    try:
        df = pd.read_parquet(f)
        df.columns = [c.lower() for c in df.columns]
        date_col = next((c for c in df.columns if 'date' in c), None)
        close_col = next((c for c in df.columns if 'close' in c), None)
        if not date_col or not close_col:
            continue
        df['date'] = pd.to_datetime(df[date_col]).dt.date
        df['close'] = pd.to_numeric(df[close_col], errors='coerce')
        df = df.sort_values('date').dropna(subset=['close'])
        df['daily_return'] = df['close'].pct_change()
        stocks[ticker] = df[['date', 'close', 'daily_return']].copy()
    except:
        pass

print(f"Loaded {len(stocks)} stocks")

# Build metadata index
meta = markets_meta[['id','event_category','volume_total','end_date']].set_index('id')

signals = []
n_processed = 0

for market_file in price_dir.glob('*.parquet'):
    market_id = market_file.stem
    try:
        ms = pd.read_parquet(market_file)
        ms['date'] = pd.to_datetime(ms['date']).dt.date
        ms = ms.sort_values('date').dropna(subset=['price_vwap'])
        
        if len(ms) < 15:
            continue
        
        n_processed += 1
        prices = ms['price_vwap'].values
        dates = ms['date'].values
        
        # Detect slow build: >=5 consecutive days rising, >=8pp change
        for i in range(len(prices) - 5):
            window = prices[i:i+6]
            # Check monotonically increasing (allow 1 small dip of < 1pp)
            diffs = np.diff(window)
            neg_diffs = diffs[diffs < 0]
            if len(neg_diffs) > 1:
                continue
            if len(neg_diffs) == 1 and abs(neg_diffs[0]) > 0.01:
                continue
            
            total_change = window[-1] - window[0]
            if total_change < 0.08:  # at least 8pp rise
                continue
            
            # Get market metadata
            cat = meta.loc[market_id, 'event_category'] if market_id in meta.index else 'unknown'
            vol = meta.loc[market_id, 'volume_total'] if market_id in meta.index else 0
            end_dt = meta.loc[market_id, 'end_date'] if market_id in meta.index else None
            
            # Determine epoch
            if end_dt is not None and not pd.isna(end_dt):
                year = pd.Timestamp(end_dt).year
                if year <= 2022:
                    epoch = '2022_2023'
                elif year == 2023:
                    epoch = '2022_2023'
                elif year == 2024:
                    epoch = '2024'
                else:
                    epoch = '2025'
            else:
                epoch = 'unknown'
            
            build_start_date = dates[i]
            build_end_date = dates[i+5]
            
            # Match with stocks: measure return 7d and 14d after build_end_date
            for ticker in ['XLE', 'GLD', 'TLT', 'ITA', 'LMT', 'RTX', 'DJT', 'EWG', 'KSA', 'COIN', 'DRS', 'GOLD', 'NOC', 'BA', 'CACI']:
                if ticker not in stocks:
                    continue
                st = stocks[ticker]
                
                # Return 7d after build end
                target_date_7d = (pd.Timestamp(build_end_date) + pd.Timedelta(days=7)).date()
                future_7d = st[st['date'] >= target_date_7d]
                ref = st[st['date'] <= build_end_date]
                
                if len(future_7d) == 0 or len(ref) == 0:
                    continue
                
                price_at_end = ref.iloc[-1]['close']
                price_7d = future_7d.iloc[0]['close']
                return_7d = (price_7d - price_at_end) / price_at_end if price_at_end > 0 else np.nan
                
                target_date_14d = (pd.Timestamp(build_end_date) + pd.Timedelta(days=14)).date()
                future_14d = st[st['date'] >= target_date_14d]
                price_14d = future_14d.iloc[0]['close'] if len(future_14d) > 0 else np.nan
                return_14d = (price_14d - price_at_end) / price_at_end if price_at_end > 0 and not np.isnan(price_14d) else np.nan
                
                signals.append({
                    'market_id': market_id,
                    'event_category': cat,
                    'volume_total': vol,
                    'epoch': epoch,
                    'build_start': str(build_start_date),
                    'build_end': str(build_end_date),
                    'price_change_pp': round(float(total_change * 100), 1),
                    'ticker': ticker,
                    'return_7d': round(float(return_7d), 4) if not np.isnan(return_7d) else None,
                    'return_14d': round(float(return_14d), 4) if not np.isnan(return_14d) else None,
                })
    except Exception as e:
        continue

print(f"\nProcessed {n_processed} markets")
print(f"Total slow build signals: {len(signals)}")

if signals:
    sig_df = pd.DataFrame(signals).dropna(subset=['return_7d'])
    
    print(f"Signals with 7d return data: {len(sig_df)}")
    print(f"Unique markets with signals: {sig_df['market_id'].nunique()}")
    
    # Overall: does return_7d > 0 after a slow build?
    overall_mean = sig_df['return_7d'].mean()
    t_stat, p_val = stats.ttest_1samp(sig_df['return_7d'].dropna(), 0)
    print(f"\nOverall 7d return after slow build: {overall_mean:.4f} ({overall_mean*100:.2f}%)")
    print(f"t-statistic: {t_stat:.3f}, p-value: {p_val:.4f}")
    
    # By category
    print("\nBy category (min 10 signals):")
    for cat, group in sig_df.groupby('event_category'):
        if len(group) < 10:
            continue
        mean_r = group['return_7d'].mean()
        t, p = stats.ttest_1samp(group['return_7d'].dropna(), 0)
        pct_pos = (group['return_7d'] > 0).mean()
        print(f"  {cat:15s} N={len(group):4d} mean={mean_r*100:+.2f}% pct_pos={pct_pos:.0%} t={t:.2f} p={p:.4f}")
    
    # By epoch
    print("\nBy epoch (min 10 signals):")
    for epoch, group in sig_df.groupby('epoch'):
        if len(group) < 10:
            continue
        mean_r = group['return_7d'].mean()
        t, p = stats.ttest_1samp(group['return_7d'].dropna(), 0)
        print(f"  {epoch:15s} N={len(group):4d} mean={mean_r*100:+.2f}% t={t:.2f} p={p:.4f}")
    
    # By ticker
    print("\nBy ticker (min 20 signals):")
    for ticker, group in sig_df.groupby('ticker'):
        if len(group) < 20:
            continue
        mean_r = group['return_7d'].mean()
        t, p = stats.ttest_1samp(group['return_7d'].dropna(), 0)
        pct_pos = (group['return_7d'] > 0).mean()
        print(f"  {ticker:8s} N={len(group):4d} mean={mean_r*100:+.2f}% pct_pos={pct_pos:.0%} t={t:.2f} p={p:.4f}")
    
    sig_df.to_csv('outputs/research/capa1_slow_build_full.csv', index=False)
    print(f"\nSaved to outputs/research/capa1_slow_build_full.csv")

print("\n=== DONE ===")
