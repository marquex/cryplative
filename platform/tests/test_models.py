"""Tests for core data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cryplative.core.models import (
    Candle,
    OrderType,
    RunContext,
    Signal,
    SignalDirection,
    StrategyConfig,
    StrategyMetrics,
    StrategyResult,
    Trade,
    TradeStatus,
)


# ---------------------------------------------------------------------------
# Candle
# ---------------------------------------------------------------------------


class TestCandle:
    def test_create_valid_candle(self) -> None:
        c = Candle(
            symbol="BTC/USDT",
            interval="1h",
            open_time=1704067200000,
            open=42000.0,
            high=42500.0,
            low=41800.0,
            close=42300.0,
            volume=1234.56,
            close_time=1704070799999,
            closed=True,
        )
        assert c.symbol == "BTC/USDT"
        assert c.close == 42300.0

    def test_open_time_must_be_before_close_time(self) -> None:
        with pytest.raises(ValidationError, match="open_time must be less than close_time"):
            Candle(
                symbol="BTC/USDT",
                interval="1h",
                open_time=1704070800000,
                open=42000.0,
                high=42500.0,
                low=41800.0,
                close=42300.0,
                volume=1234.56,
                close_time=1704067200000,
                closed=True,
            )

    def test_negative_volume_raises(self) -> None:
        with pytest.raises(ValidationError, match="non-negative"):
            Candle(
                symbol="BTC/USDT",
                interval="1h",
                open_time=1704067200000,
                open=42000.0,
                high=42500.0,
                low=41800.0,
                close=42300.0,
                volume=-1.0,
                close_time=1704070799999,
                closed=True,
            )

    def test_serialize_roundtrip(self) -> None:
        c = Candle(
            symbol="BTC/USDT",
            interval="1h",
            open_time=1704067200000,
            open=42000.0,
            high=42500.0,
            low=41800.0,
            close=42300.0,
            volume=1234.56,
            close_time=1704070799999,
            closed=True,
        )
        data = c.model_dump()
        c2 = Candle.model_validate(data)
        assert c == c2

    def test_json_roundtrip(self) -> None:
        c = Candle(
            symbol="ETH/USDT",
            interval="4h",
            open_time=1704067200000,
            open=3000.0,
            high=3100.0,
            low=2950.0,
            close=3050.0,
            volume=500.0,
            close_time=1704070799999,
            closed=False,
        )
        json_str = c.model_dump_json()
        c2 = Candle.model_validate_json(json_str)
        assert c == c2


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


class TestSignal:
    def _make_signal(self, **overrides: object) -> Signal:
        defaults: dict[str, object] = {
            "strategy_id": "sma_crossover",
            "symbol": "BTC/USDT",
            "timestamp": 1704067200000,
            "direction": SignalDirection.BUY,
            "order_type": OrderType.MARKET,
            "price": None,
            "quantity": 1.0,
            "stop_loss": None,
            "take_profit": None,
            "confidence": 0.5,
        }
        defaults.update(overrides)
        return Signal(**defaults)  # type: ignore[arg-type]

    def test_create_valid_market_buy_signal(self) -> None:
        s = self._make_signal()
        assert s.direction == SignalDirection.BUY
        assert s.order_type == OrderType.MARKET

    def test_confidence_out_of_range(self) -> None:
        with pytest.raises(ValidationError, match="confidence must be between"):
            self._make_signal(confidence=1.5)

    def test_confidence_negative(self) -> None:
        with pytest.raises(ValidationError, match="confidence must be between"):
            self._make_signal(confidence=-0.1)

    def test_limit_order_without_price_raises(self) -> None:
        with pytest.raises(ValidationError, match="price is required for LIMIT"):
            self._make_signal(order_type=OrderType.LIMIT, price=None)

    def test_limit_order_with_price_succeeds(self) -> None:
        s = self._make_signal(order_type=OrderType.LIMIT, price=42000.0)
        assert s.price == 42000.0

    def test_negative_quantity_raises(self) -> None:
        with pytest.raises(ValidationError, match="non-negative"):
            self._make_signal(quantity=-1.0)

    def test_metadata_default(self) -> None:
        s = self._make_signal()
        assert s.metadata == {}

    def test_serialize_roundtrip(self) -> None:
        s = self._make_signal(
            order_type=OrderType.LIMIT, price=42000.0, confidence=0.8
        )
        data = s.model_dump()
        s2 = Signal.model_validate(data)
        assert s == s2


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------


class TestTrade:
    def test_create_open_trade(self) -> None:
        signal = Signal(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            timestamp=1704067200000,
            direction=SignalDirection.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=1.0,
            stop_loss=None,
            take_profit=None,
            confidence=0.5,
        )
        t = Trade(
            trade_id="abc-123",
            signal=signal,
            entry_price=42000.0,
            exit_price=None,
            quantity=1.0,
            pnl=None,
            pnl_percentage=None,
            status=TradeStatus.OPEN,
            opened_at=1704067200000,
            closed_at=None,
            context=RunContext.BACKTEST,
        )
        assert t.status == TradeStatus.OPEN
        assert t.pnl is None

    def test_negative_entry_price_raises(self) -> None:
        signal = Signal(
            strategy_id="sma_crossover",
            symbol="BTC/USDT",
            timestamp=1704067200000,
            direction=SignalDirection.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=1.0,
            stop_loss=None,
            take_profit=None,
            confidence=0.5,
        )
        with pytest.raises(ValidationError, match="non-negative"):
            Trade(
                trade_id="abc-123",
                signal=signal,
                entry_price=-1.0,
                exit_price=None,
                quantity=1.0,
                pnl=None,
                pnl_percentage=None,
                status=TradeStatus.OPEN,
                opened_at=1704067200000,
                closed_at=None,
                context=RunContext.BACKTEST,
            )


# ---------------------------------------------------------------------------
# StrategyConfig, StrategyMetrics, StrategyResult
# ---------------------------------------------------------------------------


class TestStrategyConfig:
    def test_create_with_defaults(self) -> None:
        cfg = StrategyConfig(
            strategy_id="sma_crossover",
            strategy_name="SMA Crossover",
            version="1.0.0",
            symbol="BTC/USDT",
            interval="1h",
        )
        assert cfg.parameters == {}
        assert cfg.state == {}

    def test_create_with_parameters(self) -> None:
        cfg = StrategyConfig(
            strategy_id="sma_crossover",
            strategy_name="SMA Crossover",
            version="1.0.0",
            symbol="BTC/USDT",
            interval="1h",
            parameters={"fast_period": 10, "slow_period": 20},
        )
        assert cfg.parameters["fast_period"] == 10


class TestStrategyMetrics:
    def test_create_metrics(self) -> None:
        m = StrategyMetrics(
            total_return=15.3,
            sharpe_ratio=1.24,
            max_drawdown=-8.5,
            win_rate=55.0,
            total_trades=20,
            profit_factor=1.8,
        )
        assert m.total_trades == 20
        assert m.sharpe_ratio == 1.24


class TestStrategyResult:
    def test_create_result(self) -> None:
        r = StrategyResult(
            strategy_id="sma_crossover",
            run_type=RunContext.BACKTEST,
            start_date="2025-01-01T00:00:00Z",
            end_date="2025-06-01T00:00:00Z",
            parameters={"fast_period": 10},
            trades=[],
            metrics=StrategyMetrics(
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                total_trades=0,
                profit_factor=0.0,
            ),
            created_at="2026-05-04T12:00:00Z",
        )
        assert r.run_type == RunContext.BACKTEST
        assert len(r.trades) == 0

    def test_json_serialization(self) -> None:
        r = StrategyResult(
            strategy_id="sma_crossover",
            run_type=RunContext.BACKTEST,
            start_date="2025-01-01T00:00:00Z",
            end_date="2025-06-01T00:00:00Z",
            parameters={"fast_period": 10, "slow_period": 20},
            trades=[],
            metrics=StrategyMetrics(
                total_return=15.3,
                sharpe_ratio=1.24,
                max_drawdown=-8.5,
                win_rate=55.0,
                total_trades=20,
                profit_factor=1.8,
            ),
            created_at="2026-05-04T12:00:00Z",
        )
        json_str = r.model_dump_json(indent=2)
        assert "sma_crossover" in json_str
        r2 = StrategyResult.model_validate_json(json_str)
        assert r2 == r
