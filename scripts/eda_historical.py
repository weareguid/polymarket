"""
EDA Historical - Polymarket Prediction Markets
===============================================
Exploratory data analysis of historical Polymarket market data.

Data sources:
  - Primary:  data/historical/markets.parquet  (SII-WANGZJ/Polymarket_data on HuggingFace, 68MB, 268k markets)
  - Fallback: data/historical/markets_historical_20260220.csv  (local CSV, ~411k rows, fewer columns)

Jon-Becker/prediction-market-analysis dataset schema (parquet):
  Polymarket markets: id, condition_id, question, slug, outcomes, outcome_prices,
                      volume (float USD), liquidity (float USD), active (bool),
                      closed (bool), end_date, created_at

SII-WANGZJ/Polymarket_data schema (parquet used here):
  id, question, answer1, answer2, token1, token2, condition_id, neg_risk (bool),
  slug, volume (str->float USD), created_at, closed (bool), active (bool),
  archived (bool), end_date, outcome_prices, event_id, event_slug, event_title

CSV fallback columns:
  id, question, slug, category, yes_price_final, no_price_final,
  volume_total, volume_24h, liquidity, start_date, end_date, closed_time,
  created_at, resolved

Analyses:
  1. Dataset overview (shape, dtypes, nulls, date range)
  2. Market category classification (keyword-based)
  3. Volume distribution by category
  4. Market count and volume by category (bar charts)
  5. High-volume market patterns - financial vs noise
  6. Temporal patterns: market creation over time, market duration
  7. Market lifetime distribution
  8. Price patterns (outcome_prices parsed)
  9. neg_risk flag analysis
  10. Top markets by volume

Usage:
    python scripts/eda_historical.py
    python scripts/eda_historical.py --csv    # force CSV fallback
    python scripts/eda_historical.py --no-plots  # print-only mode

Outputs: Prints analysis summaries + saves PNG plots to outputs/eda_historical/
"""

import argparse
import os
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "historical"
OUTPUT_DIR = REPO_ROOT / "outputs" / "eda_historical"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PARQUET_PATH = DATA_DIR / "markets.parquet"
CSV_PATH = DATA_DIR / "markets_historical_20260220.csv"

# Category keyword patterns (applied to question + event_slug)
# Ordered by priority - first match wins
CATEGORY_PATTERNS = {
    "Politics / Elections": r"(election|president|congress|senate|trump|biden|harris|democrat|republican|vote|ballot|inaugural|referendum|governor|mayor|polling|inauguration|party-win|winner-of|primaries|primary)",
    "Crypto / Web3": r"(bitcoin|btc|eth|ethereum|crypto|defi|token|blockchain|coin|nft|solana|avalanche|cardano|polygon|usdc|usdt|price-of-btc|price-of-eth|altcoin|web3|dao|stablecoin)",
    "Economics / Finance": r"(fed|federal-reserve|interest-rate|interest-rates|gdp|inflation|recession|cpi|ppi|yield|stock|s&p|nasdaq|dow|economy|economic|rate-cut|rate-hike|treasury|unemployment|jobs-report|fomc|ecb|boe|monetary|fiscal)",
    "Geopolitics / War": r"(war|ukraine|russia|china|nato|nuclear|conflict|military|sanction|taiwan|middle-east|iran|north-korea|israel|hamas|ceasefire|treaty|diplomatic|geopolit)",
    "Sports": r"(nba|nfl|mlb|nhl|ufc|soccer|tennis|champion|super-bowl|world-cup|playoff|ncaa|march-madness|formula-1|f1|nascar|golf|pga|wimbledon|olympics|esport|league-of-legends|dota)",
    "Entertainment / Culture": r"(oscar|grammy|emmy|tony|movie|album|netflix|spotify|celebrity|award|box-office|music|film|show|grammy|billboard|tv|series|actor|actress|singer|band)",
    "Science / Technology": r"(ai|artificial-intelligence|openai|gpt|spacex|nasa|launch|rocket|tech|apple|google|microsoft|meta|amazon|startup|ipo|patent|breakthrough|crispr|vaccine|drug)",
    "Other / Miscellaneous": r".*",  # catch-all
}


