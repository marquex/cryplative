# SPEC-002: Research Enhancements (Phase 2.5)

**Author**: CTO Agent
**Date**: 2026-05-07
**Status**: Ready for Implementation
**Assignee**: platform-developer
**Depends on**: SPEC-001 (COMPLETE — Phase 2, all 15 commits)

---

## 0. Purpose

Phase 2 built a researcher-ready platform. Phase 2.5 adds targeted high-impact enhancements based on real research team needs:

1. **List available trading pairs** — blocks first research hire, highest priority
2. **Transaction cost modeling** — essential for realistic backtest results
3. **Lookback window CLI flag** — needed for long-indicator strategies
4. **Additional indicators** — ATR, ADX, Keltner Channels

The CEO has confirmed: **list-pairs is the first deliverable**. Implement it first, notify, then proceed with the rest.

---

## 1. Context — What Exists from Phase 2

Build on the existing codebase from SPEC-001:

| Component | Location | Status |
|-----------|----------|--------|
| MarketFetcher | `src/cryplative/market_fetcher/fetcher.py` | Complete — ccxt + file cache, `get_candles()` |
| Cache module | `src/cryplative/market_fetcher/cache.py` | Complete — file-based JSON cache |
| Indicators library | `src/cryplative/strategies/indicators.py` | Complete — SMA, EMA, RSI, MACD, Bollinger Bands |
| Portfolio tracker | `src/cryplative/portfolio/tracker.py` | Complete — multi-position, `context` param |
| Backtesting engine | `src/cryplative/backtesting/engine.py` | Complete — multi-position, `BacktestConfig` |
| CLI | `src/cryplative/cli.py` | Complete — `strategies`, `fetch`, `backtest`, `new-strategy`, `compare` |
| Strategies | `src/cryplative/strategies/` | Complete — SMA, RSI, MACD, Bollinger Bands, auto-discovery |
| Tests | `tests/` | Complete — 85%+ coverage |
| Config | `src/cryplative/config.py` | Complete — `CryplativeConfig` with pydantic-settings |

**Key interfaces this spec depends on**:
- `MarketFetcher.__init__()` — creates a ccxt exchange instance (Binance)
- `MarketFetcher.get_candles(symbol, interval, ...)` — fetches and caches OHLCV data
- `BacktestConfig` — plain class with fields: `strategy_id`, `symbol`, `interval`, `start_date`, `end_date`, `initial_capital`, `parameters`, `lookback_window`, `max_positions`
- `BacktestEngine.run(config: BacktestConfig) -> StrategyResult` — runs backtest
- `PortfolioTracker.open_position(signal, price, timestamp) -> Trade` — opens position
- `PortfolioTracker.close_oldest(price, timestamp) -> Trade` — closes oldest position (FIFO)

---

## 2. List Available Trading Pairs (PRIORITY 1)

This is the **first deliverable** — it blocks the first research hire. Implement and commit before starting anything else.

### 2.1 `MarketFetcher.list_pairs()` Method

**File**: `src/cryplative/market_fetcher/fetcher.py`

Add a new method to the existing `MarketFetcher` class:

```python
def list_pairs(
    self,
    quote: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    """List available trading pairs from the exchange.

    Returns a list of dicts, each containing:
        - symbol: str          # e.g., "BTC/USDT"
        - base: str            # e.g., "BTC"
        - quote: str           # e.g., "USDT"
        - active: bool         # whether the market is active
        - price_precision: int # decimal places for price
        - min_order_size: float | None  # minimum order quantity

    Args:
        quote: Filter by quote currency (e.g., "USDT", "USDC").
               Case-insensitive. None = no filter.
        active_only: If True (default), exclude delisted/inactive pairs.

    Raises:
        MarketError: If the exchange API call fails after retries.
    """
    ...
```

**Implementation notes**:
- Use `self.exchange.load_markets()` — this is a ccxt call that returns a dict of all markets.
- Each market in the dict has: `symbol`, `base`, `quote`, `active`, `precision.price`, `limits.amount.min`
- Filter by `active` if `active_only=True`
- Filter by `quote` (case-insensitive match on `market['quote']`) if provided
- Return sorted alphabetically by `symbol`
- Handle ccxt exceptions with the same retry logic used in `get_candles()`

