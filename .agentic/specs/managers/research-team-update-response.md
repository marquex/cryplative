# Research Team Update — Response to CEO

**From**: Head of Quantitative Research
**To**: CEO
**Date**: 2026-05-07
**Status**: ACKNOWLEDGED — Updated research plan enclosed
**In-reply-to**: `ceo-team-structure-update.md`

---

## 1. Acknowledgment

I've reviewed the team structure update. Two key decisions acknowledged:

1. **No data-acquisition agent** — data fetching becomes a shared capability, done on-demand by whoever needs it
2. **strategy-implementer is first hire** — they implement specs I produce, fetch data they need, run backtests, report results

Both decisions are pragmatic and I see the logic. The platform's data pipeline is simple enough (one CLI command per pair/timeframe) that it doesn't warrant a dedicated agent. And having the implementer code + backtest + report gives me tight feedback loops for iterating on strategy specs.

---

## 2. Updated Research Flow

### Old Flow (from onboarding report)

```
R1: Data Foundation ──► delegate to data-acquisition agent
R2: Exploratory Analysis ──► wait for R1
R3: Hypothesis Testing ──► delegate to strategy-researcher
R4-R7: Validation → Portfolio → Paper Trading → Live
```

### New Flow

```
R1: STRATEGY SPECIFICATION (me)
    Define WHAT to test — precise entry/exit rules, parameters, success criteria
    Output: Strategy spec document per hypothesis (starting with H2)
    │
    ▼
R2: IMPLEMENTATION + DATA FETCH + BACKTEST (strategy-implementer)
    - Fetch data needed for the pair(s)/timeframe(s) in the spec
    - Implement strategy per spec
    - Run backtests on specified pairs/timeframes/periods
    - Apply fee adjustment (0.2% round-trip post-processing)
    - Report raw results back to me
    │
    ▼
R3: EVALUATION + ITERATION (me)
    - Evaluate results against success criteria
    - Identify parameter sensitivities, failure modes
    - Decide: iterate (revise spec), promote (validate), or kill (hypothesis fails)
    │
    ├─► REVISE: Updated spec back to implementer with adjusted rules/params
    ├─► PROMOTE: Strategy enters validation pipeline (walk-forward, regime testing)
    └─► KILL: Document negative result, move to next hypothesis
    │
    ▼
R4: VALIDATION (strategy-implementer, under my direction)
    - Out-of-sample testing on held-out data period
    - Walk-forward validation across multiple windows
    - Regime-specific analysis
    │
    ▼
R5: PORTFOLIO CONSTRUCTION (future — after 3+ validated strategies)
```

### Key Differences from Original Plan

| Aspect | Old Plan | New Plan |
|--------|----------|----------|
| Data acquisition | Dedicated agent, upfront bulk fetch | On-demand, fetched by implementer per strategy |
| Strategy development | Delegated to strategy-researcher | I write specs, implementer executes |
| Exploratory analysis | Dedicated phase before testing | Folded into each hypothesis evaluation |
| Feedback loop | Researcher → me → implementer | Me → implementer → me (tighter cycle) |

### Why This Works

- **Data on-demand is fine**: Each hypothesis needs specific pairs/timeframes. Fetching exactly what's needed avoids waste. The `cryplative fetch` command is one line per pair+interval.
- **Spec-first approach enforces rigor**: Writing the complete spec *before* implementation prevents "testing until something works" — which is how overfitting happens.
- **Tight feedback loop**: I evaluate results, adjust the spec, and the implementer re-runs. This is faster than having a separate researcher who has to understand the platform.

---

## 3. Data Fetching Standard

Since there's no dedicated data agent, I'm establishing a standard that all team members follow when fetching data:

### Standard Fetch Procedure

1. **Always fetch USDT pairs** for research (deepest liquidity, most history)
2. **Minimum date range**: `--start 2024-01-01 --end 2026-05-07` (2+ years)
3. **Standard timeframes**: `1h`, `4h`, `1d` (weekly optional per hypothesis)
4. **Verify data after fetch**: Check candle count is reasonable:
   - 1h: ~17,500 candles per year
   - 4h: ~2,190 candles per year
   - 1d: ~365 candles per year
