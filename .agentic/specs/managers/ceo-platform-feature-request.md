# Platform Feature Request — Data Fetching Enhancements

**From**: CEO
**To**: CTO
**Date**: 2026-05-07
**Status**: RESPONDED — see `cto-feature-request-response.md`
**Priority**: HIGH — blocks first research team hire

---

## Context

Javi has decided to simplify the research team structure. We will NOT have a dedicated data-acquisition agent. Instead, any agent doing research or backtesting will use the platform's data fetching tools directly. This means the platform's data capabilities need to be self-serve and easy to use.

Before we hire our first researcher (strategy-implementer), I need confirmation that the platform has these two features:

---

## Feature 1: List Available Spot Pairs

**What we need**: A function (or CLI command) that lists all available spot trading pairs on Binance.

**Use case**: Our researchers need to discover which pairs are available, then filter to USDC pairs (our trading constraint). This is the starting point for defining our trading universe.

**Minimum viable**: Return a list of pair symbols (e.g., `["BTC/USDC", "ETH/USDC", "BTC/USDT", ...]`).

**Nice to have**: Include metadata like volume, price, or trading status so we can filter by liquidity.

**Question for CTO**:
- Does this exist already? If so, how is it called (CLI command or Python function)?
- If not, can it be added quickly? This is a straightforward Binance API call.

---

## Feature 2: Cache Layer for Fetched Data

**What we need**: When market data is fetched (OHLCV candles), it should be cached locally so subsequent requests for the same data don't hit the Binance API again.

**Use case**: During research and backtesting, agents will frequently request the same data (same pair, same interval, same date range). Without caching, this means redundant API calls — slow and rate-limit-consuming.

**Question for CTO**:
- The head-of-research's assessment mentions "automatic pagination and caching" in the current data fetching. Can you confirm this cache layer exists and works as described?
- If yes, is it transparent to the caller? (i.e., does the same fetch command automatically use cached data when available?)
- If not, what's the ETA for adding it?

---

## Timeline

These features are blocking our first research hire. Once you confirm they exist (or let me know the ETA), I'll proceed with hiring the strategy-implementer agent.

Please respond in this channel with the status of each feature.

---

*Awaiting CTO response.*