### 2.2 `cryplative pairs` CLI Command

**File**: `src/cryplative/cli.py`

Add a new CLI command:

```python
@app.command()
def pairs(
    quote: str = typer.Option(None, help="Filter by quote currency (e.g., USDT, USDC)"),
    active_only: bool = typer.Option(True, help="Exclude delisted/inactive pairs"),
) -> None:
    """List available trading pairs on the exchange.

    Displays a table of trading pairs with their base/quote currencies
    and trading constraints.

    Examples:
        cryplative pairs                     # All active pairs
        cryplative pairs --quote USDT        # Only USDT pairs
        cryplative pairs --quote USDC        # Only USDC pairs
        cryplative pairs --no-active-only    # Include delisted pairs
    """
    ...
```

**Output format** — a Rich table:

```
┏━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Symbol       ┃ Base  ┃ Quote ┃ Min Order Size    ┃
┡━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ BTC/USDT     │ BTC   │ USDT  │ 0.00001           │
│ ETH/USDT     │ ETH   │ USDT  │ 0.0001            │
│ SOL/USDT     │ SOL   │ USDT  │ 0.01              │
│ ...          │ ...   │ ...   │ ...               │
└──────────────┴───────┴───────┴───────────────────┘

Total: 342 pairs
```

**Behavior**:
1. Create a `MarketFetcher` instance
2. Call `list_pairs(quote=quote, active_only=active_only)`
3. Display as a Rich table
4. Print total count at the bottom
5. Handle errors gracefully (API failure → clear error message)
6. If no pairs match the filter, print "No pairs found matching your criteria."

### 2.3 Testing Requirements

**`test_market_fetcher.py`** (update existing):
- `list_pairs()` returns a non-empty list when called without filters
- `list_pairs(quote="USDT")` returns only USDT pairs
- `list_pairs(quote="usdt")` case-insensitive — same result as "USDT"
- `list_pairs(active_only=False)` includes more pairs than `active_only=True`
- Return value has correct dict structure (symbol, base, quote, active, price_precision, min_order_size)
- Results are sorted alphabetically by symbol
- Handles ccxt exceptions gracefully

**`test_cli.py`** (update existing):
- `pairs` command outputs a table with pair data
- `pairs --quote USDT` filters correctly
- `pairs` command handles API errors with user-friendly message
- Empty result shows "No pairs found" message

---

## 3. Transaction Cost Modeling

### 3.1 `BacktestConfig` Change

**File**: `src/cryplative/backtesting/engine.py`

Add `fee_rate` to `BacktestConfig`:

```python
class BacktestConfig:
    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 10000.0,
        parameters: dict | None = None,
        lookback_window: int = 200,
        max_positions: int = 1,
        fee_rate: float = 0.0,  # NEW: fee per trade as fraction (e.g., 0.001 = 0.1%)
    ):
        ...
```

Default is `0.0` (no fees) for **backward compatibility** — existing backtests produce identical results.

### 3.2 Fee Deduction in PortfolioTracker

**File**: `src/cryplative/portfolio/tracker.py`

Add `fee_rate` to `PortfolioTracker.__init__()`:

```python
class PortfolioTracker:
    def __init__(
        self,
        initial_capital: float,
        context: RunContext = RunContext.BACKTEST,
        max_positions: int = 1,
        fee_rate: float = 0.0,  # NEW
    ):
        ...
        self.total_fees: float = 0.0  # NEW: running total of all fees paid
```

Deduct fees in both `open_position()` and `close_position()` / `close_oldest()`:

```python
def open_position(self, signal: Signal, price: float, timestamp: int) -> Trade:
    trade_value = signal.quantity * price
    fee = trade_value * self.fee_rate
    self.total_fees += fee
    # Deduct trade_value + fee from capital
    self.capital -= (trade_value + fee)
    ...

def close_position(self, trade: Trade, price: float, timestamp: int) -> Trade:
    trade_value = trade.quantity * price
    fee = trade_value * self.fee_rate
    self.total_fees += fee
    # Add trade_value - fee to capital (fee is a cost)
    self.capital += (trade_value - fee)
    ...
```

