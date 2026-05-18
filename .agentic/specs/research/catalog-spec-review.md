# SPEC-004 Review: Strategy Results Catalog

**Reviewer**: Head of Quantitative Research
**Date**: 2026-05-18
**Spec reviewed**: `SPEC-004: Strategy Results Catalog` (CTO Agent, 2026-05-18)

---

## Verdict: APPROVE_WITH_SUGGESTIONS

The spec is well-designed and addresses a real, urgent pain point. The architecture (SQLite index over JSON source-of-truth) is sound, the API surface is practical, and the CLI integration is clean. The core design can be built as-is. However, there are several gaps that will cause friction in the research workflow if not addressed — one critical (train/test tracking), two important (metric filtering, experiment grouping), and several minor improvements.

**Recommendation**: Build the core as specified, but incorporate the critical and important suggestions below before or during implementation. The minor suggestions can be deferred to a follow-up iteration.

---

## 1. Research Workflow Fit

### What works well

The four query methods (`find`, `best`, `compare_hypotheses`, `summary`) cover the most common research queries. The `tag()` method for post-hoc annotation is especially valuable — in practice, I run a batch of backtests first, then analyze and tag verdicts afterward. This matches the spec's design.

The `compare_hypotheses` output format (Section 5.3) is excellent — showing best metric, averages, and pass rates side-by-side is exactly what I need when deciding which hypothesis to promote.

### Queries I need that are NOT covered

**1. Metric threshold filtering** (Important)

`find()` filters by identity fields (strategy, symbol, interval, etc.) but NOT by metric values. In practice, I constantly ask:

- "Show me all results with Sharpe > 1.0"
- "Which results have win_rate >= 50% AND profit_factor >= 1.5?"
- "What passed the minimum viability test (return > 0, drawdown > -20%)?"

Today, I'd have to `find()` then filter in Python. This should be built into the query.

**Suggestion**: Add optional metric threshold kwargs to `find()`:
```python
def find(
    self,
    # ... existing identity filters ...
    min_sharpe: float | None = None,
    min_return_pct: float | None = None,
    max_drawdown_pct: float | None = None,
    min_win_rate_pct: float | None = None,
    min_profit_factor: float | None = None,
    min_total_trades: int | None = None,
) -> list[CatalogEntry]:
```

**2. Date range filtering** (Minor)

No way to filter by `created_at` or `start_date`/`end_date` ranges. "Show me results from the last week" or "only results using 2024 data" are queries I'd run.

**Suggestion**: Add `created_after`, `created_before`, `data_start`, `data_end` optional kwargs to `find()`.

**3. Parameter-based queries** (Minor, deferrable)

"Show me all results where sma_period=200". The `parameters_json` blob isn't queryable via the API. For now this is acceptable — parameter sweep analysis can be done via `to_dataframe()`. But as the catalog grows, this will become important.

**Suggestion**: Defer to a follow-up. The `parameters_json` column supports future JSON extraction in SQLite3.

**4. Per-pair best result** (Minor)

"What's the best strategy for each pair?" requires GROUP BY symbol. Not covered by the current API. Can be done via `to_dataframe()` for now.

---

## 2. Schema Completeness

### Critical missing field: `data_split`

This is the biggest gap. Our research methodology always splits data into train and test periods. Every strategy spec defines train/test date ranges. The H2 results currently in `data/strategy_results/` follow this pattern:

```
h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json  (TRAIN)
h2_rsi_divergence_trend_BTC_USDT_4h_2025-09-01T00:00:00Z_2026-04-30T23:59:59Z.json  (TEST)
```

These are two separate JSON files with no linkage between them. The catalog would store them as two unrelated entries. This means:

- I can't query "show me train vs test performance for H2 on BTC 4h"
- I can't compute train-to-test degradation automatically
- `compare_hypotheses` might mix train and test results in its averages

**Suggestion**: Add two fields:

```sql
data_split       TEXT,           -- "TRAIN", "TEST", "FULL", "OOS" (nullable — legacy results won't have it)
train_result_id  INTEGER,        -- FK to results.id — links test result to its train result (nullable)
FOREIGN KEY (train_result_id) REFERENCES results(id)
```

This enables:
- Filter by data_split in `find()`
- Compute degradation metrics in `compare_hypotheses()`
- Ensure train/test pairs are always compared correctly

### Important missing field: Fee tracking

