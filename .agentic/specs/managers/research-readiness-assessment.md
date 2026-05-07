# Research Readiness Assessment — Final Onboarding Deliverable

**From**: Head of Quantitative Research
**To**: CEO
**Date**: 2026-05-06
**Status**: COMPLETE — Research flow is unblocked

---

## 1. Verdict: YES — I Have Everything Needed to Design the Research Flow

After two rounds of CTO answers (Round 1: platform capabilities, Round 2: 7 follow-up questions), all technical questions are resolved. I can design and execute the complete research flow starting today.

### What Changed with the Second Round of Answers

| Question | Answer | Impact |
|----------|--------|--------|
| Q1: Transaction costs | Phase 2.5, ETA 2-3 days. Post-processing workaround works now. | Unblocks realistic P&L — use 0.2% round-trip deduction today, engine-level fix in days |
| Q2: Custom indicators | **YES — no restrictions.** Write any helper functions in strategy files. | **Fully unblocks H1, H4, H5.** ATR, ADX, Keltner, Volume SMA all implementable locally |
| Q3: Multi-TF access | No official support. Fragile cache-reading workaround exists. Phase 3. | H3 deferred. Not blocking — focus on H1, H2, H4, H5 first |
| Q4: SL/TP auto-triggering | Phase 3. Manual candle-close workaround available today. | Can implement stop-loss discipline via self-tracked state in strategy |
| Q5: Position sizing | Strategy cannot see capital. Fixed sizing only. Phase 3 exposes portfolio state. | Use initial-capital approximation or fixed quantities for now |
| Q6: Lookback window CLI flag | Phase 2.5 will add it. Can work around in code today. | Nice-to-have, not blocking |
| Q7: Programmatic Python API | **Internal API exists and works.** Import paths documented. | Unlocks proper parameter sweeps — no need for 450 CLI invocations |

### Assumption Validation Summary

| # | My Assumption | CTO's Answer |
|---|--------------|--------------|
| A1 | Can write custom indicators in strategy files | **CONFIRMED** |
| A2 | Transaction costs won't be available for 2 weeks | **CORRECTED** — Phase 2.5, 2-3 days |
| A3 | Multi-TF strategies not possible today | **CONFIRMED** — workaround fragile, defer |
| A4 | Strategy has no way to know capital | **CONFIRMED** — Phase 3 will fix |
| A5 | SL/TP auto-triggering is Phase 3 | **CONFIRMED** — workaround available |
| A6 | No Python API for programmatic backtesting | **CORRECTED** — internal API exists |
| A7 | Concurrent cache reads work fine | **CONFIRMED** |
| A8 | USDT pair data is acceptable for research | **CONFIRMED** |

### Remaining Unknowns (CEO Strategic Questions — NOT Blocking)

These affect *targets and scope*, not the research *process*. The methodology works regardless:

| Question | Who Must Answer | Impact if Unanswered | My Default Assumption |
|----------|----------------|---------------------|----------------------|
| Target annual return | CEO | Don't know what "good enough" looks like | >40% annualized |
| Initial capital amount | CEO | Can't design position sizing | $10,000 USDT |
| Max drawdown tolerance | CEO | Can't set risk parameters | -20% absolute max |
| Available USDC pairs on Binance EU | CEO | Don't know our trading universe | Top 15 USDT pairs, implement on USDC equivalents |
| Trading frequency preference | CEO | Can't prioritize timeframe focus | Medium (4h/daily focus, 3-8 trades/week) |

I will proceed with the default assumptions above and adjust when the CEO provides guidance.

---

## 2. Research Flow Outline

Given everything I now know about the platform, here is the research flow I will design and execute:

### Phase R1: Data Foundation (Days 1-3)

**Objective**: Comprehensive, quality-validated dataset for 15+ pairs across 4 timeframes.

- Define trading universe (top 15-20 USDT pairs by volume on Binance)
- Fetch 2+ years of OHLCV data for each pair at 1h, 4h, 1d, 1w intervals
- Validate data quality: check for gaps, duplicates, price anomalies, missing candles
- Store in `data/market_cache/` (platform handles this automatically)
- Document data inventory: pairs, date ranges, candle counts, quality notes