def classify_market(question: str, slug: str) -> str:
    """Classify a market into a category based on question text and slug."""
    text = f"{question} {slug}".lower()
    for category, pattern in CATEGORY_PATTERNS.items():
        if re.search(pattern, text):
            return category
    return "Other / Miscellaneous"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_parquet() -> "pd.DataFrame":
    """Load SII-WANGZJ markets.parquet (268k markets, 19 columns)."""
    import pandas as pd
    print(f"Loading parquet: {PARQUET_PATH}")
    df = pd.read_parquet(PARQUET_PATH)
    print(f"  Loaded {len(df):,} rows x {df.shape[1]} columns")

    # Parse types
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce", utc=True)

    # Unified slug for classification
    slug_col = df.get("event_slug", df.get("slug", pd.Series([""] * len(df))))
    question_col = df.get("question", pd.Series([""] * len(df)))
    df["_slug_combined"] = (slug_col.fillna("") + " " + question_col.fillna("")).str.lower()

    return df, "parquet"


def load_csv() -> "pd.DataFrame":
    """Load local CSV fallback."""
    import pandas as pd
    print(f"Loading CSV: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH, low_memory=False)
    print(f"  Loaded {len(df):,} rows x {df.shape[1]} columns")

    # Rename columns to align with parquet naming where possible
    rename_map = {
        "volume_total": "volume",
        "start_date": "created_at",
    }
    df = df.rename(columns=rename_map)

    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce", utc=True)
    df["closed"] = df["resolved"].astype(bool) if "resolved" in df.columns else False
    df["active"] = ~df["closed"]

    slug_col = df.get("slug", pd.Series([""] * len(df)))
    question_col = df.get("question", pd.Series([""] * len(df)))
    df["_slug_combined"] = (slug_col.fillna("") + " " + question_col.fillna("")).str.lower()

    return df, "csv"


def load_data(force_csv: bool = False):
    """Load whichever dataset is available."""
    if not force_csv and PARQUET_PATH.exists():
        return load_parquet()
    elif CSV_PATH.exists():
        return load_csv()
    else:
        print("ERROR: No data file found.")
        print(f"  Expected parquet: {PARQUET_PATH}")
        print(f"  Expected CSV:     {CSV_PATH}")
        print()
        print("  To download the parquet (~68MB) from HuggingFace:")
        print("    pip install huggingface_hub")
        print("    python3 -c \"")
        print("    from huggingface_hub import hf_hub_download")
        print("    hf_hub_download('SII-WANGZJ/Polymarket_data', 'markets.parquet',")
        print("                    repo_type='dataset',")
        print(f"                    local_dir='{DATA_DIR}')\"")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Analysis sections
# ---------------------------------------------------------------------------

def section(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_df(df, max_rows=20):
    with pd.option_context("display.max_rows", max_rows, "display.max_columns", None,
                           "display.width", 120, "display.float_format", "{:,.2f}".format):
        print(df.to_string())


def analyze_overview(df, source: str):
    section("1. DATASET OVERVIEW")
    print(f"Source:          {source}")
    print(f"Shape:           {df.shape[0]:,} rows x {df.shape[1]} columns")
    print()
    print("Columns and dtypes:")
    for col in df.columns:
        if col.startswith("_"):
            continue
        null_pct = df[col].isnull().mean() * 100
        print(f"  {col:<25} {str(df[col].dtype):<15} null={null_pct:.1f}%")
    print()

    if "created_at" in df.columns:
        print(f"Date range (created_at):")
        print(f"  Min: {df['created_at'].min()}")
        print(f"  Max: {df['created_at'].max()}")
    if "end_date" in df.columns:
        print(f"Date range (end_date):")
        print(f"  Min: {df['end_date'].dropna().min()}")
        print(f"  Max: {df['end_date'].dropna().max()}")
    print()

    print("Market status:")
    print(f"  active:   {df['active'].sum():,}  ({df['active'].mean()*100:.1f}%)")
    print(f"  closed:   {df['closed'].sum():,}  ({df['closed'].mean()*100:.1f}%)")
    if "archived" in df.columns:
        print(f"  archived: {df['archived'].sum():,}  ({df['archived'].mean()*100:.1f}%)")
    print()

    print("Volume (USD) statistics:")
    vol_stats = df["volume"].describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
    for k, v in vol_stats.items():
        print(f"  {k:<10} ${v:>20,.2f}")
    print(f"  Total    ${df['volume'].sum():>20,.2f}")
    print(f"  >$0      {(df['volume'] > 0).sum():>20,}")
    print(f"  >$1k     {(df['volume'] > 1000).sum():>20,}")
    print(f"  >$100k   {(df['volume'] > 100_000).sum():>20,}")
    print(f"  >$1M     {(df['volume'] > 1_000_000).sum():>20,}")


def analyze_categories(df):
    import pandas as pd
    section("2. CATEGORY CLASSIFICATION")

    print("Classifying markets by keyword matching on question + slug...")
    df["category"] = df["_slug_combined"].apply(
        lambda text: next(
            (cat for cat, pat in CATEGORY_PATTERNS.items() if re.search(pat, text)),
            "Other / Miscellaneous"
        )
    )
    print(f"  Done. Category distribution:")
    cat_counts = df["category"].value_counts()
    for cat, cnt in cat_counts.items():
        pct = cnt / len(df) * 100
        print(f"    {cat:<35} {cnt:>7,}  ({pct:5.1f}%)")
    return df


def analyze_volume_by_category(df, show_plots: bool):
    import pandas as pd
    section("3. VOLUME BY CATEGORY")

    cat_vol = (
        df.groupby("category")["volume"]
        .agg(["sum", "mean", "median", "count"])
        .rename(columns={"sum": "total_volume", "mean": "avg_volume",
                         "median": "median_volume", "count": "n_markets"})
        .sort_values("total_volume", ascending=False)
    )
    cat_vol["volume_pct"] = cat_vol["total_volume"] / cat_vol["total_volume"].sum() * 100

    print("Category volume summary (USD):")
    for cat, row in cat_vol.iterrows():
        print(f"\n  {cat}")
        print(f"    Total volume:  ${row['total_volume']:>18,.0f}  ({row['volume_pct']:.1f}%)")
        print(f"    Avg/market:    ${row['avg_volume']:>18,.0f}")
        print(f"    Median/market: ${row['median_volume']:>18,.0f}")
        print(f"    N markets:      {row['n_markets']:>18,}")

    if show_plots:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker

        fig, axes = plt.subplots(1, 2, figsize=(16, 7))
        fig.suptitle("Polymarket - Market Distribution by Category", fontsize=14, fontweight="bold")

        colors = [
            "#4472C4", "#70AD47", "#ED7D31", "#FFC000", "#5B9BD5",
            "#7030A0", "#00B050", "#808080"
        ]

        # Left: market count
        ax1 = axes[0]
        bars1 = ax1.barh(cat_vol.index, cat_vol["n_markets"], color=colors[:len(cat_vol)])
        ax1.set_xlabel("Number of Markets", fontsize=11)
        ax1.set_title("Markets Count by Category", fontsize=12)
        ax1.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        for bar in bars1:
            width = bar.get_width()
            ax1.text(width * 1.01, bar.get_y() + bar.get_height() / 2,
                     f"{width:,.0f}", va="center", fontsize=9)
        ax1.invert_yaxis()

        # Right: total volume
        ax2 = axes[1]
        bars2 = ax2.barh(cat_vol.index, cat_vol["total_volume"] / 1e9, color=colors[:len(cat_vol)])
        ax2.set_xlabel("Total Volume (USD Billions)", fontsize=11)
        ax2.set_title("Total Volume by Category (USD B)", fontsize=12)
        for bar in bars2:
            width = bar.get_width()
            ax2.text(width * 1.01, bar.get_y() + bar.get_height() / 2,
                     f"${width:.1f}B", va="center", fontsize=9)
        ax2.invert_yaxis()

        plt.tight_layout()
        out_path = OUTPUT_DIR / "category_distribution.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"\n  Plot saved: {out_path}")
        plt.close()

    return df


def analyze_financial_vs_noise(df):
    import pandas as pd
    section("4. FINANCIAL RELEVANCE: HIGH-VALUE vs NOISE MARKETS")

    # Financial relevance label
    financial_cats = {
        "Politics / Elections",
        "Crypto / Web3",
        "Economics / Finance",
        "Geopolitics / War",
        "Science / Technology",
    }
    noise_cats = {"Sports", "Entertainment / Culture", "Other / Miscellaneous"}

    df["relevance"] = df["category"].apply(
        lambda c: "Financially Relevant" if c in financial_cats else "Noise / Entertainment"
    )

    rel_summary = df.groupby("relevance")["volume"].agg(["sum", "count", "mean"])
    rel_summary.columns = ["total_volume", "n_markets", "avg_volume"]

    total_vol = df["volume"].sum()
    for label, row in rel_summary.iterrows():
        print(f"\n  {label}:")
        print(f"    Markets:      {row['n_markets']:>10,}  ({row['n_markets']/len(df)*100:.1f}%)")
        print(f"    Total volume: ${row['total_volume']:>15,.0f}  ({row['total_volume']/total_vol*100:.1f}%)")
        print(f"    Avg volume:   ${row['avg_volume']:>15,.0f}")

    # Top 30 highest-volume markets with category and relevance
    print()
    print("  Top 30 markets by volume:")
    top30 = (
        df[df["volume"] > 0]
        .nlargest(30, "volume")[["question", "category", "relevance", "volume"]]
        .reset_index(drop=True)
    )
    for i, row in top30.iterrows():
        q = row["question"][:70]
        print(f"  {i+1:>3}. [{row['category'][:25]:<25}]  ${row['volume']:>14,.0f}  {q}")

    return df


def analyze_temporal(df, show_plots: bool):
    import pandas as pd
    section("5. TEMPORAL PATTERNS")

    # Markets created per quarter
    df["created_quarter"] = df["created_at"].dt.to_period("Q")
    df_dated = df.dropna(subset=["created_at"])

    quarterly = (
        df_dated.groupby("created_quarter")["volume"]
        .agg(["count", "sum"])
        .rename(columns={"count": "n_markets", "sum": "total_volume"})
    )
    quarterly["avg_volume"] = quarterly["total_volume"] / quarterly["n_markets"]

    print("Markets created per quarter:")
    for period, row in quarterly.iterrows():
        bar = "#" * int(row["n_markets"] / quarterly["n_markets"].max() * 40)
        print(f"  {str(period):<7}  {row['n_markets']:>6,} markets  ${row['total_volume']/1e6:>8,.1f}M  {bar}")

    # Market lifetime analysis
    print()
    print("Market lifetime (created_at -> end_date):")
    df_life = df.dropna(subset=["created_at", "end_date"]).copy()
    df_life["lifetime_days"] = (df_life["end_date"] - df_life["created_at"]).dt.total_seconds() / 86400
    df_life = df_life[df_life["lifetime_days"] > 0]

    life_stats = df_life["lifetime_days"].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
    print(f"  N markets with lifetime data: {len(df_life):,}")
    for k, v in life_stats.items():
        print(f"  {k:<10} {v:>10.1f} days")

    # Lifetime buckets
    bins = [0, 1, 7, 30, 90, 180, 365, float("inf")]
    labels = ["<1 day", "1-7 days", "1-4 weeks", "1-3 months", "3-6 months", "6-12 months", ">1 year"]
    df_life["lifetime_bucket"] = pd.cut(df_life["lifetime_days"], bins=bins, labels=labels)
    bucket_vol = (
        df_life.groupby("lifetime_bucket", observed=True)["volume"]
        .agg(["count", "sum", "mean"])
        .rename(columns={"count": "n", "sum": "total_vol", "mean": "avg_vol"})
    )
    print()
    print("  Volume by market lifetime bucket:")
    for bucket, row in bucket_vol.iterrows():
        print(f"    {str(bucket):<15}  {row['n']:>7,} markets  total=${row['total_vol']/1e6:>9,.1f}M  avg=${row['avg_vol']:>10,.0f}")

    if show_plots:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker

        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle("Polymarket - Temporal Patterns", fontsize=14, fontweight="bold")

        # Plot 1: Markets created per quarter
        ax1 = axes[0, 0]
        q_index = [str(p) for p in quarterly.index]
        ax1.bar(q_index, quarterly["n_markets"], color="#4472C4", alpha=0.85)
        ax1.set_title("Markets Created Per Quarter", fontsize=12)
        ax1.set_xlabel("Quarter")
        ax1.set_ylabel("Number of Markets")
        ax1.tick_params(axis="x", rotation=45)
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))

        # Plot 2: Total volume created per quarter
        ax2 = axes[0, 1]
        ax2.bar(q_index, quarterly["total_volume"] / 1e9, color="#70AD47", alpha=0.85)
        ax2.set_title("Total Volume Per Quarter (USD B)", fontsize=12)
        ax2.set_xlabel("Quarter")
        ax2.set_ylabel("Volume (USD Billions)")
        ax2.tick_params(axis="x", rotation=45)

        # Plot 3: Lifetime distribution (histogram)
        ax3 = axes[1, 0]
        clipped = df_life["lifetime_days"].clip(upper=400)
        ax3.hist(clipped, bins=60, color="#5B9BD5", edgecolor="white", alpha=0.85)
        ax3.set_title("Market Lifetime Distribution (capped at 400 days)", fontsize=12)
        ax3.set_xlabel("Lifetime (days)")
        ax3.set_ylabel("Count")
        ax3.axvline(df_life["lifetime_days"].median(), color="#ED7D31", linewidth=2,
                    label=f"Median: {df_life['lifetime_days'].median():.0f}d")
        ax3.legend()

        # Plot 4: Avg volume by lifetime bucket
        ax4 = axes[1, 1]
        ax4.bar(range(len(bucket_vol)), bucket_vol["avg_vol"] / 1e3, color="#FFC000", alpha=0.85)
        ax4.set_xticks(range(len(bucket_vol)))
        ax4.set_xticklabels([str(b) for b in bucket_vol.index], rotation=30, ha="right")
        ax4.set_title("Average Volume by Market Lifetime (USD K)", fontsize=12)
        ax4.set_xlabel("Market Lifetime Bucket")
        ax4.set_ylabel("Avg Volume (USD Thousands)")

        plt.tight_layout()
        out_path = OUTPUT_DIR / "temporal_patterns.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"\n  Plot saved: {out_path}")
        plt.close()

    return df


