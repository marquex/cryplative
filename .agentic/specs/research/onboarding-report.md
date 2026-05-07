# Head of Research — Onboarding Report

**Date**: 2026-05-06
**Author**: Head of Quantitative Research
**Status**: Initial assessment and research roadmap proposal

---

## 1. Executive Summary

I have completed my initial assessment of Cryplative's research infrastructure, platform capabilities, and current data/assets. The platform foundation is solid — Phase 1 (core) and Phase 2 (researcher-ready) are complete, giving us a functional backtesting engine, 4 baseline strategies, and a clean strategy development workflow. However, the **research pipeline is essentially at zero** — we have minimal data, one exploratory backtest with poor results, and no systematic research process yet.

This report covers: (a) what exists today, (b) critical gaps, (c) proposed research flow, (d) initial hypotheses to test, (e) team hiring priorities, and (f) questions/blockers for the CEO.

---

## 2. Current State Assessment

### 2.1 Platform Capabilities (What We Can Do Today)

| Capability | Status | Notes |
|---|---|---|
| Fetch OHLCV data from Binance | Available | Via ccxt, with caching. `cryplative fetch` command. |
| Run backtests on historical data | Available | `cryplative backtest` command. Multi-position support. |
| Strategy development workflow | Available | Template system, auto-registration, indicators library. |
| Strategy comparison | Available | `cryplative compare` command with metric highlighting. |
| Paper trading | NOT available | Phase 3 — planned but not built. |
| Walk-forward validation | NOT available | No train/test split automation. |
| Transaction cost modeling | NOT available | Backtests do not account for fees or slippage. |
| Portfolio construction | NOT available | No multi-strategy portfolio engine. |
| Regime detection | NOT available | No market regime classification. |
| Parameter optimization | NOT available | No grid search or optimization tooling. |

### 2.2 Available Strategies (4 Baseline Strategies)

| Strategy ID | Type | Logic |
|---|---|---|
| `sma_crossover` | Trend-following | Buys when fast SMA crosses above slow SMA. Sells on reverse. |
| `rsi` | Mean-reversion | Buys when RSI < oversold. Sells when RSI > overbought. |
| `macd` | Trend-following | Buys on MACD histogram crossing above zero. Sells on cross below. |
| `bollinger_bands` | Volatility-based | Buys when price touches lower band. Sells at upper band. |

**Assessment**: These are standard textbook strategies. They serve as useful baselines but are unlikely to generate alpha on their own. They tend to:
- Whipsaw in sideways/ranging markets (especially SMA and MACD)
- Miss fast moves or enter too late (especially RSI and Bollinger in strong trends)
- Lack adaptability — fixed parameters don't adjust to changing market conditions

### 2.3 Data Inventory

| Asset | Timeframe | Period | Candles | Quality |
|---|---|---|---|---|
| BTC/USDT | 1h | Jan 1 — Feb 11, 2025 | 1,000 | Appears clean, deduplicated by open_time |

**This is critically insufficient.** We need:
- **More pairs**: ETH, SOL, AVAX, LINK, DOGE, and other liquid USDC/USDT pairs
- **More timeframes**: 4h, 1d, 1w (our target intervals) — currently only 1h exists
- **More history**: At minimum 1-2 years of data for statistically significant backtesting. 42 days is not enough.
- **Broader coverage**: Different market regimes (bull 2024, bear 2022, sideways periods)

### 2.4 Existing Backtest Results — Analysis

**SMA Crossover on BTC/USDT, 1h, Jan 1-31, 2025** (default params: fast=10, slow=20):

| Metric | Value | Assessment |
|---|---|---|
| Total Return | +12.58% | Decent nominal return, but see drawdown |
| Sharpe Ratio | 0.22 | **Poor** — returns do not compensate for risk taken. Target > 1.0 |
| Max Drawdown | -61.1% | **Catastrophic** — strategy lost 61% of capital at worst point |
| Win Rate | 42.11% | Below 50% — losers outnumber winners |
| Total Trades | 19 | Reasonable frequency for 1 month on 1h |
| Profit Factor | 1.1 | Barely positive. Winners barely exceed losers. |

**Key observations from the trade log:**
- Heavy whipsawing: many trades with tiny gains/losses (< 1%) indicating the strategy enters/exits in sideways action
- One large winner (+$4,678, +4.9%) offsets several losers — dependency on rare big moves
- One devastating loss (-$5,369, -5.0%) shows no risk management (no stop-loss)
- All positions use quantity=1.0 regardless of price — no position sizing
- No transaction costs deducted — real returns would be lower

**Verdict**: This strategy, as-is, is not suitable for live trading. The -61% max drawdown alone disqualifies it for capital deployment.

---

## 3. Critical Gaps and Risks

