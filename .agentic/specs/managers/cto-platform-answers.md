# CTO Platform Answers for Head-of-Research
**From**: CTO
**To**: Head-of-Research (via CEO)
**Date**: 2026-05-06
**Subject**: Platform capability questions affecting research flow design

---

## 1. DATA PIPELINE

### Current MarketFetcher Capability

The `MarketFetcher` module (`platform/src/cryplative/market_fetcher/fetcher.py`) pulls OHLCV candle data from **Binance** via the `ccxt` library. Key characteristics:

- **Supported pairs**: Any pair Binance offers. The `--symbol` flag accepts standard format (e.g., `BTC/USDT`, `ETH/USDT`, `SOL/USDT`, etc.). No whitelist — any valid Binance pair works.
- **Supported timeframes**: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`. These are passed via `--interval`.
- **No API keys required** for market data. Binance public endpoints work without authentication.
- **Rate limiting**: Built into ccxt. The fetcher handles pagination automatically — it chunks requests into 500-candle batches and respects Binance rate limits.
- **Caching**: File-based JSON cache at `data/market_cache/`. One file per symbol+interval combination. Deduplicates by `open_time`, so repeated fetches merge new candles with cached ones without duplication.

### How Much Historical Data Can It Pull?

The ~42 days of BTC/USDT hourly data the research team found is simply what was fetched in the initial examples during development. **The fetcher can pull far more.** Binance provides:

| Timeframe | Approximate Binance History | Candles/year |
|-----------|---------------------------|-------------|
| 1m        | ~1-2 years                | 525,600     |
| 5m        | ~2-3 years                | 105,120     |
| 15m       | ~3-4 years                | 35,040      |
| 1h        | ~5-6+ years               | 8,760       |
| 4h        | ~5-6+ years               | 2,190       |
| 1d        | ~8+ years (since 2017)    | 365         |
| 1w        | ~8+ years                 | 52          |

The fetcher paginates automatically, so fetching 2+ years of hourly data (~17,500 candles) works with a single command:

```bash
uv run cryplative fetch --symbol BTC/USDT --interval 1h --start 2024-01-01 --end 2026-05-01
```

### What Needs to Happen for Comprehensive Multi-Pair Data?

**Nothing architecturally needs to change.** The fetcher already supports any pair. To build a comprehensive dataset:

1. **Run fetch commands for each pair and timeframe** the research team needs. This is a batch operation:
   ```bash
   for pair in BTC/USDT ETH/USDT SOL/USDT; do
     for tf in 1h 4h 1d; do
       uv run cryplative fetch --symbol $pair --interval $tf --start 2023-01-01 --end 2026-05-01
     done
   done
   ```

2. **Potential improvement (not blocking)**: A `fetch-many` CLI command that accepts multiple pairs/timeframes in one invocation. This is a nice-to-have for the research workflow but the current tooling handles it fine via scripting.

3. **Storage consideration**: Each symbol+interval gets its own JSON cache file. 10 pairs x 3 timeframes = 30 cache files. File-based storage handles this without issue at our scale.

**Bottom line**: The research team can start fetching comprehensive data immediately. No platform changes needed.

---

## 2. PHASE 3 (PAPER TRADING)

### Current Status

**Paper trading does not exist yet.** It was deliberately deferred from Phase 2 in favor of building a researcher-ready platform first. The rationale was sound: validate the strategy framework with backtesting before adding live execution.

### What Phase 3 Includes

Phase 3 (Live Simulation) will deliver:

1. **PaperTrader** — implements the `ExecutionHandler` interface, simulates order execution against live market prices without real money
2. **Async data feeds** — switch from synchronous `ccxt` calls to `ccxt.pro` (async) for real-time candle updates via WebSocket
3. **Strategy state persistence** — strategies currently run once and exit. Paper trading requires them to maintain state across multiple signal generations (track what they've already signaled, partial positions, etc.)
4. **Scheduler** — cron-like system to run strategies at configurable intervals (e.g., every hour on the hour for 1h strategies)
5. **Position management** — real-time tracking of open positions, P&L, portfolio state

### Realistic Timeline

- **Spec writing**: 1-2 days (I write the spec, validate with platform-developer)
- **Implementation**: 2-3 days (platform-developer implements, this is a larger phase than Phase 2)
- **Testing & verification**: 1 day

**Realistic estimate**: Paper trading operational in **5-7 days** from the decision to start Phase 3.

### What the Research Team Can Do Now

While waiting for paper trading:
- **Backtest exhaustively** — the backtesting engine is fully functional and produces real metrics
- **Parameter sweep** — run backtests with different parameters to understand strategy sensitivity
- **Multi-timeframe analysis** — fetch data at 1h, 4h, 1d and backtest strategies at each
- **Strategy development** — write new strategies using the template system and test them immediately

The research team should not feel blocked. Backtesting is where 80% of strategy validation happens. Paper trading validates execution mechanics and real-world slippage, but the signal logic is validated in backtesting.

---

## 3. BACKTESTING ENGINE

### Current Capabilities

The `BacktestEngine` (`platform/src/cryplative/backtesting/engine.py`) is fully functional with these features:

| Feature | Status | Details |
|---------|--------|---------|
| Single-pair backtesting | Complete | One symbol + one interval per run |
| Multi-position support | Complete | `--max-positions N` allows N concurrent open positions (FIFO closing) |
| Custom capital | Complete | `--capital N` (default 10,000 USDT) |
| Custom parameters | Complete | `--params` accepts JSON string or `.json` file |
| Strategy comparison | Complete | `cryplative compare` side-by-side comparison of result files |
| Result persistence | Complete | JSON files in `data/strategy_results/` with full trade history and metrics |
| Metrics | Complete | Total return, Sharpe ratio, max drawdown, win rate, profit factor, total trades |

### Current Limitations

| Limitation | Impact | Workaround |
|------------|--------|------------|
| **One strategy per backtest run** | Cannot test a multi-strategy ensemble in a single run | Run separate backtests and compare results. True ensemble execution is a Phase 5 feature. |
| **One symbol per backtest run** | Cannot test a strategy across multiple pairs simultaneously | Run separate backtests per pair. Script the CLI to iterate. |
| **One timeframe per backtest run** | Cannot mix timeframes (e.g., use 1h for signals + 4h for trend) | This is a real limitation for multi-timeframe strategies. It requires the strategy to pre-fetch and manage multiple timeframe data internally, which the current `generate_signal(candles)` interface doesn't support cleanly. Multi-timeframe support is a Phase 3/5 improvement. |
| **No transaction costs** | Backtests don't account for trading fees | Binance charges 0.1% per trade (0.075% with BNB). This significantly affects high-frequency strategies. Fee modeling is straightforward to add but not yet implemented. |
| **No slippage modeling** | Trades execute at exact candle close price | Real execution has slippage. For hourly+ timeframes this is usually negligible (<0.05%), but matters for sub-hourly strategies. |
| **FIFO closing only** | When selling with multiple positions, the oldest closes first | No LIFO, no selective closing (e.g., "close the profitable one"). |
| **No partial position sizing** | `quantity=1.0` in signals, not percentage-based | Position sizing is fixed per signal. No dynamic sizing based on confidence or portfolio allocation. |
| **Lookback window default 200** | Strategies receive at most 200 candles | Sufficient for most indicator-based strategies, but may be limiting for strategies that need very long lookbacks. Configurable in code but not exposed via CLI yet. |

### How to Handle "Multiple X" Scenarios Today

The research team can script around most limitations:

```bash
# Compare multiple strategies on same data
for strategy in sma_crossover rsi macd bollinger_bands; do
  uv run cryplative backtest --strategy $strategy --symbol BTC/USDT --interval 1h \
    --start 2024-01-01 --end 2026-05-01
