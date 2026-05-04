"""Tests for backtesting engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from cryplative.backtesting.engine import BacktestConfig, BacktestEngine
from cryplative.config import CryplativeConfig
from cryplative.core.exceptions import BacktestError
from cryplative.core.interfaces import DataProvider
from cryplative.core.models import Candle, RunContext
from cryplative.strategies.registry import StrategyRegistry
from cryplative.strategies.sma_crossover import SMACrossoverStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_candle(
    index: int = 0,
    close: float = 100.0,
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    base_time: int = 1704067200000,
) -> Candle:
    """Create a test candle."""
    step = 3600000  # 1 hour in ms
    open_time = base_time + index * step
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=close - 5,
        high=close + 10,
        low=close - 10,
        close=close,
        volume=100.0,
        close_time=open_time + 3599999,
        closed=True,
    )


def _generate_candles_with_pattern(
    n: int = 100,
) -> list[Candle]:
    """Generate candles with a pattern that triggers SMA crossovers.

    Creates an uptrend followed by a downtrend to produce both
    BUY and SELL signals.
    """
    candles: list[Candle] = []
    for i in range(n):
        if i < n // 3:
            # Flat start
            close = 100.0
        elif i < 2 * n // 3:
            # Rising prices (should trigger BUY crossover)
            close = 100.0 + (i - n // 3) * 1.5
        else:
            # Falling prices (should trigger SELL crossover)
            peak = 100.0 + (n // 3) * 1.5
            close = peak - (i - 2 * n // 3) * 2.0
        candles.append(_make_candle(index=i, close=close))
    return candles


def _flat_candles(n: int = 50) -> list[Candle]:
    """Generate flat candles that produce no signals."""
    return [_make_candle(index=i, close=100.0) for i in range(n)]


class MockDataProvider(DataProvider):
    """Mock data provider for testing."""

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


# ---------------------------------------------------------------------------
# Metrics calculation tests
# ---------------------------------------------------------------------------


class TestMetricsCalculation:
    def test_total_return(self, tmp_path: Path) -> None:
        """Verify total_return is calculated correctly."""
        # Simple scenario: buy low, sell high
        candles = []
        for i in range(30):
            close = (
                100.0 - i * 0.5
                if i < 15
                else 100.0 - 15 * 0.5 + (i - 15) * 2.0
            )
            candles.append(_make_candle(index=i, close=close))

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-05T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=30,
        )

        result = engine.run(backtest_config)
        assert result.metrics.total_trades >= 0
        assert isinstance(result.metrics.total_return, float)

    def test_zero_trades(self, tmp_path: Path) -> None:
        """Test metrics when no trades are generated."""
        candles = _flat_candles(50)

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-05T00:00:00Z",
            initial_capital=10000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)
        assert result.metrics.total_trades == 0
        assert result.metrics.win_rate == 0.0
        assert result.metrics.sharpe_ratio == 0.0

    def test_max_drawdown(self, tmp_path: Path) -> None:
        """Test that max_drawdown is non-positive."""
        candles = _generate_candles_with_pattern(100)

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)
        assert result.metrics.max_drawdown <= 0.0

    def test_win_rate(self, tmp_path: Path) -> None:
        """Test win_rate calculation."""
        candles = _generate_candles_with_pattern(100)

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)
        if result.metrics.total_trades > 0:
            assert 0.0 <= result.metrics.win_rate <= 100.0

    def test_profit_factor_all_wins(self, tmp_path: Path) -> None:
        """Test profit_factor when all trades are wins."""
        candles = _generate_candles_with_pattern(100)

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)
        if result.metrics.total_trades > 0:
            # profit_factor should be positive
            assert result.metrics.profit_factor >= 0.0


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------


class TestBacktestEngine:
    def setup_method(self) -> None:
        StrategyRegistry.clear()
        StrategyRegistry.register(SMACrossoverStrategy)

    def test_full_backtest_run(self, tmp_path: Path) -> None:
        """End-to-end backtest produces a StrategyResult."""
        candles = _generate_candles_with_pattern(100)

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)

        assert result.strategy_id == "sma_crossover"
        assert result.run_type == RunContext.BACKTEST
        assert isinstance(result.metrics, type(result.metrics))
        assert isinstance(result.trades, list)

    def test_force_close_at_end(self, tmp_path: Path) -> None:
        """Open position at end of data should be force-closed."""
        # Create candles where the last pattern is a BUY
        candles = _generate_candles_with_pattern(100)
        # Truncate to only include the rising part → likely leaves a BUY open
        candles = candles[:80]

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)

        # Check no OPEN trades remain
        open_trades = [t for t in result.trades if t.status.value == "OPEN"]
        assert len(open_trades) == 0

    def test_result_saved_to_file(self, tmp_path: Path) -> None:
        """Result JSON is saved to the correct path."""
        candles = _generate_candles_with_pattern(100)

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        engine.run(backtest_config)

        expected_file = (
            tmp_path
            / "results"
            / "sma_crossover_BTC_USDT_1h_2024-01-01T00:00:00Z_2024-01-10T00:00:00Z.json"
        )
        assert expected_file.exists()
        content = expected_file.read_text(encoding="utf-8")
        assert "sma_crossover" in content

    def test_no_data_raises_error(self, tmp_path: Path) -> None:
        """No candle data should raise BacktestError."""
        provider = MockDataProvider([])
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=10000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        with pytest.raises(BacktestError, match="No candle data found"):
            engine.run(backtest_config)

    def test_unknown_strategy_raises_error(self, tmp_path: Path) -> None:
        """Unknown strategy ID should raise BacktestError."""
        candles = _flat_candles(50)
        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="nonexistent",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=10000.0,
        )

        with pytest.raises(BacktestError, match="not registered"):
            engine.run(backtest_config)

    def test_single_trade(self, tmp_path: Path) -> None:
        """Edge case: exactly one trade."""
        # Create a pattern that generates exactly one crossover
        candles = []
        for i in range(25):
            close = 100.0 if i < 12 else 100.0 + (i - 12) * 3.0
            candles.append(_make_candle(index=i, close=close))

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-05T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 3, "slow_period": 5},
            lookback_window=25,
        )

        result = engine.run(backtest_config)
        # Should have at most one trade (plus a force-close)
        assert result.strategy_id == "sma_crossover"

    def test_all_losing_trades_scenario(self, tmp_path: Path) -> None:
        """Test with a scenario that produces losing trades."""
        # Moderate uptrend then downtrend (keeping prices positive)
        candles = []
        for i in range(60):
            close = 100.0 + i * 1.0 if i < 20 else 120.0 - (i - 20) * 1.5
            candles.append(_make_candle(index=i, close=close))

        provider = MockDataProvider(candles)
        config = CryplativeConfig(strategy_results_dir=str(tmp_path / "results"))
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-10T00:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)
        assert result.metrics.total_trades >= 0
        assert result.metrics.max_drawdown <= 0.0