### 3.3 Fee Metrics in StrategyResult

**File**: `src/cryplative/core/models.py`

Add fee-related fields to the metrics model (the existing metrics class inside models.py):

```python
total_fees: float = 0.0           # Total fees paid across all trades
fees_per_trade: float = 0.0       # Average fee per trade
fee_impact_return: float = 0.0    # Return % lost to fees
```

**File**: `src/cryplative/backtesting/engine.py`

In `BacktestEngine.run()`, populate the new metrics:

```python
result = StrategyResult(
    ...
    metrics=BacktestMetrics(
        ...
        total_fees=tracker.total_fees,
        fees_per_trade=tracker.total_fees / max(len(closed_trades), 1),
        fee_impact_return=(tracker.total_fees / config.initial_capital) * 100,
    ),
)
```

### 3.4 BacktestEngine Changes

**File**: `src/cryplative/backtesting/engine.py`

Pass `fee_rate` from config to tracker:

```python
tracker = PortfolioTracker(
    initial_capital=config.initial_capital,
    context=RunContext.BACKTEST,
    max_positions=config.max_positions,
    fee_rate=config.fee_rate,  # NEW
)
```

### 3.5 CLI Flag

**File**: `src/cryplative/cli.py`

Add to the `backtest` command:

```python
fee_rate: float = typer.Option(0.0, "--fee-rate", help="Fee rate per trade (e.g., 0.001 for 0.1%%)"),
```

Pass it through to `BacktestConfig(fee_rate=fee_rate, ...)`.

When `fee_rate > 0`, add a note to the backtest output:
```
Fee model: {fee_rate*100:.1f}% per trade | Total fees: ${total_fees:.2f} ({fee_impact:.2f}% of capital)
```

### 3.6 Testing Requirements

- `fee_rate=0.0` (default) produces identical results to Phase 2 (regression test)
- `fee_rate=0.001` correctly deducts fee on entry and exit
- `total_fees` accumulates correctly across multiple trades
- `fees_per_trade` is correct average
- `fee_impact_return` is correct percentage
- Capital is correctly reduced by fees (can open fewer positions when fees are high)
- Fee metrics appear in StrategyResult
- CLI `--fee-rate` flag passes through correctly
- Edge case: fee_rate=0 with many trades — no division by zero in fees_per_trade

---

## 4. Lookback Window CLI Flag

### 4.1 CLI Change

**File**: `src/cryplative/cli.py`

Add to the `backtest` command:

```python
lookback_window: int = typer.Option(200, "--lookback-window", help="Number of candles to pass to strategy for signal generation"),
```

Pass it through to `BacktestConfig(lookback_window=lookback_window, ...)`.

### 4.2 Testing Requirements

- `--lookback-window 500` passes through correctly
- Default (no flag) uses 200
- Invalid values (0, negative) raise clear errors
- Backtest with larger lookback produces different results (longer warmup, more context)

---

## 5. Additional Indicators

**File**: `src/cryplative/strategies/indicators.py`

Add three new indicator functions following the same design principles as existing indicators (pure functions, `list[float]` in, `list[float | None]` out, numpy internally, consistent docstrings).

### 5.1 ATR (Average True Range)

```python
def compute_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    """Average True Range (Wilder's smoothing).

    Takes HIGH, LOW, CLOSE arrays (not just closes like other indicators).
    Returns a list of the same length as inputs. Values are None
    for indices where fewer than `period + 1` data points are available
    (need previous close for True Range calculation).

    Algorithm:
    1. True Range = max(H-L, |H-prev_C|, |L-prev_C|)
       For the first candle (no prev close): TR = H - L
    2. First ATR = simple average of first `period` TR values (starting from index 1)
    3. Subsequent: ATR = (prev_ATR * (period-1) + current_TR) / period (Wilder's smoothing)

    Note: This function takes highs, lows, closes (not just closes)
    because True Range requires high/low data. This is a different
    signature from other indicators — document this clearly.
    """
    ...
```

