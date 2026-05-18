"""ResultsCatalog — lightweight SQLite catalog for strategy backtest results."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryplative.catalog.db import (
    CatalogEntry,
    CatalogSummary,
    RebuildResult,
    init_db,
)

logger = logging.getLogger(__name__)

VALID_DATA_SPLITS = {"TRAIN", "TEST", "FULL", "OUT_OF_SAMPLE"}
VALID_METRICS = {
    "total_return_pct",
    "sharpe_ratio",
    "max_drawdown_pct",
    "win_rate_pct",
    "total_trades",
    "profit_factor",
}
# Metrics where higher is better (sort descending).
# max_drawdown_pct is stored as negative, so "higher" (closer to 0) is better.
HIGHER_IS_BETTER = {
    "total_return_pct",
    "sharpe_ratio",
    "max_drawdown_pct",
    "win_rate_pct",
    "total_trades",
    "profit_factor",
}

# Filename patterns for rebuild()
# Pattern 1: engine format — timestamps with T00:00:00Z
PATTERN_ENGINE = re.compile(
    r"^(.+)_(\w+)_(\w+)_(\w+)_(\d{4}-\d{2}-\d{2}T[\d:]+Z)_(\d{4}-\d{2}-\d{2}T[\d:]+Z)\.json$"
)
# Pattern 2: old format — bare dates
PATTERN_OLD = re.compile(r"^(.+)_(\w+)_(\w+)_(\w+)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json$")


class ResultsCatalog:
    """Lightweight SQLite catalog for strategy backtest results."""

    def __init__(self, db_path: str = "data/catalog.db") -> None:
        """Open or create the catalog database.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to "data/catalog.db".
                     Creates the file and schema if it doesn't exist.
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        init_db(self._conn)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> CatalogEntry:
        """Convert a database row to a CatalogEntry."""
        d = dict(row)
        d["parameters"] = json.loads(d.pop("parameters_json"))
        d["fees_included"] = None if d["fees_included"] is None else bool(d["fees_included"])
        return CatalogEntry(**d)

    # ── Insert ──────────────────────────────────────────

    def insert(
        self,
        strategy_id: str,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        run_type: str,
        metrics: dict[str, Any],
        results_file: str,
        parameters: dict[str, Any],
        hypothesis_id: str | None = None,
        experiment_id: str | None = None,
        data_split: str = "FULL",
        train_result_id: int | None = None,
        fees_included: bool | None = None,
        verdict: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Insert a result record into the catalog.

        Returns the auto-generated row ID.

        Raises:
            ValueError: If required fields are missing, metrics dict lacks expected
                        keys, or data_split is not a valid value.
            sqlite3.IntegrityError: If results_file already exists (duplicate prevention)
        """
        if data_split not in VALID_DATA_SPLITS:
            raise ValueError(
                f"Invalid data_split '{data_split}'. "
                f"Must be one of: {', '.join(sorted(VALID_DATA_SPLITS))}"
            )

        now = datetime.now(UTC).isoformat()
        fees_val = None if fees_included is None else int(fees_included)

        try:
            cursor = self._conn.execute(
                """
                INSERT INTO results (
                    strategy_id, hypothesis_id, experiment_id, run_type,
                    data_split, train_result_id,
                    symbol, interval, start_date, end_date,
                    total_return_pct, sharpe_ratio, max_drawdown_pct,
                    win_rate_pct, total_trades, profit_factor,
                    fees_included, verdict, results_file,
                    parameters_json, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strategy_id,
                    hypothesis_id,
                    experiment_id,
                    run_type,
                    data_split,
                    train_result_id,
                    symbol,
                    interval,
                    start_date,
                    end_date,
                    metrics.get("total_return_pct"),
                    metrics.get("sharpe_ratio"),
                    metrics.get("max_drawdown_pct"),
                    metrics.get("win_rate_pct"),
                    metrics.get("total_trades"),
                    metrics.get("profit_factor"),
                    fees_val,
                    verdict,
                    results_file,
                    json.dumps(parameters),
                    notes,
                    now,
                ),
            )
            self._conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]
        except sqlite3.IntegrityError:
            self._conn.rollback()
            raise

    def insert_from_strategy_result(
        self,
        result: Any,
        symbol: str,
        interval: str,
        results_file: str,
        hypothesis_id: str | None = None,
        experiment_id: str | None = None,
        data_split: str = "FULL",
        train_result_id: int | None = None,
        fees_included: bool | None = None,
        verdict: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Convenience method: insert directly from a StrategyResult object.

        IMPORTANT: StrategyResult does NOT contain symbol or interval at the
        top level. These come from BacktestConfig. The caller MUST pass them
        explicitly.
        """
        metrics = {
            "total_return_pct": result.metrics.total_return,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "max_drawdown_pct": result.metrics.max_drawdown,
            "win_rate_pct": result.metrics.win_rate,
            "total_trades": result.metrics.total_trades,
            "profit_factor": result.metrics.profit_factor,
        }

        return self.insert(
            strategy_id=result.strategy_id,
            symbol=symbol,
            interval=interval,
            start_date=result.start_date,
            end_date=result.end_date,
            run_type=result.run_type.value,
            metrics=metrics,
            results_file=results_file,
            parameters=result.parameters,
            hypothesis_id=hypothesis_id,
            experiment_id=experiment_id,
            data_split=data_split,
            train_result_id=train_result_id,
            fees_included=fees_included,
            verdict=verdict,
            notes=notes,
        )

    @staticmethod
    def build_results_path(
        strategy_id: str,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
    ) -> str:
        """Build the expected relative results file path matching the engine's save convention.

        Constructs:
        "strategy_results/{id}_{BASE}_{QUOTE}_{interval}_{start}T00:00:00Z_{end}T23:59:59Z.json"
        """
        safe_symbol = symbol.replace("/", "_")
        # Normalize dates to ISO timestamps
        start_ts = start_date if "T" in start_date else f"{start_date}T00:00:00Z"
        end_ts = end_date if "T" in end_date else f"{end_date}T23:59:59Z"
        return f"strategy_results/{strategy_id}_{safe_symbol}_{interval}_{start_ts}_{end_ts}.json"

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
        """Find results matching all given filters (AND logic).

        Returns list of CatalogEntry objects, sorted by created_at desc.
        """
        conditions: list[str] = []
        params: list[Any] = []

        if strategy_id is not None:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)
        if hypothesis_id is not None:
            conditions.append("hypothesis_id = ?")
            params.append(hypothesis_id)
        if experiment_id is not None:
            conditions.append("experiment_id = ?")
            params.append(experiment_id)
        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        if interval is not None:
            conditions.append("interval = ?")
            params.append(interval)
        if verdict is not None:
            conditions.append("verdict = ?")
            params.append(verdict)
        if run_type is not None:
            conditions.append("run_type = ?")
            params.append(run_type)
        if data_split is not None:
            conditions.append("data_split = ?")
            params.append(data_split)
        if min_sharpe is not None:
            conditions.append("sharpe_ratio >= ?")
            params.append(min_sharpe)
        if min_return_pct is not None:
            conditions.append("total_return_pct >= ?")
            params.append(min_return_pct)
        if min_win_rate_pct is not None:
            conditions.append("win_rate_pct >= ?")
            params.append(min_win_rate_pct)
        if min_profit_factor is not None:
            conditions.append("profit_factor >= ?")
            params.append(min_profit_factor)
        if max_drawdown_pct is not None:
            conditions.append("max_drawdown_pct >= ?")
            params.append(max_drawdown_pct)

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM results WHERE {where} ORDER BY created_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def best(
        self,
        metric: str = "sharpe_ratio",
        n: int = 10,
        strategy_id: str | None = None,
        symbol: str | None = None,
        hypothesis_id: str | None = None,
        data_split: str | None = None,
    ) -> list[CatalogEntry]:
        """Get the top N results by a given metric."""
        if metric not in VALID_METRICS:
            raise ValueError(
                f"Invalid metric '{metric}'. Must be one of: {', '.join(sorted(VALID_METRICS))}"
            )

        conditions: list[str] = []
        params: list[Any] = []

        if strategy_id is not None:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)
        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        if hypothesis_id is not None:
            conditions.append("hypothesis_id = ?")
            params.append(hypothesis_id)
        if data_split is not None:
            conditions.append("data_split = ?")
            params.append(data_split)

        where = " AND ".join(conditions) if conditions else "1=1"
        order = "DESC" if metric in HIGHER_IS_BETTER else "ASC"

        sql = f"SELECT * FROM results WHERE {where} ORDER BY {metric} {order} LIMIT ?"
        params.append(n)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def compare_hypotheses(
        self,
        hypothesis_ids: list[str],
        metric: str = "sharpe_ratio",
        data_split: str | None = "TEST",
    ) -> dict[str, list[CatalogEntry]]:
        """Compare results across multiple hypotheses.

        Returns dict mapping hypothesis_id -> list of CatalogEntry,
        sorted by the given metric.
        """
        if metric not in VALID_METRICS:
            raise ValueError(
                f"Invalid metric '{metric}'. Must be one of: {', '.join(sorted(VALID_METRICS))}"
            )

        order = "DESC" if metric in HIGHER_IS_BETTER else "ASC"
        result: dict[str, list[CatalogEntry]] = {}

        for hyp_id in hypothesis_ids:
            conditions = ["hypothesis_id = ?"]
            params: list[Any] = [hyp_id]

            if data_split is not None:
                conditions.append("data_split = ?")
                params.append(data_split)

            where = " AND ".join(conditions)
            sql = f"SELECT * FROM results WHERE {where} ORDER BY {metric} {order}"
            rows = self._conn.execute(sql, params).fetchall()
            result[hyp_id] = [self._row_to_entry(row) for row in rows]

        return result

    def get(self, result_id: int) -> CatalogEntry | None:
        """Get a single result by its row ID. Returns None if not found."""
        row = self._conn.execute("SELECT * FROM results WHERE id = ?", (result_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def summary(self) -> CatalogSummary:
        """Get a high-level overview of the catalog."""
        total = self._conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]

        strategies = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT strategy_id FROM results ORDER BY strategy_id"
            ).fetchall()
        ]
        hypotheses = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT hypothesis_id FROM results "
                "WHERE hypothesis_id IS NOT NULL ORDER BY hypothesis_id"
            ).fetchall()
        ]
        symbols = [
            r[0]
            for r in self._conn.execute(
                "SELECT DISTINCT symbol FROM results ORDER BY symbol"
            ).fetchall()
        ]

        # Verdict counts
        verdict_rows = self._conn.execute(
            "SELECT verdict, COUNT(*) FROM results GROUP BY verdict"
        ).fetchall()
        verdict_counts: dict[str | None, int] = {}
        for v, cnt in verdict_rows:
            verdict_counts[v] = cnt

        # Data split counts
        split_rows = self._conn.execute(
            "SELECT data_split, COUNT(*) FROM results GROUP BY data_split"
        ).fetchall()
        data_split_counts = {r[0]: r[1] for r in split_rows}

        # Best by metric (considering sort direction)
        best_by_metric: dict[str, CatalogEntry] = {}
        for metric in VALID_METRICS:
            order = "DESC" if metric in HIGHER_IS_BETTER else "ASC"
            row = self._conn.execute(
                f"SELECT * FROM results ORDER BY {metric} {order} LIMIT 1"
            ).fetchone()
            if row is not None:
                best_by_metric[metric] = self._row_to_entry(row)

        return CatalogSummary(
            total_results=total,
            unique_strategies=strategies,
            unique_hypotheses=hypotheses,
            unique_symbols=symbols,
            verdict_counts=verdict_counts,
            best_by_metric=best_by_metric,
            data_split_counts=data_split_counts,
        )

    # ── Delete ──────────────────────────────────────────

    def delete(self, result_id: int) -> bool:
        """Delete a result by its row ID. Returns True if deleted."""
        cursor = self._conn.execute("DELETE FROM results WHERE id = ?", (result_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def delete_by_file(self, results_file: str) -> bool:
        """Delete a result by its results_file path. Returns True if deleted."""
        cursor = self._conn.execute("DELETE FROM results WHERE results_file = ?", (results_file,))
        self._conn.commit()
        return cursor.rowcount > 0

    # ── Tag ─────────────────────────────────────────────

    def tag(
        self,
        result_id: int,
        hypothesis_id: str | None = None,
        experiment_id: str | None = None,
        verdict: str | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update metadata fields on an existing result.

        Only updates fields that are passed (not None).
        Returns True if the result was found and updated.
        """
        # Build dynamic SET clause from non-None args
        set_parts: list[str] = []
        params: list[Any] = []

        if hypothesis_id is not None:
            set_parts.append("hypothesis_id = ?")
            params.append(hypothesis_id)
        if experiment_id is not None:
            set_parts.append("experiment_id = ?")
            params.append(experiment_id)
        if verdict is not None:
            set_parts.append("verdict = ?")
            params.append(verdict)
        if notes is not None:
            set_parts.append("notes = ?")
            params.append(notes)

        if not set_parts:
            # Nothing to update — check if result exists
            row = self._conn.execute("SELECT id FROM results WHERE id = ?", (result_id,)).fetchone()
            return row is not None

        params.append(result_id)
        sql = f"UPDATE results SET {', '.join(set_parts)} WHERE id = ?"
        cursor = self._conn.execute(sql, params)
        self._conn.commit()
        return cursor.rowcount > 0

    # ── Rebuild ─────────────────────────────────────────

    def rebuild(self, results_dir: str = "data/strategy_results") -> RebuildResult:
        """Rebuild the catalog by scanning the results directory.

        Reads all JSON files in results_dir, extracts metadata and metrics,
        and inserts them into the catalog. Skips files already indexed
        (by results_file uniqueness).
        """
        indexed = 0
        skipped_existing = 0
        skipped_parse_error = 0
        errors: list[str] = []

        results_path = Path(results_dir)
        if not results_path.exists():
            return RebuildResult(
                indexed=0,
                skipped_existing=0,
                skipped_parse_error=0,
                errors=[f"Results directory not found: {results_dir}"],
            )

        # Get already-indexed files
        existing_files = {
            r[0] for r in self._conn.execute("SELECT results_file FROM results").fetchall()
        }

        for json_file in sorted(results_path.glob("*.json")):
            rel_path = json_file.name  # relative filename within strategy_results/
            full_rel = f"strategy_results/{rel_path}"

            if full_rel in existing_files:
                skipped_existing += 1
                continue

            # Parse filename to extract strategy_id, symbol, interval, dates
            parsed = self._parse_filename(rel_path)

            if parsed is None:
                logger.warning("Skipping non-result file: %s", rel_path)
                continue

            # Read JSON for metrics, parameters, run_type
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                skipped_parse_error += 1
                errors.append(f"{rel_path}: {e}")
                continue

            strategy_id = data.get("strategy_id", parsed["strategy_id"])
            run_type = data.get("run_type", "BACKTEST")
            start_date = data.get("start_date", parsed["start_date"])
            end_date = data.get("end_date", parsed["end_date"])
            parameters = data.get("parameters", {})
            metrics_data = data.get("metrics", {})

            metrics: dict[str, Any] = {
                "total_return_pct": metrics_data.get("total_return"),
                "sharpe_ratio": metrics_data.get("sharpe_ratio"),
                "max_drawdown_pct": metrics_data.get("max_drawdown"),
                "win_rate_pct": metrics_data.get("win_rate"),
                "total_trades": metrics_data.get("total_trades"),
                "profit_factor": metrics_data.get("profit_factor"),
            }

            # Get symbol from parsed filename (or fallback to first trade)
            symbol = parsed["symbol"]
            interval = parsed["interval"]

            if not symbol:
                # Fallback: try to get symbol from first trade's signal
                trades = data.get("trades", [])
                if trades:
                    symbol = trades[0].get("signal", {}).get("symbol", "UNKNOWN")
                else:
                    symbol = "UNKNOWN"

            try:
                self.insert(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    interval=interval,
                    start_date=start_date,
                    end_date=end_date,
                    run_type=run_type,
                    metrics=metrics,
                    results_file=full_rel,
                    parameters=parameters,
                )
                indexed += 1
            except sqlite3.IntegrityError:
                skipped_existing += 1
            except Exception as e:
                skipped_parse_error += 1
                errors.append(f"{rel_path}: {e}")

        return RebuildResult(
            indexed=indexed,
            skipped_existing=skipped_existing,
            skipped_parse_error=skipped_parse_error,
            errors=errors,
        )

    @staticmethod
    def _parse_filename(filename: str) -> dict[str, str] | None:
        """Parse a result filename to extract strategy_id, symbol, interval, dates.

        Returns None if the filename doesn't match any known pattern.
        """
        # Try Pattern 1 (engine format — timestamps with T)
        match = PATTERN_ENGINE.match(filename)
        if match:
            return {
                "strategy_id": match.group(1),
                "symbol": f"{match.group(2)}/{match.group(3)}",
                "interval": match.group(4),
                "start_date": match.group(5),
                "end_date": match.group(6),
            }

        # Try Pattern 2 (old format — bare dates)
        match = PATTERN_OLD.match(filename)
        if match:
            return {
                "strategy_id": match.group(1),
                "symbol": f"{match.group(2)}/{match.group(3)}",
                "interval": match.group(4),
                "start_date": match.group(5),
                "end_date": match.group(6),
            }

        return None

    # ── Clear ───────────────────────────────────────────

    def clear(self) -> int:
        """Delete all records from the catalog. Returns count of deleted rows."""
        count: int = self._conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        self._conn.execute("DELETE FROM results")
        self._conn.commit()
        return count

    # ── Export ──────────────────────────────────────────

    def to_dataframe(
        self,
        strategy_id: str | None = None,
        hypothesis_id: str | None = None,
        symbol: str | None = None,
    ) -> Any:
        """Export filtered results as a pandas DataFrame.

        Raises ImportError if pandas is not available.
        """
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError as err:
            raise ImportError(
                "pandas is required for to_dataframe(). Install it with: pip install pandas"
            ) from err

        entries = self.find(
            strategy_id=strategy_id,
            hypothesis_id=hypothesis_id,
            symbol=symbol,
        )

        if not entries:
            return pd.DataFrame()

        rows = []
        for e in entries:
            rows.append(
                {
                    "id": e.id,
                    "strategy_id": e.strategy_id,
                    "hypothesis_id": e.hypothesis_id,
                    "experiment_id": e.experiment_id,
                    "run_type": e.run_type,
                    "data_split": e.data_split,
                    "train_result_id": e.train_result_id,
                    "symbol": e.symbol,
                    "interval": e.interval,
                    "start_date": e.start_date,
                    "end_date": e.end_date,
                    "total_return_pct": e.total_return_pct,
                    "sharpe_ratio": e.sharpe_ratio,
                    "max_drawdown_pct": e.max_drawdown_pct,
                    "win_rate_pct": e.win_rate_pct,
                    "total_trades": e.total_trades,
                    "profit_factor": e.profit_factor,
                    "fees_included": e.fees_included,
                    "verdict": e.verdict,
                    "results_file": e.results_file,
                    "parameters": e.parameters,
                    "notes": e.notes,
                    "created_at": e.created_at,
                }
            )

        return pd.DataFrame(rows)
