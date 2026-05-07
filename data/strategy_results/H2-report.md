# H2: RSI Divergence with Trend Filter — Backtest Report

**Generated**: 2026-05-07T16:16:02.534481+00:00
**Strategy ID**: h2_rsi_divergence_trend

## 0. Parameter Adjustment Note

The spec defaults (`pivot_window=5, min_pivot_spacing=10, oversold_threshold=40`)
produced only **1 divergence signal** across the entire BTC/USDT 4h dataset.
This matches the spec's anticipated failure mode: *"Too few signals: Divergence is rare."*

After sweeping the spec's parameter ranges, the following adjusted defaults were
selected to produce sufficient trade counts for statistical validity:

| Parameter | Spec Default | Adjusted | Rationale |
|-----------|-------------|----------|-----------|
| `pivot_window` | 5 | **3** | Smaller window detects more granular pivots |
| `min_pivot_spacing` | 10 | **5** | Allows closer pivots, more divergence candidates |
| `oversold_threshold` | 40 | **50** | RSI rarely drops below 40 in uptrends; 50 captures pullbacks |

Result: ~38 potential divergences in BTC training period (vs 1 with spec defaults).

## 1. Strategy Parameters (Adjusted Defaults)

| Parameter | Value |
|-----------|-------|
| `sma_period` | `200` |
| `rsi_period` | `14` |
| `oversold_threshold` | `50` |
| `overbought_exit` | `70` |
| `stop_loss_pct` | `0.05` |
| `take_profit_pct` | `0.1` |
| `pivot_window` | `3` |
| `min_pivot_spacing` | `5` |
| `assumed_capital` | `10000.0` |
| `risk_per_trade` | `0.1` |

| Interval Override | `max_holding_candles` |
|-------------------|----------------------|
| `4h` | `50` |
| `1d` | `20` |

## 2. Results Summary

| Config | Raw Ret | Fee-Adj Ret | Sharpe | Max DD | Win% | Trades | PF |
|--------|--------|------------|--------|--------|------|--------|----|
| BTC_4h_train | +2.56% | +2.44% | 2.45 | -0.17% | 66.7 | 6 | 14.9331 |
| BTC_4h_test | +0.09% | +0.03% | 0.03 | -0.53% | 66.7 | 3 | 1.0539 |
| ETH_4h_train | +0.01% | -0.03% | -0.02 | -0.83% | 50.0 | 2 | 0.9694 |
| ETH_4h_test | +0.28% | +0.22% | 0.25 | -0.43% | 33.3 | 3 | 1.4946 |
| BTC_1d_train | +1.01% | +0.99% | 0.00 | 0.00% | 100.0 | 1 | inf |
| BTC_1d_test | +0.00% | +0.00% | 0.00 | 0.00% | 0.0 | 0 | 0.0 |
| SOL_4h_train | +1.11% | +0.97% | 0.51 | -1.21% | 42.9 | 7 | 1.7138 |
| SOL_4h_test | -0.40% | -0.44% | -1.44 | -0.44% | 0.0 | 2 | 0.0 |
| LINK_4h_train | +0.90% | +0.78% | 0.63 | -0.38% | 16.7 | 6 | 3.0356 |
| LINK_4h_test | +0.08% | +0.04% | 0.03 | -0.62% | 50.0 | 2 | 1.06 |
| ETH_1d_train | +0.00% | +0.00% | 0.00 | 0.00% | 0.0 | 0 | 0.0 |
| ETH_1d_test | +0.00% | +0.00% | 0.00 | 0.00% | 0.0 | 0 | 0.0 |

## BTC_4h_train

- **Pair**: BTC/USDT
- **Interval**: 4h
- **Period**: 2024-01-01T00:00:00Z  ->  2025-08-31T23:59:59Z
- **Total Signals**: 6
- **Closed Trades**: 6

### Raw Metrics

- **total_return_pct**: 2.56
- **sharpe_ratio**: 2.57
- **max_drawdown_pct**: -0.42
- **win_rate_pct**: 83.33
- **total_trades**: 6
- **profit_factor**: 17.79

### Fee-Adjusted Metrics

- **total_return_pct**: 2.4402
- **sharpe_ratio**: 2.4527
- **max_drawdown_pct**: -0.1681
- **win_rate_pct**: 66.67
- **total_trades**: 6
- **profit_factor**: 14.9331
- **avg_trade_return_pct**: 0.4067

### Exit Distribution

