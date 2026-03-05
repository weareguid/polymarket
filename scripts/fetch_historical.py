#!/usr/bin/env python3
"""
Historical market data fetcher.

Downloads ALL closed Polymarket markets via the Gamma API, paginating
until exhausted. Saves a single CSV with one row per market.

This gives us the baseline historical dataset to:
- Analyse patterns across resolved markets
- Cross-reference with future daily snapshots for delta analysis
- Understand how market volume/price evolve over their lifecycle

Usage:
    python scripts/fetch_historical.py                    # fetch everything
    python scripts/fetch_historical.py --since 2025-01-01  # from a date
    python scripts/fetch_historical.py --limit 2000       # quick sample
    python scripts/fetch_historical.py --no-filter        # include sports/noise

Runtime: ~5-15 min for 20k+ markets depending on connection.
Output:  data/historical/markets_historical_YYYYMMDD.csv
"""
import sys
import argparse
import csv
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch_historical")

GAMMA_API = "https://gamma-api.polymarket.com"
BATCH_SIZE = 500          # Max per request
RATE_LIMIT_DELAY = 0.25  # Seconds between requests

# ── Noise filter (mirrors trending_detector._NOISE_PATTERNS) ──────────────────
import re

_NOISE_PATTERNS = [
    r"\b(counter.?strike|cs2|csgo|league of legends|valorant|dota\b|overwatch|fortnite|rocket league)\b",
    r"\b(pgl [a-z]+|blast [a-z]+|iem [a-z]+|esl [a-z]+|bo3\b|bo5\b)\b",
    r"\b(vitality|aurora gaming|natus vincere|faze clan|g2 esports|team liquid|cloud9|fnatic|navi)\b",
    r"\bpost\b.{0,50}\d{2,4}.{0,30}\btweet",
    r"\btweet.{0,50}\d{2,4}",
    r"\b(tweets?|retweets?).{0,20}(times?|per (day|week)|between)\b",
    r"\b(jesus christ|son of god|rapture|second coming)\b",
    r"\balien[s]? (exist|confirmed|disclosure|contact)\b",
    r"\bufo (confirmed|disclosure|reveal)\b",
    r"\b(zombie|asteroid (hit|destroy|wipe out) earth)\b",
    r"\b(academy award|oscar (win|best)|emmy (award|win)|grammy (award|win)|golden globe (win|best)|bafta)\b",
    r"\b(nhl|nba|nfl|mlb|fifa|uefa|wnba)\b.{0,60}\bvs\.?\b",
    r"\b(semifinal|quarterfinal|playoff[s]?|round of \d+)\b.{0,30}\bvs\.?\b",
    r"\b(bachelor|bachelorette|survivor|big brother|american idol|the voice|dancing with)\b",
    # Daily crypto price bets ("above $X on [date]") — already resolved, no forward signal
    r"(above|below|reach) \$[\d,]+ (on|by) \w+ \d{1,2}(,| at)",
    r"up or down on \w+ \d{1,2}",
]

_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]


def is_noise(question: str) -> bool:
    q = question.lower()
    return any(r.search(q) for r in _NOISE_RE)


# ── API ───────────────────────────────────────────────────────────────────────

