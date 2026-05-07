# H2: RSI Divergence with Trend Filter — Strategy Specification

**Hypothesis ID**: H2
**Priority**: HIGH (first hypothesis to test)
**Author**: Head of Quantitative Research
**Date**: 2026-05-07
**Status**: READY FOR IMPLEMENTATION
**Target Agent**: strategy-implementer

---

## 1. Hypothesis Statement

Bullish RSI divergence (price makes a lower low while RSI makes a higher low) during an established uptrend (price above 200 SMA) predicts a short-term reversal with >55% accuracy and >2:1 reward-to-risk ratio.

**Rationale**: Pure RSI oversold signals fail in downtrends — the asset keeps falling. By requiring an uptrend filter, we only buy dips within established bullish trends, increasing the probability of reversal. RSI divergence adds timing precision compared to simple RSI oversold thresholds.

---

## 2. Indicators Required

All indicators are available in the platform's `cryplative.strategies.indicators` module. No custom indicators needed.

| Indicator | Platform Function | Parameters |
|-----------|-------------------|------------|
| RSI | `compute_rsi(closes, period)` | period = 14 |
| SMA | `compute_sma(closes, period)` | period = 200 |

---

## 3. Entry Rules — BUY Signal

A BUY signal is generated when ALL of the following conditions are true simultaneously:

### Condition 1: Uptrend Filter
- Current close > SMA(200)

### Condition 2: Bullish RSI Divergence Detected
- **Price makes a lower low**: The most recent pivot low in price is LOWER than the previous pivot low
- **RSI makes a higher low**: The RSI value at the most recent pivot low is HIGHER than the RSI value at the previous pivot low
- See Section 4 for the divergence detection algorithm

### Condition 3: RSI Below Threshold
- Current RSI(14) < `oversold_threshold` (default: 40)
- This ensures we're entering when RSI is still relatively low, not after the reversal has already started

### Condition 4: No Open Position
- Self-track position state. Only generate BUY if no position is currently open. (See Section 7 for position tracking workaround.)

---

## 4. Divergence Detection Algorithm

This is the core logic. Implement as a helper function within the strategy.

### Step 1: Identify Pivot Lows

A candle at index `i` is a **pivot low** if its low is the minimum low within a window of `pivot_window` candles on each side:

```
pivot_low(i) = True if:
    candles[i].low <= min(candles[j].low for j in range(i - pivot_window, i + pivot_window + 1))
    AND i >= pivot_window
    AND i < len(candles) - pivot_window
```

Default `pivot_window` = 5 (meaning the low must be the lowest in an 11-candle window centered on it).

### Step 2: Find the Last Two Pivot Lows

Scan backward from the current candle and collect the two most recent pivot lows:

```
pivot_lows = []
for i in range(len(candles) - 1, pivot_window, -1):
    if is_pivot_low(i):
        pivot_lows.append(i)
        if len(pivot_lows) == 2:
            break

# i2 = most recent pivot low index (closer to current candle)
# i1 = second most recent pivot low index (further back)
i2, i1 = pivot_lows[0], pivot_lows[1]  # i2 > i1
```

### Step 3: Check for Bullish Divergence

```
bullish_divergence = (candles[i2].low < candles[i1].low) AND (rsi_values[i2] > rsi_values[i1])
```

This means:
- Price made a lower low at i2 compared to i1 (price is going down)
- But RSI made a higher low at i2 compared to i1 (momentum is strengthening)
- This mismatch suggests the selling pressure is weakening → potential reversal

### Edge Cases to Handle

- **Insufficient data**: If fewer than 2 pivot lows found in the lookback window, no divergence possible → return None (no signal)
- **RSI is None**: `compute_rsi` returns None for indices where there isn't enough data. Skip those pivot lows
- **Pivot lows too close together**: If i2 and i1 are within `min_pivot_spacing` candles (default: 10), skip — too noisy. Look for the next older pivot low instead
- **Warmup period**: Don't generate any signals until at least `sma_period + pivot_window + min_pivot_spacing` candles are available

