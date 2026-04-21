"""
Momentum analysis for paper trading signals.

Uses yfinance to compute recent price momentum for a list of tickers,
then classifies each ticker's momentum relative to the proposed trade action.
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]
    logger.warning("yfinance not installed — MomentumFilter will return neutral for all tickers")


class MomentumFilter:
    """
    Computes 10-day (or N-day) price momentum for a batch of tickers and
    classifies each result relative to a proposed trade action.
    """

    # Threshold constants (percentage points)
    STRONG_THRESHOLD: float = 5.0   # |pct_change| > this → "late_bull" / "late_bear"
    MILD_THRESHOLD: float = 3.0     # |pct_change| >= this → "trending_up" / "trending_down"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_momentum_batch(
        self, tickers: List[str], days: int = 10
    ) -> Dict[str, dict]:
        """
        Fetch momentum data for a list of tickers.

        Parameters
        ----------
        tickers:
            List of equity ticker symbols (e.g. ["AAPL", "TSLA"]).
        days:
            Look-back window in *trading* days.  We request ``days + 5``
            calendar days of history to guarantee enough trading-day rows.

        Returns
        -------
        Dict[ticker, {"pct_change": float | None, "flag": str}]
            flag values: "neutral", "late_bull", "late_bear",
                         "trending_up", "trending_down"
        """
        results: Dict[str, dict] = {}

        if not tickers:
            return results

        if yf is None:
            logger.warning("yfinance unavailable — returning neutral for all tickers")
            for ticker in tickers:
                results[ticker] = {"pct_change": None, "flag": "neutral"}
            return results

        for ticker in tickers:
            results[ticker] = self._fetch_single(ticker, days)

        return results

    def classify_for_signal(self, action: str, pct_change: Optional[float]) -> str:
        """
        Map a momentum reading to a signal-level classification.

        Parameters
        ----------
        action:
            "BUY" or "SELL"
        pct_change:
            The momentum percentage change (can be None).

        Returns
        -------
        "aligned" | "late" | "contrarian" | "neutral"
        """
        if pct_change is None:
            return "neutral"

        flag = self._flag_from_pct(pct_change)

        action = action.upper()

        if action == "BUY":
            if flag in ("trending_up", "late_bull"):
                return "late"          # price already ran up; entry is late
            if flag in ("trending_down", "late_bear"):
                return "contrarian"    # buying into weakness — possible value play
            return "aligned"           # neutral momentum → no conflict

        if action == "SELL":
            if flag in ("trending_down", "late_bear"):
                return "late"          # price already fell; exit is late
            if flag in ("trending_up", "late_bull"):
                return "contrarian"    # selling into strength — against momentum
            return "aligned"

        # Unknown action
        return "neutral"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_single(self, ticker: str, days: int) -> dict:
        """
        Download price history for one ticker and compute pct_change.

        We request ``days + 5`` calendar days to ensure we have at least
        ``days`` trading-day rows even around weekends / holidays.
        """
        fetch_days = days + 5
        try:
            hist = yf.Ticker(ticker).history(period=f"{fetch_days}d")

            if hist is None or hist.empty:
                logger.debug("No price history returned for %s", ticker)
                return {"pct_change": None, "flag": "neutral"}

            closes = hist["Close"].dropna()

            if len(closes) < 2:
                logger.debug("Insufficient price rows for %s (%d rows)", ticker, len(closes))
                return {"pct_change": None, "flag": "neutral"}

            # Use at most the last `days` trading-day rows
            available = min(len(closes) - 1, days)
            last_close = float(closes.iloc[-1])
            ref_close = float(closes.iloc[-(available + 1)])

            if ref_close == 0:
                return {"pct_change": None, "flag": "neutral"}

            pct_change = (last_close - ref_close) / ref_close * 100.0
            flag = self._flag_from_pct(pct_change)

            logger.debug(
                "%s: last=%.2f ref=%.2f pct=%.2f%% flag=%s",
                ticker, last_close, ref_close, pct_change, flag,
            )
            return {"pct_change": round(pct_change, 4), "flag": flag}

        except Exception as exc:
            logger.warning("Error fetching momentum for %s: %s", ticker, exc)
            return {"pct_change": None, "flag": "neutral"}

    def _flag_from_pct(self, pct_change: float) -> str:
        """
        Convert a raw percentage change to a momentum flag string.

        Thresholds:
            |pct| < 3         → "neutral"
            3 <= pct <= 5     → "trending_up"
            pct > 5           → "late_bull"
            -5 <= pct <= -3   → "trending_down"
            pct < -5          → "late_bear"
        """
        if abs(pct_change) < self.MILD_THRESHOLD:
            return "neutral"
        if pct_change > self.STRONG_THRESHOLD:
            return "late_bull"
        if pct_change < -self.STRONG_THRESHOLD:
            return "late_bear"
        if pct_change >= self.MILD_THRESHOLD:
            return "trending_up"
        # pct_change <= -MILD_THRESHOLD
        return "trending_down"
