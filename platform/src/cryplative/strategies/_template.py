# noqa: E501
"""Strategy Template — Copy this file to create a new strategy.

Instructions:
1. Copy this file to ``src/cryplative/strategies/<your_strategy_name>.py``
2. Replace all ``<PLACEHOLDER>`` values with your strategy's details
3. Implement the ``generate_signal()`` method with your trading logic
4. Your strategy is automatically registered — run ``cryplative strategies`` to verify

Quick start::

    cp strategies/_template.py strategies/my_strategy.py
    # Edit my_strategy.py
    cryplative backtest --strategy my_strategy --symbol BTC/USDT \\
        --interval 1h --start 2025-01-01 --end 2025-06-01
"""

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (  # noqa: F401
    Candle,
    OrderType,
    Signal,
    SignalDirection,
    StrategyConfig,
)
from cryplative.strategies.registry import StrategyRegistry  # noqa: F401

# Import indicators you need:
# from cryplative.strategies.indicators import compute_sma, compute_rsi, compute_macd


# NOTE: Do NOT add @StrategyRegistry.register here.
# This is a template file only. Auto-discovery skips files starting with "_".

class TemplateStrategy(Strategy):
    """<PLACEHOLDER: One-line description of your strategy>"""

    @property
    def strategy_id(self) -> str:
        return "<PLACEHOLDER: unique_id>"  # e.g., "rsi_mean_reversion"

    @property
    def strategy_name(self) -> str:
        return "<PLACEHOLDER: Human-readable name>"  # e.g., "RSI Mean Reversion"

    def initialize(self, config: StrategyConfig) -> None:
        """Called once before running. Set up parameters and state here."""
        super().initialize(config)
        # Access your parameters:
        # self.my_param = config.parameters.get("my_param", default_value)

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        """Analyze candles and return a Signal, or None if no action.

        The ``candles`` list is sorted by open_time ascending (oldest first).
        It contains at most ``lookback_window`` candles (default 200).

        Return a Signal to trigger a trade, or None to do nothing.
        """
        if len(candles) < self._min_candles_needed():
            return None

        # Extract closing prices
        # closes = [c.close for c in candles]

        # <PLACEHOLDER: Your strategy logic here>
        # Example: compute an indicator
        # values = compute_sma(closes, period=20)
        # if values[-1] is not None and values[-2] is not None:
        #     if values[-1] > values[-2]:  # crossing up
        #         return Signal(...)

        return None

    def _min_candles_needed(self) -> int:
        """Minimum number of candles needed before this strategy can produce signals.

        Override based on your indicator requirements.
        """
        return 20  # <PLACEHOLDER: adjust to your needs}

    def _build_signal(
        self,
        direction: SignalDirection,
        candle: Candle,
        confidence: float = 0.5,
    ) -> Signal:
        """Helper to build a Signal with standard fields."""
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
            metadata={},
        )
