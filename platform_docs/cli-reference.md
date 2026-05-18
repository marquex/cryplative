# CLI Reference

The `cryplative` CLI is available after activating the root virtual environment:

```bash
source .venv/bin/activate
cryplative <command> [options]
```

Alternatively, from inside `platform/`, use `uv run cryplative <command>`.

---

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
| `--catalog` | `false` | Save result to the strategy catalog after backtest |
| `--hypothesis` | — | Hypothesis ID tag (e.g., `H2`) |
| `--experiment` | — | Experiment batch ID (e.g., `sweep_20260518`) |
| `--data-split` | `FULL` | Data split: `TRAIN`, `TEST`, `FULL`, `OUT_OF_SAMPLE` |
| `--train-result` | — | ID of the training result (for TEST splits) |
| `--verdict` | — | Verdict tag: `PASS`, `FAIL`, or `MARGINAL` |

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

# Backtest with catalog integration
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --catalog \
    --hypothesis H2 \
    --data-split TEST
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

---

## cryplative results

Query and manage the strategy results catalog. The catalog is a lightweight SQLite index over the JSON result files in `data/strategy_results/`.

### Subcommands

#### `cryplative results list`

List strategy results from the catalog with optional filters.

```bash
uv run cryplative results list
uv run cryplative results list --symbol BTC/USDT --data-split TEST
uv run cryplative results list --min-sharpe 1.0 --limit 50
```

| Flag | Default | Description |
|------|---------|-------------|
| `--strategy` | — | Filter by strategy ID |
| `--hypothesis` | — | Filter by hypothesis ID |
| `--experiment` | — | Filter by experiment ID |
| `--symbol` | — | Filter by trading pair |
| `--interval` | — | Filter by interval |
| `--verdict` | — | Filter by verdict |
| `--data-split` | — | Filter by data split |
| `--min-sharpe` | — | Minimum Sharpe ratio threshold |
| `--min-return` | — | Minimum return (%) threshold |
| `--limit` | `20` | Maximum results to display |

#### `cryplative results best`

Show top N results by a given metric.

```bash
uv run cryplative results best --metric sharpe_ratio --top 5
uv run cryplative results best --metric total_return_pct --data-split TEST
```

| Flag | Default | Description |
|------|---------|-------------|
| `--metric` | `sharpe_ratio` | Metric to rank by |
| `--top` | `10` | Number of top results |
| `--strategy` | — | Filter by strategy |
| `--symbol` | — | Filter by symbol |
| `--hypothesis` | — | Filter by hypothesis |
| `--data-split` | — | Filter by data split |

#### `cryplative results show`

Display full details of a single result.

```bash
uv run cryplative results show 12
```

#### `cryplative results compare`

Compare results across multiple hypotheses.

```bash
uv run cryplative results compare H2 H5
uv run cryplative results compare H2 H5 --data-split TEST
```

| Flag | Default | Description |
|------|---------|-------------|
| `--metric` | `sharpe_ratio` | Metric to compare |
| `--data-split` | `TEST` | Data split filter |

#### `cryplative results summary`

Show catalog overview.

```bash
uv run cryplative results summary
```

#### `cryplative results rebuild`

Rebuild catalog by scanning the results directory.

```bash
uv run cryplative results rebuild
```

| Flag | Default | Description |
|------|---------|-------------|
| `--results-dir` | `data/strategy_results` | Results directory path |

#### `cryplative results tag`

Add or update hypothesis, experiment, verdict, or notes for a result.

```bash
uv run cryplative results tag 12 --hypothesis H2 --verdict PASS --notes "Strong on BTC"
```

#### `cryplative results delete`

Delete a result from the catalog (does NOT delete the JSON file).

```bash
uv run cryplative results delete 5
```

---

## Python API: ResultsCatalog

For programmatic use, the catalog is available as a Python class:

```python
from cryplative.catalog import ResultsCatalog

catalog = ResultsCatalog()  # defaults to data/catalog.db

# Query
results = catalog.find(symbol="BTC/USDT", data_split="TEST", min_sharpe=1.0)
best = catalog.best(metric="sharpe_ratio", n=5)
entry = catalog.get(12)

# Insert
row_id = catalog.insert_from_strategy_result(
    result, symbol="BTC/USDT", interval="4h",
    results_file="strategy_results/test.json",
    hypothesis_id="H2", data_split="TEST",
)

# Tag
catalog.tag(12, verdict="PASS", notes="Strong on BTC")

# Rebuild from existing files
catalog.rebuild()

# Export
df = catalog.to_dataframe()
```
