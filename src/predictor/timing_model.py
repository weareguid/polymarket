"""
Timing model for optimal entry/exit decisions.

Determines WHEN to act on a signal based on:
- Distance to event resolution
- Price velocity (rate of change)
- Volume patterns
- Historical patterns (once we have data)
"""
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from enum import Enum

from ..utils import config, logger


class TimingAction(Enum):
    """Recommended timing action."""
    WAIT = "wait"           # Too early, keep monitoring
    PREPARE = "prepare"     # Get ready, event approaching
    ACT_NOW = "act_now"     # Optimal window, execute
    LATE = "late"           # Optimal window may have passed
    EXPIRED = "expired"     # Event resolved or too late


@dataclass
class TimingAnalysis:
    """Result of timing analysis."""
    action: TimingAction
    confidence: float       # 0-1
    days_to_event: Optional[int]
    optimal_window_start: Optional[datetime]
    optimal_window_end: Optional[datetime]
    reasoning: str
    factors: Dict[str, float]  # Individual factor scores


class TimingModel:
    """
    Model for determining optimal timing of trades.

    Based on research findings:
    - Prediction markets price events hours to days before mainstream
    - Stock correlation is highest close to event resolution
    - But acting too late means the move already happened

    Heuristics (to be refined with backtesting):
    - Geopolitical events: 24-72 hours lead time
    - Elections: 1-7 days lead time
    - Earnings/corporate: 1-3 days lead time
    - Crypto markets: 1-6 hours (moves fast)
    """

    def __init__(self):
        """Initialize timing model with default parameters."""
        # Event type specific parameters
        self.event_params = {
            "geopolitical": {
                "optimal_days_before": (1, 3),  # 1-3 days before
                "min_conviction": 0.70,
                "min_volume_spike": 1.5
            },
            "election": {
                "optimal_days_before": (1, 7),
                "min_conviction": 0.75,
                "min_volume_spike": 2.0
            },
            "crypto": {
                "optimal_days_before": (0, 1),  # Same day to 1 day
                "min_conviction": 0.65,
                "min_volume_spike": 1.3
            },
            "economic": {
                "optimal_days_before": (1, 5),
                "min_conviction": 0.70,
                "min_volume_spike": 1.5
            },
            "default": {
                "optimal_days_before": (1, 5),
                "min_conviction": 0.70,
                "min_volume_spike": 1.5
            }
        }

    def analyze(
        self,
        yes_price: float,
        volume_24h: float,
        avg_volume: float,
        end_date: Optional[str],
        event_type: str = "default",
        price_history: List[float] = None
    ) -> TimingAnalysis:
        """
        Analyze optimal timing for a trade.

        Args:
            yes_price: Current YES price (probability)
            volume_24h: Last 24h volume
            avg_volume: Average volume (for comparison)
            end_date: Event end date (ISO format)
            event_type: Type of event (geopolitical, election, crypto, economic)
            price_history: Historical prices for velocity calculation

        Returns:
            TimingAnalysis with recommendation
        """
        params = self.event_params.get(event_type, self.event_params["default"])
        factors = {}

        # 1. Calculate days to event
        days_to_event = self._calculate_days_to_event(end_date)
        factors["days_to_event"] = self._score_days_to_event(days_to_event, params)

        # 2. Calculate conviction score (distance from 0.5)
        conviction = abs(yes_price - 0.5) * 2  # 0 at 0.5, 1 at 0 or 1
        factors["conviction"] = conviction

        # 3. Calculate volume spike
        volume_ratio = volume_24h / avg_volume if avg_volume > 0 else 1.0
        factors["volume_spike"] = min(1.0, volume_ratio / params["min_volume_spike"])

        # 4. Calculate price velocity (if history available)
        if price_history and len(price_history) >= 2:
            velocity = self._calculate_velocity(price_history)
            factors["velocity"] = velocity
        else:
            factors["velocity"] = 0.5  # Neutral

        # 5. Combine factors
        combined_score = self._combine_factors(factors, params)

        # 6. Determine action
        action, reasoning = self._determine_action(
            combined_score=combined_score,
            days_to_event=days_to_event,
            conviction=conviction,
            params=params
        )

        # 7. Calculate optimal window
        window_start, window_end = self._calculate_optimal_window(
            end_date=end_date,
            params=params
        )

        return TimingAnalysis(
            action=action,
            confidence=combined_score,
            days_to_event=days_to_event,
            optimal_window_start=window_start,
            optimal_window_end=window_end,
            reasoning=reasoning,
            factors=factors
        )

    def _calculate_days_to_event(self, end_date: Optional[str]) -> Optional[int]:
        """Calculate days until event resolution."""
        if not end_date:
            return None

        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            now = datetime.now(end_dt.tzinfo) if end_dt.tzinfo else datetime.now()
            delta = end_dt - now
            return max(0, delta.days)
        except Exception:
            return None

    def _score_days_to_event(
        self,
        days: Optional[int],
        params: Dict
    ) -> float:
        """Score based on days to event."""
        if days is None:
            return 0.5  # Unknown, neutral

        min_days, max_days = params["optimal_days_before"]

        if days < 0:
            return 0.0  # Event passed
        elif days == 0:
            return 0.8  # Event today, still actionable
        elif min_days <= days <= max_days:
            return 1.0  # Optimal window
        elif days < min_days:
            return 0.7  # Close but maybe too late
        elif days <= max_days * 2:
            return 0.6  # Approaching window
        else:
            return 0.3  # Too early

    def _calculate_velocity(self, prices: List[float]) -> float:
        """
        Calculate price velocity (rate of change).

        Args:
            prices: List of historical prices (oldest first)

        Returns:
            Velocity score 0-1 (higher = faster movement)
        """
        if len(prices) < 2:
            return 0.5

        # Calculate simple momentum
        recent_change = abs(prices[-1] - prices[-2])
        total_change = abs(prices[-1] - prices[0])

        # Accelerating movement is more significant
        if len(prices) >= 3:
            prev_change = abs(prices[-2] - prices[-3])
            acceleration = recent_change - prev_change
        else:
            acceleration = 0

        # Score: higher total change + acceleration = higher score
        velocity_score = min(1.0, total_change + max(0, acceleration))
        return velocity_score

    def _combine_factors(self, factors: Dict[str, float], params: Dict) -> float:
        """
        Combine factors into single score.

        Weighted average with custom weights.
        """
        weights = {
            "days_to_event": 0.30,
            "conviction": 0.35,
            "volume_spike": 0.20,
            "velocity": 0.15
        }

        total_weight = sum(weights.values())
        score = sum(factors.get(k, 0.5) * w for k, w in weights.items())
        return score / total_weight

    def _determine_action(
        self,
        combined_score: float,
        days_to_event: Optional[int],
        conviction: float,
        params: Dict
    ) -> tuple:
        """Determine action and reasoning."""
        min_days, max_days = params["optimal_days_before"]

        # Event expired
        if days_to_event is not None and days_to_event < 0:
            return TimingAction.EXPIRED, "Event has already resolved"

        # Not enough conviction
        if conviction < params["min_conviction"] - 0.2:
            return TimingAction.WAIT, f"Conviction too low ({conviction:.0%}), waiting for clearer signal"

        # Optimal window
        if combined_score >= 0.75:
            if days_to_event is None or min_days <= days_to_event <= max_days:
                return TimingAction.ACT_NOW, f"High confidence ({combined_score:.0%}), optimal timing window"
            elif days_to_event < min_days:
                return TimingAction.LATE, f"High confidence but may be late, {days_to_event} days to event"
            else:
                return TimingAction.PREPARE, f"High confidence, preparing for optimal window in {days_to_event - max_days} days"

        # Medium confidence
        elif combined_score >= 0.60:
            if days_to_event is not None and days_to_event <= max_days:
                return TimingAction.PREPARE, f"Medium confidence ({combined_score:.0%}), event approaching"
            else:
                return TimingAction.WAIT, f"Medium confidence ({combined_score:.0%}), monitoring"

        # Low confidence
        else:
            return TimingAction.WAIT, f"Low confidence ({combined_score:.0%}), continue monitoring"

    def _calculate_optimal_window(
        self,
        end_date: Optional[str],
        params: Dict
    ) -> tuple:
        """Calculate optimal trading window."""
        if not end_date:
            return None, None

        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            min_days, max_days = params["optimal_days_before"]

            # Window ends min_days before event
            window_end = end_dt - timedelta(days=min_days)
            # Window starts max_days before event
            window_start = end_dt - timedelta(days=max_days)

            return window_start, window_end
        except Exception:
            return None, None

    def classify_event_type(self, question: str, category: str) -> str:
        """
        Classify event type from market question and category.

        Args:
            question: Market question text
            category: Market category

        Returns:
            Event type string
        """
        question_lower = question.lower()

        # Geopolitical keywords
        geo_keywords = ["war", "invasion", "attack", "missile", "military", "conflict",
                       "sanctions", "treaty", "nato", "russia", "ukraine", "taiwan", "china",
                       "iran", "israel", "north korea"]
        if any(kw in question_lower for kw in geo_keywords):
            return "geopolitical"

        # Election keywords
        election_keywords = ["election", "vote", "president", "governor", "senate",
                           "congress", "poll", "ballot", "democrat", "republican"]
        if any(kw in question_lower for kw in election_keywords):
            return "election"

        # Crypto keywords
        crypto_keywords = ["bitcoin", "ethereum", "btc", "eth", "crypto", "token",
                         "blockchain", "defi", "nft"]
        if any(kw in question_lower for kw in crypto_keywords):
            return "crypto"

        # Economic keywords
        economic_keywords = ["fed", "interest rate", "inflation", "gdp", "unemployment",
                           "recession", "tariff", "trade", "economy"]
        if any(kw in question_lower for kw in economic_keywords):
            return "economic"

        return "default"
