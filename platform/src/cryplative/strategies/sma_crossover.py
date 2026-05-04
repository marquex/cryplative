"""SMA Crossover Strategy — the Hello World of trading strategies."""

from __future__ import annotations

import structlog

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle,
    OrderType,
    Signal,
    SignalDirection,
    StrategyConfig,
)
from cryplative.strategies.registry import StrategyRegistry

logger = structlog.get_logger()


def compute_sma(closes: list[float], period: int) -> list[float | None]:
    """Compute Simple Moving Average.

    Returns a list where each element is the SMA at that index, or None
    if there aren't enough data points to compute the average.
    """
    result: list[float | None] = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(None)
        else:
            window = closes[i - period + 1 : i + 1]
            result.append(sum(window) / period)
    return result


@StrategyRegistry.register
class SMACrossoverStrategy(Strategy):
    """Simple Moving Average Crossover strategy.

    Generates BUY signals when the fast SMA crosses above the slow SMA,
    and SELL signals when the fast SMA crosses below the slow SMA.
    """

    def __init__(self) -> None:
        self._config: StrategyConfig = StrategyConfig(
            strategy_id="sma_crossover",
            strategy_name="SMA Crossover",
            version="1.0.0",
            symbol="",
            interval="",
        )
        self._fast_period: int = 10
        self._slow_period: int = 20

    @property
    def strategy_id(self) -> str:
        return "sma_crossover"

    @property
    def strategy_name(self) -> str:
        return "SMA Crossover"

    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
        params = config.parameters
        self._fast_period = int(params.get("fast_period", 10))
        self._slow_period = int(params.get("slow_period", 20))

        if self._fast_period >= self._slow_period:
            logger.warning(
                "sma_fast_ge_slow",
                fast=self._fast_period,
                slow=self._slow_period,
            )

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        """Analyze candles and optionally return a trading signal.

        Requires at least ``slow_period + 1`` candles (slow_period for the
        SMA calculation plus one more to detect a crossover).
        """
        if len(candles) < self._slow_period + 1:
            return None

        closes = [c.close for c in candles]
        fast_sma = compute_sma(closes, self._fast_period)
        slow_sma = compute_sma(closes, self._slow_period)

        # Look at the last two completed candles to detect a crossover
        prev_fast = fast_sma[-2]
        prev_slow = slow_sma[-2]
        curr_fast = fast_sma[-1]
        curr_slow = slow_sma[-1]

        if any(v is None for v in [prev_fast, prev_slow, curr_fast, curr_slow]):
            return None

        # At this point mypy should know they're not None
        assert prev_fast is not None
        assert prev_slow is not None
        assert curr_fast is not None
        assert curr_slow is not None

        # Crossover detection
        latest_candle = candles[-1]

        # Fast crossed above slow → BUY
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return Signal(
                strategy_id=self.strategy_id,
                symbol=latest_candle.symbol,
                timestamp=latest_candle.open_time,
                direction=SignalDirection.BUY,
                order_type=OrderType.MARKET,
                price=None,
                quantity=1.0,
                stop_loss=None,
                take_profit=None,
                confidence=0.5,
                metadata={
                    "fast_sma": curr_fast,
                    "slow_sma": curr_slow,
                    "fast_period": self._fast_period,
                    "slow_period": self._slow_period,
                },
            )

        # Fast crossed below slow → SELL
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return Signal(
                strategy_id=self.strategy_id,
                symbol=latest_candle.symbol,
                timestamp=latest_candle.open_time,
                direction=SignalDirection.SELL,
                order_type=OrderType.MARKET,
                price=None,
                quantity=1.0,
                stop_loss=None,
                take_profit=None,
                confidence=0.5,
                metadata={
                    "fast_sma": curr_fast,
                    "slow_sma": curr_slow,
                    "fast_period": self._fast_period,
                    "slow_period": self._slow_period,
                },
            )

        return None