---

## 5. Exit Rules — SELL Signal

A SELL signal is generated when ANY of the following conditions are true while a position is open:

### Exit Condition 1: RSI Overbought
- Current RSI(14) > `overbought_exit` (default: 70)

### Exit Condition 2: Stop-Loss Hit (Manual Check)
- Current close <= entry_price * (1 - `stop_loss_pct`)
- Default: 5% stop-loss
- **Note**: Since the platform doesn't auto-trigger SL/TP, check this condition on each candle close via self-tracked position state

### Exit Condition 3: Take-Profit Hit (Manual Check)
- Current close >= entry_price * (1 + `take_profit_pct`)
- Default: 10% take-profit
- **Note**: Same manual check as stop-loss

### Exit Condition 4: Trend Reversal
- Current close drops below SMA(200) — the uptrend has failed
- This is a defensive exit: close the position even if SL/TP haven't been hit

### Exit Condition 5: Maximum Holding Period
- Position has been open for more than `max_holding_candles` candles (default: 50 on 4h = ~8 days, 20 on 1d = ~20 days)
- Time-based exit prevents capital from being locked in stagnant positions

---

## 6. Parameters

### Primary Parameters (to test)

| Parameter | Default | Range to Sweep | Description |
|-----------|---------|---------------|-------------|
| `sma_period` | 200 | 100, 150, 200, 250 | Trend filter SMA period |
| `rsi_period` | 14 | 10, 14, 21 | RSI calculation period |
| `oversold_threshold` | 40 | 30, 35, 40, 45 | Max RSI for entry |
| `overbought_exit` | 70 | 65, 70, 75, 80 | RSI level for exit |
| `stop_loss_pct` | 0.05 | 0.03, 0.05, 0.07, 0.10 | Stop-loss percentage |
| `take_profit_pct` | 0.10 | 0.07, 0.10, 0.15, 0.20 | Take-profit percentage |
| `pivot_window` | 5 | 3, 5, 7 | Window for pivot low detection |
| `min_pivot_spacing` | 10 | 5, 10, 15 | Min candles between pivot lows |
| `max_holding_candles` | 50 | 30, 50, 75, 100 | Max candles to hold position |

### Initial Test Configuration

Start with default parameters. Only sweep after confirming the strategy logic produces reasonable trade behavior on the primary pair.

---

## 7. Position Management (Platform Workarounds)

The current platform has limitations that require manual handling:

### Position State Tracking
Since strategies cannot see open positions, self-track state in the strategy object:

```python
def initialize(self, config):
    super().initialize(config)
    self._has_open_position = False
    self._entry_price = None
    self._entry_candle_index = 0

def generate_signal(self, candles):
    # ... compute indicators ...

    # Check exit conditions if position is open
    if self._has_open_position:
        current_price = candles[-1].close
        candles_since_entry = len(candles) - self._entry_candle_index

        # Exit conditions...
        if should_exit:
            self._has_open_position = False
            return Signal(direction=SignalDirection.SELL, ...)

    # Check entry conditions if no position
    if not self._has_open_position and entry_conditions_met:
        self._has_open_position = True
        self._entry_price = candles[-1].close
        self._entry_candle_index = len(candles)
        return Signal(direction=SignalDirection.BUY, ...)
```

### Position Sizing
Use the initial-capital approximation approach:

```python
# Approximate 10% of capital per trade (adjust for price)
assumed_capital = 10000.0  # Match --capital flag
risk_per_trade = 0.10  # 10% of capital
quantity = (assumed_capital * risk_per_trade) / candles[-1].close
```

---

## 8. Fee Adjustment

Apply post-processing fee adjustment to all results until Phase 2.5 ships with `--fee-rate`:

```python
ROUND_TRIP_FEE = 0.002  # 0.1% per side = 0.2% round-trip

# For each trade:
adjusted_pnl = trade.pnl - (trade.entry_price * trade.quantity * 0.001) - (trade.exit_price * trade.quantity * 0.001)
```

Report BOTH raw and fee-adjusted metrics.