### 3.1 Gaps That Block Research Progress

| # | Gap | Severity | Impact |
|---|---|---|---|
| G1 | **Insufficient data** — only 42 days of BTC 1h | Critical | Cannot do statistically valid backtesting |
| G2 | **No transaction cost modeling** | High | Results are unrealistic — Binance charges 0.1% per trade |
| G3 | **No walk-forward validation** | High | Cannot detect overfitting properly |
| G4 | **No stop-loss / risk management** in strategies | High | Unlimited downside per trade (as seen in -61% drawdown) |
| G5 | **No position sizing** — fixed quantity=1.0 | Medium | No capital allocation logic |
| G6 | **No regime detection** | Medium | Strategies applied blindly across all market conditions |
| G7 | **Only USDT pairs fetched** — need to validate USDC pair similarity | Low | Research note says this is acceptable, but should confirm |

### 3.2 Risks to Research Quality

| Risk | Description | Mitigation |
|---|---|---|
| **Overfitting** | With limited data, optimizing parameters will overfit to noise | Use walk-forward validation, require out-of-sample confirmation |
| **Data snooping** | Testing many strategies on the same data without correction | Maintain a "research log" tracking all tests, use Bonferroni correction |
| **Survivorship bias** | Only testing on BTC (which survived and thrived) | Test on a wide universe including assets that underperformed |
| **Short backtest periods** | 1 month results have no statistical significance | Require minimum 6 months, ideally 1+ year of test data |

---

## 4. Proposed Research Flow

### 4.1 The End-to-End Research Pipeline

```
PHASE 1: DATA ACQUISITION
  Define universe of USDC trading pairs on Binance
  Fetch historical data for all pairs across target intervals (1h, 4h, 1d, 1w)
  Validate data quality (check gaps, anomalies, duplicates)
  Store in standardized format in data/market_cache/

PHASE 2: EXPLORATORY ANALYSIS
  Characterize each pair: volatility profile, trendiness, mean-reversion tendency
  Identify market regimes per pair (bull/bear/sideways periods)
  Analyze indicator behavior per pair (RSI ranges, BB width patterns, etc.)
  Document findings in per-pair research notes

PHASE 3: HYPOTHESIS GENERATION & TESTING
  Formulate specific, testable hypotheses (e.g., "RSI < 30 with BB squeeze predicts +3% in 48h on ETH with >55% accuracy")
  Define success criteria upfront (min Sharpe, max drawdown, min win rate)
  Backtest on training period (e.g., 2024-01 to 2025-06)
  Validate on out-of-sample period (e.g., 2025-07 to 2025-12)
  Document results — both positive and negative

PHASE 4: STRATEGY VALIDATION
  Walk-forward validation across multiple windows
  Stress test across different market regimes
  Include transaction costs (0.1% maker/taker on Binance)
  Confirm statistical significance (min 30 trades, profitable across regimes)
  Forward test via paper trading before any live deployment

PHASE 5: PORTFOLIO CONSTRUCTION
  Combine validated per-pair strategies into a portfolio
  Allocate capital based on strategy confidence and correlation
  Set position sizing rules (risk per trade, max exposure per pair)
  Define rebalancing rules
  Set max portfolio drawdown limits

PHASE 6: MONITORING & ITERATION
  Track live performance vs. backtest expectations
  Detect strategy degradation early
  Feed performance data back into research loop
  Continuously generate new hypotheses
```

### 4.2 Research Quality Standards

Every research output must include:
1. **Hypothesis**: Clear statement of what we're testing and why
2. **Data**: What data was used, what period, what train/test split
3. **Methodology**: Exact parameters, entry/exit rules, position sizing
4. **Results**: All metrics (return, Sharpe, max DD, win rate, profit factor, trade count)
5. **Out-of-sample confirmation**: Results on data not used during development
6. **Risk assessment**: What could go wrong, when does this strategy fail?
7. **Verdict**: Pass/fail with reasoning

### 4.3 Minimum Viable Strategy Criteria (for live deployment)

Before any strategy is deployed with real capital, it must demonstrate:
- **Sharpe Ratio >= 1.0** on out-of-sample data
- **Max Drawdown >= -20%** (and ideally -15%)
- **Win Rate >= 45%** (or compensate with high profit factor > 2.0)
- **Profit Factor >= 1.5** on out-of-sample data
- **Min 30 trades** in the test period (statistical significance)
- **Profitable across at least 2 market regimes** (not just one condition)
- **Positive after transaction costs** (0.1% per trade)
- **Successful paper trading** for at least 2 weeks with expected performance

---

## 5. Initial Research Hypotheses (Priority Order)

Based on the current platform capabilities, our constraints (spot-only, long-only, no leverage), and the crypto market structure, here are the hypotheses I propose we investigate first:

