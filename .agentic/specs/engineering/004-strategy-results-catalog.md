# SPEC-004: Strategy Results Catalog

**Author**: CTO Agent
**Date**: 2026-05-18
**Status**: Draft v2 — Updated per research team review (3 critical + 4 suggestions incorporated)
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
- "Show me results with Sharpe > 1.0 on test data only"
- "Group this parameter sweep as one experiment"

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
    experiment_id   TEXT,                   -- e.g., "sweep_20260518" (nullable — groups parameter sweeps)
    run_type        TEXT    NOT NULL,       -- "BACKTEST", "PAPER", "REAL"

    -- Data split (critical for train/test methodology)
    data_split      TEXT    NOT NULL DEFAULT 'FULL',  -- "TRAIN", "TEST", "FULL", "OUT_OF_SAMPLE"
    train_result_id INTEGER,               -- Nullable. Links a TEST result to its TRAIN result's id.
                                            -- Only set when data_split="TEST". No FK constraint —
                                            -- logical reference only (keeps single-table design simple).

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

    -- Fee tracking (comparability)
    fees_included   INTEGER,               -- 0 or 1. Whether fees were applied during backtest.
                                            -- Critical for comparing results fairly.

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
CREATE INDEX IF NOT EXISTS idx_experiment_id  ON results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_symbol         ON results(symbol);
CREATE INDEX IF NOT EXISTS idx_interval       ON results(interval);
CREATE INDEX IF NOT EXISTS idx_verdict        ON results(verdict);
CREATE INDEX IF NOT EXISTS idx_data_split     ON results(data_split);
CREATE UNIQUE INDEX IF NOT EXISTS idx_results_file ON results(results_file);
```

**Key**: `idx_results_file` is a **UNIQUE** index. This prevents the same results file from being indexed twice — critical for idempotent `rebuild()` and safe `insert()` operations.

### 3.3 Design Decisions

- **Single table, not normalized**: We're indexing backtest results, not building a relational analytics warehouse. One table with indexes is simpler to query and maintain.
- **Nullable hypothesis_id**: Not every backtest run belongs to a hypothesis. Ad-hoc exploration runs won't have one.
- **Nullable experiment_id**: Groups parameter sweep results into one batch. Distinct from hypothesis_id — an experiment tests one hypothesis with varied parameters.
- **data_split with DEFAULT 'FULL'**: Every result tracks whether it's from training data, test data, full data, or out-of-sample. Defaults to FULL for backward compatibility and ad-hoc runs. This prevents the critical error of mixing train and test results in comparisons.
- **train_result_id as logical reference (no FK)**: Links a TEST result back to the TRAIN result that produced its parameters. No formal foreign key constraint — keeps the single-table design simple and avoids circular schema issues. Application-level validation ensures the referenced ID exists.
- **Nullable verdict**: Set by the researcher after analysis, not automatically. An un-verdicted result is just "logged".
- **fees_included as INTEGER boolean**: Critical for comparability. If one result includes 0.1% fees and another doesn't, comparing them directly is misleading. Stored as INTEGER because SQLite has no native boolean type. The actual fee_rate is available in the detailed JSON if needed — not duplicated in the index.
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
        experiment_id: str | None = None,
        data_split: str = "FULL",        # "TRAIN", "TEST", "FULL", "OUT_OF_SAMPLE"
        train_result_id: int | None = None,  # Links TEST to its TRAIN result
        fees_included: bool | None = None,
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
            experiment_id: Optional experiment batch tag (e.g., "sweep_20260518")
            data_split: Data split type — "TRAIN", "TEST", "FULL", "OUT_OF_SAMPLE".
                        Defaults to "FULL".
            train_result_id: When data_split="TEST", the catalog ID of the
                             corresponding TRAIN result. None otherwise.
            fees_included: Whether fees were applied during the backtest.
                           None = unknown (backward compat for rebuild).
            verdict: Optional verdict ("PASS", "FAIL", "MARGINAL")
            notes: Optional free-form notes

        Raises:
            ValueError: If required fields are missing, metrics dict lacks expected
                        keys, or data_split is not a valid value.
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
        experiment_id: str | None = None,
        data_split: str = "FULL",
        train_result_id: int | None = None,
        fees_included: bool | None = None,
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

        NOTE on results_file: The BacktestEngine._save_result() method saves
        the JSON file but currently returns None. When using this method
        programmatically, obtain the results_file path from either:
        (a) The return value of BacktestEngine.save_result() after the engine
            update in Step 6 (preferred), or
        (b) The ResultsCatalog.build_results_path() helper method.

        Typical usage:
            config = BacktestConfig(strategy_id="sma", symbol="BTC/USDT", interval="4h", ...)
            result = engine.run(config)
            saved_path = engine.save_result(result, config)  # returns path after Step 6
            catalog.insert_from_strategy_result(
                result,
                symbol=config.symbol,
                interval=config.interval,
                results_file=saved_path,
                hypothesis_id="H2",
                data_split="TEST",
                train_result_id=train_row_id,
            )
        """
        ...

    @staticmethod
    def build_results_path(
        strategy_id: str,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
    ) -> str:
        """
        Build the expected relative results file path matching the engine's
        save convention.

        Constructs: "strategy_results/{strategy_id}_{BASE}_{QUOTE}_{interval}_{start}T00:00:00Z_{end}T23:59:59Z.json"

        Args:
            strategy_id: Strategy identifier
            symbol: Trading pair (e.g., "BTC/USDT")
            interval: Candle interval (e.g., "4h")
            start_date: Start date (ISO 8601 date, e.g., "2024-01-01")
            end_date: End date (ISO 8601 date, e.g., "2025-08-31")

        Returns:
            Relative path string from data/ directory.

        Example:
            >>> ResultsCatalog.build_results_path("sma", "BTC/USDT", "4h", "2024-01-01", "2025-08-31")
            "strategy_results/sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json"
        """
        ...

    # ── Query ───────────────────────────────────────────

    def find(
        self,
        strategy_id: str | None = None,
        hypothesis_id: str | None = None,
        experiment_id: str | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        verdict: str | None = None,
        run_type: str | None = None,
        data_split: str | None = None,
        min_sharpe: float | None = None,
        min_return_pct: float | None = None,
        min_win_rate_pct: float | None = None,
        min_profit_factor: float | None = None,
        max_drawdown_pct: float | None = None,
    ) -> list[CatalogEntry]:
        """
        Find results matching all given filters (AND logic).
        None means "don't filter by this field".

        Returns list of CatalogEntry objects, sorted by created_at desc
        (newest first).

        Metric thresholds:
            min_sharpe:         Only results with sharpe_ratio >= this value
            min_return_pct:     Only results with total_return_pct >= this value
            min_win_rate_pct:   Only results with win_rate_pct >= this value
            min_profit_factor:  Only results with profit_factor >= this value
            max_drawdown_pct:   Only results with max_drawdown_pct >= this value
                                (note: drawdown is negative, so -5.0 means
                                 "no worse than -5%")

        Examples:
            catalog.find(symbol="BTC/USDT")
            catalog.find(hypothesis_id="H2", data_split="TEST")
            catalog.find(strategy_id="sma_crossover", interval="4h")
            catalog.find(verdict="PASS", min_sharpe=1.0)
            catalog.find(data_split="TEST", min_return_pct=5.0)
            catalog.find(experiment_id="sweep_20260518")
        """
        ...

    def compare_hypotheses(
        self,
        hypothesis_ids: list[str],
        metric: str = "sharpe_ratio",
        data_split: str | None = "TEST",
    ) -> dict[str, list[CatalogEntry]]:
        """
        Compare results across multiple hypotheses.

        By default, only compares TEST data_split results to avoid train/test
        contamination. Pass data_split=None to include all splits.

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
        data_split: str | None = None,
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
            data_split: Optional filter (e.g., "TEST" for test-only best)
        """
        ...

    def get(self, result_id: int) -> CatalogEntry | None:
        """
        Get a single result by its row ID.

        Returns the CatalogEntry, or None if not found.

        Example:
            entry = catalog.get(12)
            if entry:
                print(entry.strategy_id, entry.sharpe_ratio)
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
            - data_split_counts: dict[str, int]  (e.g., {"TRAIN": 5, "TEST": 5, "FULL": 10})
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
        experiment_id: str | None = None,
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

    def rebuild(self, results_dir: str = "data/strategy_results") -> RebuildResult:
        """
        Rebuild the catalog by scanning the results directory.

        Reads all JSON files in results_dir, extracts metadata and metrics,
        and inserts them into the catalog. Skips files already indexed
        (by results_file uniqueness).

        Returns a RebuildResult with counts:
            - indexed: number of newly inserted records
            - skipped_existing: number already in catalog
            - skipped_parse_error: number that failed to parse (with reasons)

        FILENAME PARSING STRATEGY:
        The actual files in data/strategy_results/ follow at least two naming
        conventions. rebuild() tries them in order:

        Pattern 1 (engine format — current):
            {strategy_id}_{BASE}_{QUOTE}_{interval}_{start}T00:00:00Z_{end}T23:59:59Z.json
            Regex: r"^(.+)_(\w+)_(\w+)_(\w+)_(\d{4}-\d{2}-\d{2}T[\d:]+Z)_(\d{4}-\d{2}-\d{2}T[\d:]+Z)\.json$"
            symbol = f"{match.group(2)}/{match.group(3)}"

        Pattern 2 (old format — initial engine output):
            {strategy_id}_{BASE}_{QUOTE}_{interval}_{start}_{end}.json
            Regex: r"^(.+)_(\w+)_(\w+)_(\w+)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json$"
            symbol = f"{match.group(2)}/{match.group(3)}"

        Non-matching files (e.g., "H2-detailed-results.json") are skipped
        with a logged warning. They are NOT result files and should not
        be in the catalog.

        If neither regex matches, attempt to read symbol from the first
        trade's signal.symbol field inside the JSON (last-resort fallback).

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
    experiment_id: str | None
    run_type: str
    data_split: str                    # "TRAIN", "TEST", "FULL", "OUT_OF_SAMPLE"
    train_result_id: int | None        # Links TEST to its TRAIN result
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
    fees_included: bool | None         # Whether fees were applied
    verdict: str | None
    results_file: str
    parameters: dict                   # parsed from parameters_json
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
    data_split_counts: dict[str, int]  # e.g., {"TRAIN": 5, "TEST": 5, "FULL": 10}


@dataclass
class RebuildResult:
    """Result of a catalog rebuild operation."""
    indexed: int                       # Successfully inserted
    skipped_existing: int              # Already in catalog
    skipped_parse_error: int           # Could not parse
    errors: list[str]                  # Parse error details (filename + reason)
```

