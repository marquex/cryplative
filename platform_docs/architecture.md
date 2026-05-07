# Cryplative Platform — Architecture Overview

**Audience**: Any agent or developer who needs to understand how the trading platform works.
**Last updated**: 2026-05-07

---

## What Is the Platform?

The Cryplative platform is a Python-based system for researching, testing, and executing crypto trading strategies. It lives in `platform/src/cryplative/` and is managed via a CLI (`cryplative`).

The core loop is simple: **fetch market data → feed it to a strategy → get signals → execute trades → track results**.

---

## Key Components

### Data Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| **MarketFetcher** | `market_fetcher/fetcher.py` | Pulls OHLCV candle data from Binance via ccxt. Handles rate limiting, caching, and pagination. |
| **Market Cache** | `market_fetcher/cache.py` | File-based JSON cache. One file per symbol+interval at `data/market_cache/`. Deduplicates by `open_time`. |

### Strategy Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| **Strategy ABC** | `core/interfaces.py` | The universal contract. Every strategy implements `strategy_id`, `strategy_name`, `initialize()`, `generate_signal()`, and `teardown()`. |
| **Strategy Registry** | `strategies/registry.py` | `@StrategyRegistry.register` decorator. Strategies auto-register on import. |
| **Auto-Discovery** | `strategies/__init__.py` | Uses `pkgutil` to import all strategy modules. Files starting with `_` are skipped (template). |
| **Indicators Library** | `strategies/indicators.py` | Pure functions: `compute_sma`, `compute_ema`, `compute_rsi`, `compute_macd`, `compute_bollinger_bands`. Take `list[float]`, return `list[float \| None]`. |
| **Strategy Template** | `strategies/_template.py` | Scaffold for new strategies. Copied by `cryplative new-strategy <name>`. |

### Execution Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| **BacktestEngine** | `backtesting/engine.py` | Simulates running a strategy over historical data. Supports multi-position via `max_positions` config. |
| **PortfolioTracker** | `portfolio/tracker.py` | Tracks capital, open/closed trades, equity curve during a run. FIFO closing for multi-position. |

### CLI

| Component | Location | Purpose |
|-----------|----------|---------|
| **CLI** | `cli.py` | Typer-based CLI with commands: `backtest`, `fetch`, `strategies`, `new-strategy`, `compare`. |

### Core Models

All data shapes are Pydantic v2 models in `core/models.py`:

- **Candle** — OHLCV bar with symbol, interval, timestamps
- **Signal** — BUY/SELL with direction, order type, quantity, confidence, stop_loss, take_profit
- **Trade** — Records a trade with entry/exit prices, PnL, status (OPEN/CLOSED/CANCELLED), and context (BACKTEST/PAPER/REAL)
- **StrategyConfig** — Strategy identity, parameters, and state
- **StrategyResult** — Full result of a strategy run with trades and performance metrics

---

## Data Flow

```
User runs: cryplative backtest --strategy sma_crossover --symbol BTC/USDT ...

    1. CLI parses args → BacktestConfig
    2. MarketFetcher.get_candles() → check cache → fetch from Binance → cache → return candles
    3. BacktestEngine.run(config):
       a. Resolve strategy from registry
       b. Iterate candles chronologically with sliding window
       c. For each candle: strategy.generate_signal(window) → Signal or None
       d. Signal BUY + can_open → PortfolioTracker.open_position()
       e. Signal SELL + has open trades → PortfolioTracker.close_oldest() (FIFO)
       f. Track equity at each step
       g. Force-close remaining open positions at end
       h. Calculate metrics (return, Sharpe, drawdown, win rate, profit factor)
    4. Save StrategyResult as JSON to data/strategy_results/
    5. Print summary table to console
```

---

## File Layout

