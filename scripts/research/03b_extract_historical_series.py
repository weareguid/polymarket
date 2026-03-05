"""
Extract daily probability time series from quant.parquet via HTTP streaming.

Strategy:
- quant.parquet is sorted by TIME (not market_id), so we cannot skip row groups
  by market_id. Instead we exploit the datetime stats to skip row groups outside
  our 2024–2025 window, then filter by the set of target condition_ids (which are
  present as a column directly in quant.parquet).
- We process all relevant row groups in ONE PASS, collecting data for all 60
  target markets simultaneously — far more efficient than 60 separate passes.
- Output: one parquet file per market with daily VWAP probability series.

Key schema facts (verified):
  - quant.parquet columns include: datetime, market_id (numeric str), condition_id,
    question, price, usd_amount, asset_id (token/YES-NO), maker_direction
  - Sorted by datetime ascending
  - 176 row groups, ~1M rows each, 170M rows total
"""
import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pyarrow as pa
import fsspec
from pathlib import Path
import time, json

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
QUANT_URL  = "https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data/resolve/main/quant.parquet"
TARGETS_CSV = "data/historical/price_series_targets.csv"
OUTPUT_DIR  = Path("data/historical/price_series_historical")
INDEX_CSV   = "data/historical/price_series_historical_index.csv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Date window for extraction (quant.parquet datetime is a string 'YYYY-MM-DD HH:MM:SS')
DATE_MIN = "2024-01-01"
DATE_MAX = "2025-12-31"

# Columns to read per row group (skip heavy cols to reduce bandwidth)
READ_COLUMNS = ["datetime", "condition_id", "price", "usd_amount", "asset_id", "maker_direction"]

# ---------------------------------------------------------------------------
# Load targets
# ---------------------------------------------------------------------------
targets = pd.read_csv(TARGETS_CSV)
print(f"Target markets loaded: {len(targets)}")

# Build lookup: condition_id -> row metadata
target_cids = set(targets["id"].tolist())          # condition_id set for fast filtering
cid_meta = targets.set_index("id").to_dict("index")

# Also: YES token per condition_id
yes_token = dict(zip(targets["id"], targets["token1"].astype(str)))

print(f"  Unique condition_ids : {len(target_cids)}")
print(f"  Date window          : {DATE_MIN} → {DATE_MAX}")
print()

# ---------------------------------------------------------------------------
# Open quant.parquet via HTTP (single connection, reused across all row groups)
# ---------------------------------------------------------------------------
print("Connecting to quant.parquet (HuggingFace)...")
fs = fsspec.filesystem("http")
fh = fs.open(QUANT_URL)
pf = pq.ParquetFile(fh)
n_rg = pf.metadata.num_row_groups
print(f"  Row groups : {n_rg}")
print(f"  Total rows : {pf.metadata.num_rows:,}")
print()

# ---------------------------------------------------------------------------
# Identify relevant row groups by datetime stats
# ---------------------------------------------------------------------------
def rg_datetime_range(pf, i):
    """Return (min_dt_str, max_dt_str) for row group i using statistics."""
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
        # No stats — must include
        relevant_rgs.append(i)
        continue
    # Keep if row group overlaps [DATE_MIN, DATE_MAX]
    if rg_max < DATE_MIN or rg_min > DATE_MAX:
        continue
    relevant_rgs.append(i)

print(f"  Row groups in date window : {len(relevant_rgs)} / {n_rg}")
print()

# ---------------------------------------------------------------------------
# Single-pass extraction: accumulate chunks per condition_id
# ---------------------------------------------------------------------------
# accum[cid] = list of DataFrames
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
        continue

    df = batch.to_pandas()
    total_rows_read += len(df)

    # Date filter (string comparison works for ISO format)
    df = df[(df["datetime"] >= DATE_MIN) & (df["datetime"] <= DATE_MAX + " 23:59:59")]

    # Filter to our target condition_ids
    df = df[df["condition_id"].isin(target_cids)]
    total_rows_kept += len(df)

    # Distribute to per-market accumulators
    if len(df) > 0:
        for cid, grp in df.groupby("condition_id"):
            accum[cid].append(grp)

    elapsed = time.time() - t0
    matched_markets = df["condition_id"].nunique() if len(df) > 0 else 0
    print(
        f"  RG{rg_i:3d} ({idx+1:3d}/{len(relevant_rgs)}) "
        f"rows={len(batch):>8,}  kept={len(df):>7,}  "
        f"markets={matched_markets:3d}  t={elapsed:.1f}s"
    )

