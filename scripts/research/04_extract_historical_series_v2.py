"""
Extract daily probability time series from quant.parquet for new target markets v2.

New categories: energy/commodities, Ukraine/Russia, Iran/Israel, macro (Fed rates)
Date window expanded to 2024-01-01 → 2026-12-31

Outputs:
- data/historical/price_series_historical/<condition_id>.parquet  (shared with v1)
- data/historical/price_series_targets_v2_index.csv               (new index)
- data/historical/price_series_targets_v2.csv already created by exploration step
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
QUANT_URL   = "https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data/resolve/main/quant.parquet"
TARGETS_CSV = "data/historical/price_series_targets_v2.csv"
OUTPUT_DIR  = Path("data/historical/price_series_historical")
INDEX_CSV   = "data/historical/price_series_historical_index_v2.csv"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATE_MIN = "2024-01-01"
DATE_MAX = "2026-12-31"

READ_COLUMNS = ["datetime", "condition_id", "price", "usd_amount", "asset_id", "maker_direction"]

# ---------------------------------------------------------------------------
# Load targets
# ---------------------------------------------------------------------------
targets = pd.read_csv(TARGETS_CSV)
print(f"Target markets loaded : {len(targets)}")

target_cids = set(targets["id"].tolist())
cid_meta    = targets.set_index("id").to_dict("index")
yes_token   = dict(zip(targets["id"], targets["token1"].astype(str)))

print(f"  Unique condition_ids : {len(target_cids)}")
print(f"  Date window          : {DATE_MIN} -> {DATE_MAX}")
print()
print("Category breakdown:")
print(targets["event_category"].value_counts().to_string())
print()

# Show what we're about to download
print("=== MARKETS TO EXTRACT ===")
for _, r in targets.sort_values("volume_total", ascending=False).iterrows():
    print(f"  ${r['volume_total']/1e6:6.1f}M [{r['event_category']:12s}] {r['question'][:75]}")
print()

# ---------------------------------------------------------------------------
# Open quant.parquet via HTTP
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

print(f"  Row groups in date window : {len(relevant_rgs)} / {n_rg}")
print()

# ---------------------------------------------------------------------------
# Single-pass extraction
# ---------------------------------------------------------------------------
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

    df = df[(df["datetime"] >= DATE_MIN) & (df["datetime"] <= DATE_MAX + " 23:59:59")]
    df = df[df["condition_id"].isin(target_cids)]
    total_rows_kept += len(df)

    if len(df) > 0:
        for cid, grp in df.groupby("condition_id"):
            accum[cid].append(grp)

    elapsed = time.time() - t0
    matched_markets = df["condition_id"].nunique() if len(df) > 0 else 0
    print(
        f"  RG{rg_i:3d} ({idx+1:3d}/{len(relevant_rgs)})  "
        f"rows={len(batch):>8,}  kept={len(df):>7,}  "
        f"markets={matched_markets:3d}  t={elapsed:.1f}s"
    )

elapsed_total = time.time() - t_start
print(f"\nPass complete in {elapsed_total:.1f}s")
print(f"Total rows read : {total_rows_read:,}")
print(f"Total rows kept : {total_rows_kept:,}")
print()

# ---------------------------------------------------------------------------
# Aggregate to daily VWAP series
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
        print(f"  [EMPTY   ] {cat:12s} | {n_trades:,} trades but no daily series | {q[:55]}")
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
# Save index + print summary
# ---------------------------------------------------------------------------
idx_df = pd.DataFrame(results_index)
idx_df.to_csv(INDEX_CSV, index=False)

n_ok = idx_df["has_data"].sum()
print(f"\n{'='*65}")
print(f"DONE: {n_ok}/{len(idx_df)} markets extracted with data")
print(f"Index saved : {INDEX_CSV}")
print(f"Series dir  : {OUTPUT_DIR}/")

print("\n=== SAMPLE DATA (2 interesting markets) ===")
interesting = idx_df[idx_df["has_data"]].sort_values("n_trades", ascending=False).head(2)
for _, row in interesting.iterrows():
    cid = row["condition_id"]
    series = pd.read_parquet(OUTPUT_DIR / f"{cid}.parquet")
    print(f"\n{row['question'][:75]}")
    print(f"  Trades: {row['n_trades']:,}  Days: {row['n_days']}  "
          f"Period: {row['date_start']} -> {row['date_end']}")
    print("  First 3 rows:")
    print(series.head(3).to_string(index=False))
    print("  Last 3 rows:")
    print(series.tail(3).to_string(index=False))

print(f"\n=== TOTAL TRADES ACROSS ALL NEW MARKETS ===")
print(f"  {idx_df['n_trades'].sum():,} trades processed")
print(f"  {n_ok} parquet files written to {OUTPUT_DIR}/")