```
cryplative/                   # Project root
├── .venv/                    # Root virtual environment (uv-managed Python 3.12)
│                              #   source .venv/bin/activate → import cryplative anywhere
├── .gitignore                # Includes .venv/
├── platform/                 # Platform source code (engineering domain)
│   ├── src/cryplative/       # Python package (installed as editable into root .venv)
│   │   ├── cli.py            # CLI entry point
│   │   ├── config.py         # Pydantic settings
│   │   ├── core/
│   │   │   ├── models.py     # All Pydantic data models
│   │   │   ├── interfaces.py # Strategy, DataProvider, ExecutionHandler ABCs
│   │   │   └── exceptions.py # Custom exceptions
│   │   ├── market_fetcher/
│   │   │   ├── fetcher.py    # MarketFetcher (ccxt + Binance)
│   │   │   └── cache.py      # JSON file cache
│   │   ├── strategies/
│   │   │   ├── indicators.py # Pure indicator functions (SMA, EMA, RSI, MACD, BB)
│   │   │   ├── registry.py   # StrategyRegistry
│   │   │   ├── _template.py  # Strategy scaffold template
│   │   │   ├── sma_crossover.py
│   │   │   ├── rsi.py
│   │   │   ├── macd.py
│   │   │   └── bollinger_bands.py
│   │   ├── backtesting/
│   │   │   └── engine.py     # BacktestEngine + BacktestConfig
│   │   └── portfolio/
│   │       └── tracker.py    # PortfolioTracker
│   ├── tests/                # pytest test suite
│   ├── data/                 # Runtime data (gitignored)
│   │   ├── market_cache/     # Cached candle JSON files
│   │   └── strategy_results/ # Backtest result JSON files
│   └── pyproject.toml        # uv project config
├── data/                     # Research team workspace (research domain)
├── platform_docs/            # Documentation for all agents
│   ├── architecture.md       # This file
│   ├── getting-started.md    # Setup and first backtest
│   ├── public-api.md         # Public API contract for programmatic use
│   ├── writing-strategies.md # How to create new strategies
│   ├── cli-reference.md      # All CLI commands
│   ├── backtesting-guide.md  # Backtesting deep-dive
│   └── indicators.md         # Indicator function reference
└── .agentic/                 # Agent configuration and expertise
```

---

## Available Strategies

| ID | Name | Type | Key Parameters |
|----|------|------|----------------|
| `sma_crossover` | SMA Crossover | Trend-following | fast_period=10, slow_period=20 |
| `rsi` | RSI Mean Reversion | Mean-reversion | period=14, oversold=30, overbought=70 |
| `macd` | MACD Crossover | Trend-following | fast_period=12, slow_period=26, signal_period=9 |
| `bollinger_bands` | Bollinger Bands Reversion | Volatility-based | period=20, num_std=2.0 |

---

## Key Abstractions

### Strategy Protocol (the most important one)

Every strategy implements the same interface. This ensures any strategy can run in any execution mode (backtest, paper, real):

```python
class Strategy(ABC):
    @property
    def strategy_id(self) -> str: ...

    @property
    def strategy_name(self) -> str: ...

    def initialize(self, config: StrategyConfig) -> None: ...

    def generate_signal(self, candles: list[Candle]) -> Signal | None: ...

    def teardown(self) -> None: ...
```

### Data Provider

Abstracts market data access. Currently only `MarketFetcher` implements it, but the interface allows swapping in other data sources:

```python
class DataProvider(ABC):
    def get_candles(self, symbol, interval, start_time=None, end_time=None, limit=None) -> list[Candle]: ...
```

### Execution Handler

Abstracts trade execution. Will be implemented by BacktestEngine, PaperTrader, and RealTrader:

```python
class ExecutionHandler(ABC):
    def submit_signal(self, signal: Signal) -> Trade: ...
    def close_trade(self, trade: Trade, price: float, timestamp: int) -> Trade: ...
```

---

## Quick Start

```bash
# Activate the root virtual environment (from project root)
source .venv/bin/activate

# List available strategies
cryplative strategies

# Fetch market data
cryplative fetch --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01

# Run a backtest
cryplative backtest --strategy sma_crossover --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01

# Use programmatically in Python
python -c "from cryplative.backtesting.engine import BacktestEngine; print('OK')"
```

> **Alternative**: For platform development (inside `platform/`), use `uv run` instead.
> See [Getting Started](getting-started.md) for the two usage modes.

---

## Development Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Foundation | Complete | Models, interfaces, MarketFetcher, SMA strategy, backtesting, CLI |
| Phase 2: Researcher-Ready | Complete | Indicators library, multi-position, 3 more strategies, template system, docs |
| Phase 3: Live Simulation | Planned | Paper trading, async data feeds, strategy state persistence |
| Phase 4: Monitoring & Control | Planned | Bun.js API, React webapp |
| Phase 5: Optimization | Planned | Parameter tuning, strategy ensembles, advanced analytics |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Platform | Python 3.11+ (Pydantic, ccxt, numpy, typer, rich, structlog) |
| API (Phase 4) | Bun.js |
| Frontend (Phase 4) | React + Vite + shadcn/ui |
| Exchange | Binance (via ccxt, adapter pattern for future exchanges) |
| Storage | File-based JSON (abstracted for future DB migration) |
