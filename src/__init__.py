"""Polymarket Investment Adviser - Main package."""
from .scraper import PolymarketClient, TrendingDetector
from .analyzer import MomentumAnalyzer, MarketClassifier
from .correlator import KnowledgeBase, StockCorrelator
from .predictor import TimingModel, SignalGenerator

__version__ = "0.1.0"

__all__ = [
    "PolymarketClient",
    "TrendingDetector",
    "MomentumAnalyzer",
    "MarketClassifier",
    "KnowledgeBase",
    "StockCorrelator",
    "TimingModel",
    "SignalGenerator",
]
