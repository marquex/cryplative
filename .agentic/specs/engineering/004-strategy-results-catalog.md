# SPEC-004: Strategy Results Catalog

**Author**: CTO Agent
**Date**: 2026-05-18
**Status**: Draft — Validated (post platform-developer review, issues addressed)
**Assignee**: platform-developer
**Depends on**: SPEC-001 (COMPLETE), SPEC-002 (partially complete — Steps 1,3 done)

---

## 0. Purpose

The research team is iterating through trading strategies (implement, backtest, store results, compare). Right now, results are stored as individual JSON files in `data/strategy_results/` with no way to query or compare across strategies. This spec adds a lightweight SQLite catalog layer that indexes strategy result metadata for easy querying, comparison, and analysis — without replacing the existing JSON files as the source of truth for detailed trade-level data.

**Key principle**: The JSON files remain the source of truth. The SQLite database is an index — fast to query, lightweight, and always reconstructible from the JSON files.

---

## 1. Context — Current State

### 1.1 What Exists

| Component | Location | Status |
|-----------|----------|--------|
| StrategyResult JSON | `data/strategy_results/{strategy_id}_{symbol}_{interval}_{timestamp}.json` | Auto-saved by backtest engine |
| BacktestMetrics | `platform/src/cryplative/core/models.py` | Contains: total_return, sharpe_ratio, max_drawdown, win_rate, total_trades, profit_factor (+ fee metrics from SPEC-002) |
| CLI compare | `cryplative compare` | Side-by-side Rich table for 2+ result files |
| Python API | `BacktestEngine.run(config) -> StrategyResult` | Typed Pydantic result objects |

### 1.2 The Gap

From SPEC-002 research team assessment:
- "No results database — flat JSON files, no query across all runs"
- "No tagging/metadata convention for hypothesis, regime, experiment batch"
- "No automatic best-result tracking per strategy/pair combo"

Research team needs to answer questions like:
- "Show me all strategies tested on BTC"
- "Compare H2 vs H5 results"
- "Which strategy has the best Sharpe ratio?"
- "What's the average win rate across all RSI strategies?"

This spec closes that gap.

---

## 2. Architecture

### 2.1 Module Location

```
platform/src/cryplative/
└── catalog/                    # NEW module
    ├── __init__.py             # Public API: ResultsCatalog, CatalogEntry
    ├── db.py                   # SQLite connection, schema init, migrations
    └── query.py                # ResultsCatalog class — query/insert/delete
```

The catalog is a **platform module** — importable by anyone who can `import cryplative`.

### 2.2 Data Flow

```
┌─────────────┐     insert()      ┌──────────────────────┐
│ Backtest    │ ──────────────────►│                      │
│ Engine      │                    │   ResultsCatalog     │
│ (or CLI)    │                    │   (SQLite index)     │
└──────┬──────┘                    └──────────┬───────────┘
       │                                      │
       │ saves JSON                           │ indexes metadata
       ▼                                      ▼
┌─────────────────────────┐      ┌──────────────────────┐
│ data/strategy_results/  │      │ data/catalog.db       │
│ {strategy}_{sym}_{tf}_  │◄─────│ (strategy metadata +  │
│ {timestamp}.json        │ ref  │  metrics + file ref)  │
│ SOURCE OF TRUTH         │      └──────────────────────┘
└─────────────────────────┘
```

### 2.3 Database Location

```
data/catalog.db
```

The database file lives in `data/` alongside the JSON files it indexes. It is gitignored (like all data/ contents).

---

## 3. Database Schema

### 3.1 `results` Table

This is the **only table**. Keep it simple.