---

## 9. Test Configuration

### Pairs to Test

| Pair | Rationale | Priority |
|------|-----------|----------|
| BTC/USDT | Most liquid, best data quality, primary test pair | HIGH |
| ETH/USDT | Different volatility profile, second most liquid | HIGH |
| SOL/USDT | Higher volatility alt-coin, tests edge in different regime | MEDIUM |
| LINK/USDT | Lower BTC correlation, interesting for diversification | MEDIUM |

### Timeframes

| Timeframe | Rationale | Priority |
|-----------|-----------|----------|
| 4h | Primary test timeframe — good signal-to-noise ratio for divergence | HIGH |
| 1d | Secondary — fewer signals but potentially higher quality | HIGH |

### Data Fetch Commands (run before backtesting)

```bash
# BTC
uv run cryplative fetch --symbol BTC/USDT --interval 4h --start 2024-01-01 --end 2026-05-07
uv run cryplative fetch --symbol BTC/USDT --interval 1d --start 2024-01-01 --end 2026-05-07

# ETH
uv run cryplative fetch --symbol ETH/USDT --interval 4h --start 2024-01-01 --end 2026-05-07
uv run cryplative fetch --symbol ETH/USDT --interval 1d --start 2024-01-01 --end 2026-05-07

# SOL
uv run cryplative fetch --symbol SOL/USDT --interval 4h --start 2024-01-01 --end 2026-05-07
uv run cryplative fetch --symbol SOL/USDT --interval 1d --start 2024-01-01 --end 2026-05-07

# LINK
uv run cryplative fetch --symbol LINK/USDT --interval 4h --start 2024-01-01 --end 2026-05-07
uv run cryplative fetch --symbol LINK/USDT --interval 1d --start 2024-01-01 --end 2026-05-07
```

### Train/Test Split

| Period | Usage | Dates |
|--------|-------|-------|
| Training (in-sample) | Develop and tune strategy | 2024-01-01 to 2025-08-31 |
| Test (out-of-sample) | Validate without tuning | 2025-09-01 to 2026-04-30 |

**Important**: Parameter tuning is ONLY allowed on the training period. The test period is held out for final evaluation. Report both sets of results.

### Lookback Window

For 200-period SMA, the engine needs a lookback window > 200. Use `--lookback-window 300` if the CLI flag is available, or set `lookback_window=300` via the programmatic API. If neither works yet, the first ~200 candles will serve as warmup (no signals generated).

---

## 10. Success Criteria

### Minimum Viable (for promotion to validation)

| Metric | Threshold | Notes |
|--------|-----------|-------|
| Sharpe Ratio | >= 1.0 (out-of-sample) | Risk-adjusted return must be positive |
| Max Drawdown | <= -20% | Absolute ceiling on downside |
| Win Rate | >= 50% | Or profit factor >= 2.0 compensates |
| Profit Factor | >= 1.5 (out-of-sample) | Winners must meaningfully exceed losers |
| Trade Count | >= 20 (test period) | Statistical significance |
| Fee-Adjusted Return | Positive | Must be profitable after 0.2% round-trip fees |
| Regime Coverage | Profitable in >= 2 regimes | Not a one-trick pony |

### Aspirational (for live deployment consideration)

| Metric | Target |
|--------|--------|
| Sharpe Ratio | >= 1.5 |
| Max Drawdown | <= -15% |
| Annualized Return | >= 40% |
| Profit Factor | >= 2.0 |

---

## 11. Expected Results and Failure Modes

### What Success Looks Like

- BTC and ETH 4h show positive Sharpe with divergence entries filtering out most whipsaw
- Win rate 50-60% with average winner > 2x average loser
- Strategy underperforms in strong downtrends (expected — trend filter keeps us out)
- SOL may show stronger results due to higher volatility creating cleaner divergences

### Known Failure Modes to Watch For