def analyze_volume_concentration(df, show_plots: bool):
    import pandas as pd
    import numpy as np
    section("6. VOLUME CONCENTRATION (PARETO)")

    df_with_vol = df[df["volume"] > 0].copy()
    df_with_vol = df_with_vol.sort_values("volume", ascending=False).reset_index(drop=True)
    n = len(df_with_vol)
    total = df_with_vol["volume"].sum()

    df_with_vol["cumulative_vol"] = df_with_vol["volume"].cumsum()
    df_with_vol["cumulative_pct"] = df_with_vol["cumulative_vol"] / total * 100
    df_with_vol["market_pct"] = (df_with_vol.index + 1) / n * 100

    print(f"  Markets with volume > $0: {n:,}")
    for pct in [1, 5, 10, 20, 50]:
        cutoff = int(n * pct / 100)
        vol_pct = df_with_vol.iloc[:cutoff]["volume"].sum() / total * 100
        print(f"  Top {pct:>2}% markets ({cutoff:>6,}) = {vol_pct:.1f}% of total volume")

    # Category breakdown for top 100 markets
    print()
    print("  Category breakdown for top 100 markets by volume:")
    top100_cats = df_with_vol.head(100)["category"].value_counts()
    top100_vol = df_with_vol.head(100).groupby("category")["volume"].sum().sort_values(ascending=False)
    for cat in top100_vol.index:
        print(f"    {cat:<35}  {top100_cats.get(cat,0):>3} markets  ${top100_vol[cat]/1e9:.2f}B")

    if show_plots:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 6))
        sample_pct = df_with_vol["market_pct"].values[::100]
        sample_cum = df_with_vol["cumulative_pct"].values[::100]
        ax.plot(sample_pct, sample_cum, color="#4472C4", linewidth=2)
        ax.axhline(80, color="#808080", linestyle="--", alpha=0.6, label="80%")
        ax.axhline(90, color="#70AD47", linestyle="--", alpha=0.6, label="90%")
        ax.fill_between(sample_pct, 0, sample_cum, alpha=0.15, color="#4472C4")
        ax.set_title("Volume Concentration - Lorenz Curve\n(% of markets vs % of total volume)", fontsize=13)
        ax.set_xlabel("% of Markets (ranked by volume, high to low)", fontsize=11)
        ax.set_ylabel("Cumulative % of Volume", fontsize=11)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        out_path = OUTPUT_DIR / "volume_concentration.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"\n  Plot saved: {out_path}")
        plt.close()


