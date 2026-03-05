"""
Phase 1: Filter 411k historical markets to financially relevant subset.

Criteria for "financially relevant":
- Category signals: geopolitics, macro, elections, commodities, regulation, corporate
- Keyword matching against known financial topics
- Minimum volume threshold (signal quality)
- Exclude: sports, entertainment, celebrities, celebrity gossip

Output: data/historical/relevant_markets.csv
"""

import pandas as pd
import re
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INPUT_CSV = "data/historical/markets_historical_20260220.csv"
OUTPUT_CSV = "data/historical/relevant_markets.csv"
MIN_VOLUME = 50_000  # Only markets with meaningful volume

# Knowledge base: keywords that map to financial relevance + which tickers
# Format: keyword → {tickers, direction_hint, category}
FINANCIAL_KEYWORD_MAP = {
    # Geopolitical
    "iran": {"tickers": ["XLE", "USO", "LMT", "NOC", "GLD"], "category": "geopolitical"},
    "russia": {"tickers": ["XLE", "LMT", "NOC", "GLD", "URNM"], "category": "geopolitical"},
    "ukraine": {"tickers": ["XLE", "LMT", "NOC", "GLD", "URNM"], "category": "geopolitical"},
    "china": {"tickers": ["FXI", "BABA", "JD", "TSM", "EWT", "KWEB"], "category": "geopolitical"},
    "taiwan": {"tickers": ["TSM", "EWT", "SOXX", "SMH"], "category": "geopolitical"},
    "north korea": {"tickers": ["ITA", "LMT", "EWY"], "category": "geopolitical"},
    "israel": {"tickers": ["XLE", "USO", "GLD", "ITA"], "category": "geopolitical"},
    "gaza": {"tickers": ["XLE", "GLD", "ITA"], "category": "geopolitical"},
    "middle east": {"tickers": ["XLE", "USO", "GLD", "ITA"], "category": "geopolitical"},
    "nato": {"tickers": ["ITA", "LMT", "NOC", "RTX"], "category": "geopolitical"},
    "missile": {"tickers": ["ITA", "LMT", "NOC", "RTX"], "category": "geopolitical"},
    "war": {"tickers": ["ITA", "GLD", "XLE"], "category": "geopolitical"},
    "nuclear": {"tickers": ["URNM", "CCJ", "GLD", "NLR"], "category": "geopolitical"},
    "ceasefire": {"tickers": ["ITA", "XLE", "GLD"], "category": "geopolitical"},
    "sanctions": {"tickers": ["XLE", "GLD", "FXI"], "category": "geopolitical"},

    # US Politics / Macro
    "trump": {"tickers": ["DJT", "IWM", "XLE", "BTC-USD", "GLD"], "category": "us_politics"},
    "harris": {"tickers": ["TSLA", "RIVN", "XLE", "IWM"], "category": "us_politics"},
    "biden": {"tickers": ["XLE", "TLT", "IWM"], "category": "us_politics"},
    "election": {"tickers": ["IWM", "VIX", "GLD"], "category": "us_politics"},
    "president": {"tickers": ["IWM", "VIX", "GLD"], "category": "us_politics"},
    "republican": {"tickers": ["XLE", "IWM", "DJT"], "category": "us_politics"},
    "democrat": {"tickers": ["ICLN", "TAN", "XLP"], "category": "us_politics"},
    "congress": {"tickers": ["TLT", "IWM", "GLD"], "category": "us_politics"},
    "senate": {"tickers": ["TLT", "IWM", "GLD"], "category": "us_politics"},
    "impeach": {"tickers": ["VIX", "GLD", "TLT"], "category": "us_politics"},
    "debt ceiling": {"tickers": ["TLT", "GLD", "VIX"], "category": "macro"},
    "government shutdown": {"tickers": ["TLT", "GLD", "VIX"], "category": "macro"},
    "tariff": {"tickers": ["FXI", "EWZ", "IWM", "XLI"], "category": "trade"},
    "trade war": {"tickers": ["FXI", "EWZ", "XLI", "AAPL"], "category": "trade"},
    "inflation": {"tickers": ["TLT", "GLD", "XLE", "TIPS"], "category": "macro"},
    "recession": {"tickers": ["TLT", "GLD", "XLV", "SPY"], "category": "macro"},
    "gdp": {"tickers": ["SPY", "IWM", "TLT"], "category": "macro"},

    # Federal Reserve / Interest Rates
    "fed ": {"tickers": ["TLT", "XLF", "SPY"], "category": "macro"},
    "federal reserve": {"tickers": ["TLT", "XLF", "SPY"], "category": "macro"},
    "interest rate": {"tickers": ["TLT", "XLF", "SPY"], "category": "macro"},
    "rate cut": {"tickers": ["TLT", "XLF", "IWM"], "category": "macro"},
    "rate hike": {"tickers": ["TLT", "XLF", "SPY"], "category": "macro"},
    "basis points": {"tickers": ["TLT", "XLF", "SPY"], "category": "macro"},
    "bps": {"tickers": ["TLT", "XLF"], "category": "macro"},
    "powell": {"tickers": ["TLT", "XLF", "SPY"], "category": "macro"},
    "fomc": {"tickers": ["TLT", "XLF", "SPY"], "category": "macro"},
    "quantitative": {"tickers": ["TLT", "GLD", "BTC-USD"], "category": "macro"},

    # Crypto
    "bitcoin": {"tickers": ["BTC-USD", "MSTR", "COIN", "GBTC"], "category": "crypto"},
    "btc": {"tickers": ["BTC-USD", "MSTR", "COIN", "GBTC"], "category": "crypto"},
    "ethereum": {"tickers": ["ETH-USD", "COIN", "MARA", "RIOT"], "category": "crypto"},
    "eth": {"tickers": ["ETH-USD", "COIN"], "category": "crypto"},
    "solana": {"tickers": ["SOL-USD", "COIN"], "category": "crypto"},
    "crypto": {"tickers": ["BTC-USD", "COIN", "MSTR"], "category": "crypto"},
    "coinbase": {"tickers": ["COIN"], "category": "crypto"},
    "sec crypto": {"tickers": ["COIN", "BTC-USD"], "category": "crypto"},
    "etf bitcoin": {"tickers": ["IBIT", "GBTC", "FBTC", "BTC-USD"], "category": "crypto"},
    "spot etf": {"tickers": ["IBIT", "GBTC", "BTC-USD"], "category": "crypto"},

    # Energy / Oil
    "oil": {"tickers": ["XLE", "USO", "COP", "XOM"], "category": "energy"},
    "opec": {"tickers": ["XLE", "USO", "COP", "XOM"], "category": "energy"},
    "crude": {"tickers": ["XLE", "USO", "COP"], "category": "energy"},
    "natural gas": {"tickers": ["UNG", "XLE", "EQT"], "category": "energy"},
    "lng": {"tickers": ["LNG", "XLE"], "category": "energy"},
    "renewable": {"tickers": ["ICLN", "TAN", "ENPH"], "category": "energy"},
    "solar": {"tickers": ["TAN", "ENPH", "FSLR"], "category": "energy"},
    "nuclear energy": {"tickers": ["URNM", "CCJ", "NLR"], "category": "energy"},

    # Defense
    "defense": {"tickers": ["ITA", "LMT", "NOC", "RTX", "GD"], "category": "defense"},
    "military": {"tickers": ["ITA", "LMT", "NOC", "RTX"], "category": "defense"},
    "pentagon": {"tickers": ["ITA", "LMT", "NOC"], "category": "defense"},
    "weapons": {"tickers": ["ITA", "LMT", "NOC", "RTX"], "category": "defense"},
    "drone": {"tickers": ["ITA", "AXON", "RTX"], "category": "defense"},
    "lockheed": {"tickers": ["LMT"], "category": "defense"},
    "boeing": {"tickers": ["BA"], "category": "corporate"},
    "raytheon": {"tickers": ["RTX"], "category": "corporate"},

    # Corporate / Specific Companies
    "apple": {"tickers": ["AAPL"], "category": "corporate"},
    "elon musk": {"tickers": ["TSLA", "DOGE-USD"], "category": "corporate"},
    "tesla": {"tickers": ["TSLA"], "category": "corporate"},
    "twitter": {"tickers": ["TSLA"], "category": "corporate"},
    "nvidia": {"tickers": ["NVDA"], "category": "corporate"},
    "openai": {"tickers": ["MSFT", "NVDA"], "category": "ai"},
    "gpt": {"tickers": ["MSFT", "NVDA", "GOOGL"], "category": "ai"},
    "artificial intelligence": {"tickers": ["NVDA", "MSFT", "GOOGL", "META"], "category": "ai"},
    "ai ": {"tickers": ["NVDA", "MSFT", "GOOGL"], "category": "ai"},
    "sam altman": {"tickers": ["MSFT", "NVDA"], "category": "ai"},
    "amazon": {"tickers": ["AMZN"], "category": "corporate"},
    "google": {"tickers": ["GOOGL", "GOOG"], "category": "corporate"},
    "microsoft": {"tickers": ["MSFT"], "category": "corporate"},
    "meta": {"tickers": ["META"], "category": "corporate"},
    "spacex": {"tickers": ["TSLA"], "category": "corporate"},
    "antitrust": {"tickers": ["GOOGL", "META", "AAPL", "AMZN"], "category": "regulation"},
    "merger": {"tickers": ["SPY"], "category": "corporate"},
    "acquisition": {"tickers": ["SPY"], "category": "corporate"},
    "ipo": {"tickers": ["SPY", "IWM"], "category": "corporate"},
    "bankrupt": {"tickers": ["SPY"], "category": "corporate"},

    # Commodities / Precious Metals
    "gold": {"tickers": ["GLD", "GDX", "GOLD"], "category": "commodities"},
    "silver": {"tickers": ["SLV", "PSLV"], "category": "commodities"},
    "copper": {"tickers": ["COPX", "FCX"], "category": "commodities"},
    "wheat": {"tickers": ["WEAT", "ADM"], "category": "commodities"},
    "corn": {"tickers": ["CORN", "ADM"], "category": "commodities"},
    "commodity": {"tickers": ["DJP", "GSG"], "category": "commodities"},

    # International Politics
    "europe": {"tickers": ["VGK", "EWG", "EWQ", "FEZ"], "category": "international"},
    "germany": {"tickers": ["EWG"], "category": "international"},
    "france": {"tickers": ["EWQ"], "category": "international"},
    "japan": {"tickers": ["EWJ", "DXJ"], "category": "international"},
    "india": {"tickers": ["INDA", "EPI"], "category": "international"},
    "brazil": {"tickers": ["EWZ", "BRL=X"], "category": "international"},
    "mexico": {"tickers": ["EWW", "MXN=X"], "category": "international"},
    "saudi": {"tickers": ["KSA", "XLE"], "category": "geopolitical"},
    "venezuela": {"tickers": ["XLE", "USO"], "category": "geopolitical"},
    "latin america": {"tickers": ["ILF", "EWZ"], "category": "international"},

    # Regulation
    "regulation": {"tickers": ["XLF", "COIN", "AAPL"], "category": "regulation"},
    "sec ": {"tickers": ["COIN", "XLF"], "category": "regulation"},
    "lawsuit": {"tickers": ["SPY"], "category": "regulation"},
    "fine": {"tickers": ["XLF", "SPY"], "category": "regulation"},

    # Macro Events
    "pandemic": {"tickers": ["XLV", "MRNA", "PFE"], "category": "macro"},
    "covid": {"tickers": ["XLV", "MRNA", "PFE", "LUV", "CCL"], "category": "macro"},
    "vaccine": {"tickers": ["MRNA", "PFE", "BNTX"], "category": "macro"},
    "unemployment": {"tickers": ["SPY", "IWM", "TLT"], "category": "macro"},
    "jobs": {"tickers": ["SPY", "IWM"], "category": "macro"},
    "cpi": {"tickers": ["TLT", "GLD", "TIPS"], "category": "macro"},
    "dollar": {"tickers": ["UUP", "FXE", "GLD"], "category": "macro"},
    "yen": {"tickers": ["FXY", "EWJ"], "category": "macro"},
    "euro": {"tickers": ["FXE", "VGK"], "category": "macro"},
}

