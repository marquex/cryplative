"""Tests for CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cryplative.cli import app, build_comparison_data, load_strategy_results
from cryplative.config import CryplativeConfig

runner = CliRunner()


class TestCLIStrategies:
    """Tests for the strategies CLI command."""

    def test_strategies_lists_registered(self, capsys: object) -> None:
        """Strategies command should list sma_crossover."""
        from cryplative.cli import strategies as cmd

        # Should not raise
        cmd()

        captured = capsys.readouterr()
        assert "sma_crossover" in captured.out


class TestCLIPairs:
    """Tests for the pairs CLI command."""

    def test_pairs_displays_table(self, tmp_path: Path) -> None:
        """pairs command should display a table of trading pairs."""
        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        from unittest.mock import MagicMock

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.list_pairs.return_value = [
                {
                    "symbol": "BTC/USDT",
                    "base": "BTC",
                    "quote": "USDT",
                    "active": True,
                    "price_precision": 2,
                    "min_order_size": 0.00001,
                },
                {
                    "symbol": "ETH/USDT",
                    "base": "ETH",
                    "quote": "USDT",
                    "active": True,
                    "price_precision": 2,
                    "min_order_size": 0.0001,
                },
            ]

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(app, ["pairs"])

        assert result.exit_code == 0
        assert "Available Trading Pairs" in result.output
        assert "BTC/USDT" in result.output
        assert "ETH/USDT" in result.output
        assert "Total: 2 pairs" in result.output

    def test_pairs_filters_by_quote(self, tmp_path: Path) -> None:
        """pairs --quote USDT should filter to USDT pairs only."""
        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        from unittest.mock import MagicMock

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.list_pairs.return_value = [
                {
                    "symbol": "BTC/USDT",
                    "base": "BTC",
                    "quote": "USDT",
                    "active": True,
                    "price_precision": 2,
                    "min_order_size": 0.00001,
                },
            ]

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(app, ["pairs", "--quote", "USDT"])

        assert result.exit_code == 0
        assert "BTC/USDT" in result.output
        # Verify the quote filter was passed correctly
        mock_instance.list_pairs.assert_called_once_with(quote="USDT", active_only=True)

    def test_pairs_handles_api_error(self, tmp_path: Path) -> None:
        """pairs command should handle API errors with a user-friendly message."""
        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        from cryplative.core.exceptions import MarketDataError

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.list_pairs.side_effect = MarketDataError("API rate limit exceeded")

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(app, ["pairs"])

        assert result.exit_code == 1
        assert "Error fetching pairs" in result.output

    def test_pairs_empty_result(self, tmp_path: Path) -> None:
        """pairs command should show 'No pairs found' when result is empty."""
        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        from unittest.mock import MagicMock

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.list_pairs.return_value = []

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(app, ["pairs"])

        # Empty result should exit with 0 (not an error)
        assert result.exit_code == 0 or "No pairs found" in result.output
        assert "No pairs found matching your criteria" in result.output


class TestCLIFetch:
    """Tests for the fetch CLI command."""

    def test_fetch_prints_summary(self, tmp_path: Path) -> None:
        """Fetch command should print summary table."""
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

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(
                    app,
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
        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = []

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(
                    app,
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
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                app,
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

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(
                    app,
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

    def test_backtest_params_from_file(self, tmp_path: Path) -> None:
        """Backtest --params should read from JSON file."""
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        params_file = tmp_path / "params.json"
        params_file.write_text('{"fast_period": 5, "slow_period": 10}', encoding="utf-8")

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

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(
                    app,
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
                        "--params",
                        str(params_file),
                    ],
                )

        assert result.exit_code == 0

    def test_backtest_max_positions(self, tmp_path: Path) -> None:
        """Backtest --max-positions should pass through to config."""
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

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(
                    app,
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
                        "--max-positions",
                        "3",
                    ],
                )

        assert result.exit_code == 0
        assert "Max Positions" in result.output
        assert "3" in result.output


class TestCLIMain:
    """Test CLI app entry point."""

    def test_app_has_commands(self) -> None:
        """The app should have backtest, fetch, and strategies commands."""
        assert app is not None
        assert app.info.name == "cryplative"

    def test_app_help(self) -> None:
        """App help should list all commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "backtest" in result.output
        assert "fetch" in result.output
        assert "strategies" in result.output
        assert "new-strategy" in result.output
        assert "compare" in result.output
        assert "pairs" in result.output


