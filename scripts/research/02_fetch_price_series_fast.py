"""
Phase 2: Fetch CLOB price history — FAST VERSION (priority markets only).

Filters:
- Priority categories only (geopolitical, macro, us_politics, corporate, ai, energy, defense)
- Volume >= $500K
- Ended in last 9 months
- Max 400 markets to keep runtime under 15 minutes

Output:
- data/historical/price_series/{market_id}.parquet
- data/historical/price_series_index.csv
"""

import json
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta

INPUT_CSV = "data/historical/relevant_markets.csv"
OUTPUT_DIR = Path("data/historical/price_series")
INDEX_CSV = "data/historical/price_series_index.csv"

MAX_AGE_MONTHS = 9
PAUSE = 0.25
CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"

PRIORITY_CATEGORIES = {"geopolitical", "macro", "us_politics", "corporate", "ai", "energy", "defense"}
MIN_VOLUME = 500_000
MAX_MARKETS = 400


def fetch_token_ids(condition_id: str) -> list:
    try:
        r = requests.get(f"{GAMMA_BASE}/markets", params={"condition_id": condition_id}, timeout=10)
        if r.ok and r.json():
            market = r.json()[0]
            tokens = market.get("clobTokenIds", "[]")
            if isinstance(tokens, str):
                tokens = json.loads(tokens)
            return tokens
    except:
        pass
    return []


def fetch_price_history(token_id: str, fidelity: int = 60) -> pd.DataFrame:
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
        df = pd.DataFrame(history, columns=["timestamp", "price"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df["price"] = df["price"].astype(float)
        return df.sort_values("timestamp")
    except:
        return pd.DataFrame()


def main():
    print("=== Phase 2: Fetch CLOB Price Series (FAST/PRIORITY) ===\n")

    df = pd.read_csv(INPUT_CSV)
    df["volume_total"] = pd.to_numeric(df["volume_total"], errors="coerce").fillna(0)
    df["end_date"] = pd.to_datetime(df["end_date"], utc=True, errors="coerce")

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_MONTHS * 30)

    work = df[
        (df["end_date"] >= cutoff) &
        (df["event_category"].isin(PRIORITY_CATEGORIES)) &
        (df["volume_total"] >= MIN_VOLUME)
    ].copy()

    # Sort by volume descending, take top N
    work = work.sort_values("volume_total", ascending=False).head(MAX_MARKETS)

    print(f"Markets to process: {len(work)}")
    print(f"Estimated time: ~{len(work)*0.5/60:.0f} min")
    print(f"Category breakdown:")
    print(work["event_category"].value_counts().to_string())
    print(f"\nVolume range: ${work['volume_total'].min():,.0f} - ${work['volume_total'].max():,.0f}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, row in enumerate(work.itertuples(), 1):
        market_id = row.id
        question = str(row.question)[:70]
        out_path = OUTPUT_DIR / f"{market_id}.parquet"

        if out_path.exists():
            skip_count += 1
            # Load cached and add to results
            try:
                ps = pd.read_parquet(out_path)
                results.append({"id": market_id, "has_series": True, "n_points": len(ps),
                                 "price_first": float(ps["price"].iloc[0]),
                                 "price_last": float(ps["price"].iloc[-1]),
                                 "max_1day_spike": float(ps["price"].diff().abs().max())})
            except:
                results.append({"id": market_id, "has_series": True, "n_points": 0})
            continue

        token_ids = fetch_token_ids(str(market_id))
        time.sleep(PAUSE)

        if not token_ids:
            results.append({"id": market_id, "has_series": False, "n_points": 0, "reason": "no_tokens"})
            fail_count += 1
            if i % 20 == 0:
                print(f"  [{i}/{len(work)}] No tokens: {question[:50]}")
            continue

        yes_token = token_ids[0]
        price_df = fetch_price_history(yes_token, fidelity=60)
        time.sleep(PAUSE)

        if price_df.empty:
            results.append({"id": market_id, "has_series": False, "n_points": 0, "reason": "empty_history"})
            fail_count += 1
            if i % 20 == 0:
                print(f"  [{i}/{len(work)}] Empty: {question[:50]}")
            continue

        price_df.to_parquet(out_path, index=False)
        success_count += 1

        daily_diff = price_df["price"].diff().abs()
        results.append({
            "id": market_id,
            "has_series": True,
            "n_points": len(price_df),
            "price_first": float(price_df["price"].iloc[0]),
            "price_last": float(price_df["price"].iloc[-1]),
            "max_1day_spike": float(daily_diff.max()),
        })

        if i % 10 == 0 or i <= 5:
            print(
                f"  [{i}/{len(work)}] OK ({len(price_df)} pts) | "
                f"price {price_df['price'].iloc[0]:.2f}→{price_df['price'].iloc[-1]:.2f} | "
                f"{question[:50]}"
            )

    print(f"\n--- Done ---")
    print(f"Success (new): {success_count}")
    print(f"Cached: {skip_count}")
    print(f"Failed: {fail_count}")

    if results:
        idx_df = pd.DataFrame(results)
        idx_df.to_csv(INDEX_CSV, index=False)
        print(f"\nIndex saved: {INDEX_CSV}")
        print(f"Markets with series: {idx_df['has_series'].sum()}/{len(idx_df)}")
        has = idx_df[idx_df["has_series"]]
        if len(has) > 0:
            print(f"Avg price points: {has['n_points'].mean():.0f}")
            print(f"Markets >100 pts: {(has['n_points'] > 100).sum()}")


if __name__ == "__main__":
    main()
