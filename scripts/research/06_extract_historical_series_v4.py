"""
Extract daily probability time series from quant.parquet for new target markets v4.

Phase: Batch 4 — ~200 new markets not in batches 1, 2, or 3.

Strategy: Diverse across categories and years.
  - Categories: geopolitical, macro, us_politics, defense, energy, commodities, corporate, ai
  - Volume threshold: >= 100,000 USD (lower than v3 to get more variety)
  - End date window: 2022-06-01 → 2026-01-01
  - Prioritize underrepresented categories: energy, ai, corporate
  - Prioritize earlier years: 2022-2023 data

Outputs:
  - data/historical/price_series_historical/<condition_id>.parquet  (shared dir)
  - data/historical/price_series_targets_v4.csv                     (new targets)
  - data/historical/price_series_historical_index_v4.csv            (new index)
"""
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import fsspec
from pathlib import Path
import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
QUANT_URL  = "https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data/resolve/main/quant.parquet"
OUTPUT_DIR = Path("data/historical/price_series_historical")
TARGETS_V4 = "data/historical/price_series_targets_v4.csv"
INDEX_V4   = "data/historical/price_series_historical_index_v4.csv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATE_MIN = "2022-06-01"
DATE_MAX = "2026-01-01"

READ_COLUMNS = ["datetime", "condition_id", "price", "usd_amount", "asset_id", "maker_direction"]

# ---------------------------------------------------------------------------
# Step 1: Build target list
# ---------------------------------------------------------------------------
print("=" * 70)
print("STEP 1: Selecting new target markets")
print("=" * 70)

df = pd.read_csv("data/historical/relevant_markets.csv")
markets_meta = pd.read_parquet("data/historical/markets.parquet")
t1 = pd.read_csv("data/historical/price_series_targets.csv")
t2 = pd.read_csv("data/historical/price_series_targets_v2.csv")
t3 = pd.read_csv("data/historical/price_series_targets_v3.csv")

already_targeted = set(t1["id"].tolist() + t2["id"].tolist() + t3["id"].tolist())
print(f"Already targeted (batches 1+2+3): {len(already_targeted)} markets")

df["volume_total"] = pd.to_numeric(df["volume_total"], errors="coerce").fillna(0)
df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
df["year"] = df["end_date"].dt.year

CATEGORIES = ["geopolitical", "macro", "us_politics", "defense", "energy", "commodities", "corporate", "ai"]

mask = (
    ~df["id"].isin(already_targeted) &
    (df["volume_total"] >= 100_000) &
    (df["event_category"].isin(CATEGORIES)) &
    (df["end_date"] >= DATE_MIN) &
    (df["end_date"] <= DATE_MAX) &
    (df["id"].isin(markets_meta["condition_id"]))
)
candidates = df[mask].copy().sort_values("volume_total", ascending=False)
print(f"Total candidates: {len(candidates)}")
print()

# Diverse sampling:
# Prioritize: ai, corporate, energy (underrepresented in prev batches)
# Also prioritize 2022-2023 data
# Target allocations (sum ~200)
CATEGORY_CAPS = {
    "ai":           40,
    "corporate":    40,
    "geopolitical": 40,
    "macro":        30,
    "us_politics":  25,
    "commodities":  12,
    "defense":      12,
    "energy":        1,   # only 1 available
}

