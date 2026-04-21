"""
Paper Trading Daily Check
=========================
Run this daily (after generate_dashboard.py) to:
  1. Check if any open paper trades have resolved
  2. Close resolved trades with their outcomes
  3. Print a performance summary

Usage:
    python scripts/paper_trading_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.paper_trading import PaperTradeLogger, PaperTradeResolver, PerformanceTracker
from src.scraper import PolymarketClient


def main():
    logger   = PaperTradeLogger()
    client   = PolymarketClient()
    resolver = PaperTradeResolver(client)

    open_trades   = logger.load_open_trades()
    closed_trades = logger.load_closed_trades()

    print(f"\n📋 Paper Trading Check")
    print(f"   Open trades:   {len(open_trades)}")
    print(f"   Closed trades: {len(closed_trades)}")

    if not open_trades:
        print("   No open trades to resolve.")
    else:
        still_open, newly_closed = resolver.check_resolutions(open_trades)

        if newly_closed:
            print(f"\n✅ Resolved {len(newly_closed)} trade(s):")
            for t in newly_closed:
                icon = "🟢" if t.outcome == "win" else ("🔴" if t.outcome == "loss" else "⚪")
                print(f"   {icon} {t.ticker} ({t.action}) → {t.outcome.upper():7} "
                      f"| PM resolved={'YES' if t.pm_resolved_yes else 'NO':3} "
                      f"| Price move: {t.price_move_pct:+.1f}%")
        else:
            print("   No new resolutions found.")

        logger.save_open_trades(still_open)
        logger.save_closed_trades(closed_trades + newly_closed)
        closed_trades = closed_trades + newly_closed

    # Performance summary
    all_open   = logger.load_open_trades()
    tracker    = PerformanceTracker(all_open, closed_trades)
    summary    = tracker.summary()

    print(f"\n📊 Performance Summary")
    print(f"   Total trades:  {summary['total_trades']}")
    print(f"   Win rate:      {summary['win_rate']:.0%}  "
          f"({summary['win_count']}W / {summary['loss_count']}L / {summary['neutral_count']}N)")
    print(f"   Avg return:    {summary['avg_return_pct']:+.1f}%")
    print(f"   Total return:  {summary['total_return_pct']:+.1f}%")

    if summary.get("best_trade"):
        b = summary["best_trade"]
        print(f"   Best trade:    {b.get('ticker')} {b.get('price_move_pct',0):+.1f}%")
    if summary.get("worst_trade"):
        w = summary["worst_trade"]
        print(f"   Worst trade:   {w.get('ticker')} {w.get('price_move_pct',0):+.1f}%")

    streak = tracker.streak()
    if streak["current_streak"] != 0:
        direction = "win" if streak["current_streak"] > 0 else "loss"
        print(f"   Current streak: {abs(streak['current_streak'])} {direction}(s)")

    print()


if __name__ == "__main__":
    main()