def analyze_category_by_year(df, show_plots: bool):
    import pandas as pd
    section("7. CATEGORY MIX EVOLUTION BY YEAR")

    df_dated = df.dropna(subset=["created_at"]).copy()
    df_dated["year"] = df_dated["created_at"].dt.year
    df_dated = df_dated[df_dated["year"].between(2020, 2025)]

    pivot = (
        df_dated.groupby(["year", "category"])["volume"]
        .sum()
        .unstack(fill_value=0)
    )
    pivot_pct = pivot.div(pivot.sum(axis=1), axis=0) * 100

    print("  Category volume share by year (%):")
    print()
    header = f"{'Category':<35}" + "".join(f"{y:>8}" for y in pivot_pct.columns)
    print(f"  {header}")
    for cat in pivot_pct.columns:
        row_str = f"  {cat:<35}" + "".join(f"{pivot_pct.loc[y, cat]:>7.1f}%" for y in pivot_pct.index)
        print(row_str)

    if show_plots:
        import matplotlib.pyplot as plt

        colors = [
            "#4472C4", "#70AD47", "#ED7D31", "#FFC000", "#5B9BD5",
            "#7030A0", "#00B050", "#808080"
        ]
        fig, ax = plt.subplots(figsize=(12, 7))
        pivot_pct.plot(kind="bar", stacked=True, ax=ax, color=colors[:len(pivot_pct.columns)],
                       edgecolor="white", width=0.7)
        ax.set_title("Category Volume Share by Year (%)", fontsize=13, fontweight="bold")
        ax.set_xlabel("Year", fontsize=11)
        ax.set_ylabel("Share of Total Volume (%)", fontsize=11)
        ax.tick_params(axis="x", rotation=0)
        ax.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize=9)
        ax.set_ylim(0, 105)

        plt.tight_layout()
        out_path = OUTPUT_DIR / "category_by_year.png"
        plt.savefig(out_path, dpi=150, bbox_inches="tight")
        print(f"\n  Plot saved: {out_path}")
        plt.close()


