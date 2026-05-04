"""Portfolio tracker for managing positions and equity during strategy runs."""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from cryplative.core.models import (
    RunContext,
    Signal,
    Trade,
    TradeStatus,
)

logger = structlog.get_logger()


class PortfolioTracker:
    """Tracks equity curve and positions during a backtest or live run.

    Minimal implementation for Phase 1.
    """

    def __init__(self, initial_capital: float, context: RunContext = RunContext.BACKTEST) -> None:
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position: float | None = None  # quantity held
        self.entry_price: float | None = None
        self.trades: list[Trade] = []
        self._context = context
        self._equity_curve: list[tuple[int, float]] = []

    @property
    def has_open_position(self) -> bool:
        """Whether there is currently an open position."""
        return self.position is not None and self.position > 0

    def open_position(self, signal: Signal, price: float, timestamp: int) -> Trade:
        """Open a position. Deduct capital.

        Args:
            signal: The signal that triggered this position.
            price: The execution price.
            timestamp: The execution timestamp (ms).

        Returns:
            The opened Trade.
        """
        if self.has_open_position:
            logger.warning("open_position_already_exists", trade_id=self.trades[-1].trade_id)

        cost = price * signal.quantity
        if cost > self.capital:
            logger.error(
                "insufficient_capital",
                capital=self.capital,
                cost=cost,
                signal_id=signal.strategy_id,
            )

        self.capital -= cost
        self.position = signal.quantity
        self.entry_price = price

        trade = Trade(
            trade_id=str(uuid.uuid4()),
            signal=signal,
            entry_price=price,
            exit_price=None,
            quantity=signal.quantity,
            pnl=None,
            pnl_percentage=None,
            status=TradeStatus.OPEN,
            opened_at=timestamp,
            closed_at=None,
            context=self._context,
        )
        self.trades.append(trade)

        logger.debug(
            "position_opened",
            trade_id=trade.trade_id,
            price=price,
            quantity=signal.quantity,
            capital_remaining=self.capital,
        )

        return trade

    def close_position(self, price: float, timestamp: int) -> Trade | None:
        """Close the current position at the given price.

        Args:
            price: The exit price.
            timestamp: The exit timestamp (ms).

        Returns:
            The closed Trade, or None if no position was open.
        """
        if not self.has_open_position:
            logger.warning("close_position_no_position")
            return None

        assert self.position is not None
        assert self.entry_price is not None

        proceeds = price * self.position
        self.capital += proceeds

        trade = self.trades[-1]
        pnl = (price - self.entry_price) * self.position
        pnl_pct = (price / self.entry_price - 1) * 100 if self.entry_price > 0 else 0.0

        trade.exit_price = price
        trade.pnl = pnl
        trade.pnl_percentage = pnl_pct
        trade.status = TradeStatus.CLOSED
        trade.closed_at = timestamp

        self.position = None
        self.entry_price = None

        logger.debug(
            "position_closed",
            trade_id=trade.trade_id,
            price=price,
            pnl=pnl,
            pnl_percentage=pnl_pct,
            capital=self.capital,
        )

        return trade

    def get_equity(self, current_price: float) -> float:
        """Current equity = cash + position value at current price."""
        position_value = (self.position or 0) * current_price
        return self.capital + position_value

    def record_equity(self, timestamp: int, price: float) -> None:
        """Record an equity snapshot at the given timestamp and price."""
        equity = self.get_equity(price)
        self._equity_curve.append((timestamp, equity))

    def get_equity_curve(self) -> list[tuple[int, float]]:
        """Return list of (timestamp, equity) snapshots."""
        return list(self._equity_curve)

    @property
    def closed_trades(self) -> list[Trade]:
        """Return all closed trades."""
        return [t for t in self.trades if t.status == TradeStatus.CLOSED]

    @property
    def open_trade(self) -> Trade | None:
        """Return the current open trade, if any."""
        if self.has_open_position:
            return self.trades[-1]
        return None