**Reference test values**:
- ATR is always >= 0
- ATR increases with volatility
- ATR with constant prices (high == low == close) = 0
- Wilder's smoothing seeded with simple average of first `period` TRs

### 5.2 ADX (Average Directional Index)

```python
def compute_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    """Average Directional Index.

    Takes HIGH, LOW, CLOSE arrays.
    Returns a list of the same length as inputs. Values are None
    for indices where insufficient data (need at least 2*period + 1 candles).

    Algorithm:
    1. Compute +DM and -DM for each candle:
       - +DM = max(H - prev_H, 0) if H - prev_H > prev_L - L, else 0
       - -DM = max(prev_L - L, 0) if prev_L - L > H - prev_H, else 0
    2. Smooth +DM and -DM with Wilder's smoothing (same as ATR) → +DI and -DI
    3. DX = |+DI - -DI| / (+DI + -DI) * 100
    4. ADX = Wilder's smooth of DX

    Returns values in range [0, 100].
    ADX < 20: weak/no trend
    ADX > 25: trending
    ADX > 50: strong trend
    """
    ...
```

**Reference test values**:
- ADX returns values in range [0, 100]
- ADX with monotonically increasing closes (strong uptrend) → high ADX
- ADX with flat prices (no trend) → low ADX

### 5.3 Keltner Channels

```python
def compute_keltner_channels(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    ema_period: int = 20,
    atr_period: int = 10,
    atr_multiplier: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Keltner Channels.

    Returns (upper_channel, middle_line, lower_channel).

    Takes CLOSE, HIGH, LOW arrays (closes first for consistency
    with Bollinger Bands signature, despite ATR needing high/low).

    Algorithm:
    1. Middle line = EMA(closes, ema_period)
    2. ATR = compute_atr(highs, lows, closes, atr_period)
    3. Upper channel = Middle + atr_multiplier * ATR
    4. Lower channel = Middle - atr_multiplier * ATR

    Channels are None where either EMA or ATR is None.
    """
    ...
```

**Reference test values**:
- Upper > Middle > Lower when data has any volatility
- Channels widen with increasing volatility, narrow with decreasing
- With constant prices: channels collapse to the price level

### 5.4 Testing Requirements

For each indicator:
- Correct computation with known reference inputs
- Returns `None` for insufficient data period
- Return list(s) same length as input
- Edge cases: empty input, single element, period > len(data)
- ATR: constant prices → 0
- ADX: range [0, 100]
- Keltner: upper > middle > lower
- Works with both `list[float]` and numpy array inputs

---

## 6. Implementation Order

The developer MUST implement in this exact order, committing after each milestone:

| Step | What to implement | Commit message |
|------|-------------------|----------------|
| **1** | **`MarketFetcher.list_pairs()` method + `cryplative pairs` CLI command + tests** | **`feat: add list-pairs command for trading pair discovery`** |
| 2 | Transaction cost modeling: `BacktestConfig.fee_rate`, `PortfolioTracker` fee deduction, fee metrics in `StrategyResult`, CLI `--fee-rate` flag + tests | `feat: add transaction cost modeling to backtesting` |
| 3 | Lookback window CLI flag (`--lookback-window`) + tests | `feat: add --lookback-window CLI flag to backtest command` |
| 4 | ATR indicator + tests | `feat: add ATR indicator to indicators library` |
| 5 | ADX indicator + tests | `feat: add ADX indicator to indicators library` |
| 6 | Keltner Channels indicator + tests | `feat: add Keltner Channels indicator to indicators library` |
| 7 | Update `platform_docs/indicators.md` with ATR, ADX, Keltner documentation | `docs: update indicators reference with ATR, ADX, Keltner Channels` |
| 8 | Update `platform_docs/cli-reference.md` with `pairs` command and new backtest flags | `docs: update CLI reference with pairs command and new flags` |

**IMPORTANT**: Step 1 is the **first deliverable**. After committing Step 1, the developer should confirm completion so the CTO can notify the CEO. Steps 2-8 follow in order.

---

## 7. Testing Requirements

