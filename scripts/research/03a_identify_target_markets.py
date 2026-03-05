"""
Identify top 60 markets for historical time series extraction from quant.parquet.

Outputs:
- data/historical/price_series_targets.csv  — target market list with quant IDs
"""
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Load source data
# ---------------------------------------------------------------------------
markets_csv = pd.read_csv("data/historical/relevant_markets.csv")
markets_pq  = pd.read_parquet("data/historical/markets.parquet")

print(f"relevant_markets.csv  : {len(markets_csv):,} rows")
print(f"markets.parquet       : {len(markets_pq):,} rows")
print()

# ---------------------------------------------------------------------------
# Join: CSV uses condition_id as 'id'; parquet has condition_id + numeric id
# We need markets_pq['id'] (numeric) as the quant.parquet market_id,
# and token1 as the YES-token asset_id.
# ---------------------------------------------------------------------------
markets_csv["end_date"] = pd.to_datetime(markets_csv["end_date"], utc=True, errors="coerce")

merged = markets_csv.merge(
    markets_pq[["condition_id", "id", "token1", "token2"]].rename(
        columns={"id": "numeric_id"}
    ),
    left_on="id",
    right_on="condition_id",
    how="inner",
)
print(f"After join (CSV ∩ parquet by condition_id): {len(merged):,}")

# ---------------------------------------------------------------------------
# Priority categories and filters
# ---------------------------------------------------------------------------
TARGET_CATS   = ["geopolitical", "macro", "us_politics", "energy", "defense", "ai"]
MIN_VOLUME    = 2_000_000   # $2M USD
DATE_START    = "2024-01-01"
DATE_END      = "2025-12-31"

filtered = merged[
    merged["event_category"].isin(TARGET_CATS) &
    (merged["volume_total"] >= MIN_VOLUME) &
    (merged["end_date"] >= DATE_START) &
    (merged["end_date"] <= DATE_END)
].copy()

print(f"After category/volume/date filters  : {len(filtered):,}")
print()

# ---------------------------------------------------------------------------
# Pick top 60 by volume, but ensure category diversity
# Strategy: top N per category, then fill to 60 with globally highest volume
# ---------------------------------------------------------------------------
PER_CAT_QUOTA = {"geopolitical": 12, "macro": 12, "us_politics": 20,
                 "defense": 4, "energy": 2, "ai": 2}

selected_ids = set()
selected_rows = []

for cat, quota in PER_CAT_QUOTA.items():
    cat_df = (
        filtered[filtered["event_category"] == cat]
        .sort_values("volume_total", ascending=False)
        .head(quota)
    )
    selected_rows.append(cat_df)
    selected_ids.update(cat_df["id"].tolist())
    print(f"  {cat:15s}: {len(cat_df)} selected (quota {quota})")

target_df = pd.concat(selected_rows).drop_duplicates("id")

# Fill to 60 with highest-volume remaining
remaining = filtered[~filtered["id"].isin(selected_ids)].sort_values(
    "volume_total", ascending=False
)
fill_needed = 60 - len(target_df)
if fill_needed > 0 and len(remaining) > 0:
    target_df = pd.concat([target_df, remaining.head(fill_needed)])
    print(f"\n  Filled {fill_needed} more from remaining pool")

target_df = target_df.sort_values("volume_total", ascending=False).reset_index(drop=True)
print(f"\nFinal target count : {len(target_df)}")
print()

# ---------------------------------------------------------------------------
# Output columns
# ---------------------------------------------------------------------------
out = target_df[[
    "id",           # condition_id (used in our price_series filenames)
    "numeric_id",   # quant.parquet market_id
    "token1",       # YES token asset_id in quant.parquet
    "token2",       # NO  token asset_id
    "question",
    "event_category",
    "matched_tickers",
    "volume_total",
    "start_date",
    "end_date",
    "yes_price_final",
    "resolved",
]].copy()

out["quant_market_id"] = out["numeric_id"].astype(str)

# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------
print("=== TOP 20 BY VOLUME ===")
for i, row in out.head(20).iterrows():
    print(
        f"  #{i+1:2d} ${row['volume_total']/1e6:6.1f}M "
        f"[{row['event_category']:12s}] "
        f"{str(row['end_date'])[:10]} "
        f"{row['question'][:75]}"
    )

print()
print("=== BY CATEGORY ===")
print(out["event_category"].value_counts())

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
Path("data/historical").mkdir(parents=True, exist_ok=True)
out.to_csv("data/historical/price_series_targets.csv", index=False)
print(f"\nSaved: data/historical/price_series_targets.csv  ({len(out)} rows)")
