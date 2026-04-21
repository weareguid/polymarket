"""
PaperTradeResolver — checks open paper trades against Polymarket resolutions
and marks them as closed (or expired) with final P&L calculations.
"""
import logging
from datetime import date, datetime
from typing import List, Optional, Tuple

from src.paper_trading.models import PaperTrade

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]
    logger.warning("yfinance not installed — exit prices will default to entry price")


class PaperTradeResolver:
    """
    Iterates over open PaperTrades and resolves them against Polymarket
    market outcomes plus live equity prices.

    Parameters
    ----------
    client:
        An instance of PolymarketClient (or compatible duck-type).  If None,
        resolution checks that require market look-ups are skipped.
    """

    def __init__(self, client=None) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_resolutions(
        self, open_trades: List[PaperTrade]
    ) -> Tuple[List[PaperTrade], List[PaperTrade]]:
        """
        Evaluate each open trade for resolution or expiry.

        Returns
        -------
        (still_open, newly_closed)
            still_open  — trades that remain unresolved.
            newly_closed — trades that were just closed / expired this run.
        """
        still_open: List[PaperTrade] = []
        newly_closed: List[PaperTrade] = []

        for trade in open_trades:
            if trade.status != "open":
                still_open.append(trade)
                continue

            # --- Check Polymarket resolution ---
            resolution = self._find_resolution(trade)

            if resolution is not None:
                resolved_yes, current_price = resolution
                closed_trade = self._close_trade(trade, current_price, resolved_yes, "closed")
                newly_closed.append(closed_trade)
                logger.info(
                    "Resolved: %s → pm_yes=%s price_move=%.2f%% outcome=%s",
                    trade.id, resolved_yes, closed_trade.price_move_pct, closed_trade.outcome,
                )
                continue

            # --- Check expiry by days_to_resolution ---
            if self._is_expired(trade):
                current_price = self._fetch_current_price(trade.ticker, trade.entry_price)
                expired_trade = self._close_trade(trade, current_price, None, "expired")
                newly_closed.append(expired_trade)
                logger.info(
                    "Expired: %s | price_move=%.2f%%",
                    trade.id, expired_trade.price_move_pct,
                )
                continue

            still_open.append(trade)

        return still_open, newly_closed

    # ------------------------------------------------------------------
    # Resolution detection
    # ------------------------------------------------------------------

    def _find_resolution(
        self, trade: PaperTrade
    ) -> Optional[Tuple[bool, float]]:
        """
        Attempt to determine whether the Polymarket market linked to *trade*
        has resolved.

        Returns
        -------
        (resolved_yes: bool, current_price: float) if resolved, else None.
        """
        if self._client is None:
            logger.debug("No PolymarketClient — skipping resolution check for %s", trade.id)
            return None

        try:
            # --- Strategy 1: direct market lookup by URL slug ---
            market = self._fetch_market_direct(trade)
            if market is not None:
                result = self._extract_resolution(market)
                if result is not None:
                    resolved_yes, yes_price = result
                    current_price = self._fetch_current_price(trade.ticker, trade.entry_price)
                    return resolved_yes, current_price

            # --- Strategy 2: search closed markets ---
            market = self._search_closed_markets(trade)
            if market is not None:
                result = self._extract_resolution(market)
                if result is not None:
                    resolved_yes, yes_price = result
                    current_price = self._fetch_current_price(trade.ticker, trade.entry_price)
                    return resolved_yes, current_price

        except Exception as exc:
            logger.warning("Resolution check failed for %s: %s", trade.id, exc)

        return None

    def _fetch_market_direct(self, trade: PaperTrade):
        """
        Try to fetch the market directly using the stored URL / ID.
        Returns a market object or None.
        """
        if not trade.pm_market_url:
            return None
        try:
            # Extract the market id / slug from the URL if possible.
            # Polymarket URLs: https://polymarket.com/event/{slug}
            parts = trade.pm_market_url.rstrip("/").split("/")
            if parts:
                slug = parts[-1]
                market = self._client.get_market(slug)
                return market
        except Exception as exc:
            logger.debug("Direct market fetch failed for %s: %s", trade.id, exc)
        return None

    def _search_closed_markets(self, trade: PaperTrade):
        """
        Search closed markets for one whose question matches trade.pm_market.
        Returns the first matching market object or None.
        """
        if not trade.pm_market:
            return None
        try:
            markets = self._client.get_markets(closed=True, limit=200)
            if not markets:
                return None

            needle = trade.pm_market[:60].lower()
            for m in markets:
                question = ""
                if hasattr(m, "question"):
                    question = (m.question or "").lower()
                elif isinstance(m, dict):
                    question = (m.get("question", "") or "").lower()

                if needle in question:
                    return m

        except Exception as exc:
            logger.debug("Closed-market search failed for %s: %s", trade.id, exc)
        return None

    def _extract_resolution(self, market) -> Optional[Tuple[bool, float]]:
        """
        Given a market object (dataclass or dict), determine if it has resolved
        and extract the YES outcome.

        A market is considered resolved when the YES price is ~1.0 or ~0.0
        (i.e. not the ambiguous ~0.5 pre-resolution state).

        Returns (resolved_yes, yes_price) or None if not yet resolved.
        """
        yes_price: Optional[float] = None

        # Support both dict-like and attribute-like market objects
        if isinstance(market, dict):
            # Try common field names
            yes_price = (
                market.get("outcomePrices", {}).get("YES")
                or market.get("outcome_prices", {}).get("YES")
                or market.get("yes_price")
            )
            if yes_price is None:
                tokens = market.get("tokens", [])
                for token in tokens:
                    if isinstance(token, dict) and token.get("outcome", "").upper() == "YES":
                        yes_price = token.get("price")
                        break
        else:
            # Attribute access
            for attr in ("outcome_prices", "outcomePrices"):
                op = getattr(market, attr, None)
                if op:
                    if isinstance(op, dict):
                        yes_price = op.get("YES")
                    break
            if yes_price is None:
                yes_price = getattr(market, "yes_price", None)

        if yes_price is None:
            return None

        try:
            yes_price_f = float(yes_price)
        except (TypeError, ValueError):
            return None

        # Resolved YES: price converged to ~1.0
        if yes_price_f >= 0.95:
            return True, yes_price_f
        # Resolved NO: price converged to ~0.0
        if yes_price_f <= 0.05:
            return False, yes_price_f

        # Still unresolved (ambiguous mid-range price)
        return None

    # ------------------------------------------------------------------
    # Expiry check
    # ------------------------------------------------------------------

    def _is_expired(self, trade: PaperTrade) -> bool:
        """
        Return True if days_to_resolution was set and we are past that date.
        """
        if trade.days_to_resolution < 0:
            return False
        try:
            entry = datetime.strptime(trade.entry_date, "%Y-%m-%d").date()
            deadline = entry
            from datetime import timedelta
            deadline = entry + timedelta(days=trade.days_to_resolution)
            return date.today() > deadline
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Trade closing
    # ------------------------------------------------------------------

    def _close_trade(
        self,
        trade: PaperTrade,
        exit_price: float,
        resolved_yes: Optional[bool],
        status: str,
    ) -> PaperTrade:
        """
        Return a *new* PaperTrade with exit fields filled in.
        """
        price_move_pct = 0.0
        if trade.entry_price and trade.entry_price != 0:
            price_move_pct = (exit_price - trade.entry_price) / trade.entry_price * 100.0

        outcome = self._determine_outcome(trade.action, resolved_yes, price_move_pct)

        import dataclasses
        closed = dataclasses.replace(
            trade,
            status=status,
            exit_price=round(exit_price, 4),
            exit_date=date.today().isoformat(),
            pm_resolved_yes=resolved_yes,
            price_move_pct=round(price_move_pct, 4),
            outcome=outcome,
        )
        return closed

    # ------------------------------------------------------------------
    # Outcome determination
    # ------------------------------------------------------------------

    @staticmethod
    def _determine_outcome(
        action: str,
        pm_resolved_yes: Optional[bool],
        price_move_pct: float,
    ) -> str:
        """
        Map trade action + Polymarket resolution + price move to a win/loss label.

        Rules
        -----
        Overriding rule: |price_move_pct| < 1 → "neutral" (negligible move).

        BUY trades:
          pm_resolved_yes=True  + price_move > 0  → "win"
          pm_resolved_yes=True  + price_move <= 0 → "loss"
          pm_resolved_yes=False                   → "loss" (thesis was wrong)

        SELL trades:
          pm_resolved_yes=False + price_move < 0  → "win"
          pm_resolved_yes=False + price_move >= 0 → "loss"
          pm_resolved_yes=True                    → "loss" (thesis was wrong)

        Expired / unknown resolution:
          Use price_move alone.
        """
        if abs(price_move_pct) < 1.0:
            return "neutral"

        action = action.upper()

        if pm_resolved_yes is None:
            # No market resolution — judge purely by price movement
            if action == "BUY":
                return "win" if price_move_pct > 0 else "loss"
            if action == "SELL":
                return "win" if price_move_pct < 0 else "loss"
            return "neutral"

        if action == "BUY":
            if pm_resolved_yes:
                return "win" if price_move_pct > 0 else "loss"
            return "loss"  # thesis was wrong — market resolved NO

        if action == "SELL":
            if not pm_resolved_yes:
                return "win" if price_move_pct < 0 else "loss"
            return "loss"  # thesis was wrong — market resolved YES

        return "neutral"

    # ------------------------------------------------------------------
    # Price fetching
    # ------------------------------------------------------------------

    def _fetch_current_price(self, ticker: str, fallback: float) -> float:
        """
        Fetch the most recent closing price for *ticker* via yfinance.
        Returns *fallback* if unavailable.
        """
        if yf is None:
            logger.debug("yfinance unavailable — using entry price as exit price for %s", ticker)
            return fallback
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if hist is not None and not hist.empty:
                return float(hist["Close"].dropna().iloc[-1])
        except Exception as exc:
            logger.warning("Could not fetch current price for %s: %s", ticker, exc)
        return fallback