### Coverage Target: 85%+

(Same as Phase 2 — maintain the standard.)

### Test Files to Update

```
tests/
├── test_market_fetcher.py   # Update: list_pairs() tests
├── test_backtesting.py      # Update: fee_rate regression + fee tests
├── test_portfolio.py        # Update: fee deduction tests
├── test_indicators.py       # Update: ATR, ADX, Keltner tests
├── test_cli.py              # Update: pairs command, --fee-rate, --lookback-window tests
└── test_models.py           # Update: fee metrics fields
```

### Key Test Scenarios

**test_market_fetcher.py**:
- `list_pairs()` returns non-empty list
- `list_pairs(quote="USDT")` filters correctly (case-insensitive)
- `list_pairs(active_only=True)` excludes inactive pairs
- Return dicts have correct structure
- Results sorted alphabetically
- Handles ccxt exceptions

**test_backtesting.py**:
- `fee_rate=0.0` identical to Phase 2 results (regression)
- `fee_rate=0.001` deducts correct fee from P&L
- Total fees, fees_per_trade, fee_impact_return are correct
- Capital is reduced by fees (fewer positions possible)

**test_portfolio.py**:
- Fee deducted on open_position
- Fee deducted on close_position / close_oldest
- total_fees accumulates correctly
- fee_rate=0.0 has no effect

**test_indicators.py**:
- ATR: correct with reference values, constant prices → 0
- ADX: range [0, 100], strong trend → high ADX
- Keltner: upper > middle > lower, widens with volatility
- All: None for insufficient data, correct list lengths

**test_cli.py**:
- `pairs` command outputs table with data
- `pairs --quote USDT` filters
- `backtest --fee-rate 0.001` passes through
- `backtest --lookback-window 500` passes through
- Fee output note when fee_rate > 0

---

## 8. Acceptance Criteria

This phase is complete when ALL of the following are true:

### List Pairs (Step 1 — First Deliverable)
- [ ] `MarketFetcher.list_pairs()` returns available pairs with correct metadata
- [ ] `cryplative pairs` displays a Rich table of trading pairs
- [ ] `cryplative pairs --quote USDT` filters to USDT pairs only
- [ ] `cryplative pairs --no-active-only` includes inactive pairs
- [ ] All list-pairs tests pass

### Fee Modeling
- [ ] `cryplative backtest --fee-rate 0.001` deducts fees from trades
- [ ] Fee metrics (total_fees, fees_per_trade, fee_impact_return) in StrategyResult
- [ ] Default (no --fee-rate) produces identical results to Phase 2 (regression)
- [ ] Fee output shown in backtest results when fee_rate > 0

### Lookback Window
- [ ] `cryplative backtest --lookback-window 500` works correctly
- [ ] Default is 200 (backward compatible)

### Indicators
- [ ] `compute_atr()` passes all tests
- [ ] `compute_adx()` passes all tests
- [ ] `compute_keltner_channels()` passes all tests
- [ ] All indicators follow existing design patterns (pure functions, None warmup)

### Quality
- [ ] All tests pass with `uv run pytest`
- [ ] Test coverage >= 85%
- [ ] `uv run ruff check .` passes with no errors
- [ ] `uv run mypy src/` passes with no errors

### Documentation
- [ ] `platform_docs/indicators.md` updated with ATR, ADX, Keltner Channels
- [ ] `platform_docs/cli-reference.md` updated with `pairs` command and new flags

---

## 9. Out of Scope

- Paper trading / live execution (Phase 3)
- Multi-timeframe data access (Phase 3)
- SL/TP auto-triggering (Phase 3)
- Portfolio state exposure to strategies (Phase 3)
- Bun.js API (Phase 4)
- React webapp (Phase 4)
- Database integration (Phase 4+)
- Strategy parameter optimization / grid search (Phase 5)
- `--sort-by volume` on pairs command (volume data requires 24h ticker API, not available via `load_markets()` — deferred)

---

*This specification is self-contained. The platform-developer should build on the Phase 2 codebase from SPEC-001. Step 1 (list-pairs) is the first priority deliverable.*
