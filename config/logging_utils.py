"""
config/logging_utils.py
───────────────────────
Standardized logging configuration for the RentalTruth system.
"""

import logging
import sys
from typing import Optional
from config.settings import config

def setup_logging(
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    console: bool = True
) -> None:
    """Sets up a standardized logging configuration."""
    log_level = level or config.LOG_LEVEL
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    log_format = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    formatter = logging.Formatter(log_format)

    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, mode="a")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Suppress noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("elasticsearch").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