# Negative keywords - if these are the MAIN topic, exclude
EXCLUDE_KEYWORDS = [
    "nfl", "nba", "mlb", "nhl", "fifa", "soccer", "football", "basketball",
    "baseball", "tennis", "golf", "rugby", "cricket", "olympics", "esports",
    "dota", "counter-strike", "fortnite", "chess", "poker", "boxing",
    "mma", "ufc", "wrestling", "superbowl", "super bowl", "world cup",
    "league of legends", "valorant", "overwatch",
    "grammy", "oscar", "emmy", "golden globe", "academy award",
    "celebrity", "actor", "actress", "singer", "rapper", "kardashian",
    "taylor swift", "beyonce", "kim k", "kanye",
    "reality tv", "bachelor", "survivor",
    "game of thrones", "netflix show", "disney+",
    "sports bet", "series winner", "match winner", "set winner",
    "kills", "assists", "draft pick",
]

SPORTS_CATEGORIES = {
    "Sports", "NBA Playoffs", "Chess", "Poker", "Art", "Pop-Culture", "NFTs"
}


def classify_market(question: str, category: str, volume: float) -> tuple[bool, list[str], str]:
    """
    Returns (is_relevant, matched_tickers, event_category)
    """
    q_lower = question.lower()

    # Exclude sports categories
    if category in SPORTS_CATEGORIES:
        return False, [], ""

    # Exclude by negative keywords
    for kw in EXCLUDE_KEYWORDS:
        if kw in q_lower:
            return False, [], ""

    # Match financial keywords
    matched_tickers = []
    matched_categories = []

    for kw, info in FINANCIAL_KEYWORD_MAP.items():
        # Use word-boundary-aware matching
        if re.search(r'\b' + re.escape(kw.strip()) + r'\b', q_lower):
            matched_tickers.extend(info["tickers"])
            matched_categories.append(info["category"])

    if matched_tickers:
        # Deduplicate tickers
        matched_tickers = list(dict.fromkeys(matched_tickers))
        event_cat = matched_categories[0] if matched_categories else "unknown"
        return True, matched_tickers[:6], event_cat

    return False, [], ""


