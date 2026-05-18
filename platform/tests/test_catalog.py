"""Tests for the strategy results catalog."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cryplative.catalog import RebuildResult, ResultsCatalog
from cryplative.core.models import RunContext, StrategyMetrics, StrategyResult


@pytest.fixture
def catalog(tmp_path: Path) -> ResultsCatalog:
    """Create a catalog with a temporary database."""
    db_path = str(tmp_path / "test_catalog.db")
    cat = ResultsCatalog(db_path=db_path)
    yield cat
    cat.close()


@pytest.fixture
def sample_metrics() -> dict:
    """Standard metrics dict for testing."""
    return {
        "total_return_pct": 2.56,
        "sharpe_ratio": 2.57,
        "max_drawdown_pct": -0.42,
        "win_rate_pct": 83.33,
        "total_trades": 6,
        "profit_factor": 17.79,
    }


@pytest.fixture
def sample_entry(catalog: ResultsCatalog, sample_metrics: dict) -> int:
    """Insert a sample entry and return its ID."""
    return catalog.insert(
        strategy_id="h2_rsi_divergence_trend",
        symbol="BTC/USDT",
        interval="4h",
        start_date="2024-01-01T00:00:00Z",
        end_date="2025-08-31T23:59:59Z",
        run_type="BACKTEST",
        metrics=sample_metrics,
        results_file="strategy_results/h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json",
        parameters={"rsi_period": 14, "stop_loss_pct": 0.05},
        hypothesis_id="H2",
        experiment_id="sweep_20260518",
        data_split="TRAIN",
        fees_included=True,
        verdict="PASS",
        notes="Strong on BTC",
    )


def _make_strategy_result(
    strategy_id: str = "sma_crossover",
    total_return: float = 12.58,
    sharpe: float = 0.22,
    max_dd: float = -61.1,
    win_rate: float = 42.11,
    total_trades: int = 19,
    profit_factor: float = 1.1,
) -> StrategyResult:
    """Create a StrategyResult for testing."""
    return StrategyResult(
        strategy_id=strategy_id,
        run_type=RunContext.BACKTEST,
        start_date="2025-01-01",
        end_date="2025-01-31",
        parameters={"fast_period": 10, "slow_period": 20},
        trades=[],
        metrics=StrategyMetrics(
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=total_trades,
            profit_factor=profit_factor,
        ),
        created_at=datetime.now(UTC).isoformat(),
    )


# ── Schema Tests ────────────────────────────────────────────


class TestSchema:
    """Tests for schema creation."""

    def test_schema_creates_on_fresh_db(self, tmp_path: Path) -> None:
        """Fresh database should have results table and indexes."""
        db_path = str(tmp_path / "fresh.db")
        cat = ResultsCatalog(db_path=db_path)
        # Check table exists
        rows = cat._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='results'"
        ).fetchall()
        assert len(rows) == 1
        cat.close()

    def test_idempotent_schema_creation(self, tmp_path: Path) -> None:
        """Creating schema twice should not error."""
        db_path = str(tmp_path / "idempotent.db")
        cat = ResultsCatalog(db_path=db_path)
        # Re-init schema
        from cryplative.catalog.db import init_db

        init_db(cat._conn)  # Should not raise
        cat.close()

    def test_unique_results_file_constraint(
        self, catalog: ResultsCatalog, sample_metrics: dict
    ) -> None:
        """Duplicate results_file should raise IntegrityError."""
        catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/test.json",
            parameters={},
        )
        with pytest.raises(sqlite3.IntegrityError):
            catalog.insert(
                strategy_id="sma",
                symbol="ETH/USDT",
                interval="4h",
                start_date="2025-01-01",
                end_date="2025-01-31",
                run_type="BACKTEST",
                metrics=sample_metrics,
                results_file="strategy_results/test.json",  # same file
                parameters={},
            )


# ── Insert Tests ────────────────────────────────────────────


class TestInsert:
    """Tests for catalog insert operations."""

    def test_insert_stores_all_fields(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """insert() should store all fields correctly."""
        row_id = catalog.insert(
            strategy_id="h2_rsi_divergence_trend",
            symbol="BTC/USDT",
            interval="4h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2025-08-31T23:59:59Z",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/test_result.json",
            parameters={"rsi_period": 14, "stop_loss_pct": 0.05},
            hypothesis_id="H2",
            experiment_id="sweep_20260518",
            data_split="TRAIN",
            train_result_id=None,
            fees_included=True,
            verdict="PASS",
            notes="Strong on BTC",
        )

        entry = catalog.get(row_id)
        assert entry is not None
        assert entry.id == row_id
        assert entry.strategy_id == "h2_rsi_divergence_trend"
        assert entry.hypothesis_id == "H2"
        assert entry.experiment_id == "sweep_20260518"
        assert entry.run_type == "BACKTEST"
        assert entry.data_split == "TRAIN"
        assert entry.train_result_id is None
        assert entry.symbol == "BTC/USDT"
        assert entry.interval == "4h"
        assert entry.start_date == "2024-01-01T00:00:00Z"
        assert entry.end_date == "2025-08-31T23:59:59Z"
        assert entry.total_return_pct == 2.56
        assert entry.sharpe_ratio == 2.57
        assert entry.max_drawdown_pct == -0.42
        assert entry.win_rate_pct == 83.33
        assert entry.total_trades == 6
        assert entry.profit_factor == 17.79
        assert entry.fees_included is True
        assert entry.verdict == "PASS"
        assert entry.results_file == "strategy_results/test_result.json"
        assert entry.parameters == {"rsi_period": 14, "stop_loss_pct": 0.05}
        assert entry.notes == "Strong on BTC"
        assert entry.created_at is not None

    def test_insert_with_defaults(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """insert() with minimal args should use defaults."""
        row_id = catalog.insert(
            strategy_id="sma_crossover",
            symbol="ETH/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/sma_minimal.json",
            parameters={"fast": 10},
        )

        entry = catalog.get(row_id)
        assert entry is not None
        assert entry.hypothesis_id is None
        assert entry.experiment_id is None
        assert entry.data_split == "FULL"  # default
        assert entry.train_result_id is None
        assert entry.fees_included is None
        assert entry.verdict is None
        assert entry.notes is None

    def test_insert_test_with_train_result_id(
        self, catalog: ResultsCatalog, sample_metrics: dict
    ) -> None:
        """insert() with data_split TEST and train_result_id links correctly."""
        train_id = catalog.insert(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01",
            end_date="2025-08-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/train.json",
            parameters={},
            data_split="TRAIN",
        )

        test_id = catalog.insert(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-09-01",
            end_date="2026-04-30",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/test.json",
            parameters={},
            data_split="TEST",
            train_result_id=train_id,
        )

        test_entry = catalog.get(test_id)
        assert test_entry is not None
        assert test_entry.data_split == "TEST"
        assert test_entry.train_result_id == train_id

    def test_insert_invalid_data_split(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """insert() with invalid data_split should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid data_split"):
            catalog.insert(
                strategy_id="sma",
                symbol="BTC/USDT",
                interval="1h",
                start_date="2025-01-01",
                end_date="2025-01-31",
                run_type="BACKTEST",
                metrics=sample_metrics,
                results_file="strategy_results/bad_split.json",
                parameters={},
                data_split="INVALID",
            )

    def test_insert_returns_row_id(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """insert() should return an integer row ID."""
        row_id = catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/id_test.json",
            parameters={},
        )
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_insert_fees_included_false(
        self, catalog: ResultsCatalog, sample_metrics: dict
    ) -> None:
        """insert() with fees_included=False stores correctly."""
        row_id = catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/no_fees.json",
            parameters={},
            fees_included=False,
        )
        entry = catalog.get(row_id)
        assert entry is not None
        assert entry.fees_included is False


