"""
Phase 2: Fetch CLOB price history for relevant markets.

Strategy:
- For each financially relevant market, try to get daily price series from CLOB API.
- CLOB retains history for active + recently closed markets (~6 months back).
- For older markets: price series will be empty → fall back to final price only.
- Save per-market price series as parquet files.

Output:
- data/historical/price_series/{market_id}.parquet  — daily price series per market
- data/historical/price_series_index.csv            — index of which markets have data
"""

import json
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_CSV = "data/historical/relevant_markets.csv"
OUTPUT_DIR = Path("data/historical/price_series")
INDEX_CSV = "data/historical/price_series_index.csv"

# Only try markets from the last N months (CLOB likely retains this long)
MAX_AGE_MONTHS = 9
PAUSE_BETWEEN_REQUESTS = 0.3  # seconds
CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"

# Priority categories for the first run (most financially impactful)
PRIORITY_CATEGORIES = {"geopolitical", "macro", "us_politics", "corporate", "ai", "energy", "defense"}
MIN_VOLUME_FOR_PRIORITY = 500_000  # Focus on high-volume markets first


def fetch_token_ids(condition_id: str) -> list[str]:
    """Get CLOB token IDs from Gamma API using condition ID."""
    try:
        r = requests.get(
            f"{GAMMA_BASE}/markets",
            params={"condition_id": condition_id},
            timeout=10,
        )
        if r.ok and r.json():
            market = r.json()[0]
            tokens = market.get("clobTokenIds", "[]")
            if isinstance(tokens, str):
                tokens = json.loads(tokens)
            return tokens
    except Exception as e:
        pass
    return []


def fetch_price_history(token_id: str, fidelity: int = 60) -> pd.DataFrame:
    """
    Fetch price history from CLOB API for a token.
    Returns DataFrame with columns: [timestamp, price]
    fidelity = minutes between data points (60 = hourly, 1440 = daily)
    """
    try:
        r = requests.get(
            f"{CLOB_BASE}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": fidelity},
            timeout=15,
        )
        if not r.ok:
            return pd.DataFrame()
        history = r.json().get("history", [])
        if not history:
            return pd.DataFrame()
        df = pd.DataFrame(history)
        df.columns = ["timestamp", "price"]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df["price"] = df["price"].astype(float)
        return df.sort_values("timestamp")
    except Exception as e:
        return pd.DataFrame()


def compute_volume_metrics(df: pd.DataFrame) -> dict:
    """
    From a daily price series, compute momentum and change metrics.
    These proxy for market activity / interest.
    """
    if len(df) < 3:
        return {}

    prices = df["price"].values
    first_price = prices[0]
    last_price = prices[-1]

    # Price change metrics
    total_change = last_price - first_price
    max_price = prices.max()
    min_price = prices.min()

    # Price velocity: change per day
    n_days = (df["timestamp"].max() - df["timestamp"].min()).days or 1
    daily_change = total_change / n_days

    # Momentum: did price accelerate in final 25% of the market?
    split = int(len(prices) * 0.75)
    early_change = prices[split] - prices[0] if split > 0 else 0
    late_change = prices[-1] - prices[split] if split < len(prices) - 1 else 0

    # Spike detection: was there a 1-day jump > 20pp?
    daily_diffs = pd.Series(prices).diff().abs()
    max_1day_spike = daily_diffs.max() if len(daily_diffs) > 1 else 0

    return {
        "price_first": float(first_price),
        "price_last": float(last_price),
        "price_max": float(max_price),
        "price_min": float(min_price),
        "total_price_change": float(total_change),
        "daily_price_velocity": float(daily_change),
        "early_price_change": float(early_change),
        "late_price_change": float(late_change),
        "max_1day_spike": float(max_1day_spike),
        "n_price_points": int(len(df)),
        "market_duration_days_actual": int(n_days),
        "had_price_reversal": bool(max_price > last_price * 1.15),  # went up then came back down
    }


