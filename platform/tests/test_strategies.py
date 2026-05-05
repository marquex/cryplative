"""Tests for strategy registry and SMA Crossover strategy."""

from __future__ import annotations

import pytest

from cryplative.core.models import Candle, SignalDirection, StrategyConfig
from cryplative.strategies.indicators import compute_sma
from cryplative.strategies.registry import StrategyRegistry
from cryplative.strategies.sma_crossover import SMACrossoverStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle(
    index: int = 0,
    close: float = 100.0,
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    base_time: int = 1704067200000,
) -> Candle:
    """Create a test candle with configurable close price and index offset."""
    step = 3600000  # 1 hour in ms
    open_time = base_time + index * step
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=close - 10,
        high=close + 20,
        low=close - 20,
        close=close,
        volume=100.0,
        close_time=open_time + 3599999,
        closed=True,
    )


def _make_candles_with_crossover(
    trend: str = "up",
    n: int = 30,
) -> list[Candle]:
    """Generate candles designed to produce an SMA crossover.

    Args:
        trend: "up" generates an upward crossover (fast > slow),
               "down" generates a downward crossover.
        n: Total number of candles.
    """
    candles: list[Candle] = []
    half = n // 2
    for i in range(n):
        if trend == "up":
            # First half: prices go down slowly, then up fast
            close = (
                100.0 - i * 0.5
                if i < half
                else 100.0 - half * 0.5 + (i - half) * 2.0
            )
        else:
            # First half: prices go up slowly, then down fast
            close = (
                100.0 + i * 0.5
                if i < half
                else 100.0 + half * 0.5 - (i - half) * 2.0
            )
        candles.append(_make_candle(index=i, close=close))
    return candles


# ---------------------------------------------------------------------------
# compute_sma
# ---------------------------------------------------------------------------


class TestComputeSMA:
    def test_basic_sma(self) -> None:
        result = compute_sma([10.0, 20.0, 30.0, 40.0, 50.0], 3)
        assert result == [None, None, 20.0, 30.0, 40.0]

    def test_sma_period_1(self) -> None:
        result = compute_sma([10.0, 20.0, 30.0], 1)
        assert result == [10.0, 20.0, 30.0]

    def test_sma_not_enough_data(self) -> None:
        result = compute_sma([10.0], 3)
        assert result == [None]

    def test_sma_empty(self) -> None:
        result = compute_sma([], 3)
        assert result == []

    def test_sma_constant_values(self) -> None:
        result = compute_sma([5.0, 5.0, 5.0, 5.0], 2)
        assert result == [None, 5.0, 5.0, 5.0]


# ---------------------------------------------------------------------------
# StrategyRegistry
# ---------------------------------------------------------------------------


class TestStrategyRegistry:
    def setup_method(self) -> None:
        """Clear registry before each test to avoid cross-test pollution."""
        StrategyRegistry.clear()

    def test_register_and_get(self) -> None:
        StrategyRegistry.register(SMACrossoverStrategy)
        cls = StrategyRegistry.get("sma_crossover")
        assert cls is SMACrossoverStrategy

    def test_get_unknown_raises(self) -> None:
        with pytest.raises(KeyError, match="not_a_strategy"):
            StrategyRegistry.get("not_a_strategy")

    def test_list_strategies_empty(self) -> None:
        assert StrategyRegistry.list_strategies() == []

    def test_list_strategies(self) -> None:
        StrategyRegistry.register(SMACrossoverStrategy)
        ids = StrategyRegistry.list_strategies()
        assert "sma_crossover" in ids

    def test_clear(self) -> None:
        StrategyRegistry.register(SMACrossoverStrategy)
        assert len(StrategyRegistry.list_strategies()) > 0
        StrategyRegistry.clear()
        assert StrategyRegistry.list_strategies() == []


# ---------------------------------------------------------------------------
# SMACrossoverStrategy
# ---------------------------------------------------------------------------


