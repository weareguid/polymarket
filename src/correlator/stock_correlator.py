"""
Stock correlator module.

Maps prediction market signals to potentially affected stocks and ETFs.
"""
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime
import csv
import re

from .knowledge_base import KnowledgeBase, Instrument
from ..scraper.trending_detector import TrendingSignal
from ..scraper.polymarket_client import Market
from ..utils import config, logger


@dataclass
class StockSignal:
    """A signal mapped to a specific stock/ETF."""
    instrument: Instrument
    source_market: Market
    source_signal: TrendingSignal
    relevance_score: float  # How relevant is this instrument to the market
    combined_score: float   # relevance * signal score
    action: str            # "watch", "buy_signal", "sell_signal"
    rationale: str         # Human-readable explanation


class StockCorrelator:
    """
    Maps prediction market signals to stock/ETF instruments.

    Uses knowledge base to find correlations and generates actionable signals.
    """

    def __init__(self, knowledge_base: KnowledgeBase = None):
        """
        Initialize correlator.

        Args:
            knowledge_base: Knowledge base instance
        """
        self.kb = knowledge_base or KnowledgeBase()

    # Keywords that indicate a non-financial market (sports, entertainment, etc.)
    _SPORTS_KEYWORDS = [
        "medal", "championship", "tournament", "world cup", "stanley cup",
        "super bowl", "nba", "nfl", "nhl", "mlb", "fifa", "uefa", "premier league",
        "champions league", "mvp", "playoffs", "conference finals", "nfl draft",
        "wimbledon", "us open", "french open", "australian open", "olympic",
        "olympics", "world series", "march madness", "final four",
    ]
    _NON_FINANCE_KEYWORDS = [
        "jesus christ", "aliens exist", "alien", "extraterrestrial",
        "will god", "rapture", "zombie", "asteroid", "alien",
    ]
    # Topics that ARE financial/relevant even if they mention a country
    _FINANCE_KEYWORDS = [
        "strike", "attack", "invasion", "sanction", "tariff", "trade war",
        "military", "war", "conflict", "interest rate", "fed ", "inflation",
        "recession", "gdp", "bitcoin", "ethereum", "crypto", "election",
        "nominate", "president", "senate", "congress", "economy",
        "earnings", "stock", "ipo", "merger", "acquisition",
    ]

    def _is_financially_relevant(self, question: str) -> bool:
        """
        Filter out sports, entertainment and other non-financial markets.

        Returns True if the market is potentially relevant to financial instruments.
        """
        q = question.lower()

        # Immediately reject known non-financial topics
        for kw in self._NON_FINANCE_KEYWORDS:
            if kw in q:
                return False

        # If it contains a sports keyword but NO financial keyword → reject
        has_sports = any(kw in q for kw in self._SPORTS_KEYWORDS)
        if has_sports:
            has_finance = any(kw in q for kw in self._FINANCE_KEYWORDS)
            if not has_finance:
                return False

        return True

    def correlate(self, signals: List[TrendingSignal]) -> List[StockSignal]:
        """
        Map trending signals to stock signals.

        Args:
            signals: Trending signals from Polymarket

        Returns:
            List of stock signals
        """
        stock_signals = []

        for signal in signals:
            market = signal.market

            # Skip non-financial markets (sports, entertainment, etc.)
            if not self._is_financially_relevant(market.question):
                logger.debug(f"Skipping non-financial market: {market.question[:60]}")
                continue

            # Search for related instruments
            instruments = self.kb.search(market.question)

            if not instruments:
                # Try searching in description too
                instruments = self.kb.search(market.description)

            for instrument in instruments:
                stock_signal = self._create_stock_signal(
                    instrument=instrument,
                    signal=signal
                )
                if stock_signal:
                    stock_signals.append(stock_signal)

        # Deduplicate and rank
        stock_signals = self._deduplicate_and_rank(stock_signals)

        logger.info(f"Generated {len(stock_signals)} stock signals")
        return stock_signals

    def _create_stock_signal(
        self,
        instrument: Instrument,
        signal: TrendingSignal
    ) -> Optional[StockSignal]:
        """
        Create a stock signal from an instrument and trending signal.

        Args:
            instrument: Financial instrument
            signal: Source trending signal

        Returns:
            StockSignal or None
        """
        market = signal.market

        # Calculate relevance (simple text matching for now)
        question_lower = market.question.lower()
        relevance = 0.7  # Base relevance for any keyword/country/sector match

        # Boost if ticker or company mentioned directly
        if instrument.ticker.lower() in question_lower:
            relevance = 1.0
        elif instrument.name.lower() in question_lower:
            relevance = 0.9

        # Combined score
        combined_score = relevance * signal.score

        # Skip low scores
        if combined_score < config.min_correlation_confidence:
            return None

        # Determine action based on market outcome and correlation direction
        yes_price = market.outcome_prices.get("Yes", 0.5)
        action, rationale = self._determine_action(
            instrument=instrument,
            yes_price=yes_price,
            signal_type=signal.signal_type,
            question=market.question
        )

        return StockSignal(
            instrument=instrument,
            source_market=market,
            source_signal=signal,
            relevance_score=relevance,
            combined_score=combined_score,
            action=action,
            rationale=rationale
        )

    def _determine_action(
        self,
        instrument: Instrument,
        yes_price: float,
        signal_type: str,
        question: str
    ) -> tuple:
        """
        Determine trading action based on signal and correlation.

        Args:
            instrument: The instrument
            yes_price: Current Yes price (probability)
            signal_type: Type of trending signal
            question: Market question

        Returns:
            Tuple of (action, rationale)
        """
        # Default to watch
        action = "watch"
        rationale = ""

        # Strong conviction threshold
        HIGH_CONVICTION = 0.75
        LOW_CONVICTION = 0.25

        if instrument.correlation_direction == "positive":
            if yes_price > HIGH_CONVICTION:
                action = "buy_signal"
                rationale = f"Market {yes_price:.0%} likely YES, positive correlation with {instrument.ticker}"
            elif yes_price < LOW_CONVICTION:
                action = "sell_signal"
                rationale = f"Market {yes_price:.0%} likely NO, positive correlation = negative for {instrument.ticker}"
            else:
                rationale = f"Watching {instrument.ticker} - market at {yes_price:.0%}, waiting for conviction"

        elif instrument.correlation_direction == "negative":
            if yes_price > HIGH_CONVICTION:
                action = "sell_signal"
                rationale = f"Market {yes_price:.0%} likely YES, negative correlation = sell {instrument.ticker}"
            elif yes_price < LOW_CONVICTION:
                action = "buy_signal"
                rationale = f"Market {yes_price:.0%} likely NO, negative correlation = buy {instrument.ticker}"
            else:
                rationale = f"Watching {instrument.ticker} - market at {yes_price:.0%}, inverse correlation"

        else:  # neutral
            rationale = f"Neutral correlation - monitor {instrument.ticker} for volatility"

        # Add signal type context
        if signal_type == "closing_soon":
            rationale += " [EVENT IMMINENT]"
        elif signal_type == "volume_spike":
            rationale += " [HIGH VOLUME]"

        return action, rationale

    def _deduplicate_and_rank(self, signals: List[StockSignal]) -> List[StockSignal]:
        """
        Deduplicate signals (keep highest score per ticker) and rank.

        Args:
            signals: List of stock signals

        Returns:
            Deduplicated and sorted list
        """
        by_ticker: Dict[str, StockSignal] = {}

        for signal in signals:
            ticker = signal.instrument.ticker
            if ticker not in by_ticker or signal.combined_score > by_ticker[ticker].combined_score:
                by_ticker[ticker] = signal

        # Sort by combined score
        ranked = sorted(by_ticker.values(), key=lambda s: s.combined_score, reverse=True)
        return ranked

    def save_correlations(self, signals: List[StockSignal], filepath: str = None) -> str:
        """
        Save correlations to CSV.

        Args:
            signals: Stock signals to save
            filepath: Custom filepath (optional)

        Returns:
            Path to saved file
        """
        if not filepath:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = config.processed_data_dir / f"correlations_{date_str}.csv"

        fieldnames = [
            "ticker", "instrument_name", "type", "correlation_direction",
            "action", "combined_score", "relevance_score",
            "market_question", "yes_price", "volume_24h",
            "signal_type", "rationale", "generated_at"
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for signal in signals:
                row = {
                    "ticker": signal.instrument.ticker,
                    "instrument_name": signal.instrument.name,
                    "type": signal.instrument.type,
                    "correlation_direction": signal.instrument.correlation_direction,
                    "action": signal.action,
                    "combined_score": round(signal.combined_score, 3),
                    "relevance_score": round(signal.relevance_score, 3),
                    "market_question": signal.source_market.question[:150],
                    "yes_price": signal.source_market.outcome_prices.get("Yes", 0),
                    "volume_24h": signal.source_market.volume_24h,
                    "signal_type": signal.source_signal.signal_type,
                    "rationale": signal.rationale,
                    "generated_at": datetime.now().isoformat()
                }
                writer.writerow(row)

        logger.info(f"Saved {len(signals)} correlations to {filepath}")
        return str(filepath)


def run_correlation_pipeline():
    """
    Run full correlation pipeline: fetch -> detect -> correlate -> save.

    Returns:
        Path to correlations file
    """
    from ..scraper import PolymarketClient, TrendingDetector

    # 1. Fetch markets
    client = PolymarketClient()
    markets = client.get_trending_markets(limit=100)
    client.save_snapshot(markets)

    # 2. Detect signals
    detector = TrendingDetector(client)
    signals = detector.detect_all(markets)
    detector.save_signals(signals)

    # 3. Correlate
    correlator = StockCorrelator()
    stock_signals = correlator.correlate(signals)

    # 4. Save
    return correlator.save_correlations(stock_signals)


if __name__ == "__main__":
    filepath = run_correlation_pipeline()
    print(f"Pipeline complete. Correlations saved to: {filepath}")
