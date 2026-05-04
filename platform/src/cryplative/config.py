"""Configuration and logging setup for Cryplative."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Literal

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_project_root() -> Path:
    """Walk up from this file to find the project root.

    The project root is identified by the presence of CLAUDE.md.
    Falls back to the directory containing this file's grandparent
    (i.e. platform/) if CLAUDE.md is not found above.
    """
    current = Path(__file__).resolve()
    # Walk up the directory tree
    for parent in [current] + list(current.parents):
        if (parent / "CLAUDE.md").exists():
            return parent
    # Fallback: the platform/ directory itself
    return Path(__file__).resolve().parent.parent.parent


class CryplativeConfig(BaseSettings):
    """Application configuration loaded from environment variables with defaults."""

    # Exchange
    exchange_id: str = "binance"
    binance_api_key: str = ""
    binance_api_secret: str = ""

    # Data paths
    data_dir: str = "data"
    market_cache_dir: str = "data/market_cache"
    strategy_results_dir: str = "data/strategy_results"

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"

    model_config = SettingsConfigDict(
        env_prefix="CRYPLATIVE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    def resolve_data_dir(self) -> Path:
        """Return the data directory resolved relative to the project root."""
        root = get_project_root()
        return root / self.data_dir

    def resolve_market_cache_dir(self) -> Path:
        """Return the market cache directory resolved relative to the project root."""
        root = get_project_root()
        return root / self.market_cache_dir

    def resolve_strategy_results_dir(self) -> Path:
        """Return the strategy results directory resolved relative to the project root."""
        root = get_project_root()
        return root / self.strategy_results_dir


def setup_logging(config: CryplativeConfig) -> None:
    """Configure structlog based on the application config.

    - JSON output when log_format == "json"
    - Console (colored) output when log_format == "console"
    """
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if config.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)
