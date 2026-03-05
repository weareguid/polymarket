"""
Incremental Correlation Pipeline — runs after each download batch.

For each newly downloaded market:
- Correlates its daily price series with all stock tickers
- Records: market_id, ticker, pearson_r, spearman_r, n_overlap_days, lag_days,
           market_category, market_volume, market_question, epoch, is_assigned_ticker, surprise_rank
- Appends to data/historical/correlation_db.parquet (never overwrites old data)

Run after each batch download. Re-running is safe (skips already-processed markets).

Output: data/historical/correlation_db.parquet
Summary: outputs/research/correlation_summary.csv
"""

import pandas as pd
import numpy as np
from scipy.stats import pearsonr, spearmanr
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BASE_DIR = Path("/Users/santiagobattezzati/repos/Polymarket")
PRICE_SERIES_DIR = BASE_DIR / "data/historical/price_series_historical"
STOCK_DIR = BASE_DIR / "data/historical/stock_prices"
MARKETS_CSV = BASE_DIR / "data/historical/relevant_markets.csv"
CORR_DB_PATH = BASE_DIR / "data/historical/correlation_db.parquet"
SUMMARY_PATH = BASE_DIR / "outputs/research/correlation_summary.csv"

# Lags to test (days): 0 = same day, 1 = stock moves 1 day after probability change
LAGS_TO_TEST = [0, 1, 3, 7, 14]

# Minimum overlap days between market series and stock series
MIN_OVERLAP_DAYS = 20

# Epoch boundaries for data quality segmentation
EPOCH_BOUNDARIES = {
    "pre_2022": ("2020-01-01", "2022-02-01"),
    "2022_2023": ("2022-02-01", "2024-01-01"),
    "2024": ("2024-01-01", "2025-01-01"),
    "2025": ("2025-01-01", "2026-03-01"),
}


def get_epoch(end_date):
    """Classify a market by its epoch based on end_date."""
    if pd.isna(end_date):
        return "unknown"
    for name, (start, end) in EPOCH_BOUNDARIES.items():
        if pd.Timestamp(start, tz="UTC") <= end_date < pd.Timestamp(end, tz="UTC"):
            return name
    return "pre_2022"


def load_stock_data():
    """
    Load all stock price series into a dict: ticker -> DataFrame(date, close, daily_return).

    Handles two formats stored on disk:
      1. Flat columns: Date, Close, High, Low, Open, Volume  (RangeIndex)
      2. MultiIndex columns: (Close, TICKER), ...  (Date as index)
    """
    stocks = {}
    for f in STOCK_DIR.glob("*_full.parquet"):
        ticker = f.stem.replace("_full", "")
        try:
            df = pd.read_parquet(f)

            # --- Format detection ---
            if isinstance(df.columns, pd.MultiIndex):
                # MultiIndex format: columns like ('Close', 'AAPL'), index is Date
                df = df.copy()
                df.columns = [c[0].lower() for c in df.columns]
                df.index.name = "date"
                df = df.reset_index()
                df["date"] = pd.to_datetime(df["date"]).dt.date
            else:
                # Flat format: columns Date, Close, ...
                df.columns = [c.lower() for c in df.columns]
                date_col = next((c for c in df.columns if "date" in c), None)
                if not date_col:
                    continue
                df["date"] = pd.to_datetime(df[date_col]).dt.date

            close_col = next((c for c in df.columns if c == "close"), None)
            if not close_col:
                continue

            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.sort_values("date").dropna(subset=["close"])
            df["daily_return"] = df["close"].pct_change()
            stocks[ticker] = df[["date", "close", "daily_return"]].copy()
        except Exception as e:
            print(f"  Warning: could not load {ticker}: {e}")

    print(f"Loaded {len(stocks)} stock tickers")
    return stocks


def load_market_metadata():
    """Load market metadata for joining."""
    df = pd.read_csv(MARKETS_CSV)
    df["volume_total"] = pd.to_numeric(df["volume_total"], errors="coerce").fillna(0)
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce", utc=True)
    df["epoch"] = df["end_date"].apply(get_epoch)
    return df.set_index("id")


