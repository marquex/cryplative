# How to Write a Trading Strategy

All import examples in this guide work from any directory after activating the root virtual environment (`source .venv/bin/activate`). No `sys.path` manipulation needed.

## The Strategy Interface

Every strategy must implement the `Strategy` abstract base class from `cryplative.core.interfaces`. You need to implement these methods and properties:

### `strategy_id` (property)

A unique string identifier for your strategy. This is how the strategy is referenced in CLI commands.

```python
@property
def strategy_id(self) -> str:
    return "my_strategy"
```

### `strategy_name` (property)

A human-readable name displayed in tables and results.

```python
@property
def strategy_name(self) -> str:
    return "My Strategy"
```

### `default_parameters()` (classmethod)

Return a dict of default parameter values for your strategy.

```python
@classmethod
def default_parameters(cls) -> dict[str, object]:
    return {"period": 14, "threshold": 30}
```

### `initialize(config)` (optional)

Called once before running. Use it to read parameters from the config.

```python
def initialize(self, config: StrategyConfig) -> None:
    super().initialize(config)
    self._period = int(config.parameters.get("period", 14))
```

### `generate_signal(candles)` (required)

The core logic. Analyze candles and return a `Signal`, or `None` if no action.

```python
def generate_signal(self, candles: list[Candle]) -> Signal | None:
    if len(candles) < self._min_candles_needed():
        return None
    # Your logic here
    return None
```

### `teardown()` (optional)

Called after the run completes. Default is no-op.

## Quick Start: Scaffold a Strategy

```bash
# From project root with activated venv
source .venv/bin/activate
cryplative new-strategy my_idea
```

Or from inside `platform/`:

```bash
cd platform && uv run cryplative new-strategy my_idea
```

This creates `platform/src/cryplative/strategies/my_idea.py` with boilerplate code. The strategy is automatically registered and appears in `cryplative strategies` immediately.

## Complete Example: Momentum Strategy

Here is a full working strategy that uses RSI as a momentum indicator:

```python
"""Simple momentum strategy using RSI."""

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle, OrderType, Signal, SignalDirection, StrategyConfig,
)
from cryplative.strategies.indicators import compute_rsi
from cryplative.strategies.registry import StrategyRegistry


@StrategyRegistry.register
class MomentumStrategy(Strategy):
    """Buy when RSI shows strong upward momentum."""

    @property
    def strategy_id(self) -> str:
        return "momentum"

    @property
    def strategy_name(self) -> str:
        return "Simple Momentum"

    @classmethod
    def default_parameters(cls) -> dict[str, object]:
        return {"rsi_period": 14, "rsi_threshold": 50}

    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
        self._period = int(config.parameters.get("rsi_period", 14))
        self._threshold = float(config.parameters.get("rsi_threshold", 50))

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        if len(candles) < self._period + 2:
            return None

        closes = [c.close for c in candles]
        rsi_values = compute_rsi(closes, self._period)

        prev_rsi = rsi_values[-2]
        curr_rsi = rsi_values[-1]

        if prev_rsi is None or curr_rsi is None:
            return None

        # RSI crosses above threshold → BUY
        if prev_rsi < self._threshold and curr_rsi >= self._threshold:
            return Signal(
                strategy_id=self.strategy_id,
                symbol=candles[-1].symbol,
                timestamp=candles[-1].open_time,
                direction=SignalDirection.BUY,
                order_type=OrderType.MARKET,
                price=None,
                quantity=1.0,
                stop_loss=None,
                take_profit=None,
                confidence=0.6,
                metadata={"rsi": curr_rsi},
            )

        return None
```

## Working with Candles

The `candles` list in `generate_signal()` contains `Candle` objects:

| Field       | Type    | Description                        |
|-------------|---------|------------------------------------|
| `symbol`    | `str`   | Trading pair (e.g., "BTC/USDT")    |
| `interval`  | `str`   | Candle interval (e.g., "1h")       |
| `open_time` | `int`   | Unix timestamp in milliseconds     |
| `open`      | `float` | Opening price                      |
| `high`      | `float` | Highest price                      |
| `low`       | `float` | Lowest price                       |
| `close`     | `float` | Closing price                      |
| `volume`    | `float` | Trading volume                     |
| `close_time`| `int`   | End timestamp in milliseconds       |
| `closed`    | `bool`  | Whether the candle is complete      |

Candles are sorted by `open_time` ascending (oldest first). The list contains at most `lookback_window` candles (default 200).

## Generating Signals

A `Signal` contains:

| Field         | Type             | Description                                  |
|---------------|------------------|----------------------------------------------|
| `strategy_id` | `str`           | Your strategy's ID                           |
| `symbol`      | `str`           | The trading pair                              |
| `timestamp`   | `int`           | Unix timestamp in ms (use `candle.open_time`)  |
| `direction`   | `SignalDirection`| `BUY` or `SELL`                              |
| `order_type`  | `OrderType`      | `MARKET` or `LIMIT`                          |
| `price`       | `float or None`  | Required for LIMIT orders                     |
| `quantity`    | `float`          | Number of units to trade                      |
| `stop_loss`   | `float or None`  | Stop loss price                               |
| `take_profit` | `float or None`  | Take profit price                             |
| `confidence`  | `float`          | 0.0 to 1.0                                   |
| `metadata`    | `dict`           | Strategy-specific data (logged in results)    |

## Using Indicators

The `cryplative.strategies.indicators` module provides common technical indicators:

```python
from cryplative.strategies.indicators import (
    compute_sma, compute_ema, compute_rsi, compute_macd, compute_bollinger_bands,
)

closes = [c.close for c in candles]

# Simple Moving Average
sma_20 = compute_sma(closes, period=20)
if sma_20[-1] is not None:
    # Use the value

# RSI
rsi = compute_rsi(closes, period=14)

# MACD
macd_line, signal_line, histogram = compute_macd(closes)

# Bollinger Bands
upper, middle, lower = compute_bollinger_bands(closes)
```

All indicator functions return lists where `None` means insufficient data at that index. See [Indicators Reference](indicators.md) for details.

## Strategy Parameters

Access parameters via `config.parameters` in `initialize()`:

```python
def initialize(self, config: StrategyConfig) -> None:
    super().initialize(config)
    self._period = int(config.parameters.get("period", 20))
```

Override `default_parameters()` to provide defaults shown in `cryplative strategies --verbose`.

Pass custom parameters via the CLI:

```bash
uv run cryplative backtest \
    --strategy my_strategy \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --params '{"period": 10, "threshold": 40}'
```

Or from a JSON file:

```bash
uv run cryplative backtest \
    --strategy my_strategy \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --params my_params.json
```

## Testing Your Strategy

Write tests in `tests/test_strategies.py`:

```python
class TestMyStrategy:
    def setup_method(self) -> None:
        StrategyRegistry.clear()
        from cryplative.strategies.my_strategy import MyStrategy
        self.strategy = MyStrategy()
        self.strategy.initialize(
            StrategyConfig(
                strategy_id="my_strategy",
                strategy_name="My Strategy",
                version="1.0.0",
                symbol="BTC/USDT",
                interval="1h",
                parameters={},
            )
        )

    def test_no_signal_with_insufficient_data(self) -> None:
        candles = [make_candle(i) for i in range(5)]
        assert self.strategy.generate_signal(candles) is None
```

## Registering Your Strategy

Registration is automatic when you use the `@StrategyRegistry.register` decorator. When you place your strategy file in `src/cryplative/strategies/`, the auto-discovery system imports it automatically (files starting with `_` are skipped).
