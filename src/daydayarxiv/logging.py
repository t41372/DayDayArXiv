"""Logging configuration using loguru."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def configure_logging(log_level: str, log_dir: Path) -> None:
    """Configure loguru handlers."""
    logger.remove()

    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
        level=log_level,
    )

    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "daydayarxiv_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level="DEBUG",
        compression="zip",
    )
