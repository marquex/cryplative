# CLI Reference

## cryplative strategies

List all registered strategies.

```bash
uv run cryplative strategies
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--verbose` | `false` | Show default parameters for each strategy |

### Examples

```bash
# List strategies
uv run cryplative strategies

# Show parameters
uv run cryplative strategies --verbose
```

---

## cryplative fetch

Fetch and cache market data from the exchange.

```bash
uv run cryplative fetch --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01
```

### Flags

| Flag | Required | Description |
|------|----------|-------------|
| `--symbol` | Yes | Trading pair in `BASE/QUOTE` format (e.g., `BTC/USDT`) |
| `--interval` | Yes | Candle interval: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w` |
| `--start` | Yes | Start date in ISO 8601 format (e.g., `2025-01-01`) |
| `--end` | Yes | End date in ISO 8601 format |

### Examples

```bash
# Fetch hourly BTC data
uv run cryplative fetch --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01

# Fetch daily ETH data
uv run cryplative fetch --symbol ETH/USDT --interval 1d --start 2024-01-01 --end 2025-01-01
```

---

## cryplative backtest

Run a backtest with a strategy against historical data.

```bash
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--strategy` | Required | Strategy ID (must be registered) |
| `--symbol` | Required | Trading pair in `BASE/QUOTE` format |
| `--interval` | Required | Candle interval |
| `--start` | Required | Start date (ISO 8601) |
| `--end` | Required | End date (ISO 8601) |
| `--capital` | `10000.0` | Initial capital for the simulation |
| `--params` | `{}` | Strategy parameters as JSON string or path to `.json` file |
| `--max-positions` | `1` | Maximum concurrent open positions |

### Examples

```bash
# Basic backtest
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01

# Custom parameters
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --params '{"fast_period": 5, "slow_period": 20}'

# Parameters from file
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --params my_params.json

# Multi-position
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --max-positions 3 \
    --capital 100000

# Custom capital
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --capital 50000
```

### Output

The command displays:
- A metrics table with key performance indicators
- A trades table with entry/exit prices and P&L for each trade
- Results are saved as JSON to `data/strategy_results/`

---

## cryplative new-strategy

Scaffold a new strategy from the template.

```bash
uv run cryplative new-strategy my_strategy
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Strategy name in `snake_case` (letters, numbers, underscores) |

### Examples

```bash
# Create a new strategy
uv run cryplative new-strategy rsi_divergence
```

This creates `src/cryplative/strategies/rsi_divergence.py` with boilerplate code. The strategy is automatically registered.

---

## cryplative compare

Compare backtest results from multiple JSON files.

```bash
uv run cryplative compare result_a.json result_b.json result_c.json
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `files` | Yes | One or more paths to strategy result JSON files |

### Output

A comparison table with columns for each strategy and rows for each metric:

| Metric | Strategy A | Strategy B |
|--------|-----------|-----------|
| Total Return | +15.3% | +8.2% |
| Sharpe Ratio | 1.24 | 0.85 |
| Max Drawdown | -8.5% | -12.3% |
| Win Rate | 55.0% | 48.0% |
| Total Trades | 20 | 35 |
| Profit Factor | 1.80 | 1.20 |

Best values are highlighted in green, worst in red.
