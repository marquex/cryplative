# Getting Started with Cryplative Platform

## Prerequisites

- **Python 3.11+** — required for type hints and modern syntax
- **uv** — fast Python package manager (`pip install uv`)
- **git** — version control

## Installation

```bash
cd platform
uv sync
```

This installs all dependencies including development tools (pytest, ruff, mypy).

## Verify Installation

```bash
uv run cryplative strategies
```

You should see a table listing the available strategies:

```
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ Strategy ID      ┃ Name                 ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ bollinger_bands  │ Bollinger Bands Reversion │
│ macd             │ MACD Crossover       │
│ rsi              │ RSI Mean Reversion   │
│ sma_crossover    │ SMA Crossover        │
└─────────────────┴──────────────────────┘
```

## Your First Backtest

### 1. Fetch market data

```bash
uv run cryplative fetch \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01
```

### 2. Run a backtest

```bash
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01
```

### What Happens

The backtest engine simulates running the strategy against historical data:

1. **Loads** the cached candle data for the requested symbol and interval
2. **Iterates** through each candle, building a sliding window
3. **Generates signals** — the strategy analyzes the window and produces BUY/SELL signals
4. **Executes trades** — signals trigger position opens/closes
5. **Calculates metrics** — total return, Sharpe ratio, max drawdown, win rate, etc.
6. **Saves results** — a JSON file is written to `data/strategy_results/`

You'll see a results table with key metrics and a trades table with each trade's entry/exit price and P&L.

## Next Steps

- **[Writing Strategies](writing-strategies.md)** — learn how to implement your own strategies
- **[CLI Reference](cli-reference.md)** — full documentation of all CLI commands
- **[Backtesting Guide](backtesting-guide.md)** — understanding metrics and best practices
- **[Indicators Reference](indicators.md)** — available technical indicator functions
