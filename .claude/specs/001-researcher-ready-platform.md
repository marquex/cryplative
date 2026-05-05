# SPEC-001: Researcher-Ready Platform

**Author**: CTO Agent
**Date**: 2026-05-05
**Status**: Ready for Implementation
**Assignee**: platform-developer
**Depends on**: SPEC-000 (COMPLETE), Architecture Overview

---

## 0. Purpose

Phase 1 built the foundation. Phase 2 makes it **usable by an algo-researcher**.

The goal is simple: an algo-researcher (human or AI agent) should be able to:
1. Read the documentation
2. Scaffold a new strategy
3. Implement their trading logic
4. Backtest it against real market data
5. Compare results across strategies and parameters
6. Iterate quickly

To achieve this, we need to:
- **Prove the framework works** by implementing diverse strategy types (not just SMA crossover)
- **Make strategy development easy** with reusable indicator building blocks and a template system
- **Expand backtesting capabilities** to support multiple concurrent positions
- **Polish the CLI** into a researcher's primary tool
- **Write clear documentation** so a new researcher can be productive immediately

---

## 1. Context — What Exists from Phase 1

The developer should build on the existing codebase from SPEC-000:

| Component | Location | Status |
|-----------|----------|--------|
| Core models | `src/cryplative/core/models.py` | Complete — Candle, Signal, Trade, StrategyConfig, StrategyResult |
| Core interfaces | `src/cryplative/core/interfaces.py` | Complete — Strategy ABC, DataProvider ABC, ExecutionHandler ABC |
| Exceptions | `src/cryplative/core/exceptions.py` | Complete |
| Config | `src/cryplative/config.py` | Complete — CryplativeConfig with pydantic-settings |
| MarketFetcher | `src/cryplative/market_fetcher/` | Complete — ccxt + file cache |
| Strategy registry | `src/cryplative/strategies/registry.py` | Complete — `@StrategyRegistry.register` decorator |
| SMA Crossover | `src/cryplative/strategies/sma_crossover.py` | Complete — includes `compute_sma()` helper |
| Portfolio tracker | `src/cryplative/portfolio/tracker.py` | Minimal — single position only |
| Backtesting engine | `src/cryplative/backtesting/engine.py` | Complete — single position only |
| CLI | `src/cryplative/cli.py` | Complete — `backtest`, `fetch`, `strategies` commands |
| Tests | `tests/` | Complete — 99 tests, 93% coverage |

**Key limitation**: The backtesting engine and portfolio tracker only support a single concurrent position. Many strategies (portfolio-level, multi-entry, scaling) require multiple positions. This must be fixed.

---

## 2. Common Indicators Library

**New file**: `src/cryplative/strategies/indicators.py`

A library of pure technical indicator functions that any strategy can use. These are the building blocks a researcher composes to create their strategy.

### 2.1 Design Principles

- **Pure functions** — take data in, return computed values. No side effects, no state.
- **Consistent interface** — all functions accept `list[float]` (closing prices), return `list[float | None]` where `None` means insufficient data at that index.
- **Use numpy internally** — correct and fast. Convert back to list for output.
- **Well-documented docstrings** — each function has a clear docstring explaining the algorithm, parameters, and return format.

### 2.2 Functions to Implement