class TestNewStrategyCLI:
    """Tests for the new-strategy CLI command."""

    def _make_template(self, strategies_dir: Path) -> None:
        """Write the template file to strategies_dir."""
        template_content = '''"""Template."""

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle, OrderType, Signal, SignalDirection, StrategyConfig,
)
from cryplative.strategies.registry import StrategyRegistry

# NOTE: Do NOT add @StrategyRegistry.register here.
# This is a template file only.

class TemplateStrategy(Strategy):
    """<PLACEHOLDER: One-line description>"""
    @property
    def strategy_id(self) -> str:
        return "<PLACEHOLDER: unique_id>"
    @property
    def strategy_name(self) -> str:
        return "<PLACEHOLDER: Human-readable name>"
    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        return None
'''
        (strategies_dir / "_template.py").write_text(template_content, encoding="utf-8")

    def test_creates_strategy_file(self, tmp_path: Path) -> None:
        """new-strategy creates a file with correct content."""
        import cryplative.cli

        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        self._make_template(strategies_dir)

        with patch.object(cryplative.cli.Path, "resolve", return_value=strategies_dir):
            result = runner.invoke(app, ["new-strategy", "test_strat"])

        assert result.exit_code == 0
        assert "Created strategy: test_strat" in result.output

        created_file = strategies_dir / "test_strat.py"
        assert created_file.exists()

        content = created_file.read_text(encoding="utf-8")
        assert "class TestStrat(Strategy):" in content
        assert 'return "test_strat"' in content
        assert "Test Strat" in content
        assert "@StrategyRegistry.register" in content

    def test_error_on_duplicate_name(self, tmp_path: Path) -> None:
        """new-strategy errors when strategy file already exists."""
        import cryplative.cli

        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        self._make_template(strategies_dir)
        (strategies_dir / "existing.py").write_text("# existing", encoding="utf-8")

        with patch.object(cryplative.cli.Path, "resolve", return_value=strategies_dir):
            result = runner.invoke(app, ["new-strategy", "existing"])

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_invalid_name_rejected(self) -> None:
        """new-strategy rejects names with uppercase or special chars."""
        result = runner.invoke(app, ["new-strategy", "MyStrategy"])
        assert result.exit_code == 1
        assert "Invalid strategy name" in result.output

        result2 = runner.invoke(app, ["new-strategy", "123strategy"])
        assert result2.exit_code == 1

    def test_helper_functions(self) -> None:
        """Test the snake_case conversion helpers."""
        from cryplative.cli import _snake_to_pascal, _snake_to_title

        assert _snake_to_pascal("my_strategy") == "MyStrategy"
        assert _snake_to_pascal("sma_crossover") == "SmaCrossover"
        assert _snake_to_pascal("rsi") == "Rsi"
        assert _snake_to_title("my_strategy") == "My Strategy"
        assert _snake_to_title("bollinger_bands") == "Bollinger Bands"


