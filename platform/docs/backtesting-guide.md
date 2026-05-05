# Backtesting Guide

## How Backtesting Works

The backtest engine simulates running a strategy against historical data through a simple loop:

1. **Load candles** — fetch historical OHLCV data for the requested symbol and interval
2. **Iterate** — for each candle, build a sliding window of the last `lookback_window` candles
3. **Generate signal** — pass the window to the strategy's `generate_signal()` method
4. **Execute trade** — if a BUY signal and positions available, open a position; if SELL and positions open, close the oldest
5. **Track equity** — record equity at each candle for the equity curve
6. **Force close** — at the end, close any remaining open positions
7. **Calculate metrics** — compute performance metrics from the equity curve and trades

## Understanding Metrics

### Total Return

The percentage change in equity from start to end of the backtest.

```
Total Return = (Final Equity - Initial Capital) / Initial Capital * 100
```

- **Positive** = profitable strategy
- **Negative** = losing strategy
- A 10% annual return is modest; 50%+ may indicate overfitting

### Sharpe Ratio

Risk-adjusted return. Measures excess return per unit of risk (volatility).

- **< 0**: Strategy loses money on average
- **0 - 1**: Acceptable but not great
- **1 - 2**: Good risk-adjusted returns
- **> 2**: Excellent (suspiciously high may indicate overfitting)

The calculation uses trade returns with annualization: `Sharpe = (mean_return / std_return) * sqrt(n)`.

### Max Drawdown

The worst peak-to-trough decline in equity during the backtest, expressed as a percentage.

```
Max Drawdown = min((Equity - Peak) / Peak * 100)
```

Always negative (or zero). A -10% max drawdown means at some point, equity dropped 10% from its highest point.

- **-5% to -15%**: Reasonable for most strategies
- **> -30%**: Very risky

### Win Rate

Percentage of closed trades that were profitable.

- **> 55%**: Good for most strategies
- **< 45%**: Hard to be profitable unless winners are much larger than losers

### Profit Factor

Ratio of gross profit to gross loss.

```
Profit Factor = Total Winning P&L / |Total Losing P&L|
```

- **> 1.5**: Good
- **> 2.0**: Very good
- **< 1.0**: Losing money

### Total Trades

The total number of closed trades. More trades generally means more statistical significance, but too many trades may indicate excessive trading (high fees).

## Multi-Position Backtesting

Use `--max-positions` to allow multiple concurrent open positions:

```bash
uv run cryplative backtest \
    --strategy sma_crossover \
    --symbol BTC/USDT \
    --interval 1h \
    --start 2025-01-01 \
    --end 2025-06-01 \
    --max-positions 3
```

- **Default (`max-positions=1`)**: Only one position at a time. Backward compatible with Phase 1.
- **`max-positions > 1`**: The strategy can open multiple positions. SELL signals close the **oldest** position (FIFO).

Multi-position backtesting is useful for:
- Strategies that generate frequent signals
- Portfolio-level approaches
- Scaling into/out of positions

## Comparing Strategies

Use `cryplative compare` to evaluate multiple strategies side by side:

```bash
# Run two backtests
uv run cryplative backtest --strategy sma_crossover --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01
uv run cryplative backtest --strategy rsi --symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01

# Compare the results
uv run cryplative compare data/strategy_results/sma_crossover_*.json data/strategy_results/rsi_*.json
```

The comparison table highlights the best value in green and worst in red for each metric.

## Common Pitfalls

### Overfitting

Tuning parameters to perfectly match historical data. Signs: extremely high returns that don't hold on new data. Mitigation: use out-of-sample testing.

### Look-Ahead Bias

Using future information in signal generation (e.g., looking at candle close to decide to trade at candle open). The engine always uses the current candle's close price for execution, so as long as your signal is based on completed candles, this is avoided.

### Insufficient Data

Short backtest periods produce unreliable results. Aim for at least 100+ candles, preferably 500+.

### Survivorship Bias

Only testing on assets that "survived" (didn't go to zero). Test on a variety of assets and time periods.

## Result Files

Backtest results are saved as JSON files in `data/strategy_results/`. Each file contains:

- `strategy_id`: The strategy used
- `start_date` / `end_date`: The backtest period
- `parameters`: Strategy parameters used
- `trades`: List of all trades (open and closed) with entry/exit prices, P&L
- `metrics`: Performance metrics (total return, Sharpe ratio, etc.)
- `created_at`: When the backtest was run

You can load results programmatically:

```python
from cryplative.core.models import StrategyResult
import json

with open("data/strategy_results/result.json") as f:
    data = json.load(f)

result = StrategyResult.model_validate(data)
print(f"Return: {result.metrics.total_return:.2f}%")
```