class TestInsertFromStrategyResult:
    """Tests for insert_from_strategy_result method."""

    def test_inserts_from_strategy_result(self, catalog: ResultsCatalog) -> None:
        """insert_from_strategy_result() extracts fields correctly."""
        result = _make_strategy_result()
        row_id = catalog.insert_from_strategy_result(
            result=result,
            symbol="BTC/USDT",
            interval="1h",
            results_file="strategy_results/sma_result.json",
            hypothesis_id="H3",
            data_split="TEST",
            fees_included=True,
        )

        entry = catalog.get(row_id)
        assert entry is not None
        assert entry.strategy_id == "sma_crossover"
        assert entry.symbol == "BTC/USDT"
        assert entry.interval == "1h"
        assert entry.start_date == "2025-01-01"
        assert entry.end_date == "2025-01-31"
        assert entry.run_type == "BACKTEST"
        assert entry.total_return_pct == 12.58
        assert entry.sharpe_ratio == 0.22
        assert entry.max_drawdown_pct == -61.1
        assert entry.win_rate_pct == 42.11
        assert entry.total_trades == 19
        assert entry.profit_factor == 1.1
        assert entry.parameters == {"fast_period": 10, "slow_period": 20}
        assert entry.hypothesis_id == "H3"
        assert entry.data_split == "TEST"
        assert entry.fees_included is True


class TestBuildResultsPath:
    """Tests for build_results_path static method."""

    def test_builds_path_with_bare_dates(self) -> None:
        """build_results_path with bare dates should append timestamps."""
        path = ResultsCatalog.build_results_path(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="4h",
            start_date="2024-01-01",
            end_date="2025-08-31",
        )
        assert path == (
            "strategy_results/sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json"
        )

    def test_builds_path_with_timestamps(self) -> None:
        """build_results_path with ISO timestamps should use them as-is."""
        path = ResultsCatalog.build_results_path(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="4h",
            start_date="2024-01-01T00:00:00Z",
            end_date="2025-08-31T23:59:59Z",
        )
        assert path == (
            "strategy_results/sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json"
        )

    def test_builds_path_converts_slash_in_symbol(self) -> None:
        """build_results_path should convert / to _ in symbol."""
        path = ResultsCatalog.build_results_path(
            strategy_id="rsi",
            symbol="ETH/USDT",
            interval="1d",
            start_date="2024-01-01",
            end_date="2025-01-01",
        )
        assert "ETH_USDT" in path
        assert "ETH/USDT" not in path


# ── Query Tests ─────────────────────────────────────────────