```sql
CREATE TABLE IF NOT EXISTS results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    strategy_id     TEXT    NOT NULL,       -- e.g., "h2_rsi_divergence_trend"
    hypothesis_id   TEXT,                   -- e.g., "H2", "H5" (nullable — not all runs have one)
    run_type        TEXT    NOT NULL,       -- "BACKTEST", "PAPER", "REAL"

    -- Market context
    symbol          TEXT    NOT NULL,       -- e.g., "BTC/USDT"
    interval        TEXT    NOT NULL,       -- e.g., "4h", "1d"
    start_date      TEXT    NOT NULL,       -- ISO 8601
    end_date        TEXT    NOT NULL,       -- ISO 8601

    -- Key metrics (extracted from StrategyResult.metrics)
    total_return_pct    REAL,              -- e.g., 2.56
    sharpe_ratio        REAL,              -- e.g., 2.57
    max_drawdown_pct    REAL,              -- e.g., -0.42 (stored as negative)
    win_rate_pct        REAL,              -- e.g., 83.33
    total_trades        INTEGER,           -- e.g., 6
    profit_factor       REAL,              -- e.g., 17.79

    -- Verdict
    verdict         TEXT,                  -- "PASS", "FAIL", "MARGINAL" (nullable — set by researcher)

    -- Reference to detailed data
    results_file    TEXT    NOT NULL,      -- relative path from data/ e.g., "strategy_results/h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json"

    -- Parameters snapshot (JSON blob)
    parameters_json TEXT    NOT NULL,      -- JSON string of strategy parameters

    -- Metadata
    notes           TEXT,                  -- Free-form researcher notes (nullable)
    created_at      TEXT    NOT NULL       -- ISO 8601 timestamp when inserted
);
```