def fetch_batch(offset: int, session: requests.Session) -> list:
    params = {
        "closed":    "true",
        "limit":     BATCH_SIZE,
        "offset":    offset,
        "order":     "volume",
        "ascending": "false",
    }
    resp = session.get(f"{GAMMA_API}/markets", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("data", [])


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_outcome_prices(raw: dict) -> tuple[float, float]:
    """Return (yes_price, no_price) from raw market dict."""
    import json as _json
    outcomes = raw.get("outcomes", [])
    prices   = raw.get("outcomePrices", [])
    if isinstance(outcomes, str):
        try: outcomes = _json.loads(outcomes)
        except Exception: outcomes = []
    if isinstance(prices, str):
        try: prices = _json.loads(prices)
        except Exception: prices = []

    yes_price, no_price = 0.0, 0.0
    for outcome, price in zip(outcomes, prices):
        try:
            val = float(price) if price else 0.0
        except (ValueError, TypeError):
            val = 0.0
        if str(outcome).lower() in ("yes", "true", "1"):
            yes_price = val
        elif str(outcome).lower() in ("no", "false", "0"):
            no_price = val
    return yes_price, no_price


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since",     default=None,
                        help="Only include markets that closed after this date (YYYY-MM-DD)")
    parser.add_argument("--limit",     type=int, default=0,
                        help="Stop after N total markets (0 = unlimited)")
    parser.add_argument("--no-filter", action="store_true",
                        help="Don't apply noise filter (include sports, esports, etc.)")
    args = parser.parse_args()

    since_dt = None
    if args.since:
        since_dt = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
        log.info(f"Filtering: only markets closed after {args.since}")

    out_dir = Path(__file__).parent.parent / "data" / "historical"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    out_path = out_dir / f"markets_historical_{date_str}.csv"

    fieldnames = [
        "id", "question", "slug", "category",
        "yes_price_final", "no_price_final",
        "volume_total", "volume_24h",
        "liquidity",
        "start_date", "end_date", "closed_time",
        "created_at", "resolved",
    ]

    session = requests.Session()
    session.headers["User-Agent"] = "PolymarketHistoricalFetcher/1.0"

    total_fetched = 0
    total_written = 0
    total_noise   = 0
    offset = 0

    log.info(f"Starting historical fetch → {out_path}")

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        while True:
            try:
                batch = fetch_batch(offset, session)
            except requests.RequestException as e:
                log.error(f"Request failed at offset {offset}: {e}")
                log.info("Waiting 5s before retry…")
                time.sleep(5)
                continue

            if not batch:
                log.info(f"No more markets at offset {offset}. Done.")
                break

            total_fetched += len(batch)

            for raw in batch:
                question  = raw.get("question", "")
                closed_at = raw.get("closedTime") or raw.get("endDate") or ""

                # Date filter
                if since_dt and closed_at:
                    try:
                        dt = datetime.fromisoformat(
                            closed_at.replace("Z", "+00:00").replace(" ", "T")
                        )
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt < since_dt:
                            continue
                    except Exception:
                        pass

                # Noise filter
                if not args.no_filter and is_noise(question):
                    total_noise += 1
                    continue

                yes_price, no_price = parse_outcome_prices(raw)

                writer.writerow({
                    "id":              raw.get("conditionId") or raw.get("id", ""),
                    "question":        question[:250],
                    "slug":            raw.get("slug", ""),
                    "category":        raw.get("category", "unknown"),
                    "yes_price_final": round(yes_price, 4),
                    "no_price_final":  round(no_price, 4),
                    "volume_total":    raw.get("volume", 0) or 0,
                    "volume_24h":      raw.get("volume24hr", 0) or 0,
                    "liquidity":       raw.get("liquidity", 0) or 0,
                    "start_date":      raw.get("startDate", ""),
                    "end_date":        raw.get("endDate", ""),
                    "closed_time":     raw.get("closedTime", ""),
                    "created_at":      raw.get("createdAt", ""),
                    "resolved":        raw.get("closed", True),
                })
                total_written += 1

            log.info(
                f"  offset={offset:>6}  fetched={total_fetched:>6}  "
                f"written={total_written:>6}  noise_skipped={total_noise:>5}"
            )

            if args.limit and total_fetched >= args.limit:
                log.info(f"Reached --limit {args.limit}. Stopping.")
                break

            offset += BATCH_SIZE
            time.sleep(RATE_LIMIT_DELAY)

    log.info(f"\nDone.")
    log.info(f"  Total fetched from API : {total_fetched:,}")
    log.info(f"  Written to CSV         : {total_written:,}")
    log.info(f"  Noise skipped          : {total_noise:,}")
    log.info(f"  Output file            : {out_path}")


if __name__ == "__main__":
    main()