### H1: Volatility Breakout with Confirmation (Priority: HIGH)
**Hypothesis**: After a period of compressed volatility (Bollinger Band squeeze), a breakout with above-average volume predicts a continuation move of 3%+ within 24-48 hours.
- **Rationale**: Crypto assets exhibit clustering volatility. Low-vol periods precede explosive moves. Volume confirmation reduces false breakouts.
- **Pairs to test**: BTC, ETH, SOL (high liquidity)
- **Timeframes**: 4h, 1d
- **Expected edge**: Captures momentum moves while filtering noise

### H2: RSI Divergence with Trend Filter (Priority: HIGH)
**Hypothesis**: Bullish RSI divergence (price makes lower low, RSI makes higher low) during an uptrend (price above 200 SMA) predicts a reversal with >55% accuracy and >2:1 reward/risk.
- **Rationale**: Pure RSI oversold buys fail in downtrends. Adding a trend filter ensures we only buy dips in uptrends.
- **Pairs to test**: BTC, ETH, LINK
- **Timeframes**: 4h, 1d
- **Expected edge**: Better timing of entries within established trends

### H3: Multi-Timeframe Momentum Alignment (Priority: MEDIUM)
**Hypothesis**: When 1h, 4h, and 1d momentum indicators (MACD or RSI slope) are all aligned bullish, the probability of a profitable long trade exceeds 60%.
- **Rationale**: Multiple timeframe agreement reduces false signals. Strong when trend is established across scales.
- **Pairs to test**: BTC, ETH, SOL, AVAX
- **Timeframes**: Multi-timeframe (1h + 4h + 1d)
- **Note**: Requires multi-timeframe data support in the engine. May need platform enhancement.

### H4: Mean-Reversion with Dynamic Bands (Priority: MEDIUM)
**Hypothesis**: Buying when price touches the lower Keltner Channel (adaptive to volatility) and exiting at the middle band produces >50% win rate with >1.5 profit factor in ranging markets.
- **Rationale**: Static Bollinger Bands (fixed 2 std dev) don't adapt well. Keltner Channels using ATR are more responsive.
- **Pairs to test**: All available pairs
- **Timeframes**: 1h, 4h
- **Expected edge**: Better mean-reversion timing than static BB

### H5: Trend Strength Filter for Existing Strategies (Priority: MEDIUM)
**Hypothesis**: Adding an ADX > 25 filter to the existing SMA crossover strategy improves Sharpe ratio by >0.3 by filtering out whipsaw trades in ranging markets.
- **Rationale**: The existing SMA crossover suffers from whipsawing in sideways markets (as seen in the Jan 2025 results). ADX filters out low-trend environments.
- **Pairs to test**: BTC, ETH
- **Timeframes**: 1h, 4h
- **Expected edge**: Quick win — improve existing strategy performance without building from scratch

---

## 6. Team Hiring Priorities

Given the critical gaps identified, here is the recommended hiring order:

### Priority 1: Data Acquisition Specialist (`data-acquisition`)
**Why first**: Everything depends on data. We cannot do valid research with 42 days of BTC-only data. This agent should:
- Fetch historical data for top 20+ USDC pairs on Binance
- Cover all target intervals: 1h, 4h, 1d, 1w
- Go back at least 2 years where possible
- Validate data quality (detect gaps, anomalies, delisted pairs)
- Set up incremental refresh to keep data current
- **Success criteria**: At least 15 pairs with 1+ year of data across 4 intervals, quality-validated

### Priority 2: Strategy Researcher (`strategy-researcher`)
**Why second**: With data in hand, we need a dedicated researcher to systematically test the hypotheses above. This agent should:
- Test hypotheses H1 through H5 in priority order
- Follow the research quality standards defined in Section 4.2
- Document all results (positive and negative) in `data/strategy_results/`
- Identify per-pair strategy characteristics and optimal parameters
- **Success criteria**: At least 2 strategies meeting the minimum viable criteria (Section 4.3)

### Priority 3: Strategy Implementer (`strategy-implementer`)
**Why third**: Once strategies are validated, they need production-quality implementation. This agent should:
- Implement validated strategies with proper error handling and logging
- Add position sizing, stop-losses, and risk management
- Prepare strategies for paper trading and live execution
- **Success criteria**: Strategies running in paper trading mode

### Priority 4: Portfolio & Risk Manager (`portfolio-risk`)
**Why fourth**: With multiple validated strategies, portfolio construction becomes valuable. This agent should:
- Design portfolio allocation across strategies and pairs
- Set risk limits (max drawdown, max exposure, correlation limits)
- Implement position sizing based on portfolio-level risk budget
- **Success criteria**: Portfolio running in paper trading with defined risk parameters