The spec references SPEC-002 fee metrics, but the catalog schema doesn't capture whether fees were included in the metrics. Currently, fee adjustment is done manually (post-processing), so some results include fees and others don't. Without tracking this, comparing fee-adjusted vs non-adjusted results is misleading.

**Suggestion**: Add:
```sql
fees_included    INTEGER DEFAULT 0,  -- 0 = no fees, 1 = fees included in metrics
fee_rate         REAL,               -- e.g., 0.001 for 0.1% (nullable)
```

### Minor missing fields

| Field | Why it matters | Priority |
|-------|---------------|----------|
| `initial_capital` | BacktestConfig has this. Affects position sizing and trade behavior. | Low |
| `lookback_window` | From BacktestConfig. Affects indicator warmup. | Low |
| `engine_version` | Platform version that produced the result. Enables reproducibility tracking. | Low (defer) |

### One naming concern

The spec uses `total_return_pct` (2.56%) while `StrategyMetrics` uses `total_return` (2.56). The actual JSON data shows values like `12.58` for SMA crossover and `2.56` for H2 — these appear to be percentages already. The `_pct` suffix in the spec is fine for clarity, but `insert_from_strategy_result()` needs to document the unit conversion (or lack thereof) explicitly.

---

## 3. Blind Spots

### 3.1 Fragile filename parsing in `rebuild()` (Important)

The spec says `rebuild()` parses filenames to extract symbol and interval. The parsing logic is: `symbol = f"{parts[-5]}/{parts[-4]}", interval = parts[-3]`.

This will break on existing files. The actual filenames in `data/strategy_results/` show TWO different conventions:

```
h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json  (engine format)
sma_crossover_BTC_USDT_1h_2025-01-01_2025-01-31.json                                  (old format — different date)
H2-detailed-results.json                                                               (custom format — unparsable)
```

The old SMA crossover file uses `_` as delimiter in dates (`2025-01-01`) without the `T` and timezone. The parsing logic for "take parts[-5] through parts[-3]" assumes all dates have `T00:00:00Z` format.

**Suggestion**: The `rebuild()` method should:
1. Try filename parsing first (primary)
2. Fall back to reading the JSON and extracting symbol from the first trade's signal (secondary — spec already mentions this)
3. Skip files that can't be parsed and log a warning with the filename
4. The H2-detailed-results.json and H2-report.md files are not engine results — they should be skipped silently (non-JSON or non-matching pattern)

### 3.2 No experiment/batch grouping

When the strategy-implementer runs parameter sweeps (e.g., 4 symbols x 2 intervals x 3 parameter sets = 24 results), there's no way to group these as "one experiment." If I run three different parameter configurations for H5, I want to compare them as a batch.

**Suggestion**: Add optional `experiment_id` field:
```sql
experiment_id    TEXT,           -- e.g., "H5-param-sweep-2026-05-19" (nullable)
```
And add it as a filter in `find()` and `compare_hypotheses()`.

### 3.3 `results_file` path mismatch in programmatic use

The spec's integration pattern (Section 6.1) shows `results_file="strategy_results/h2_..."` being passed manually to `insert_from_strategy_result()`. But the engine's `_save_result()` method (engine.py:307-321) doesn't return the saved filename. The caller must reconstruct the exact filename pattern the engine uses internally.

This is fragile — if the engine's naming convention changes, catalog inserts break silently (wrong filename stored).

**Suggestion**: Either:
- (a) Have the engine return the saved path from `run()`, or
- (b) Provide a `ResultsCatalog.results_file_for(config, result)` helper that generates the expected path, or
- (c) Have the `--catalog` integration happen INSIDE the engine (after `_save_result`), where the filename is already known

Option (c) is cleanest for CLI use. Option (a) is cleanest for programmatic use.

### 3.4 `max_drawdown_pct` sorting convention

The spec says `best(metric="max_drawdown_pct")` sorts ascending "for metrics where lower is better." Since drawdowns are stored as negative values (e.g., -0.42, -61.1), ascending means -0.42 comes first (smallest absolute drawdown). This is correct behavior but could confuse users.

**Suggestion**: Add a clear comment in the docstring: "Ascending means least negative first = smallest drawdown."

---

## 4. CLI Usability

### Strong points

The command structure is intuitive: `cryplative results {list,best,compare,summary,tag,rebuild,delete}`. The Rich table formatting with color-coding (green positive, red negative, bold for Sharpe > 1.0) is a nice touch that helps quick visual scanning.

