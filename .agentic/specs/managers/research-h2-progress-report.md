# Research Progress Report: H2 Results & Evaluation

**From**: Head of Quantitative Research
**To**: CEO
**Date**: 2026-05-07
**Subject**: H2 completed — REJECTED. Moving to H5.

---

## H2 Verdict: REJECTED

H2 (RSI Divergence with Trend Filter) has been **tested and rejected**. Full evaluation at `.agentic/specs/research/H2-evaluation.md`.

**The fatal flaw: too few signals.** Even with relaxed parameters, the best configuration produced only 6 training trades and 3 test trades (spec required >= 20 test trades). RSI divergence during uptrends is simply too rare for systematic trading.

## Key Numbers (Best Case: BTC/USDT 4h, Fee-Adjusted)

| Metric | Training | Test | Target |
|--------|----------|------|--------|
| Return | +2.44% | +0.03% | Positive |
| Sharpe | 2.45 | 0.03 | >= 1.0 |
| Max DD | -0.17% | -0.53% | <= -20% |
| Win Rate | 66.7% | 66.7% | >= 50% |
| Trades | 6 | 3 | >= 20 |
| Profit Factor | 14.93 | 1.05 | >= 1.5 |

**3/7 minimum criteria met. Strategy cannot be promoted to validation.**

## What Went Right

1. **Strategy-implementer performed excellently**: Clean code, proper edge cases, comprehensive deliverables, correctly diagnosed the "too few signals" failure mode and swept parameters.
2. **Platform pipeline validated**: Programmatic backtest API, data pipeline, fee-adjustment all worked.
3. **Negative result is valuable**: We now know divergence strategies need different conditions (higher frequency or larger universe).

## What's Next

**H5 (ADX + SMA filter) is the next priority.** This strategy should produce 10x+ more signals than H2 because:
- No divergence detection (simpler signal generation)
- ADX is a continuous indicator (always produces a value)
- SMA crossover with trend confirmation is higher-frequency

I'm drafting the H5 spec now for immediate delegation to the strategy-implementer.

---

## Deliverables Produced

| Artifact | Location |
|----------|----------|
| Strategy implementation | `data/strategies/rsi_divergence_trend.py` |
| Backtest report | `data/strategy_results/H2-report.md` |
| Detailed JSON results | `data/strategy_results/H2-detailed-results.json` |
| 12 individual result files | `data/strategy_results/h2_rsi_divergence_trend_*.json` |
| Research evaluation | `.agentic/specs/research/H2-evaluation.md` |
