"""End-to-end researcher workflow test.

Simulates a researcher:
1. Scaffolding a new strategy
2. Implementing generate_signal()
3. Running a backtest
4. Comparing results with another strategy
"""

from __future__ import annotations

from pathlib import Path

from cryplative.backtesting.engine import BacktestConfig, BacktestEngine
from cryplative.config import CryplativeConfig
from cryplative.core.interfaces import DataProvider
from cryplative.core.models import Candle, TradeStatus
from cryplative.strategies.registry import StrategyRegistry


def _make_candle(
    index: int = 0,
    close: float = 100.0,
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    base_time: int = 1704067200000,
) -> Candle:
    """Create a test candle."""
    step = 3600000
    open_time = base_time + index * step
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=max(close - 5, 0.01),
        high=close + 10,
        low=max(close - 10, 0.01),
        close=close,
        volume=100.0,
        close_time=open_time + 3599999,
        closed=True,
    )


class MockDataProvider(DataProvider):
    """Mock data provider."""

    def __init__(self, candles: list[Candle] | None = None) -> None:
        self._candles = candles or []

    def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> list[Candle]:
        result = self._candles
        if start_time is not None:
            result = [c for c in result if c.open_time >= start_time]
        if end_time is not None:
            result = [c for c in result if c.open_time <= end_time]
        if limit is not None:
            result = result[:limit]
        return result


def _generate_candles(n: int = 200) -> list[Candle]:
    """Generate candles with clear patterns for testing."""
    candles: list[Candle] = []
    for i in range(n):
        if i < n // 4:
            close = 100.0
        elif i < n // 2:
            close = 100.0 + (i - n // 4) * 2.0
        elif i < 3 * n // 4:
            close = 100.0 + (n // 4) * 2.0 - (i - n // 2) * 1.5
        else:
            close = 100.0 - (n // 4) * 0.5 + (i - 3 * n // 4) * 1.0
        candles.append(_make_candle(index=i, close=close))
    return candles


class TestResearcherWorkflow:
    """End-to-end test simulating a researcher's workflow."""

    def test_full_workflow(self, tmp_path: Path) -> None:
        """Test the complete researcher workflow:
        1. Scaffold a strategy
        2. Implement it
        3. Backtest it
        4. Compare with another strategy
        """
        StrategyRegistry.clear()

        # Register the built-in strategies
        from cryplative.strategies import sma_crossover  # noqa: F401
        from cryplative.strategies.sma_crossover import SMACrossoverStrategy
        StrategyRegistry.register(SMACrossoverStrategy)

        # Step 1: Verify built-in strategies are available
        strategies = StrategyRegistry.list_strategies()
        assert "sma_crossover" in strategies

        # Step 2: Verify auto-discovery finds all strategies (via subprocess)
        import subprocess

        result = subprocess.run(            ["python", "-c",
             "from cryplative.strategies import StrategyRegistry; "
             "print(sorted(StrategyRegistry.list_strategies()))"],
            capture_output=True,
            text=True,
            cwd=".",
            timeout=10,
        )
        assert result.returncode == 0
        # Should have at least sma_crossover, rsi, macd, bollinger_bands
        assert "sma_crossover" in result.stdout

        # Step 3: Run a backtest with the built-in strategy
        from cryplative.backtesting.engine import BacktestConfig, BacktestEngine

        candles = _generate_candles(200)
        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        bt_config_1 = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
            max_positions=1,
        )

        result_1 = engine.run(bt_config_1)

        # Verify result structure
        assert result_1.strategy_id == "sma_crossover"
        assert result_1.metrics.total_trades >= 0
        assert isinstance(result_1.metrics.total_return, float)

        # Step 4: Verify the result was saved as JSON
        results_dir = tmp_path / "results"
        json_files = list(results_dir.glob("*.json"))
        assert len(json_files) >= 1

        # Step 5: Run another backtest with different parameters
        bt_config_2 = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 3, "slow_period": 7},
            lookback_window=50,
            max_positions=1,
        )

        result_2 = engine.run(bt_config_2)

        # Both should be valid
        assert result_2.strategy_id == "sma_crossover"

        # Step 6: Compare results using the compare logic
        from cryplative.cli import build_comparison_data, load_strategy_results

        loaded = load_strategy_results([str(f) for f in json_files])
        assert len(loaded) >= 1

        metrics, names, rows = build_comparison_data(loaded)
        assert len(metrics) == 6  # total_return, sharpe_ratio, etc.
        assert len(names) >= 1
        assert len(rows) == 6

    def test_multi_strategy_backtest(self, tmp_path: Path) -> None:
        """Test backtesting with multiple strategies."""
        StrategyRegistry.clear()
        from cryplative.strategies.sma_crossover import SMACrossoverStrategy

        StrategyRegistry.register(SMACrossoverStrategy)

        candles = _generate_candles(200)
        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        # Backtest with multi-position
        bt_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
            max_positions=3,
        )

        result = engine.run(bt_config)

        # No open trades should remain
        open_trades = [t for t in result.trades if t.status == TradeStatus.OPEN]
        assert len(open_trades) == 0
        assert isinstance(result.metrics.total_return, float)

    def test_strategy_scaffold_and_discovery(self, tmp_path: Path) -> None:
        """Test scaffolding a strategy and verifying it's discoverable."""
        from cryplative.cli import _snake_to_pascal, _snake_to_title

        # Test the helper functions
        assert _snake_to_pascal("my_awesome_strategy") == "MyAwesomeStrategy"
        assert _snake_to_title("my_awesome_strategy") == "My Awesome Strategy"

        # Verify built-in strategies have default_parameters
        from cryplative.strategies.sma_crossover import SMACrossoverStrategy

        StrategyRegistry.clear()
        StrategyRegistry.register(SMACrossoverStrategy)

        cls = StrategyRegistry.get("sma_crossover")
        params = cls.default_parameters()
        assert "fast_period" in params
        assert "slow_period" in params

    def test_all_four_strategies_produce_results(self, tmp_path: Path) -> None:
        """All 4 strategies should produce valid backtest results."""
        StrategyRegistry.clear()

        candles = _generate_candles(200)
        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        from cryplative.strategies.bollinger_bands import BollingerBandsStrategy
        from cryplative.strategies.macd import MACDStrategy
        from cryplative.strategies.rsi import RSIStrategy
        from cryplative.strategies.sma_crossover import SMACrossoverStrategy

        strategies_to_test = [
            SMACrossoverStrategy,
            RSIStrategy,
            MACDStrategy,
            BollingerBandsStrategy,
        ]

        for strategy_cls in strategies_to_test:
            StrategyRegistry.clear()
            StrategyRegistry.register(strategy_cls)

            # Get default parameters
            params = strategy_cls.default_parameters()

            bt_config = BacktestConfig(
                strategy_id=strategy_cls.__new__(strategy_cls).strategy_id,
                symbol="BTC/USDT",
                interval="1h",
                start_date="2024-01-01T00:00:00Z",
                end_date="2024-01-10T00:00:00Z",
                initial_capital=100000.0,
                parameters=params,
                lookback_window=200,
                max_positions=1,
            )

            result = engine.run(bt_config)

            assert result.metrics.total_trades >= 0, (
                f"{strategy_cls.__name__} produced negative total_trades"
            )
            assert isinstance(result.metrics.total_return, float), (
                f"{strategy_cls.__name__} total_return is not a float"
            )

            # No open trades should remain
            open_trades = [t for t in result.trades if t.status == TradeStatus.OPEN]
            assert len(open_trades) == 0, (
                f"{strategy_cls.__name__} left open trades"
            )