- **rsi_overbought**: 4
- **trend_reversal**: 2

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 65223.74 | 69792.05 | 0.015332 | 70.04 | 67.97 | rsi_overbought |
| 2 | 67946.90 | 70947.58 | 0.014717 | 44.16 | 42.12 | rsi_overbought |
| 3 | 60926.00 | 61031.98 | 0.016413 | 1.74 | -0.26 | trend_reversal |
| 4 | 68810.03 | 74348.53 | 0.014533 | 80.49 | 78.41 | rsi_overbought |
| 5 | 95770.32 | 102964.00 | 0.010442 | 75.11 | 73.04 | rsi_overbought |
| 6 | 99040.00 | 97527.97 | 0.010097 | -15.27 | -17.25 | trend_reversal |

## BTC_4h_test

- **Pair**: BTC/USDT
- **Interval**: 4h
- **Period**: 2025-09-01T00:00:00Z  ->  2026-04-30T23:59:59Z
- **Total Signals**: 3
- **Closed Trades**: 3

### Raw Metrics

- **total_return_pct**: 0.09
- **sharpe_ratio**: 0.11
- **max_drawdown_pct**: -0.81
- **win_rate_pct**: 66.67
- **total_trades**: 3
- **profit_factor**: 1.17

### Fee-Adjusted Metrics

- **total_return_pct**: 0.0287
- **sharpe_ratio**: 0.0346
- **max_drawdown_pct**: -0.5313
- **win_rate_pct**: 66.67
- **total_trades**: 3
- **profit_factor**: 1.0539
- **avg_trade_return_pct**: 0.0096

### Exit Distribution

- **rsi_overbought**: 1
- **stop_loss**: 1
- **max_holding**: 1

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 90620.96 | 94226.84 | 0.011035 | 39.79 | 37.75 | rsi_overbought |
| 2 | 94585.98 | 89725.76 | 0.010572 | -51.38 | -53.33 | stop_loss |
| 3 | 75252.34 | 76793.09 | 0.013289 | 20.47 | 18.45 | max_holding |

## ETH_4h_train

- **Pair**: ETH/USDT
- **Interval**: 4h
- **Period**: 2024-01-01T00:00:00Z  ->  2025-08-31T23:59:59Z
- **Total Signals**: 2
- **Closed Trades**: 2

### Raw Metrics

- **total_return_pct**: 0.01
- **sharpe_ratio**: 0.01
- **max_drawdown_pct**: -1.06
- **win_rate_pct**: 50.0
- **total_trades**: 2
- **profit_factor**: 1.02

### Fee-Adjusted Metrics

- **total_return_pct**: -0.0253
- **sharpe_ratio**: -0.0155
- **max_drawdown_pct**: -0.8269
- **win_rate_pct**: 50.0
- **total_trades**: 2
- **profit_factor**: 0.9694
- **avg_trade_return_pct**: -0.0126

### Exit Distribution

- **stop_loss**: 1
- **rsi_overbought**: 1

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 3446.69 | 3168.30 | 0.290133 | -80.77 | -82.69 | stop_loss |
| 2 | 1808.86 | 1957.63 | 0.552834 | 82.25 | 80.16 | rsi_overbought |

## ETH_4h_test

- **Pair**: ETH/USDT
- **Interval**: 4h
- **Period**: 2025-09-01T00:00:00Z  ->  2026-04-30T23:59:59Z
- **Total Signals**: 3
- **Closed Trades**: 3

### Raw Metrics

- **total_return_pct**: 0.28
- **sharpe_ratio**: 0.32
- **max_drawdown_pct**: -0.98
- **win_rate_pct**: 33.33
- **total_trades**: 3
- **profit_factor**: 1.7

### Fee-Adjusted Metrics

- **total_return_pct**: 0.2158
- **sharpe_ratio**: 0.2474
- **max_drawdown_pct**: -0.4336
- **win_rate_pct**: 33.33
- **total_trades**: 3
- **profit_factor**: 1.4946
- **avg_trade_return_pct**: 0.0719

### Exit Distribution

- **rsi_overbought**: 1
- **trend_reversal**: 1

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 3116.14 | 3325.82 | 0.320910 | 67.29 | 65.22 | rsi_overbought |
| 2 | 2083.10 | 2049.12 | 0.480054 | -16.31 | -18.30 | trend_reversal |
| 3 | 2311.52 | 2257.51 | 0.432616 | -23.37 | -25.34 | force_close |

## BTC_1d_train

- **Pair**: BTC/USDT
- **Interval**: 1d
- **Period**: 2024-01-01T00:00:00Z  ->  2025-08-31T23:59:59Z
- **Total Signals**: 1
- **Closed Trades**: 1

### Raw Metrics

- **total_return_pct**: 1.01
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: -0.05
- **win_rate_pct**: 100.0
- **total_trades**: 1
- **profit_factor**: inf

