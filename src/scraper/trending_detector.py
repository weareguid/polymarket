"""
Trending market detector.

Identifies markets with unusual activity, momentum, or significance.
"""
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import csv
import re
from pathlib import Path

from .polymarket_client import Market, PolymarketClient
from ..utils import config, logger


@dataclass
class TrendingSignal:
    """A detected trending signal."""
    market: Market
    signal_type: str  # "volume_spike", "price_momentum", "high_liquidity", "closing_soon"
    score: float  # 0-1 relevance score
    details: Dict
    detected_at: str


class TrendingDetector:
    """
    Detects trending and significant markets.

    Signals:
    - Volume Spike: 24h volume significantly above average
    - Price Momentum: Large price change in short time
    - High Liquidity: Well-traded markets
    - Closing Soon: Markets ending in next 7 days with activity
    """

    # Markets closing in < 72h already "know" their outcome — volume is
    # end-of-life noise, not a forward-looking signal.
    _MIN_HOURS_TO_CLOSE = 72

    # Regex patterns for markets that can NEVER produce a stock/ETF signal.
    # Order matters: put cheap checks first.
    _NOISE_PATTERNS = [
        # Esports tournaments and individual match markets
        r"\b(counter.?strike|cs2|csgo|league of legends|valorant|dota\b|overwatch|fortnite|rocket league)\b",
        r"\b(pgl [a-z]+|blast [a-z]+|iem [a-z]+|esl [a-z]+|bo3\b|bo5\b)\b",
        r"\b(vitality|aurora gaming|natus vincere|faze clan|g2 esports|team liquid|cloud9|fnatic|navi)\b",
        # Social-media counting markets ("Will X post 300-319 tweets…")
        r"\bpost\b.{0,50}\d{2,4}.{0,30}\btweet",
        r"\btweet.{0,50}\d{2,4}",
        r"\b(tweets?|retweets?).{0,20}(times?|per (day|week)|between)\b",
        # Philosophical / conspiracy / novelty — high volume, zero financial signal
        r"\b(jesus christ|son of god|rapture|second coming)\b",
        r"\balien[s]? (exist|confirmed|disclosure|contact)\b",
        r"\bufo (confirmed|disclosure|reveal)\b",
        r"\b(zombie|asteroid (hit|destroy|wipe out) earth)\b",
        # Entertainment awards (not the same as streaming/media sector ETFs)
        r"\b(academy award|oscar (win|best)|emmy (award|win)|grammy (award|win)|golden globe (win|best)|bafta)\b",
        # Sports — any mention of professional sports league = no financial signal.
        # Covers: matchups, championship futures, MVP, draft, trade rumors, injuries.
        r"\b(nba|nfl|nhl|mlb|mls|wnba|nascar|pga tour|lpga|ufc|wwe)\b",
        r"\b(super bowl|world series|stanley cup|nba finals|nba championship|nfl playoffs)\b",
        r"\b(premier league|la liga|bundesliga|serie a|ligue 1|champions league|europa league|copa del rey)\b",
        r"\b(formula (1|one)|f1 (race|drivers?|champion|grand prix))\b",
        r"\b(wimbledon|us open|french open|australian open|atp|wta)\b",
        r"\b(fifa world cup|euro (2024|2026|2028)|copa america|gold cup)\b",
        r"\b(semifinal|quarterfinal|playoff[s]?|round of \d+)\b.{0,30}\bvs\.?\b",
        # Individual club/team match-day predictions ("Will X win on YYYY-MM-DD?")
        r"win on \d{4}-\d{2}-\d{2}",
        # Football clubs by suffix or well-known names
        r"\b(fc\b|football club|united fc|city fc|sporting cp|real madrid|barcelona|atletico|juventus|"
        r"ac milan|inter milan|internazionale|napoli|celtic|rangers|ajax|benfica|porto|"
        r"west ham|arsenal|chelsea|liverpool|tottenham|manchester|everton|aston villa|"
        r"olympique|lyon|marseille|psg|paris saint.germain|sevilla|osasuna|oviedo|"
        r"monaco|torino|eintracht|al.fateh|al.hilal|al.nassr|al.ittihad)\b",
        # F1 individual driver/champion markets
        r"\bdrivers?'? champion\b",
        # Generic team vs team, spreads, and over/under.
        r"\bspread: \w+",
        r"\w+ vs\.? \w+:? (?:o/u|over/under|over|under)\b",
        r"\w+ vs\.? \w+",
        r"\b(olympic games|winter olympics|summer olympics|paralympics)\b",
        # College sports
        r"\b(ncaa|march madness|college football playoff|cfp)\b",
        # Entertainment / viral creators
        r"\b(mrbeast|mr\.? beast|eurovision|esports)\b",
        # Reality TV / celebrity personal events
        r"\b(bachelor|bachelorette|survivor|big brother|american idol|the voice|dancing with)\b",
    ]

    def __init__(self, client: PolymarketClient = None):
        """
        Initialize detector.

        Args:
            client: Polymarket client instance
        """
        self.client = client or PolymarketClient()
        self.historical_data: Dict[str, List[Dict]] = {}  # market_id -> history

    def _is_relevant_for_detection(self, market: Market) -> bool:
        """
        Pre-filter: returns False for markets that can never produce a
        financially-relevant signal, so we skip them before running any
        detection algorithm.

        Filtered out:
        - Expiring in < 72 h: already near-resolved, volume is noise
        - Sports individual game matchups
        - Esports (CS2, LoL, Valorant, …)
        - Social-media counting markets (tweet counts, etc.)
        - Philosophical / conspiracy novelty markets
        - Entertainment awards
        """
        if market.end_date:
            try:
                end_date = datetime.fromisoformat(
                    market.end_date.replace("Z", "+00:00")
                )
                now = datetime.now(end_date.tzinfo) if end_date.tzinfo else datetime.now()
                hours_remaining = (end_date - now).total_seconds() / 3600
                if hours_remaining < self._MIN_HOURS_TO_CLOSE:
                    logger.debug(
                        f"Skip (expires in {hours_remaining:.0f}h): "
                        f"{market.question[:60]}"
                    )
                    return False
            except Exception:
                pass

        q = market.question.lower()
        for pattern in self._NOISE_PATTERNS:
            if re.search(pattern, q):
                logger.debug(f"Skip (noise pattern): {market.question[:60]}")
                return False

        return True

    def detect_all(self, markets: List[Market] = None) -> List[TrendingSignal]:
        """
        Run all detection algorithms on markets.

        Args:
            markets: Markets to analyze (fetches if not provided)

        Returns:
            List of detected signals, sorted by score
        """
        if markets is None:
            markets = self.client.get_trending_markets(limit=100)

        signals = []
        skipped = 0

        for market in markets:
            if not self._is_relevant_for_detection(market):
                skipped += 1
                continue

            # Volume spike detection
            volume_signal = self._detect_volume_spike(market)
            if volume_signal:
                signals.append(volume_signal)

            # Price momentum detection
            momentum_signal = self._detect_price_momentum(market)
            if momentum_signal:
                signals.append(momentum_signal)

            # Closing soon with activity
            closing_signal = self._detect_closing_soon(market)
            if closing_signal:
                signals.append(closing_signal)

        # Sort by score descending
        signals.sort(key=lambda s: s.score, reverse=True)

        logger.info(
            f"Detected {len(signals)} trending signals "
            f"(skipped {skipped} noise/expiring markets)"
        )
        return signals

    def _detect_volume_spike(self, market: Market) -> Optional[TrendingSignal]:
        """
        Detect if market has unusual volume.

        Args:
            market: Market to analyze

        Returns:
            Signal if detected, None otherwise
        """
        # Simple heuristic: volume_24h > 2x average threshold
        threshold = config.trending_volume_threshold * config.volume_spike_multiplier

        if market.volume_24h >= threshold:
            score = min(1.0, market.volume_24h / (threshold * 2))

            return TrendingSignal(
                market=market,
                signal_type="volume_spike",
                score=score,
                details={
                    "volume_24h": market.volume_24h,
                    "threshold": threshold,
                    "multiplier": market.volume_24h / config.trending_volume_threshold
                },
                detected_at=datetime.now().isoformat()
            )
        return None

    def _detect_price_momentum(self, market: Market) -> Optional[TrendingSignal]:
        """
        Detect significant price movement.

        Args:
            market: Market to analyze

        Returns:
            Signal if detected, None otherwise
        """
        yes_price = market.outcome_prices.get("Yes", 0.5)

        # High conviction markets (price far from 0.5) with volume
        distance_from_50 = abs(yes_price - 0.5)

        if distance_from_50 > 0.3 and market.volume_24h > config.trending_volume_threshold:
            # Strong conviction (>80% or <20%)
            score = distance_from_50 * 2  # 0.3 -> 0.6, 0.5 -> 1.0

            return TrendingSignal(
                market=market,
                signal_type="price_momentum",
                score=min(1.0, score),
                details={
                    "yes_price": yes_price,
                    "distance_from_50": distance_from_50,
                    "direction": "bullish" if yes_price > 0.5 else "bearish"
                },
                detected_at=datetime.now().isoformat()
            )
        return None

    def _detect_closing_soon(self, market: Market) -> Optional[TrendingSignal]:
        """
        Detect markets closing soon with significant activity.

        Args:
            market: Market to analyze

        Returns:
            Signal if detected, None otherwise
        """
        if not market.end_date:
            return None

        try:
            # Parse end date
            end_date = datetime.fromisoformat(market.end_date.replace("Z", "+00:00"))
            now = datetime.now(end_date.tzinfo) if end_date.tzinfo else datetime.now()

            days_to_close = (end_date - now).days

            if 0 < days_to_close <= 7 and market.volume_24h > config.trending_volume_threshold:
                # Closer = higher score
                score = (7 - days_to_close) / 7

                return TrendingSignal(
                    market=market,
                    signal_type="closing_soon",
                    score=score,
                    details={
                        "end_date": market.end_date,
                        "days_to_close": days_to_close,
                        "volume_24h": market.volume_24h
                    },
                    detected_at=datetime.now().isoformat()
                )
        except Exception as e:
            logger.debug(f"Could not parse end date for {market.id}: {e}")

        return None

    def save_signals(self, signals: List[TrendingSignal], filepath: str = None) -> str:
        """
        Save detected signals to CSV.

        Args:
            signals: List of signals to save
            filepath: Custom filepath (optional)

        Returns:
            Path to saved file
        """
        if not filepath:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = config.processed_data_dir / f"signals_{date_str}.csv"

        fieldnames = [
            "market_id", "question", "category", "signal_type", "score",
            "yes_price", "volume_24h", "liquidity", "end_date",
            "details", "detected_at"
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for signal in signals:
                row = {
                    "market_id": signal.market.id,
                    "question": signal.market.question[:200],
                    "category": signal.market.category,
                    "signal_type": signal.signal_type,
                    "score": round(signal.score, 3),
                    "yes_price": signal.market.outcome_prices.get("Yes", 0),
                    "volume_24h": signal.market.volume_24h,
                    "liquidity": signal.market.liquidity,
                    "end_date": signal.market.end_date,
                    "details": str(signal.details),
                    "detected_at": signal.detected_at
                }
                writer.writerow(row)

        logger.info(f"Saved {len(signals)} signals to {filepath}")
        return str(filepath)


def run_daily_detection() -> str:
    """
    Run daily trending detection.

    Returns:
        Path to saved signals file
    """
    detector = TrendingDetector()
    signals = detector.detect_all()
    return detector.save_signals(signals)


if __name__ == "__main__":
    filepath = run_daily_detection()
    print(f"Signals saved to: {filepath}")
