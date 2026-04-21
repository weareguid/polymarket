"""
Signal Calibration Logger.

Answers the question: "Does 71% confidence actually outperform 64% confidence?"

For every BUY/SELL signal generated, we log:
    signal_date, ticker, action, confidence, entry_price

Then, on each subsequent dashboard run, we fill in forward returns at:
    1w (7d), 1m (30d), 3m (90d), 6m (180d)

A calibration curve is built by bucketing signals by confidence and computing
actual win rates and average returns at each horizon.

Storage: data/signal_log/calibration_log.json
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_ROOT        = Path(__file__).parent.parent.parent
_LOG_DIR     = _ROOT / "data" / "signal_log"
_LOG_FILE    = _LOG_DIR / "calibration_log.json"

# Forward-return horizons in calendar days
_HORIZONS = {"1w": 7, "1m": 30, "3m": 90, "6m": 180}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load() -> List[dict]:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not _LOG_FILE.exists():
        return []
    try:
        raw = _LOG_FILE.read_text(encoding="utf-8").strip()
        return json.loads(raw) if raw else []
    except Exception as exc:
        logger.error("Failed to load calibration log: %s", exc)
        return []


def _save(records: List[dict]) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _LOG_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(records, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        tmp.replace(_LOG_FILE)
    except Exception as exc:
        logger.error("Failed to save calibration log: %s", exc)
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Log a new signal
# ---------------------------------------------------------------------------

def log_signal(
    ticker: str,
    action: str,
    confidence: float,
    entry_price: float,
    signal_date: Optional[str] = None,
    instrument_name: str = "",
    source_market: str = "",
) -> bool:
    """
    Append a new signal to the calibration log.
    Skips if an entry with the same id already exists (idempotent).

    Returns True if a new record was added, False if it was a duplicate.
    """
    today    = signal_date or date.today().isoformat()
    entry_id = f"{ticker}_{today}_{action}"

    records = _load()
    existing_ids = {r["id"] for r in records}
    if entry_id in existing_ids:
        return False

    # Pre-compute target dates for each horizon
    base = date.fromisoformat(today)
    target_dates = {
        label: (base + timedelta(days=days)).isoformat()
        for label, days in _HORIZONS.items()
    }

    record: dict = {
        "id":              entry_id,
        "ticker":          ticker,
        "instrument_name": instrument_name,
        "action":          action.upper(),
        "confidence":      round(float(confidence), 4),
        "entry_price":     round(float(entry_price), 4),
        "signal_date":     today,
        "target_dates":    target_dates,
        "returns":         {label: None for label in _HORIZONS},
        "wins":            {label: None for label in _HORIZONS},
        "source_market":   source_market,
        "logged_at":       datetime.utcnow().isoformat(),
    }

    records.append(record)
    _save(records)
    logger.info("Calibration: logged %s %s conf=%.2f @ %.4f", action, ticker, confidence, entry_price)
    return True


# ---------------------------------------------------------------------------
# Fill forward returns for due signals
# ---------------------------------------------------------------------------

def update_forward_returns() -> int:
    """
    For each record where a horizon's target_date <= today and return is still None,
    fetch the current price and compute the return.

    Returns number of returns filled.
    """
    records = _load()
    if not records:
        return 0

    today_str = date.today().isoformat()

    # Gather tickers that need price updates
    due: Dict[str, List[tuple]] = {}   # ticker → [(record_idx, label), ...]
    for idx, rec in enumerate(records):
        for label, target in rec.get("target_dates", {}).items():
            if rec["returns"].get(label) is None and target <= today_str:
                due.setdefault(rec["ticker"], []).append((idx, label))

    if not due:
        return 0

    # Fetch prices in batch
    try:
        import yfinance as yf
        tickers_list = list(due.keys())
        raw = yf.download(
            tickers_list,
            period="2d",
            auto_adjust=True,
            progress=False,
        )
        if hasattr(raw.columns, "levels"):
            prices = raw["Close"].iloc[-1].to_dict()
        else:
            prices = {tickers_list[0]: float(raw["Close"].iloc[-1])}
    except Exception as exc:
        logger.warning("Price fetch for calibration update failed: %s", exc)
        return 0

    filled = 0
    for ticker, jobs in due.items():
        cur_price = prices.get(ticker)
        if cur_price is None or cur_price != cur_price:  # NaN check
            continue
        for idx, label in jobs:
            rec        = records[idx]
            entry      = rec["entry_price"]
            if entry <= 0:
                continue
            ret_pct    = round((float(cur_price) - entry) / entry * 100, 4)
            direction  = rec["action"]   # "BUY" or "SELL"
            # Win = price went up for BUY, down for SELL
            win = (ret_pct > 0) if direction == "BUY" else (ret_pct < 0)
            rec["returns"][label] = ret_pct
            rec["wins"][label]    = win
            filled += 1

    if filled:
        _save(records)
        logger.info("Calibration: filled %d forward returns", filled)

    return filled


# ---------------------------------------------------------------------------
# Calibration statistics
# ---------------------------------------------------------------------------

_CONF_BUCKETS = [
    (0.50, 0.60, "50–60%"),
    (0.60, 0.70, "60–70%"),
    (0.70, 0.80, "70–80%"),
    (0.80, 0.90, "80–90%"),
    (0.90, 1.01, "90%+"),
]


def get_calibration_stats() -> dict:
    """
    Build a calibration table:
        per confidence bucket × horizon → {n, win_rate, avg_return}

    Returns:
        {
          "total_signals": int,
          "oldest_signal": str,
          "buckets": [
              {
                "label": "70–80%",
                "total": 12,
                "horizons": {
                    "1w": {"n": 8, "win_rate": 0.625, "avg_return": 1.3},
                    ...
                }
              }, ...
          ]
        }
    """
    records = _load()
    total   = len(records)
    oldest  = min((r["signal_date"] for r in records), default="—")

    bucket_stats = []
    for lo, hi, label in _CONF_BUCKETS:
        bucket_records = [
            r for r in records
            if lo <= r["confidence"] < hi and r["action"] in ("BUY", "SELL")
        ]
        horizons: dict = {}
        for h in _HORIZONS:
            wins    = [r["wins"][h] for r in bucket_records if r["wins"].get(h) is not None]
            returns = [r["returns"][h] for r in bucket_records if r["returns"].get(h) is not None]
            if wins:
                horizons[h] = {
                    "n":          len(wins),
                    "win_rate":   round(sum(wins) / len(wins), 3),
                    "avg_return": round(sum(returns) / len(returns), 2),
                }
            else:
                horizons[h] = {"n": 0, "win_rate": None, "avg_return": None}

        bucket_stats.append({
            "label":    label,
            "total":    len(bucket_records),
            "horizons": horizons,
        })

    return {
        "total_signals": total,
        "oldest_signal": oldest,
        "buckets": bucket_stats,
    }