def get_assigned_tickers(category, question):
    """Simple heuristic for what tickers were 'assigned' in the original KB."""
    q = question.lower() if question else ""

    assignments = []
    if any(k in q for k in ["fed", "rate", "fomc", "powell", "inflation", "cpi"]):
        assignments = ["TLT", "SHY", "IEF"]
    elif any(k in q for k in ["trump", "republican", "gop"]):
        assignments = ["DJT", "XLE", "GEO"]
    elif any(k in q for k in ["iran", "israel", "ukraine", "russia", "war", "attack", "ceasefire"]):
        assignments = ["XLE", "GLD", "RTX", "LMT", "ITA"]
    elif any(k in q for k in ["oil", "opec", "crude", "energy"]):
        assignments = ["XLE", "USO", "OIH"]
    elif any(k in q for k in ["nvidia", "ai", "openai", "llm", "chip", "semiconductor"]):
        assignments = ["NVDA", "SOXX", "AMD"]
    elif any(k in q for k in ["bitcoin", "crypto", "btc"]):
        assignments = ["MSTR", "COIN"]
    elif any(k in q for k in ["election", "harris", "democrat", "biden"]):
        assignments = ["TLT", "GLD"]
    elif "gold" in q or "gld" in q:
        assignments = ["GLD", "GDX"]
    return assignments


def correlate_market_with_stocks(market_series, stocks, lags=LAGS_TO_TEST):
    """
    For one market's price series, compute correlation with all stocks at multiple lags.
    Returns list of dicts with correlation results.
    """
    results = []

    # Prepare market series
    ms = market_series.copy()
    ms["date"] = pd.to_datetime(ms["date"]).dt.date
    ms = ms.sort_values("date").dropna(subset=["price_vwap"])

    if len(ms) < MIN_OVERLAP_DAYS:
        return results

    for ticker, stock_df in stocks.items():
        for lag in lags:
            if lag == 0:
                merged = ms.merge(
                    stock_df[["date", "close", "daily_return"]], on="date", how="inner"
                )
            else:
                # Shift stock returns forward by lag days
                # Market signal at date T correlates with stock at T+lag
                ms_lagged = ms.copy()
                ms_lagged["stock_date"] = (
                    pd.to_datetime(ms_lagged["date"]) + pd.Timedelta(days=lag)
                ).dt.date
                merged = ms_lagged.merge(
                    stock_df[["date", "daily_return"]].rename(columns={"date": "stock_date"}),
                    on="stock_date",
                    how="inner",
                )

            if len(merged) < MIN_OVERLAP_DAYS:
                continue

            x = merged["price_vwap"].values
            y = merged["daily_return"].values

            # Remove NaN / Inf
            mask = ~(np.isnan(x) | np.isnan(y) | np.isinf(y) | np.isinf(x))
            x, y = x[mask], y[mask]

            if len(x) < MIN_OVERLAP_DAYS:
                continue

            try:
                pearson_r, pearson_p = pearsonr(x, y)
                spearman_r, spearman_p = spearmanr(x, y)
            except Exception:
                continue

            results.append(
                {
                    "ticker": ticker,
                    "lag_days": lag,
                    "pearson_r": round(float(pearson_r), 4),
                    "pearson_p": round(float(pearson_p), 4),
                    "spearman_r": round(float(spearman_r), 4),
                    "spearman_p": round(float(spearman_p), 4),
                    "n_overlap_days": int(len(x)),
                    "abs_pearson": abs(float(pearson_r)),
                }
            )

    return results


def rank_correlations(results):
    """Add rank by abs_pearson for each lag."""
    if not results:
        return results
    df = pd.DataFrame(results)
    df["rank_by_abs_pearson"] = (
        df.groupby("lag_days")["abs_pearson"]
        .rank(ascending=False, method="min")
        .astype(int)
    )
    return df.to_dict("records")