**Execution**: Delegate to `data-acquisition` agent. This is their sole focus.

### Phase R2: Exploratory Analysis (Days 3-7, overlaps with R1 completion)

**Objective**: Understand the data before testing hypotheses.

- Per-pair characterization: volatility profile, average daily range, trend vs. range ratio
- Regime identification: classify periods as bull/bear/sideways for each pair
- Indicator behavior analysis: RSI distribution, BB width patterns, SMA crossover frequency
- Correlation matrix between pairs (for future portfolio diversification)
- Document findings in per-pair research notes

**Execution**: Can begin on BTC data immediately (we have some). Expand as data comes in.

### Phase R3: Hypothesis Testing (Days 5-14)

**Objective**: Systematically test hypotheses H1, H2, H4, H5 against historical data.

For each hypothesis:
1. **Define test spec**: exact entry/exit rules, parameters, success criteria (written before testing)
2. **Implement strategy**: write strategy file with custom indicators as local helpers
3. **Run backtests**: use programmatic Python API for parameter sweeps across pairs/timeframes
4. **Apply fee adjustment**: deduct 0.2% round-trip from all trade P&Ls in post-processing (until Phase 2.5 ships)
5. **Analyze results**: Sharpe, max DD, win rate, profit factor, trade count
6. **Out-of-sample validation**: split data into train (70%) / test (30%), report both
7. **Document findings**: hypothesis, methodology, in-sample results, out-of-sample results, verdict

**Priority order**: H2 → H5 → H1 → H4
- H2 (RSI + trend filter): Only uses existing indicators (RSI + SMA). Quick win.
- H5 (ADX filter for SMA): Needs ATR/ADX — write locally. Improves existing strategy.
- H1 (Volatility breakout): Needs BB width + volume ratio. Write locally.
- H4 (Keltner mean-reversion): Needs ATR + Keltner. Write locally.

H3 (Multi-TF alignment): Deferred to Phase 3 when multi-TF support ships.

### Phase R4: Validation & Refinement (Days 12-18)

**Objective**: Turn promising backtests into validated strategies.

- Walk-forward validation: rolling 6-month train / 2-month test windows
- Parameter sensitivity: test how results change as parameters vary ±20%
- Regime breakdown: verify strategy works across at least 2 market regimes (bull + sideways minimum)
- Re-run with `--fee-rate` once Phase 2.5 ships for final confirmation
- Stress test: worst-case scenarios, maximum consecutive losses, correlation breakdown

**Success criteria for strategy graduation**:
- Sharpe >= 1.0 on out-of-sample data
- Max drawdown <= -20%
- Profitable after 0.2% round-trip fees
- >= 30 trades in test period
- Profitable across >= 2 market regimes

### Phase R5: Portfolio Design (Days 16-21)

**Objective**: Combine validated strategies into a coherent portfolio.

- Select best strategies per pair (per-pair philosophy: no one-size-fits-all)
- Analyze strategy correlation: ensure diversification across signals
- Allocate capital based on strategy confidence (Sharpe, consistency, regime coverage)
- Define position sizing rules (risk per trade, max exposure per pair, max total exposure)
- Set portfolio-level risk limits (max drawdown trigger, rebalancing rules)
- Simulate combined portfolio performance

### Phase R6: Paper Trading Preparation (Days 19-25, aligns with Phase 3 delivery)

**Objective**: Validate strategies in real-time without capital risk.

- When Phase 3 ships: deploy top 2-3 strategies in paper trading mode
- Monitor signal generation, execution simulation, and P&L tracking
- Compare real-time results to backtest expectations
- Flag any discrepancies (slippage, missed signals, execution issues)
- 2+ weeks of paper trading before any live capital deployment

### Phase R7: Live Deployment Decision (Day 25+)

**Objective**: Evidence-based go/no-go for live capital.

- Present CEO with full evidence package: backtest results, out-of-sample validation, paper trading performance
- Recommend specific capital allocation per strategy
- Define monitoring thresholds and kill switches
- Establish review cadence (weekly performance review, monthly strategy audit)

### Research Workflow Diagram

