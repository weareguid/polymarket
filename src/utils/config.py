"""
Configuration module for Polymarket Investment Adviser.
"""
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class Config:
    """Main configuration class."""

    # Paths
    project_root: Path = Path(__file__).parent.parent.parent
    data_dir: Path = project_root / "data"
    raw_data_dir: Path = data_dir / "raw"
    processed_data_dir: Path = data_dir / "processed"
    models_dir: Path = data_dir / "models"

    # Polymarket API
    polymarket_base_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_api_key: Optional[str] = None

    # Scraper settings
    trending_volume_threshold: float = 10000  # USD min 24h volume
    trending_change_threshold: float = 0.05   # 5% price change
    max_markets_per_fetch: int = 100

    # Analyzer settings
    momentum_window_days: int = 7
    volume_spike_multiplier: float = 2.0  # 2x normal = spike

    # Correlator settings
    min_correlation_confidence: float = 0.6

    # Predictor settings
    min_days_to_event: int = 1
    max_days_to_event: int = 30
    confidence_threshold: float = 0.7

    # Logging
    log_level: str = "INFO"

    def __post_init__(self):
        """Load from environment variables if present."""
        self.polymarket_api_key = os.getenv("POLYMARKET_API_KEY")
        self.log_level = os.getenv("LOG_LEVEL", self.log_level)

        # Create directories if they don't exist
        for dir_path in [self.raw_data_dir, self.processed_data_dir, self.models_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()
