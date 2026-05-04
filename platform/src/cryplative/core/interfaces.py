"""Core abstract interfaces for Cryplative.

Every module implements one or more of these contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from cryplative.core.models import Candle, Signal, StrategyConfig, Trade


class Strategy(ABC):
    """Every trading strategy must implement this interface."""

    @property
    @abstractmethod
    def strategy_id(self) -> str:
        """Unique identifier for this strategy."""
        ...

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Human-readable name."""
        ...

    def initialize(self, config: StrategyConfig) -> None:
        """Called once before running. Sets up internal state from config.

        Default implementation stores config; override if needed.
        """
        self._config = config

    @abstractmethod
    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        """Analyze the given candles and optionally return a Signal.

        Returns None if no action should be taken.
        The candles list is guaranteed to be sorted by open_time ascending.
        """

    def teardown(self) -> None:
        """Called after a run completes. Clean up resources.

        Default is no-op; override if needed.
        """
        pass


class DataProvider(ABC):
    """Abstraction for fetching market data. Implemented by MarketFetcher."""

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> list[Candle]:
        """Fetch candle data. Returns sorted by open_time ascending."""
        ...


class ExecutionHandler(ABC):
    """Abstraction for trade execution. Implemented by backtesting, paper, real."""

    @abstractmethod
    def submit_signal(self, signal: Signal) -> Trade:
        """Process a signal and return the resulting trade."""
        ...

    @abstractmethod
    def close_trade(self, trade: Trade, price: float, timestamp: int) -> Trade:
        """Close an open trade at the given price and time."""
        ...