### 4.3 Design Principles

1. **No raw SQL required** — all common queries are methods on `ResultsCatalog`. The research team calls `catalog.find(symbol="BTC/USDT")`, not `cursor.execute("SELECT * FROM results WHERE symbol = ?", ...)`.
2. **Filter by any combination** — `find()` takes optional kwargs, all ANDed together. None = no filter.
3. **Metric threshold filtering** — `find()` supports `min_sharpe`, `min_return_pct`, etc. for queries like "show me results with Sharpe > 1.0".
4. **Typed returns** — `CatalogEntry` dataclasses, not raw tuples. IDE-friendly, self-documenting.
5. **Graceful pandas optional** — `to_dataframe()` is available when pandas is present, doesn't fail when it's not. This respects that the platform doesn't require pandas.
6. **Idempotent insert** — duplicate `results_file` raises `IntegrityError`. The catalog won't index the same result twice.
7. **Train/test safety** — `data_split` is tracked on every result. `compare_hypotheses()` defaults to TEST-only to prevent train/test contamination.

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
cryplative results list   [--strategy STRATEGY] [--hypothesis HYPOTHESIS]
                          [--experiment EXPERIMENT] [--symbol SYMBOL]
                          [--interval INTERVAL] [--verdict VERDICT]
                          [--data-split SPLIT] [--min-sharpe FLOAT]
                          [--min-return FLOAT] [--limit N]

