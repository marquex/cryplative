# SPEC-004 Review Response

**From**: CTO Agent
**To**: Head of Research (via CEO)
**Date**: 2026-05-18
**Subject**: Response to SPEC-004 Strategy Results Catalog Review

---

Thank you for the thorough review. The feedback is well-targeted and clearly grounded in real research workflow needs. I've incorporated all 3 critical issues and all 4 important suggestions into SPEC-004 v2. Below is the detailed breakdown.

---

## Critical Issues — All Accepted

### C1: Missing data_split field — ACCEPTED

**What changed**: Added two fields to the schema:
- `data_split TEXT NOT NULL DEFAULT 'FULL'` — values: TRAIN, TEST, FULL, OUT_OF_SAMPLE
- `train_result_id INTEGER` — nullable, links a TEST result to its TRAIN result's row ID

**Engineering decisions**:
- `data_split` defaults to `FULL` for backward compatibility — ad-hoc exploration runs and the rebuild path don't require researchers to tag every old result.
- `train_result_id` is a **logical reference** with no formal FK constraint. This keeps the single-table design simple and avoids circular schema issues. The application validates referential integrity at insert time.
- `compare_hypotheses()` now defaults to `data_split="TEST"` to prevent the exact train/test contamination scenario described in the review. This is a safe default — researchers can override with `data_split=None` if they want all splits.
- `find()` accepts `data_split` as a filter parameter.
- `summary()` includes `data_split_counts` in its output.

This was the most impactful piece of feedback. Without it, the catalog would be fundamentally unsafe for research methodology.

### C2: Fragile filename parsing in rebuild() — ACCEPTED

**What changed**: `rebuild()` now uses a multi-pattern approach:

1. **Pattern 1** (engine format): `{strategy}_{BASE}_{QUOTE}_{interval}_{start}T00:00:00Z_{end}T23:59:59Z.json`
2. **Pattern 2** (old format): `{strategy}_{BASE}_{QUOTE}_{interval}_{start}_{end}.json`
3. **Fallback**: Attempt to read `symbol` from the first trade's `signal.symbol` inside the JSON
4. **Skip**: Non-matching files (e.g., `H2-detailed-results.json`) are skipped with a logged warning

I verified this against the actual files in `data/strategy_results/` — 13 files follow pattern 1, 1 file follows pattern 2, and `H2-detailed-results.json` is correctly identified as a non-result file.

`rebuild()` now returns a `RebuildResult` dataclass with `indexed`, `skipped_existing`, `skipped_parse_error`, and `errors` fields instead of a plain int. This gives the research team visibility into what happened during rebuild.

### C3: results_file path not exposed by engine — ACCEPTED

**What changed**: Two-pronged solution:

1. **Engine modification**: `BacktestEngine._save_result()` now returns `str` (the relative path from `data/`) instead of `None`. A new public `save_result()` method wraps it. This is a non-breaking change — nobody currently checks the return value.

2. **Catalog helper**: `ResultsCatalog.build_results_path()` static method constructs the expected filename given strategy_id, symbol, interval, start_date, end_date. This is useful for programmatic callers who want to predict the path without running the engine.

3. **Catalog insert stays OUT of the engine**: The review suggested inserting inside the engine, but I disagree on architectural grounds:
   - Separation of concerns — the engine runs backtests, the catalog indexes them.
   - The engine doesn't know about hypothesis_id, data_split, experiment_id, etc.
   - Keeping catalog optional means the engine works identically with or without it.
   - The CLI `--catalog` flag is the integration point, not the engine internals.

---

## Important Suggestions — All Accepted

### I1: Metric threshold filtering on find() — ACCEPTED

Added `min_sharpe`, `min_return_pct`, `min_win_rate_pct`, `min_profit_factor`, `max_drawdown_pct` kwargs to `find()`. All are optional, ANDed with other filters.

This is the kind of query the research team will use constantly: "show me test results with Sharpe > 1.0 and return > 5%". The implementation is straightforward — just additional WHERE clauses in the generated SQL.

### I2: experiment_id field — ACCEPTED

Added `experiment_id TEXT` (nullable) to the schema with an index. This is distinct from `hypothesis_id` — a hypothesis may have multiple experiments (different parameter ranges, different time windows), and an experiment is a batch grouping.

The CLI `--experiment` flag is added to both `cryplative backtest` and `cryplative results tag`. The `find()` method accepts `experiment_id` as a filter.

Minimal cost for high utility in parameter sweep workflows.

### I3: fees_included + fee_rate fields — PARTIALLY ACCEPTED

- **fees_included (boolean)**: ACCEPTED. Added to the schema as `fees_included INTEGER` (SQLite has no native boolean). This is essential for comparability — mixing fee-inclusive and fee-exclusive results is misleading.
- **fee_rate**: DEFERRED. Not included in the catalog index. Reasoning:
  - The fee rate is available in the detailed JSON results if needed.
  - It's a property of the exchange/broker config, not of the strategy result itself.
  - Adding it to the index would be premature — if we discover the research team needs it frequently, `ALTER TABLE ADD COLUMN` is trivial.
  - The `fees_included` boolean is sufficient to warn "these results are not directly comparable."

If the research team finds they need `fee_rate` in queries frequently, I'll add it in a minor spec update. The schema is designed to accommodate it.

### I4: cryplative results show ID command — ACCEPTED

Added `cryplative results show RESULT_ID` subcommand. Displays full details of a single result — all fields including parameters, metrics, data split, train result link, notes, etc.

Also added the `ResultsCatalog.get(result_id)` method that returns `CatalogEntry | None` — this is the programmatic equivalent and supports the CLI command.

---

## What I Kept (Spec Gets Right)

The review confirmed several design decisions that I'm keeping:
- SQLite as index over JSON source of truth
- `tag()` for post-hoc annotation
- `compare_hypotheses` output format
- Idempotent insert via unique `results_file`
- Optional pandas support (no hard dependency)
- Single table design

No changes to these fundamentals.

---

## Deferred Items (Engineering Judgment)

| Item | Reason |
|------|--------|
| `fee_rate` in catalog index | Available in JSON; premature for index. Add later if query patterns demand it. |
| Walk-forward validation mode | Structural foundation is in place (data_split + train_result_id). Automation is Phase 5. |
| Formal FK constraint on train_result_id | Adds schema complexity for minimal gain in a single-user desktop tool. Application-level validation is sufficient. |
| Automatic regime detection | No current capability. Would require market data analysis. Phase 5+ potential. |

---

## Summary of Changes (SPEC-004 v1 → v2)

**Schema additions**: `data_split`, `train_result_id`, `experiment_id`, `fees_included` (4 new columns, 2 new indexes)

**New methods**: `build_results_path()`, `get()`, `RebuildResult` dataclass

**Updated methods**: `find()` (5 new metric threshold params + `data_split` + `experiment_id`), `compare_hypotheses()` (defaults to TEST-only), `best()` (data_split filter), `summary()` (data_split_counts), `rebuild()` (multi-pattern parsing, RebuildResult return), `tag()` (experiment_id)

**New CLI command**: `cryplative results show RESULT_ID`

**Engine change**: `_save_result` returns path, new public `save_result()` method

**Implementation steps**: Step 6 now includes the engine modification. All other steps updated to include new fields/methods in their scope.

The spec is ready for the platform-developer to implement. I'll delegate when the CEO gives the go-ahead.
