#!/usr/bin/env python3
"""
Main entry point for running the Polymarket investment pipeline.

Usage:
    python run_pipeline.py          # Run full pipeline
    python run_pipeline.py scrape   # Only scrape markets
    python run_pipeline.py signals  # Generate signals from existing data
"""
import sys
from datetime import datetime

from src.scraper import PolymarketClient, TrendingDetector
from src.correlator import StockCorrelator
from src.predictor import SignalGenerator
from src.utils import logger, config


def run_scrape():
    """Run only the scraping step."""
    logger.info("Starting scrape...")

    client = PolymarketClient()
    markets = client.get_trending_markets(limit=100)

    filepath = client.save_snapshot(markets)
    logger.info(f"Scraped {len(markets)} markets to {filepath}")

    return markets


def run_detect(markets=None):
    """Run signal detection."""
    logger.info("Running signal detection...")

    if markets is None:
        # Load from most recent snapshot
        import csv
        from pathlib import Path

        snapshots = sorted(config.raw_data_dir.glob("markets_*.csv"))
        if not snapshots:
            logger.error("No market snapshots found. Run scrape first.")
            return []

        latest = snapshots[-1]
        logger.info(f"Loading from {latest}")

        # Would need to convert back to Market objects
        # For now, just run fresh
        client = PolymarketClient()
        markets = client.get_trending_markets(limit=100)

    detector = TrendingDetector()
    signals = detector.detect_all(markets)
    detector.save_signals(signals)

    logger.info(f"Detected {len(signals)} trending signals")
    return signals


def run_correlate(signals):
    """Run stock correlation."""
    logger.info("Running stock correlation...")

    correlator = StockCorrelator()
    stock_signals = correlator.correlate(signals)
    correlator.save_correlations(stock_signals)

    logger.info(f"Generated {len(stock_signals)} stock signals")
    return stock_signals


def run_generate(stock_signals):
    """Generate final investment signals."""
    logger.info("Generating investment signals...")

    generator = SignalGenerator()
    investment_signals = generator.generate(stock_signals)

    filepath = generator.save_signals(investment_signals)
    generator.print_summary(investment_signals)

    return investment_signals, filepath


def run_full_pipeline():
    """Run the complete pipeline."""
    print("\n" + "="*60)
    print("POLYMARKET INVESTMENT ADVISER")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

    # Step 1: Scrape
    print("Step 1/4: Scraping Polymarket...")
    client = PolymarketClient()
    markets = client.get_trending_markets(limit=100)
    client.save_snapshot(markets)
    print(f"  -> Found {len(markets)} trending markets\n")

    # Step 2: Detect
    print("Step 2/4: Detecting signals...")
    detector = TrendingDetector(client)
    trending_signals = detector.detect_all(markets)
    detector.save_signals(trending_signals)
    print(f"  -> Detected {len(trending_signals)} signals\n")

    # Step 3: Correlate
    print("Step 3/4: Correlating with stocks...")
    correlator = StockCorrelator()
    stock_signals = correlator.correlate(trending_signals)
    correlator.save_correlations(stock_signals)
    print(f"  -> Mapped to {len(stock_signals)} instruments\n")

    # Step 4: Generate
    print("Step 4/4: Generating investment signals...")
    generator = SignalGenerator()
    investment_signals = generator.generate(stock_signals)
    filepath = generator.save_signals(investment_signals)

    # Print summary
    generator.print_summary(investment_signals)

    print(f"\nResults saved to: {filepath}")
    print("\nPipeline complete!")

    return investment_signals


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "scrape":
            run_scrape()
        elif command == "signals":
            # Run from existing data
            signals = run_detect()
            if signals:
                stock_signals = run_correlate(signals)
                if stock_signals:
                    run_generate(stock_signals)
        elif command == "help":
            print(__doc__)
        else:
            print(f"Unknown command: {command}")
            print(__doc__)
    else:
        run_full_pipeline()


if __name__ == "__main__":
    main()
