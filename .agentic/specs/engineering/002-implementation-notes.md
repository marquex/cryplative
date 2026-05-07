# SPEC-002 Implementation Notes

**Date**: 2026-05-07
**Author**: platform-developer
**Status**: Pre-implementation validation complete

---

## Validation Summary

Validated SPEC-002 against the Phase 2 codebase. The spec is well-aligned and ready for implementation with two minor clarifications noted below.

---

## Findings

### 1. MarketFetcher.list_pairs() — ccxt Market Dict Access

**Spec line 89** states:
> Each market in the dict has: symbol, base, quote, active, precision.price, limits.amount.min

**Clarification**: ccxt uses bracket/dict access, not dot notation:
- `market['precision']['price']` (int) — not `market.precision.price`
- `market['limits']['amount']['min']` (float) — not `market.limits.amount.min`

**Impact**: Low — implementation will use correct bracket access.

### 2. PortfolioTracker Fee Calculation — Variable Names

**Spec lines 213-227** uses `trade_value` for fee calculations:
```python
trade_value = signal.quantity * price
fee = trade_value * self.fee_rate
```

**Current code uses different names**:
- `open_position()`: `cost = price * signal.quantity`
- `close_position()`: `proceeds = price * trade.quantity`

**Decision**: Will use existing variable names (`cost` and `proceeds`) for consistency with current codebase, but implement the exact fee logic specified.

---

## Confirmed Correct Assumptions

| Component | Spec Claim | Validation Result |
|-----------|------------|-------------------|
| MarketFetcher exchange instance | `self.exchange.load_markets()` | ✅ Correct (attribute is `self._exchange`) |
| BacktestConfig type | Plain class | ✅ Confirmed |
| BacktestConfig fields | Listed fields match | ✅ Exact match |
| PortfolioTracker.__init__ params | `initial_capital`, `context`, `max_positions` | ✅ Exact match |
| StrategyMetrics type | Pydantic BaseModel | ✅ Confirmed |
| StrategyMetrics fields | Listed fields match | ✅ Exact match |
| Indicator pattern | Pure functions, list[float] in, list[float | None] out | ✅ Confirmed |
| Division by zero protection | `max(len(closed_trades), 1)` | ✅ Matches code style |

---

## No Blocking Issues

The spec is ready for implementation as-is. Minor clarifications above are for implementer reference and do not require spec revision.