The `tag` command is particularly well-designed — it matches the research workflow perfectly (run backtests first, analyze, then tag with verdict/notes).

### Missing command: `cryplative results show ID`

`list` shows a summary table. But when evaluating a specific result, I need to see ALL fields — parameters, notes, exact dates, full metrics. There's no way to drill into a single result from the CLI.

**Suggestion**: Add:
```
cryplative results show RESULT_ID
```
Display full details of a single result, including parsed parameters and notes.

### Minor: `compare` positional args

`cryplative results compare H2 H5` requires the user to know that hypothesis IDs are positional args. This is fine, but consider also supporting `--hypotheses H2,H5` (comma-separated) as an alternative, since hypothesis IDs might not be intuitive as positional args.

---

## 5. Integration with Strategy-Implementer Workflow

### The `--catalog` flag is well-designed

Adding `--catalog --hypothesis H2` to the existing `cryplative backtest` command is zero-friction. The implementer already runs `cryplative backtest` — adding one flag is easy.

### Programmatic use is slightly awkward

The implementer currently uses the programmatic Python API for batch backtests (running 8+ symbol/interval combinations in a loop). The `insert_from_strategy_result()` method supports this, but the `results_file` path issue (Section 3.3 above) adds friction. The implementer would need to reconstruct the filename for each result.

**Suggestion**: Ensure the `--catalog` integration on the CLI side handles filename generation internally (not user-specified), and for the Python API, provide the helper method suggested in 3.3.

### Missing: Auto-tagging with data_split

When the implementer runs backtests with the train period then the test period, the `--catalog` flag should also accept `--data-split TRAIN` or `--data-split TEST`. Without this, every result needs manual tagging afterward.

---

## 6. Summary of Suggestions

### Critical (address before/during build)

| # | Suggestion | Impact |
|---|-----------|--------|
| C1 | Add `data_split` field ("TRAIN"/"TEST"/"FULL") + optional `train_result_id` | Without this, our core research methodology (train/test split tracking) is not supported by the catalog |
| C2 | Fix `rebuild()` filename parsing to handle legacy formats + skip non-result files | Will fail on existing data otherwise |
| C3 | Resolve `results_file` path generation — engine should expose saved path or catalog should compute it | Without this, programmatic inserts require fragile path reconstruction |

### Important (recommended for initial build)

| # | Suggestion | Impact |
|---|-----------|--------|
| I1 | Add metric threshold filtering to `find()` (min_sharpe, min_return_pct, etc.) | High-frequency query pattern not currently supported |
| I2 | Add `experiment_id` field for grouping sweep results | Enables proper batch comparison |
| I3 | Add `fees_included` + `fee_rate` fields | Critical for comparing fee-adjusted vs raw results |
| I4 | Add `cryplative results show ID` command | No way to view full result details from CLI |

### Minor (defer to follow-up)

| # | Suggestion | Impact |
|---|-----------|--------|
| M1 | Add date range filters to `find()` | Nice-to-have for time-scoped queries |
| M2 | Add `initial_capital` and `lookback_window` fields | Low — context fields |
| M3 | Add `data_split` and `experiment_id` to CLI `tag` command | Needed if fields are added |
| M4 | Clarify `max_drawdown_pct` sorting in docstring | Documentation clarity |
| M5 | Add `--data-split` flag to `cryplative backtest --catalog` | Streamlines train/test workflow |

---

## 7. What the Spec Gets Right

To balance the feedback above, these are the things the spec nails:

1. **SQLite as index, JSON as truth** — correct architecture. No data duplication, easy rebuild, portable.
2. **Single table design** — appropriate for the scale and complexity. Over-normalizing would add friction.
3. **`tag()` for post-hoc annotation** — matches the actual research workflow perfectly.
4. **`compare_hypotheses` output format** — the side-by-side summary with averages and pass rates is exactly what I need.
5. **Optional `to_dataframe()`** — respects the platform's no-pandas constraint while enabling power users.
6. **Idempotent insert via unique `results_file`** — prevents the most common data integrity issue.
7. **85% test coverage requirement** — appropriate for an indexing layer that must be reliable.
8. **Test database isolation** — never touching real `data/catalog.db` in tests is correct practice.
9. **Clear implementation order** — the 8-step build plan is logical and incremental.

---

*This review was prepared by the Head of Quantitative Research based on the current state of the research pipeline (14 strategy result files, H2 completed/rejected, H5 next priority) and the platform's existing models (StrategyResult, BacktestConfig, StrategyMetrics).*
