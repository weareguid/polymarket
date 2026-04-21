"""
Signal Decorrelation Layer.

When multiple signals fire on the same day, this module:
1. Fetches 90-day rolling price history for all tickers
2. Computes a correlation matrix
3. Clusters tickers with |corr| > threshold (default 0.7) via union-find
4. Within each cluster, keeps only the highest-conviction signal
5. Returns the kept signals + metadata about suppressed clusters

Usage:
    from src.predictor.decorrelator import decorrelate_signals

    kept, clusters = decorrelate_signals(inv_signals)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sector / theme labels — used when inferring a cluster's underlying factor
# ---------------------------------------------------------------------------
_THEME_MAP: Dict[str, List[str]] = {
    "Crypto":          ["MSTR", "GBTC", "COIN", "BTC-USD", "ETH-USD", "IBIT", "BITO", "HOOD"],
    "Energy":          ["XLE", "USO", "CVX", "XOM", "OXY", "COP", "SLB", "HAL", "PSX", "MPC", "VLO"],
    "Defense/Aero":    ["LMT", "RTX", "NOC", "GD", "BA", "ITA", "KTOS", "PLTR", "CACI"],
    "Rates/Bonds":     ["TLT", "IEF", "SHY", "AGG", "BND", "TMF", "TBT", "VGLT"],
    "Financials":      ["JPM", "GS", "BAC", "MS", "C", "WFC", "BRK-B", "AXP", "V", "MA"],
    "Tech/AI":         ["NVDA", "AMD", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "AAPL", "AVGO", "ARM"],
    "Healthcare":      ["UNH", "CVS", "HUM", "ELV", "CI", "HCA", "JNJ", "LLY", "MRK", "PFE"],
    "Materials/Gold":  ["GLD", "SLV", "GDX", "NEM", "FCX", "AA", "X", "NUE"],
    "Real Estate":     ["VNQ", "XLRE", "AMT", "PLD", "SPG", "O"],
    "Utilities":       ["XLU", "NEE", "DUK", "SO", "AEP", "EXC"],
    "Consumer":        ["XLY", "AMZN", "HD", "MCD", "NKE", "SBUX", "TGT", "WMT", "COST"],
}


def _infer_theme(tickers: List[str]) -> str:
    """Return the best-matching sector label for a cluster of tickers."""
    best_theme = "Multi-Factor"
    best_count = 0
    for theme, members in _THEME_MAP.items():
        count = sum(1 for t in tickers if t.upper() in members)
        if count > best_count:
            best_count = count
            best_theme = theme
    return best_theme


def _union_find_clusters(
    tickers: List[str],
    corr_matrix,
    threshold: float,
) -> List[List[str]]:
    """Group tickers into clusters where |pairwise corr| > threshold."""
    parent = {t: t for t in tickers}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, t1 in enumerate(tickers):
        for t2 in tickers[i + 1:]:
            if t1 in corr_matrix.index and t2 in corr_matrix.columns:
                try:
                    c = corr_matrix.loc[t1, t2]
                    if abs(c) > threshold:   # |corr| catches inverse factor exposure too
                        union(t1, t2)
                except Exception:
                    pass

    groups: Dict[str, List[str]] = {}
    for t in tickers:
        root = find(t)
        groups.setdefault(root, []).append(t)
    return list(groups.values())


def _fetch_corr_matrix(tickers: List[str], lookback_days: int = 100):
    """
    Download price history and return a pandas correlation matrix.
    Returns None on failure (decorrelation is best-effort).
    """
    try:
        import yfinance as yf
        import pandas as pd

        end   = datetime.today()
        start = end - timedelta(days=lookback_days)

        if len(tickers) == 1:
            return None

        raw = yf.download(
            tickers,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )

        # Handle multi-index (multiple tickers) vs single-ticker flat frame
        if hasattr(raw.columns, "levels"):
            close = raw["Close"]
        else:
            close = raw[["Close"]]
            close.columns = tickers

        # Drop tickers with < 30 days of data
        close = close.dropna(axis=1, thresh=30)
        if close.shape[1] < 2:
            return None

        returns = close.pct_change().dropna()
        corr    = returns.corr()
        return corr

    except Exception as exc:
        logger.warning("Correlation fetch failed: %s", exc)
        return None


def decorrelate_signals(
    signals: list,
    lookback_days: int = 90,
    corr_threshold: float = 0.70,
) -> Tuple[list, List[dict]]:
    """
    Parameters
    ----------
    signals       : list of InvestmentSignal (or any object with .ticker, .confidence)
    lookback_days : rolling window for correlation
    corr_threshold: |corr| above which two tickers are treated as the same factor

    Returns
    -------
    kept       : signals to surface (one per cluster + singletons)
    suppressed : list of dicts describing each collapsed cluster
                 { theme, leader_ticker, suppressed_tickers, avg_corr, n }
    """
    if len(signals) <= 1:
        return signals, []

    # Build a map: ticker → best signal (highest confidence)
    signal_map: Dict[str, object] = {}
    for s in signals:
        ticker = s.ticker
        if ticker not in signal_map or s.confidence > signal_map[ticker].confidence:
            signal_map[ticker] = s

    unique_tickers = list(signal_map.keys())

    logger.info("Decorrelating %d unique tickers (threshold=%.2f)…", len(unique_tickers), corr_threshold)

    corr_matrix = _fetch_corr_matrix(unique_tickers, lookback_days)

    if corr_matrix is None:
        logger.info("Correlation matrix unavailable — returning all signals unchanged")
        return signals, []

    clusters = _union_find_clusters(unique_tickers, corr_matrix, corr_threshold)

    kept       = []
    suppressed = []

    for cluster in clusters:
        cluster_sigs = [signal_map[t] for t in cluster if t in signal_map]
        if not cluster_sigs:
            continue

        # Always keep singletons untouched
        if len(cluster_sigs) == 1:
            kept.append(cluster_sigs[0])
            continue

        # Leader = highest confidence in cluster
        leader = max(cluster_sigs, key=lambda s: s.confidence)
        others = [s for s in cluster_sigs if s.ticker != leader.ticker]

        kept.append(leader)

        # Compute average pairwise correlation for reporting
        pairs = []
        for i, t1 in enumerate(cluster):
            for t2 in cluster[i + 1:]:
                if t1 in corr_matrix.index and t2 in corr_matrix.columns:
                    try:
                        pairs.append(abs(corr_matrix.loc[t1, t2]))
                    except Exception:
                        pass
        avg_corr = round(sum(pairs) / len(pairs), 2) if pairs else 0.0

        theme = _infer_theme(cluster)
        suppressed.append({
            "theme":              theme,
            "leader_ticker":      leader.ticker,
            "leader_name":        getattr(leader, "instrument_name", leader.ticker),
            "leader_confidence":  round(leader.confidence, 2),
            "suppressed_tickers": [s.ticker for s in others],
            "avg_corr":           avg_corr,
            "n":                  len(cluster),
        })

        logger.info(
            "Cluster [%s]: kept %s (conf=%.2f), suppressed %s (avg_corr=%.2f)",
            theme, leader.ticker, leader.confidence,
            [s.ticker for s in others], avg_corr,
        )

    logger.info(
        "Decorrelation complete: %d in → %d kept, %d suppressed across %d clusters",
        len(signals), len(kept),
        sum(len(c["suppressed_tickers"]) for c in suppressed),
        len(suppressed),
    )

    return kept, suppressed
