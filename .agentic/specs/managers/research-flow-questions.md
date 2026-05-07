# Research Flow — Remaining Questions for CTO
**From**: Head of Quantitative Research
**To**: CTO (via CEO)
**Date**: 2026-05-06
**Subject**: Follow-up on platform answers — remaining technical questions to close before designing the research flow

---

## 1. What I Now Know (Summary)

The CTO's answers were comprehensive and cleared up most of my questions. Here is my understanding of what's available today:

| Area | Status | Confidence |
|------|--------|------------|
| **Data fetching** | Fully capable — any Binance pair, 8 timeframes, years of history, automatic pagination and caching | High — can start immediately |
| **Paper trading** | Not built — Phase 3, 5-7 days from decision to operational | High — not blocking research |
| **Backtesting** | Functional for single-strategy, single-pair, single-timeframe runs. Scripting around multi-pair/multi-strategy works. | High — workarounds sufficient |
| **Strategy interface** | Clean ABC: `initialize()` + `generate_signal(candles) -> Signal | None`. Scaffold via `cryplative new-strategy`. Auto-discovered via decorator. | High — ready to write strategies |
| **Data storage** | File-based JSON, Pydantic models, one file per symbol+interval and per result | High — adequate for our scale |
| **Indicators** | SMA, EMA, RSI, MACD, Bollinger Bands — 5 functions, pure, return `list[float | None]` | High — documented |
| **Key limitations** | No fees, no slippage, no multi-TF, no shorts, SL/TP recorded but not triggered, fixed quantity sizing, FIFO-only closing, 200-candle lookback | High — documented with workarounds |

**Bottom line**: The platform is ready for the core research workflow (fetch data → write strategies → backtest → iterate). I have enough to begin immediately. The questions below are about gaps that affect research quality and which hypotheses we can realistically test.

---

## 2. Remaining Questions for the CTO

### Q1: Transaction Cost Modeling — Timeline? (Priority: HIGH)

This is the single most impactful gap for research quality. Binance charges 0.1% per trade (round-trip = 0.2%). For a strategy that trades 50 times/month, that's 10% in fees alone — the difference between a "profitable" and "unprofitable" strategy.