```python
import numpy as np
from typing import Optional


def compute_sma(closes: list[float], period: int) -> list[float | None]:
    """Simple Moving Average.

    Returns a list of the same length as `closes`. Values are None
    for indices where fewer than `period` data points are available.

    Algorithm: arithmetic mean of the last `period` values.
    """
    ...


def compute_ema(closes: list[float], period: int) -> list[float | None]:
    """Exponential Moving Average.

    Algorithm: EMA_t = price_t * multiplier + EMA_{t-1} * (1 - multiplier)
    where multiplier = 2 / (period + 1).
    Seed with SMA of first `period` values.
    """
    ...


def compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index (Wilder's smoothing).

    Returns values in range [0, 100].

    Algorithm:
    1. Calculate price changes.
    2. Separate into gains (positive changes) and losses (absolute negative changes).
    3. First avg_gain = mean(gains[:period]), first avg_loss = mean(losses[:period]).
    4. Subsequent: avg_gain = (prev_avg_gain * (period-1) + current_gain) / period.
    5. RS = avg_gain / avg_loss. RSI = 100 - (100 / (1 + RS)).
    """
    ...


def compute_macd(
    closes: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Moving Average Convergence Divergence.

    Returns (macd_line, signal_line, histogram).

    Algorithm:
    1. MACD line = EMA(fast) - EMA(slow).
    2. Signal line = EMA(MACD line, signal_period).
    3. Histogram = MACD line - Signal line.

    All three lists have the same length as `closes`.
    """
    ...


def compute_bollinger_bands(
    closes: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger Bands.

    Returns (upper_band, middle_band, lower_band).

    Algorithm:
    1. Middle band = SMA(period).
    2. Upper band = Middle + num_std * stdev(period).
    3. Lower band = Middle - num_std * stdev(period).
    """
    ...
```

### 2.3 Refactor SMA Crossover

After creating the indicators library, **refactor** `sma_crossover.py` to import `compute_sma` from `indicators.py` instead of having its own implementation. Delete the old `compute_sma` from `sma_crossover.py`.

This proves the indicators library is a drop-in replacement and keeps the SMA crossover strategy clean.

### 2.4 Testing Requirements

For each indicator function:
- Correct computation against **known values** (compute expected values manually or reference a known source — e.g., a well-known RSI calculator with specific inputs)
- Returns `None` for indices where insufficient data exists
- Handles edge cases: empty list, single element, list shorter than period
- Return list has same length as input list
- Works with numpy arrays as input (in addition to lists)

---

## 3. Multi-Position Backtesting

The current engine and tracker only support a single concurrent position. This blocks many strategy types. We need multi-position support while keeping backward compatibility.

### 3.1 BacktestConfig Changes

Add to `BacktestConfig` (in `backtesting/engine.py`):

```python
class BacktestConfig(BaseModel):
    strategy_id: str
    symbol: str
    interval: str
    start_date: str
    end_date: str
    initial_capital: float = 10000.0
    parameters: dict = {}
    lookback_window: int = 200
    max_positions: int = 1  # NEW: max concurrent open positions. Default 1 = backward compatible.
```

### 3.2 PortfolioTracker Refactor

**File**: `src/cryplative/portfolio/tracker.py`

Refactor from single-position to multi-position:

```python
class PortfolioTracker:
    def __init__(self, initial_capital: float, max_positions: int = 1):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.max_positions = max_positions
        self.open_trades: list[Trade] = []
        self.closed_trades: list[Trade] = []
        self.equity_snapshots: list[tuple[int, float]] = []

    def can_open(self) -> bool:
        """Whether we can open a new position."""
        return len(self.open_trades) < self.max_positions

    def open_position(self, signal: Signal, price: float, timestamp: int) -> Trade:
        """Open a new position. Deduct capital.
        Raises BacktestError if max_positions already reached."""
        ...

    def close_position(self, trade: Trade, price: float, timestamp: int) -> Trade:
        """Close a specific trade. Add capital back."""
        ...

    def close_oldest(self, price: float, timestamp: int) -> Trade:
        """Close the oldest open trade (FIFO)."""
        ...

    def get_equity(self, current_price: float) -> float:
        """Current equity = cash + sum of all open position values at current price."""
        ...

    def snapshot_equity(self, timestamp: int, current_price: float) -> None:
        """Record an equity snapshot."""
        ...

    def get_equity_curve(self) -> list[tuple[int, float]]:
        """Return all equity snapshots."""
        ...

    @property
    def all_trades(self) -> list[Trade]:
        """All trades (open + closed)."""
        return self.open_trades + self.closed_trades
```

### 3.3 BacktestEngine Changes

**File**: `src/cryplative/backtesting/engine.py`

Update the simulation loop:

