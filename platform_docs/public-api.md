# Public API Reference

**Audience**: Research team (algo-researchers, strategy developers) who use the platform programmatically.
**Last updated**: 2026-05-07

---

This document defines the **public API contract** — the set of modules, classes, and functions that the research team can rely on for programmatic access. These imports are stable within a phase and work from any directory after activating the root virtual environment.

## Setup

```bash
source .venv/bin/activate
python  # ready to import
```

No `sys.path` manipulation needed. All imports below work from any working directory.

---

## Data Models

**Module**: `cryplative.core.models`

```python
from cryplative.core.models import (
    Candle,            # OHLCV bar with symbol, interval, timestamps
    Signal,            # BUY/SELL with direction, order type, quantity, confidence
    SignalDirection,   # Enum: BUY, SELL
    OrderType,         # Enum: MARKET, LIMIT
    Trade,             # Records a trade with entry/exit prices, PnL, status
    TradeStatus,       # Enum: OPEN, CLOSED, CANCELLED
    TradeContext,      # Enum: BACKTEST, PAPER, REAL
    StrategyConfig,    # Strategy identity, parameters, state
    StrategyResult,    # Full result of a strategy run with trades + metrics
    BacktestMetrics,   # Performance metrics: return, Sharpe, drawdown, win rate, profit factor
)
```

### Key model fields

**Candle**:
- `symbol: str` — e.g., `"BTC/USDT"`
- `interval: str` — e.g., `"1h"`, `"4h"`, `"1d"`
- `open_time: int` — Unix timestamp in milliseconds
- `open: float`, `high: float`, `low: float`, `close: float`, `volume: float`
- `close_time: int`, `closed: bool`

**Signal**:
- `strategy_id: str`, `symbol: str`, `timestamp: int`
- `direction: SignalDirection` — `BUY` or `SELL`
- `order_type: OrderType` — `MARKET` or `LIMIT`
- `price: float | None` — required for LIMIT orders
- `quantity: float`, `stop_loss: float | None`, `take_profit: float | None`
- `confidence: float` — 0.0 to 1.0
- `metadata: dict` — strategy-specific data

**Trade**:
- `entry_price: float`, `exit_price: float | None`
- `quantity: float`, `pnl: float | None`
- `status: TradeStatus` — `OPEN`, `CLOSED`, `CANCELLED`
- `context: TradeContext` — `BACKTEST`, `PAPER`, `REAL`

**StrategyResult**:
- `strategy_id: str`, `start_date: str`, `end_date: str`
- `parameters: dict`, `trades: list[Trade]`
- `metrics: BacktestMetrics`
- `created_at: str`

---

## Strategy Interface

**Module**: `cryplative.core.interfaces`

```python
from cryplative.core.interfaces import Strategy
```

The abstract base class all strategies implement. For creating custom strategies, see [Writing Strategies](writing-strategies.md).

Key methods:
- `strategy_id: str` — unique identifier property
- `strategy_name: str` — human-readable name property
- `default_parameters() -> dict` — class method returning defaults
- `initialize(config: StrategyConfig) -> None` — called before running
- `generate_signal(candles: list[Candle]) -> Signal | None` — core logic
- `teardown() -> None` — called after run completes

---

## Strategy Registry

**Module**: `cryplative.strategies.registry`

```python
from cryplative.strategies.registry import StrategyRegistry
```

- `StrategyRegistry.register` — decorator to auto-register strategy classes
- `StrategyRegistry.get(strategy_id: str) -> type[Strategy]` — look up a strategy by ID
- `StrategyRegistry.list_strategies() -> list[type[Strategy]]` — get all registered strategies
- `StrategyRegistry.clear() -> None` — clear registry (used in tests)

---

## Technical Indicators

**Module**: `cryplative.strategies.indicators`

```python
from cryplative.strategies.indicators import (
    compute_sma,             # Simple Moving Average
    compute_ema,             # Exponential Moving Average
    compute_rsi,             # Relative Strength Index
    compute_macd,            # MACD (returns 3 lists)
    compute_bollinger_bands, # Bollinger Bands (returns 3 lists)
)
```

All indicators are **pure functions**: `list[float] -> list[float | None]`. Same length as input, `None` during warmup period. See [Indicators Reference](indicators.md) for full details.

### Quick examples

```python
closes = [44000, 44500, 44200, 44800, 45000, 45200, 44900]

# SMA
sma = compute_sma(closes, period=3)       # [None, None, 44233.3, ...]

# EMA
ema = compute_ema(closes, period=3)       # [None, None, 44233.3, ...]

# RSI (default period=14)
rsi = compute_rsi(closes, period=5)       # [None, ..., 100.0]

# MACD (returns tuple of 3 lists)
macd_line, signal_line, histogram = compute_macd(closes)

# Bollinger Bands (returns tuple of 3 lists)
upper, middle, lower = compute_bollinger_bands(closes, period=20, num_std=2.0)
```

---

## Market Data Fetching

**Module**: `cryplative.market_fetcher.fetcher`

```python
from cryplative.market_fetcher.fetcher import MarketFetcher
```

### Constructor