def main():
    print("=== Phase 2: Fetch CLOB Price Series ===\n")

    df = pd.read_csv(INPUT_CSV)
    df["volume_total"] = pd.to_numeric(df["volume_total"], errors="coerce").fillna(0)
    df["end_date"] = pd.to_datetime(df["end_date"], utc=True, errors="coerce")
    df["start_date"] = pd.to_datetime(df["start_date"], utc=True, errors="coerce")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_MONTHS * 30)

    # Filter: recent markets in priority categories
    mask_recent = df["end_date"] >= cutoff_date
    mask_category = df["event_category"].isin(PRIORITY_CATEGORIES)
    mask_volume = df["volume_total"] >= MIN_VOLUME_FOR_PRIORITY

    df_priority = df[mask_recent & mask_category & mask_volume].copy()
    df_all_recent = df[mask_recent].copy()

    print(f"Total relevant markets: {len(df):,}")
    print(f"Recent (<{MAX_AGE_MONTHS}mo) + priority categories + >${MIN_VOLUME_FOR_PRIORITY/1e6:.1f}M vol: {len(df_priority):,}")
    print(f"Recent markets total: {len(df_all_recent):,}")
    print()

    # Work on priority first, then fill with all recent
    work_df = pd.concat([df_priority, df_all_recent]).drop_duplicates(subset=["id"])
    print(f"Markets to process: {len(work_df):,}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    success_count = 0
    skip_count = 0

    for i, row in enumerate(work_df.itertuples(), 1):
        market_id = row.id
        question = str(row.question)[:70]
        out_path = OUTPUT_DIR / f"{market_id}.parquet"

        # Skip already downloaded
        if out_path.exists():
            skip_count += 1
            if i % 50 == 0:
                print(f"  [{i}/{len(work_df)}] Skip (cached): {question[:50]}")
            continue

        # Get token IDs from Gamma API
        token_ids = fetch_token_ids(str(row.id))
        time.sleep(PAUSE_BETWEEN_REQUESTS)

        if not token_ids:
            results.append({
                "id": market_id,
                "has_series": False,
                "n_points": 0,
                "reason": "no_tokens",
            })
            if i % 50 == 0:
                print(f"  [{i}/{len(work_df)}] No tokens: {question[:50]}")
            continue

        # Fetch price history for YES token (first token)
        yes_token = token_ids[0]
        price_df = fetch_price_history(yes_token, fidelity=60)  # hourly
        time.sleep(PAUSE_BETWEEN_REQUESTS)

        if price_df.empty:
            results.append({
                "id": market_id,
                "has_series": False,
                "n_points": 0,
                "reason": "empty_history",
            })
            if i % 50 == 0:
                print(f"  [{i}/{len(work_df)}] Empty history: {question[:50]}")
            continue

        # Save price series
        price_df.to_parquet(out_path, index=False)
        success_count += 1

        # Compute metrics
        metrics = compute_volume_metrics(price_df)
        results.append({
            "id": market_id,
            "has_series": True,
            "n_points": len(price_df),
            **metrics,
        })

        if i % 10 == 0 or i <= 5:
            print(
                f"  [{i}/{len(work_df)}] OK ({len(price_df)} pts) | "
                f"price {metrics.get('price_first', 0):.2f}→{metrics.get('price_last', 0):.2f} | "
                f"{question[:45]}"
            )

    print(f"\n--- Done ---")
    print(f"Success: {success_count}")
    print(f"Skipped (cached): {skip_count}")
    print(f"Failed: {len(results) - success_count}")

    if results:
        results_df = pd.DataFrame(results)
        results_df.to_csv(INDEX_CSV, index=False)
        print(f"Index saved to {INDEX_CSV}")
        print(f"Markets with series: {results_df['has_series'].sum()}/{len(results_df)}")


if __name__ == "__main__":
    main()