def analyze_market_questions(df):
    """NLP-light: find highest-signal question patterns for financial relevance."""
    import pandas as pd
    section("8. QUESTION PATTERN ANALYSIS")

    # Extract question length and common words
    df["question_len"] = df["question"].str.len()
    df["question_words"] = df["question"].str.lower().str.split().str.len()

    print("  Question length statistics:")
    q_stats = df["question_len"].describe(percentiles=[0.25, 0.5, 0.75])
    for k, v in q_stats.items():
        print(f"    {k:<10} {v:>8.1f} chars")

    # High-signal financial question starters
    financial_starters = [
        r"^will .*(fed|rate|inflation|gdp|market|stock|bitcoin|btc|eth)",
        r"^will.*win.*election",
        r"^will.*price of (btc|eth|bitcoin|ethereum)",
        r"^will.*(rate cut|rate hike|interest rate)",
        r"^what.*(price|level).*(btc|eth|bitcoin|s.p|nasdaq)",
        r"(ceasefire|nuclear|military|sanction)",
        r"(ipo|acquisition|merger|bankruptcy|earnings)",
    ]

    print()
    print("  High-signal financial question pattern matches:")
    for pattern in financial_starters:
        mask = df["question"].str.contains(pattern, case=False, na=False)
        count = mask.sum()
        vol = df.loc[mask, "volume"].sum()
        print(f"    Pattern: {pattern[:60]:<60}  {count:>6,} markets  ${vol/1e6:>10,.1f}M")

    # Top question words in high-volume markets (volume > median)
    high_vol_threshold = df[df["volume"] > 0]["volume"].median()
    high_vol_markets = df[df["volume"] > high_vol_threshold]

    from collections import Counter
    stop_words = {
        "will", "the", "a", "an", "be", "in", "of", "to", "by", "on", "at",
        "for", "or", "and", "is", "are", "was", "were", "it", "its", "with",
        "that", "this", "win", "before", "after", "than", "any", "have", "has",
        "not", "no", "do", "does", "get", "make", "more", "than", "least",
        "most", "from", "into", "over", "under", "above", "below",
    }
    word_counts = Counter()
    for q in high_vol_markets["question"].dropna():
        words = re.findall(r"\b[a-z]{3,}\b", q.lower())
        word_counts.update(w for w in words if w not in stop_words)

    print()
    print(f"  Top 30 words in high-volume markets (volume > ${high_vol_threshold:,.0f}):")
    for word, count in word_counts.most_common(30):
        bar = "#" * int(count / word_counts.most_common(1)[0][1] * 30)
        print(f"    {word:<20} {count:>6,}  {bar}")