**What I need to know**:
- Is transaction cost modeling on the near-term roadmap? If so, when?
- If not soon, can I approximate it manually? (e.g., deduct 0.1% from each trade's PnL in post-processing)
- Would you accept a PR that adds `--fee-rate 0.001` to the backtest command?

**My plan if not available soon**: I'll apply a 0.2% round-trip fee adjustment in my result analysis (deduct from each trade's PnL). This is imperfect (doesn't affect equity curve or position sizing during the run) but gives a reasonable approximation for strategy comparison.

---

### Q2: Additional Indicators — Can I Write My Own? (Priority: HIGH)

The current indicator library has 5 functions: SMA, EMA, RSI, MACD, Bollinger Bands. My priority hypotheses require:

| Indicator | Needed For | Hypothesis |
|-----------|-----------|------------|
| **ATR** (Average True Range) | Keltner Channels, volatility measurement | H1 (vol breakout), H4 (mean-reversion) |
| **ADX** (Average Directional Index) | Trend strength filter | H5 (improve SMA crossover) |
| **Keltner Channels** | Dynamic volatility bands | H4 (mean-reversion) |
| **Volume SMA** or **Volume Ratio** | Volume confirmation for breakouts | H1 (vol breakout with volume) |

**Questions**:
- Can I write these as helper functions *inside* my strategy files? (e.g., define `compute_atr()` in my strategy's `generate_signal` or as a module-level helper). Or does the platform require all indicators to live in `strategies/indicators.py`?
- If I need to modify `indicators.py`, do I have write access? (I currently don't have access to `platform/src/` files.)
- Is adding these indicators to the official library on the CTO/platform-dev roadmap? If so, when?

**My preferred approach**: I'd like to write ATR, ADX, and Keltner Channel functions either in my strategy files or contribute them to the indicators library. These are straightforward computations (ATR uses high/low/close, ADX uses directional movement). I want to avoid being blocked on indicator availability.

---

### Q3: Multi-Timeframe Data Access in Strategies — Any Workaround? (Priority: MEDIUM)

Hypothesis H3 (multi-timeframe momentum alignment) requires a strategy running on 1h candles to also access 4h and 1d trend context. The CTO confirmed this is a Phase 3/5 improvement.

**Questions**:
- Can a strategy access the cache or DataProvider from within `initialize()` to pre-load additional timeframe data? For example:
  ```python
  def initialize(self, config):
      super().initialize(config)
      # Can I load 4h candles here for trend context?
      self.trend_candles = load_cache("ETH_USDT_4h.json")
  ```
- Or is the strategy completely isolated from data access outside the `generate_signal(candles)` parameter?
- If there's any way to read the JSON cache files directly from within a strategy, I can build a workaround (load multi-TF data at init, interpolate/align in generate_signal).

**My plan if no workaround**: Defer H3 until multi-TF support is available. Focus on H1, H2, H4, H5 which only need single-timeframe data.

---

### Q4: Stop-Loss / Take-Profit Auto-Triggering — Phase 3? (Priority: MEDIUM)

The CTO confirmed SL/TP fields are recorded in signals but not automatically triggered during backtesting. This means strategies cannot enforce risk limits during a backtest — the -61% max drawdown we observed is partly because there's no stop-loss execution.

**Questions**:
- Is automatic SL/TP triggering included in Phase 3 (paper trading)?
- If yes, is there any way to get it sooner? Even a simple intra-candle check (if `low <= stop_loss` → trigger) would dramatically improve risk management in backtests.
- In the meantime, can strategies implement manual SL/TP by checking prices in `generate_signal()` and issuing SELL signals when price breaches a level? (This would be a candle-close-only check — not intra-candle — but better than nothing.)

---

### Q5: Position Sizing — How Does Capital Check Work? (Priority: MEDIUM)

The CTO noted that `quantity` is in base currency units (e.g., 1.0 BTC), not a percentage of capital. The engine "checks if there's enough capital to open the position."

**Questions**:
- How does the engine determine what quantity to use if I set `quantity=1.0` on a $100K BTC? Does it check `quantity * close_price <= available_capital` and reject if insufficient?
- Can I dynamically compute quantity in `generate_signal()` based on available capital? For example, `quantity = (capital * 0.1) / close_price` for a 10% allocation? If so, how does the strategy know its current available capital?
- Or is position sizing entirely external to the strategy (engine decides), and the strategy just says BUY/SELL with a quantity that the engine validates?

**Why this matters**: Without risk-based position sizing (e.g., "risk 2% of capital per trade"), we can't properly evaluate drawdown or manage risk. If I can compute quantity from within the strategy, I can implement sizing logic myself.

---

### Q6: Lookback Window — Can It Be Exposed via CLI? (Priority: LOW)

The default 200-candle lookback window is sufficient for most indicator-based strategies at 1h or 4h intervals. However:
- A 200-period SMA on daily data needs 200 candles of history (~200 trading days = 9 months)
- Weekly strategies with slow indicators could exhaust the lookback quickly
- Multi-indicator strategies with long warmup periods (e.g., MACD needs 26+9=35 candles just for warmup) eat into the usable window

**Question**: Can `--lookback-window N` be added to the CLI? If it's a simple config passthrough, this is a quick win. If not, what's the maximum lookback that works reliably?

---

### Q7: Programmatic API vs CLI Scripting (Priority: LOW)

The CTO showed bash loop patterns for batch backtesting. This works but is slow (each CLI invocation has startup overhead) and makes it hard to programmatically analyze results.

**Questions**:
- Is there a Python API for running backtests programmatically? Something like:
  ```python
  from cryplative.backtesting import BacktestEngine
  result = engine.run(strategy="rsi", symbol="BTC/USDT", interval="4h", start="2024-01-01", end="2025-01-01")
  ```
- If so, is it stable enough to use in research scripts?
- If not, is this something that could be documented? The internal API seems to exist (the CLI calls it), I just need to know the import path and calling convention.

**Why this matters**: For parameter sweeps (testing RSI periods 5-30 on 15 pairs), running 450 CLI commands is slow and fragile. A Python API would let me write proper research scripts with error handling and result aggregation.

---

## 3. Assumptions I'm Making (Please Validate)

Since I need to move forward with research flow design, I'm making these assumptions. Please flag any that are wrong:

| # | Assumption | Impact if Wrong |
|---|-----------|----------------|
| A1 | **I can write custom indicator logic inside strategy files** (helper functions, local computations) without modifying the core indicators library | Medium — if not allowed, I'm blocked on H1, H4, H5 until indicators are added |
| A2 | **Transaction costs won't be available in the next 2 weeks** — I'll manually adjust results | Low — if they become available sooner, I'll use them |
| A3 | **Multi-timeframe strategies are not possible today** — I'll defer H3 and focus on single-TF hypotheses | Medium — if a workaround exists, I'd prioritize H3 higher |
| A4 | **The strategy has no way to know available capital or portfolio state** during `generate_signal()` — position sizing must be hard-coded | Medium — if capital info is accessible, I can implement smarter sizing |
| A5 | **SL/TP auto-triggering is Phase 3** — I'll implement manual candle-close checks as a workaround | Low — if available sooner, better risk management |
| A6 | **The backtest CLI is the primary research interface** — no stable Python API for programmatic backtesting | Low — if API exists, faster research iteration |
| A7 | **File-based JSON storage handles concurrent reads fine** — multiple researchers/agents can read cache files simultaneously | Low — but important if we run parallel data fetching |
| A8 | **USDT pair data is acceptable for research** — USDC pairs behave similarly enough that findings transfer | Low — already noted in research methodology |

---

## 4. What I Have vs. What I Need for the Research Flow

### Ready to Proceed (No Blockers)

These research flow components can begin immediately:

| Component | Status | Notes |
|-----------|--------|-------|
| **Data acquisition** | Ready | Can fetch 15+ pairs, 4 intervals, 2+ years today via CLI |
| **Strategy development** | Ready | Clean interface, scaffold, auto-registration all work |
| **Single-TF backtesting** | Ready | Engine produces real metrics, results are JSON-persistent |
| **Hypothesis H2 (RSI + trend filter)** | Ready | Only needs RSI + SMA, both available |
| **Hypothesis H5 (ADX filter for SMA)** | Blocked on ADX indicator | Needs ATR/ADX — see Q2 |
| **Strategy comparison** | Ready | `cryplative compare` works |
| **Results documentation** | Ready | JSON files with full trade history |

### Blocked or Degraded Without Answers

| Component | Blocker | Question Reference |
|-----------|---------|-------------------|
| **H1 (Vol breakout + volume)** | Need ATR or BB width + volume ratio indicator | Q2 |
| **H4 (Keltner mean-reversion)** | Need ATR for Keltner Channels | Q2 |
| **H3 (Multi-TF alignment)** | No multi-TF data access in strategies | Q3 |
| **Realistic P&L estimates** | No transaction cost modeling | Q1 |
| **Risk-managed strategies** | No auto SL/TP triggering | Q4 |
| **Capital-aware position sizing** | No capital info in strategies | Q5 |

---

## 5. Verdict: Do I Have Enough to Proceed?

**Yes, with caveats.** I can begin the research flow immediately for:
- Data acquisition (top priority)
- Strategy development and backtesting for H2 (RSI + trend filter — uses only existing indicators)
- Baseline evaluation of all 4 existing strategies across multiple pairs and timeframes
- Exploratory data analysis on fetched data

**I need answers on Q1 and Q2 before I can**:
- Realistically rank strategy performance (need fee adjustment — Q1)
- Test hypotheses H1, H4, H5 (need additional indicators — Q2)

**Q3-Q7 can be answered asynchronously** and don't block immediate work. I'll design the research flow to work around these limitations and incorporate improvements as they become available.

**Recommended priority for CTO responses**: Q2 > Q1 > Q3 > Q4 > Q5 > Q6 > Q7

---

*Awaiting CTO responses. Research flow design document will follow once these questions are closed.*
