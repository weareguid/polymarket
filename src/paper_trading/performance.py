"""
PerformanceTracker — compute summary statistics over paper trade history.

Uses only stdlib + dataclasses. No pandas required.
"""
import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.paper_trading.models import PaperTrade

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    Compute aggregate statistics across open and closed paper trades.

    Parameters
    ----------
    open_trades:
        List of PaperTrade objects with status="open".
    closed_trades:
        List of PaperTrade objects with status="closed" or "expired".
    """

    def __init__(
        self,
        open_trades: List[PaperTrade],
        closed_trades: List[PaperTrade],
    ) -> None:
        self._open = list(open_trades)
        self._closed = list(closed_trades)
        self._all = self._open + self._closed

    # ------------------------------------------------------------------
    # Top-level summary
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """
        Return a flat dict of portfolio-level statistics.

        Keys
        ----
        total_trades, open_count, closed_count,
        win_count, loss_count, neutral_count,
        win_rate (0.0–1.0),
        avg_return_pct, best_trade (dict), worst_trade (dict),
        total_return_pct
        """
        closed = self._closed
        wins    = [t for t in closed if t.outcome == "win"]
        losses  = [t for t in closed if t.outcome == "loss"]
        neutrals = [t for t in closed if t.outcome == "neutral"]

        decided = len(wins) + len(losses)  # exclude neutrals for win-rate
        win_rate = len(wins) / decided if decided > 0 else 0.0

        returns = [t.price_move_pct for t in closed if t.price_move_pct != 0.0]
        avg_return_pct = sum(returns) / len(returns) if returns else 0.0
        total_return_pct = sum(returns)

        best_trade  = self._trade_to_summary(max(closed, key=lambda t: t.price_move_pct, default=None))
        worst_trade = self._trade_to_summary(min(closed, key=lambda t: t.price_move_pct, default=None))

        return {
            "total_trades":     len(self._all),
            "open_count":       len(self._open),
            "closed_count":     len(closed),
            "win_count":        len(wins),
            "loss_count":       len(losses),
            "neutral_count":    len(neutrals),
            "win_rate":         round(win_rate, 4),
            "avg_return_pct":   round(avg_return_pct, 4),
            "best_trade":       best_trade,
            "worst_trade":      worst_trade,
            "total_return_pct": round(total_return_pct, 4),
        }

    # ------------------------------------------------------------------
    # Per-ticker breakdown
    # ------------------------------------------------------------------

    def by_ticker(self) -> List[Dict[str, Any]]:
        """
        Return per-ticker aggregated stats, sorted by number of trades descending.

        Each entry contains:
            ticker, trades, wins, losses, neutral, win_rate (0.0–1.0),
            avg_return_pct, total_return_pct
        """
        buckets: Dict[str, List[PaperTrade]] = defaultdict(list)
        for trade in self._all:
            buckets[trade.ticker].append(trade)

        rows = []
        for ticker, trades in buckets.items():
            closed = [t for t in trades if t.status in ("closed", "expired")]
            wins   = sum(1 for t in closed if t.outcome == "win")
            losses = sum(1 for t in closed if t.outcome == "loss")
            neutral = sum(1 for t in closed if t.outcome == "neutral")
            decided = wins + losses
            win_rate = wins / decided if decided > 0 else 0.0
            returns = [t.price_move_pct for t in closed]
            avg_return = sum(returns) / len(returns) if returns else 0.0
            rows.append({
                "ticker":           ticker,
                "trades":           len(trades),
                "wins":             wins,
                "losses":           losses,
                "neutral":          neutral,
                "win_rate":         round(win_rate, 4),
                "avg_return_pct":   round(avg_return, 4),
                "total_return_pct": round(sum(returns), 4),
            })

        rows.sort(key=lambda r: r["trades"], reverse=True)
        return rows

    # ------------------------------------------------------------------
    # Per confirmation source breakdown
    # ------------------------------------------------------------------

    def by_source(self) -> List[Dict[str, Any]]:
        """
        Return stats grouped by confirmation source tag.

        Each entry contains:
            source, appearances, wins, losses, neutral, win_rate
        """
        source_trades: Dict[str, List[PaperTrade]] = defaultdict(list)
        for trade in self._all:
            for src in trade.confirmation_sources:
                source_trades[src].append(trade)

        rows = []
        for source, trades in source_trades.items():
            closed  = [t for t in trades if t.status in ("closed", "expired")]
            wins    = sum(1 for t in closed if t.outcome == "win")
            losses  = sum(1 for t in closed if t.outcome == "loss")
            neutral = sum(1 for t in closed if t.outcome == "neutral")
            decided = wins + losses
            win_rate = wins / decided if decided > 0 else 0.0
            rows.append({
                "source":      source,
                "appearances": len(trades),
                "wins":        wins,
                "losses":      losses,
                "neutral":     neutral,
                "win_rate":    round(win_rate, 4),
            })

        rows.sort(key=lambda r: r["appearances"], reverse=True)
        return rows

    # ------------------------------------------------------------------
    # Streak analysis
    # ------------------------------------------------------------------

    def streak(self) -> Dict[str, int]:
        """
        Analyse the win/loss streak over closed trades (sorted by exit_date).

        Returns
        -------
        {
            "current_streak":  int,   # positive = wins, negative = losses
            "max_win_streak":  int,
            "max_loss_streak": int,   # stored as positive integer
        }
        """
        # Only consider decided outcomes
        decided = [
            t for t in self._closed
            if t.outcome in ("win", "loss") and t.exit_date
        ]
        decided.sort(key=lambda t: t.exit_date)

        if not decided:
            return {"current_streak": 0, "max_win_streak": 0, "max_loss_streak": 0}

        # Build outcome sequence: +1 for win, -1 for loss
        sequence = [1 if t.outcome == "win" else -1 for t in decided]

        current_streak = self._compute_current_streak(sequence)
        max_win_streak, max_loss_streak = self._compute_max_streaks(sequence)

        return {
            "current_streak":  current_streak,
            "max_win_streak":  max_win_streak,
            "max_loss_streak": max_loss_streak,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_current_streak(sequence: List[int]) -> int:
        """
        Count the current unbroken streak at the tail of *sequence*.

        Returns positive int for wins, negative for losses.
        """
        if not sequence:
            return 0
        direction = sequence[-1]  # +1 or -1
        count = 0
        for val in reversed(sequence):
            if val == direction:
                count += 1
            else:
                break
        return count * direction

    @staticmethod
    def _compute_max_streaks(sequence: List[int]) -> tuple:
        """
        Return (max_win_streak, max_loss_streak) as positive integers.
        """
        max_win = 0
        max_loss = 0
        current = 0
        prev = 0

        for val in sequence:
            if val == prev:
                current += 1
            else:
                current = 1
            prev = val

            if val == 1:
                max_win = max(max_win, current)
            else:
                max_loss = max(max_loss, current)

        return max_win, max_loss

    @staticmethod
    def _trade_to_summary(trade: Optional[PaperTrade]) -> Dict[str, Any]:
        """Convert a PaperTrade to a minimal summary dict, or {} if None."""
        if trade is None:
            return {}
        return {
            "id":             trade.id,
            "ticker":         trade.ticker,
            "action":         trade.action,
            "entry_price":    trade.entry_price,
            "exit_price":     trade.exit_price,
            "price_move_pct": trade.price_move_pct,
            "outcome":        trade.outcome,
            "entry_date":     trade.entry_date,
            "exit_date":      trade.exit_date,
        }
