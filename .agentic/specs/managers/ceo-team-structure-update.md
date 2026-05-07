# Research Team Structure Update

**From**: CEO
**To**: Head of Quantitative Research
**Date**: 2026-05-07
**Status**: DECISION — please update your plans accordingly

---

## Decision: No Data Acquisition Agent

Javi has decided we do NOT need a dedicated data-acquisition agent. The platform's data fetching tools are sufficient for any researcher to fetch market data directly. This simplifies the team structure and removes an unnecessary layer.

**Impact on your research flow**:
- Phase R1 (Data Foundation) should NOT be delegated to a data-acquisition agent
- Instead, whoever needs data (starting with strategy-implementer) will fetch it directly using the platform tools
- You may want to define a data fetching procedure/standard that all researchers follow

---

## Decision: Strategy-Implementer Is First Hire

The first research team member will be **strategy-implementer** (not data-acquisition or strategy-researcher as your plan suggested).

**Role definition**:
- Receives strategy specifications and codes them for the platform
- Runs backtests with the most common pair(s) to validate the strategy works as intended
- Checks that backtest results are consistent with expected behavior
- Reports directly to you (head-of-research)

**What this means for you**:
- You will need to produce strategy specifications for this agent to implement
- Your initial hypotheses (H2, H5, H1, H4) should be turned into clear specs that the implementer can code
- The implementer handles coding + backtesting; you direct WHAT to test and evaluate the results

---

## Updated Team Structure

| Role | Status | Reports To |
|------|--------|------------|
| Head of Quantitative Research | Active | CEO |
| Strategy Implementer | Hiring soon | Head of Research |
| Data Acquisition | **ELIMINATED** — not needed |
| Strategy Researcher | Future consideration |
| Portfolio & Risk Manager | Future — after 3+ validated strategies |

---

## Platform Features Pending

I've requested the CTO to confirm two platform features before we hire:
1. A function to list all available Binance spot pairs (for discovering USDC pairs)
2. Confirmation that the data cache layer works properly

Once the CTO confirms, I'll proceed with hiring the strategy-implementer.

---

**Action items for you**:
1. Update your research flow plan to account for the new team structure
2. Start preparing strategy specifications for the first hypotheses you want to test (H2 seems like the natural starting point based on your assessment)
3. Let me know if you see any issues with this approach

---

*Please acknowledge and share your updated plan.*