class TestFind:
    """Tests for the find() query method."""

    def _insert_sample_data(self, catalog: ResultsCatalog) -> None:
        """Insert a variety of entries for testing find()."""
        metrics_btc = {
            "total_return_pct": 5.0,
            "sharpe_ratio": 1.5,
            "max_drawdown_pct": -2.0,
            "win_rate_pct": 60.0,
            "total_trades": 10,
            "profit_factor": 2.0,
        }
        metrics_eth = {
            "total_return_pct": -1.2,
            "sharpe_ratio": 0.43,
            "max_drawdown_pct": -10.0,
            "win_rate_pct": 40.0,
            "total_trades": 5,
            "profit_factor": 0.8,
        }
        metrics_sol = {
            "total_return_pct": 8.12,
            "sharpe_ratio": 1.89,
            "max_drawdown_pct": -1.5,
            "win_rate_pct": 75.0,
            "total_trades": 8,
            "profit_factor": 3.5,
        }

        catalog.insert(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2024-01-01",
            end_date="2025-01-01",
            run_type="BACKTEST",
            metrics=metrics_btc,
            results_file="strategy_results/sma_btc_train.json",
            parameters={},
            hypothesis_id="H1",
            experiment_id="sweep_20260518",
            data_split="TRAIN",
        )
        catalog.insert(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2026-01-01",
            run_type="BACKTEST",
            metrics=metrics_btc,
            results_file="strategy_results/sma_btc_test.json",
            parameters={},
            hypothesis_id="H1",
            experiment_id="sweep_20260518",
            data_split="TEST",
            verdict="PASS",
        )
        catalog.insert(
            strategy_id="sma_crossover",
            symbol="ETH/USDT",
            interval="4h",
            start_date="2024-01-01",
            end_date="2025-01-01",
            run_type="BACKTEST",
            metrics=metrics_eth,
            results_file="strategy_results/sma_eth_full.json",
            parameters={},
            data_split="FULL",
            verdict="FAIL",
        )
        catalog.insert(
            strategy_id="h2_rsi_divergence_trend",
            symbol="BTC/USDT",
            interval="4h",
            start_date="2024-01-01",
            end_date="2025-01-01",
            run_type="BACKTEST",
            metrics=metrics_sol,
            results_file="strategy_results/h2_btc_train.json",
            parameters={},
            hypothesis_id="H2",
            data_split="TRAIN",
        )
        catalog.insert(
            strategy_id="h2_rsi_divergence_trend",
            symbol="BTC/USDT",
            interval="4h",
            start_date="2025-01-01",
            end_date="2026-01-01",
            run_type="BACKTEST",
            metrics=metrics_sol,
            results_file="strategy_results/h2_btc_test.json",
            parameters={},
            hypothesis_id="H2",
            data_split="TEST",
            verdict="PASS",
        )

    def test_find_no_filters_returns_all(self, catalog: ResultsCatalog) -> None:
        """find() with no filters returns all results."""
        self._insert_sample_data(catalog)
        results = catalog.find()
        assert len(results) == 5

    def test_find_by_symbol(self, catalog: ResultsCatalog) -> None:
        """find(symbol=) returns only matching results."""
        self._insert_sample_data(catalog)
        results = catalog.find(symbol="BTC/USDT")
        assert len(results) == 4
        assert all(r.symbol == "BTC/USDT" for r in results)

    def test_find_by_strategy_and_interval(self, catalog: ResultsCatalog) -> None:
        """find() with multiple filters applies AND logic."""
        self._insert_sample_data(catalog)
        results = catalog.find(strategy_id="sma_crossover", interval="1h")
        assert len(results) == 2
        assert all(r.strategy_id == "sma_crossover" for r in results)
        assert all(r.interval == "1h" for r in results)

    def test_find_no_matches(self, catalog: ResultsCatalog) -> None:
        """find() with no matches returns empty list."""
        self._insert_sample_data(catalog)
        results = catalog.find(symbol="DOGE/USDT")
        assert results == []

    def test_find_by_data_split(self, catalog: ResultsCatalog) -> None:
        """find(data_split=) returns only matching split."""
        self._insert_sample_data(catalog)
        results = catalog.find(data_split="TEST")
        assert len(results) == 2
        assert all(r.data_split == "TEST" for r in results)

    def test_find_by_experiment(self, catalog: ResultsCatalog) -> None:
        """find(experiment_id=) returns only matching experiment."""
        self._insert_sample_data(catalog)
        results = catalog.find(experiment_id="sweep_20260518")
        assert len(results) == 2
        assert all(r.experiment_id == "sweep_20260518" for r in results)

    def test_find_by_verdict(self, catalog: ResultsCatalog) -> None:
        """find(verdict=) returns only matching verdict."""
        self._insert_sample_data(catalog)
        results = catalog.find(verdict="PASS")
        assert len(results) == 2
        assert all(r.verdict == "PASS" for r in results)

    def test_find_min_sharpe(self, catalog: ResultsCatalog) -> None:
        """find(min_sharpe=) filters by metric threshold."""
        self._insert_sample_data(catalog)
        results = catalog.find(min_sharpe=1.0)
        assert all(r.sharpe_ratio is not None and r.sharpe_ratio >= 1.0 for r in results)

    def test_find_min_return_combined_with_data_split(self, catalog: ResultsCatalog) -> None:
        """find() combines threshold with filter."""
        self._insert_sample_data(catalog)
        results = catalog.find(data_split="TEST", min_return_pct=5.0)
        assert len(results) >= 1
        assert all(r.data_split == "TEST" for r in results)
        assert all(r.total_return_pct is not None and r.total_return_pct >= 5.0 for r in results)

    def test_find_sorted_by_created_at_desc(self, catalog: ResultsCatalog) -> None:
        """find() returns results sorted by created_at descending."""
        self._insert_sample_data(catalog)
        results = catalog.find()
        # Results should be newest first
        for i in range(len(results) - 1):
            assert results[i].created_at >= results[i + 1].created_at

    def test_find_min_profit_factor(self, catalog: ResultsCatalog) -> None:
        """find(min_profit_factor=) filters correctly."""
        self._insert_sample_data(catalog)
        results = catalog.find(min_profit_factor=2.0)
        assert all(r.profit_factor is not None and r.profit_factor >= 2.0 for r in results)

    def test_find_max_drawdown_pct(self, catalog: ResultsCatalog) -> None:
        """find(max_drawdown_pct=) filters by max drawdown (>= means no worse than)."""
        self._insert_sample_data(catalog)
        results = catalog.find(max_drawdown_pct=-3.0)
        assert all(r.max_drawdown_pct is not None and r.max_drawdown_pct >= -3.0 for r in results)