1. **Too few signals**: Divergence is rare. If we get < 20 trades in the training period, the statistical power is too low. Mitigation: consider relaxing pivot_window or adding time-based RSI oversold + divergence confirmation
2. **Divergence detection noise**: Pivot lows can be noisy on 4h data. Watch for false divergences that don't reverse. Mitigation: pivot_window sweep should find the right balance
3. **RSI divergence lag**: By the time divergence is confirmed, the move may have already started. Watch for entries at already-elevated RSI. Mitigation: oversold_threshold parameter
4. **Whipsaw in weak uptrends**: Price barely above SMA(200) can still produce losing trades. Consider requiring a minimum distance above SMA (e.g., close > SMA * 1.02) in an iteration

---

## 12. Deliverables Expected from Strategy-Implementer

### Directory Ownership Boundary (CEO Directive 2026-05-07)

**ALL research work lives in `data/`.** The strategy-implementer works entirely within `data/` and imports platform tools as a library. No strategy code or research output goes into `platform/`.

**Current workaround**: Until the root-level `.venv` with editable `pip install -e ./platform` is set up (Phase 2.5), use the `sys.path` import hack as done in `data/fetch_h2_data.py`. Once the root venv is ready, switch to clean imports.

### Deliverables

1. **Strategy file**: `data/strategies/rsi_divergence_trend.py` — a standalone Python script that:
   - Imports platform modules (`BacktestEngine`, indicators, models) as a library
   - Contains the strategy logic (subclassing `Strategy` from platform, or using `BacktestEngine` programmatically)
   - All helper functions (pivot detection, divergence check) live in this file
   - Can be run directly to execute backtests and write results
2. **Backtest results**: JSON result files in `data/strategy_results/` for:
   - BTC/USDT 4h (training period)
   - BTC/USDT 4h (test period)
   - ETH/USDT 4h (training period)
   - ETH/USDT 4h (test period)
   - BTC/USDT 1d (training period)
   - BTC/USDT 1d (test period)
3. **Fee-adjusted analysis**: Post-processing showing impact of 0.2% round-trip fees
4. **Summary report**: Brief write-up in `data/strategy_results/H2-report.md`:
   - Number of signals generated
   - Trade distribution (how many divergence entries, how exited)
   - Any implementation issues or edge cases encountered
   - Raw vs fee-adjusted metrics comparison

---

## 13. Implementation Notes

### Working in data/ (CEO Directive)

The strategy-implementer works exclusively in `data/`:
- Create `data/strategies/` directory for strategy implementations
- Import platform tools as a library (see import pattern below)
- All output (results, reports, metrics) goes into `data/strategy_results/`
- **Do NOT write any files into `platform/`**

### Import Pattern

Until root venv is available (Phase 2.5):
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "platform", "src"))

from cryplative.strategies.base import Strategy
from cryplative.strategies.indicators import compute_rsi, compute_sma
from cryplative.backtesting.engine import BacktestEngine
from cryplative.core.models import Signal, SignalDirection
```

After root venv is available (Phase 2.5), remove the `sys.path` hack:
```python
from cryplative.strategies.base import Strategy
from cryplative.strategies.indicators import compute_rsi, compute_sma
from cryplative.backtesting.engine import BacktestEngine
from cryplative.core.models import Signal, SignalDirection
```

### Strategy Implementation Approach

Two valid approaches (choose based on what works with the programmatic API):

**Approach A: Strategy subclass (preferred)**
- Subclass `Strategy` from platform
- Register with `@StrategyRegistry.register`
- Run via `BacktestEngine` programmatic API
- This is the cleanest approach if the engine can discover strategies from `data/`

**Approach B: Direct engine usage**
- Use `BacktestEngine` + `BacktestConfig` directly
- Implement signal logic as a function that processes candles
- Feed results to the engine
- Use this if registry-based discovery doesn't work from `data/`

### General Notes

- Handle warmup period: return None until enough candles for SMA(200) + pivot detection
- Remember: `compute_rsi` and `compute_sma` return `list[float | None]` — always check for None before using values

---

*This specification is complete and unambiguous. The strategy-implementer should be able to code, test, and report without requiring clarification. If edge cases arise during implementation, document them and report back.*