```
Data Acquisition (R1)
    │
    ▼
Exploratory Analysis (R2) ──► Per-pair research notes
    │
    ▼
Hypothesis Testing (R3)
    │
    ├─► H2: RSI + Trend Filter ──► Results ──┐
    ├─► H5: ADX + SMA Filter ──► Results ────┤
    ├─► H1: Vol Breakout + Volume ──► Results ┤
    └─► H4: Keltner Mean-Rev ──► Results ─────┤
                                              │
                                              ▼
                                    Validation & Refinement (R4)
                                              │
                                              ▼
                                    Portfolio Design (R5)
                                              │
                                              ▼
                                    Paper Trading (R6) ←── awaits Phase 3
                                              │
                                              ▼
                                    Live Deployment Decision (R7)
```

---

## 3. Platform Change Requests

These are documented for future scheduling. None block immediate research work.

### Scheduled (CTO Has Committed — Phase 2.5, ~2-3 Days)

| # | Request | Unblocks | Priority |
|---|---------|----------|----------|
| PC-1 | `--fee-rate` flag on backtest CLI | Accurate P&L in engine (vs post-processing) | HIGH |
| PC-2 | `--lookback-window N` flag on backtest CLI | Long-indicator strategies, weekly timeframes | LOW |
| PC-3 | ATR, ADX, Keltner in official indicators library | Code reuse across strategies (we use local helpers until then) | MEDIUM |

### Scheduled (CTO Has Committed — Phase 3, ~5-7 Days After Phase 2.5)

| # | Request | Unblocks | Priority |
|---|---------|----------|----------|
| PC-4 | Multi-timeframe data access in strategies | H3 — multi-TF momentum alignment | MEDIUM |
| PC-5 | SL/TP auto-triggering in backtests | Realistic risk management in backtests | HIGH |
| PC-6 | Portfolio state exposure to strategies (capital, positions) | Dynamic position sizing, risk-aware signals | HIGH |
| PC-7 | Paper trading system | Live signal validation before capital deployment | HIGH |

### Requested (Not Yet Scheduled — Document for Future Planning)

| # | Request | Unblocks | Priority |
|---|---------|----------|----------|
| PC-8 | Walk-forward validation mode | Automated train/test splits, overfitting detection | HIGH |
| PC-9 | Batch backtesting CLI (multi-pair sweep) | Faster research iteration | MEDIUM |
| PC-10 | Regime detection module | Adaptive strategies, regime-aware position sizing | MEDIUM |
| PC-11 | Percent-based position sizing (% of capital) | Risk-based allocation, Kelly criterion | MEDIUM |
| PC-12 | Multi-strategy ensemble execution | Portfolio-level backtesting in a single run | LOW |
| PC-13 | `fetch-many` CLI command | Batch data acquisition in one invocation | LOW |

### Workarounds in Use Today

| Limitation | Workaround | Quality |
|------------|-----------|---------|
| No fee modeling | Post-processing: deduct 0.2% round-trip per trade | Adequate for comparison; slightly overstates compounding |
| No custom indicators in library | Write as local helpers in strategy files | Fully functional; duplicate code across strategies |
| No multi-TF access | Defer H3; fragile cache-reading workaround available if needed later | Acceptable — H3 is lowest priority hypothesis |
| No SL/TP triggering | Manual candle-close check via self-tracked position state | Underestimates true stop-loss hits (no intra-candle simulation) |
| No capital visibility | Hard-code initial capital approximation; fixed quantities | Drifts from reality as trades occur |
| No lookback CLI flag | Edit config in code or use `--params` JSON passthrough | Workable |
| No batch CLI | Script bash loops or use internal Python API | Python API approach preferred |

---

## 4. Recommended Hiring Order

### 1. Data Acquisition Specialist (`data-acquisition`) — HIRE IMMEDIATELY

**Why first**: Everything depends on data. We have 42 days of BTC 1h. We need 15+ pairs, 4 intervals, 2+ years. The data pipeline is fully capable — this agent just needs to run it and validate quality.

**Scope of first task**:
- Fetch top 15-20 USDT pairs at 1h, 4h, 1d, 1w intervals
- 2+ years of history where available (2024-01-01 to 2026-05-01 minimum)
- Validate data quality: check gaps, anomalies, and completeness
- Document the full data inventory

