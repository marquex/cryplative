"""End-to-end integration test: fetch data + run backtest.

This test validates the complete pipeline from data fetching through
strategy execution to result persistence, without making real API calls.
"""

from __future__ import annotations

from pathlib import Path

from cryplative.backtesting.engine import BacktestConfig, BacktestEngine
from cryplative.config import CryplativeConfig
from cryplative.core.interfaces import DataProvider
from cryplative.core.models import Candle, RunContext
from cryplative.strategies.registry import StrategyRegistry
from cryplative.strategies.sma_crossover import SMACrossoverStrategy

# ---------------------------------------------------------------------------
# Mock DataProvider that generates realistic candle patterns
# ---------------------------------------------------------------------------


class SyntheticDataProvider(DataProvider):
    """Generates synthetic candle data for testing."""

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

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


def _generate_realistic_candles(n: int = 500) -> list[Candle]:
    """Generate realistic candle data with trends and crossovers.

    Produces a pattern: consolidation → uptrend → downtrend → uptrend
    to generate multiple trading signals.
    """
    import random

    random.seed(42)
    candles: list[Candle] = []
    base_time = 1704067200000  # 2024-01-01 00:00 UTC
    step = 3600000  # 1h

    price = 42000.0
    for i in range(n):
        phase = i / n

        if phase < 0.2:
            # Consolidation
            drift = 0
            volatility = 100
        elif phase < 0.45:
            # Uptrend
            drift = 50
            volatility = 200
        elif phase < 0.7:
            # Downtrend
            drift = -40
            volatility = 250
        else:
            # Recovery
            drift = 30
            volatility = 150

        change = drift + random.gauss(0, volatility)
        price = max(price + change, 1000.0)

        noise_open = random.gauss(0, 30)
        noise_high = abs(random.gauss(50, 30))
        noise_low = abs(random.gauss(50, 30))

        open_time = base_time + i * step
        candle_open = price + noise_open
        candle_close = price
        candle_high = max(open_price := candle_open, candle_close) + noise_high
        candle_low = min(candle_open, candle_close) - noise_low

        candles.append(
            Candle(
                symbol="BTC/USDT",
                interval="1h",
                open_time=open_time,
                open=round(open_price, 2),
                high=round(candle_high, 2),
                low=round(max(candle_low, 100.0), 2),
                close=round(candle_close, 2),
                volume=round(random.uniform(50, 500), 2),
                close_time=open_time + step - 1,
                closed=True,
            )
        )

    return candles