class TestBest:
    """Tests for the best() method."""

    def _insert_varied_data(self, catalog: ResultsCatalog) -> None:
        """Insert entries with varied metrics for best() testing."""
        metrics_list = [
            {
                "total_return_pct": 2.56,
                "sharpe_ratio": 2.57,
                "max_drawdown_pct": -0.42,
                "win_rate_pct": 83.33,
                "total_trades": 6,
                "profit_factor": 17.79,
            },
            {
                "total_return_pct": 8.12,
                "sharpe_ratio": 1.89,
                "max_drawdown_pct": -1.5,
                "win_rate_pct": 75.0,
                "total_trades": 8,
                "profit_factor": 3.5,
            },
            {
                "total_return_pct": -1.2,
                "sharpe_ratio": 0.43,
                "max_drawdown_pct": -10.0,
                "win_rate_pct": 40.0,
                "total_trades": 5,
                "profit_factor": 0.8,
            },
            {
                "total_return_pct": 3.41,
                "sharpe_ratio": 1.22,
                "max_drawdown_pct": -2.5,
                "win_rate_pct": 60.0,
                "total_trades": 10,
                "profit_factor": 2.0,
            },
            {
                "total_return_pct": 5.67,
                "sharpe_ratio": 1.11,
                "max_drawdown_pct": -3.0,
                "win_rate_pct": 55.0,
                "total_trades": 7,
                "profit_factor": 1.5,
            },
        ]
        symbols = ["BTC/USDT", "BTC/USDT", "ETH/USDT", "BTC/USDT", "SOL/USDT"]
        splits = ["TEST", "TEST", "FULL", "TEST", "TEST"]
        hyps = ["H2", "H5", None, "H2", "H5"]
        strategies = ["h2_rsi", "h5_macd", "sma", "sma", "h5_macd"]

        for i, (m, sym, sp, hyp, sid) in enumerate(
            zip(metrics_list, symbols, splits, hyps, strategies, strict=True)
        ):
            catalog.insert(
                strategy_id=sid,
                symbol=sym,
                interval="4h",
                start_date="2024-01-01",
                end_date="2025-01-01",
                run_type="BACKTEST",
                metrics=m,
                results_file=f"strategy_results/entry_{i}.json",
                parameters={},
                hypothesis_id=hyp,
                data_split=sp,
            )

    def test_best_by_sharpe(self, catalog: ResultsCatalog) -> None:
        """best(metric='sharpe_ratio') returns top results sorted desc."""
        self._insert_varied_data(catalog)
        results = catalog.best(metric="sharpe_ratio", n=3)
        assert len(results) == 3
        assert results[0].sharpe_ratio >= results[1].sharpe_ratio
        assert results[1].sharpe_ratio >= results[2].sharpe_ratio

    def test_best_by_drawdown_asc(self, catalog: ResultsCatalog) -> None:
        """best(metric='max_drawdown_pct') sorts ascending (least drawdown first)."""
        self._insert_varied_data(catalog)
        results = catalog.best(metric="max_drawdown_pct", n=3)
        assert len(results) == 3
        # Less negative = better
        assert results[0].max_drawdown_pct is not None
        assert results[1].max_drawdown_pct is not None
        assert results[0].max_drawdown_pct >= results[1].max_drawdown_pct

    def test_best_with_data_split_filter(self, catalog: ResultsCatalog) -> None:
        """best(data_split=) only returns results from that split."""
        self._insert_varied_data(catalog)
        results = catalog.best(metric="sharpe_ratio", n=10, data_split="TEST")
        assert all(r.data_split == "TEST" for r in results)

    def test_best_with_strategy_filter(self, catalog: ResultsCatalog) -> None:
        """best(strategy_id=) only returns results from that strategy."""
        self._insert_varied_data(catalog)
        results = catalog.best(metric="sharpe_ratio", n=10, strategy_id="sma")
        assert all(r.strategy_id == "sma" for r in results)

    def test_best_with_symbol_filter(self, catalog: ResultsCatalog) -> None:
        """best(symbol=) only returns results from that symbol."""
        self._insert_varied_data(catalog)
        results = catalog.best(metric="sharpe_ratio", n=10, symbol="BTC/USDT")
        assert all(r.symbol == "BTC/USDT" for r in results)

    def test_best_invalid_metric(self, catalog: ResultsCatalog) -> None:
        """best() with invalid metric raises ValueError."""
        with pytest.raises(ValueError, match="Invalid metric"):
            catalog.best(metric="invalid_metric")