def main():
    print("=== Phase 1: Filter Financially Relevant Markets ===\n")
    print(f"Loading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    print(f"Total markets: {len(df):,}")
    print(f"Columns: {list(df.columns)}\n")

    # Ensure numeric volume
    df["volume_total"] = pd.to_numeric(df["volume_total"], errors="coerce").fillna(0)
    df["volume_24h"] = pd.to_numeric(df["volume_24h"], errors="coerce").fillna(0)

    # Parse dates
    df["start_date"] = pd.to_datetime(df["start_date"], utc=True, errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], utc=True, errors="coerce")
    df["closed_time"] = pd.to_datetime(df["closed_time"], utc=True, errors="coerce")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")

    # Market duration in days
    df["market_duration_days"] = (
        (df["end_date"] - df["start_date"]).dt.total_seconds() / 86400
    ).clip(lower=1)

    # Daily average volume proxy
    df["avg_daily_vol"] = df["volume_total"] / df["market_duration_days"]

    print(f"Volume filter (>= ${MIN_VOLUME:,}): ", end="")
    df_vol = df[df["volume_total"] >= MIN_VOLUME]
    print(f"{len(df_vol):,} markets pass")

    # Apply relevance classification
    print("Classifying markets...")
    results = df_vol.apply(
        lambda row: classify_market(
            str(row.get("question", "")),
            str(row.get("category", "")),
            row["volume_total"],
        ),
        axis=1,
    )

    df_vol = df_vol.copy()
    df_vol["is_relevant"] = results.apply(lambda x: x[0])
    df_vol["matched_tickers"] = results.apply(lambda x: json.dumps(x[1]))
    df_vol["event_category"] = results.apply(lambda x: x[2])

    df_relevant = df_vol[df_vol["is_relevant"]].copy()
    print(f"\nFinancially relevant markets: {len(df_relevant):,}")

    # Stats
    print("\n--- Category breakdown ---")
    print(df_relevant["event_category"].value_counts().to_string())

    print("\n--- Volume stats for relevant markets ---")
    print(df_relevant["volume_total"].describe().apply(lambda x: f"${x:,.0f}"))

    print("\n--- Date range ---")
    print(f"From: {df_relevant['start_date'].min()}")
    print(f"To:   {df_relevant['end_date'].max()}")

    print("\n--- Top 20 by volume ---")
    top20 = df_relevant.nlargest(20, "volume_total")[
        ["question", "volume_total", "event_category", "matched_tickers", "start_date", "end_date", "yes_price_final"]
    ]
    for _, row in top20.iterrows():
        print(f"  ${row['volume_total']:>12,.0f}  [{row['event_category'][:12]}]  {str(row['question'])[:70]}")

    # Save output
    Path(OUTPUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    df_relevant.to_csv(OUTPUT_CSV, index=False)
    print(f"\nSaved to {OUTPUT_CSV}")

    # Also save a summary JSON
    summary = {
        "total_markets": len(df),
        "volume_filtered": len(df_vol),
        "relevant_markets": len(df_relevant),
        "categories": df_relevant["event_category"].value_counts().to_dict(),
        "volume_threshold": MIN_VOLUME,
        "date_from": str(df_relevant["start_date"].min()),
        "date_to": str(df_relevant["end_date"].max()),
    }
    with open("outputs/research/phase1_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary saved to outputs/research/phase1_summary.json")


if __name__ == "__main__":
    main()