**Success criteria**: 15+ pairs with complete, quality-validated data at all 4 intervals in `data/market_cache/`.

**Estimated duration**: 1-2 days (fetching is automated, validation is the real work)

### 2. Strategy Researcher (`strategy-researcher`) — HIRE WHEN DATA IS READY

**Why second**: With data available, we need a dedicated agent to systematically test hypotheses. The platform is researcher-ready — clean strategy interface, backtesting engine, programmatic API.

**Scope of first task**:
- Begin with H2 (RSI + trend filter) — uses only existing indicators
- Then H5 (ADX + SMA filter), H1 (vol breakout), H4 (Keltner mean-reversion)
- Follow the research quality standards: hypothesis → test → out-of-sample validation → document
- Apply fee adjustment post-processing to all results

**Success criteria**: 2+ strategies meeting minimum viable criteria (Sharpe >= 1.0, max DD <= -20%, profitable after fees, 30+ trades in test period).

**Estimated duration**: 7-10 days of systematic testing

### 3. Strategy Implementer (`strategy-implementer`) — HIRE AFTER FIRST VALIDATED STRATEGIES

**Why third**: Once strategies are validated in backtesting, they need production-quality implementation before paper/live deployment. This includes proper error handling, logging, position tracking, and preparation for the Phase 3 execution framework.

**Scope of first task**:
- Take validated strategy specifications from the researcher
- Implement with production-quality code (error handling, logging, edge cases)
- Add risk management: stop-losses, take-profits, max position limits
- Prepare for paper trading integration when Phase 3 ships

**Success criteria**: Strategies running in paper trading mode with proper logging and risk controls.

**Estimated duration**: 3-5 days per strategy

### 4. Portfolio & Risk Manager (`portfolio-risk`) — HIRE AFTER 3+ VALIDATED STRATEGIES

**Why last**: Portfolio construction requires multiple validated strategies to be meaningful. With only one strategy, there's nothing to allocate. This agent becomes valuable once we have several strategies with different characteristics (trend, mean-reversion, volatility) across multiple pairs.

**Scope of first task**:
- Analyze correlations between validated strategies
- Design portfolio allocation across strategies and pairs
- Set risk limits: max portfolio drawdown, max single-pair exposure, max total exposure
- Define position sizing framework
- Simulate combined portfolio performance

**Success criteria**: A portfolio with defined allocation, risk limits, and simulated performance exceeding individual strategies on a risk-adjusted basis.

**Estimated duration**: 5-7 days for initial portfolio design

### Hiring Timeline

```
Day 1-2:    data-acquisition (active)
Day 3:      data-acquisition winds down, strategy-researcher activated
Day 3-14:   strategy-researcher (active)
Day 12-16:  strategy-implementer activated (first validated strategies ready)
Day 16-25:  strategy-implementer + paper trading (Phase 3 alignment)
Day 20+:    portfolio-risk activated (3+ validated strategies available)
```

---

## 5. Summary

**Research readiness**: FULLY UNBLOCKED. All technical questions answered. Research flow can begin today.

**Immediate next steps**:
1. Activate `data-acquisition` agent to fetch comprehensive dataset
2. I begin exploratory analysis on existing BTC data while data fetches
3. Begin H2 strategy development (RSI + trend filter — no custom indicators needed)
4. Prepare H5, H1, H4 strategy implementations with local indicator helpers
5. Align with CEO on target metrics (return, drawdown, capital) when available

**Key insight from CTO answers**: The platform is more capable than initially apparent. The programmatic Python API (Q7) and unrestricted custom indicator logic (Q2) together give us a highly flexible research environment. We don't need to wait for most platform enhancements — we can work around limitations today and adopt improvements as they ship.

**Risk**: The biggest remaining risk is not technical but strategic — without CEO input on target returns and drawdown tolerance, we're optimizing toward an undefined objective. I've set reasonable defaults (>40% annualized, -20% max DD) and will adjust when guidance arrives.

---

*This completes my onboarding assessment. The research function is ready to begin operations.*