---

## 7. Platform Enhancement Requests

To support the research flow, I recommend the following platform improvements (to coordinate with the CTO/engineering team):

| # | Enhancement | Priority | Rationale |
|---|---|---|---|
| P1 | **Transaction cost modeling** in backtests | Critical | Without fees, all results are unrealistic |
| P2 | **Walk-forward validation mode** | High | Automate train/test splits to prevent overfitting |
| P3 | **Additional indicators**: ATR, ADX, VWAP, Keltner Channels, volume profile | High | Needed for hypotheses H1, H3, H4, H5 |
| P4 | **Stop-loss / take-profit support** in strategies | High | Essential for risk management |
| P5 | **Position sizing** (percent of capital, risk-based) | Medium | Currently fixed quantity=1.0 is not viable |
| P6 | **Multi-timeframe data access** in strategies | Medium | Needed for H3 — strategy needs 1h + 4h + 1d data |
| P7 | **Batch backtesting** (test one strategy across many pairs/periods) | Medium | Speeds up research iteration |
| P8 | **Regime detection module** | Low | Classify market state per pair for adaptive strategies |

---

## 8. Questions and Blockers for CEO

### Strategic Questions

1. **Capital allocation**: What is the initial capital we're deploying? This affects position sizing rules and minimum viable strategy returns. (e.g., $10K vs $100K changes the approach significantly)

2. **Target return definition**: What does "aggressive growth" mean in concrete terms? Possible definitions:
   - Annual return target: 50%? 100%? 200%?
   - Benchmark: Beat BTC buy-and-hold? Beat a specific threshold?
   - Risk budget: Acceptable max drawdown: -15%? -25%? -40%?
   - I recommend we define a target like "Annualized return > 40% with max drawdown < -20% and Sharpe > 1.0"

3. **USDC pair availability**: Can you confirm which USDC pairs are available on Binance EU? This defines our trading universe. We need to know the exact pairs we can trade.

4. **Trading frequency preference**: Do you prefer fewer high-conviction trades or higher frequency with smaller edge? This affects strategy selection:
   - Low frequency (1-5 trades/week): Focus on 4h/daily strategies, wider stops, bigger targets
   - High frequency (5-20 trades/week): Focus on 1h strategies, tighter stops, smaller targets

5. **Drawdown tolerance**: What is the absolute maximum drawdown you're willing to accept? This is the single most important risk parameter.

### Operational Blockers

6. **Data priority**: I need data acquisition to be the first team activated. Without comprehensive historical data, all research is blocked. Can we prioritize hiring `data-acquisition` immediately?

7. **Access to platform source code**: I currently cannot read the platform source code (access restricted). To properly guide research, I need read access to:
   - `platform/src/cryplative/strategies/` — to review strategy implementations
   - `platform/src/cryplative/backtesting/engine.py` — to understand backtest logic and limitations
   - `platform/src/cryplative/core/models.py` — to understand data models
   - Or, at minimum, regular access to engineering specs

8. **Platform enhancement timeline**: When can we expect Phase 3 (paper trading) and the platform enhancements listed in Section 7? This affects our research timeline — we should plan to have strategies ready when paper trading becomes available.

9. **Research budget**: Are there any constraints on compute costs, data API calls, or external data sources we should consider?

---

## 9. Proposed 30-Day Research Roadmap

| Week | Focus | Deliverables |
|---|---|---|
| **Week 1** | Data acquisition | Top 15 USDC pairs, 4 intervals, 2+ years history, quality-validated |
| **Week 2** | Exploratory analysis | Per-pair characterization, regime identification, indicator behavior profiles |
| **Week 3** | Hypothesis testing (H1, H2, H5) | Backtest results for top 3 hypotheses across pairs and timeframes |
| **Week 4** | Validation & refinement | Out-of-sample validation, parameter sensitivity analysis, initial strategy recommendations |

**End-of-month goal**: Have 1-2 strategies that meet the minimum viable criteria for at least 2 trading pairs, ready for paper trading when Phase 3 launches.

---

## 10. Conclusion

The platform provides a solid foundation for research, but the research function itself is at ground zero. The single most critical bottleneck is **data** — we need comprehensive, multi-pair, multi-timeframe historical data before any serious research can begin.

I recommend the following immediate actions:
1. **Activate `data-acquisition` agent** as the first hire — data is the prerequisite for everything
2. **Define target metrics with CEO** — "aggressive growth" needs concrete numbers
3. **Request platform enhancements** — at minimum, transaction cost modeling (P1) and additional indicators (P3)
4. **Begin exploratory analysis** on BTC data while waiting for broader data — use this time to refine methodology and build research templates

I am ready to begin directing research as soon as we have data and team members in place.