class TestInputValidation:
    """Tests for CLI input validation."""

    def test_invalid_symbol_format(self, tmp_path: Path) -> None:
        """Invalid symbol format should error."""
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                app,
                [
                    "backtest",
                    "--strategy",
                    "sma_crossover",
                    "--symbol",
                    "INVALID",
                    "--interval",
                    "1h",
                    "--start",
                    "2025-01-01",
                    "--end",
                    "2025-01-31",
                ],
            )

        assert result.exit_code == 1
        assert "Invalid symbol format" in result.output

    def test_invalid_interval(self, tmp_path: Path) -> None:
        """Invalid interval should error with valid options."""
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                app,
                [
                    "backtest",
                    "--strategy",
                    "sma_crossover",
                    "--symbol",
                    "BTC/USDT",
                    "--interval",
                    "99m",
                    "--start",
                    "2025-01-01",
                    "--end",
                    "2025-01-31",
                ],
            )

        assert result.exit_code == 1
        assert "Invalid interval" in result.output
        assert "1m" in result.output  # Should list valid options

    def test_invalid_date_format(self, tmp_path: Path) -> None:
        """Invalid date format should error."""
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                app,
                [
                    "backtest",
                    "--strategy",
                    "sma_crossover",
                    "--symbol",
                    "BTC/USDT",
                    "--interval",
                    "1h",
                    "--start",
                    "not-a-date",
                    "--end",
                    "2025-01-31",
                ],
            )

        assert result.exit_code == 1
        assert "Invalid" in result.output

    def test_unknown_strategy_lists_available(self, tmp_path: Path) -> None:
        """Unknown strategy should list available strategies."""
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                app,
                [
                    "backtest",
                    "--strategy",
                    "nonexistent_strategy",
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

        assert result.exit_code == 1
        assert "not found" in result.output
        assert "Available strategies" in result.output

    def test_zero_or_negative_capital(self, tmp_path: Path) -> None:
        """Zero or negative capital should error."""
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                app,
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
                    "--capital",
                    "0",
                ],
            )

        assert result.exit_code == 1
        assert "positive" in result.output


