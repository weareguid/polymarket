#!/usr/bin/env python3
"""
Trade recorder — log a trade that was triggered by a Polymarket signal.

Usage:
    python scripts/record_trade.py BUY LMT 180.50
    python scripts/record_trade.py BUY LMT 180.50 --source "US strikes Iran 4% YES"
    python scripts/record_trade.py list
    python scripts/record_trade.py performance

The dashboard picks up trades.json automatically and shows P&L.
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

TRADES_FILE = Path(__file__).parent.parent / "data" / "portfolio" / "trades.json"


def load_trades() -> list:
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TRADES_FILE.exists():
        return json.loads(TRADES_FILE.read_text())
    return []


def save_trades(trades: list):
    TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRADES_FILE.write_text(json.dumps(trades, indent=2))


def fetch_current_price(ticker: str):
    """Fetch current stock price using yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except ImportError:
        print("  yfinance not installed. Run: pip install yfinance")
    except Exception as e:
        print(f"  Could not fetch price for {ticker}: {e}")
    return None


def fetch_price_on_date(ticker: str, date_str: str):
    """Fetch closing price on a specific date."""
    try:
        import yfinance as yf
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(date_str[:10])
        start = (dt - timedelta(days=3)).strftime("%Y-%m-%d")
        end   = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        t = yf.Ticker(ticker)
        hist = t.history(start=start, end=end)
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None


def cmd_record(action: str, ticker: str, price: float, source: str):
    trades = load_trades()
    trade = {
        "id":         len(trades) + 1,
        "date":       datetime.now().isoformat(),
        "action":     action.upper(),
        "ticker":     ticker.upper(),
        "price_buy":  price,
        "source":     source,
        "status":     "open",
    }
    trades.append(trade)
    save_trades(trades)
    print(f"Trade #{trade['id']} recorded:")
    print(f"  {trade['action']} {trade['ticker']} @ ${price:.2f}")
    if source:
        print(f"  Source: {source}")
    print(f"  Saved to: {TRADES_FILE}")


def cmd_list():
    trades = load_trades()
    if not trades:
        print("No trades recorded yet.")
        print("Usage: python scripts/record_trade.py BUY TICKER PRICE")
        return

    print(f"\n{'#':<4} {'Date':<12} {'Action':<6} {'Ticker':<8} {'Buy $':<10} {'Source'}")
    print("-" * 70)
    for t in trades:
        date = t["date"][:10]
        print(f"{t['id']:<4} {date:<12} {t['action']:<6} {t['ticker']:<8} "
              f"${t['price_buy']:<9.2f} {t.get('source', '')[:30]}")


def cmd_performance():
    trades = load_trades()
    if not trades:
        print("No trades recorded yet.")
        return

    print(f"\n{'#':<4} {'Ticker':<8} {'Buy $':<10} {'Now $':<10} {'P&L $':<10} {'P&L %':<8} {'Days':<6} Source")
    print("-" * 85)

    total_pnl = 0.0
    wins = 0
    evaluated = 0

    for t in trades:
        ticker     = t["ticker"]
        buy_price  = t["price_buy"]
        buy_date   = t["date"]
        days_held  = (datetime.now() - datetime.fromisoformat(buy_date)).days

        current = fetch_current_price(ticker)
        if current is None:
            print(f"{t['id']:<4} {ticker:<8} ${buy_price:<9.2f} {'N/A':<10} {'?':<10} {'?':<8} {days_held:<6}")
            continue

        pnl_dollar = current - buy_price
        pnl_pct    = (pnl_dollar / buy_price) * 100
        total_pnl += pnl_dollar
        evaluated += 1
        if pnl_dollar >= 0:
            wins += 1

        sign = "+" if pnl_dollar >= 0 else ""
        print(f"{t['id']:<4} {ticker:<8} ${buy_price:<9.2f} ${current:<9.2f} "
              f"{sign}{pnl_dollar:<9.2f} {sign}{pnl_pct:<7.1f}% {days_held:<6} "
              f"{t.get('source', '')[:25]}")

    if evaluated:
        win_rate = wins / evaluated * 100
        print("-" * 85)
        print(f"Win rate: {wins}/{evaluated} ({win_rate:.0f}%)  |  "
              f"Total P&L per share: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Polymarket trade recorder")
    subparsers = parser.add_subparsers(dest="command")

    # record command (default if first arg is BUY/SELL)
    rec = subparsers.add_parser("record", help="Record a trade")
    rec.add_argument("action", choices=["BUY", "SELL", "buy", "sell"])
    rec.add_argument("ticker", help="Stock ticker (e.g. LMT)")
    rec.add_argument("price",  type=float, help="Purchase price")
    rec.add_argument("--source", default="", help="Polymarket signal that triggered it")

    subparsers.add_parser("list",        help="List all recorded trades")
    subparsers.add_parser("performance", help="Show current P&L for all trades")

    # Allow shorthand: record_trade.py BUY LMT 180.50
    if len(sys.argv) >= 4 and sys.argv[1].upper() in ("BUY", "SELL"):
        sys.argv.insert(1, "record")

    args = parser.parse_args()

    if args.command == "record":
        source = getattr(args, "source", "")
        cmd_record(args.action, args.ticker, args.price, source)
    elif args.command == "list":
        cmd_list()
    elif args.command == "performance":
        cmd_performance()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
