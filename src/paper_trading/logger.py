"""
PaperTradeLogger — persists paper trades to JSON files.

Open trades:   data/paper_trades/open_trades.json
Closed trades: data/paper_trades/closed_trades.json
"""
import json
import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from src.paper_trading.models import PaperTrade
from src.predictor.signal_generator import InvestmentSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default storage paths (resolved relative to project root)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent  # src/paper_trading/../../ → project root
_DATA_DIR = _PROJECT_ROOT / "data" / "paper_trades"
_DEFAULT_OPEN_FILE = _DATA_DIR / "open_trades.json"
_DEFAULT_CLOSED_FILE = _DATA_DIR / "closed_trades.json"


class PaperTradeLogger:
    """
    Manages persistence of paper trades across open and closed trade files.

    Usage
    -----
    ::

        logger = PaperTradeLogger()
        trade = logger.log_signal(signal, entry_price=142.50, ...)
        if trade:
            print(f"Logged: {trade.id}")
    """

    def __init__(self, trades_file: Optional[Path] = None) -> None:
        self._open_file: Path = trades_file or _DEFAULT_OPEN_FILE
        self._closed_file: Path = _DEFAULT_CLOSED_FILE

        # Ensure the storage directory exists
        self._open_file.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load helpers
    # ------------------------------------------------------------------

    def load_open_trades(self) -> List[PaperTrade]:
        """Load all open trades from disk."""
        return self._load_from_file(self._open_file)

    def load_closed_trades(self) -> List[PaperTrade]:
        """Load all closed/expired trades from disk."""
        return self._load_from_file(self._closed_file)

    # ------------------------------------------------------------------
    # Core logging entry point
    # ------------------------------------------------------------------

    def log_signal(
        self,
        signal: InvestmentSignal,
        entry_price: float,
        confirmation_score: int,
        confirmation_sources: List[str],
        momentum_10d: float,
        momentum_flag: str,
    ) -> Optional[PaperTrade]:
        """
        Convert an InvestmentSignal into a PaperTrade and persist it.

        Filtering rules
        ---------------
        * Only "BUY" or "SELL" actions are accepted (WATCH / HOLD are skipped).
        * signal.confidence must be >= 0.60.
        * confirmation_score must be >= 2.
        * If the same ticker already has an open trade dated today, skip.

        Returns
        -------
        The newly created PaperTrade, or None if the signal was filtered out.
        """
        action = (signal.action or "").upper()

        # --- Gate 1: action filter (also accept high-confidence WATCH for monitoring) ---
        if action not in ("BUY", "SELL", "WATCH"):
            logger.debug(
                "Skipping signal for %s — action %r is not BUY/SELL/WATCH",
                signal.ticker, action,
            )
            return None
        # WATCH signals need higher bar: confidence >= 0.75 and score >= 3
        if action == "WATCH" and (signal.confidence < 0.75 or confirmation_score < 3):
            logger.debug(
                "Skipping WATCH signal for %s — needs conf>=0.75 and score>=3",
                signal.ticker,
            )
            return None

        # --- Gate 2: confidence filter ---
        if action in ("BUY", "SELL") and signal.confidence < 0.60:
            logger.debug(
                "Skipping signal for %s — confidence %.2f < 0.60",
                signal.ticker, signal.confidence,
            )
            return None

        # --- Gate 3: confirmation score filter ---
        if action in ("BUY", "SELL") and confirmation_score < 2:
            logger.debug(
                "Skipping signal for %s — confirmation_score %d < 2",
                signal.ticker, confirmation_score,
            )
            return None

        today_str = date.today().isoformat()

        # --- Gate 4: duplicate check (any open position for this ticker) ---
        open_trades = self.load_open_trades()
        for existing in open_trades:
            if existing.ticker == signal.ticker:
                logger.info(
                    "Duplicate skipped: %s already has an open trade from %s",
                    signal.ticker, existing.entry_date,
                )
                return None

        # --- Build days_to_resolution ---
        days_to_resolution: int = -1
        if signal.days_to_event is not None and signal.days_to_event >= 0:
            days_to_resolution = int(signal.days_to_event)

        # --- Construct the trade id ---
        trade_id = f"{signal.ticker}_{today_str}_{action}"

        trade = PaperTrade(
            id=trade_id,
            ticker=signal.ticker,
            instrument_name=signal.instrument_name,
            action=action,
            entry_price=round(float(entry_price), 4),
            entry_date=today_str,
            pm_market=signal.source_market,
            pm_market_url=signal.market_url,
            pm_yes_at_entry=round(float(signal.yes_price), 4),
            pm_volume_at_entry=round(float(signal.volume_24h), 2),
            confidence=round(float(signal.confidence), 4),
            confirmation_score=confirmation_score,
            confirmation_sources=list(confirmation_sources),
            momentum_10d=round(float(momentum_10d), 4),
            momentum_flag=momentum_flag,
            days_to_resolution=days_to_resolution,
            status="open",
        )

        open_trades.append(trade)
        self.save_open_trades(open_trades)

        logger.info(
            "Paper trade logged: %s | %s @ %.4f | confidence=%.2f score=%d",
            trade_id, action, entry_price, signal.confidence, confirmation_score,
        )
        return trade

    # ------------------------------------------------------------------
    # Save helpers
    # ------------------------------------------------------------------

    def save_open_trades(self, trades: List[PaperTrade]) -> None:
        """Overwrite the open trades file with the supplied list."""
        self._save_to_file(self._open_file, trades)

    def save_closed_trades(self, trades: List[PaperTrade]) -> None:
        """Overwrite the closed trades file with the supplied list."""
        self._save_to_file(self._closed_file, trades)

    # ------------------------------------------------------------------
    # Internal I/O
    # ------------------------------------------------------------------

    def _load_from_file(self, path: Path) -> List[PaperTrade]:
        """Read a JSON array of trade dicts and deserialise to PaperTrade objects."""
        if not path.exists():
            return []
        try:
            raw = path.read_text(encoding="utf-8")
            if not raw.strip():
                return []
            records = json.loads(raw)
            if not isinstance(records, list):
                logger.error("Expected JSON array in %s, got %s", path, type(records))
                return []
            trades: List[PaperTrade] = []
            for rec in records:
                try:
                    trades.append(PaperTrade.from_dict(rec))
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("Skipping malformed trade record: %s — %s", rec, exc)
            return trades
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load trades from %s: %s", path, exc)
            return []

    def _save_to_file(self, path: Path, trades: List[PaperTrade]) -> None:
        """Serialise a list of PaperTrade objects to a JSON file (atomic write)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            [t.to_dict() for t in trades],
            indent=2,
            ensure_ascii=False,
            default=str,
        )
        # Write to a temp file first, then rename for atomicity
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(path)
        except OSError as exc:
            logger.error("Failed to write trades to %s: %s", path, exc)
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
