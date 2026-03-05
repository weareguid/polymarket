"""
Logging configuration for Polymarket Investment Adviser.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

from .config import config


def setup_logger(name: str = "polymarket") -> logging.Logger:
    """
    Set up and return a configured logger.

    Args:
        name: Logger name

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.log_level.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    # File handler (optional)
    log_dir = config.project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(
        log_dir / f"polymarket_{datetime.now().strftime('%Y%m%d')}.log"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Default logger
logger = setup_logger()