class TestCompareHypotheses:
    """Tests for compare_hypotheses method."""

    def _insert_hypothesis_data(self, catalog: ResultsCatalog) -> None:
        """Insert data for H2 and H5 hypotheses."""
        metrics_h2 = [
            {
                "total_return_pct": 2.56,
                "sharpe_ratio": 2.57,
                "max_drawdown_pct": -0.42,
                "win_rate_pct": 83.33,
                "total_trades": 6,
                "profit_factor": 17.79,
            },
            {
                "total_return_pct": 1.89,
                "sharpe_ratio": 1.94,
                "max_drawdown_pct": -1.0,
                "win_rate_pct": 70.0,
                "total_trades": 4,
                "profit_factor": 5.0,
            },
        ]
        metrics_h5 = [
            {
                "total_return_pct": 8.12,
                "sharpe_ratio": 1.89,
                "max_drawdown_pct": -1.5,
                "win_rate_pct": 75.0,
                "total_trades": 8,
                "profit_factor": 3.5,
            },
            {
                "total_return_pct": 5.67,
                "sharpe_ratio": 1.11,
                "max_drawdown_pct": -3.0,
                "win_rate_pct": 55.0,
                "total_trades": 7,
                "profit_factor": 1.5,
            },
        ]

        for i, m in enumerate(metrics_h2):
            catalog.insert(
                strategy_id="h2_rsi",
                symbol="BTC/USDT",
                interval="4h",
                start_date="2024-01-01",
                end_date="2025-01-01",
                run_type="BACKTEST",
                metrics=m,
                results_file=f"strategy_results/h2_test_{i}.json",
                parameters={},
                hypothesis_id="H2",
                data_split="TEST",
                verdict="PASS",
            )
        for i, m in enumerate(metrics_h5):
            catalog.insert(
                strategy_id="h5_macd",
                symbol="BTC/USDT",
                interval="4h",
                start_date="2024-01-01",
                end_date="2025-01-01",
                run_type="BACKTEST",
                metrics=m,
                results_file=f"strategy_results/h5_test_{i}.json",
                parameters={},
                hypothesis_id="H5",
                data_split="TEST",
                verdict="PASS",
            )
        # Also add some TRAIN entries for H2
        catalog.insert(
            strategy_id="h2_rsi",
            symbol="BTC/USDT",
            interval="4h",
            start_date="2024-01-01",
            end_date="2025-01-01",
            run_type="BACKTEST",
            metrics=metrics_h2[0],
            results_file="strategy_results/h2_train.json",
            parameters={},
            hypothesis_id="H2",
            data_split="TRAIN",
        )

    def test_compare_hypotheses_default_test_only(self, catalog: ResultsCatalog) -> None:
        """compare_hypotheses() defaults to TEST data_split."""
        self._insert_hypothesis_data(catalog)
        result = catalog.compare_hypotheses(["H2", "H5"])
        assert "H2" in result
        assert "H5" in result
        # H2 has 2 TEST entries, H5 has 2 TEST entries
        assert len(result["H2"]) == 2
        assert len(result["H5"]) == 2
        # All should be TEST
        assert all(r.data_split == "TEST" for r in result["H2"])
        assert all(r.data_split == "TEST" for r in result["H5"])

    def test_compare_hypotheses_all_splits(self, catalog: ResultsCatalog) -> None:
        """compare_hypotheses(data_split=None) includes all splits."""
        self._insert_hypothesis_data(catalog)
        result = catalog.compare_hypotheses(["H2"], data_split=None)
        # H2 has 2 TEST + 1 TRAIN = 3
        assert len(result["H2"]) == 3

    def test_compare_hypotheses_sorted_by_metric(self, catalog: ResultsCatalog) -> None:
        """compare_hypotheses() sorts by metric desc for higher-is-better."""
        self._insert_hypothesis_data(catalog)
        result = catalog.compare_hypotheses(["H2"])
        h2_entries = result["H2"]
        assert h2_entries[0].sharpe_ratio >= h2_entries[1].sharpe_ratio

    def test_compare_hypotheses_invalid_metric(self, catalog: ResultsCatalog) -> None:
        """compare_hypotheses() with invalid metric raises ValueError."""
        with pytest.raises(ValueError, match="Invalid metric"):
            catalog.compare_hypotheses(["H2"], metric="bad_metric")


class TestGet:
    """Tests for get() method."""

    def test_get_existing(self, catalog: ResultsCatalog, sample_entry: int) -> None:
        """get() returns the correct entry."""
        entry = catalog.get(sample_entry)
        assert entry is not None
        assert entry.id == sample_entry
        assert entry.strategy_id == "h2_rsi_divergence_trend"

    def test_get_nonexistent(self, catalog: ResultsCatalog) -> None:
        """get() returns None for non-existent ID."""
        assert catalog.get(999) is None


