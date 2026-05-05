"""Tests for portfolio tracker."""

from __future__ import annotations

import pytest

from cryplative.core.exceptions import BacktestError
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
        assert tracker.open_trades == []
        assert tracker.closed_trades == []
        assert tracker.can_open()  # max_positions=1, 0 open → can open

    def test_initial_state_max_3(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0, max_positions=3)
        assert tracker.can_open()

    def test_can_open_respects_max(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0, max_positions=2)
        assert tracker.can_open()
        tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1000)
        assert tracker.can_open()
        tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1001)
        assert not tracker.can_open()

    def test_open_position(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        signal = _buy_signal(quantity=1.0)

        trade = tracker.open_position(signal, price=42000.0, timestamp=1704067200000)

        assert trade.status == TradeStatus.OPEN
        assert trade.entry_price == 42000.0
        assert tracker.capital == 10000.0 - 42000.0  # negative for simplicity
        assert len(tracker.open_trades) == 1

    def test_close_position_profit(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        buy_signal = _buy_signal(quantity=1.0)
        trade = tracker.open_position(buy_signal, price=42000.0, timestamp=1704067200000)

        closed = tracker.close_position(trade, price=43000.0, timestamp=1704070800000)

        assert closed.status == TradeStatus.CLOSED
        assert closed.exit_price == 43000.0
        assert closed.pnl == 1000.0
        assert closed.pnl_percentage == pytest.approx((43000.0 / 42000.0 - 1) * 100)
        assert len(tracker.open_trades) == 0
        assert len(tracker.closed_trades) == 1

    def test_close_position_loss(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        buy_signal = _buy_signal(quantity=1.0)
        trade = tracker.open_position(buy_signal, price=42000.0, timestamp=1704067200000)

        closed = tracker.close_position(trade, price=41000.0, timestamp=1704070800000)

        assert closed.pnl == -1000.0
        assert closed.pnl_percentage < 0

    def test_close_oldest(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0, max_positions=3)
        trade1 = tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1000)
        trade2 = tracker.open_position(_buy_signal(quantity=1.0), price=200.0, timestamp=1001)
        tracker.open_position(_buy_signal(quantity=1.0), price=300.0, timestamp=1002)

        closed = tracker.close_oldest(price=150.0, timestamp=2000)
        assert closed.trade_id == trade1.trade_id
        assert closed.exit_price == 150.0
        assert closed.pnl == 50.0

        # Now open_trades should have trade2 and trade3
        assert len(tracker.open_trades) == 2
        assert tracker.open_trades[0].trade_id == trade2.trade_id

    def test_close_oldest_no_positions(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        with pytest.raises(BacktestError, match="No open positions"):
            tracker.close_oldest(price=100.0, timestamp=1000)

    def test_exceed_max_positions_raises(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0, max_positions=2)
        tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1000)
        tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1001)
        with pytest.raises(BacktestError, match="max_positions"):
            tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1002)

    def test_get_equity_no_position(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        equity = tracker.get_equity(current_price=42000.0)
        assert equity == 10000.0

    def test_get_equity_with_single_position(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)
        signal = _buy_signal(quantity=1.0)
        tracker.open_position(signal, price=42000.0, timestamp=1704067200000)

        equity = tracker.get_equity(current_price=43000.0)
        expected = (10000.0 - 42000.0) + 43000.0
        assert equity == expected

    def test_get_equity_with_multiple_positions(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0, max_positions=3)
        tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1000)
        tracker.open_position(_buy_signal(quantity=1.0), price=200.0, timestamp=1001)

        equity = tracker.get_equity(current_price=150.0)
        expected = (100000.0 - 100.0 - 200.0) + (1.0 * 150.0) + (1.0 * 150.0)
        assert equity == expected

    def test_equity_curve(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0)

        tracker.snapshot_equity(1704067200000, 42000.0)
        tracker.snapshot_equity(1704070800000, 42500.0)
        tracker.snapshot_equity(1704074400000, 43000.0)

        curve = tracker.get_equity_curve()
        assert len(curve) == 3
        assert curve[0] == (1704067200000, 10000.0)
        assert curve[1] == (1704070800000, 10000.0)
        assert curve[2] == (1704074400000, 10000.0)

    def test_multiple_trades(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0)

        # Trade 1: buy at 42k, sell at 43k
        s1 = _buy_signal(quantity=1.0)
        t1 = tracker.open_position(s1, price=42000.0, timestamp=1704067200000)
        tracker.close_position(t1, price=43000.0, timestamp=1704070800000)

        # Trade 2: buy at 43k, sell at 41k
        s2 = _buy_signal(quantity=1.0)
        t2 = tracker.open_position(s2, price=43000.0, timestamp=1704074400000)
        tracker.close_position(t2, price=41000.0, timestamp=1704078000000)

        assert len(tracker.all_trades) == 2
        assert tracker.all_trades[0].pnl == 1000.0
        assert tracker.all_trades[1].pnl == -2000.0
        assert tracker.closed_trades == tracker.all_trades

    def test_all_trades_property(self) -> None:
        tracker = PortfolioTracker(initial_capital=100000.0, max_positions=3)
        tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1000)
        t2 = tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1001)
        tracker.close_position(t2, price=110.0, timestamp=2000)

        assert len(tracker.all_trades) == 2  # 1 open + 1 closed
        assert len(tracker.open_trades) == 1
        assert len(tracker.closed_trades) == 1

    def test_backtest_context(self) -> None:
        tracker = PortfolioTracker(initial_capital=10000.0, context=RunContext.BACKTEST)
        signal = _buy_signal(quantity=1.0)
        trade = tracker.open_position(signal, price=42000.0, timestamp=1704067200000)
        assert trade.context == RunContext.BACKTEST

    def test_force_close_all(self) -> None:
        """Simulate force-closing all remaining positions."""
        tracker = PortfolioTracker(initial_capital=100000.0, max_positions=3)
        tracker.open_position(_buy_signal(quantity=1.0), price=100.0, timestamp=1000)
        tracker.open_position(_buy_signal(quantity=1.0), price=200.0, timestamp=1001)

        while tracker.open_trades:
            tracker.close_oldest(price=150.0, timestamp=3000)

        assert len(tracker.open_trades) == 0
        assert len(tracker.closed_trades) == 2
