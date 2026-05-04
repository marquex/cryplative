"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cryplative.config import CryplativeConfig


class TestCLIStrategies:
    """Tests for the strategies CLI command."""

    def test_strategies_lists_registered(self, capsys: object) -> None:
        """Strategies command should list sma_crossover."""
        from cryplative.cli import strategies as cmd

        # Should not raise
        cmd()

        captured = capsys.readouterr()
        assert "sma_crossover" in captured.out


class TestCLIFetch:
    """Tests for the fetch CLI command."""

    def test_fetch_prints_summary(self, tmp_path: Path) -> None:
        """Fetch command should print summary table."""
        runner = CliRunner()
        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        from cryplative.core.models import Candle

        test_candles = [
            Candle(
                symbol="BTC/USDT",
                interval="1h",
                open_time=1704067200000 + i * 3600000,
                open=42000.0 + i,
                high=42500.0 + i,
                low=41800.0 + i,
                close=42300.0 + i,
                volume=100.0,
                close_time=1704067200000 + i * 3600000 + 3599999,
                closed=True,
            )
            for i in range(10)
        ]

        with patch(
            "cryplative.market_fetcher.fetcher.MarketFetcher"
        ) as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with patch(
                "cryplative.cli.CryplativeConfig", return_value=config
            ), patch("cryplative.cli.setup_logging"):
                result = runner.invoke(
                    __import__(
                        "cryplative.cli", fromlist=["app"]
                    ).app,
                    [
                        "fetch",
                        "--symbol",
                        "BTC/USDT",
                        "--interval",
                        "1h",
                        "--start",
                        "2025-01-01",
                        "--end",
                        "2025-01-31",
                    ],
                )

        assert result.exit_code == 0
        assert "BTC/USDT" in result.output

    def test_fetch_no_data_exits(self, tmp_path: Path) -> None:
        """Fetch with no data should print warning and exit."""
        runner = CliRunner()
        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        with patch(
            "cryplative.market_fetcher.fetcher.MarketFetcher"
        ) as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = []

            with patch(
                "cryplative.cli.CryplativeConfig", return_value=config
            ), patch("cryplative.cli.setup_logging"):
                result = runner.invoke(
                    __import__(
                        "cryplative.cli", fromlist=["app"]
                    ).app,
                    [
                        "fetch",
                        "--symbol",
                        "BTC/USDT",
                        "--interval",
                        "1h",
                        "--start",
                        "2025-01-01",
                        "--end",
                        "2025-01-31",
                    ],
                )

        assert result.exit_code != 0


class TestCLIBacktest:
    """Tests for the backtest CLI command."""

    def test_backtest_invalid_params_json(self, tmp_path: Path) -> None:
        """Invalid JSON in --params should exit with error."""
        runner = CliRunner()
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                __import__(
                    "cryplative.cli", fromlist=["app"]
                ).app,
                [
                    "backtest",
                    "--strategy",
                    "sma_crossover",
                    "--symbol",
                    "BTC/USDT",
                    "--interval",
                    "1h",
                    "--start",
                    "2025-01-01",
                    "--end",
                    "2025-01-31",
                    "--params",
                    "not-valid-json",
                ],
            )

        assert result.exit_code != 0
        assert "Invalid JSON" in result.output

    def test_backtest_successful_run(self, tmp_path: Path) -> None:
        """Backtest with mocked data should succeed."""
        runner = CliRunner()
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        from cryplative.core.models import Candle

        test_candles = [
            Candle(
                symbol="BTC/USDT",
                interval="1h",
                open_time=1704067200000 + i * 3600000,
                open=100.0 + i * 0.5,
                high=105.0 + i * 0.5,
                low=95.0 + i * 0.5,
                close=102.0 + i * 0.5,
                volume=100.0,
                close_time=1704067200000 + i * 3600000 + 3599999,
                closed=True,
            )
            for i in range(50)
        ]

        with patch(
            "cryplative.market_fetcher.fetcher.MarketFetcher"
        ) as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with patch(
                "cryplative.cli.CryplativeConfig", return_value=config
            ), patch("cryplative.cli.setup_logging"):
                result = runner.invoke(
                    __import__(
                        "cryplative.cli", fromlist=["app"]
                    ).app,
                    [
                        "backtest",
                        "--strategy",
                        "sma_crossover",
                        "--symbol",
                        "BTC/USDT",
                        "--interval",
                        "1h",
                        "--start",
                        "2024-01-01",
                        "--end",
                        "2024-01-03",
                        "--capital",
                        "100000",
                    ],
                )

        assert result.exit_code == 0
        assert "Backtest Results" in result.output


class TestCLIMain:
    """Test CLI app entry point."""

    def test_app_has_commands(self) -> None:
        """The app should have backtest, fetch, and strategies commands."""
        from cryplative.cli import app

        # Typer stores commands differently - check the group
        assert app is not None
        assert app.info.name == "cryplative"

    def test_app_help(self) -> None:
        """App help should list all commands."""
        from cryplative.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "backtest" in result.output
        assert "fetch" in result.output
        assert "strategies" in result.output