class TestSummary:
    """Tests for summary() method."""

    def _insert_diverse_data(self, catalog: ResultsCatalog) -> None:
        """Insert diverse entries for summary testing."""
        data = [
            (
                "sma_crossover",
                "BTC/USDT",
                "FULL",
                None,
                "PASS",
                {
                    "total_return_pct": 5.0,
                    "sharpe_ratio": 1.5,
                    "max_drawdown_pct": -2.0,
                    "win_rate_pct": 60.0,
                    "total_trades": 10,
                    "profit_factor": 2.0,
                },
            ),
            (
                "sma_crossover",
                "ETH/USDT",
                "TRAIN",
                "H1",
                "FAIL",
                {
                    "total_return_pct": -1.0,
                    "sharpe_ratio": 0.5,
                    "max_drawdown_pct": -8.0,
                    "win_rate_pct": 40.0,
                    "total_trades": 5,
                    "profit_factor": 0.8,
                },
            ),
            (
                "h2_rsi",
                "BTC/USDT",
                "TEST",
                "H2",
                "PASS",
                {
                    "total_return_pct": 8.0,
                    "sharpe_ratio": 2.0,
                    "max_drawdown_pct": -0.5,
                    "win_rate_pct": 80.0,
                    "total_trades": 6,
                    "profit_factor": 5.0,
                },
            ),
            (
                "h2_rsi",
                "ETH/USDT",
                "TEST",
                "H2",
                "PASS",
                {
                    "total_return_pct": 3.0,
                    "sharpe_ratio": 1.5,
                    "max_drawdown_pct": -1.0,
                    "win_rate_pct": 70.0,
                    "total_trades": 4,
                    "profit_factor": 3.0,
                },
            ),
            (
                "h5_macd",
                "SOL/USDT",
                "FULL",
                "H5",
                "MARGINAL",
                {
                    "total_return_pct": 1.0,
                    "sharpe_ratio": 0.9,
                    "max_drawdown_pct": -3.0,
                    "win_rate_pct": 50.0,
                    "total_trades": 3,
                    "profit_factor": 1.2,
                },
            ),
        ]
        for i, (sid, sym, sp, hyp, verd, m) in enumerate(data):
            catalog.insert(
                strategy_id=sid,
                symbol=sym,
                interval="4h",
                start_date="2024-01-01",
                end_date="2025-01-01",
                run_type="BACKTEST",
                metrics=m,
                results_file=f"strategy_results/summary_{i}.json",
                parameters={},
                hypothesis_id=hyp,
                data_split=sp,
                verdict=verd,
            )

    def test_summary_total_results(self, catalog: ResultsCatalog) -> None:
        """summary() returns correct total count."""
        self._insert_diverse_data(catalog)
        s = catalog.summary()
        assert s.total_results == 5

    def test_summary_unique_strategies(self, catalog: ResultsCatalog) -> None:
        """summary() lists unique strategies."""
        self._insert_diverse_data(catalog)
        s = catalog.summary()
        assert set(s.unique_strategies) == {"sma_crossover", "h2_rsi", "h5_macd"}

    def test_summary_unique_hypotheses(self, catalog: ResultsCatalog) -> None:
        """summary() lists unique hypotheses (excludes None)."""
        self._insert_diverse_data(catalog)
        s = catalog.summary()
        assert set(s.unique_hypotheses) == {"H1", "H2", "H5"}

    def test_summary_unique_symbols(self, catalog: ResultsCatalog) -> None:
        """summary() lists unique symbols."""
        self._insert_diverse_data(catalog)
        s = catalog.summary()
        assert set(s.unique_symbols) == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}

    def test_summary_verdict_counts(self, catalog: ResultsCatalog) -> None:
        """summary() returns correct verdict counts."""
        self._insert_diverse_data(catalog)
        s = catalog.summary()
        assert s.verdict_counts["PASS"] == 3
        assert s.verdict_counts["FAIL"] == 1
        assert s.verdict_counts["MARGINAL"] == 1

    def test_summary_data_split_counts(self, catalog: ResultsCatalog) -> None:
        """summary() returns correct data split counts."""
        self._insert_diverse_data(catalog)
        s = catalog.summary()
        assert s.data_split_counts["FULL"] == 2
        assert s.data_split_counts["TRAIN"] == 1
        assert s.data_split_counts["TEST"] == 2

    def test_summary_best_by_metric(self, catalog: ResultsCatalog) -> None:
        """summary() returns best entry for each metric."""
        self._insert_diverse_data(catalog)
        s = catalog.summary()
        assert "sharpe_ratio" in s.best_by_metric
        assert s.best_by_metric["sharpe_ratio"].sharpe_ratio == 2.0
        assert "total_return_pct" in s.best_by_metric
        assert s.best_by_metric["total_return_pct"].total_return_pct == 8.0

    def test_summary_empty_catalog(self, catalog: ResultsCatalog) -> None:
        """summary() on empty catalog returns zeros."""
        s = catalog.summary()
        assert s.total_results == 0
        assert s.unique_strategies == []
        assert s.unique_hypotheses == []
        assert s.unique_symbols == []
        assert s.best_by_metric == {}


# ── Delete Tests ────────────────────────────────────────────


