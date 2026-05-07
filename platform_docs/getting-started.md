# Getting Started with Cryplative Platform

## Prerequisites

- **Python 3.12+** — provided automatically by the root virtual environment (uv-managed)
- **uv** — fast Python package manager (`pip install uv`)
- **git** — version control

## Installation

The project uses a **root-level virtual environment** at `.venv/` with an editable install of the `cryplative` package. This means the platform is importable from **anywhere** in the project — no `sys.path` hacks needed.

### Step 1: Create the root virtual environment

From the project root (`cryplative/`):

```bash
source .venv/bin/activate
```

> **If the venv does not exist yet**, run the setup script:
> ```bash
> bash .agentic/expertise/cto/setup-venv.sh
> ```
> This creates `.venv/`, installs the platform as editable, and verifies all imports.

### Step 2: Verify installation

```bash
# With activated venv
cryplative strategies
```

Or without activating:

```bash
# Using the venv Python directly
.venv/bin/python -m cryplative.cli strategies
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

### Step 3: Verify Python imports

```bash
source .venv/bin/activate
python -c "from cryplative.core.models import Candle; print('Imports working!')"
```

## Two Usage Modes

### Mode A: Root venv (recommended for research & scripting)

Activate the venv once, then work from anywhere in the project tree:

```bash
source .venv/bin/activate

# CLI commands work directly
cryplative strategies
cryplative fetch --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01

# Python imports work from any directory
python -c "from cryplative.backtesting.engine import BacktestEngine; print('OK')"
```

This is the **recommended mode for the research team**. Clean imports like `from cryplative.strategies.indicators import compute_rsi` work from `data/`, `research/`, or any other directory without path manipulation.

### Mode B: Platform-local uv (for platform development)

If you are working **inside** the `platform/` directory on platform code itself:

```bash
cd platform
uv run cryplative strategies
uv run pytest
```

This uses the platform's own `pyproject.toml` and manages its own environment. Use this mode when developing the platform, not when using it.

> **Important**: Do NOT mix modes. If you activated the root venv, run `deactivate` before using `cd platform; uv run`.

## Your First Backtest

### 1. Fetch market data

```bash
source .venv/bin/activate
cryplative fetch --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01
```

### 2. Run a backtest

```bash
cryplative backtest \
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

- **[Public API Reference](public-api.md)** — the definitive import contract for programmatic use
- **[Writing Strategies](writing-strategies.md)** — learn how to implement your own strategies
- **[CLI Reference](cli-reference.md)** — full documentation of all CLI commands
- **[Backtesting Guide](backtesting-guide.md)** — understanding metrics and best practices
- **[Indicators Reference](indicators.md)** — available technical indicator functions