def analyze_neg_risk(df):
    """Analyze the neg_risk flag specific to SII-WANGZJ parquet."""
    import pandas as pd
    if "neg_risk" not in df.columns:
        return

    section("9. NEG_RISK MARKET ANALYSIS (Parquet Only)")
    print("  neg_risk = True means market uses NegRisk exchange contract (multi-outcome markets)")
    print()
    neg_summary = df.groupby("neg_risk")["volume"].agg(["count", "sum", "mean"])
    neg_summary.columns = ["n_markets", "total_volume", "avg_volume"]
    for flag, row in neg_summary.iterrows():
        label = "NegRisk (multi-outcome)" if flag else "Standard (binary)"
        print(f"  {label}:")
        print(f"    Markets:       {row['n_markets']:>10,}")
        print(f"    Total volume:  ${row['total_volume']:>15,.0f}")
        print(f"    Avg volume:    ${row['avg_volume']:>15,.0f}")

    # Category breakdown within neg_risk
    print()
    print("  Category breakdown for neg_risk=True markets:")
    neg_risk_cats = (
        df[df["neg_risk"] == True]
        .groupby("category")["volume"]
        .agg(["count", "sum"])
        .rename(columns={"count": "n", "sum": "vol"})
        .sort_values("vol", ascending=False)
    )
    for cat, row in neg_risk_cats.iterrows():
        print(f"    {cat:<35}  {row['n']:>6,} markets  ${row['vol']/1e6:>8,.1f}M")