cryplative results best   [--metric METRIC] [--top N] [--strategy STRATEGY]
                          [--symbol SYMBOL] [--hypothesis HYPOTHESIS]
                          [--data-split SPLIT]

cryplative results show   RESULT_ID

cryplative results compare  HYPOTHESIS_IDS... [--metric METRIC]
                            [--data-split SPLIT]

cryplative results summary

cryplative results rebuild [--results-dir DIR]

cryplative results tag    RESULT_ID [--hypothesis HYPOTHESIS]
                          [--experiment EXPERIMENT]
                          [--verdict VERDICT] [--notes NOTES]

cryplative results delete RESULT_ID
```

### 5.3 Subcommand Details

#### `cryplative results list`
Display a Rich table of results matching the filters.

```
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ ID ┃ Strategy             ┃ Hyp  ┃ Symbol    ┃ TF    ┃ Split  ┃ Return  ┃ Sharpe  ┃ Verdict┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ 12 │ h2_rsi_divergence    │ H2   │ BTC/USDT  │ 4h    │ TEST   │ 2.56%   │ 2.57    │ PASS   │
│ 11 │ h5_macd_breakout     │ H5   │ BTC/USDT  │ 1d    │ TEST   │ 8.12%   │ 1.89    │ PASS   │
│ 10 │ sma_crossover        │ —    │ ETH/USDT  │ 1h    │ FULL   │ -1.2%   │ 0.43    │ FAIL   │
└────┴──────────────────────┴──────┴───────────┴───────┴────────┴─────────┴─────────┴────────┘