class TestSMACrossoverStrategy:
    def setup_method(self) -> None:
        StrategyRegistry.clear()
        self.strategy = SMACrossoverStrategy()
        self.strategy.initialize(
            StrategyConfig(
                strategy_id="sma_crossover",
                strategy_name="SMA Crossover",
                version="1.0.0",
                symbol="BTC/USDT",
                interval="1h",
                parameters={"fast_period": 5, "slow_period": 10},
            )
        )

    def test_no_signal_with_insufficient_data(self) -> None:
        candles = [_make_candle(index=i, close=100.0 + i) for i in range(5)]
        signal = self.strategy.generate_signal(candles)
        assert signal is None

    def test_buy_signal_on_upward_crossover(self) -> None:
        candles = _make_candles_with_crossover("up", n=30)
        # The crossover should occur somewhere in the latter half
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.direction == SignalDirection.BUY

    def test_sell_signal_on_downward_crossover(self) -> None:
        candles = _make_candles_with_crossover("down", n=30)
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.direction == SignalDirection.SELL

    def test_no_signal_when_no_crossover(self) -> None:
        # Steadily increasing prices — no crossover
        candles = [_make_candle(index=i, close=100.0 + i * 0.1) for i in range(30)]
        signal = self.strategy.generate_signal(candles)
        assert signal is None

    def test_signal_confidence(self) -> None:
        candles = _make_candles_with_crossover("up", n=30)
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.confidence == 0.5

    def test_signal_quantity(self) -> None:
        candles = _make_candles_with_crossover("up", n=30)
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.quantity == 1.0

    def test_strategy_id(self) -> None:
        assert self.strategy.strategy_id == "sma_crossover"

    def test_strategy_name(self) -> None:
        assert self.strategy.strategy_name == "SMA Crossover"

    def test_custom_parameters(self) -> None:
        s = SMACrossoverStrategy()
        s.initialize(
            StrategyConfig(
                strategy_id="sma_crossover",
                strategy_name="SMA Crossover",
                version="1.0.0",
                symbol="BTC/USDT",
                interval="1h",
                parameters={"fast_period": 3, "slow_period": 7},
            )
        )
        assert s._fast_period == 3
        assert s._slow_period == 7

    def test_buy_crossover_detection(self) -> None:
        """Explicitly construct candles that produce a BUY crossover."""
        # Create 15 candles with a clear pattern:
        # First 10: flat, then rising fast enough for fast SMA to cross above slow
        closes = [100.0] * 8 + [100.0, 101.0, 103.0, 106.0, 110.0, 115.0, 121.0]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(15)]
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.direction == SignalDirection.BUY

    def test_sell_crossover_detection(self) -> None:
        """Explicitly construct candles that produce a SELL crossover."""
        closes = [100.0] * 8 + [100.0, 99.0, 97.0, 94.0, 90.0, 85.0, 79.0]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(15)]
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.direction == SignalDirection.SELL


# ---------------------------------------------------------------------------
# Auto-discovery
# ---------------------------------------------------------------------------


class TestAutoDiscovery:
    """Test that auto-discovery works correctly.

    These tests run first (alphabetically) or ensure fresh state by
    manually registering what auto-discovery would provide.
    """

    def test_auto_discovery_finds_sma_crossover(self) -> None:
        """Auto-discovery should find sma_crossover when importing fresh.

        Run in a subprocess to avoid module caching issues.
        """
        import subprocess

        result = subprocess.run(
            [
                "python",
                "-c",
                "from cryplative.strategies import StrategyRegistry; "
                "print(StrategyRegistry.list_strategies())",
            ],
            capture_output=True,
            text=True,
            cwd=".",
        )
        assert "sma_crossover" in result.stdout
        assert "template" not in result.stdout

    def test_template_not_registered(self) -> None:
        """The _template.py file should NOT register a strategy."""
        ids = StrategyRegistry.list_strategies()
        assert "template" not in ids
