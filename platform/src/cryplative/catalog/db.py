"""SQLite connection, schema initialization, and data classes for the catalog."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity
    strategy_id     TEXT    NOT NULL,
    hypothesis_id   TEXT,
    experiment_id   TEXT,
    run_type        TEXT    NOT NULL,

    -- Data split
    data_split      TEXT    NOT NULL DEFAULT 'FULL',
    train_result_id INTEGER,

    -- Market context
    symbol          TEXT    NOT NULL,
    interval        TEXT    NOT NULL,
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,

    -- Key metrics
    total_return_pct    REAL,
    sharpe_ratio        REAL,
    max_drawdown_pct    REAL,
    win_rate_pct        REAL,
    total_trades        INTEGER,
    profit_factor       REAL,

    -- Fee tracking
    fees_included   INTEGER,

    -- Verdict
    verdict         TEXT,

    -- Reference
    results_file    TEXT    NOT NULL UNIQUE,

    -- Parameters snapshot
    parameters_json TEXT    NOT NULL,

    -- Metadata
    notes           TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strategy_id    ON results(strategy_id);
CREATE INDEX IF NOT EXISTS idx_hypothesis_id  ON results(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_experiment_id  ON results(experiment_id);
CREATE INDEX IF NOT EXISTS idx_symbol         ON results(symbol);
CREATE INDEX IF NOT EXISTS idx_interval       ON results(interval);
CREATE INDEX IF NOT EXISTS idx_verdict        ON results(verdict);
CREATE INDEX IF NOT EXISTS idx_data_split     ON results(data_split);
CREATE UNIQUE INDEX IF NOT EXISTS idx_results_file ON results(results_file);
"""


@dataclass
class CatalogEntry:
    """A single result record from the catalog."""

    id: int
    strategy_id: str
    hypothesis_id: str | None
    experiment_id: str | None
    run_type: str
    data_split: str  # "TRAIN", "TEST", "FULL", "OUT_OF_SAMPLE"
    train_result_id: int | None  # Links TEST to its TRAIN result
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
    fees_included: bool | None  # Whether fees were applied
    verdict: str | None
    results_file: str
    parameters: dict[str, Any]  # parsed from parameters_json
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
    data_split_counts: dict[str, int]


@dataclass
class RebuildResult:
    """Result of a catalog rebuild operation."""

    indexed: int  # Successfully inserted
    skipped_existing: int  # Already in catalog
    skipped_parse_error: int  # Could not parse
    errors: list[str] = field(default_factory=list)  # Parse error details


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database schema. Idempotent — safe to call multiple times."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