Showing 3 of 15 results. Use --limit to show more.
```

Default limit: 20. Color-code: green for positive return, red for negative. Sharpe > 1.0 in bold. Data split shown as a column.

#### `cryplative results best`
Show the top N results for a given metric.

```
Top 5 by sharpe_ratio (data_split=TEST):
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ ID ┃ Strategy             ┃ Symbol    ┃ Split  ┃ Return  ┃ Sharpe ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ 12 │ h2_rsi_divergence    │ BTC/USDT  │ TEST   │ 2.56%   │ 2.57   │
│  8 │ h2_rsi_divergence    │ ETH/USDT  │ TEST   │ 1.89%   │ 1.94   │
│ 11 │ h5_macd_breakout     │ BTC/USDT  │ TEST   │ 8.12%   │ 1.89   │
│  3 │ sma_crossover        │ BTC/USDT  │ TEST   │ 3.41%   │ 1.22   │
│  7 │ h5_macd_breakout     │ SOL/USDT  │ TEST   │ 5.67%   │ 1.11   │
└────┴──────────────────────┴───────────┴────────┴─────────┴────────┘
```

#### `cryplative results show`
Display full details of a single result.

```
Result #12
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Strategy:        h2_rsi_divergence_trend
Hypothesis:      H2
Experiment:      sweep_20260518
Data Split:      TEST
Train Result:    #8
Symbol:          BTC/USDT
Interval:        4h
Period:          2025-09-01 to 2026-04-30

Metrics:
  Return:        2.56%
  Sharpe:        2.57
  Max Drawdown:  -0.42%
  Win Rate:      83.33%
  Trades:        6
  Profit Factor: 17.79
  Fees Included: Yes

Verdict:         PASS
Notes:           Strong on BTC, consistent train/test
File:            strategy_results/h2_rsi_divergence_trend_BTC_USDT_4h_2025-09-01T00:00:00Z_2026-04-30T23:59:59Z.json

Parameters:
  rsi_period: 14
  divergence_threshold: 0.5
  stop_loss_pct: 2.0
```

#### `cryplative results compare`
Side-by-side comparison of hypotheses.

```
Comparing H2 vs H5 (metric=sharpe_ratio, data_split=TEST):

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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total results:     15
Strategies:        h2_rsi_divergence_trend, h5_macd_breakout, sma_crossover
Hypotheses:        H2, H5
Symbols:           BTC/USDT, ETH/USDT, SOL/USDT, LINK/USDT

Data Splits:
  FULL:           8
  TRAIN:          4
  TEST:           3

Verdicts:
  PASS:     8
  FAIL:     4
  MARGINAL: 1
  (none):   2

Best by metric (TEST only):
  Return:   8.12%  (h5_macd_breakout, BTC/USDT, 1d)
  Sharpe:   2.57   (h2_rsi_divergence_trend, BTC/USDT, 4h)
  Drawdown: -0.16% (h2_rsi_divergence_trend, BTC/USDT, 4h)
  Win Rate: 83.3%  (h2_rsi_divergence_trend, BTC/USDT, 4h)
```

#### `cryplative results tag`
Add or update hypothesis_id, experiment_id, verdict, or notes for an existing result.

```bash
cryplative results tag 12 --hypothesis H2 --verdict PASS --notes "Strong on BTC, train/test consistent"
# Output: "Updated result #12: hypothesis=H2, verdict=PASS"

