#!/usr/bin/env python3
"""
FinSignal Collector — reads newsletters from Gmail, extracts stock signals,
cross-references with Polymarket, saves results to data/finsignal/.

Usage:
    python scripts/finsignal_collect.py              # Read last 7 days
    python scripts/finsignal_collect.py --days 14    # Read last 14 days
    python scripts/finsignal_collect.py --demo       # Use sample data (no Gmail needed)
    python scripts/finsignal_collect.py --demo --show-context  # With full context
"""
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.finsignal.gmail_reader import GmailReader
from src.finsignal.newsletter_parser import parse_email
from src.finsignal.polymarket_matcher import match_ticker_to_markets, classify_alignment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("finsignal")

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "finsignal"


# ── Demo emails for testing without Gmail ─────────────────────────────────────
# These mimic the subtle analyst language used in real financial newsletters.
# Real newsletters don't say "BUY AAPL" — they say "valuation looks compelling"
# or "Goldman initiates with overweight" or "consider trimming exposure".
_DEMO_EMAILS = [
    {
        "uid": "demo1",
        "sender": "Morning Brew <hello@morningbrew.com>",
        "subject": "NVDA hits record; TSLA faces headwinds; MSFT target raised",
        "date": datetime.now().isoformat(),
        "body": (
            "Good morning! Here's what's moving markets today.\n\n"
            "Nvidia (NVDA) closed at another all-time high yesterday. Goldman Sachs raised its "
            "price target to $1,000, citing insatiable demand for H100 chips in AI training "
            "workloads. The setup looks compelling here — we see meaningful upside as the "
            "data center buildout accelerates through 2025.\n\n"
            "Microsoft (MSFT) shares ticked higher after Deutsche Bank raised its target to $450. "
            "Azure cloud growth is reaccelerating and the Copilot monetization opportunity is "
            "still in its early innings. Well-positioned for the AI infrastructure wave.\n\n"
            "Tesla, on the other hand, is facing real headwinds. Delivery numbers disappointed "
            "again and the valuation looks stretched at current levels relative to its growth "
            "trajectory. The risk/reward appears unfavorable here — consider trimming your "
            "position ahead of Q4 earnings if you're sitting on gains.\n\n"
            "AMD stock was upgraded to outperform by Barclays, which sees upside to $200 "
            "as the MI300X GPU gains traction in cloud hyperscaler deployments.\n"
        ),
    },
    {
        "uid": "demo2",
        "sender": "Seeking Alpha <news@seekingalpha.com>",
        "subject": "Defense rally on NATO pledges; Airlines hit by OPEC cut; COIN update",
        "date": datetime.now().isoformat(),
        "body": (
            "Defense Sector — Top Pick Update:\n\n"
            "Lockheed Martin (LMT) remains our high-conviction name in defense. NATO's renewed "
            "spending commitments create a multi-year tailwind and the backlog is at record levels. "
            "Morgan Stanley raised its price target to $600. We're adding to our position.\n\n"
            "$RTX was initiated with overweight by Barclays this morning following its latest "
            "contract win. The integrated defense and aerospace business is well-positioned "
            "as geopolitical tensions sustain elevated procurement budgets.\n\n"
            "Airlines — Cautious Outlook:\n"
            "United Airlines (UAL) is facing a difficult setup. OPEC's production cut sent "
            "crude higher, and jet fuel represents roughly 25% of UAL's operating costs. "
            "The risk/reward looks unfavorable at current levels — we'd stay on the sidelines "
            "until there's more clarity on fuel costs.\n\n"
            "Southwest Airlines (LUV) was downgraded to underperform by JPMorgan, citing "
            "the highest fuel exposure in the group and limited pricing power.\n\n"
            "Coinbase ($COIN) is our top speculative idea. Goldman Sachs sees upside to $250 "
            "on Bitcoin ETF expansion momentum. We've been adding exposure on dips.\n"
        ),
    },
    {
        "uid": "demo3",
        "sender": "Finimize <hello@finimize.com>",
        "subject": "Big Tech earnings week — where we see upside and where to trim",
        "date": datetime.now().isoformat(),
        "body": (
            "Big Tech Earnings Preview:\n\n"
            "Meta (META) — The ad revenue recovery is stronger than expected and "
            "Reels monetization is inflecting. The valuation looks attractive given the "
            "growth runway, and we're maintaining our full position here.\n\n"
            "Google (GOOGL) — We're watching from the sidelines for now. Search revenue "
            "is fairly stable but the competitive threat from AI-native search products "
            "creates uncertainty. Waiting for a better entry point before adding exposure.\n\n"
            "Amazon (AMZN) — AWS growth is reaccelerating and free cash flow generation "
            "is impressive. We see significant upside as the margin expansion story plays out. "
            "A strong long thesis backed by multiple growth drivers.\n\n"
            "Semiconductor check:\n"
            "TSMC (TSM) — AI chip demand is driving record orders. Initiating a new position "
            "here given the attractive valuation relative to its earnings power.\n\n"
            "Intel (INTC) — The foundry business continues losing market share and the "
            "turnaround is taking longer than expected. Valuation still looks rich for a "
            "business with declining margins. We'd avoid for now.\n\n"
            "ExxonMobil (XOM) — Fairly valued at current levels pending the next OPEC meeting. "
            "We're maintaining our position but not adding until there's more direction on oil.\n"
        ),
    },
]


