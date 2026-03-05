"""
Cross-references FinSignal ticker mentions with active Polymarket markets.

Strategy: fetch a batch of active markets once, then match locally by keyword.
The Gamma API does not support free-text search via query parameters.
"""
import logging
import re
import requests
from typing import List, Dict, Optional

from .newsletter_parser import TickerMention

logger = logging.getLogger("polymarket.finsignal")

GAMMA_URL = "https://gamma-api.polymarket.com"

# Ticker → keywords to match against Polymarket market questions (case-insensitive)
TICKER_KEYWORDS: Dict[str, List[str]] = {
    "AAPL":  ["apple", "iphone", "wwdc", "tim cook"],
    "MSFT":  ["microsoft", "azure", "openai", "copilot"],
    "GOOGL": ["google", "alphabet", "youtube", "gemini", "search"],
    "GOOG":  ["google", "alphabet", "youtube"],
    "AMZN":  ["amazon", "aws", "amazon prime"],
    "META":  ["meta platforms", "facebook", "instagram", "zuckerberg"],
    "NVDA":  ["nvidia", "nvda", "gpu", "blackwell", "jensen huang"],
    "TSLA":  ["tesla", "elon musk", "cybertruck"],
    "AMD":   ["advanced micro", "amd gpu", "amd chip", "amd cpu"],
    "INTC":  ["intel"],
    "TSM":   ["tsmc", "taiwan semiconductor", "taiwan"],
    "BA":    ["boeing"],
    "LMT":   ["lockheed"],
    "RTX":   ["raytheon"],
    "NOC":   ["northrop"],
    "JPM":   ["jpmorgan", "jp morgan"],
    "GS":    ["goldman sachs", "goldman"],
    "BAC":   ["bank of america"],
    "MS":    ["morgan stanley"],
    "COIN":  ["coinbase"],
    "MSTR":  ["microstrategy", "michael saylor"],
    "UAL":   ["united airlines"],
    "DAL":   ["delta"],
    "LUV":   ["southwest airlines"],
    "AAL":   ["american airlines"],
    "TM":    ["toyota"],
    "F":     ["ford"],
    "GM":    ["general motors"],
    "RIVN":  ["rivian"],
    "XOM":   ["exxon", "exxonmobil"],
    "CVX":   ["chevron"],
    "BTC":   ["bitcoin", "btc"],
    "ETH":   ["ethereum", "eth"],
    "WEAT":  ["wheat", "grain"],
    "UNG":   ["natural gas", "lng"],
    "ITA":   ["defense", "nato", "military spending"],
    "KWEB":  ["china internet", "china tech"],
    "VGK":   ["europe", "european stocks"],
    "ERUS":  ["russia", "russian"],
    "VNQ":   ["real estate", "reit"],
    "KRE":   ["regional banks", "community banks"],
    "GLD":   ["gold"],
    "SLV":   ["silver"],
    "HOOD":  ["robinhood"],
    "SNAP":  ["snapchat", "snap"],
    "UBER":  ["uber"],
    "SHOP":  ["shopify"],
    "PLTR":  ["palantir"],
    "SNOW":  ["snowflake"],
    # Healthcare / insurance
    "UNH":   ["unitedhealth", "united health", "unitedhealthcare", "medicare advantage"],
    "HUM":   ["humana"],
    "CVS":   ["cvs health", "cvs", "aetna"],
    "ELV":   ["elevance", "anthem"],
    "CNC":   ["centene"],
    "MOH":   ["molina"],
    "CI":    ["cigna"],
    # Tech / consumer
    "MU":    ["micron", "dram", "memory chip"],
    "GLW":   ["corning", "fiber optic", "optical fiber"],
    "PINS":  ["pinterest"],
    "BYND":  ["beyond meat", "plant-based meat", "plant based meat"],
    "W":     ["wayfair"],
    "ETSY":  ["etsy"],
    "ACN":   ["accenture"],
    "EBAY":  ["ebay"],
    # Commodities / macro ETFs
    "BTC-USD": ["bitcoin", "btc"],
    "ETH-USD": ["ethereum", "eth"],
}

# Module-level cache for fetched markets (one fetch per run)
_market_cache: Optional[List[Dict]] = None


def _fetch_active_markets(limit: int = 500) -> List[Dict]:
    """Fetch active Polymarket markets sorted by 24h volume."""
    global _market_cache
    if _market_cache is not None:
        return _market_cache

    try:
        r = requests.get(
            f"{GAMMA_URL}/markets",
            params={"active": "true", "closed": "false", "limit": limit,
                    "order": "volume24hr", "ascending": "false"},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                _market_cache = data
                logger.info(f"Fetched {len(data)} active Polymarket markets for matching")
                return data
    except Exception as exc:
        logger.warning(f"Could not fetch Polymarket markets: {exc}")

    _market_cache = []
    return []


def _normalize_price(raw) -> str:
    """Parse outcomePrices (list or string) → YES price as string like '0.65'."""
    try:
        import json
        prices = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(prices, list) and prices:
            return str(round(float(prices[0]), 3))
    except Exception:
        pass
    return "?"


def match_ticker_to_markets(mention: TickerMention, top_n: int = 3) -> List[Dict]:
    """
    Find active Polymarket markets related to the ticker by local keyword search.

    Returns list of dicts: question, yes_price, volume_24h, end_date, url, alignment.
    """
    markets   = _fetch_active_markets()
    keywords  = TICKER_KEYWORDS.get(mention.ticker, [mention.ticker.lower()])
    results   = []
    seen_ids: set = set()

    for mkt in markets:
        mid      = mkt.get("id", "")
        question = mkt.get("question", "").lower()

        if mid in seen_ids:
            continue
        if not any(re.search(r'\b' + re.escape(kw.lower()) + r'\b', question)
                   for kw in keywords):
            continue

        seen_ids.add(mid)
        yes_price = _normalize_price(mkt.get("outcomePrices"))

        results.append({
            "question":   mkt.get("question", "")[:120],
            "yes_price":  yes_price,
            "volume_24h": round(float(mkt.get("volume24hr") or 0), 0),
            "end_date":   (mkt.get("endDate") or "")[:10],
            "url":        f"https://polymarket.com/event/{mkt.get('slug', '')}",
        })

        if len(results) >= top_n:
            break

    return results


def classify_alignment(mention: TickerMention, market: Dict) -> str:
    """
    CONFIRMS if newsletter direction aligns with Polymarket probability.
    BUY + high YES (>0.6) = CONFIRMS, SELL + low YES (<0.4) = CONFIRMS.
    """
    try:
        yes_price = float(market.get("yes_price", 0.5))
    except (ValueError, TypeError):
        return "NEUTRAL"

    if mention.direction == "BUY"  and yes_price > 0.60:
        return "CONFIRMS"
    if mention.direction == "SELL" and yes_price < 0.40:
        return "CONFIRMS"
    return "NEUTRAL"