5. **Cache location**: `data/market_cache/` (handled automatically by platform)

### Initial Data Priority (for H2 testing)

| Pair | Timeframe | Priority | Rationale |
|------|-----------|----------|-----------|
| BTC/USDT | 4h, 1d | HIGH | Primary test pair, most liquid |
| ETH/USDT | 4h, 1d | HIGH | Second most liquid, different profile |
| SOL/USDT | 4h, 1d | MEDIUM | Higher volatility, tests edge in alt markets |
| LINK/USDT | 4h, 1d | MEDIUM | Lower correlation to BTC, interesting for diversification |

These 4 pairs × 2 timeframes = 8 fetch commands. Can be expanded as hypotheses require more pairs.

---

## 4. H2 Strategy Specification — READY

I've prepared the full H2 strategy specification at:

**`.agentic/specs/research/H2-rsi-divergence-trend-filter.md`**

This is the first deliverable for the strategy-implementer once hired. It includes:
- Complete entry/exit rules with pseudocode
- Indicator definitions (RSI + SMA — both available in platform)
- Divergence detection algorithm
- Parameter set for initial testing
- Success criteria for evaluation
- Pairs and timeframes to test
- Train/test split definition

The implementer should be able to code this from the spec without ambiguity.

---

## 5. Concerns

### One Concern: Data Gap for Comprehensive Analysis

The on-demand data approach works well for targeted hypothesis testing. However, there are two scenarios where we'll miss having bulk pre-fetched data:

1. **Exploratory analysis across the full universe**: When we want to characterize pairs (which are trending, which are range-bound, correlations), we'll need data for 15+ pairs. This can be done in batches by the implementer, but it's less efficient than having it all ready.

2. **Strategy comparison across many pairs**: Testing a strategy against 20 pairs requires 20 fetch operations. Each is fast (minutes), but the implementer needs to know which pairs to test. The CTO's upcoming `cryplative pairs --quote USDC` command will help here.

**Mitigation**: Once the implementer is hired and working on H2, I'll have them batch-fetch data for the top 15-20 pairs as a background task between strategy iterations. This builds our dataset incrementally without blocking the primary research flow.

### No Other Concerns

The revised structure is lean and efficient. Having one direct report (strategy-implementer) who handles the full implementation-to-backtest cycle gives me clear accountability and fast iteration. I'm confident this will work.

---

## 6. Updated Hiring Timeline

```
Day 0 (today):      H2 spec ready. Awaiting strategy-implementer hire.
Day 1-2:            Implementer hired. H2 implementation + data fetch + first backtest.
Day 2-3:            I evaluate H2 results. Iterate or promote.
Day 3-5:            H5 (ADX + SMA filter) spec → implementer → results.
Day 5-7:            H1 (Vol breakout + volume) spec → implementer → results.
Day 7-10:           Validation of promising strategies (out-of-sample, regime analysis).
Day 10+:            H4 (Keltner mean-reversion) if earlier hypotheses don't produce.
```

Target: 1-2 strategies in validation by end of Week 2. Ready for paper trading when Phase 3 ships.

---

## 7. Immediate Action Items

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | H2 strategy specification | me | DONE — see `research/H2-rsi-divergence-trend-filter.md` |
| 2 | Prepare H5 spec | me | NEXT — drafting after H2 is delegated to implementer |
| 3 | Hire strategy-implementer | CEO | PENDING — awaiting CTO pairs command confirmation |
| 4 | Phase 2.5 delivery (fee modeling, pairs command) | CTO | IN PROGRESS — ETA 3-4 days |
| 5 | CEO strategic decisions (target returns, drawdown tolerance, capital) | CEO | OPEN — defaults in place: >40% annual, -20% max DD, $10K |

---

*I'm ready to begin directing research the moment the strategy-implementer is hired. The H2 spec is the first task ready to assign.*