def main():
    print("=== Incremental Correlation Pipeline ===\n")

    # Load metadata and stocks
    markets_meta = load_market_metadata()
    stocks = load_stock_data()

    if not stocks:
        print("ERROR: No stock data found. Run stock download script first.")
        return

    # Load existing DB to find already-processed markets
    already_processed = set()
    if CORR_DB_PATH.exists():
        existing_db = pd.read_parquet(CORR_DB_PATH)
        already_processed = set(existing_db["market_id"].unique())
        print(
            f"Existing DB: {len(existing_db):,} rows, "
            f"{len(already_processed)} markets already processed"
        )
    else:
        existing_db = pd.DataFrame()
        print("No existing DB — starting fresh")

    # Find all downloaded market series
    all_market_files = list(PRICE_SERIES_DIR.glob("*.parquet"))
    new_files = [f for f in all_market_files if f.stem not in already_processed]

    print(f"\nTotal market series on disk: {len(all_market_files)}")
    print(f"Already processed:           {len(already_processed)}")
    print(f"New to process:              {len(new_files)}\n")

    if not new_files:
        print("Nothing new to process.")
    else:
        new_rows = []

        for i, market_file in enumerate(new_files, 1):
            market_id = market_file.stem

            try:
                market_series = pd.read_parquet(market_file)
            except Exception as e:
                print(f"  [{i}/{len(new_files)}] Error reading {market_id}: {e}")
                continue

            # Get metadata
            meta = markets_meta.loc[market_id] if market_id in markets_meta.index else None
            category = meta["event_category"] if meta is not None else "unknown"
            question = meta["question"] if meta is not None else ""
            volume = meta["volume_total"] if meta is not None else 0
            epoch = meta["epoch"] if meta is not None else "unknown"
            end_date = str(meta["end_date"])[:10] if meta is not None else ""

            # Get assigned tickers from original KB
            assigned = set(get_assigned_tickers(category, question))

            # Correlate with all stocks
            raw_results = correlate_market_with_stocks(market_series, stocks)
            if not raw_results:
                if i <= 5 or i % 20 == 0:
                    print(
                        f"  [{i}/{len(new_files)}] SKIP (too short) | "
                        f"{category} | {str(question)[:60]}"
                    )
                continue

            ranked_results = rank_correlations(raw_results)

            for r in ranked_results:
                new_rows.append(
                    {
                        "market_id": market_id,
                        "question": str(question)[:120],
                        "event_category": category,
                        "volume_total": float(volume),
                        "end_date": end_date,
                        "epoch": epoch,
                        "ticker": r["ticker"],
                        "lag_days": r["lag_days"],
                        "pearson_r": r["pearson_r"],
                        "pearson_p": r["pearson_p"],
                        "spearman_r": r["spearman_r"],
                        "spearman_p": r["spearman_p"],
                        "n_overlap_days": r["n_overlap_days"],
                        "abs_pearson": r["abs_pearson"],
                        "rank_by_abs_pearson": r["rank_by_abs_pearson"],
                        "is_assigned_ticker": r["ticker"] in assigned,
                        "is_surprise": (
                            (r["ticker"] not in assigned)
                            and (r["abs_pearson"] > 0.3)
                            and (r["rank_by_abs_pearson"] <= 5)
                        ),
                    }
                )

            if i % 10 == 0 or i <= 3:
                top = min(
                    (rr for rr in ranked_results if rr["lag_days"] == 0),
                    key=lambda x: x["rank_by_abs_pearson"],
                    default=ranked_results[0] if ranked_results else {},
                )
                print(
                    f"  [{i:3d}/{len(new_files)}] {category:12s} | "
                    f"{str(question)[:55]:55s} | "
                    f"top={top.get('ticker','?'):6s} r={top.get('pearson_r', 0):+.3f}"
                )

        # Append to DB
        if new_rows:
            new_df = pd.DataFrame(new_rows)
            full_db = (
                pd.concat([existing_db, new_df], ignore_index=True)
                if len(existing_db) > 0
                else new_df
            )
            CORR_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            full_db.to_parquet(CORR_DB_PATH, index=False)
            print(
                f"\nDB updated: {len(full_db):,} rows total "
                f"({len(new_rows):,} new from {len(new_files)} markets)"
            )
        else:
            full_db = existing_db
            print("\nNo new rows to add.")

    # -----------------------------------------------------------------------
    # Generate summary: for each (category, ticker, lag) — avg |r|, N, % top-5
    # -----------------------------------------------------------------------
    print("\n--- Generating summary ---")

    if CORR_DB_PATH.exists():
        db = pd.read_parquet(CORR_DB_PATH)

        # Focus on lag=0 and lag=3/7, exclude pre_2022 (noisy), require decent overlap
        db_clean = db[
            (db["lag_days"].isin([0, 3, 7]))
            & (db["epoch"] != "pre_2022")
            & (db["n_overlap_days"] >= 30)
        ].copy()

        if len(db_clean) > 0:
            summary = (
                db_clean.groupby(["event_category", "ticker", "lag_days"])
                .agg(
                    n_markets=("market_id", "nunique"),
                    avg_abs_pearson=("abs_pearson", "mean"),
                    avg_spearman_r=("spearman_r", "mean"),
                    pct_top5=("rank_by_abs_pearson", lambda x: (x <= 5).mean()),
                    pct_surprise=("is_surprise", "mean"),
                    pct_assigned=("is_assigned_ticker", "mean"),
                )
                .reset_index()
            )

            summary = summary.sort_values(
                ["event_category", "lag_days", "avg_abs_pearson"],
                ascending=[True, True, False],
            )

            SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
            summary.to_csv(SUMMARY_PATH, index=False)

            print(
                f"\nTop correlations by category "
                f"(lag=0, 2022+, >=30 overlap days):"
            )
            print("-" * 85)

            for cat in sorted(db_clean["event_category"].unique()):
                sub = summary[
                    (summary["event_category"] == cat) & (summary["lag_days"] == 0)
                ]
                if len(sub) == 0:
                    continue
                n_mkts = sub["n_markets"].max()
                top5 = sub.nlargest(5, "avg_abs_pearson")
                print(f"\n{cat.upper()} ({int(n_mkts)} markets, lag=0):")
                for _, row in top5.iterrows():
                    flag = (
                        "assigned"
                        if row["pct_assigned"] > 0
                        else "SURPRISE"
                    )
                    print(
                        f"  {row['ticker']:8s} | "
                        f"avg|r|={row['avg_abs_pearson']:.3f} | "
                        f"top5_rate={row['pct_top5']:.0%} | "
                        f"n={int(row['n_markets'])} | "
                        f"{flag}"
                    )

            # Also show lag=3 surprises across all categories
            surprises = summary[
                (summary["lag_days"] == 3)
                & (summary["pct_assigned"] == 0)
                & (summary["avg_abs_pearson"] > 0.25)
                & (summary["n_markets"] >= 2)
            ].sort_values("avg_abs_pearson", ascending=False)

            if len(surprises) > 0:
                print(f"\n\nSURPRISES at lag=3 (unassigned, avg|r|>0.25, n>=2 markets):")
                print("-" * 85)
                for _, row in surprises.head(10).iterrows():
                    print(
                        f"  {row['event_category']:14s} | "
                        f"{row['ticker']:8s} | "
                        f"avg|r|={row['avg_abs_pearson']:.3f} | "
                        f"n={int(row['n_markets'])}"
                    )

            print(f"\nFull summary saved to {SUMMARY_PATH}")
            print(
                f"DB stats: {len(db):,} rows | "
                f"{db['market_id'].nunique()} markets | "
                f"{db['ticker'].nunique()} tickers | "
                f"file size: {CORR_DB_PATH.stat().st_size / 1024:.1f} KB"
            )
        else:
            print("Not enough clean data for summary yet.")
    else:
        print("DB file not found — nothing to summarize.")


if __name__ == "__main__":
    main()