```python
def run(self, config: BacktestConfig) -> StrategyResult:
    ...
    # Create tracker with max_positions from config
    tracker = PortfolioTracker(config.initial_capital, config.max_positions)

    for i in range(lookback_window, len(candles)):
        window = candles[i - lookback_window : i + 1]
        current_candle = candles[i]
        signal = strategy.generate_signal(window)

        if signal is not None:
            if signal.direction == SignalDirection.BUY and tracker.can_open():
                trade = tracker.open_position(signal, current_candle.close, current_candle.close_time)
            elif signal.direction == SignalDirection.SELL and len(tracker.open_trades) > 0:
                # Close the oldest open trade (FIFO)
                tracker.close_oldest(current_candle.close, current_candle.close_time)

        # Snapshot equity at each candle
        tracker.snapshot_equity(current_candle.close_time, current_candle.close)

    # Force-close all remaining open positions at the end
    while tracker.open_trades:
        last_candle = candles[-1]
        tracker.close_oldest(last_candle.close, last_candle.close_time)
    ...
```

**Backward compatibility**: When `max_positions=1` (default), behavior is identical to the Phase 1 engine — single position, same P&L calculations.

### 3.4 Testing Requirements

- Single-position mode (max_positions=1) produces identical results to Phase 1 (regression test — use existing test data)
- Multi-position mode (max_positions=3) correctly tracks 3 concurrent positions
- Cannot exceed max_positions — raises error or ignores signal
- FIFO closing works correctly
- Equity calculation includes all open positions
- Force-close at end closes all remaining positions
- Edge case: max_positions larger than capital allows (capital constraint)

---

## 4. Strategy Template System

### 4.1 Template File

**New file**: `src/cryplative/strategies/_template.py`

This is a well-commented skeleton strategy that serves as both a template and documentation:

```python
"""
Strategy Template — Copy this file to create a new strategy.

Instructions:
1. Copy this file to `src/cryplative/strategies/<your_strategy_name>.py`
2. Replace all <PLACEHOLDER> values with your strategy's details
3. Implement the `generate_signal()` method with your trading logic
4. Your strategy is automatically registered — run `cryplative strategies` to verify

Quick start:
    cp strategies/_template.py strategies/my_strategy.py
    # Edit my_strategy.py
    cryplative backtest --strategy my_strategy --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01
"""

from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle,
    Signal,
    SignalDirection,
    OrderType,
    StrategyConfig,
)
from cryplative.strategies.registry import StrategyRegistry
# Import indicators you need:
# from cryplative.strategies.indicators import compute_sma, compute_rsi, compute_macd


@StrategyRegistry.register
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

        The `candles` list is sorted by open_time ascending (oldest first).
        It contains at most `lookback_window` candles (default 200).

        Return a Signal to trigger a trade, or None to do nothing.
        """
        if len(candles) < self._min_candles_needed():
            return None

        closes = [c.close for c in candles]

        # <PLACEHOLDER: Your strategy logic here>
        # Example: compute an indicator
        # values = compute_sma(closes, period=20)
        # if values[-1] is not None and values[-2] is not None:
        #     if values[-1] > values[-2]:  # crossing up
        #         return Signal(...)

        return None

    def _min_candles_needed(self) -> int:
        """Minimum number of candles needed before this strategy can produce signals.
        Override based on your indicator requirements."""
        return 20  # <PLACEHOLDER: adjust to your needs>

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
            timestamp=candle.close_time,
            direction=direction,
            order_type=OrderType.MARKET,
            price=None,
            quantity=1.0,
            stop_loss=None,
            take_profit=None,
            confidence=confidence,
            metadata={},
        )
```

### 4.2 `new-strategy` CLI Command

Add a new command to `cli.py`:

```python
@app.command()
def new_strategy(name: str) -> None:
    """Scaffold a new strategy from the template.

    Creates a new strategy file with boilerplate code and
    registers it for immediate use.
    """
```

**Behavior**:
1. Read `_template.py`
2. Replace all `<PLACEHOLDER>` strings with sensible defaults based on `name`:
   - Class name: snake_case → PascalCase (e.g., `my_strategy` → `MyStrategy`)
   - `strategy_id`: use the `name` argument as-is (snake_case)
   - `strategy_name`: convert to title case (e.g., `my_strategy` → `"My Strategy"`)