selected_parts = []
for cat, cap in CATEGORY_CAPS.items():
    subset = candidates[candidates["event_category"] == cat]
    if len(subset) == 0:
        print(f"  {cat:14s}: 0 candidates (skipped)")
        continue

    subset = subset.copy()
    subset["year_bucket"] = subset["year"].fillna(2025).astype(int)

    # Boost 2022-2023: give them proportionally more slots
    early = subset[subset["year_bucket"] <= 2023].nlargest(
        min(len(subset[subset["year_bucket"] <= 2023]), max(1, cap // 3)), "volume_total"
    )
    # Fill rest from overall top by volume
    rest_cap = cap - len(early)
    rest = subset[~subset["id"].isin(early["id"])].nlargest(rest_cap, "volume_total")

    per_cat = pd.concat([early, rest], ignore_index=True).drop_duplicates(subset=["id"]).head(cap)

    selected_parts.append(per_cat)
    early_count = (per_cat["year_bucket"] <= 2023).sum()
    print(
        f"  {cat:14s}: {len(per_cat):3d} markets selected (cap={cap})  "
        f"[early 2022-23: {early_count}]"
    )

new_targets = pd.concat(selected_parts, ignore_index=True).drop_duplicates(subset=["id"])
print(f"\nTotal selected: {len(new_targets)} markets")
print()
print("Year distribution:")
print(new_targets["year"].value_counts().sort_index().to_string())
print()
print("Category distribution:")
print(new_targets["event_category"].value_counts().to_string())
print()

# Merge token info from markets.parquet
token_info = markets_meta[["condition_id", "token1", "token2", "id"]].rename(
    columns={"condition_id": "condition_id_m", "id": "numeric_id"}
)
new_targets = new_targets.merge(
    token_info[["condition_id_m", "token1", "token2", "numeric_id"]],
    left_on="id", right_on="condition_id_m", how="left"
).drop(columns=["condition_id_m"])

# Save targets CSV
save_cols = ["id", "numeric_id", "token1", "token2", "question", "event_category",
             "matched_tickers", "volume_total", "start_date", "end_date", "yes_price_final", "resolved"]
new_targets[save_cols].to_csv(TARGETS_V4, index=False)
print(f"Targets saved to: {TARGETS_V4}")
print()
print("=== MARKETS TO EXTRACT (top 30 by volume) ===")
for _, r in new_targets.sort_values("volume_total", ascending=False).head(30).iterrows():
    print(f"  ${r['volume_total']/1e6:6.1f}M [{r['event_category']:12s}] {str(r['question'])[:70]}")
print(f"  ... and {max(0, len(new_targets)-30)} more")
print()

# ---------------------------------------------------------------------------
# Step 2: Open quant.parquet via HTTP
# ---------------------------------------------------------------------------
print("=" * 70)
print("STEP 2: Connecting to quant.parquet (HuggingFace)")
print("=" * 70)

target_cids = set(new_targets["id"].tolist())
yes_token   = dict(zip(new_targets["id"], new_targets["token1"].astype(str)))
cid_meta    = new_targets.set_index("id").to_dict("index")

fs = fsspec.filesystem("http")
fh = fs.open(QUANT_URL)
pf = pq.ParquetFile(fh)
n_rg = pf.metadata.num_row_groups
print(f"Row groups : {n_rg}")
print(f"Total rows : {pf.metadata.num_rows:,}")
print()

# ---------------------------------------------------------------------------
# Step 3: Identify relevant row groups by datetime stats
# ---------------------------------------------------------------------------
def rg_datetime_range(pf, i):
    rg = pf.metadata.row_group(i)
    for j in range(rg.num_columns):
        col = rg.column(j)
        if col.path_in_schema == "datetime":
            stats = col.statistics
            if stats and stats.min is not None:
                return str(stats.min), str(stats.max)
    return None, None

print("Scanning row group datetime ranges...")
relevant_rgs = []
for i in range(n_rg):
    rg_min, rg_max = rg_datetime_range(pf, i)
    if rg_min is None:
        relevant_rgs.append(i)
        continue
    if rg_max < DATE_MIN or rg_min > DATE_MAX:
        continue
    relevant_rgs.append(i)

print(f"Row groups in date window : {len(relevant_rgs)} / {n_rg}")
print()

# ---------------------------------------------------------------------------
# Step 4: Single-pass extraction
# ---------------------------------------------------------------------------
print("=" * 70)
print("STEP 3: Extracting data (single pass through relevant row groups)")
print("=" * 70)

accum = {cid: [] for cid in target_cids}
total_rows_read = 0
total_rows_kept = 0
t_start = time.time()

for idx, rg_i in enumerate(relevant_rgs):
    t0 = time.time()
    try:
        batch = pf.read_row_group(rg_i, columns=READ_COLUMNS)
    except Exception as e:
        print(f"  [RG{rg_i:3d}] ERROR reading: {e}")
        time.sleep(2)
        continue

    df_rg = batch.to_pandas()
    total_rows_read += len(df_rg)

    df_rg = df_rg[(df_rg["datetime"] >= DATE_MIN) & (df_rg["datetime"] <= DATE_MAX + " 23:59:59")]
    df_rg = df_rg[df_rg["condition_id"].isin(target_cids)]
    total_rows_kept += len(df_rg)

    if len(df_rg) > 0:
        for cid, grp in df_rg.groupby("condition_id"):
            accum[cid].append(grp)

    elapsed = time.time() - t0
    matched_markets = df_rg["condition_id"].nunique() if len(df_rg) > 0 else 0
    found_so_far = sum(1 for v in accum.values() if v)
    print(
        f"  RG{rg_i:3d} ({idx+1:3d}/{len(relevant_rgs)})  "
        f"rows={len(batch):>8,}  kept={len(df_rg):>7,}  "
        f"markets={matched_markets:3d}  found_total={found_so_far:3d}  t={elapsed:.1f}s"
    )

elapsed_total = time.time() - t_start
print(f"\nPass complete in {elapsed_total:.1f}s  ({elapsed_total/60:.1f} min)")
print(f"Total rows read : {total_rows_read:,}")
print(f"Total rows kept : {total_rows_kept:,}")
print()

# ---------------------------------------------------------------------------
# Step 5: Aggregate to daily VWAP series
# ---------------------------------------------------------------------------
def trades_to_daily(trades_df, yes_tok):
    if trades_df.empty:
        return pd.DataFrame()

    trades_df = trades_df.copy()
    trades_df["datetime"] = pd.to_datetime(trades_df["datetime"])

    yes_trades = trades_df[trades_df["asset_id"] == yes_tok]
    if len(yes_trades) == 0:
        yes_trades = trades_df

    yes_trades = yes_trades.copy()
    yes_trades["date"] = yes_trades["datetime"].dt.date

    def vwap_row(x):
        total_usd = x["usd_amount"].sum()
        if total_usd > 0:
            vwap = np.average(x["price"], weights=x["usd_amount"])
        else:
            vwap = x["price"].mean()
        return pd.Series({
            "price_vwap"  : round(vwap, 6),
            "volume_usd"  : round(total_usd, 2),
            "n_trades"    : len(x),
            "price_open"  : x.sort_values("datetime")["price"].iloc[0],
            "price_close" : x.sort_values("datetime")["price"].iloc[-1],
            "price_high"  : x["price"].max(),
            "price_low"   : x["price"].min(),
        })

    daily = yes_trades.groupby("date").apply(vwap_row).reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    return daily.sort_values("date").reset_index(drop=True)


print("=" * 70)
print("STEP 4: Building daily VWAP series per market")
print("=" * 70)

results_index = []
for cid in sorted(target_cids):
    chunks = accum[cid]
    meta   = cid_meta[cid]
    q      = str(meta["question"])[:80]
    cat    = meta["event_category"]

    if not chunks:
        print(f"  [NO DATA ] {cat:12s} | {q[:60]}")
        results_index.append({
            "condition_id"   : cid,
            "question"       : q,
            "event_category" : cat,
            "has_data"       : False,
            "n_trades"       : 0,
            "n_days"         : 0,
        })
        continue

    all_trades = pd.concat(chunks, ignore_index=True)
    n_trades   = len(all_trades)
    daily      = trades_to_daily(all_trades, yes_token[cid])

    if daily.empty:
        print(f"  [EMPTY   ] {cat:12s} | {n_trades:,} trades but no daily series | {q[:50]}")
        results_index.append({
            "condition_id"   : cid,
            "question"       : q,
            "event_category" : cat,
            "has_data"       : False,
            "n_trades"       : n_trades,
            "n_days"         : 0,
        })
        continue

    out_path = OUTPUT_DIR / f"{cid}.parquet"
    daily.to_parquet(out_path, index=False)

    vol_m = daily["volume_usd"].sum() / 1e6
    print(
        f"  [OK {len(daily):4d}d] {cat:12s} | "
        f"{n_trades:7,} trades | ${vol_m:5.1f}M vol | {q[:55]}"
    )

    results_index.append({
        "condition_id"    : cid,
        "question"        : q,
        "event_category"  : cat,
        "matched_tickers" : meta.get("matched_tickers", ""),
        "has_data"        : True,
        "n_trades"        : n_trades,
        "n_days"          : len(daily),
        "date_start"      : str(daily["date"].min().date()),
        "date_end"        : str(daily["date"].max().date()),
        "price_start"     : round(daily["price_vwap"].iloc[0], 4),
        "price_end"       : round(daily["price_vwap"].iloc[-1], 4),
        "total_volume_usd": round(daily["volume_usd"].sum(), 2),
    })

# ---------------------------------------------------------------------------
# Step 6: Save index + print summary
# ---------------------------------------------------------------------------
idx_df = pd.DataFrame(results_index)
idx_df.to_csv(INDEX_V4, index=False)

n_ok  = idx_df["has_data"].sum()
n_all = len(list(OUTPUT_DIR.glob("*.parquet")))

print()
print("=" * 70)
print(f"DONE: {n_ok}/{len(idx_df)} new markets extracted with data")
print(f"Index saved : {INDEX_V4}")
print(f"Series dir  : {OUTPUT_DIR}/")
print(f"TOTAL markets in directory: {n_all}")
print()
print("Breakdown by category (this batch):")
cat_summary = idx_df[idx_df["has_data"]].groupby("event_category").agg(
    count=("condition_id", "count"),
    total_vol_M=("total_volume_usd", lambda x: round(x.sum()/1e6, 1)),
    avg_days=("n_days", "mean"),
).round(1)
print(cat_summary.to_string())
print()

if idx_df["has_data"].any():
    print("Year distribution (by market end_date):")
    meta_year = new_targets[["id", "year"]].rename(columns={"id": "condition_id"})
    idx_year = idx_df[idx_df["has_data"]].merge(meta_year, on="condition_id", how="left")
    print(idx_year["year"].value_counts().sort_index().to_string())
    print()

print("Top 5 markets by trade count:")
top5 = idx_df[idx_df["has_data"]].sort_values("n_trades", ascending=False).head(5)
for _, r in top5.iterrows():
    print(f"  {r['n_trades']:>8,} trades | ${r['total_volume_usd']/1e6:5.1f}M | {r['question'][:65]}")
print()
print(f"Total trades processed: {idx_df['n_trades'].sum():,}")
print("=" * 70)
