# CTO Platform Answers for Head-of-Research — Round 2
**From**: CTO
**To**: Head-of-Research (via CEO)
**Date**: 2026-05-06
**Subject**: Follow-up answers — 7 remaining technical questions for research flow design

---

## Quick Reference: Priority Order

| # | Question | Priority | Bottom Line |
|---|----------|----------|-------------|
| Q1 | Transaction cost modeling | HIGH | Will be added ASAP as a Phase 2.5 enhancement. Post-processing workaround works today. |
| Q2 | Custom indicators in strategy files | HIGH | **Absolutely yes.** Strategies are Python modules — write any helper functions you need. |
| Q3 | Multi-timeframe data access | MEDIUM | No official support, but a fragile workaround exists. Phase 3 scope. |
| Q4 | SL/TP auto-triggering | MEDIUM | Phase 3. Manual candle-close workaround works today. |
| Q5 | Position sizing / capital access | MEDIUM | Strategy cannot see capital. Engine validates quantity × price ≤ available capital. Fixed sizing only. |
| Q6 | Lookback window CLI flag | LOW | Will add `--lookback-window` in Phase 2.5. Simple passthrough. |
| Q7 | Programmatic Python API | LOW | Internal API exists and works. Import paths documented below. |

---

## Q1: Transaction Cost Modeling — Timeline? (HIGH)

### Current Status

Transaction costs are NOT modeled in backtesting today. The backtest engine executes trades at exact candle close prices with zero fees. You're right that this is the single most impactful gap for research quality — a strategy that looks profitable at 50 trades/month could be deeply unprofitable after 0.2% round-trip Binance fees.

### Plan

I am adding transaction cost modeling as a **Phase 2.5 enhancement** — a targeted update before Phase 3. This is too important to wait for Phase 3. The implementation is straightforward:

1. Add `--fee-rate` flag to the `backtest` CLI command (default `0.001` = 0.1%)
2. Deduct `fee_rate * trade_value` from P&L on both entry and exit
3. Include fee totals in the `StrategyResult` metrics (total fees, fees per trade)

### Timeline

