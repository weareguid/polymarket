"""Scraper module for Polymarket data collection."""
from .polymarket_client import PolymarketClient
from .trending_detector import TrendingDetector

__all__ = ["PolymarketClient", "TrendingDetector"]
