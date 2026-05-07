# H2 Evaluation: RSI Divergence with Trend Filter

**Evaluator**: Head of Quantitative Research
**Date**: 2026-05-07
**Verdict**: FAIL — Does not meet minimum viability criteria

---

## Executive Summary

H2 (RSI Divergence with Trend Filter) fails on the fundamental criterion: **too few signals** to be statistically meaningful. Even after the implementer correctly identified and addressed the spec's anticipated failure mode by relaxing parameters, the best configuration produced only 6-7 trades on the primary training set. The strategy cannot be promoted to validation.

---

## Results Against Success Criteria

### Minimum Viable Criteria (from H2 spec Section 10)

| Criterion | Threshold | Best Result (BTC 4h fee-adj) | Pass? |
|-----------|-----------|------------------------------|-------|
| Sharpe >= 1.0 (OOS) | >= 1.0 | 0.03 (test) | FAIL |
| Max Drawdown <= -20% | <= -20% | -0.53% (test) | PASS (trivially — too few trades) |
| Win Rate >= 50% OR PF >= 2.0 | >= 50% / >= 2.0 | 66.7% / 1.05 (test) | Win PASS, PF FAIL |
| Profit Factor >= 1.5 (OOS) | >= 1.5 | 1.05 (test) | FAIL |
| Trade Count >= 20 (test) | >= 20 | 3 | CATASTROPHIC FAIL |
| Fee-Adjusted Return > 0 | Positive | +0.03% (test) | PASS (marginal) |
| Regime Coverage >= 2 | >= 2 regimes | ~1.5 (mostly BTC bull) | FAIL |

**Score: 3/7 minimum criteria met. Strategy REJECTED.**

---

## Detailed Analysis

### 1. Signal Scarcity — The Fatal Flaw

The spec anticipated this as failure mode #1: *"Divergence is rare."* The data confirms it:

**With spec defaults** (pivot_window=5, min_pivot_spacing=10, oversold_threshold=40):
- 1 signal across entire BTC 4h dataset (2.3 years)

**With relaxed parameters** (pivot_window=3, min_pivot_spacing=5, oversold_threshold=50):
- BTC 4h training: 6 trades
- BTC 4h test: 3 trades
- Best case (SOL 4h training): 7 trades
- Multiple configs: 0-2 trades

Even the relaxed parameters produce far too few trades for statistical significance. The spec required >= 20 in the test period alone; the best test result was 3.

### 2. Parameter Relaxation Concern

The implementer made the right call adjusting parameters — the spec explicitly suggested this path. However, this raises a serious concern:

- **oversold_threshold moved from 40 to 50**: This means we're entering when RSI is below 50 — essentially "not overbought." This is a fundamentally different signal than "oversold divergence." At RSI 50, the asset isn't necessarily oversold at all.
- **pivot_window moved from 5 to 3**: Smaller windows create noisier pivot detection, increasing false divergences.

The relaxed parameters arguably test a different hypothesis than the original H2.

### 3. Out-of-Sample Degradation

| Config | Train Fee-Adj Return | Test Fee-Adj Return | Degradation |
|--------|---------------------|---------------------|-------------|
| BTC 4h | +2.44% | +0.03% | -99% |
| ETH 4h | -0.03% | +0.22% | improved (from near-zero) |
| SOL 4h | +0.97% | -0.44% | flipped negative |
| LINK 4h | +0.78% | +0.04% | -95% |

BTC's 99% degradation from train to test is a red flag, but with only 6/3 trades, none of these numbers are statistically meaningful.

### 4. 1-Day Timeframe: Dead

ETH and BTC 1d produced 0-1 trades. The 1d timeframe generates too few candles (~860) for meaningful divergence detection with a 200-SMA filter. This is not a viable timeframe for this strategy.

### 5. Positive Observations

- **Implementation quality**: The code is well-structured, follows the spec precisely, handles edge cases properly (warmup, None RSI, pivot spacing, force-close).
- **Fee adjustment**: Correctly implemented and reported.
- **BTC 4h training metrics look good on paper** (Sharpe 2.45, PF 14.9) — but this is an illusion of small sample size.
- **Exit distribution**: RSI overbought exits dominate in BTC (4/6), which aligns with the hypothesis that divergences in uptrends lead to reversals.

---

## Root Cause Analysis

**Why does H2 fail?**

1. **RSI divergence is inherently rare**: Price making a lower low while RSI makes a higher low, during an uptrend (above 200 SMA), with RSI below a threshold — this is a 4-constraint filter on an already-scarce pattern.

2. **Uptrend filter removes most opportunities**: In an uptrend, pullbacks deep enough to create lower lows are uncommon. The trend filter does its job — it keeps us out of downtrends — but it also eliminates most divergence candidates.

3. **Divergence timing is imprecise**: Even when true divergence exists, the exact candle of detection varies with pivot_window sensitivity. The pattern is robust conceptually but fragile in implementation.

---

## Recommendation

**H2 is REJECTED for live deployment or further validation.**

### Options going forward:

**Option A: Abandon H2 entirely** (RECOMMENDED)
- The hypothesis has been tested and found wanting. RSI divergence is too rare for systematic trading within our constraints.
- Lesson learned: Divergence-based strategies require either (a) much higher frequency data (15min or below), (b) no trend filter, or (c) a much larger universe of tradeable assets.
- Move on to H5 (ADX + SMA filter) which should produce many more signals.

**Option B: Radical rework as a different strategy**
- Remove the divergence requirement entirely — just buy when RSI < threshold during uptrend.
- This is essentially "buy the dip in uptrends" — a simpler, higher-signal strategy.
- However, this is a fundamentally different hypothesis and should be written as a new spec.

### What we gained from H2:

1. **Validated the implementer**: The strategy-implementer executed the spec competently, handled edge cases well, produced comprehensive deliverables, and correctly diagnosed the "too few signals" failure mode.
2. **Negative result is valuable**: We now know RSI divergence + trend filter doesn't produce enough signals. We won't waste more time on it.
3. **Platform validation**: The programmatic backtest API, data pipeline, and fee-adjustment workflow all functioned correctly.
4. **Parameter sensitivity data**: We learned that pivot_window and oversold_threshold are extremely sensitive parameters for this strategy type.

---

## Next Steps

1. **Archive H2** — mark as TESTED/REJECTED in strategy catalog
2. **Prioritize H5** — ADX + SMA filter should produce 10x more signals
3. **Draft H5 spec** immediately for delegation
4. **Consider "buy the dip" variant** — simplified H2 without divergence, as a future hypothesis
