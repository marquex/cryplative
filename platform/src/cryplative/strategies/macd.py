"""MACD Crossover Strategy."""

from __future__ import annotations

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle,
    OrderType,
    Signal,
    SignalDirection,
    StrategyConfig,
)
from cryplative.strategies.indicators import compute_macd
from cryplative.strategies.registry import StrategyRegistry


@StrategyRegistry.register
class MACDStrategy(Strategy):
    """Trend-following strategy based on MACD histogram crossovers."""

    @property
    def strategy_id(self) -> str:
        return "macd"

    @property
    def strategy_name(self) -> str:
        return "MACD Crossover"

    @classmethod
    def default_parameters(cls) -> dict[str, object]:
        return {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
        self._fast_period = int(config.parameters.get("fast_period", 12))
        self._slow_period = int(config.parameters.get("slow_period", 26))
        self._signal_period = int(config.parameters.get("signal_period", 9))

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        """Analyze candles using MACD histogram crossovers."""
        min_candles = self._slow_period + self._signal_period
        if len(candles) < min_candles:
            return None

        closes = [c.close for c in candles]
        _, _, histogram = compute_macd(
            closes, self._fast_period, self._slow_period, self._signal_period
        )

        # Look at the last two histogram values for crossover
        prev_hist = histogram[-2]
        curr_hist = histogram[-1]

        if prev_hist is None or curr_hist is None:
            return None

        latest_candle = candles[-1]

        # Histogram crossed from negative to positive → BUY
        if prev_hist < 0 and curr_hist > 0:
            return self._build_signal(SignalDirection.BUY, latest_candle)

        # Histogram crossed from positive to negative → SELL
        if prev_hist > 0 and curr_hist < 0:
            return self._build_signal(SignalDirection.SELL, latest_candle)

        return None

    def _build_signal(
        self,
        direction: SignalDirection,
        candle: Candle,
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
            confidence=0.55,
            metadata={
                "fast_period": self._fast_period,
                "slow_period": self._slow_period,
                "signal_period": self._signal_period,
            },
        )