### Fee-Adjusted Metrics

- **total_return_pct**: 0.9872
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: 0.0
- **win_rate_pct**: 100.0
- **total_trades**: 1
- **profit_factor**: inf
- **avg_trade_return_pct**: 0.9872

### Exit Distribution

- **take_profit**: 1

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 94545.06 | 104077.48 | 0.010577 | 100.82 | 98.72 | take_profit |

## BTC_1d_test

- **Pair**: BTC/USDT
- **Interval**: 1d
- **Period**: 2025-09-01T00:00:00Z  ->  2026-04-30T23:59:59Z
- **Total Signals**: 0
- **Closed Trades**: 0

### Raw Metrics

- **total_return_pct**: 0.0
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: 0.0
- **win_rate_pct**: 0.0
- **total_trades**: 0
- **profit_factor**: 0.0

### Fee-Adjusted Metrics

- **total_return_pct**: 0.0
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: 0.0
- **win_rate_pct**: 0.0
- **total_trades**: 0
- **profit_factor**: 0.0
- **avg_trade_return_pct**: 0.0

### Exit Distribution


## SOL_4h_train

- **Pair**: SOL/USDT
- **Interval**: 4h
- **Period**: 2024-01-01T00:00:00Z  ->  2025-08-31T23:59:59Z
- **Total Signals**: 7
- **Closed Trades**: 7

### Raw Metrics

- **total_return_pct**: 1.11
- **sharpe_ratio**: 0.58
- **max_drawdown_pct**: -1.81
- **win_rate_pct**: 42.86
- **total_trades**: 7
- **profit_factor**: 1.87

### Fee-Adjusted Metrics

- **total_return_pct**: 0.9691
- **sharpe_ratio**: 0.5056
- **max_drawdown_pct**: -1.2132
- **win_rate_pct**: 42.86
- **total_trades**: 7
- **profit_factor**: 1.7138
- **avg_trade_return_pct**: 0.1384

### Exit Distribution

- **trend_reversal**: 3
- **rsi_overbought**: 2
- **stop_loss**: 1
- **max_holding**: 1

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 101.95 | 100.95 | 9.808730 | -9.81 | -11.80 | trend_reversal |
| 2 | 144.19 | 158.52 | 6.935294 | 99.38 | 97.28 | rsi_overbought |
| 3 | 162.82 | 184.94 | 6.141752 | 135.86 | 133.72 | rsi_overbought |
| 4 | 232.67 | 225.99 | 4.297933 | -28.71 | -30.68 | trend_reversal |
| 5 | 238.31 | 226.38 | 4.196215 | -50.06 | -52.01 | stop_loss |
| 6 | 221.75 | 213.03 | 4.509583 | -39.32 | -41.28 | trend_reversal |
| 7 | 146.34 | 146.88 | 6.833402 | 3.69 | 1.69 | max_holding |

## SOL_4h_test

- **Pair**: SOL/USDT
- **Interval**: 4h
- **Period**: 2025-09-01T00:00:00Z  ->  2026-04-30T23:59:59Z
- **Total Signals**: 2
- **Closed Trades**: 2

### Raw Metrics

- **total_return_pct**: -0.4
- **sharpe_ratio**: -1.31
- **max_drawdown_pct**: -0.52
- **win_rate_pct**: 0.0
- **total_trades**: 2
- **profit_factor**: 0.0

### Fee-Adjusted Metrics

- **total_return_pct**: -0.4418
- **sharpe_ratio**: -1.4391
- **max_drawdown_pct**: -0.4418
- **win_rate_pct**: 0.0
- **total_trades**: 2
- **profit_factor**: 0.0
- **avg_trade_return_pct**: -0.2209

### Exit Distribution

- **trend_reversal**: 2

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 89.37 | 86.20 | 11.189437 | -35.47 | -37.44 | trend_reversal |
| 2 | 86.40 | 85.99 | 11.574074 | -4.75 | -6.74 | trend_reversal |

## LINK_4h_train

- **Pair**: LINK/USDT
- **Interval**: 4h
- **Period**: 2024-01-01T00:00:00Z  ->  2025-08-31T23:59:59Z
- **Total Signals**: 6
- **Closed Trades**: 6

### Raw Metrics

- **total_return_pct**: 0.9
- **sharpe_ratio**: 0.72
- **max_drawdown_pct**: -0.54
- **win_rate_pct**: 16.67
- **total_trades**: 6
- **profit_factor**: 4.18

### Fee-Adjusted Metrics

