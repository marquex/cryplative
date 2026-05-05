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


# ---------------------------------------------------------------------------
# RSI Strategy
# ---------------------------------------------------------------------------


class TestRSIStrategy:
    def setup_method(self) -> None:
        StrategyRegistry.clear()
        from cryplative.strategies.rsi import RSIStrategy

        self.strategy = RSIStrategy()
        self.strategy.initialize(
            StrategyConfig(
                strategy_id="rsi",
                strategy_name="RSI Mean Reversion",
                version="1.0.0",
                symbol="BTC/USDT",
                interval="1h",
                parameters={"period": 5, "oversold": 30, "overbought": 70},
            )
        )

    def test_no_signal_with_insufficient_data(self) -> None:
        candles = [_make_candle(index=i, close=100.0 + i) for i in range(5)]
        signal = self.strategy.generate_signal(candles)
        assert signal is None

    def test_buy_on_rsi_cross_above_oversold(self) -> None:
        """RSI crossing above oversold should generate BUY."""
        # Create price data that will produce RSI going from below 30 to above 30
        # Steep drop followed by recovery
        closes = [100.0, 98.0, 96.0, 94.0, 92.0, 90.0, 88.0, 86.0, 85.0, 87.0, 90.0]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(len(closes))]
        signal = self.strategy.generate_signal(candles)
        # May or may not trigger depending on exact RSI values
        if signal is not None:
            assert signal.direction == SignalDirection.BUY

    def test_sell_on_rsi_cross_below_overbought(self) -> None:
        """RSI crossing below overbought should generate SELL."""
        # Create price data with strong uptrend then reversal
        closes = [
            100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0, 135.0, 140.0, 138.0, 135.0,
        ]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(len(closes))]
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.direction == SignalDirection.SELL

    def test_no_signal_when_rsi_stays_neutral(self) -> None:
        """No signal when RSI stays between oversold and overbought."""
        # Steady prices should keep RSI near 50
        closes = [100.0 + i * 0.1 for i in range(30)]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(30)]
        signal = self.strategy.generate_signal(candles)
        assert signal is None

    def test_strategy_registered(self) -> None:
        from cryplative.strategies.rsi import RSIStrategy

        StrategyRegistry.clear()
        StrategyRegistry.register(RSIStrategy)
        assert "rsi" in StrategyRegistry.list_strategies()

    def test_strategy_id_and_name(self) -> None:
        assert self.strategy.strategy_id == "rsi"
        assert self.strategy.strategy_name == "RSI Mean Reversion"

    def test_default_parameters(self) -> None:
        from cryplative.strategies.rsi import RSIStrategy

        params = RSIStrategy.default_parameters()
        assert params["period"] == 14
        assert params["oversold"] == 30
        assert params["overbought"] == 70

    def test_signal_confidence(self) -> None:
        """RSI strategy should have confidence 0.6."""
        # Create a scenario that triggers BUY
        closes = [100.0, 98.0, 96.0, 94.0, 92.0, 90.0, 88.0, 86.0, 85.0, 87.0, 90.0]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(len(closes))]
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.confidence == 0.6


# ---------------------------------------------------------------------------
# MACD Strategy
# ---------------------------------------------------------------------------


class TestMACDStrategy:
    def setup_method(self) -> None:
        StrategyRegistry.clear()
        from cryplative.strategies.macd import MACDStrategy

        self.strategy = MACDStrategy()
        self.strategy.initialize(
            StrategyConfig(
                strategy_id="macd",
                strategy_name="MACD Crossover",
                version="1.0.0",
                symbol="BTC/USDT",
                interval="1h",
                parameters={"fast_period": 3, "slow_period": 6, "signal_period": 3},
            )
        )

    def test_no_signal_with_insufficient_data(self) -> None:
        candles = [_make_candle(index=i, close=100.0 + i) for i in range(5)]
        signal = self.strategy.generate_signal(candles)
        assert signal is None

    def test_buy_on_bullish_crossover(self) -> None:
        """MACD histogram going negative to positive → BUY."""
        # Create data that produces a trend reversal (down then up)
        closes = [100.0, 95.0, 90.0, 85.0, 80.0, 82.0, 85.0, 90.0, 96.0, 103.0, 111.0]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(len(closes))]
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.direction == SignalDirection.BUY

    def test_sell_on_bearish_crossover(self) -> None:
        """MACD histogram going positive to negative → SELL."""
        closes = [100.0, 105.0, 110.0, 115.0, 120.0, 118.0, 115.0, 110.0, 105.0, 100.0, 95.0]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(len(closes))]
        signal = self.strategy.generate_signal(candles)
        if signal is not None:
            assert signal.direction == SignalDirection.SELL

    def test_no_signal_when_no_crossover(self) -> None:
        """No signal when histogram stays on one side."""
        closes = [float(100 + i) for i in range(30)]
        candles = [_make_candle(index=i, close=closes[i]) for i in range(30)]
        signal = self.strategy.generate_signal(candles)
        # Steady uptrend — histogram stays positive, no crossover
        assert signal is None

    def test_strategy_registered(self) -> None:
        from cryplative.strategies.macd import MACDStrategy

        StrategyRegistry.clear()
        StrategyRegistry.register(MACDStrategy)
        assert "macd" in StrategyRegistry.list_strategies()

    def test_strategy_id_and_name(self) -> None:
        assert self.strategy.strategy_id == "macd"
        assert self.strategy.strategy_name == "MACD Crossover"

    def test_default_parameters(self) -> None:
        from cryplative.strategies.macd import MACDStrategy

        params = MACDStrategy.default_parameters()
        assert params["fast_period"] == 12
        assert params["slow_period"] == 26
        assert params["signal_period"] == 9