elapsed_total = time.time() - t_start
print(f"\nPass complete in {elapsed_total:.1f}s")
print(f"Total rows read : {total_rows_read:,}")
print(f"Total rows kept : {total_rows_kept:,}")
print()

# ---------------------------------------------------------------------------
# Aggregate trades → daily VWAP series per market
# ---------------------------------------------------------------------------
def trades_to_daily(trades_df: pd.DataFrame, yes_tok: str) -> pd.DataFrame:
    """Convert raw trades to daily probability series using YES token VWAP."""
    if trades_df.empty:
        return pd.DataFrame()

    trades_df = trades_df.copy()
    trades_df["datetime"] = pd.to_datetime(trades_df["datetime"])

    # Prefer YES token trades; fall back to all trades if token unavailable
    yes_trades = trades_df[trades_df["asset_id"] == yes_tok]
    if len(yes_trades) == 0:
        yes_trades = trades_df  # fallback

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


results_index = []

print("Building daily series per market...")
for cid in sorted(target_cids):
    chunks = accum[cid]
    meta   = cid_meta[cid]
    q      = str(meta["question"])[:80]
    cat    = meta["event_category"]

    if not chunks:
        print(f"  [NO DATA ] {cat:12s} | {q[:60]}")
        results_index.append({
            "condition_id"   : cid,
            "quant_market_id": meta["quant_market_id"],
            "question"       : q,
            "event_category" : cat,
            "has_data"       : False,
            "n_trades"       : 0,
            "n_days"         : 0,
        })
        continue

    all_trades = pd.concat(chunks, ignore_index=True)
    n_trades   = len(all_trades)

    daily = trades_to_daily(all_trades, yes_token[cid])

    if daily.empty:
        print(f"  [EMPTY   ] {cat:12s} | {n_trades:,} trades but no daily series | {q[:55]}")
        results_index.append({
            "condition_id"   : cid,
            "quant_market_id": meta["quant_market_id"],
            "question"       : q,
            "event_category" : cat,
            "has_data"       : False,
            "n_trades"       : n_trades,
            "n_days"         : 0,
        })
        continue

    # Save per-market parquet
    out_path = OUTPUT_DIR / f"{cid}.parquet"
    daily.to_parquet(out_path, index=False)

    vol_m = daily["volume_usd"].sum() / 1e6
    print(
        f"  [OK {len(daily):4d}d] {cat:12s} | "
        f"{n_trades:7,} trades | ${vol_m:6.1f}M vol | {q[:55]}"
    )

    results_index.append({
        "condition_id"      : cid,
        "quant_market_id"   : meta["quant_market_id"],
        "question"          : q,
        "event_category"    : cat,
        "matched_tickers"   : meta.get("matched_tickers", ""),
        "has_data"          : True,
        "n_trades"          : n_trades,
        "n_days"            : len(daily),
        "date_start"        : str(daily["date"].min().date()),
        "date_end"          : str(daily["date"].max().date()),
        "price_start"       : round(daily["price_vwap"].iloc[0], 4),
        "price_end"         : round(daily["price_vwap"].iloc[-1], 4),
        "total_volume_usd"  : round(daily["volume_usd"].sum(), 2),
    })

# ---------------------------------------------------------------------------
# Save index
# ---------------------------------------------------------------------------
idx_df = pd.DataFrame(results_index)
idx_df.to_csv(INDEX_CSV, index=False)

n_ok = idx_df["has_data"].sum()
print(f"\n{'='*60}")
print(f"DONE: {n_ok}/{len(idx_df)} markets with data")
print(f"Index saved: {INDEX_CSV}")
print(f"Series saved in: {OUTPUT_DIR}/")