class TestDelete:
    """Tests for delete operations."""

    def test_delete_by_id(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """delete() removes a record by ID."""
        row_id = catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/to_delete.json",
            parameters={},
        )
        assert catalog.get(row_id) is not None
        result = catalog.delete(row_id)
        assert result is True
        assert catalog.get(row_id) is None

    def test_delete_nonexistent(self, catalog: ResultsCatalog) -> None:
        """delete() returns False for non-existent ID."""
        result = catalog.delete(999)
        assert result is False

    def test_delete_by_file(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """delete_by_file() removes a record by file path."""
        catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/by_file.json",
            parameters={},
        )
        result = catalog.delete_by_file("strategy_results/by_file.json")
        assert result is True

    def test_delete_by_file_nonexistent(self, catalog: ResultsCatalog) -> None:
        """delete_by_file() returns False for non-existent file."""
        result = catalog.delete_by_file("nonexistent.json")
        assert result is False

    def test_clear(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """clear() removes all records."""
        for i in range(5):
            catalog.insert(
                strategy_id="sma",
                symbol="BTC/USDT",
                interval="1h",
                start_date="2025-01-01",
                end_date="2025-01-31",
                run_type="BACKTEST",
                metrics=sample_metrics,
                results_file=f"strategy_results/clear_{i}.json",
                parameters={},
            )
        count = catalog.clear()
        assert count == 5
        assert catalog.find() == []


# ── Tag Tests ───────────────────────────────────────────────


class TestTag:
    """Tests for tag() method."""

    def test_tag_hypothesis(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """tag() updates hypothesis_id."""
        row_id = catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/tag_test.json",
            parameters={},
        )
        result = catalog.tag(row_id, hypothesis_id="H3")
        assert result is True
        entry = catalog.get(row_id)
        assert entry is not None
        assert entry.hypothesis_id == "H3"

    def test_tag_verdict_and_notes(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """tag() updates multiple fields at once."""
        row_id = catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/tag_multi.json",
            parameters={},
        )
        result = catalog.tag(row_id, verdict="PASS", notes="Strong on BTC")
        assert result is True
        entry = catalog.get(row_id)
        assert entry is not None
        assert entry.verdict == "PASS"
        assert entry.notes == "Strong on BTC"

    def test_tag_experiment(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """tag() updates experiment_id."""
        row_id = catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/tag_exp.json",
            parameters={},
        )
        result = catalog.tag(row_id, experiment_id="sweep_20260518")
        assert result is True
        entry = catalog.get(row_id)
        assert entry is not None
        assert entry.experiment_id == "sweep_20260518"

    def test_tag_nonexistent(self, catalog: ResultsCatalog) -> None:
        """tag() returns False for non-existent ID."""
        result = catalog.tag(999, hypothesis_id="H3")
        assert result is False

    def test_tag_no_fields_returns_true_if_exists(
        self, catalog: ResultsCatalog, sample_metrics: dict
    ) -> None:
        """tag() with no fields returns True if result exists."""
        row_id = catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/tag_empty.json",
            parameters={},
        )
        result = catalog.tag(row_id)
        assert result is True

    def test_tag_no_fields_returns_false_if_not_exists(self, catalog: ResultsCatalog) -> None:
        """tag() with no fields returns False if result doesn't exist."""
        result = catalog.tag(9999)
        assert result is False


# ── Rebuild Tests ───────────────────────────────────────────


