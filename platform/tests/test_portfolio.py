"""Tests for portfolio tracker."""

from __future__ import annotations

import pytest

from cryplative.core.models import (
    RunContext,
    Signal,
    SignalDirection,
    TradeStatus,
)
from cryplative.portfolio.tracker import PortfolioTracker


def _buy_signal(timestamp: int = 1704067200000, quantity: float = 1.0) -> Signal:
    return Signal(
        strategy_id="test_strategy",
        symbol="BTC/USDT",
        timestamp=timestamp,
        direction=SignalDirection.BUY,
        order_type="MARKET",
        price=None,
        quantity=quantity,
        stop_loss=None,
        take_profit=None,
        confidence=0.8,
    )


def _sell_signal(timestamp: int = 1704070800000, quantity: float = 1.0) -> Signal:
    return Signal(
        strategy_id="test_strategy",
        symbol="BTC/USDT",
        timestamp=timestamp,
        direction=SignalDirection.SELL,
        order_type="MARKET",
        price=None,
        quantity=quantity,
        stop_loss=None,
        take_profit=None,
        confidence=0.8,
    )


class TestPortfolioTracker:
    def test_initial_state(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        assert tracker.capital == 10000.0
        assert tracker.position is None
        assert tracker.trades == []
        assert not tracker.has_open_position

    def test_open_position(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        signal = _buy_signal(quantity=1.0)

        trade = tracker.open_position(signal, price=42000.0, timestamp=1704067200000)

        assert trade.status == TradeStatus.OPEN
        assert trade.entry_price == 42000.0
        assert tracker.capital == 10000.0 - 42000.0  # negative for simplicity
        assert tracker.position == 1.0
        assert len(tracker.trades) == 1

    def test_close_position_profit(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        buy_signal = _buy_signal(quantity=1.0)
        tracker.open_position(buy_signal, price=42000.0, timestamp=1704067200000)

        closed = tracker.close_position(price=43000.0, timestamp=1704070800000)

        assert closed is not None
        assert closed.status == TradeStatus.CLOSED
        assert closed.exit_price == 43000.0
        assert closed.pnl == 1000.0
        assert closed.pnl_percentage == pytest.approx((43000.0 / 42000.0 - 1) * 100)
        assert tracker.position is None

    def test_close_position_loss(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        buy_signal = _buy_signal(quantity=1.0)
        tracker.open_position(buy_signal, price=42000.0, timestamp=1704067200000)

        closed = tracker.close_position(price=41000.0, timestamp=1704070800000)

        assert closed is not None
        assert closed.pnl == -1000.0
        assert closed.pnl_percentage < 0

    def test_close_position_no_position(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        result = tracker.close_position(price=42000.0, timestamp=1704070800000)
        assert result is None

    def test_get_equity_no_position(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        equity = tracker.get_equity(current_price=42000.0)
        assert equity == 10000.0

    def test_get_equity_with_position(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        signal = _buy_signal(quantity=1.0)
        tracker.open_position(signal, price=42000.0, timestamp=1704067200000)

        equity = tracker.get_equity(current_price=43000.0)
        expected = (10000.0 - 42000.0) + 43000.0
        assert equity == expected

    def test_equity_curve(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)

        tracker.record_equity(1704067200000, 42000.0)
        tracker.record_equity(1704070800000, 42500.0)
        tracker.record_equity(1704074400000, 43000.0)

        curve = tracker.get_equity_curve()
        assert len(curve) == 3
        assert curve[0] == (1704067200000, 10000.0)
        assert curve[1] == (1704070800000, 10000.0)
        assert curve[2] == (1704074400000, 10000.0)

    def test_multiple_trades(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0)

        # Trade 1: buy at 42k, sell at 43k
        s1 = _buy_signal(quantity=1.0)
        tracker.open_position(s1, price=42000.0, timestamp=1704067200000)
        tracker.close_position(price=43000.0, timestamp=1704070800000)

        # Trade 2: buy at 43k, sell at 41k
        s2 = _buy_signal(quantity=1.0)
        tracker.open_position(s2, price=43000.0, timestamp=1704074400000)
        tracker.close_position(price=41000.0, timestamp=1704078000000)

        assert len(tracker.trades) == 2
        assert tracker.trades[0].pnl == 1000.0
        assert tracker.trades[1].pnl == -2000.0
        assert tracker.closed_trades == tracker.trades

    def test_open_trade_property(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0)

        assert tracker.open_trade is None

        signal = _buy_signal(quantity=1.0)
        tracker.open_position(signal, price=42000.0, timestamp=1704067200000)

        assert tracker.open_trade is not None
        assert tracker.open_trade.status == TradeStatus.OPEN

        tracker.close_position(price=43000.0, timestamp=1704070800000)
        assert tracker.open_trade is None

    def test_backtest_context(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0, context=RunContext.BACKTEST)
        signal = _buy_signal(quantity=1.0)
        trade = tracker.open_position(signal, price=42000.0, timestamp=1704067200000)
        assert trade.context == RunContext.BACKTEST