def run(days_back: int = 7, demo: bool = False, show_context: bool = False) -> list:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Get emails ────────────────────────────────────────────────────
    if demo:
        logger.info("Demo mode — using sample newsletter emails")
        emails = _DEMO_EMAILS
    else:
        reader = GmailReader(days_back=days_back)
        emails = reader.fetch_newsletters()

    if not emails:
        logger.warning(
            "No newsletter emails found.\n"
            "  → Run with --demo to test with sample data\n"
            "  → Check that GMAIL_ADDRESS and GMAIL_PASSWORD are in .env\n"
            "  → Ensure Gmail App Password is set (not regular password)"
        )
        return []

    logger.info(f"Processing {len(emails)} newsletter(s)…")

    # ── Step 2: Parse tickers ─────────────────────────────────────────────────
    all_mentions = []
    for em in emails:
        mentions = parse_email(em)
        logger.info(f"  [{em['subject'][:55]}] → {len(mentions)} ticker(s)")
        all_mentions.extend(mentions)

    # Deduplicate: keep highest confidence mention per ticker
    by_ticker = {}
    for m in all_mentions:
        if m.ticker not in by_ticker or by_ticker[m.ticker].confidence < m.confidence:
            by_ticker[m.ticker] = m

    tickers_sorted = sorted(by_ticker.keys())
    logger.info(f"Unique tickers: {tickers_sorted}")

    # ── Step 3: Match with Polymarket ─────────────────────────────────────────
    results = []
    for ticker in tickers_sorted:
        mention = by_ticker[ticker]
        pm_markets = match_ticker_to_markets(mention)

        # Add alignment classification to each market
        for mkt in pm_markets:
            mkt["alignment"] = classify_alignment(mention, mkt)

        result = {
            "ticker":             mention.ticker,
            "direction":          mention.direction,
            "confidence":         mention.confidence,
            "context":            mention.context if show_context else mention.context[:120],
            "source":             mention.source,
            "date":               mention.date,
            "polymarket_matches": pm_markets,
            "has_pm_signal":      len(pm_markets) > 0,
            "pm_confirms":        any(m["alignment"] == "CONFIRMS" for m in pm_markets),
        }
        results.append(result)

        pm_info = f"{len(pm_markets)} match(es)"
        if pm_markets:
            first = pm_markets[0]
            pm_info += f" | '{first['question'][:50]}' YES={first['yes_price']}"
        logger.info(f"  {ticker:6s} [{mention.direction:7s}] conf={mention.confidence:.2f}  PM: {pm_info}")

    # ── Step 4: Save ──────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "collected_at":     datetime.now().isoformat(),
        "emails_processed": len(emails),
        "tickers_found":    len(results),
        "mode":             "demo" if demo else "live",
        "signals":          results,
    }

    (OUTPUT_DIR / f"signals_{ts}.json").write_text(json.dumps(payload, indent=2, default=str))
    (OUTPUT_DIR / "signals_latest.json").write_text(json.dumps(payload, indent=2, default=str))

    logger.info(f"Saved → data/finsignal/signals_latest.json  ({len(results)} signals)")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinSignal newsletter → Polymarket pipeline")
    parser.add_argument("--days",          type=int, default=7,    help="Days back to scan (default: 7)")
    parser.add_argument("--demo",          action="store_true",    help="Use sample emails without Gmail")
    parser.add_argument("--show-context",  action="store_true",    help="Print full context snippets")
    args = parser.parse_args()

    results = run(days_back=args.days, demo=args.demo, show_context=args.show_context)

    print(f"\n{'═'*62}")
    print(f"  FinSignal Results — {len(results)} signals")
    print(f"{'═'*62}")
    if results:
        buy  = [r for r in results if r["direction"] == "BUY"]
        sell = [r for r in results if r["direction"] == "SELL"]
        hold = [r for r in results if r["direction"] == "HOLD"]
        pm   = [r for r in results if r["has_pm_signal"]]
        conf = [r for r in results if r["pm_confirms"]]
        print(f"  BUY: {len(buy)}  SELL: {len(sell)}  HOLD: {len(hold)}")
        print(f"  With Polymarket match: {len(pm)}  Confirmed by PM: {len(conf)}")
        print()
        for r in results:
            pm_flag = "🟢" if r["pm_confirms"] else ("🔵" if r["has_pm_signal"] else "⚫")
            print(f"  {pm_flag} {r['ticker']:6s} {r['direction']:7s} (conf={r['confidence']:.2f})")
            if args.show_context and r["polymarket_matches"]:
                for m in r["polymarket_matches"]:
                    print(f"         → PM: {m['question'][:60]}  YES={m['yes_price']}")
    print(f"{'═'*62}")
    print("  Output: data/finsignal/signals_latest.json")