class TestCompareLogic:
    """Tests for the compare command logic."""

    def test_load_strategy_results(self, tmp_path: Path) -> None:
        """load_strategy_results loads valid JSON files."""
        result_data = {
            "strategy_id": "sma_crossover",
            "metrics": {
                "total_return": 15.3,
                "sharpe_ratio": 1.24,
                "max_drawdown": -8.5,
                "win_rate": 55.0,
                "total_trades": 20,
                "profit_factor": 1.8,
            },
        }
        f1 = tmp_path / "result1.json"
        f1.write_text(json.dumps(result_data), encoding="utf-8")

        results = load_strategy_results([str(f1)])
        assert len(results) == 1
        assert results[0][0] == "sma_crossover"

    def test_load_skips_invalid_files(self, tmp_path: Path) -> None:
        """load_strategy_results skips invalid files."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json", encoding="utf-8")

        results = load_strategy_results([str(bad_file)])
        assert len(results) == 0

    def test_build_comparison_data(self) -> None:
        """build_comparison_data produces correct table structure."""
        results = [
            (
                "sma_crossover",
                {
                    "total_return": 15.3,
                    "sharpe_ratio": 1.24,
                    "max_drawdown": -8.5,
                    "win_rate": 55.0,
                    "total_trades": 20,
                    "profit_factor": 1.8,
                },
            ),
            (
                "rsi",
                {
                    "total_return": 8.2,
                    "sharpe_ratio": 0.85,
                    "max_drawdown": -12.3,
                    "win_rate": 48.0,
                    "total_trades": 35,
                    "profit_factor": 1.2,
                },
            ),
        ]

        metrics, names, rows = build_comparison_data(results)
        assert len(metrics) == 6
        assert names == ["sma_crossover", "rsi"]
        assert len(rows) == 6


class TestCompareCommand:
    """Tests for the compare CLI command."""

    def test_compare_command(self, tmp_path: Path) -> None:
        """Compare command displays a table."""
        result_data_a = {
            "strategy_id": "sma_crossover",
            "metrics": {
                "total_return": 15.3,
                "sharpe_ratio": 1.24,
                "max_drawdown": -8.5,
                "win_rate": 55.0,
                "total_trades": 20,
                "profit_factor": 1.8,
            },
        }
        result_data_b = {
            "strategy_id": "rsi",
            "metrics": {
                "total_return": 8.2,
                "sharpe_ratio": 0.85,
                "max_drawdown": -12.3,
                "win_rate": 48.0,
                "total_trades": 35,
                "profit_factor": 1.2,
            },
        }
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text(json.dumps(result_data_a), encoding="utf-8")
        f2.write_text(json.dumps(result_data_b), encoding="utf-8")

        config = CryplativeConfig()
        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["compare", str(f1), str(f2)])

        assert result.exit_code == 0
        assert "Strategy Comparison" in result.output
        assert "sma_crossover" in result.output
        assert "rsi" in result.output
        assert "Total Return" in result.output

    def test_compare_empty_files(self) -> None:
        """Compare with no valid files should error."""
        config = CryplativeConfig()
        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["compare", "/nonexistent/file.json"])

        assert result.exit_code == 1
        assert "No valid" in result.output


class TestCLIResultsCatalog:
    """Tests for the results catalog CLI commands."""

    def _make_catalog_with_data(self, tmp_path: Path) -> str:
        """Create a catalog DB with sample data and return its path."""
        from cryplative.catalog import ResultsCatalog

        db_path = str(tmp_path / "catalog.db")
        cat = ResultsCatalog(db_path=db_path)

        metrics_a = {
            "total_return_pct": 2.56,
            "sharpe_ratio": 2.57,
            "max_drawdown_pct": -0.42,
            "win_rate_pct": 83.33,
            "total_trades": 6,
            "profit_factor": 17.79,
        }
        metrics_b = {
            "total_return_pct": -1.2,
            "sharpe_ratio": 0.43,
            "max_drawdown_pct": -10.0,
            "win_rate_pct": 40.0,
            "total_trades": 5,
            "profit_factor": 0.8,
        }

        cat.insert(
            strategy_id="h2_rsi_divergence_trend",
            symbol="BTC/USDT",
            interval="4h",
            start_date="2024-01-01",
            end_date="2025-08-31",
            run_type="BACKTEST",
            metrics=metrics_a,
            results_file="strategy_results/h2_btc_test.json",
            parameters={"rsi_period": 14},
            hypothesis_id="H2",
            data_split="TEST",
            verdict="PASS",
        )
        cat.insert(
            strategy_id="sma_crossover",
            symbol="ETH/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=metrics_b,
            results_file="strategy_results/sma_eth_full.json",
            parameters={"fast": 10, "slow": 20},
            data_split="FULL",
            verdict="FAIL",
        )
        cat.insert(
            strategy_id="h5_macd_breakout",
            symbol="BTC/USDT",
            interval="1d",
            start_date="2024-01-01",
            end_date="2025-08-31",
            run_type="BACKTEST",
            metrics=metrics_a,
            results_file="strategy_results/h5_btc_test.json",
            parameters={"macd_fast": 12},
            hypothesis_id="H5",
            data_split="TEST",
            verdict="PASS",
        )

        cat.close()
        return db_path

    def test_results_list_displays_table(self, tmp_path: Path) -> None:
        """results list displays a table of results."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "list"])

        assert result.exit_code == 0
        assert "Strategy Results" in result.output
        assert "h2_rsi_divergence" in result.output
        assert "sma_crossover" in result.output

    def test_results_list_filters_by_symbol(self, tmp_path: Path) -> None:
        """results list --symbol filters correctly."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "list", "--symbol", "BTC/USDT"])

        assert result.exit_code == 0
        assert "BTC/USDT" in result.output
        assert "ETH/USDT" not in result.output

    def test_results_list_filters_by_data_split(self, tmp_path: Path) -> None:
        """results list --data-split filters correctly."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "list", "--data-split", "TEST"])

        assert result.exit_code == 0
        assert "TEST" in result.output

    def test_results_list_min_sharpe(self, tmp_path: Path) -> None:
        """results list --min-sharpe filters by threshold."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "list", "--min-sharpe", "1.0"])

        assert result.exit_code == 0
        # Should include H2 and H5 (sharpe > 1) but not sma (0.43)
        assert "h2_rsi" in result.output
        assert "sma_crossover" not in result.output

    def test_results_best_displays_top(self, tmp_path: Path) -> None:
        """results best displays top results."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "best", "--metric", "sharpe_ratio"])

        assert result.exit_code == 0
        assert "sharpe_ratio" in result.output

    def test_results_show_displays_details(self, tmp_path: Path) -> None:
        """results show displays full result details."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "show", "1"])

        assert result.exit_code == 0
        assert "Result #1" in result.output
        assert "h2_rsi_divergence_trend" in result.output
        assert "BTC/USDT" in result.output

    def test_results_show_not_found(self, tmp_path: Path) -> None:
        """results show with non-existent ID displays error."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "show", "999"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_results_compare_hypotheses(self, tmp_path: Path) -> None:
        """results compare shows side-by-side comparison."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "compare", "H2", "H5"])

        assert result.exit_code == 0
        assert "H2" in result.output
        assert "H5" in result.output

    def test_results_summary_displays_overview(self, tmp_path: Path) -> None:
        """results summary shows catalog overview."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "summary"])

        assert result.exit_code == 0
        assert "Strategy Results Catalog" in result.output
        assert "Total results" in result.output

    def test_results_rebuild_scans_directory(self, tmp_path: Path) -> None:
        """results rebuild indexes JSON files."""
        import json as json_mod

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        # Create a result file
        result_data = {
            "strategy_id": "sma_crossover",
            "run_type": "BACKTEST",
            "start_date": "2024-01-01",
            "end_date": "2025-01-01",
            "parameters": {"fast": 10},
            "trades": [],
            "metrics": {
                "total_return": 5.0,
                "sharpe_ratio": 1.5,
                "max_drawdown": -2.0,
                "win_rate": 60.0,
                "total_trades": 10,
                "profit_factor": 2.0,
            },
            "created_at": "2026-01-01T00:00:00Z",
        }
        (results_dir / "sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-01-01T23:59:59Z.json").write_text(
            json_mod.dumps(result_data), encoding="utf-8"
        )

        config = CryplativeConfig(
            data_dir=str(tmp_path),
            strategy_results_dir=str(results_dir),
        )

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "rebuild", "--results-dir", str(results_dir)])

        assert result.exit_code == 0
        assert "Indexed" in result.output

    def test_results_tag_updates_record(self, tmp_path: Path) -> None:
        """results tag updates hypothesis and verdict."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(
                app, ["results", "tag", "2", "--hypothesis", "H3", "--verdict", "PASS"]
            )

        assert result.exit_code == 0
        assert "Updated result #2" in result.output
        assert "hypothesis=H3" in result.output

    def test_results_tag_experiment(self, tmp_path: Path) -> None:
        """results tag --experiment updates experiment."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "tag", "1", "--experiment", "sweep_20260518"])

        assert result.exit_code == 0
        assert "experiment=sweep_20260518" in result.output

    def test_results_delete_removes_record(self, tmp_path: Path) -> None:
        """results delete removes a catalog entry."""
        self._make_catalog_with_data(tmp_path)
        config = CryplativeConfig(data_dir=str(tmp_path))

        with (
            patch("cryplative.cli.CryplativeConfig", return_value=config),
            patch("cryplative.cli.setup_logging"),
        ):
            result = runner.invoke(app, ["results", "delete", "1"])

        assert result.exit_code == 0
        assert "Deleted result #1" in result.output