cryplative results tag 12 --experiment sweep_20260518
# Output: "Updated result #12: experiment=sweep_20260518"
```

#### `cryplative results rebuild`
Scan `data/strategy_results/` and index any JSON files not yet in the catalog.

```bash
cryplative results rebuild
# Output:
# "Indexed 12 new results (2 already indexed, 1 skipped: H2-detailed-results.json)"
# Total catalog entries: 14
```

#### `cryplative results delete`
Remove a record from the catalog (does NOT delete the JSON file).

```bash
cryplative results delete 5
# Output: "Deleted result #5 (sma_crossover, ETH/USDT, 1h)"
```

### 5.4 Auto-insert on Backtest

Add optional flags to the existing `cryplative backtest` command:

```python
# In the backtest command
catalog_flag: bool = typer.Option(False, "--catalog", help="Save result to the strategy catalog after backtest"),
hypothesis: str = typer.Option(None, "--hypothesis", help="Hypothesis ID tag (e.g., H2)"),
experiment: str = typer.Option(None, "--experiment", help="Experiment batch ID (e.g., sweep_20260518)"),
data_split: str = typer.Option("FULL", "--data-split", help="Data split: TRAIN, TEST, FULL, OUT_OF_SAMPLE"),
train_result: int = typer.Option(None, "--train-result", help="ID of the training result (for TEST splits)"),
verdict: str = typer.Option(None, "--verdict", help="Verdict tag: PASS, FAIL, or MARGINAL"),
```

When `--catalog` is set:
1. Run the backtest as normal
2. After saving the JSON file, also insert into the catalog
3. The results_file path is obtained from the engine's save_result return value (see Step 6)
4. Print a confirmation: "Result cataloged as #15 (h2_rsi_divergence_trend, BTC/USDT, 4h, split=TEST)"

This gives the research team a zero-friction way to build the catalog — just add `--catalog --hypothesis H2 --data-split TEST` to their existing backtest commands.

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

# Save to JSON — engine returns the saved path (after Step 6 engine update)
saved_path = engine.save_result(result, config)

# Index in catalog (new)
row_id = catalog.insert_from_strategy_result(
    result,
    symbol=config.symbol,          # from config — NOT on StrategyResult
    interval=config.interval,      # from config — NOT on StrategyResult
    results_file=saved_path,       # from engine's save_result
    hypothesis_id="H2",
    data_split="TEST",
    train_result_id=train_row_id,
    fees_included=True,
    verdict="PASS",
    notes="Strong on BTC, consistent across train/test",
)
```

### 6.2 Batch Backtest + Catalog Loop (Parameter Sweep)

For the research team's parameter sweep workflows:

```python
catalog = ResultsCatalog()
experiment_id = "sweep_20260518"

# First: training runs
train_ids = {}
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
        saved_path = engine.save_result(result, config)
        row_id = catalog.insert_from_strategy_result(
            result,
            symbol=config.symbol,
            interval=config.interval,
            results_file=saved_path,
            hypothesis_id="H2",
            experiment_id=experiment_id,
            data_split="TRAIN",
        )
        train_ids[(symbol, interval)] = row_id

# Then: test runs, linked to training
for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
    for interval in ["4h", "1d"]:
        config = BacktestConfig(
            strategy_id="h2_rsi_divergence_trend",
            symbol=symbol,
            interval=interval,
            start_date="2025-09-01",
            end_date="2026-04-30",
            ...
        )
        result = engine.run(config)
        saved_path = engine.save_result(result, config)
        catalog.insert_from_strategy_result(
            result,
            symbol=config.symbol,
            interval=config.interval,
            results_file=saved_path,
            hypothesis_id="H2",
            experiment_id=experiment_id,
            data_split="TEST",
            train_result_id=train_ids[(symbol, interval)],
        )

# Query test results only
best = catalog.best(metric="sharpe_ratio", n=5, data_split="TEST")
```

### 6.3 Rebuilding from Existing Files

The research team already has 14 JSON files in `data/strategy_results/`. On first use:

```bash
cryplative results rebuild
# Scans data/strategy_results/, indexes all 14 files
# Skips H2-detailed-results.json (doesn't match patterns)

# Then tag them
cryplative results tag 1 --hypothesis H2 --data-split TRAIN
cryplative results tag 2 --hypothesis H2 --data-split TEST
# ...
```

