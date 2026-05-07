# Head-of-Research Onboarding: CEO Summary Report

**Date**: 2026-05-06
**Status**: Onboarding complete. Research team ready to proceed.

---

## Decisions Taken

### 1. Platform is Research-Ready (No Immediate Changes Needed)
The CTO confirmed the platform is more capable than initially apparent:
- **Custom indicators**: Strategies can include any Python logic internally — no need to add indicators to the official library. This unblocks 3 of 5 research hypotheses immediately.
- **Data pipeline**: MarketFetcher can pull historical data for any pair/timeframe. The current ~42 days of BTC data was just an initial run, not a platform limitation.
- **Backtesting engine**: Fully functional with no material limitations for current needs.
- **Programmatic Python API**: Researchers can script data fetching, backtesting, and analysis directly.

**Decision**: No platform changes needed now. 13 enhancement requests documented by head-of-research for future scheduling.

### 2. Research Flow: 7-Phase Pipeline
The head-of-research has designed the following flow:
1. **Data Foundation** — Fetch comprehensive historical data across multiple pairs and timeframes
2. **Exploratory Analysis** — Analyze market characteristics per pair
3. **Hypothesis Testing** — Prioritized: H2 (RSI + trend filter) → H5 (ADX filter) → H1 (volatility breakout) → H4 (Keltner Channel)
4. **Validation & Refinement** — Rigorous out-of-sample testing
5. **Portfolio Design** — Combine strategies, manage position sizing
6. **Paper Trading** — Test in simulated live conditions (depends on Phase 3 platform support)
7. **Live Deployment Decision** — Evidence-based go/no-go

### 3. Hypothesis Prioritization (H3 Deferred)
- **H2** (RSI divergence + trend filter): Tests first — uses only existing indicators
- **H5** (ADX filter for existing strategies): Quick value add
- **H1** (Volatility breakout): Requires custom ATR — now confirmed possible
- **H4** (Keltner Channel mean-reversion): Requires custom indicators — confirmed possible
- **H3** (Multi-timeframe momentum): **Deferred to Phase 3** — platform doesn't support multi-TF data access yet. CTO has workarounds but they're cumbersome.

### 4. Hiring Order for Research Team
1. **data-acquisition** — FIRST. Everything depends on having comprehensive data. This is the critical path.
2. **strategy-researcher** — Second. Once data is available, begin hypothesis testing.
3. **strategy-implementer** — Third. Formalize promising strategies into the platform.
4. **portfolio-risk** — Last. Portfolio construction and risk management once strategies are validated.

### 5. Assumptions Made by Head-of-Research (Pending CEO/Javi Input)
The head-of-research set reasonable defaults that will be adjusted:
| Parameter | Default Assumption | Status |
|---|---|---|
| Target return | >40% annualized | Needs Javi input |
| Max drawdown | -20% | Needs Javi input |
| Initial capital | $10,000 | Needs Javi input |
| Trading pairs | TBD (pending data acquisition) | Research decision |
| Risk-free rate | 4.5% (for Sharpe) | Reasonable |

---

## Platform Change Requests (Documented, NOT Scheduled Now)
The head-of-research identified 13 platform enhancements, categorized by priority:

### Phase 2.5 (Imminent — blocks research quality)
1. **Transaction cost modeling** in backtesting (currently no fees — all P&L inflated)
2. **Trade-level logging** in backtest results (currently only aggregate metrics)
3. **Equity curve data** output from backtests

### Phase 3 (Paper Trading Support)
4. Paper trading mode
5. Multi-timeframe data access in strategies
6. Position sizing controls (percentage-based)
7. Stop-loss / take-profit integration in backtests

### Future Planning
8. Strategy parameter optimization framework
9. Walk-forward analysis tooling
10. Monte Carlo simulation
11. Correlation matrix between strategies
12. Automated data refresh pipeline
13. Strategy performance dashboard

---

## Next Steps

### Immediate (This Session)
- [ ] **CEO**: Get Javi's input on target return, max drawdown tolerance, and initial capital
- [ ] **CEO**: Communicate these targets to head-of-research

### Short-Term (Next Actions)
1. **Hire data-acquisition agent** — critical path, blocks everything else
2. **Head-of-Research**: Begin exploratory analysis on existing BTC data while data-acquisition agent ramps up
3. **CTO**: Plan Phase 2.5 platform enhancements (especially transaction cost modeling)

### Medium-Term
1. **Hire strategy-researcher** (after data-acquisition is operational)
2. **CTO**: Draft Phase 3 (paper trading) specification
3. **Head-of-Research**: Test H2 hypothesis (RSI + trend filter) as first strategy validation

---

## Communication Artifacts
All cross-team communication is documented in the managers channel:
- `.agentic/specs/managers/cto-platform-answers.md` — CTO's first round of answers
- `.agentic/specs/managers/research-flow-questions.md` — Head-of-research's 7 follow-up questions
- `.agentic/specs/managers/cto-platform-answers-2.md` — CTO's second round of answers
- `.agentic/specs/managers/research-readiness-assessment.md` — Head-of-research's final assessment

## Key Insight
The platform is more capable than initially apparent. The CTO's answers removed all technical blockers. The critical path is: **hire data-acquisition → fetch data → test H2 → validate → scale**. Everything else follows from having data and a first validated strategy.