### 3.2 Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_strategy_id    ON results(strategy_id);
CREATE INDEX IF NOT EXISTS idx_hypothesis_id  ON results(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_symbol         ON results(symbol);
CREATE INDEX IF NOT EXISTS idx_interval       ON results(interval);
CREATE INDEX IF NOT EXISTS idx_verdict        ON results(verdict);
CREATE UNIQUE INDEX IF NOT EXISTS idx_results_file ON results(results_file);
```

**Key**: `idx_results_file` is a **UNIQUE** index. This prevents the same results file from being indexed twice — critical for idempotent `rebuild()` and safe `insert()` operations.

### 3.3 Design Decisions

- **Single table, not normalized**: We're indexing backtest results, not building a relational analytics warehouse. One table with indexes is simpler to query and maintain.
- **Nullable hypothesis_id**: Not every backtest run belongs to a hypothesis. Ad-hoc exploration runs won't have one.
- **Nullable verdict**: Set by the researcher after analysis, not automatically. An un-verdicted result is just "logged".
- **parameters_json as TEXT blob**: Parameters vary per strategy. No point in a separate table — just store as JSON and parse when needed.
- **results_file as relative path**: The file path relative to `data/`. Makes the catalog portable if the data directory moves.
- **max_drawdown stored as negative**: Matches the convention in the existing JSON results.

---

## 4. Python Query Interface

### 4.1 `ResultsCatalog` Class

The main interface. Lives in `platform/src/cryplative/catalog/query.py`.

```python
class ResultsCatalog:
    """Lightweight SQLite catalog for strategy backtest results."""

    def __init__(self, db_path: str = "data/catalog.db"):
        """
        Open or create the catalog database.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to "data/catalog.db".
                     Creates the file and schema if it doesn't exist.
        """
        ...

    # ── Insert ──────────────────────────────────────────

    def insert(
        self,
        strategy_id: str,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        run_type: str,
        metrics: dict,           # {total_return_pct, sharpe_ratio, ...}
        results_file: str,       # relative path from data/
        parameters: dict,        # strategy parameters
        hypothesis_id: str | None = None,
        verdict: str | None = None,
        notes: str | None = None,
    ) -> int:
        """
        Insert a result record into the catalog.

        Returns the auto-generated row ID.

        Args:
            strategy_id: Strategy identifier (e.g., "h2_rsi_divergence_trend")
            symbol: Trading pair (e.g., "BTC/USDT")
            interval: Candle interval (e.g., "4h")
            start_date: Backtest start date (ISO 8601)
            end_date: Backtest end date (ISO 8601)
            run_type: "BACKTEST", "PAPER", or "REAL"
            metrics: Dict with keys: total_return_pct, sharpe_ratio,
                     max_drawdown_pct, win_rate_pct, total_trades, profit_factor
            results_file: Relative path to the JSON results file from data/
            parameters: Strategy parameters dict (stored as JSON)
            hypothesis_id: Optional hypothesis tag (e.g., "H2")
            verdict: Optional verdict ("PASS", "FAIL", "MARGINAL")
            notes: Optional free-form notes

        Raises:
            ValueError: If required fields are missing or metrics dict lacks expected keys
            sqlite3.IntegrityError: If results_file already exists (duplicate prevention)
        """
        ...

    def insert_from_strategy_result(
        self,
        result,                  # StrategyResult object
        symbol: str,             # from BacktestConfig (not on StrategyResult)
        interval: str,           # from BacktestConfig (not on StrategyResult)
        results_file: str,       # relative path from data/
        hypothesis_id: str | None = None,
        verdict: str | None = None,
        notes: str | None = None,
    ) -> int:
        """
        Convenience method: insert directly from a StrategyResult object.

        IMPORTANT: StrategyResult does NOT contain symbol or interval at the
        top level. These come from BacktestConfig. The caller MUST pass them
        explicitly.

        Extracts strategy_id, dates, metrics, and parameters from the
        StrategyResult, then delegates to insert().

        This is the primary integration point — call it after BacktestEngine.run().

        Typical usage:
            config = BacktestConfig(strategy_id="sma", symbol="BTC/USDT", interval="4h", ...)
            result = engine.run(config)
            catalog.insert_from_strategy_result(
                result,
                symbol=config.symbol,
                interval=config.interval,
                results_file="strategy_results/sma_BTC_USDT_4h_2024.json",
                hypothesis_id="H2",
            )
        """
        ...

    # ── Query ───────────────────────────────────────────

    def find(
        self,
        strategy_id: str | None = None,
        hypothesis_id: str | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        verdict: str | None = None,
        run_type: str | None = None,
    ) -> list[CatalogEntry]:
        """
        Find results matching all given filters (AND logic).
        None means "don't filter by this field".

        Returns list of CatalogEntry objects, sorted by created_at desc
        (newest first).

        Examples:
            catalog.find(symbol="BTC/USDT")               # All BTC results
            catalog.find(hypothesis_id="H2")              # All H2 results
            catalog.find(strategy_id="sma_crossover",     # SMA on 4h
                        interval="4h")
            catalog.find(verdict="PASS")                  # All passing results
        """
        ...

    def compare_hypotheses(
        self,
        hypothesis_ids: list[str],
        metric: str = "sharpe_ratio",
    ) -> dict[str, list[CatalogEntry]]:
        """
        Compare results across multiple hypotheses.

        Returns dict mapping hypothesis_id -> list of CatalogEntry,
        sorted by the given metric (descending for higher-is-better metrics,
        ascending for lower-is-better like max_drawdown_pct).

        Example:
            catalog.compare_hypotheses(["H2", "H5"])
            # Returns {"H2": [...entries sorted by sharpe desc...],
            #          "H5": [...entries sorted by sharpe desc...]}
        """
        ...

    def best(
        self,
        metric: str = "sharpe_ratio",
        n: int = 10,
        strategy_id: str | None = None,
        symbol: str | None = None,
        hypothesis_id: str | None = None,
    ) -> list[CatalogEntry]:
        """
        Get the top N results by a given metric.

        For metrics where higher is better (total_return_pct, sharpe_ratio,
        win_rate_pct, profit_factor, total_trades), sorts descending.
        For metrics where lower is better (max_drawdown_pct), sorts ascending.

        Args:
            metric: One of: total_return_pct, sharpe_ratio, max_drawdown_pct,
                    win_rate_pct, total_trades, profit_factor
            n: Number of results to return (default 10)
            strategy_id: Optional filter
            symbol: Optional filter
            hypothesis_id: Optional filter
        """
        ...

    def summary(self) -> CatalogSummary:
        """
        Get a high-level overview of the catalog.

        Returns CatalogSummary with:
            - total_results: int
            - unique_strategies: list[str]
            - unique_hypotheses: list[str]
            - unique_symbols: list[str]
            - verdict_counts: dict[str, int]  (e.g., {"PASS": 5, "FAIL": 3, None: 10})
            - best_by_metric: dict[str, CatalogEntry]  (best entry for each metric)
        """
        ...

    # ── Delete ──────────────────────────────────────────

    def delete(self, result_id: int) -> bool:
        """Delete a result by its row ID. Returns True if deleted."""
        ...

    def delete_by_file(self, results_file: str) -> bool:
        """Delete a result by its results_file path. Returns True if deleted."""
        ...

    # ── Tag ─────────────────────────────────────────────

    def tag(
        self,
        result_id: int,
        hypothesis_id: str | None = None,
        verdict: str | None = None,
        notes: str | None = None,
    ) -> bool:
        """
        Update metadata fields on an existing result.

        Only updates fields that are passed (not None). Returns True if
        the result was found and updated, False if result_id doesn't exist.

        This is how researchers add hypothesis tags, verdicts, and notes
        to results after analysis.

        Example:
            catalog.tag(12, hypothesis_id="H2", verdict="PASS",
                        notes="Strong on BTC, consistent train/test")
        """
        ...

    # ── Rebuild ─────────────────────────────────────────

    def rebuild(self, results_dir: str = "data/strategy_results") -> int:
        """
        Rebuild the catalog by scanning the results directory.

        Reads all JSON files in results_dir, extracts metadata and metrics,
        and inserts them into the catalog. Skips files already indexed
        (by results_file uniqueness).

        Returns the number of newly inserted records.

        NOTE ON SYMBOL/INTERVAL EXTRACTION:
        The StrategyResult JSON files do NOT contain symbol or interval at the
        top level. These must be extracted from either:
        (a) The filename, which follows the pattern:
            {strategy_id}_{BASE}_{QUOTE}_{interval}_{start}_{end}.json
            e.g., "h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json"
            Parse: symbol = f"{parts[-5]}/{parts[-4]}", interval = parts[-3]
        (b) The first trade's signal.symbol field (if trades exist).
        Use the filename approach as primary — it's always available and consistent.

        Useful for:
            - Initial setup (catalog didn't exist before)
            - After manual JSON file changes
            - Recovery if catalog.db gets corrupted

        Note: This does NOT clear the existing catalog first. It only adds
        entries for files not yet indexed. Use clear() first if you want
        a full rebuild.
        """
        ...

    def clear(self) -> int:
        """Delete all records from the catalog. Returns count of deleted rows."""
        ...

    # ── Export ──────────────────────────────────────────

    def to_dataframe(
        self,
        strategy_id: str | None = None,
        hypothesis_id: str | None = None,
        symbol: str | None = None,
    ) -> "pandas.DataFrame":
        """
        Export filtered results as a pandas DataFrame.

        Optional dependency — only available if pandas is installed.
        Raises ImportError if pandas is not available, with a helpful message.

        Useful for the research team's ad-hoc analysis in Jupyter notebooks.
        Columns match the table schema (parameters_json parsed into a dict column).
        """
        ...
```

### 4.2 Data Classes

```python
@dataclass
class CatalogEntry:
    """A single result record from the catalog."""
    id: int
    strategy_id: str
    hypothesis_id: str | None
    run_type: str
    symbol: str
    interval: str
    start_date: str
    end_date: str
    total_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float | None
    win_rate_pct: float | None
    total_trades: int | None
    profit_factor: float | None
    verdict: str | None
    results_file: str
    parameters: dict            # parsed from parameters_json
    notes: str | None
    created_at: str


@dataclass
class CatalogSummary:
    """High-level overview of the catalog contents."""
    total_results: int
    unique_strategies: list[str]
    unique_hypotheses: list[str]
    unique_symbols: list[str]
    verdict_counts: dict[str | None, int]
    best_by_metric: dict[str, CatalogEntry]
```

### 4.3 Design Principles

1. **No raw SQL required** — all common queries are methods on `ResultsCatalog`. The research team calls `catalog.find(symbol="BTC/USDT")`, not `cursor.execute("SELECT * FROM results WHERE symbol = ?", ...)`.
2. **Filter by any combination** — `find()` takes optional kwargs, all ANDed together. None = no filter.
3. **Typed returns** — `CatalogEntry` dataclasses, not raw tuples. IDE-friendly, self-documenting.
4. **Graceful pandas optional** — `to_dataframe()` is available when pandas is present, doesn't fail when it's not. This respects that the platform doesn't require pandas.
5. **Idempotent insert** — duplicate `results_file` raises `IntegrityError`. The catalog won't index the same result twice.

---

## 5. CLI Integration

### 5.1 `cryplative results` Command Group

Add a `results` subcommand group to the existing CLI. This gives the research team command-line access without writing Python.

```python
@app.command()
def results(
    ctx: typer.Context,
) -> None:
    """Query and manage the strategy results catalog."""
    ...
```

### 5.2 Subcommands

```
cryplative results list [--strategy STRATEGY] [--hypothesis HYPOTHESIS]
                        [--symbol SYMBOL] [--interval INTERVAL]
                        [--verdict VERDICT] [--limit N]

cryplative results best  [--metric METRIC] [--top N] [--strategy STRATEGY]
                         [--symbol SYMBOL] [--hypothesis HYPOTHESIS]

cryplative results compare  HYPOTHESIS_IDS... [--metric METRIC]

cryplative results summary

cryplative results rebuild [--results-dir DIR]

cryplative results tag    RESULT_ID --hypothesis HYPOTHESIS
                          [--verdict VERDICT] [--notes NOTES]

cryplative results delete RESULT_ID
```

### 5.3 Subcommand Details

#### `cryplative results list`
Display a Rich table of results matching the filters.

```
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓
┃ ID ┃ Strategy             ┃ Hyp  ┃ Symbol    ┃ TF    ┃ Return ┃ Sharpe  ┃ Verdict ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩
│ 12 │ h2_rsi_divergence    │ H2   │ BTC/USDT  │ 4h    │ 2.56%  │ 2.57    │ PASS    │
│ 11 │ h5_macd_breakout     │ H5   │ BTC/USDT  │ 1d    │ 8.12%  │ 1.89    │ PASS    │
│ 10 │ sma_crossover        │ —    │ ETH/USDT  │ 1h    │ -1.2%  │ 0.43    │ FAIL    │
└────┴──────────────────────┴──────┴───────────┴───────┴────────┴─────────┴─────────┘

Showing 3 of 15 results. Use --limit to show more.
```

Default limit: 20. Color-code: green for positive return, red for negative. Sharpe > 1.0 in bold.

#### `cryplative results best`
Show the top N results for a given metric.

```
Top 5 by sharpe_ratio:
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┓
┃ ID ┃ Strategy             ┃ Symbol    ┃ Return ┃ Sharpe  ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━┩
│ 12 │ h2_rsi_divergence    │ BTC/USDT  │ 2.56%  │ 2.57    │
│  8 │ h2_rsi_divergence    │ ETH/USDT  │ 1.89%  │ 1.94    │
│ 11 │ h5_macd_breakout     │ BTC/USDT  │ 8.12%  │ 1.89    │
│  3 │ sma_crossover        │ BTC/USDT  │ 3.41%  │ 1.22    │
│  7 │ h5_macd_breakout     │ SOL/USDT  │ 5.67%  │ 1.11    │
└────┴──────────────────────┴───────────┴────────┴─────────┘
```

#### `cryplative results compare`
Side-by-side comparison of hypotheses.

```
Comparing H2 vs H5 (sorted by sharpe_ratio):

── H2 (6 results) ──────────────────────────────────────
  Best Sharpe:  2.57 (h2_rsi_divergence_trend, BTC/USDT, 4h)
  Avg Return:   1.82%
  Avg Sharpe:   1.45
  Pass rate:    67% (4/6)

── H5 (4 results) ──────────────────────────────────────
  Best Sharpe:  1.89 (h5_macd_breakout, BTC/USDT, 1d)
  Avg Return:   5.23%
  Avg Sharpe:   1.52
  Pass rate:    75% (3/4)

── Summary ──────────────────────────────────────────────
  Better avg Sharpe:    H5 (1.52 vs 1.45)
  Better avg Return:    H5 (5.23% vs 1.82%)
  Better pass rate:     H5 (75% vs 67%)
```

#### `cryplative results summary`
Catalog overview.

```
Strategy Results Catalog — data/catalog.db
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total results:     15
Strategies:        h2_rsi_divergence_trend, h5_macd_breakout, sma_crossover
Hypotheses:        H2, H5
Symbols:           BTC/USDT, ETH/USDT, SOL/USDT, LINK/USDT

Verdicts:
  PASS:     8
  FAIL:     4
  MARGINAL: 1
  (none):   2

Best by metric:
  Return:   8.12%  (h5_macd_breakout, BTC/USDT, 1d)
  Sharpe:   2.57   (h2_rsi_divergence_trend, BTC/USDT, 4h)
  Drawdown: -0.16% (h2_rsi_divergence_trend, BTC/USDT, 4h)
  Win Rate: 83.3%  (h2_rsi_divergence_trend, BTC/USDT, 4h)
```

#### `cryplative results tag`
Add or update hypothesis_id, verdict, or notes for an existing result.

```bash
cryplative results tag 12 --hypothesis H2 --verdict PASS --notes "Strong on BTC, train/test consistent"
# Output: "Updated result #12: hypothesis=H2, verdict=PASS"
```

#### `cryplative results rebuild`
Scan `data/strategy_results/` and index any JSON files not yet in the catalog.

```bash
cryplative results rebuild
# Output: "Indexed 12 new results. Total catalog entries: 15."
```

#### `cryplative results delete`
Remove a record from the catalog (does NOT delete the JSON file).

```bash
cryplative results delete 5
# Output: "Deleted result #5 (sma_crossover, ETH/USDT, 1h)"
```

### 5.4 Auto-insert on Backtest

Add an optional `--catalog` flag to the existing `cryplative backtest` command:

```python
# In the backtest command
catalog_flag: bool = typer.Option(False, "--catalog", help="Save result to the strategy catalog after backtest"),
hypothesis: str = typer.Option(None, "--hypothesis", help="Hypothesis ID tag (e.g., H2)"),
verdict: str = typer.Option(None, "--verdict", help="Verdict tag: PASS, FAIL, or MARGINAL"),
```

When `--catalog` is set:
1. Run the backtest as normal
2. After saving the JSON file, also insert into the catalog
3. Print a confirmation: "Result cataloged as #15 (h2_rsi_divergence_trend, BTC/USDT, 4h)"

This gives the research team a zero-friction way to build the catalog — just add `--catalog --hypothesis H2` to their existing backtest commands.

---

## 6. Integration Patterns

### 6.1 After BacktestEngine.run() — Python API

The primary integration point for programmatic use:

```python
from cryplative.backtesting.engine import BacktestEngine, BacktestConfig
from cryplative.catalog import ResultsCatalog

engine = BacktestEngine()
catalog = ResultsCatalog()  # defaults to data/catalog.db

# Run backtest
config = BacktestConfig(
    strategy_id="h2_rsi_divergence_trend",
    symbol="BTC/USDT",
    interval="4h",
    start_date="2024-01-01",
    end_date="2025-08-31",
    ...
)
result = engine.run(config)

# Save to JSON (existing behavior — engine does this already)
# ...

# Index in catalog (new)
row_id = catalog.insert_from_strategy_result(
    result,
    symbol=config.symbol,          # from config — NOT on StrategyResult
    interval=config.interval,      # from config — NOT on StrategyResult
    results_file="strategy_results/h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json",
    hypothesis_id="H2",
    verdict="PASS",
    notes="Strong on BTC, consistent across train/test",
)
```

### 6.2 Batch Backtest + Catalog Loop

For the research team's parameter sweep workflows:

```python
catalog = ResultsCatalog()

for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
    for interval in ["4h", "1d"]:
        config = BacktestConfig(
            strategy_id="h2_rsi_divergence_trend",
            symbol=symbol,
            interval=interval,
            start_date="2024-01-01",
            end_date="2025-08-31",
            ...
        )
        result = engine.run(config)
        # Auto-generate the results_file path matching the engine's save pattern
        catalog.insert_from_strategy_result(
            result,
            symbol=config.symbol,
            interval=config.interval,
            results_file=...,
            hypothesis_id="H2",
        )

# Now query
best = catalog.best(metric="sharpe_ratio", n=5)
```

### 6.3 Rebuilding from Existing Files

The research team already has 14 JSON files in `data/strategy_results/`. On first use:

```bash
cryplative results rebuild
# Scans data/strategy_results/, indexes all 14 files

# Then tag them
cryplative results tag 1 --hypothesis H2 --verdict PASS
cryplative results tag 2 --hypothesis H2 --verdict PASS
# ...
```

---

## 7. Implementation Steps

Implement in this exact order, committing after each step:

| Step | What to implement | Commit message |
|------|-------------------|----------------|
| **1** | **Schema + core module**: `catalog/__init__.py`, `catalog/db.py` (SQLite connection, CREATE TABLE + indexes, `CatalogEntry` and `CatalogSummary` dataclasses) | `feat: add strategy results catalog module with SQLite schema` |
| **2** | **Insert methods**: `ResultsCatalog.insert()` and `insert_from_strategy_result()` in `catalog/query.py` + tests | `feat: add catalog insert methods for indexing strategy results` |
| **3** | **Query methods**: `find()`, `best()`, `compare_hypotheses()`, `summary()` in `catalog/query.py` + tests | `feat: add catalog query methods for finding and comparing results` |
| **4** | **Rebuild + delete**: `rebuild()`, `clear()`, `delete()`, `delete_by_file()` + tests | `feat: add catalog rebuild and delete operations` |
| **5** | **CLI commands**: `cryplative results list/best/compare/summary/tag/rebuild/delete` subcommands + tests | `feat: add CLI commands for strategy results catalog` |
| **6** | **Backtest integration**: `--catalog`, `--hypothesis`, `--verdict` flags on `cryplative backtest` + tests | `feat: add --catalog flag to backtest command for auto-indexing` |
| **7** | **Optional: `to_dataframe()`** export method + tests | `feat: add optional pandas DataFrame export to catalog` |
| **8** | **Documentation**: Update `platform_docs/` with catalog usage guide | `docs: add strategy results catalog documentation` |

---

## 8. Testing Requirements

### 8.1 Coverage Target: 85%+

### 8.2 Test Files

```
tests/
├── test_catalog.py         # NEW — core catalog tests
└── test_cli.py             # UPDATE — catalog CLI subcommand tests
```

### 8.3 Key Test Scenarios

**test_catalog.py**:
- Schema creation on fresh database
- Idempotent schema creation (run twice, no error)
- `insert()` stores all fields correctly
- `insert_from_strategy_result()` extracts fields from StrategyResult correctly
- Duplicate `results_file` raises IntegrityError
- `find()` with no filters returns all results
- `find(symbol="BTC/USDT")` returns only BTC results
- `find(strategy_id="sma_crossover", interval="4h")` filters by both
- `find()` with no matches returns empty list
- `best(metric="sharpe_ratio", n=3)` returns top 3 sorted correctly
- `best(metric="max_drawdown_pct")` sorts ascending (least drawdown first)
- `compare_hypotheses(["H2", "H5"])` returns separate lists per hypothesis
- `summary()` returns correct counts and best-by-metric entries
- `rebuild()` scans directory and inserts new files
- `rebuild()` skips already-indexed files (idempotent)
- `delete()` removes a record
- `delete_by_file()` removes by file path
- `clear()` removes all records
- `to_dataframe()` returns DataFrame when pandas available
- `to_dataframe()` raises ImportError with helpful message when pandas not available
- `tag()` updates hypothesis_id, verdict, notes on existing record
- Results sorted by created_at desc in find()

**test_cli.py** (additions):
- `cryplative results list` displays a table
- `cryplative results list --symbol BTC/USDT` filters correctly
- `cryplative results best --metric sharpe_ratio` displays top results
- `cryplative results compare H2 H5` shows side-by-side comparison
- `cryplative results summary` shows catalog overview
- `cryplative results rebuild` scans and indexes
- `cryplative results tag 1 --hypothesis H2 --verdict PASS` updates record
- `cryplative results delete 1` removes record
- `cryplative backtest --catalog --hypothesis H2` inserts into catalog after run

### 8.4 Test Database

Tests MUST use a temporary file (`:memory:` or `tempfile.NamedTemporaryFile`) — never the real `data/catalog.db`.

---

## 9. Dependencies

### 9.1 New Dependencies

**None required.** SQLite is in the Python standard library.

### 9.2 Optional Dependencies

- **pandas**: For `to_dataframe()`. NOT added to requirements. The method gracefully handles absence.

### 9.3 Existing Dependencies Used

- `sqlite3` (stdlib) — database
- `json` (stdlib) — parsing parameters and reading result files for rebuild
- `pathlib` (stdlib) — file path handling
- `rich` (existing) — CLI table output
- `typer` (existing) — CLI framework

---

## 10. Acceptance Criteria

This spec is complete when ALL of the following are true:

### Core
- [ ] `ResultsCatalog` class in `platform/src/cryplative/catalog/`
- [ ] SQLite database schema creates correctly on fresh start
- [ ] `insert()` and `insert_from_strategy_result()` work correctly
- [ ] Duplicate `results_file` is rejected (IntegrityError)

### Query
- [ ] `find()` filters by strategy_id, hypothesis_id, symbol, interval, verdict, run_type
- [ ] `best()` returns top N results sorted by any metric
- [ ] `compare_hypotheses()` separates results by hypothesis ID
- [ ] `summary()` returns catalog overview with best-by-metric

### Management
- [ ] `rebuild()` scans `data/strategy_results/` and indexes existing files
- [ ] `delete()` and `delete_by_file()` remove records
- [ ] `tag()` updates hypothesis_id, verdict, notes

### CLI
- [ ] `cryplative results list` displays filtered results table
- [ ] `cryplative results best --metric sharpe_ratio` shows top results
- [ ] `cryplative results compare H2 H5` shows hypothesis comparison
- [ ] `cryplative results summary` shows catalog overview
- [ ] `cryplative results tag` updates result metadata
- [ ] `cryplative results rebuild` indexes existing files
- [ ] `cryplative results delete` removes catalog entries

### Integration
- [ ] `cryplative backtest --catalog --hypothesis H2` auto-inserts into catalog
- [ ] `--catalog` flag is optional (default: off, no catalog interaction)
- [ ] Backtest without `--catalog` produces identical behavior to current (regression)

### Quality
- [ ] All tests pass with `uv run pytest`
- [ ] Test coverage >= 85%
- [ ] `uv run ruff check .` passes
- [ ] `uv run mypy src/` passes
- [ ] Tests use temporary databases, never the real `data/catalog.db`

### Documentation
- [ ] Platform docs updated with catalog usage guide and examples

---

## 11. Out of Scope

- Trade-level data storage (stays in JSON files)
- Automatic verdict calculation (researcher decides)
- Multi-user access / concurrent writes (single-user desktop tool)
- Web API for catalog (Phase 4 — Bun.js API will wrap this)
- Schema migrations framework (single table, version 1 — add migration logic when needed)
- Automated hypothesis tracking / experiment management (could be Phase 5)
- Time-series analytics on results (the catalog indexes, not analyzes)

---

## 12. Future Considerations

These are NOT in scope now but inform the design:

1. **Phase 4 API**: The Bun.js API will expose catalog endpoints. The SQLite database file in `data/` will be the backend. Keep the schema stable.
2. **Phase 5 analytics**: Parameter optimization tools will query the catalog to understand which parameter ranges perform best. The `parameters_json` blob supports this.
3. **Regime tagging**: A future `regime` column could tag results by market regime (bull/bear/range). The schema is easy to extend with `ALTER TABLE ADD COLUMN`.
4. **Multi-TF results**: When multi-timeframe backtesting arrives (Phase 3), the interval field can become a comma-separated list or a separate table. For now, single interval per result.

---

*This specification is self-contained. The platform-developer should build this as a new module in the existing platform, following the patterns from SPEC-000 and SPEC-001.*
