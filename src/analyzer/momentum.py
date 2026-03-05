"""
Momentum analyzer for price movement detection.
"""
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import csv
from pathlib import Path

from ..utils import config, logger


@dataclass
class MomentumSignal:
    """Detected momentum signal."""
    market_id: str
    direction: str  # "bullish", "bearish", "neutral"
    strength: float  # 0-1
    price_change: float  # Absolute change
    price_change_pct: float  # Percentage change
    current_price: float
    previous_price: float
    window_days: int


class MomentumAnalyzer:
    """
    Analyzes price momentum across markets.

    Compares current prices to historical snapshots to detect
    significant price movements.
    """

    def __init__(self, historical_data_dir: Path = None):
        """
        Initialize analyzer.

        Args:
            historical_data_dir: Directory containing historical snapshots
        """
        self.data_dir = historical_data_dir or config.raw_data_dir
        self._price_history: Dict[str, List[tuple]] = {}  # market_id -> [(date, price), ...]

    def load_historical_data(self, days: int = 7) -> int:
        """
        Load historical price data from snapshots.

        Args:
            days: Number of days of history to load

        Returns:
            Number of records loaded
        """
        self._price_history.clear()
        records_loaded = 0

        # Find all market snapshot files
        snapshot_files = sorted(self.data_dir.glob("markets_*.csv"))

        # Take last N files (assuming daily snapshots)
        recent_files = snapshot_files[-days:] if len(snapshot_files) > days else snapshot_files

        for filepath in recent_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        market_id = row.get('id')
                        yes_price = float(row.get('yes_price', 0))
                        snapshot_time = row.get('snapshot_time', '')

                        if market_id and yes_price > 0:
                            if market_id not in self._price_history:
                                self._price_history[market_id] = []
                            self._price_history[market_id].append((snapshot_time, yes_price))
                            records_loaded += 1
            except Exception as e:
                logger.warning(f"Could not load {filepath}: {e}")

        logger.info(f"Loaded {records_loaded} historical price records for {len(self._price_history)} markets")
        return records_loaded

    def analyze_market(
        self,
        market_id: str,
        current_price: float,
        window_days: int = None
    ) -> Optional[MomentumSignal]:
        """
        Analyze momentum for a single market.

        Args:
            market_id: Market ID
            current_price: Current YES price
            window_days: Window for comparison (defaults to config)

        Returns:
            MomentumSignal if significant movement detected
        """
        window = window_days or config.momentum_window_days

        history = self._price_history.get(market_id, [])
        if not history:
            return None

        # Get oldest price in window
        # Sort by date and take oldest
        sorted_history = sorted(history, key=lambda x: x[0])
        previous_price = sorted_history[0][1]

        # Calculate change
        price_change = current_price - previous_price
        price_change_pct = (price_change / previous_price) if previous_price > 0 else 0

        # Determine direction and strength
        if abs(price_change_pct) < 0.05:  # Less than 5%
            direction = "neutral"
            strength = abs(price_change_pct) / 0.05
        elif price_change > 0:
            direction = "bullish"
            strength = min(1.0, price_change_pct / 0.3)  # 30% = max strength
        else:
            direction = "bearish"
            strength = min(1.0, abs(price_change_pct) / 0.3)

        # Only return if significant
        if direction == "neutral" and strength < 0.5:
            return None

        return MomentumSignal(
            market_id=market_id,
            direction=direction,
            strength=strength,
            price_change=price_change,
            price_change_pct=price_change_pct,
            current_price=current_price,
            previous_price=previous_price,
            window_days=len(sorted_history)
        )

    def analyze_markets(
        self,
        markets: List[Dict],
        min_strength: float = 0.3
    ) -> List[MomentumSignal]:
        """
        Analyze momentum for multiple markets.

        Args:
            markets: List of market dictionaries (must have 'id' and 'yes_price')
            min_strength: Minimum strength to include

        Returns:
            List of momentum signals
        """
        # Load history if not loaded
        if not self._price_history:
            self.load_historical_data()

        signals = []

        for market in markets:
            market_id = market.get('id') or market.get('conditionId')
            current_price = float(market.get('yes_price', 0) or market.get('outcomePrices', [0.5])[0])

            if market_id and current_price > 0:
                signal = self.analyze_market(market_id, current_price)
                if signal and signal.strength >= min_strength:
                    signals.append(signal)

        # Sort by strength
        signals.sort(key=lambda s: s.strength, reverse=True)

        logger.info(f"Found {len(signals)} momentum signals")
        return signals
