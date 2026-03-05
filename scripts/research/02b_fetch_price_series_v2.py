"""
Phase 2B: Fetch CLOB price history for financially-relevant markets.

Key fixes vs original script:
- Uses markets.parquet for direct token IDs (no Gamma API roundtrip)
- CLOB history dict format: {'t': unix_seconds, 'p': price}
- Only fetches active/recent markets (CLOB retains ~60 days of history)
- Filters: priority categories + >$500K volume + ended in last 60 days

Output:
- data/historical/price_series/{condition_id}.parquet
- data/historical/price_series_index.csv
"""

import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Config
REL_CSV = "data/historical/relevant_markets.csv"
MKT_PARQUET = "data/historical/markets.parquet"
OUTPUT_DIR = Path("data/historical/price_series")
INDEX_CSV = "data/historical/price_series_index.csv"

CLOB_BASE = "https://clob.polymarket.com"
PAUSE = 0.3
MAX_AGE_DAYS = 60
MIN_VOLUME = 500_000
PRIORITY_CATEGORIES = {"geopolitical", "macro", "us_politics", "corporate", "ai", "energy", "defense"}


def fetch_price_history(token_id: str, fidelity: int = 60) -> pd.DataFrame:
    """Fetch CLOB price history. Returns DataFrame with [timestamp, price]."""
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
        # Format: list of dicts {'t': unix_seconds, 'p': price}
        df = pd.DataFrame(history)
        df = df.rename(columns={"t": "timestamp", "p": "price"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        df["price"] = df["price"].astype(float)
        return df.sort_values("timestamp").reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()


def main():
    print("=== Phase 2B: Fetch CLOB Price Series (v2, token-direct) ===\n")

    # Load relevant markets
    rel = pd.read_csv(REL_CSV)
    rel["volume_total"] = pd.to_numeric(rel["volume_total"], errors="coerce").fillna(0)
    rel["end_date"] = pd.to_datetime(rel["end_date"], utc=True, errors="coerce")

    # Load markets for token IDs
    mkt = pd.read_parquet(MKT_PARQUET)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_AGE_DAYS)

    # Filter to priority + volume + recent
    work = rel[
        (rel["event_category"].isin(PRIORITY_CATEGORIES)) &
        (rel["volume_total"] >= MIN_VOLUME) &
        (rel["end_date"] >= cutoff)
    ].copy()

    # Merge with token data
    tokens_df = mkt[["condition_id", "token1", "token2"]].drop_duplicates("condition_id")
    work = work.merge(tokens_df, left_on="id", right_on="condition_id", how="left")
    work = work[work["token1"].notna()].copy()

    # Sort by volume descending
    work = work.sort_values("volume_total", ascending=False).reset_index(drop=True)

    print(f"Priority markets with tokens: {len(work)}")
    print(f"Category breakdown:")
    print(work["event_category"].value_counts().to_string())
    print(f"\nVolume range: ${work['volume_total'].min():,.0f} – ${work['volume_total'].max():,.0f}")
    print(f"Estimated time: ~{len(work) * PAUSE / 60:.0f} min (single API call per market)")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, row in enumerate(work.itertuples(), 1):
        market_id = row.id  # condition_id
        question = str(row.question)[:70]
        token1 = str(row.token1)
        out_path = OUTPUT_DIR / f"{market_id}.parquet"

        # Skip cached
        if out_path.exists():
            skip_count += 1
            try:
                ps = pd.read_parquet(out_path)
                results.append({
                    "id": market_id,
                    "has_series": True,
                    "n_points": len(ps),
                    "price_first": float(ps["price"].iloc[0]) if len(ps) else None,
                    "price_last": float(ps["price"].iloc[-1]) if len(ps) else None,
                    "date_first": str(ps["timestamp"].iloc[0].date()) if len(ps) else None,
                    "date_last": str(ps["timestamp"].iloc[-1].date()) if len(ps) else None,
                    "max_1h_spike": float(ps["price"].diff().abs().max()) if len(ps) > 1 else 0,
                })
            except:
                results.append({"id": market_id, "has_series": True, "n_points": 0})
            continue

        # Fetch from CLOB
        price_df = fetch_price_history(token1, fidelity=60)
        time.sleep(PAUSE)

        if price_df.empty:
            results.append({"id": market_id, "has_series": False, "n_points": 0, "reason": "empty"})
            fail_count += 1
            if i % 20 == 0 or i <= 5:
                print(f"  [{i}/{len(work)}] Empty: {question[:55]}")
            continue

        # Save
        price_df.to_parquet(out_path, index=False)
        success_count += 1

        max_spike = float(price_df["price"].diff().abs().max()) if len(price_df) > 1 else 0
        results.append({
            "id": market_id,
            "has_series": True,
            "n_points": len(price_df),
            "price_first": float(price_df["price"].iloc[0]),
            "price_last": float(price_df["price"].iloc[-1]),
            "date_first": str(price_df["timestamp"].iloc[0].date()),
            "date_last": str(price_df["timestamp"].iloc[-1].date()),
            "max_1h_spike": max_spike,
        })

        if i % 10 == 0 or i <= 5:
            print(
                f"  [{i}/{len(work)}] OK ({len(price_df)} pts) | "
                f"price {price_df['price'].iloc[0]:.3f}→{price_df['price'].iloc[-1]:.3f} | "
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
        has = idx_df[idx_df["has_series"] == True]
        print(f"Markets with series: {len(has)}/{len(idx_df)}")
        if len(has) > 0:
            print(f"Avg price points: {has['n_points'].mean():.0f}")
            print(f"Markets with >100 pts: {(has['n_points'] > 100).sum()}")
            print(f"\nSample (top by points):")
            print(has.sort_values("n_points", ascending=False).head(5).to_string())


if __name__ == "__main__":
    main()