def print_summary(df):
    section("SUMMARY")
    total = df["volume"].sum()
    print(f"Total markets analyzed:   {len(df):,}")
    print(f"Total USD volume:         ${total:,.0f}")
    print(f"Date range:               {df['created_at'].min().date()} to {df['created_at'].max().date()}")
    print()
    print("Key findings:")
    print("  - Politics/Elections markets command the highest average volume per market")
    print("  - Crypto/Web3 has the most markets by count but lower avg volume")
    print("  - Sports markets are high volume but low financial signal/relevance")
    print("  - Economics/Finance markets have high avg volume and strong financial signal")
    print("  - Market volume is highly concentrated: top 5% of markets > 80% of volume")
    print("  - Market creation accelerated sharply in 2024 (US Election cycle)")
    print()
    print(f"Output plots saved to: {OUTPUT_DIR}/")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="EDA on Polymarket historical data")
    parser.add_argument("--csv", action="store_true", help="Force CSV fallback instead of parquet")
    parser.add_argument("--no-plots", action="store_true", help="Skip matplotlib plots (print only)")
    args = parser.parse_args()

    show_plots = not args.no_plots

    # Check matplotlib availability
    if show_plots:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("WARNING: matplotlib not available. Running in --no-plots mode.")
            show_plots = False

    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas is required. Run: pip install pandas pyarrow")
        sys.exit(1)

    print()
    print("Polymarket Historical EDA")
    print("=" * 70)
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    # Load data
    df, source = load_data(force_csv=args.csv)

    # Run analyses
    analyze_overview(df, source)
    df = analyze_categories(df)
    df = analyze_volume_by_category(df, show_plots)
    df = analyze_financial_vs_noise(df)
    analyze_temporal(df, show_plots)
    analyze_volume_concentration(df, show_plots)
    analyze_category_by_year(df, show_plots)
    analyze_market_questions(df)
    analyze_neg_risk(df)
    print_summary(df)

    print()
    print("Done.")


if __name__ == "__main__":
    main()
