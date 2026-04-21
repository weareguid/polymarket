"""
PaperTrade dataclass model for paper trading records.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class PaperTrade:
    """
    Represents a single paper trade entry.

    id is composed as: {ticker}_{entry_date}_{action}
    action must be "BUY" or "SELL" (WATCH/HOLD are not logged)
    confirmation_score is 0-4: how many independent sources confirm the signal
    momentum_flag: "aligned", "late", "contrarian", "neutral"
    status: "open", "closed", "expired"
    outcome: "win", "loss", "neutral", or "" (empty while open)
    """

    # --- Identity ---
    id: str
    ticker: str
    instrument_name: str

    # --- Signal ---
    action: str                            # "BUY" or "SELL"
    entry_price: float
    entry_date: str                        # YYYY-MM-DD

    # --- Polymarket context ---
    pm_market: str                         # Market question text
    pm_market_url: str
    pm_yes_at_entry: float                 # YES price at time of signal (0–1)
    pm_volume_at_entry: float

    # --- Confidence / confirmation ---
    confidence: float                      # 0.0 – 1.0
    confirmation_score: int               # 0–4
    confirmation_sources: List[str]       # e.g. ["pm_probability", "newsletter", ...]

    # --- Momentum ---
    momentum_10d: float                   # % price change last 10 days (0.0 if unknown)
    momentum_flag: str                    # "aligned", "late", "contrarian", "neutral"

    # --- Timing ---
    days_to_resolution: int              # -1 if unknown

    # --- Lifecycle ---
    status: str                          # "open", "closed", "expired"

    # --- Position sizing ---
    usd_amount: float = 0.0                  # USD invested (0 = not specified)

    # --- Exit / resolution (filled in when closed) ---
    exit_price: float = 0.0
    exit_date: str = ""
    pm_resolved_yes: Optional[bool] = None   # None=unknown, True=YES, False=NO
    price_move_pct: float = 0.0              # (exit_price - entry_price) / entry_price * 100
    outcome: str = ""                        # "win", "loss", "neutral", ""
    notes: str = ""

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return all fields as a plain dict (JSON-serialisable)."""
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaperTrade":
        """
        Reconstruct a PaperTrade from a plain dict.

        Handles missing optional fields gracefully so that records written
        by older versions of the schema can still be loaded.
        """
        # Normalise pm_resolved_yes: JSON stores null / true / false
        pm_resolved_yes = data.get("pm_resolved_yes", None)
        if pm_resolved_yes is not None:
            pm_resolved_yes = bool(pm_resolved_yes)

        return cls(
            id=data["id"],
            ticker=data["ticker"],
            instrument_name=data.get("instrument_name", ""),
            action=data["action"],
            entry_price=float(data["entry_price"]),
            entry_date=data["entry_date"],
            pm_market=data.get("pm_market", ""),
            pm_market_url=data.get("pm_market_url", ""),
            pm_yes_at_entry=float(data.get("pm_yes_at_entry", 0.0)),
            pm_volume_at_entry=float(data.get("pm_volume_at_entry", 0.0)),
            confidence=float(data.get("confidence", 0.0)),
            confirmation_score=int(data.get("confirmation_score", 0)),
            confirmation_sources=list(data.get("confirmation_sources", [])),
            momentum_10d=float(data.get("momentum_10d", 0.0)),
            momentum_flag=data.get("momentum_flag", "neutral"),
            days_to_resolution=int(data.get("days_to_resolution", -1)),
            status=data.get("status", "open"),
            usd_amount=float(data.get("usd_amount", 0.0)),
            exit_price=float(data.get("exit_price", 0.0)),
            exit_date=data.get("exit_date", ""),
            pm_resolved_yes=pm_resolved_yes,
            price_move_pct=float(data.get("price_move_pct", 0.0)),
            outcome=data.get("outcome", ""),
            notes=data.get("notes", ""),
        )

    def __repr__(self) -> str:
        return (
            f"PaperTrade(id={self.id!r}, action={self.action!r}, "
            f"ticker={self.ticker!r}, status={self.status!r}, "
            f"confidence={self.confidence:.2f}, outcome={self.outcome!r})"
        )
