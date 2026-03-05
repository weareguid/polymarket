"""
Phase 3: Fetch historical stock prices via yfinance for all tickers
that appear in relevant markets.

For each market in relevant_markets.csv, download stock price data
for the matched tickers over the market window + a 30-day post window.

Output:
- data/historical/stock_prices/{TICKER}_YYYY-MM-DD_YYYY-MM-DD.parquet
- data/historical/stock_prices_index.csv  — which tickers/windows we have
"""

import json
import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_CSV = "data/historical/relevant_markets.csv"
OUTPUT_DIR = Path("data/historical/stock_prices")
INDEX_CSV = "data/historical/stock_prices_index.csv"

# How many days after market end to observe stock impact
POST_EVENT_WINDOW_DAYS = 30
PRE_EVENT_WINDOW_DAYS = 14  # Also grab some days before for baseline

# Round download windows to quarters to maximize cache reuse
ROUND_TO_QUARTER = True


def round_to_quarter(dt: datetime) -> datetime:
    """Round date to nearest quarter for caching."""
    month = (((dt.month - 1) // 3) * 3) + 1
    return dt.replace(month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def fetch_ticker(
    ticker: str, start: datetime, end: datetime, cache: dict
) -> tuple[pd.DataFrame, str]:
    """Download ticker data with simple in-memory cache."""
    cache_key = f"{ticker}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}"
    if cache_key in cache:
        return cache[cache_key], cache_key

    try:
        data = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if data.empty:
            cache[cache_key] = pd.DataFrame()
        else:
            # Flatten multi-index columns if needed
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)
            data = data.reset_index()
            data["Date"] = pd.to_datetime(data["Date"], utc=True, errors="coerce")
            cache[cache_key] = data
        return cache[cache_key], cache_key
    except Exception as e:
        print(f"    ERROR fetching {ticker}: {e}")
        cache[cache_key] = pd.DataFrame()
        return pd.DataFrame(), cache_key


def compute_stock_returns(
    stock_df: pd.DataFrame,
    event_start: datetime,
    event_end: datetime,
) -> dict:
    """
    Compute stock returns at multiple horizons relative to event.

    Returns dict with:
    - return_during_event: return from market start to end
    - return_1d_post: return on day 1 after event end
    - return_3d_post: cumulative return days 1-3 after event end
    - return_7d_post: cumulative return days 1-7 after event end
    - return_14d_post: cumulative return days 1-14 after event end
    - return_30d_post: cumulative return days 1-30 after event end
    - pre_event_vol: volatility in 14 days before event (annualized)
    """
    if stock_df.empty or "Close" not in stock_df.columns:
        return {}

    df = stock_df.copy()
    df["Date"] = pd.to_datetime(df["Date"], utc=True, errors="coerce")
    df = df.sort_values("Date").set_index("Date")

    def safe_return(start_dt, end_dt):
        """Calculate return between two dates."""
        window = df.loc[start_dt:end_dt, "Close"]
        if len(window) < 2:
            return None
        return float(window.iloc[-1] / window.iloc[0] - 1)

    def safe_vol(start_dt, end_dt):
        """Calculate annualized volatility."""
        window = df.loc[start_dt:end_dt, "Close"]
        if len(window) < 5:
            return None
        returns = window.pct_change().dropna()
        return float(returns.std() * (252 ** 0.5))

    return {
        "return_during_event": safe_return(event_start, event_end),
        "return_1d_post": safe_return(
            event_end, event_end + timedelta(days=2)
        ),
        "return_3d_post": safe_return(
            event_end, event_end + timedelta(days=5)
        ),
        "return_7d_post": safe_return(
            event_end, event_end + timedelta(days=10)
        ),
        "return_14d_post": safe_return(
            event_end, event_end + timedelta(days=20)
        ),
        "return_30d_post": safe_return(
            event_end, event_end + timedelta(days=35)
        ),
        "pre_event_volatility": safe_vol(
            event_start - timedelta(days=PRE_EVENT_WINDOW_DAYS), event_start
        ),
    }


def main():
    print("=== Phase 3: Fetch Stock Prices via yfinance ===\n")

    df = pd.read_csv(INPUT_CSV)
    df["volume_total"] = pd.to_numeric(df["volume_total"], errors="coerce").fillna(0)
    df["start_date"] = pd.to_datetime(df["start_date"], utc=True, errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], utc=True, errors="coerce")

    # Get all unique tickers needed
    all_tickers = set()
    for tickers_json in df["matched_tickers"].dropna():
        try:
            tickers = json.loads(tickers_json) if isinstance(tickers_json, str) else tickers_json
            all_tickers.update(tickers)
        except Exception:
            pass

    print(f"Total unique tickers needed: {len(all_tickers)}")
    print(f"Tickers: {sorted(all_tickers)}\n")

    # Remove crypto tickers that yfinance handles differently (or might not have data)
    # We'll handle crypto separately (prices are 24/7, no trading halts)
    equity_tickers = {t for t in all_tickers if not t.endswith("-USD")}
    crypto_tickers = {t for t in all_tickers if t.endswith("-USD")}
    print(f"Equity tickers: {len(equity_tickers)}")
    print(f"Crypto tickers: {len(crypto_tickers)}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Download full history for each ticker (2020-present) ---
    # One bulk download per ticker, then slice as needed
    print("\n--- Downloading full ticker history (2020-2026) ---")

    ticker_data = {}
    global_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    global_end = datetime.now(timezone.utc)

    for i, ticker in enumerate(sorted(equity_tickers | crypto_tickers), 1):
        out_path = OUTPUT_DIR / f"{ticker}_full.parquet"

        if out_path.exists():
            print(f"  [{i}/{len(equity_tickers | crypto_tickers)}] {ticker}: cached")
            ticker_data[ticker] = pd.read_parquet(out_path)
            continue

        try:
            data = yf.download(
                ticker,
                start="2020-01-01",
                end=global_end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.droplevel(1)
                data = data.reset_index()
                data.to_parquet(out_path, index=False)
                ticker_data[ticker] = data
                print(f"  [{i}/{len(equity_tickers | crypto_tickers)}] {ticker}: {len(data)} days saved")
            else:
                print(f"  [{i}/{len(equity_tickers | crypto_tickers)}] {ticker}: EMPTY")
        except Exception as e:
            print(f"  [{i}/{len(equity_tickers | crypto_tickers)}] {ticker}: ERROR {e}")

    # --- Compute returns for each market ---
    print("\n--- Computing stock returns per market ---")

    records = []
    for _, row in df.iterrows():
        market_id = row["id"]
        question = str(row["question"])[:60]
        event_start = row["start_date"]
        event_end = row["end_date"]
        yes_final = float(row.get("yes_price_final", 0) or 0)
        volume = float(row["volume_total"])
        event_cat = row["event_category"]

        tickers = json.loads(row["matched_tickers"]) if isinstance(row.get("matched_tickers"), str) else []

        # Skip if dates are invalid or too far in future
        if pd.isna(event_start) or pd.isna(event_end):
            continue
        if event_end > datetime.now(timezone.utc) + timedelta(days=1):
            continue  # Skip open/future markets

        for ticker in tickers:
            if ticker not in ticker_data:
                continue
            stock_df = ticker_data[ticker]
            if stock_df.empty:
                continue

            returns = compute_stock_returns(stock_df, event_start, event_end)

            records.append({
                "market_id": market_id,
                "question": str(row["question"]),
                "ticker": ticker,
                "event_category": event_cat,
                "volume_total": volume,
                "yes_price_final": yes_final,
                "event_start": event_start,
                "event_end": event_end,
                **returns,
            })

    if records:
        results_df = pd.DataFrame(records)
        results_df.to_csv(INDEX_CSV, index=False)
        results_df.to_parquet(INDEX_CSV.replace(".csv", ".parquet"), index=False)
        print(f"\nStock returns computed for {len(results_df):,} market-ticker pairs")
        print(f"Saved to {INDEX_CSV}")

        # Quick stats
        with_returns = results_df.dropna(subset=["return_7d_post"])
        print(f"Pairs with 7d post return: {len(with_returns):,}")
        print("\nMean 7d post-event return by category:")
        if not with_returns.empty:
            print(
                with_returns.groupby("event_category")["return_7d_post"]
                .agg(["mean", "count"])
                .sort_values("mean", ascending=False)
                .to_string()
            )
    else:
        print("No records generated.")


if __name__ == "__main__":
    main()