```python
fetcher = MarketFetcher()  # Uses default config (Binance)
```

### Key methods

```python
# Fetch candle data (uses cache, then API)
candles: list[Candle] = fetcher.get_candles(
    symbol="BTC/USDT",
    interval="1h",
    start_time=None,   # Optional: Unix ms timestamp
    end_time=None,     # Optional: Unix ms timestamp
    limit=None,        # Optional: max candles to return
)

# List all available trading pairs on the exchange
pairs: list[dict] = fetcher.list_pairs()
# Returns: [{"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT"}, ...]
```

### Caching

Data is automatically cached as JSON files in `data/market_cache/`. Subsequent requests for the same symbol+interval use the cache and only fetch new data. Cache is transparent — no configuration needed.

---

## Backtesting Engine

**Module**: `cryplative.backtesting.engine`

```python
from cryplative.backtesting.engine import BacktestEngine, BacktestConfig
```

### Programmatic backtest

```python
from datetime import datetime

config = BacktestConfig(
    strategy_id="sma_crossover",
    symbol="BTC/USDT",
    interval="1h",
    start_date="2025-01-01",
    end_date="2025-06-01",
    initial_capital=10000.0,
    max_positions=1,
    parameters={"fast_period": 10, "slow_period": 20},
)

engine = BacktestEngine()
result: StrategyResult = engine.run(config)

print(f"Return: {result.metrics.total_return:.2f}%")
print(f"Sharpe: {result.metrics.sharpe_ratio:.2f}")
print(f"Trades: {len(result.trades)}")
```

### Parameter sweeps

The programmatic API enables parameter optimization:

```python
results = {}
for fast in [5, 10, 15]:
    for slow in [20, 30, 50]:
        if fast >= slow:
            continue
        config = BacktestConfig(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-06-01",
            parameters={"fast_period": fast, "slow_period": slow},
        )
        result = engine.run(config)
        results[(fast, slow)] = result.metrics.total_return

# Find best parameters
best = max(results, key=results.get)
print(f"Best: fast={best[0]}, slow={best[1]}, return={results[best]:.2f}%")
```

### BacktestConfig fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy_id` | `str` | required | Registered strategy ID |
| `symbol` | `str` | required | Trading pair (e.g., `"BTC/USDT"`) |
| `interval` | `str` | required | Candle interval (e.g., `"1h"`, `"4h"`) |
| `start_date` | `str` | required | Start date (ISO 8601) |
| `end_date` | `str` | required | End date (ISO 8601) |
| `initial_capital` | `float` | `10000.0` | Starting capital |
| `max_positions` | `int` | `1` | Max concurrent open positions |
| `parameters` | `dict` | `{}` | Strategy-specific parameters |

---

## Portfolio Tracker

**Module**: `cryplative.portfolio.tracker`

```python
from cryplative.portfolio.tracker import PortfolioTracker
```

Tracks capital, open/closed trades, and equity curve during a strategy run. Normally used internally by the backtest engine, but available for custom execution loops.

Key methods:
- `can_open_position() -> bool` — checks if `max_positions` allows it
- `open_position(signal, price, timestamp) -> Trade` — open a new position
- `close_oldest(price, timestamp) -> Trade` — close the oldest open position (FIFO)
- `close_all(price, timestamp) -> list[Trade]` — close all open positions
- `equity: float` — current equity (cash + unrealized PnL)

---

## Complete Import Map

For quick reference, here are all stable public imports:

```python
# Data models
from cryplative.core.models import (
    Candle, Signal, SignalDirection, OrderType,
    Trade, TradeStatus, TradeContext,
    StrategyConfig, StrategyResult, BacktestMetrics,
)

# Strategy interface
from cryplative.core.interfaces import Strategy

# Strategy registry
from cryplative.strategies.registry import StrategyRegistry

# Technical indicators
from cryplative.strategies.indicators import (
    compute_sma, compute_ema, compute_rsi,
    compute_macd, compute_bollinger_bands,
)

# Market data
from cryplative.market_fetcher.fetcher import MarketFetcher

# Backtesting
from cryplative.backtesting.engine import BacktestEngine, BacktestConfig

# Portfolio tracking
from cryplative.portfolio.tracker import PortfolioTracker
```

All 22 modules in the `cryplative` package are importable. The above list represents the **intended public surface** for the research team. Internal modules (`core.exceptions`, `config`, `cli`, cache internals) may change between phases.

---

## Stability Guarantees

- **Within a phase**: All public imports listed above are stable. Function signatures, model fields, and return types will not change.
- **Between phases**: Breaking changes are possible but will be documented in release notes. Models use Pydantic v2 — `model_validate()` handles migration for added/removed fields gracefully.
- **Internal modules**: Anything not listed above is internal and may change without notice.

## Known Limitations (Current Phase)

- **No fee modeling** — backtests do not account for trading fees (planned for Phase 2.5)
- **No slippage modeling** — execution price is exact candle close
- **No multi-timeframe** — strategies receive one interval at a time
- **SL/TP not auto-triggered** — stop loss and take profit are recorded on signals but not enforced by the engine
- **Synchronous only** — no async data feeds yet (Phase 3)