### 6.4 Querying with Metric Thresholds

```python
# Research lead: "Show me test results with Sharpe > 1.0"
good_results = catalog.find(data_split="TEST", min_sharpe=1.0)

# "Show me profitable test results on BTC"
profitable = catalog.find(
    data_split="TEST",
    symbol="BTC/USDT",
    min_return_pct=0.0,
)

# "Best test results from the parameter sweep"
sweep_best = catalog.best(
    metric="sharpe_ratio",
    n=10,
    experiment_id="sweep_20260518",
    data_split="TEST",
)
```

---

## 7. Engine Modification (Prerequisite for Step 6)

### 7.1 `BacktestEngine._save_result` Return Value Change

The existing `BacktestEngine._save_result()` method currently returns `None`. It must be updated to return the saved file's relative path from `data/`.

**Change** (in `platform/src/cryplative/backtesting/engine.py`):

```python
# BEFORE (current):
def _save_result(self, result: StrategyResult, config: BacktestConfig) -> None:
    """Save the strategy result as JSON to the results directory."""
    ...

# AFTER (updated):
def _save_result(self, result: StrategyResult, config: BacktestConfig) -> str:
    """Save the strategy result as JSON to the results directory.

    Returns the relative path from data/ to the saved file.
    """
    ...
```

This is a **non-breaking change** — nobody currently checks the return value of `_save_result`.

Additionally, expose this as a public method for programmatic callers:

```python
def save_result(self, result: StrategyResult, config: BacktestConfig) -> str:
    """Public wrapper for _save_result. Returns the relative path from data/."""
    return self._save_result(result, config)
```

### 7.2 Why Not Insert in the Engine?

The catalog insert should NOT happen inside the engine. Reasons:
1. **Separation of concerns** — the engine's job is to run backtests and save results. Catalog is a separate concern.
2. **Optional dependency** — catalog use is optional. The engine should work identically without it.
3. **The caller has context** — only the caller knows hypothesis_id, data_split, experiment_id, etc. The engine does not.

The engine provides the saved path. The caller (CLI or Python script) does the catalog insert.

---

## 8. Implementation Steps

Implement in this exact order, committing after each step:

| Step | What to implement | Commit message |
|------|-------------------|----------------|
| **1** | **Schema + core module**: `catalog/__init__.py`, `catalog/db.py` (SQLite connection, CREATE TABLE + indexes, `CatalogEntry`, `CatalogSummary`, `RebuildResult` dataclasses) | `feat: add strategy results catalog module with SQLite schema` |
| **2** | **Insert methods**: `ResultsCatalog.insert()` and `insert_from_strategy_result()` + `build_results_path()` + tests | `feat: add catalog insert methods for indexing strategy results` |
| **3** | **Query methods**: `find()` (with metric thresholds), `best()`, `compare_hypotheses()`, `get()`, `summary()` + tests | `feat: add catalog query methods for finding and comparing results` |
| **4** | **Rebuild + delete**: `rebuild()` (with multi-pattern filename parsing + fallback), `clear()`, `delete()`, `delete_by_file()` + tests | `feat: add catalog rebuild and delete operations` |
| **5** | **CLI commands**: `cryplative results list/best/show/compare/summary/tag/rebuild/delete` subcommands + tests | `feat: add CLI commands for strategy results catalog` |
| **6** | **Engine update + backtest integration**: Update `_save_result` to return path, add public `save_result`, add `--catalog`, `--hypothesis`, `--experiment`, `--data-split`, `--train-result`, `--verdict` flags on `cryplative backtest` + tests | `feat: update engine to return saved path, add --catalog flag to backtest` |
| **7** | **Optional: `to_dataframe()`** export method + tests | `feat: add optional pandas DataFrame export to catalog` |
| **8** | **Documentation**: Update `platform_docs/` with catalog usage guide | `docs: add strategy results catalog documentation` |

---

## 9. Testing Requirements

### 9.1 Coverage Target: 85%+

### 9.2 Test Files

```
tests/
├── test_catalog.py         # NEW — core catalog tests
└── test_cli.py             # UPDATE — catalog CLI subcommand tests
```

### 9.3 Key Test Scenarios