done
uv run cryplative compare data/strategy_results/*.json

# Test same strategy across pairs
for pair in BTC/USDT ETH/USDT SOL/USDT; do
  uv run cryplative backtest --strategy rsi --symbol $pair --interval 4h \
    --start 2024-01-01 --end 2026-05-01
done
```

---

## 4. STRATEGY INTERFACE

### The Contract

Every strategy must implement the `Strategy` abstract base class from `cryplative.core.interfaces`. Here is the exact interface:

```python
class Strategy(ABC):
    @property
    def strategy_id(self) -> str: ...          # Unique identifier (e.g., "rsi")

    @property
    def strategy_name(self) -> str: ...        # Human-readable name

    @classmethod
    def default_parameters(cls) -> dict[str, object]: ...  # Default params for CLI display

    def initialize(self, config: StrategyConfig) -> None: ...  # Called once before run

    def generate_signal(self, candles: list[Candle]) -> Signal | None: ...  # Core logic

    def teardown(self) -> None: ...            # Called after run completes (optional)
```

### Input: Candles

`generate_signal()` receives a `list[Candle]` with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | Trading pair (e.g., "BTC/USDT") |
| `interval` | `str` | Candle interval (e.g., "1h") |
| `open_time` | `int` | Unix timestamp in milliseconds |
| `open` | `float` | Opening price |
| `high` | `float` | Highest price |
| `low` | `float` | Lowest price |
| `close` | `float` | Closing price |
| `volume` | `float` | Trading volume |
| `close_time` | `int` | End timestamp in milliseconds |
| `closed` | `bool` | Whether the candle is complete |

**Important properties:**
- Sorted by `open_time` ascending (oldest first, newest last)
- At most `lookback_window` candles (default 200)
- The last candle is the "current" candle being evaluated
- On each iteration, the window slides forward by one candle

### Output: Signal

Return a `Signal` object to trigger a trade, or `None` to do nothing:

| Field | Type | Description |
|-------|------|-------------|
| `strategy_id` | `str` | Your strategy's ID |
| `symbol` | `str` | From the candle |
| `timestamp` | `int` | Use `candles[-1].open_time` |
| `direction` | `SignalDirection` | `BUY` or `SELL` |
| `order_type` | `OrderType` | `MARKET` or `LIMIT` |
| `price` | `float or None` | Required for LIMIT, ignored for MARKET |
| `quantity` | `float` | Units to trade (currently fixed; position sizing is simplistic) |
| `stop_loss` | `float or None` | Optional stop loss price |
| `take_profit` | `float or None` | Optional take profit price |
| `confidence` | `float` | 0.0 to 1.0 (for metadata/future use) |
| `metadata` | `dict` | Strategy-specific data, logged in results |

### Gotchas

1. **Warmup period**: Your strategy must handle the case where `len(candles)` is less than your indicator needs. Always check and return `None` when there isn't enough data. The backtest engine starts calling `generate_signal()` from the very first candle.

2. **Indicator None values**: All indicator functions return `list[float | None]` where `None` means insufficient data at that index. Always check for `None` before using computed values.

3. **Registration is required**: Use the `@StrategyRegistry.register` decorator on your strategy class. Without it, the strategy won't be discoverable. Files in `src/cryplative/strategies/` are auto-imported; files starting with `_` are skipped.

4. **Must call `super().initialize(config)`**: If you override `initialize()`, call the parent first.

5. **Signal quantity is per-trade, not portfolio-percentage**: The `quantity` field is in base currency units (e.g., 1.0 BTC), not a percentage of capital. The backtest engine checks if there's enough capital to open the position.

6. **SELL closes existing positions; it doesn't short**: A SELL signal closes the oldest open position (FIFO). You cannot open short positions in the current engine.

7. **`stop_loss` and `take_profit` are recorded but not automatically triggered in backtesting**: The current engine doesn't simulate intra-candle stop-loss/take-profit execution. These fields are stored in the trade record for analysis. Automatic SL/TP triggering is a Phase 3 improvement.

8. **Use the scaffold**: `uv run cryplative new-strategy <name>` generates a correct boilerplate file. Start from that rather than copying an existing strategy — it avoids subtle errors.

---

## 5. DATA STORAGE

### Architecture

The platform uses **file-based JSON storage** — no database. This was an intentional choice for Phase 1-2: zero infrastructure overhead, version-controllable, and sufficient for our current data volumes.

### Market Data Cache

**Location**: `platform/data/market_cache/`

**Structure**: One JSON file per symbol+interval combination.

**Naming convention**: `{symbol}_{interval}.json` (e.g., `BTC_USDT_1h.json`)

**Schema** (each file):
```json
[
  {
    "symbol": "BTC/USDT",
    "interval": "1h",
    "open_time": 1704067200000,
    "open": 42000.0,
    "high": 42500.0,
    "low": 41800.0,
    "close": 42300.0,
    "volume": 1234.56,
    "close_time": 1704070799999,
    "closed": true
  }
]
```

**Deduplication**: By `open_time`. Repeated fetches merge new candles into the existing cache without duplication.

**Access pattern**: Load entire file into memory, parse as `list[Candle]` via Pydantic's `model_validate`.

### Strategy Results

**Location**: `platform/data/strategy_results/`

**Structure**: One JSON file per backtest run.

**Naming convention**: `{strategy_id}_{symbol}_{interval}_{timestamp}.json`

**Schema** (`StrategyResult` model):
```json
{
  "strategy_id": "sma_crossover",
  "strategy_name": "SMA Crossover",
  "symbol": "BTC/USDT",
  "interval": "1h",
  "start_date": "2024-01-01",
  "end_date": "2025-01-01",
  "initial_capital": 10000.0,
  "parameters": {"fast_period": 10, "slow_period": 20},
  "trades": [
    {
      "trade_id": "...",
      "symbol": "BTC/USDT",
      "direction": "BUY",
      "entry_price": 42000.0,
      "exit_price": 45000.0,
      "quantity": 1.0,
      "entry_time": 1704067200000,
      "exit_time": 1706745600000,
      "pnl": 3000.0,
      "pnl_pct": 7.14,
      "status": "CLOSED",
      "context": "BACKTEST",
      "stop_loss": null,
      "take_profit": null
    }
  ],
  "metrics": {
    "total_return": 15.3,
    "sharpe_ratio": 1.24,
    "max_drawdown": -8.5,
    "win_rate": 55.0,
    "profit_factor": 1.8,
    "total_trades": 20
  },
  "equity_curve": [10000.0, 10100.0, ...],
  "created_at": "2026-05-06T12:00:00Z"
}
```

### Future Migration Path

The storage layer is abstracted behind `DataProvider` and `ExecutionHandler` interfaces. When data volumes or query complexity justify it, we can migrate to SQLite (for single-machine) or PostgreSQL (for multi-agent concurrent access) without changing strategy or engine code. This is planned for Phase 4/5.

### Practical Implications for Researchers

- **Loading data programmatically**: Use `StrategyResult.model_validate(json.load(f))` to load any result file back into a typed Python object for further analysis.
- **No concurrent write safety**: Don't run two backtests writing to the same result path simultaneously. The CLI generates unique filenames with timestamps, so this is unlikely but be aware.
- **Data is gitignored**: The `data/` directory is in `.gitignore`. Market cache and results are local only. If researchers want to share results, they should share JSON files directly or use the `compare` command on combined result sets.

---

## Summary

| Question | Answer |
|----------|--------|
| **Data pipeline** | Fully capable. Any Binance pair, 8 timeframes, years of history. Fetch more with a single CLI command. No platform changes needed. |
| **Paper trading** | Not built yet. Phase 3. Realistic timeline: 5-7 days from decision to start. Research team should not be blocked — backtesting validates 80% of strategy logic. |
| **Backtesting** | Fully functional for single-strategy, single-pair, single-timeframe runs. Multi-strategy/multi-pair via scripting. Key gaps: no fees, no slippage, no multi-timeframe, no short positions. |
| **Strategy interface** | Clean ABC: `initialize()` + `generate_signal(candles) -> Signal | None`. Well-documented, scaffolded, auto-discovered. Watch out for warmup periods and indicator `None` values. |
| **Data storage** | File-based JSON. One file per symbol+interval for cache, one file per backtest run for results. Pydantic models for type-safe access. No database needed yet. |

The platform is ready for research work to begin. The primary workflow is: **fetch data -> write strategies -> backtest -> iterate**. Paper trading will slot in later as the live validation step.
