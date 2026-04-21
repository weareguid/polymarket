"""
Signal generator for investment recommendations.

Combines all pipeline outputs into actionable investment signals.
"""
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import datetime
import csv
import json

from .timing_model import TimingModel, TimingAction, TimingAnalysis
from ..correlator.stock_correlator import StockSignal
from ..utils import config, logger


@dataclass
class InvestmentSignal:
    """Final investment recommendation."""
    # Instrument info
    ticker: str
    instrument_name: str
    instrument_type: str
    exchange: str

    # Signal info
    action: str              # "BUY", "SELL", "HOLD", "WATCH"
    strength: str            # "strong", "moderate", "weak"
    confidence: float        # 0-1

    # Timing info
    timing_action: str       # TimingAction value
    days_to_event: Optional[int]
    optimal_window: str      # "now", "approaching", "too_early", "passed"

    # Source info
    source_market: str       # Market question
    source_category: str
    market_url: str          # https://polymarket.com/event/{slug}
    yes_price: float
    volume_24h: float

    # Rationale
    rationale: str
    risk_factors: List[str]

    # Metadata
    generated_at: str

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class SignalGenerator:
    """
    Generates final investment signals from the pipeline.

    Combines:
    - Stock correlations (WHAT to trade)
    - Timing analysis (WHEN to trade)
    - Risk assessment (HOW MUCH to risk)
    """

    def __init__(self, timing_model: TimingModel = None):
        """
        Initialize signal generator.

        Args:
            timing_model: Timing model instance
        """
        self.timing = timing_model or TimingModel()

    def generate(
        self,
        stock_signals: List[StockSignal],
        avg_volumes: Dict[str, float] = None
    ) -> List[InvestmentSignal]:
        """
        Generate investment signals from stock signals.

        Args:
            stock_signals: Correlated stock signals
            avg_volumes: Average volumes per market (for timing calc)

        Returns:
            List of investment signals
        """
        avg_volumes = avg_volumes or {}
        signals = []

        for stock_signal in stock_signals:
            market = stock_signal.source_market
            trending = stock_signal.source_signal

            # Get event type for timing
            event_type = self.timing.classify_event_type(
                question=market.question,
                category=market.category
            )

            # Calculate average volume (use threshold as fallback)
            avg_vol = avg_volumes.get(market.id, config.trending_volume_threshold)

            # Run timing analysis
            timing_result = self.timing.analyze(
                yes_price=market.outcome_prices.get("Yes", 0.5),
                volume_24h=market.volume_24h,
                avg_volume=avg_vol,
                end_date=market.end_date,
                event_type=event_type
            )

            # Generate investment signal
            inv_signal = self._create_investment_signal(
                stock_signal=stock_signal,
                timing_result=timing_result,
                event_type=event_type
            )

            if inv_signal:
                signals.append(inv_signal)

        # Sort by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)

        logger.info(f"Generated {len(signals)} investment signals")
        return signals

    def _create_investment_signal(
        self,
        stock_signal: StockSignal,
        timing_result: TimingAnalysis,
        event_type: str
    ) -> Optional[InvestmentSignal]:
        """
        Create investment signal from components.

        Args:
            stock_signal: Stock correlation signal
            timing_result: Timing analysis result
            event_type: Type of event

        Returns:
            InvestmentSignal or None
        """
        instrument = stock_signal.instrument
        market = stock_signal.source_market

        # Determine final action
        action, strength = self._determine_final_action(
            stock_action=stock_signal.action,
            timing_action=timing_result.action,
            combined_score=stock_signal.combined_score,
            timing_confidence=timing_result.confidence
        )

        # Calculate overall confidence
        confidence = (stock_signal.combined_score + timing_result.confidence) / 2

        # Determine optimal window status
        optimal_window = self._determine_window_status(timing_result)

        # Build rationale
        rationale = self._build_rationale(
            stock_signal=stock_signal,
            timing_result=timing_result,
            action=action
        )

        # Identify risk factors
        risk_factors = self._identify_risks(
            market=market,
            timing_result=timing_result,
            event_type=event_type
        )

        return InvestmentSignal(
            ticker=instrument.ticker,
            instrument_name=instrument.name,
            instrument_type=instrument.type,
            exchange=instrument.exchange,
            action=action,
            strength=strength,
            confidence=round(confidence, 3),
            timing_action=timing_result.action.value,
            days_to_event=timing_result.days_to_event,
            optimal_window=optimal_window,
            source_market=market.question[:150],
            source_category=market.category,
            market_url=f"https://polymarket.com/event/{market.slug}" if market.slug else "",
            yes_price=market.outcome_prices.get("Yes", 0.5),
            volume_24h=market.volume_24h,
            rationale=rationale,
            risk_factors=risk_factors,
            generated_at=datetime.now().isoformat()
        )

    def _determine_final_action(
        self,
        stock_action: str,
        timing_action: TimingAction,
        combined_score: float,
        timing_confidence: float
    ) -> tuple:
        """Determine final action and strength."""
        # If timing says wait or expired, downgrade
        if timing_action in [TimingAction.WAIT, TimingAction.EXPIRED]:
            return "WATCH", "weak"

        # If timing says late, be cautious
        if timing_action == TimingAction.LATE:
            if stock_action == "buy_signal":
                return "BUY", "weak"
            elif stock_action == "sell_signal":
                return "SELL", "weak"
            return "WATCH", "weak"

        # If timing says act now or prepare
        if timing_action in [TimingAction.ACT_NOW, TimingAction.PREPARE]:
            avg_confidence = (combined_score + timing_confidence) / 2

            if stock_action == "buy_signal":
                strength = "strong" if avg_confidence > 0.75 else "moderate"
                return "BUY", strength
            elif stock_action == "sell_signal":
                strength = "strong" if avg_confidence > 0.75 else "moderate"
                return "SELL", strength
            else:
                return "HOLD", "moderate"

        return "WATCH", "weak"

    def _determine_window_status(self, timing_result: TimingAnalysis) -> str:
        """Determine optimal window status string."""
        if timing_result.action == TimingAction.ACT_NOW:
            return "now"
        elif timing_result.action == TimingAction.PREPARE:
            return "approaching"
        elif timing_result.action == TimingAction.LATE:
            return "passed"
        elif timing_result.action == TimingAction.EXPIRED:
            return "expired"
        else:
            return "too_early"

    def _build_rationale(
        self,
        stock_signal: StockSignal,
        timing_result: TimingAnalysis,
        action: str
    ) -> str:
        """Build human-readable rationale."""
        parts = []

        # Stock signal rationale
        parts.append(stock_signal.rationale)

        # Timing rationale
        parts.append(timing_result.reasoning)

        # Days to event if known
        if timing_result.days_to_event is not None:
            parts.append(f"Event in {timing_result.days_to_event} days.")

        return " | ".join(parts)

    def _identify_risks(
        self,
        market,
        timing_result: TimingAnalysis,
        event_type: str
    ) -> List[str]:
        """Identify risk factors for the signal."""
        risks = []

        # Low liquidity risk
        if market.liquidity < 5000:
            risks.append("Low liquidity market - execution risk")

        # Close to event risk
        if timing_result.days_to_event is not None:
            if timing_result.days_to_event <= 1:
                risks.append("Event imminent - high volatility expected")
            elif timing_result.days_to_event > 14:
                risks.append("Far from event - signal may change")

        # Conviction uncertainty
        yes_price = market.outcome_prices.get("Yes", 0.5)
        if 0.4 <= yes_price <= 0.6:
            risks.append("Market uncertain (40-60% range)")

        # Event type risks
        if event_type == "geopolitical":
            risks.append("Geopolitical event - unpredictable outcomes")
        elif event_type == "crypto":
            risks.append("Crypto market - extreme volatility possible")

        return risks

    def save_signals(self, signals: List[InvestmentSignal], filepath: str = None) -> str:
        """
        Save investment signals to CSV.

        Args:
            signals: Investment signals to save
            filepath: Custom filepath (optional)

        Returns:
            Path to saved file
        """
        if not filepath:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = config.processed_data_dir / f"investment_signals_{date_str}.csv"

        fieldnames = [
            "ticker", "instrument_name", "instrument_type", "exchange",
            "action", "strength", "confidence",
            "timing_action", "days_to_event", "optimal_window",
            "source_market", "source_category", "market_url", "yes_price", "volume_24h",
            "rationale", "risk_factors", "generated_at"
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for signal in signals:
                row = signal.to_dict()
                row["risk_factors"] = "; ".join(row["risk_factors"])
                writer.writerow(row)

        logger.info(f"Saved {len(signals)} investment signals to {filepath}")
        return str(filepath)

    def print_summary(self, signals: List[InvestmentSignal]):
        """Print human-readable summary of signals."""
        print("\n" + "="*80)
        print("INVESTMENT SIGNALS SUMMARY")
        print("="*80)

        # Group by action
        buys = [s for s in signals if s.action == "BUY"]
        sells = [s for s in signals if s.action == "SELL"]
        watches = [s for s in signals if s.action in ["WATCH", "HOLD"]]

        if buys:
            print(f"\n🟢 BUY SIGNALS ({len(buys)}):")
            for s in buys[:5]:  # Top 5
                print(f"  {s.ticker} ({s.strength}) - {s.confidence:.0%} confidence")
                print(f"    {s.rationale[:100]}...")

        if sells:
            print(f"\n🔴 SELL SIGNALS ({len(sells)}):")
            for s in sells[:5]:
                print(f"  {s.ticker} ({s.strength}) - {s.confidence:.0%} confidence")
                print(f"    {s.rationale[:100]}...")

        if watches:
            print(f"\n🟡 WATCH ({len(watches)}):")
            for s in watches[:3]:
                print(f"  {s.ticker} - monitoring")

        print("\n" + "="*80)


def run_full_pipeline() -> str:
    """
    Run the complete pipeline from scraping to investment signals.

    Returns:
        Path to investment signals file
    """
    from ..scraper import PolymarketClient, TrendingDetector
    from ..correlator import StockCorrelator

    logger.info("Starting full pipeline...")

    # 1. Scrape
    logger.info("Step 1: Fetching markets...")
    client = PolymarketClient()
    markets = client.get_trending_markets(limit=100)
    client.save_snapshot(markets)

    # 2. Detect trending
    logger.info("Step 2: Detecting trending signals...")
    detector = TrendingDetector(client)
    trending_signals = detector.detect_all(markets)
    detector.save_signals(trending_signals)

    # 3. Correlate
    logger.info("Step 3: Correlating with stocks...")
    correlator = StockCorrelator()
    stock_signals = correlator.correlate(trending_signals)
    correlator.save_correlations(stock_signals)

    # 4. Generate investment signals
    logger.info("Step 4: Generating investment signals...")
    generator = SignalGenerator()
    investment_signals = generator.generate(stock_signals)

    # 5. Save and print
    filepath = generator.save_signals(investment_signals)
    generator.print_summary(investment_signals)

    logger.info(f"Pipeline complete! Signals saved to {filepath}")
    return filepath


if __name__ == "__main__":
    run_full_pipeline()