**test_catalog.py**:
- Schema creation on fresh database
- Idempotent schema creation (run twice, no error)
- `insert()` stores all fields correctly (including new: data_split, experiment_id, fees_included, train_result_id)
- `insert_from_strategy_result()` extracts fields from StrategyResult correctly
- `insert()` with data_split="TEST" and train_result_id links to training run
- Duplicate `results_file` raises IntegrityError
- `find()` with no filters returns all results
- `find(symbol="BTC/USDT")` returns only BTC results
- `find(strategy_id="sma_crossover", interval="4h")` filters by both
- `find()` with no matches returns empty list
- `find(data_split="TEST")` returns only test results
- `find(experiment_id="sweep_20260518")` returns only that experiment's results
- `find(min_sharpe=1.0)` filters by metric threshold
- `find(min_return_pct=5.0, data_split="TEST")` combines threshold with filter
- `best(metric="sharpe_ratio", n=3)` returns top 3 sorted correctly
- `best(metric="max_drawdown_pct")` sorts ascending (least drawdown first)
- `best(data_split="TEST")` filters by data split
- `compare_hypotheses(["H2", "H5"])` returns separate lists per hypothesis
- `compare_hypotheses(["H2", "H5"], data_split=None)` includes all splits
- `get(12)` returns the correct entry
- `get(999)` returns None for non-existent ID
- `summary()` returns correct counts, data_split_counts, and best-by-metric entries
- `rebuild()` scans directory and inserts new files
- `rebuild()` handles engine-format filenames correctly
- `rebuild()` handles old-format filenames correctly (e.g., `sma_crossover_BTC_USDT_1h_2025-01-01_2025-01-31.json`)
- `rebuild()` skips non-result files (e.g., `H2-detailed-results.json`) with logged warning
- `rebuild()` skips already-indexed files (idempotent)
- `rebuild()` returns RebuildResult with correct counts
- `delete()` removes a record
- `delete_by_file()` removes by file path
- `clear()` removes all records
- `to_dataframe()` returns DataFrame when pandas available
- `to_dataframe()` raises ImportError with helpful message when pandas not available
- `tag()` updates hypothesis_id, experiment_id, verdict, notes on existing record
- `build_results_path()` constructs correct path
- Results sorted by created_at desc in find()

**test_cli.py** (additions):
- `cryplative results list` displays a table
- `cryplative results list --symbol BTC/USDT --data-split TEST` filters correctly
- `cryplative results list --min-sharpe 1.0` filters by threshold
- `cryplative results best --metric sharpe_ratio` displays top results
- `cryplative results show 12` displays full result details
- `cryplative results show 999` displays "not found" message
- `cryplative results compare H2 H5` shows side-by-side comparison
- `cryplative results summary` shows catalog overview
- `cryplative results rebuild` scans and indexes
- `cryplative results tag 1 --hypothesis H2 --verdict PASS` updates record
- `cryplative results tag 1 --experiment sweep_20260518` updates experiment
- `cryplative results delete 1` removes record
- `cryplative backtest --catalog --hypothesis H2 --data-split TEST` inserts into catalog after run

### 9.4 Test Database

Tests MUST use a temporary file (`:memory:` or `tempfile.NamedTemporaryFile`) — never the real `data/catalog.db`.

---

## 10. Dependencies

### 10.1 New Dependencies

**None required.** SQLite is in the Python standard library.

### 10.2 Optional Dependencies

- **pandas**: For `to_dataframe()`. NOT added to requirements. The method gracefully handles absence.

### 10.3 Existing Dependencies Used

- `sqlite3` (stdlib) — database
- `json` (stdlib) — parsing parameters and reading result files for rebuild
- `pathlib` (stdlib) — file path handling
- `re` (stdlib) — filename pattern matching in rebuild
- `logging` (stdlib) — warnings for skipped files in rebuild
- `rich` (existing) — CLI table output
- `typer` (existing) — CLI framework

---

## 11. Acceptance Criteria

This spec is complete when ALL of the following are true:

### Core
- [ ] `ResultsCatalog` class in `platform/src/cryplative/catalog/`
- [ ] SQLite database schema creates correctly on fresh start
- [ ] `insert()` and `insert_from_strategy_result()` work correctly with all fields
- [ ] Duplicate `results_file` is rejected (IntegrityError)
- [ ] `build_results_path()` constructs correct paths

