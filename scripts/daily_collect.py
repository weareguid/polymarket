#!/usr/bin/env python3
"""
Daily market snapshot collector.

Fetches the top 200 Polymarket markets and saves a timestamped CSV snapshot.
Run this daily (via launchd/cron) to accumulate historical data for delta
analysis, backtesting, and trend detection over time.

Usage:
    python scripts/daily_collect.py
    python scripts/daily_collect.py --limit 300
"""
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Allow running from project root or from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scraper import PolymarketClient
from src.utils import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("daily_collect")


def main():
    parser = argparse.ArgumentParser(description="Polymarket daily snapshot")
    parser.add_argument("--limit", type=int, default=200,
                        help="Number of markets to fetch (default: 200)")
    args = parser.parse_args()

    log.info(f"Starting daily snapshot (limit={args.limit})")

    client = PolymarketClient()

    # Fetch more markets than the default pipeline — we want breadth for
    # historical analysis, not just the top-100 by volume.
    markets = client.get_trending_markets(
        limit=args.limit,
        min_volume_24h=1_000,   # Lower threshold to capture emerging markets
        min_liquidity=500,
    )

    filepath = client.save_snapshot(markets)
    log.info(f"Saved {len(markets)} markets → {filepath}")

    # Quick summary to stdout (visible in launchd logs)
    volumes = sorted([m.volume_24h for m in markets], reverse=True)
    top_market = max(markets, key=lambda m: m.volume_24h)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] "
          f"Snapshot: {len(markets)} markets | "
          f"Top vol: ${volumes[0]:,.0f} | "
          f"Median vol: ${volumes[len(volumes)//2]:,.0f}")
    print(f"  Top market: {top_market.question[:80]}")


if __name__ == "__main__":
    main()
