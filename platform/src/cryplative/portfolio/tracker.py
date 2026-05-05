"""Portfolio tracker for managing positions and equity during strategy runs."""

from __future__ import annotations

import uuid

import structlog

from cryplative.core.exceptions import BacktestError
from cryplative.core.models import (
    RunContext,
    Signal,
    Trade,
    TradeStatus,
)

logger = structlog.get_logger()


class PortfolioTracker:
    """Tracks equity curve and positions during a backtest or live run.

    Supports multiple concurrent positions with configurable max_positions.
    """

    def __init__(
        self,
        initial_capital: float,
        context: RunContext = RunContext.BACKTEST,
        max_positions: int = 1,
    ) -> None:
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self._context = context
        self.max_positions = max_positions
        self.open_trades: list[Trade] = []
        self.closed_trades: list[Trade] = []
        self.equity_snapshots: list[tuple[int, float]] = []

    def can_open(self) -> bool:
        """Whether we can open a new position."""
        return len(self.open_trades) < self.max_positions

    def open_position(self, signal: Signal, price: float, timestamp: int) -> Trade:
        """Open a new position. Deduct capital.

        Args:
            signal: The signal that triggered this position.
            price: The execution price.
            timestamp: The execution timestamp (ms).

        Returns:
            The opened Trade.

        Raises:
            BacktestError: If max_positions already reached.
        """
        if not self.can_open():
            raise BacktestError(
                f"Cannot open position: max_positions ({self.max_positions}) reached"
            )

        cost = price * signal.quantity
        if cost > self.capital:
            logger.warning(
                "insufficient_capital",
                capital=self.capital,
                cost=cost,
                signal_id=signal.strategy_id,
            )

        self.capital -= cost

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
        self.open_trades.append(trade)

        logger.debug(
            "position_opened",
            trade_id=trade.trade_id,
            price=price,
            quantity=signal.quantity,
            capital_remaining=self.capital,
            open_positions=len(self.open_trades),
        )

        return trade

    def close_position(self, trade: Trade, price: float, timestamp: int) -> Trade:
        """Close a specific trade. Add capital back.

        Args:
            trade: The open trade to close.
            price: The exit price.
            timestamp: The exit timestamp (ms).

        Returns:
            The closed Trade.
        """
        proceeds = price * trade.quantity
        self.capital += proceeds

        pnl = (price - trade.entry_price) * trade.quantity
        pnl_pct = (price / trade.entry_price - 1) * 100 if trade.entry_price > 0 else 0.0

        trade.exit_price = price
        trade.pnl = pnl
        trade.pnl_percentage = pnl_pct
        trade.status = TradeStatus.CLOSED
        trade.closed_at = timestamp

        self.open_trades.remove(trade)
        self.closed_trades.append(trade)

        logger.debug(
            "position_closed",
            trade_id=trade.trade_id,
            price=price,
            pnl=pnl,
            pnl_percentage=pnl_pct,
            capital=self.capital,
            open_positions=len(self.open_trades),
        )

        return trade

    def close_oldest(self, price: float, timestamp: int) -> Trade:
        """Close the oldest open trade (FIFO).

        Args:
            price: The exit price.
            timestamp: The exit timestamp (ms).

        Returns:
            The closed Trade.

        Raises:
            BacktestError: If no open positions.
        """
        if not self.open_trades:
            raise BacktestError("No open positions to close")
        return self.close_position(self.open_trades[0], price, timestamp)

    def get_equity(self, current_price: float) -> float:
        """Current equity = cash + sum of all open position values at current price."""
        position_value = sum(t.quantity * current_price for t in self.open_trades)
        return self.capital + position_value

    def snapshot_equity(self, timestamp: int, current_price: float) -> None:
        """Record an equity snapshot at the given timestamp and price."""
        equity = self.get_equity(current_price)
        self.equity_snapshots.append((timestamp, equity))

    def get_equity_curve(self) -> list[tuple[int, float]]:
        """Return all equity snapshots."""
        return list(self.equity_snapshots)

    @property
    def all_trades(self) -> list[Trade]:
        """All trades (open + closed)."""
        return self.open_trades + self.closed_trades