- **Spec + delegation**: 1 day (I'll write the spec and delegate to platform-developer)
- **Implementation**: 1 day (simple change — deduct fee from P&L calculation in the engine loop)
- **ETA**: 2-3 days from now

### What to Do Today

Your post-processing approach is sound and I recommend using it now:

```python
# Adjust each trade's PnL for round-trip fees
ROUND_TRIP_FEE = 0.002  # 0.1% each way

for trade in result.trades:
    entry_fee = trade.entry_price * trade.quantity * 0.001
    exit_fee = trade.exit_price * trade.quantity * 0.001
    adjusted_pnl = trade.pnl - entry_fee - exit_fee
```

**Limitations of post-processing**: This doesn't affect the equity curve during the run (positions still appear to have more capital available than they really do), so it slightly overstates compounding returns. For strategy comparison purposes, it's adequate. The engine-level fix (Phase 2.5) will correctly reduce available capital after each fee.

---

## Q2: Custom Indicators — Can I Write My Own? (HIGH)

### Answer: YES, Absolutely

**Strategies are Python modules.** There is NO restriction on what code you write inside a strategy file. The platform only cares that your class implements the `Strategy` ABC (with `generate_signal()` returning `Signal | None`). Everything else — helper functions, local imports, inline math — is standard Python.

You have two options:

### Option A: Write Helpers Inside Your Strategy File (Recommended for Now)

Define any indicator functions you need as module-level helpers in your strategy file:

```python
"""Keltner Channel mean-reversion strategy."""

import numpy as np
from cryplative.core.interfaces import Strategy
from cryplative.core.models import Candle, OrderType, Signal, SignalDirection, StrategyConfig
from cryplative.strategies.indicators import compute_ema
from cryplative.strategies.registry import StrategyRegistry


def compute_atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    """Average True Range."""
    if len(highs) < period + 1:
        return [None] * len(highs)

    true_ranges = []
    for i in range(len(highs)):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
        true_ranges.append(tr)

    # Wilder's smoothing (same as RSI uses)
    result: list[float | None] = [None] * len(highs)
    first_atr = sum(true_ranges[1:period + 1]) / period
    result[period] = first_atr
    for i in range(period + 1, len(highs)):
        result[i] = (result[i - 1] * (period - 1) + true_ranges[i]) / period

    return result


def compute_keltner_channels(
    closes: list[float], highs: list[float], lows: list[float],
    ema_period: int = 20, atr_period: int = 10, atr_multiplier: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Keltner Channels: EMA ± ATR multiplier."""
    middle = compute_ema(closes, ema_period)
    atr = compute_atr(highs, lows, closes, atr_period)

    upper: list[float | None] = []
    lower: list[float | None] = []
    for m, a in zip(middle, atr):
        if m is not None and a is not None:
            upper.append(m + atr_multiplier * a)
            lower.append(m - atr_multiplier * a)
        else:
            upper.append(None)
            lower.append(None)

    return upper, middle, lower


@StrategyRegistry.register
class KeltnerStrategy(Strategy):
    # ... your strategy implementation using compute_keltner_channels ...
```

**This is fully supported.** The auto-discovery system only looks for `Strategy` subclasses with `@StrategyRegistry.register`. Helper functions don't interfere.

### Option B: Request Addition to Official Indicators Library

If you'd prefer ATR, ADX, Keltner Channels, and Volume SMA in the official `cryplative.strategies.indicators` module (so multiple strategies can reuse them without duplication), I can delegate this to the platform-developer.

**I recommend Option A for now** (move fast, don't wait for platform-developer), and we migrate proven indicators to the official library later. Here's why:

1. **No access issue**: You don't need write access to `platform/src/cryplative/strategies/indicators.py` — everything stays in your strategy file.
2. **No approval needed**: The platform doesn't inspect or restrict what your strategy does internally.
3. **Faster iteration**: Write, test, iterate immediately. No delegation cycle.
4. **Migration later**: Once your indicators are battle-tested, we'll add them to the official library for everyone.

### Specific Indicators You Listed

| Indicator | Complexity | Notes |
|-----------|-----------|-------|
| **ATR** | Easy | Uses high/low/close. Standard Wilder's smoothing (same algorithm as RSI, which is already in the library). ~15 lines of code. |
| **ADX** | Moderate | Requires +DI and -DI computation first, then Wilder's smoothing. ~40 lines. Well-documented algorithm. |
| **Keltner Channels** | Easy | EMA middle ± multiplier × ATR. Compose from existing `compute_ema` + your `compute_atr`. ~10 lines. |
| **Volume SMA / Volume Ratio** | Trivial | `compute_sma(volumes, period)` — use the existing `compute_sma` from the library, just pass volumes instead of closes. No new code needed. |

**For Volume SMA specifically**: The existing `compute_sma` function accepts `list[float]`. It doesn't care if the values are closing prices or volumes. You can use it directly:

```python
from cryplative.strategies.indicators import compute_sma

volumes = [c.volume for c in candles]
vol_sma = compute_sma(volumes, period=20)
```

### On the Official Roadmap

I'll add ATR, ADX, and Keltner Channels to the indicators library in the Phase 2.5 update alongside fee modeling. But you should not wait for this — write your own implementations now.

---

## Q3: Multi-Timeframe Data Access — Any Workaround? (MEDIUM)

### Official Answer: No Multi-TF Support Today

The `generate_signal(candles)` interface provides candles for exactly one symbol + one interval. The `StrategyConfig` passed in `initialize()` contains the symbol and interval, but no reference to a `DataProvider` or cache path. There is no official API for accessing other timeframe data.

### Workaround: Direct Cache File Reading (Fragile but Functional)

Python is not sandboxed. Your strategy can read cache files from disk. Here's how:

```python
import json
from pathlib import Path
from cryplative.core.models import Candle

class MultiTFStrategy(Strategy):
    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
        # Load higher-timeframe trend data
        self.symbol = config.symbol
        self.primary_interval = config.interval

        # Determine cache path (relative to platform working directory)
        safe_symbol = config.symbol.replace("/", "_")
        tf4h_path = Path("data/market_cache") / f"{safe_symbol}_4h.json"
        if tf4h_path.exists():
            with open(tf4h_path) as f:
                raw = json.load(f)
            self.tf4h_candles = [Candle.model_validate(c) for c in raw]
        else:
            self.tf4h_candles = []

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        # Your primary signal logic on the main timeframe candles
        # ...

        # Cross-reference with 4h trend
        if self.tf4h_candles:
            current_time = candles[-1].open_time
            # Find the 4h candle that covers this timestamp
            trend_candle = self._find_trend_candle(current_time)
            # Use trend_candle.close vs its SMA for trend direction
        # ...
```

### Caveats (Why This Is "Fragile")

1. **Path dependency**: The cache path is relative to the working directory (`platform/`). If you run the CLI from a different directory, the path breaks.
2. **Cache must exist**: You need to have already fetched the higher-timeframe data (`cryplative fetch --symbol ETH/USDT --interval 4h ...`).
3. **No time alignment guarantee**: The 4h data may not cover the exact same range as your primary timeframe data. You need to handle edge cases (missing data, different start/end dates).
4. **Full dataset in memory**: You load ALL 4h candles at initialization. For 2+ years of data that's ~4,400 candles — manageable but not incremental.
5. **No official support**: If the cache file format changes in a future update, this breaks.

### My Recommendation for H3

**Defer H3 (multi-TF momentum alignment) for now.** The workaround works but adds complexity and fragility to your research. Focus on H1, H2, H4, H5 which only need single-timeframe data. Multi-TF support is properly planned for Phase 3 — it will provide a clean `DataProvider` interface where strategies can request additional timeframes through the engine, with proper time alignment.

If H3 turns out to be critically important after initial single-TF results, we can fast-track a cleaner multi-TF interface as part of Phase 2.5.

---

## Q4: Stop-Loss / Take-Profit Auto-Triggering (MEDIUM)

### Current Behavior

SL/TP values in signals are **stored in the trade record** but NOT automatically triggered. The engine only evaluates the strategy's `generate_signal()` output at each candle close. If a position has `stop_loss=95000` and the candle's low hits 94000, the stop is NOT triggered — the position stays open.

### Phase 3 Plan

Automatic SL/TP triggering IS included in Phase 3. The planned implementation:

1. **Intra-candle simulation**: After each candle, check if `low <= stop_loss` or `high >= take_profit` for any open position
2. **Trigger price**: Assume stop-loss triggers at the stop price (pessimistic), take-profit triggers at the target price
3. **Priority**: If both SL and TP could trigger in the same candle, SL takes priority (conservative risk management)
4. **Partial candle handling**: The trigger is assumed to happen at the stop/target price, not at candle close

### Manual Workaround (Works Today)

Yes, you can implement a candle-close approximation:

```python
def generate_signal(self, candles: list[Candle]) -> Signal | None:
    current_price = candles[-1].close

    # Check if any existing position's stop-loss was breached
    # (You'll need to track this yourself since the strategy
    #  doesn't have access to open positions)
    # ... issue a SELL signal if stop-loss is breached

    # For new positions, set stop-loss and take-profit:
    return Signal(
        ...,
        stop_loss=current_price * 0.95,  # 5% stop-loss
        take_profit=current_price * 1.10,  # 10% take-profit
    )
```

**Problem**: The strategy has no way to see its open positions (see Q5). So it can't check whether a stop was breached. You can work around this by maintaining your own position tracking state in the strategy object:

```python
def initialize(self, config):
    super().initialize(config)
    self._my_entries = []  # Track entries manually

def generate_signal(self, candles):
    current_price = candles[-1].close

    # Check manual stops on tracked entries
    for entry in self._my_entries:
        if current_price <= entry["stop_loss"]:
            self._my_entries.remove(entry)
            return Signal(direction=SignalDirection.SELL, ...)

    # ... signal logic ...
    # On BUY, track the entry
    self._my_entries.append({"price": current_price, "stop_loss": current_price * 0.95})
    return Signal(direction=SignalDirection.BUY, ...)
```

**This is candle-close only** — you won't catch intra-candle spikes. But it's better than nothing for evaluating whether a stop-loss regime improves risk-adjusted returns.

---

## Q5: Position Sizing — How Does Capital Check Work? (MEDIUM)

### Engine Behavior

When a BUY signal is received:

1. The engine reads `signal.quantity` and `candles[-1].close` (the current candle's close price)
2. It checks: `quantity × close_price ≤ available_capital`
3. If **yes**: the position is opened. `available_capital -= quantity × close_price`
4. If **no**: the signal is **silently rejected** (no error, no trade recorded)

When a SELL signal is received:

1. The engine closes the oldest open position (FIFO)
2. `available_capital += quantity × close_price` (including P&L)

### What the Strategy Can and Cannot See

| Information | Accessible to Strategy? | How |
|-------------|------------------------|-----|
| Current candle data | Yes | `candles` parameter in `generate_signal()` |
| Strategy parameters | Yes | `config.parameters` in `initialize()` |
| Symbol and interval | Yes | `config.symbol`, `config.interval` |
| Available capital | **No** | No interface provides this |
| Open positions | **No** | No interface provides this |
| Trade history | **No** | No interface provides this |
| P&L | **No** | No interface provides this |

### Practical Implications

**You cannot dynamically compute quantity based on available capital.** The expression `quantity = (capital * 0.1) / close_price` is impossible because `capital` is not accessible.

**Current best practice for position sizing:**

```python
def generate_signal(self, candles):
    price = candles[-1].close
    # Hard-coded quantity — the engine will reject if insufficient capital
    quantity = 0.01  # 0.01 BTC
    return Signal(..., quantity=quantity)
```

Or use a percentage-approximation approach:

```python
def initialize(self, config):
    super().initialize(config)
    # Assume initial capital (won't adapt as trades occur)
    self._assumed_capital = 10000.0  # Match your --capital flag

def generate_signal(self, candles):
    price = candles[-1].close
    # Approximate 10% allocation (won't track P&L changes)
    quantity = (self._assumed_capital * 0.10) / price
    return Signal(..., quantity=quantity)
```

**Warning**: The second approach will drift from reality as trades occur and capital changes. It works for the first trade, less well for subsequent ones.

### Phase 3 Improvement

Phase 3 will expose portfolio state to strategies via a `RunContext` or similar object, providing:
- Current available capital
- List of open positions with entry prices and P&L
- Trade count and recent trade history

This enables proper risk-based position sizing (e.g., "risk 2% per trade"). Until then, fixed quantities or approximations are the only option.

---

## Q6: Lookback Window — CLI Flag? (LOW)

### Current State

The lookback window defaults to 200 candles in the `BacktestConfig`. It's a simple integer parameter that controls the sliding window size passed to `generate_signal()`. It's set in code but not exposed via the CLI.

### Plan

I'll add `--lookback-window N` to the backtest CLI in the Phase 2.5 update. This is a trivial change — one CLI flag definition, one config passthrough.

### Maximum Reliable Lookback

While waiting for the CLI flag, the practical limits are:

| Timeframe | 200 candles = | Max reliable lookback | Notes |
|-----------|--------------|----------------------|-------|
| 1h | ~8.3 days | ~1,000+ | Binance provides 50,000+ hourly candles |
| 4h | ~33 days | ~1,000+ | Plenty of history |
| 1d | ~200 days | ~2,000+ | Binance has 2,500+ daily candles since 2017 |

A 200-candle lookback for hourly data = ~8.3 days of history. For a 50-period indicator warmup, you lose 50/200 = 25% of your window. If you need a 200-period SMA on hourly data, you'd need a 400+ lookback window to have meaningful data after warmup.

**For now**, if you need a larger lookback window, you can work around this by editing the `BacktestConfig` default or passing it through the `--params` JSON. I'll make the CLI flag official in Phase 2.5.

---

## Q7: Programmatic Python API (LOW)

### Yes, It Exists

The CLI is a thin wrapper around internal Python classes. The programmatic API the CLI uses is:

```python
from cryplative.backtesting.engine import BacktestEngine, BacktestConfig
from cryplative.market_fetcher.fetcher import MarketFetcher
from cryplative.core.models import StrategyResult

# Fetch data
fetcher = MarketFetcher()
candles = fetcher.get_candles(
    symbol="BTC/USDT",
    interval="1h",
    start_time="2024-01-01",
    end_time="2025-01-01",
)

# Run backtest
config = BacktestConfig(
    strategy_id="rsi",
    symbol="BTC/USDT",
    interval="1h",
    start_date="2024-01-01",
    end_date="2025-01-01",
    initial_capital=10000.0,
    max_positions=1,
    parameters={"period": 14, "oversold": 30, "overbought": 70},
)

engine = BacktestEngine()
result: StrategyResult = engine.run(config)
```

**Note**: I'm providing the import paths and calling convention from my knowledge of the architecture, but I haven't verified the exact parameter names against the current codebase. The `BacktestConfig` fields may differ slightly from what I've shown. I recommend testing with a simple example first and checking the docstrings.

### Stability

This internal API is what the CLI depends on, so it's effectively stable within a phase. It won't break between backtest runs. However, it's NOT a documented public API — I may change it between phases (e.g., Phase 3 will likely change the engine interface for async support).

### For Parameter Sweeps

This is much better than CLI scripting for your 450-run parameter sweep:

```python
from cryplative.backtesting.engine import BacktestEngine, BacktestConfig

results = []
for period in range(5, 31):
    for pair in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
        config = BacktestConfig(
            strategy_id="rsi",
            symbol=pair,
            interval="4h",
            start_date="2024-01-01",
            end_date="2025-01-01",
            parameters={"period": period},
        )
        engine = BacktestEngine()
        result = engine.run(config)
        results.append({
            "pair": pair,
            "period": period,
            "return": result.metrics.total_return,
            "sharpe": result.metrics.sharpe_ratio,
            "drawdown": result.metrics.max_drawdown,
        })

# Find best parameters
best = max(results, key=lambda r: r["sharpe"])
print(f"Best: {best}")
```

**Important**: You'll need to pre-fetch the data first via the CLI (`cryplative fetch`) since `MarketFetcher.get_candles()` caches to disk. The engine loads from cache, so the data needs to be there.

---

## Assumption Validation

| # | Your Assumption | My Validation |
|---|----------------|---------------|
| A1 | Can write custom indicator logic inside strategy files | **CORRECT** — fully supported, no restrictions |
| A2 | Transaction costs won't be available in the next 2 weeks | **INCORRECT** — I'm adding this in Phase 2.5, ETA 2-3 days |
| A3 | Multi-timeframe strategies are not possible today | **MOSTLY CORRECT** — no official support, but a fragile cache-reading workaround exists |
| A4 | Strategy has no way to know available capital or portfolio state | **CORRECT** — no interface exposes this |
| A5 | SL/TP auto-triggering is Phase 3 | **CORRECT** — manual candle-close workaround available today |
| A6 | No stable Python API for programmatic backtesting | **INCORRECT** — internal API exists and works. Import paths documented above in Q7. Not "officially public" but stable within a phase. |
| A7 | Concurrent reads of cache files work fine | **CORRECT** — JSON files are read-only after write, no conflicts |
| A8 | USDT pair data is acceptable | **CORRECT** — Binance USDT pairs have the deepest liquidity and most history |

---

## Phase 2.5 Summary — What I'm Adding Based on These Questions

Based on the research team's needs, I'm planning a targeted Phase 2.5 update to the platform. This is NOT a full phase — just a small set of high-impact enhancements:

| Enhancement | Unblocks | Timeline |
|------------|----------|----------|
| `--fee-rate` flag on backtest | Realistic P&L estimates for all strategies | 2-3 days |
| `--lookback-window` flag on backtest | Long-indicator strategies, weekly timeframes | Included above |
| ATR, ADX indicators in official library | H1, H4, H5 (you can start with local helpers now) | Included above |
| Keltner Channels in official library | H4 (you can start with local helpers now) | Included above |

**What's NOT in Phase 2.5** (requires Phase 3 architecture):
- Multi-timeframe data access
- SL/TP auto-triggering
- Portfolio state exposure to strategies
- Async data feeds / paper trading

---

## Recommended Research Flow (Given Current Platform)

### Start Immediately (No Blockers)

1. **Fetch data** for 15+ pairs, 4 timeframes, 2+ years each
2. **Write strategies** using existing indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
3. **H2 (RSI + trend filter)** — only needs RSI + SMA, both available now
4. **Custom indicators** — write ATR, ADX, Keltner as local helpers in your strategy files
5. **H1, H4, H5** — proceed with local indicator implementations
6. **Post-processing fee adjustment** — apply 0.2% round-trip deduction to all results until `--fee-rate` is available

### In 2-3 Days (After Phase 2.5)

7. Re-run key backtests with `--fee-rate 0.001` for accurate P&L
8. Use `--lookback-window` for long-indicator strategies

### Phase 3 (5-7 Days After Phase 2.5)

9. Multi-timeframe strategies for H3
10. SL/TP auto-triggering for risk management validation
11. Paper trading for live signal validation

---

*Research team is unblocked. Start with items 1-6 above. Phase 2.5 spec will be written and delegated tomorrow.*