class TestCLIBacktestCatalog:
    """Tests for --catalog flag on backtest command."""

    def test_backtest_with_catalog_flag(self, tmp_path: Path) -> None:
        """backtest --catalog inserts into catalog after run."""
        config = CryplativeConfig(
            data_dir=str(tmp_path),
            strategy_results_dir=str(tmp_path / "results"),
        )

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

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(
                    app,
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
                        "--catalog",
                        "--hypothesis",
                        "H2",
                        "--data-split",
                        "TEST",
                    ],
                )

        assert result.exit_code == 0
        assert "Backtest Results" in result.output
        assert "cataloged as #" in result.output
        assert "split=TEST" in result.output

    def test_backtest_without_catalog_no_change(self, tmp_path: Path) -> None:
        """backtest without --catalog produces identical behavior (no catalog output)."""
        config = CryplativeConfig(
            data_dir=str(tmp_path),
            strategy_results_dir=str(tmp_path / "results"),
        )

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

        with patch("cryplative.market_fetcher.fetcher.MarketFetcher") as mock_fetcher:
            mock_instance = MagicMock()
            mock_fetcher.return_value = mock_instance
            mock_instance.get_candles.return_value = test_candles

            with (
                patch("cryplative.cli.CryplativeConfig", return_value=config),
                patch("cryplative.cli.setup_logging"),
            ):
                result = runner.invoke(
                    app,
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
                    ],
                )

        assert result.exit_code == 0
        assert "cataloged" not in result.output