# ---------------------------------------------------------------------------
# E2E Integration Test
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """End-to-end integration test of the full pipeline."""

    def setup_method(self) -> None:
        StrategyRegistry.clear()
        StrategyRegistry.register(SMACrossoverStrategy)

    def test_full_pipeline_fetch_to_backtest_to_results(self, tmp_path: Path) -> None:
        """Complete pipeline: data → strategy → backtest → metrics → persisted results.

        This is the most important test in the entire test suite. It validates
        that all components work together correctly.
        """
        # 1. Generate data (simulates fetch)
        candles = _generate_realistic_candles(500)
        assert len(candles) >= 500

        # Verify data properties
        for i, c in enumerate(candles):
            assert c.symbol == "BTC/USDT"
            assert c.interval == "1h"
            assert c.open_time > 0
            assert c.close > 0
            if i > 0:
                assert c.open_time > candles[i - 1].open_time, "Candles must be sorted"

        # 2. Set up data provider
        provider = SyntheticDataProvider(candles)

        # 3. Set up config with temp directories
        cache_dir = tmp_path / "cache"
        results_dir = tmp_path / "results"
        config = CryplativeConfig(
            market_cache_dir=str(cache_dir),
            strategy_results_dir=str(results_dir),
        )

        # 4. Create backtest engine
        engine = BacktestEngine(provider, config)

        # 5. Configure and run backtest
        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-21T20:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 10, "slow_period": 20},
            lookback_window=200,
        )

        result = engine.run(backtest_config)

        # 6. Validate the result
        assert result.strategy_id == "sma_crossover"
        assert result.run_type == RunContext.BACKTEST
        assert result.start_date == "2024-01-01T00:00:00Z"
        assert result.end_date == "2024-01-21T20:00:00Z"
        assert result.parameters["fast_period"] == 10
        assert result.parameters["slow_period"] == 20
        assert isinstance(result.created_at, str)
        assert len(result.created_at) > 0

        # 7. Validate metrics
        metrics = result.metrics
        assert isinstance(metrics.total_return, float)
        assert isinstance(metrics.sharpe_ratio, float)
        assert metrics.max_drawdown <= 0.0
        assert isinstance(metrics.win_rate, float)
        assert isinstance(metrics.total_trades, int)
        assert metrics.total_trades >= 0
        assert isinstance(metrics.profit_factor, float)

        # 8. Validate trades
        assert isinstance(result.trades, list)
        # All trades should be closed (engine force-closes at end)
        from cryplative.core.models import TradeStatus

        open_trades = [t for t in result.trades if t.status == TradeStatus.OPEN]
        assert len(open_trades) == 0, "All trades should be closed after backtest"

        # Validate trade structure
        for trade in result.trades:
            assert trade.trade_id  # should have a UUID
            assert trade.entry_price > 0
            assert trade.exit_price is not None
            assert trade.opened_at > 0
            assert trade.closed_at is not None
            assert trade.context == RunContext.BACKTEST
            assert trade.signal.strategy_id == "sma_crossover"

        # 9. Validate result persistence
        saved_files = list(results_dir.glob("*.json"))
        assert len(saved_files) >= 1

        saved_content = saved_files[0].read_text(encoding="utf-8")
        assert "sma_crossover" in saved_content
        assert "BTC/USDT" in saved_content

        # Verify the saved result can be deserialized
        from cryplative.core.models import StrategyResult

        loaded_result = StrategyResult.model_validate_json(saved_content)
        assert loaded_result.strategy_id == result.strategy_id
        assert loaded_result.metrics.total_trades == result.metrics.total_trades

    def test_pipeline_with_no_signals(self, tmp_path: Path) -> None:
        """Pipeline with perfectly flat data generates zero trades."""
        from cryplative.core.models import Candle

        # Flat candles — no crossover possible
        candles = []
        for i in range(100):
            candles.append(
                Candle(
                    symbol="BTC/USDT",
                    interval="1h",
                    open_time=1704067200000 + i * 3600000,
                    open=42000.0,
                    high=42010.0,
                    low=41990.0,
                    close=42000.0,
                    volume=100.0,
                    close_time=1704067200000 + i * 3600000 + 3599999,
                    closed=True,
                )
            )

        provider = SyntheticDataProvider(candles)
        config = CryplativeConfig(
            strategy_results_dir=str(tmp_path / "results"),
        )
        engine = BacktestEngine(provider, config)

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-05T04:00:00Z",
            initial_capital=10000.0,
            parameters={"fast_period": 5, "slow_period": 10},
            lookback_window=50,
        )

        result = engine.run(backtest_config)
        assert result.metrics.total_trades == 0
        assert result.metrics.win_rate == 0.0
        assert result.metrics.sharpe_ratio == 0.0

    def test_pipeline_metrics_consistency(self, tmp_path: Path) -> None:
        """Verify that running the same backtest twice gives identical results."""
        candles = _generate_realistic_candles(300)

        provider = SyntheticDataProvider(candles)
        config = CryplativeConfig(
            strategy_results_dir=str(tmp_path / "results"),
        )

        backtest_config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2024-01-13T12:00:00Z",
            initial_capital=100000.0,
            parameters={"fast_period": 10, "slow_period": 20},
            lookback_window=200,
        )

        engine1 = BacktestEngine(provider, config)
        result1 = engine1.run(backtest_config)

        engine2 = BacktestEngine(provider, config)
        result2 = engine2.run(backtest_config)

        assert result1.metrics.total_trades == result2.metrics.total_trades
        assert result1.metrics.total_return == result2.metrics.total_return
        assert result1.metrics.win_rate == result2.metrics.win_rate
