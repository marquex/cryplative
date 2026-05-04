"""Tests for configuration and logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from cryplative.config import CryplativeConfig, get_project_root, setup_logging


class TestCryplativeConfig:
    def test_default_values(self) -> None:
        config = CryplativeConfig()
        assert config.exchange_id == "binance"
        assert config.log_level == "INFO"
        assert config.log_format == "console"
        assert config.data_dir == "data"
        assert config.binance_api_key == ""
        assert config.binance_api_secret == ""

    def test_custom_values(self) -> None:
        config = CryplativeConfig(
            exchange_id="kraken",
            log_level="DEBUG",
            log_format="json",
        )
        assert config.exchange_id == "kraken"
        assert config.log_level == "DEBUG"
        assert config.log_format == "json"

    def test_resolve_data_dir(self, tmp_path: Path) -> None:
        config = CryplativeConfig(data_dir="test_data")
        result = config.resolve_data_dir()
        # Should be a Path under the project root
        assert isinstance(result, Path)
        assert result.name == "test_data"

    def test_resolve_market_cache_dir(self, tmp_path: Path) -> None:
        config = CryplativeConfig(market_cache_dir="test_cache")
        result = config.resolve_market_cache_dir()
        assert isinstance(result, Path)

    def test_resolve_strategy_results_dir(self, tmp_path: Path) -> None:
        config = CryplativeConfig(strategy_results_dir="test_results")
        result = config.resolve_strategy_results_dir()
        assert isinstance(result, Path)


class TestSetupLogging:
    def test_setup_console_logging(self) -> None:
        config = CryplativeConfig(log_format="console", log_level="DEBUG")
        setup_logging(config)

        # Verify root logger has a handler
        root = logging.getLogger()
        assert len(root.handlers) > 0

    def test_setup_json_logging(self) -> None:
        config = CryplativeConfig(log_format="json", log_level="WARNING")
        setup_logging(config)

        root = logging.getLogger()
        assert len(root.handlers) > 0
        assert root.level == logging.WARNING


class TestGetProjectRoot:
    def test_returns_path(self) -> None:
        root = get_project_root()
        assert isinstance(root, Path)
        assert root.exists()