- **total_return_pct**: 0.7808
- **sharpe_ratio**: 0.6281
- **max_drawdown_pct**: -0.3792
- **win_rate_pct**: 16.67
- **total_trades**: 6
- **profit_factor**: 3.0356
- **avg_trade_return_pct**: 0.1301

### Exit Distribution

- **take_profit**: 1
- **trend_reversal**: 5

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 18.45 | 20.63 | 54.212295 | 118.56 | 116.44 | take_profit |
| 2 | 11.15 | 11.09 | 89.686099 | -5.38 | -7.38 | trend_reversal |
| 3 | 11.17 | 11.08 | 89.525515 | -8.06 | -10.05 | trend_reversal |
| 4 | 11.16 | 11.16 | 89.605735 | 0.00 | -2.00 | trend_reversal |
| 5 | 11.41 | 11.32 | 87.642419 | -7.89 | -9.88 | trend_reversal |
| 6 | 11.33 | 11.25 | 88.261253 | -7.06 | -9.05 | trend_reversal |

## LINK_4h_test

- **Pair**: LINK/USDT
- **Interval**: 4h
- **Period**: 2025-09-01T00:00:00Z  ->  2026-04-30T23:59:59Z
- **Total Signals**: 2
- **Closed Trades**: 2

### Raw Metrics

- **total_return_pct**: 0.08
- **sharpe_ratio**: 0.06
- **max_drawdown_pct**: -0.75
- **win_rate_pct**: 50.0
- **total_trades**: 2
- **profit_factor**: 1.13

### Fee-Adjusted Metrics

- **total_return_pct**: 0.0375
- **sharpe_ratio**: 0.0292
- **max_drawdown_pct**: -0.6216
- **win_rate_pct**: 50.0
- **total_trades**: 2
- **profit_factor**: 1.06
- **avg_trade_return_pct**: 0.0188

### Exit Distribution

- **rsi_overbought**: 1
- **stop_loss**: 1

### Trade List

| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |
|---|------------|-----------|-----|---------|-------------|-------------|
| 1 | 13.16 | 14.06 | 75.987842 | 68.39 | 66.32 | rsi_overbought |
| 2 | 13.69 | 12.86 | 73.046019 | -60.63 | -62.57 | stop_loss |

## ETH_1d_train

- **Pair**: ETH/USDT
- **Interval**: 1d
- **Period**: 2024-01-01T00:00:00Z  ->  2025-08-31T23:59:59Z
- **Total Signals**: 0
- **Closed Trades**: 0

### Raw Metrics

- **total_return_pct**: 0.0
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: 0.0
- **win_rate_pct**: 0.0
- **total_trades**: 0
- **profit_factor**: 0.0

### Fee-Adjusted Metrics

- **total_return_pct**: 0.0
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: 0.0
- **win_rate_pct**: 0.0
- **total_trades**: 0
- **profit_factor**: 0.0
- **avg_trade_return_pct**: 0.0

### Exit Distribution


## ETH_1d_test

- **Pair**: ETH/USDT
- **Interval**: 1d
- **Period**: 2025-09-01T00:00:00Z  ->  2026-04-30T23:59:59Z
- **Total Signals**: 0
- **Closed Trades**: 0

### Raw Metrics

- **total_return_pct**: 0.0
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: 0.0
- **win_rate_pct**: 0.0
- **total_trades**: 0
- **profit_factor**: 0.0

### Fee-Adjusted Metrics

- **total_return_pct**: 0.0
- **sharpe_ratio**: 0.0
- **max_drawdown_pct**: 0.0
- **win_rate_pct**: 0.0
- **total_trades**: 0
- **profit_factor**: 0.0
- **avg_trade_return_pct**: 0.0

### Exit Distribution


## Implementation Notes

### Edge Cases Handled
- **Warmup period**: No signals generated until `sma_period + pivot_window + min_pivot_spacing` candles available in the sliding window
- **RSI None values**: Pivot lows with undefined RSI are skipped in divergence check
- **Pivot spacing**: Minimum distance between consecutive pivot lows enforced to reduce noise
- **Position tracking**: Self-managed via `_has_position` flag; one position at a time
- **Engine force-close**: Any positions still open at backtest end are force-closed at last candle price

### Fee Adjustment
- Round-trip fee: **0.2%** (0.1% per side)
- Applied post-hoc to all closed trade PnLs
- Sharpe, drawdown, win rate, and profit factor recalculated from fee-adjusted equity curve

### Known Limitations
- The engine processes one signal per candle — cannot exit and re-enter on the same bar
- Position sizing uses fixed 10% of assumed capital, not equity-curve-aware
- Pivot detection uses strict equality (`<=`) — ties where multiple candles share the same low are all detected