class TestRebuild:
    """Tests for rebuild() method."""

    def _create_result_json(
        self,
        results_dir: Path,
        filename: str,
        strategy_id: str = "sma_crossover",
        total_return: float = 5.0,
        sharpe: float = 1.5,
        max_dd: float = -2.0,
        win_rate: float = 60.0,
        total_trades: int = 10,
        profit_factor: float = 2.0,
    ) -> Path:
        """Create a JSON result file in the results directory."""
        data = {
            "strategy_id": strategy_id,
            "run_type": "BACKTEST",
            "start_date": "2024-01-01",
            "end_date": "2025-01-01",
            "parameters": {"fast": 10},
            "trades": [],
            "metrics": {
                "total_return": total_return,
                "sharpe_ratio": sharpe,
                "max_drawdown": max_dd,
                "win_rate": win_rate,
                "total_trades": total_trades,
                "profit_factor": profit_factor,
            },
            "created_at": "2026-01-01T00:00:00Z",
        }
        filepath = results_dir / filename
        filepath.write_text(json.dumps(data), encoding="utf-8")
        return filepath

    def test_rebuild_scans_directory(self, tmp_path: Path) -> None:
        """rebuild() scans directory and inserts new files."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        # Engine format file
        self._create_result_json(
            results_dir,
            "sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-01-01T23:59:59Z.json",
            strategy_id="sma_crossover",
        )

        r = cat.rebuild(str(results_dir))
        assert r.indexed == 1
        assert r.skipped_existing == 0
        assert r.skipped_parse_error == 0
        cat.close()

    def test_rebuild_engine_format_filenames(self, tmp_path: Path) -> None:
        """rebuild() correctly parses engine format filenames."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        self._create_result_json(
            results_dir,
            "h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json",
            strategy_id="h2_rsi_divergence_trend",
        )

        r = cat.rebuild(str(results_dir))
        assert r.indexed == 1

        entries = cat.find()
        assert len(entries) == 1
        assert entries[0].symbol == "BTC/USDT"
        assert entries[0].interval == "4h"
        assert entries[0].strategy_id == "h2_rsi_divergence_trend"
        cat.close()

    def test_rebuild_old_format_filenames(self, tmp_path: Path) -> None:
        """rebuild() correctly parses old format filenames."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        self._create_result_json(
            results_dir,
            "sma_crossover_BTC_USDT_1h_2025-01-01_2025-01-31.json",
            strategy_id="sma_crossover",
        )

        r = cat.rebuild(str(results_dir))
        assert r.indexed == 1

        entries = cat.find()
        assert entries[0].symbol == "BTC/USDT"
        assert entries[0].interval == "1h"
        cat.close()

    def test_rebuild_skips_non_result_files(self, tmp_path: Path) -> None:
        """rebuild() skips non-result files."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        # A non-result file
        (results_dir / "H2-detailed-results.json").write_text(
            json.dumps({"custom": "data"}), encoding="utf-8"
        )

        r = cat.rebuild(str(results_dir))
        assert r.indexed == 0
        assert r.skipped_parse_error == 0
        cat.close()

    def test_rebuild_idempotent(self, tmp_path: Path) -> None:
        """rebuild() skips already-indexed files."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        self._create_result_json(
            results_dir,
            "sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-01-01T23:59:59Z.json",
        )

        r1 = cat.rebuild(str(results_dir))
        assert r1.indexed == 1

        r2 = cat.rebuild(str(results_dir))
        assert r2.indexed == 0
        assert r2.skipped_existing == 1
        cat.close()

    def test_rebuild_returns_counts(self, tmp_path: Path) -> None:
        """rebuild() returns correct RebuildResult."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        self._create_result_json(
            results_dir,
            "sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-01-01T23:59:59Z.json",
        )
        # Bad JSON file with a name that matches the result pattern
        (results_dir / "bad_ETH_USDT_4h_2024-01-01T00:00:00Z_2025-01-01T23:59:59Z.json").write_text(
            "not json", encoding="utf-8"
        )

        r = cat.rebuild(str(results_dir))
        assert isinstance(r, RebuildResult)
        assert r.indexed == 1
        assert r.skipped_parse_error == 1
        assert len(r.errors) == 1
        assert "bad_ETH_USDT" in r.errors[0]
        cat.close()

    def test_rebuild_nonexistent_dir(self, tmp_path: Path) -> None:
        """rebuild() with non-existent dir returns error."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        r = cat.rebuild(str(tmp_path / "nonexistent"))
        assert r.indexed == 0
        assert len(r.errors) == 1
        assert "not found" in r.errors[0]
        cat.close()

    def test_rebuild_extracts_metrics_from_json(self, tmp_path: Path) -> None:
        """rebuild() correctly extracts metrics from JSON content."""
        db_path = str(tmp_path / "test.db")
        cat = ResultsCatalog(db_path=db_path)

        results_dir = tmp_path / "strategy_results"
        results_dir.mkdir()

        self._create_result_json(
            results_dir,
            "sma_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-01-01T23:59:59Z.json",
            total_return=12.58,
            sharpe=0.22,
            max_dd=-61.1,
            win_rate=42.11,
            total_trades=19,
            profit_factor=1.1,
        )

        cat.rebuild(str(results_dir))
        entries = cat.find()
        assert len(entries) == 1
        assert entries[0].total_return_pct == 12.58
        assert entries[0].sharpe_ratio == 0.22
        assert entries[0].max_drawdown_pct == -61.1
        assert entries[0].win_rate_pct == 42.11
        assert entries[0].total_trades == 19
        assert entries[0].profit_factor == 1.1
        cat.close()


# ── to_dataframe Tests ──────────────────────────────────────


class TestToDataframe:
    """Tests for to_dataframe method."""

    def test_returns_dataframe(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """to_dataframe() returns a DataFrame with correct columns."""
        import pandas as pd

        catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/df_test.json",
            parameters={},
        )

        df = catalog.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "strategy_id" in df.columns
        assert "symbol" in df.columns
        assert "parameters" in df.columns

    def test_filters_by_strategy(self, catalog: ResultsCatalog, sample_metrics: dict) -> None:
        """to_dataframe() filters by strategy_id."""
        import pandas as pd  # noqa: F401

        catalog.insert(
            strategy_id="sma",
            symbol="BTC/USDT",
            interval="1h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/df_sma.json",
            parameters={},
        )
        catalog.insert(
            strategy_id="rsi",
            symbol="ETH/USDT",
            interval="4h",
            start_date="2025-01-01",
            end_date="2025-01-31",
            run_type="BACKTEST",
            metrics=sample_metrics,
            results_file="strategy_results/df_rsi.json",
            parameters={},
        )

        df = catalog.to_dataframe(strategy_id="sma")
        assert len(df) == 1
        assert df.iloc[0]["strategy_id"] == "sma"

    def test_empty_dataframe(self, catalog: ResultsCatalog) -> None:
        """to_dataframe() on empty catalog returns empty DataFrame."""
        import pandas as pd

        df = catalog.to_dataframe()
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


# ── Filename Parsing Tests ──────────────────────────────────


class TestFilenameParsing:
    """Tests for filename pattern parsing."""

    def test_parse_engine_format(self) -> None:
        """Parses engine format filenames correctly."""
        result = ResultsCatalog._parse_filename(
            "h2_rsi_divergence_trend_BTC_USDT_4h_2024-01-01T00:00:00Z_2025-08-31T23:59:59Z.json"
        )
        assert result is not None
        assert result["strategy_id"] == "h2_rsi_divergence_trend"
        assert result["symbol"] == "BTC/USDT"
        assert result["interval"] == "4h"
        assert result["start_date"] == "2024-01-01T00:00:00Z"
        assert result["end_date"] == "2025-08-31T23:59:59Z"

    def test_parse_old_format(self) -> None:
        """Parses old format filenames correctly."""
        result = ResultsCatalog._parse_filename(
            "sma_crossover_BTC_USDT_1h_2025-01-01_2025-01-31.json"
        )
        assert result is not None
        assert result["strategy_id"] == "sma_crossover"
        assert result["symbol"] == "BTC/USDT"
        assert result["interval"] == "1h"
        assert result["start_date"] == "2025-01-01"
        assert result["end_date"] == "2025-01-31"

    def test_parse_non_result_file(self) -> None:
        """Non-result filenames return None."""
        result = ResultsCatalog._parse_filename("H2-detailed-results.json")
        assert result is None

    def test_parse_report_file(self) -> None:
        """Non-JSON files return None."""
        result = ResultsCatalog._parse_filename("H2-report.md")
        assert result is None