### Data Split
- [ ] `data_split` field defaults to "FULL" for backward compatibility
- [ ] `train_result_id` links TEST results to TRAIN results
- [ ] `compare_hypotheses()` defaults to TEST-only to prevent train/test contamination

### Query
- [ ] `find()` filters by strategy_id, hypothesis_id, experiment_id, symbol, interval, verdict, run_type, data_split
- [ ] `find()` supports metric thresholds: min_sharpe, min_return_pct, min_win_rate_pct, min_profit_factor, max_drawdown_pct
- [ ] `best()` returns top N results sorted by any metric, optionally filtered by data_split
- [ ] `compare_hypotheses()` separates results by hypothesis ID, defaults to TEST-only
- [ ] `get()` returns a single result by ID, or None if not found
- [ ] `summary()` returns catalog overview with best-by-metric and data_split_counts

### Management
- [ ] `rebuild()` handles engine-format filenames (with T00:00:00Z timestamps)
- [ ] `rebuild()` handles old-format filenames (bare dates)
- [ ] `rebuild()` skips non-result files with a logged warning
- [ ] `rebuild()` returns RebuildResult with indexed/skipped/error counts
- [ ] `delete()` and `delete_by_file()` remove records
- [ ] `tag()` updates hypothesis_id, experiment_id, verdict, notes

### CLI
- [ ] `cryplative results list` displays filtered results table (including data_split column)
- [ ] `cryplative results list --min-sharpe 1.0` filters by metric threshold
- [ ] `cryplative results best --metric sharpe_ratio` shows top results
- [ ] `cryplative results show RESULT_ID` displays full result details
- [ ] `cryplative results compare H2 H5` shows hypothesis comparison (TEST-only by default)
- [ ] `cryplative results summary` shows catalog overview with data_split counts
- [ ] `cryplative results tag` updates result metadata
- [ ] `cryplative results rebuild` indexes existing files (handles both filename formats)
- [ ] `cryplative results delete` removes catalog entries

### Integration
- [ ] `BacktestEngine._save_result()` returns the saved file path (str, not None)
- [ ] `BacktestEngine.save_result()` public method exists and returns path
- [ ] `cryplative backtest --catalog --hypothesis H2 --data-split TEST` auto-inserts into catalog
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

## 12. Out of Scope

- Trade-level data storage (stays in JSON files)
- Automatic verdict calculation (researcher decides)
- Multi-user access / concurrent writes (single-user desktop tool)
- Web API for catalog (Phase 4 — Bun.js API will wrap this)
- Schema migrations framework (single table, version 1 — add migration logic when needed)
- Automated hypothesis tracking / experiment management (could be Phase 5)
- Time-series analytics on results (the catalog indexes, not analyzes)
- `fee_rate` in the catalog index (available in JSON if needed; `fees_included` boolean is sufficient for comparability)
- Walk-forward validation mode (Phase 5 potential — the data_split + train_result_id fields support it structurally)

---

## 13. Future Considerations

These are NOT in scope now but inform the design:

1. **Phase 4 API**: The Bun.js API will expose catalog endpoints. The SQLite database file in `data/` will be the backend. Keep the schema stable.
2. **Phase 5 analytics**: Parameter optimization tools will query the catalog to understand which parameter ranges perform best. The `parameters_json` blob supports this.
3. **Regime tagging**: A future `regime` column could tag results by market regime (bull/bear/range). The schema is easy to extend with `ALTER TABLE ADD COLUMN`.
4. **Multi-TF results**: When multi-timeframe backtesting arrives (Phase 3), the interval field can become a comma-separated list or a separate table. For now, single interval per result.
5. **Walk-forward validation**: The `data_split` + `train_result_id` fields provide the structural foundation. A future wrapper could automate the train/test cycle and insert both halves.

---

## 14. Revision History

| Version | Date | Changes |
|---------|------|---------|
| v1 | 2026-05-18 | Initial draft, validated with platform-developer |
| v2 | 2026-05-18 | Research team review incorporated: data_split + train_result_id (C1), robust multi-pattern rebuild (C2), engine return path + build_results_path helper (C3), metric threshold filtering on find() (I1), experiment_id field (I2), fees_included boolean (I3), results show command (I4). See 004-review-response.md for details. |

---

*This specification is self-contained. The platform-developer should build this as a new module in the existing platform, following the patterns from SPEC-000 and SPEC-001.*