3. Write to `src/cryplative/strategies/{name}.py`
4. Print next steps:
   ```
   Created strategy: my_strategy
   File: src/cryplative/strategies/my_strategy.py

   Next steps:
   1. Edit the file and implement generate_signal()
   2. Run: cryplative backtest --strategy my_strategy --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01
   ```
5. If the file already exists, error with a clear message (don't overwrite).

### 4.3 Auto-Discovery of Strategies

The `strategies/__init__.py` must import all strategy modules so they register themselves. Instead of manually importing each new strategy file, implement auto-discovery:

```python
# strategies/__init__.py
import importlib
import pkgutil
from cryplative.strategies import registry

# Auto-import all modules in this package to trigger @StrategyRegistry.register decorators
# Skip _template (it's a template, not a real strategy)
for _module_info in pkgutil.iter_modules(__path__):
    if not _module_info.name.startswith("_"):
        importlib.import_module(f".{_module_info.name}", __package__)
```

This ensures new strategies are discovered automatically without editing `__init__.py`.

### 4.4 Testing Requirements

- `new_strategy` command creates file with correct content
- Created strategy class has correct name, strategy_id, strategy_name
- Created strategy is discoverable via `StrategyRegistry.list_strategies()`
- Auto-discovery finds all strategies (including new ones)
- Template file (`_template.py`) is NOT registered as a strategy
- Error when creating strategy with name that already exists

---

## 5. RSI Strategy

**New file**: `src/cryplative/strategies/rsi.py`

A mean-reversion strategy based on the Relative Strength Index.

### 5.1 Strategy Details

| Field | Value |
|-------|-------|
| **strategy_id** | `"rsi"` |
| **strategy_name** | `"RSI Mean Reversion"` |
| **Type** | Mean-reversion (oscillator-based) |

### 5.2 Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `period` | 14 | RSI lookback period |
| `oversold` | 30 | Threshold to consider oversold |
| `overbought` | 70 | Threshold to consider overbought |

### 5.3 Signal Logic

1. Compute RSI(period) using `compute_rsi()` from indicators.
2. Need at least `period + 1` candles to produce a signal.
3. Look at the last two RSI values:
   - If previous RSI was **below** oversold AND current RSI **crosses above** oversold → **BUY** (price was oversold, now recovering)
   - If previous RSI was **above** overbought AND current RSI **crosses below** overbought → **SELL** (price was overbought, now declining)
   - Otherwise → None
4. `confidence`: 0.6 (slightly higher than SMA — RSI has a bounded range which is more informative)
5. `quantity`: 1.0
6. `stop_loss` and `take_profit`: None for now

### 5.4 Testing

- No signal when insufficient candles
- BUY signal on RSI crossing above oversold threshold
- SELL signal on RSI crossing below overbought threshold
- No signal when RSI stays in neutral zone
- No signal when RSI is already above oversold (no crossover)
- Strategy registered with correct ID

---

## 6. MACD Strategy

**New file**: `src/cryplative/strategies/macd.py`

A trend-following strategy based on MACD crossovers.

### 6.1 Strategy Details

| Field | Value |
|-------|-------|
| **strategy_id** | `"macd"` |
| **strategy_name** | `"MACD Crossover"` |
| **Type** | Trend-following (momentum) |

### 6.2 Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `fast_period` | 12 | Fast EMA period |
| `slow_period` | 26 | Slow EMA period |
| `signal_period` | 9 | Signal line period |

### 6.3 Signal Logic

1. Compute MACD using `compute_macd()` from indicators.
2. Need at least `slow_period + signal_period` candles to produce a signal.
3. Look at the last two values of the MACD histogram:
   - If histogram crossed from **negative to positive** → **BUY** (bullish crossover)
   - If histogram crossed from **positive to negative** → **SELL** (bearish crossover)
   - Otherwise → None
4. `confidence`: 0.55
5. `quantity`: 1.0
6. `stop_loss` and `take_profit`: None

### 6.4 Testing

- No signal when insufficient candles
- BUY on bullish MACD crossover (histogram goes negative → positive)
- SELL on bearish MACD crossover (histogram goes positive → negative)
- No signal when no crossover
- Strategy registered with correct ID

---

## 7. Bollinger Bands Strategy

**New file**: `src/cryplative/strategies/bollinger_bands.py`

A volatility-based mean-reversion strategy.

### 7.1 Strategy Details

| Field | Value |
|-------|-------|
| **strategy_id** | `"bollinger_bands"` |
| **strategy_name** | `"Bollinger Bands Reversion"` |
| **Type** | Mean-reversion (volatility-based) |

### 7.2 Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `period` | 20 | SMA period for middle band |
| `num_std` | 2.0 | Number of standard deviations for bands |

### 7.3 Signal Logic

1. Compute Bollinger Bands using `compute_bollinger_bands()` from indicators.
2. Need at least `period` candles.
3. Look at the current candle's close price relative to the bands:
   - If close **crosses below** the lower band (previous close was above or at lower, current is below) → **BUY** (price is statistically cheap)
   - If close **crosses above** the upper band (previous close was below or at upper, current is above) → **SELL** (price is statistically expensive)
   - Otherwise → None
4. `confidence`: 0.55
5. `quantity`: 1.0
6. `stop_loss` and `take_profit`: None

### 7.4 Testing

- No signal when insufficient candles
- BUY when price crosses below lower band
- SELL when price crosses above upper band
- No signal when price stays within bands
- Strategy registered with correct ID

---

## 8. CLI Enhancements

### 8.1 `cryplative compare` Command

Compare backtest results side by side:

```python
@app.command()
def compare(
    files: list[str] = typer.Argument(..., help="Paths to strategy result JSON files"),
) -> None:
    """Compare backtest results from multiple result files."""
```

**Behavior**:
1. Load each JSON file as a `StrategyResult`.
2. Print a rich comparison table with columns:

| Metric | Strategy A | Strategy B | Strategy C |
|--------|-----------|-----------|-----------|
| Total Return | 15.3% | 8.2% | -3.1% |
| Sharpe Ratio | 1.24 | 0.85 | -0.12 |
| Max Drawdown | -8.5% | -12.3% | -15.0% |
| Win Rate | 55.0% | 48.0% | 42.0% |
| Total Trades | 20 | 35 | 18 |
| Profit Factor | 1.8 | 1.2 | 0.8 |

3. Use color coding in the table: green for best value in each row, red for worst.
4. Handle errors gracefully: skip files that can't be loaded, warn user.

### 8.2 `cryplative backtest` Improvements

**`--params` accepts a JSON file path** in addition to a JSON string:

```python
@app.command()
def backtest(
    ...
    params: str = typer.Option("{}", help="Strategy parameters as JSON string or path to JSON file"),
    ...
)
```

If `params` ends with `.json`, treat it as a file path and load the JSON from there. Otherwise, parse as a JSON string.

**`--max-positions` flag**:

```python
    max_positions: int = typer.Option(1, help="Maximum concurrent open positions"),
```

**Better error output**:
- If strategy not found: list available strategies
- If symbol/interval invalid: explain the expected format
- If date range yields no data: suggest available date ranges or shorter intervals
- If params JSON is malformed: show the parse error

### 8.3 `cryplative strategies` Improvement

Add a `--verbose` flag that shows parameters and description for each strategy:

```
$ cryplative strategies --verbose

┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID              ┃ Name                 ┃ Default Parameters                    ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ sma_crossover   │ SMA Crossover        │ fast_period=10, slow_period=20        │
│ rsi             │ RSI Mean Reversion   │ period=14, oversold=30, overbought=70 │
│ macd            │ MACD Crossover       │ fast_period=12, slow_period=26, ...   │
│ bollinger_bands │ Bollinger Bands      │ period=20, num_std=2.0                │
└─────────────────┴──────────────────────┴───────────────────────────────────────┘
```

To support this, add a class method or property to the Strategy ABC:

```python
@classmethod
def default_parameters(cls) -> dict:
    """Return the default parameters for this strategy. Override in subclasses."""
    return {}
```

Each strategy overrides this to return its default parameter values.

### 8.4 Testing

- `compare` loads multiple JSON files and prints a table
- `compare` skips invalid files with a warning
- `backtest --params params.json` reads parameters from file
- `backtest --max-positions 3` passes through to BacktestConfig
- `strategies --verbose` shows parameter information
- Error messages are clear and actionable

---

## 9. Robustness Improvements

### 9.1 Input Validation in CLI

Validate all CLI inputs before executing:

- **Symbol format**: Must match `BASE/QUOTE` pattern (e.g., `BTC/USDT`). Reject with clear message.
- **Interval**: Must be one of the supported ccxt intervals (`1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`). Validate and suggest alternatives.
- **Date format**: Must be ISO 8601 date (`YYYY-MM-DD`) or datetime (`YYYY-MM-DDTHH:MM:SS`). Clear error on invalid format.
- **Capital**: Must be positive float. Reject zero or negative.
- **Strategy ID**: Must be registered. If not, list available strategies.

### 9.2 Error Handling in Backtesting

- **No candle data**: If MarketFetcher returns empty for the requested range, raise `BacktestError` with a message suggesting: checking the symbol, trying a different date range, or running `cryplative fetch` first.
- **Insufficient candles**: If fewer candles than `lookback_window` are available, raise `BacktestError` with the count available vs needed.
- **Strategy errors**: Catch `StrategyError` during `generate_signal()` calls, log it, and continue the backtest (don't crash the whole run). Track errors in the result metadata.
- **Capital exhaustion**: If `can_open()` returns False because capital is depleted, log a warning.

### 9.3 Market Data Fetching

- **Retry logic**: If a ccxt call fails with a network error, retry up to 3 times with exponential backoff (1s, 2s, 4s).
- **Partial data**: If fetching a large date range, fetch in chunks (ccxt limits per-call results). Handle pagination properly.
- **Rate limit clarity**: Log when rate limiting is active, so researchers understand why fetching is slow.

### 9.4 Testing

- Invalid symbol format raises clear error
- Invalid interval raises clear error with valid options listed
- Invalid date format raises clear error
- Unknown strategy ID lists available strategies
- Empty candle data raises BacktestError with helpful message
- Network retry works (mock ccxt to fail twice then succeed)
- Strategy error during backtest doesn't crash the run

---

## 10. Documentation for Researchers

**New directory**: `platform/docs/`

All documentation is Markdown, written for an algo-researcher who has never seen the platform. It should be concise, code-heavy, and actionable.

### 10.1 `platform/docs/getting-started.md`

**Title**: Getting Started with Cryplative Platform

**Sections**:
1. **Prerequisites** — Python 3.11+, uv, git
2. **Installation** — `cd platform && uv sync`
3. **Verify Installation** — `uv run cryplative strategies` should list available strategies
4. **Your First Backtest** — Complete example:
   ```bash
   uv run cryplative fetch --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01
   uv run cryplative backtest --strategy sma_crossover --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01
   ```
5. **What Happens** — Explain the output (metrics table, JSON file saved)
6. **Next Steps** — Link to writing-strategies.md and backtesting-guide.md

### 10.2 `platform/docs/writing-strategies.md`

**Title**: How to Write a Trading Strategy

This is the most important document. An algo-researcher should be able to read this and implement their first strategy in under 30 minutes.

**Sections**:
1. **The Strategy Interface** — What methods to implement, what each does
   - `strategy_id` and `strategy_name` properties
   - `initialize(config)` — setup
   - `generate_signal(candles)` — the core logic
   - `teardown()` — cleanup
2. **Quick Start: Scaffold a Strategy**
   ```bash
   uv run cryplative new-strategy my_idea
   ```
   Explain what gets created and where.
3. **Complete Example: Implementing a Strategy** — Walk through a full implementation (e.g., a simple momentum strategy). Show the complete code.
4. **Working with Candles** — The Candle model, what fields are available, how candles are ordered.
5. **Generating Signals** — The Signal model, required fields, direction, order types, confidence, metadata.
6. **Using Indicators** — Available indicators, how to call them, what they return:
   ```python
   from cryplative.strategies.indicators import compute_sma, compute_rsi

   closes = [c.close for c in candles]
   sma_20 = compute_sma(closes, period=20)
   if sma_20[-1] is not None:
       # Use the value
   ```
7. **Strategy Parameters** — How to accept configurable parameters, how to test with different parameters via CLI.
8. **Testing Your Strategy** — How to write tests, available fixtures, mocking patterns.
9. **Registering Your Strategy** — It's automatic via the decorator. Explain how.

### 10.3 `platform/docs/cli-reference.md`

**Title**: CLI Reference

Complete reference for all CLI commands with examples:

1. `cryplative strategies [--verbose]` — List available strategies
2. `cryplative fetch` — Fetch and cache market data
3. `cryplative backtest` — Run a backtest
4. `cryplative new-strategy <name>` — Scaffold a new strategy
5. `cryplative compare --files <...>` — Compare backtest results

For each command: description, all flags with defaults, examples.

### 10.4 `platform/docs/backtesting-guide.md`

**Title**: Backtesting Guide

**Sections**:
1. **How Backtesting Works** — Walk through the engine's simulation loop: sliding window, signal generation, trade execution, position management.
2. **Understanding Metrics** — Each metric explained:
   - Total Return: what it means, how it's calculated
   - Sharpe Ratio: risk-adjusted return, interpretation (negative = bad, >1 = good, >2 = excellent)
   - Max Drawdown: worst peak-to-trough decline, why it matters
   - Win Rate: percentage of profitable trades
   - Profit Factor: gross profit / gross loss, interpretation (>1.5 is good)
3. **Multi-Position Backtesting** — How `--max-positions` works, when to use it.
4. **Comparing Strategies** — Using `cryplative compare` to evaluate multiple strategies.
5. **Common Pitfalls** — Overfitting, look-ahead bias, survivorship bias, insufficient data.
6. **Result Files** — Where results are saved, JSON format, how to programmatically read them.

### 10.5 `platform/docs/indicators.md`

**Title**: Technical Indicators Reference

**Sections**: For each indicator function:
1. Name and brief description
2. Function signature
3. Parameters with defaults
4. Return format (explain None values for warmup period)
5. Simple usage example
6. Common trading patterns using this indicator

Indicators to document: SMA, EMA, RSI, MACD, Bollinger Bands.

---

## 11. Implementation Order

The developer MUST implement in this exact order, committing after each milestone:

| Step | What to implement | Commit message |
|------|-------------------|----------------|
| 1 | Common indicators library (`indicators.py`) with SMA, EMA, RSI, MACD, Bollinger Bands + comprehensive tests | `feat: add common technical indicators library` |
| 2 | Refactor SMA Crossover to use shared indicators library | `refactor: move compute_sma to shared indicators library` |
| 3 | Multi-position support in PortfolioTracker + BacktestEngine (backward compatible) + tests | `feat: add multi-position support to backtesting engine` |
| 4 | Strategy template file (`_template.py`) + auto-discovery in `strategies/__init__.py` + tests | `feat: add strategy template and auto-discovery` |
| 5 | `cryplative new-strategy` CLI command + tests | `feat: add new-strategy scaffold command` |
| 6 | RSI strategy + tests | `feat: add RSI mean-reversion strategy` |
| 7 | MACD strategy + tests | `feat: add MACD crossover strategy` |
| 8 | Bollinger Bands strategy + tests | `feat: add Bollinger Bands strategy` |
| 9 | CLI enhancements (`compare` command, `--max-positions`, `--params` from file, `strategies --verbose`, `default_parameters` on Strategy ABC) + tests | `feat: enhance CLI with compare command and improved UX` |
| 10 | Robustness improvements (input validation, error handling, retry logic, edge cases) + tests | `feat: improve error handling, validation, and robustness` |
| 11 | Researcher documentation (`getting-started.md`, `writing-strategies.md`, `cli-reference.md`, `backtesting-guide.md`, `indicators.md`) | `docs: add comprehensive researcher documentation` |
| 12 | End-to-end researcher workflow validation test | `feat: add end-to-end researcher workflow test` |

---

## 12. Testing Requirements

### Coverage Target: 85%+

(Raised from 80% in Phase 1 since the codebase is maturing.)

### New Test Files

```
tests/
├── conftest.py              # Update: add new fixtures for multi-position, indicators
├── test_models.py           # Existing — no changes expected
├── test_market_fetcher.py   # Existing — add retry logic tests
├── test_strategies.py       # Update: test all 4 strategies + registry auto-discovery
├── test_backtesting.py      # Update: multi-position tests, regression tests
├── test_portfolio.py        # Update: multi-position tracker tests
├── test_indicators.py       # NEW: comprehensive indicator computation tests
├── test_cli.py              # NEW: CLI command tests (new-strategy, compare, validation)
└── test_workflow.py         # NEW: end-to-end researcher workflow test
```

### Key Test Scenarios

**test_indicators.py**:
- Each indicator computes correctly against known hand-calculated values
- None values returned for warmup period
- Edge cases: empty input, single value, period > len(data)
- Return list length matches input length
- SMA matches original implementation (regression)

**test_strategies.py** (updated):
- All 4 strategies: SMA, RSI, MACD, Bollinger Bands
- Each strategy: no signal with insufficient data, correct signal on trigger, no signal without trigger
- Auto-discovery finds all 4 strategies + skips `_template`
- `default_parameters()` returns correct defaults for each strategy

**test_backtesting.py** (updated):
- Single-position mode (max_positions=1) matches Phase 1 results (regression)
- Multi-position mode opens/closes correctly
- FIFO closing order verified
- Capital constraint: cannot open position without sufficient capital
- All 4 strategies produce valid backtest results

**test_cli.py** (new):
- `new_strategy` creates file with correct content
- `new_strategy` errors on duplicate name
- `compare` loads and displays multiple results
- `compare` handles missing/invalid files gracefully
- `backtest --params file.json` reads from file
- `backtest --max-positions 3` works
- `strategies --verbose` shows parameters
- Input validation: bad symbol, bad interval, bad dates, unknown strategy

**test_workflow.py** (new):
- Full researcher workflow: scaffold → implement → backtest → compare
- Simulated: create strategy, inject test implementation, run backtest, verify results

---

## 13. Acceptance Criteria

This phase is complete when ALL of the following are true:

### Framework Validation
- [ ] `cryplative strategies` lists 4 strategies: sma_crossover, rsi, macd, bollinger_bands
- [ ] `cryplative strategies --verbose` shows default parameters for each strategy
- [ ] All 4 strategies produce valid backtest results on BTC/USDT 1h data
- [ ] Multi-position backtesting works (max_positions > 1)
- [ ] Single-position backtesting produces same results as Phase 1 (regression)

### Developer Experience
- [ ] `cryplative new-strategy test_strategy` creates a working strategy file
- [ ] The created strategy appears in `cryplative strategies` immediately
- [ ] A researcher can implement `generate_signal()` and run a backtest in under 5 minutes (validated by workflow test)
- [ ] `cryplative compare` shows side-by-side metrics for multiple result files

### Quality
- [ ] All tests pass with `uv run pytest`
- [ ] Test coverage >= 85%
- [ ] `uv run ruff check .` passes with no errors
- [ ] `uv run mypy src/` passes with no errors

### Documentation
- [ ] `platform/docs/getting-started.md` exists and is complete
- [ ] `platform/docs/writing-strategies.md` exists with full working examples
- [ ] `platform/docs/cli-reference.md` covers all 5 CLI commands
- [ ] `platform/docs/backtesting-guide.md` explains metrics and multi-position
- [ ] `platform/docs/indicators.md` documents all 5 indicator functions

---

## 14. Out of Scope (For This Spec)

These are explicitly NOT part of Phase 2:

- Paper trading / simulated live execution (Phase 3)
- Real money execution / order placement (Phase 3)
- Async data fetching (Phase 3)
- WebSocket / streaming data (Phase 3+)
- Strategy parameter optimization / grid search (Phase 5)
- Bun.js API (Phase 4)
- React webapp (Phase 4)
- Database integration (Phase 4+)
- Docker / deployment
- CI/CD pipeline
- Multi-symbol strategies (each strategy trades one symbol at a time)

---

*This specification is self-contained. The platform-developer should be able to implement everything described here by building on the Phase 1 codebase from SPEC-000.*
