"""RSI Mean Reversion Strategy."""

from __future__ import annotations

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle,
    OrderType,
    Signal,
    SignalDirection,
    StrategyConfig,
)
from cryplative.strategies.indicators import compute_rsi
from cryplative.strategies.registry import StrategyRegistry


@StrategyRegistry.register
class RSIStrategy(Strategy):
    """Mean-reversion strategy based on the Relative Strength Index."""

    @property
    def strategy_id(self) -> str:
        return "rsi"

    @property
    def strategy_name(self) -> str:
        return "RSI Mean Reversion"

    @classmethod
    def default_parameters(cls) -> dict[str, object]:
        return {"period": 14, "oversold": 30, "overbought": 70}

    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
        self._period = int(config.parameters.get("period", 14))
        self._oversold = float(config.parameters.get("oversold", 30))
        self._overbought = float(config.parameters.get("overbought", 70))

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        """Analyze candles using RSI for mean-reversion signals."""
        min_candles = self._period + 2  # need two consecutive RSI values
        if len(candles) < min_candles:
            return None

        closes = [c.close for c in candles]
        rsi_values = compute_rsi(closes, self._period)

        # Look at the last two RSI values for crossover detection
        prev_rsi = rsi_values[-2]
        curr_rsi = rsi_values[-1]

        if prev_rsi is None or curr_rsi is None:
            return None

        latest_candle = candles[-1]

        # RSI crossed above oversold → BUY
        if prev_rsi < self._oversold and curr_rsi >= self._oversold:
            return self._build_signal(SignalDirection.BUY, latest_candle, confidence=0.6)

        # RSI crossed below overbought → SELL
        if prev_rsi > self._overbought and curr_rsi <= self._overbought:
            return self._build_signal(SignalDirection.SELL, latest_candle, confidence=0.6)

        return None

    def _build_signal(
        self,
        direction: SignalDirection,
        candle: Candle,
        confidence: float = 0.6,
    ) -> Signal:
        return Signal(
            strategy_id=self.strategy_id,
            symbol=candle.symbol,
            timestamp=candle.open_time,
            direction=direction,
            order_type=OrderType.MARKET,
            price=None,
            quantity=1.0,
            stop_loss=None,
            take_profit=None,
            confidence=confidence,
            metadata={
                "period": self._period,
                "oversold": self._oversold,
                "overbought": self._overbought,
            },
        )
