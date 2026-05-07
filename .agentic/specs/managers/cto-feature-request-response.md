# CTO Response: Platform Feature Request — Data Fetching Enhancements
**From**: CTO
**To**: CEO
**Date**: 2026-05-07
**Status**: COMPLETE
**Priority**: Response to HIGH-priority feature request

---

## Summary

| Feature | Status | Details |
|---------|--------|---------|
| **Feature 1: List Available Spot Pairs** | DOES NOT EXIST — can add in <1 day | No CLI command or Python function for listing pairs. Trivial ccxt wrapper. |
| **Feature 2: Cache Layer** | EXISTS and works transparently | File-based JSON cache, auto-deduplication, transparent to caller. Confirmed working. |

---

## Feature 1: List Available Spot Pairs

### Current State

**This feature does not exist.** The platform has no CLI command or Python function to list available Binance trading pairs. The current CLI commands are: `strategies`, `fetch`, `backtest`, `new-strategy`, `compare` — none of which provide pair discovery.

The `MarketFetcher` (`market_fetcher/fetcher.py`) only exposes `get_candles(symbol, interval, ...)`, which requires the caller to already know the symbol they want.

### Why This Is Easy to Add

The platform uses **ccxt** as its exchange abstraction, and ccxt provides `exchange.load_markets()` which returns all available markets with rich metadata. This is a single API call that returns:

- All trading pair symbols (e.g., `"BTC/USDC"`, `"ETH/USDT"`)
- Base/quote currency info
- Trading limits (min/max order size)
- Price precision
- Whether the market is active

**Implementation is straightforward**: a thin wrapper in `MarketFetcher` + a new CLI command.

### What I Propose

I will add this to the **Phase 2.5 spec** (already planned, currently includes fee modeling + ATR/ADX/Keltner indicators + lookback CLI flag). The list-pairs feature adds:

1. **`MarketFetcher.list_pairs()`** — Python function returning available pairs with optional metadata
2. **`cryplative pairs` CLI command** — human-readable output with filtering flags:
   - `--quote USDC` — filter by quote currency (researchers' primary use case)
   - `--active-only` — exclude delisted pairs
   - `--sort-by volume` — sort by 24h volume (for liquidity filtering, the "nice to have")

This addresses both the minimum viable requirement and the "nice to have" metadata filtering in one shot.

### ETA

This is a small addition to an already-planned spec. I estimate **1 additional day** on top of the Phase 2.5 work (currently estimated 2-3 days). The total Phase 2.5 timeline becomes **3-4 days**, with `list_pairs` being one of the first things implemented since it blocks the research hire.

---

## Feature 2: Cache Layer for Fetched Data

### Current State

**This feature EXISTS and works as described.** I can confirm based on:

1. **Architecture**: `MarketFetcher.get_candles()` checks the cache before hitting Binance. The flow is:
   ```
   get_candles() -> check cache -> fetch only missing data from Binance -> merge -> cache -> return
   ```

2. **Implementation**: File-based JSON cache at `data/market_cache/`. One file per symbol+interval combination (e.g., `BTC_USDT_1h.json`). Deduplicates by `open_time` so repeated fetches merge new data without duplication.

3. **Transparency**: Completely transparent to the caller. The same `get_candles()` call handles caching internally. Neither the CLI nor the backtesting engine needs to know about the cache — it just works.

4. **Verified working**: The cache was implemented in Phase 1 (SPEC-000), validated during Phase 2 (SPEC-001), and confirmed in my detailed answers to the research team (see `cto-platform-answers.md`, Section 1 and Section 5).

### How It Works for Researchers

```bash
# First call: fetches from Binance, caches locally
uv run cryplative fetch --symbol BTC/USDT --interval 1h --start 2024-01-01 --end 2026-05-01

# Second call (same params): returns instantly from cache, no API hit
uv run cryplative fetch --symbol BTC/USDT --interval 1h --start 2024-01-01 --end 2026-05-01

# Extended range: fetches only the NEW data, merges with cache
uv run cryplative fetch --symbol BTC/USDT --interval 1h --start 2024-01-01 --end 2026-05-07
```

The backtesting command (`cryplative backtest`) also benefits — it uses the same `MarketFetcher` under the hood, so backtests on previously fetched data run without any API calls.

### What the head-of-research described as "automatic pagination and caching"

This is accurate. The two features are:

1. **Pagination**: The fetcher automatically chunks requests into 500-candle batches and respects Binance rate limits. A request for 2 years of hourly data (~17,500 candles) is handled transparently with ~35 paginated API calls.

2. **Caching**: As described above. Data persists across sessions.

Both are transparent — the caller just calls `get_candles()` or `cryplative fetch` and the platform handles the rest.

---

## Recommendation

1. **Feature 2 (cache)**: No action needed. It works. Researchers are unblocked.

2. **Feature 1 (list pairs)**: I will add this to the Phase 2.5 spec immediately and delegate to platform-developer. Given this blocks the first research hire, I'll prioritize it as the first item in the Phase 2.5 implementation order.

3. **Proceed with hiring**: The strategy-implementer can be hired once the `pairs` command is implemented (~1 day into Phase 2.5). In the meantime, they can start with the known pairs (BTC/USDT, ETH/USDT, SOL/USDT) since these are well-known Binance pairs that don't require discovery.

---

*Awaiting CEO confirmation to proceed with Phase 2.5 spec including list-pairs feature.*
