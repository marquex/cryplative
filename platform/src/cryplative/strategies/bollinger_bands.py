"""Bollinger Bands Reversion Strategy."""

from __future__ import annotations

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle,
    OrderType,
    Signal,
    SignalDirection,
    StrategyConfig,
)
from cryplative.strategies.indicators import compute_bollinger_bands
from cryplative.strategies.registry import StrategyRegistry


@StrategyRegistry.register
class BollingerBandsStrategy(Strategy):
    """Volatility-based mean-reversion strategy using Bollinger Bands."""

    @property
    def strategy_id(self) -> str:
        return "bollinger_bands"

    @property
    def strategy_name(self) -> str:
        return "Bollinger Bands Reversion"

    @classmethod
    def default_parameters(cls) -> dict[str, object]:
        return {"period": 20, "num_std": 2.0}

    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
        self._period = int(config.parameters.get("period", 20))
        self._num_std = float(config.parameters.get("num_std", 2.0))

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        """Analyze candles using Bollinger Bands for mean-reversion signals."""
        min_candles = self._period + 1  # need two consecutive band values
        if len(candles) < min_candles:
            return None

        closes = [c.close for c in candles]
        upper, middle, lower = compute_bollinger_bands(closes, self._period, self._num_std)

        # Check band values at current and previous indices
        curr_close = closes[-1]
        prev_close = closes[-2]

        curr_upper = upper[-1]
        curr_lower = lower[-1]
        prev_lower = lower[-2]
        prev_upper = upper[-2]

        if any(v is None for v in [curr_upper, curr_lower, prev_lower, prev_upper]):
            return None

        assert curr_upper is not None
        assert curr_lower is not None
        assert prev_lower is not None
        assert prev_upper is not None

        latest_candle = candles[-1]

        # Price crossed below lower band → BUY
        if prev_close >= prev_lower and curr_close < curr_lower:
            return self._build_signal(SignalDirection.BUY, latest_candle)

        # Price crossed above upper band → SELL
        if prev_close <= prev_upper and curr_close > curr_upper:
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
            metadata={"period": self._period, "num_std": self._num_std},
        )
