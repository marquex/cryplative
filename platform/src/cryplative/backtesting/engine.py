"""Backtesting engine — runs strategies against historical data."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import structlog

from cryplative.config import CryplativeConfig
from cryplative.core.exceptions import BacktestError, StrategyError
from cryplative.core.interfaces import DataProvider
from cryplative.core.models import (
    RunContext,
    SignalDirection,
    StrategyConfig,
    StrategyMetrics,
    StrategyResult,
    Trade,
)
from cryplative.portfolio.tracker import PortfolioTracker
from cryplative.strategies.registry import StrategyRegistry

logger = structlog.get_logger()


class BacktestConfig:
    """Configuration for a backtest run."""

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 10000.0,
        parameters: dict[str, Any] | None = None,
        lookback_window: int = 200,
        max_positions: int = 1,
    ) -> None:
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.interval = interval
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.parameters = parameters or {}
        self.lookback_window = lookback_window
        self.max_positions = max_positions

    def start_timestamp_ms(self) -> int:
        """Convert start_date to Unix timestamp in milliseconds."""
        dt = datetime.fromisoformat(self.start_date.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)

    def end_timestamp_ms(self) -> int:
        """Convert end_date to Unix timestamp in milliseconds."""
        dt = datetime.fromisoformat(self.end_date.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)


class BacktestEngine:
    """Simulates running a strategy over historical data."""

    def __init__(
        self,
        data_provider: DataProvider,
        config: CryplativeConfig | None = None,
    ) -> None:
        self._data_provider = data_provider
        self._config = config or CryplativeConfig()

    def run(self, backtest_config: BacktestConfig) -> StrategyResult:
        """Run a backtest with the given configuration.

        Returns a StrategyResult with trades and metrics.
        """
        logger.info(
            "backtest_starting",
            strategy_id=backtest_config.strategy_id,
            symbol=backtest_config.symbol,
            interval=backtest_config.interval,
            start=backtest_config.start_date,
            end=backtest_config.end_date,
        )

        # 1. Resolve strategy
        try:
            strategy_class = StrategyRegistry.get(backtest_config.strategy_id)
        except KeyError as e:
            raise BacktestError(str(e)) from e

        strategy = strategy_class()

        # 2. Fetch data
        start_ts = backtest_config.start_timestamp_ms()
        end_ts = backtest_config.end_timestamp_ms()
        candles = self._data_provider.get_candles(
            symbol=backtest_config.symbol,
            interval=backtest_config.interval,
            start_time=start_ts,
            end_time=end_ts,
        )

        if not candles:
            raise BacktestError(
                f"No candle data found for {backtest_config.symbol} "
                f"{backtest_config.interval} between {backtest_config.start_date} "
                f"and {backtest_config.end_date}. "
                "Check the symbol, try a different date range, or run "
                "'cryplative fetch' first."
            )

        # 3. Validate we have enough data
        if len(candles) < backtest_config.lookback_window:
            logger.warning(
                "insufficient_data_for_lookback",
                available=len(candles),
                required=backtest_config.lookback_window,
            )

        # 4. Initialize strategy
        strategy_config = StrategyConfig(
            strategy_id=backtest_config.strategy_id,
            strategy_name=strategy.strategy_name,
            version="1.0.0",
            symbol=backtest_config.symbol,
            interval=backtest_config.interval,
            parameters=backtest_config.parameters,
        )
        strategy.initialize(strategy_config)

        # 5. Simulate
        tracker = PortfolioTracker(
            initial_capital=backtest_config.initial_capital,
            context=RunContext.BACKTEST,
            max_positions=backtest_config.max_positions,
        )

        strategy_errors: int = 0

        for i, candle in enumerate(candles):
            # Build sliding window
            window_start = max(0, i - backtest_config.lookback_window + 1)
            window = candles[window_start : i + 1]

            # Generate signal (catch strategy errors, don't crash the run)
            try:
                signal = strategy.generate_signal(window)
            except StrategyError:
                strategy_errors += 1
                logger.warning("strategy_error_during_backtest", candle_index=i)
                tracker.snapshot_equity(candle.open_time, candle.close)
                continue

            if signal is None:
                tracker.snapshot_equity(candle.open_time, candle.close)
                continue

            # Process signal
            if signal.direction == SignalDirection.BUY and tracker.can_open():
                tracker.open_position(signal, candle.close, candle.open_time)
            elif signal.direction == SignalDirection.SELL and len(tracker.open_trades) > 0:
                tracker.close_oldest(candle.close, candle.open_time)

            tracker.snapshot_equity(candle.open_time, candle.close)

        # 6. Force-close all remaining open positions
        while tracker.open_trades and candles:
            last_candle = candles[-1]
            tracker.close_oldest(last_candle.close, last_candle.open_time)

        # 7. Calculate metrics
        closed_trades = tracker.closed_trades
        equity_curve = tracker.get_equity_curve()
        metrics = self._calculate_metrics(
            closed_trades=closed_trades,
            equity_curve=equity_curve,
            initial_capital=backtest_config.initial_capital,
        )

        # 8. Build result
        now = datetime.now(UTC).isoformat()
        metadata: dict[str, Any] = {}
        if strategy_errors > 0:
            metadata["strategy_errors"] = strategy_errors

        result = StrategyResult(
            strategy_id=backtest_config.strategy_id,
            run_type=RunContext.BACKTEST,
            start_date=backtest_config.start_date,
            end_date=backtest_config.end_date,
            parameters=backtest_config.parameters,
            trades=tracker.all_trades,
            metrics=metrics,
            created_at=now,
        )

        # Persist result
        self._save_result(result, backtest_config)

        # Teardown
        strategy.teardown()

        logger.info(
            "backtest_completed",
            strategy_id=backtest_config.strategy_id,
            total_trades=len(closed_trades),
            total_return=metrics.total_return,
            sharpe_ratio=metrics.sharpe_ratio,
        )

        return result

    def _calculate_metrics(
        self,
        closed_trades: list[Trade],
        equity_curve: list[tuple[int, float]],
        initial_capital: float,
    ) -> StrategyMetrics:
        """Calculate performance metrics from backtest results."""
        if not equity_curve:
            return StrategyMetrics(
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                total_trades=0,
                profit_factor=0.0,
            )

        final_equity = equity_curve[-1][1]
        total_return = (final_equity - initial_capital) / initial_capital * 100

        # Max drawdown from equity curve
        max_drawdown = 0.0
        peak = equity_curve[0][1]
        for _, equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (equity - peak) / peak * 100 if peak > 0 else 0.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown

        # Trade-based metrics
        total_trades = len(closed_trades)
        if total_trades == 0:
            return StrategyMetrics(
                total_return=total_return,
                sharpe_ratio=0.0,
                max_drawdown=max_drawdown,
                win_rate=0.0,
                total_trades=0,
                profit_factor=0.0,
            )

        wins = [t for t in closed_trades if t.pnl is not None and t.pnl > 0]
        losses = [t for t in closed_trades if t.pnl is not None and t.pnl <= 0]
        win_rate = len(wins) / total_trades * 100

        # Profit factor
        gross_profit = sum(t.pnl for t in wins if t.pnl is not None) if wins else 0.0
        gross_loss = (
            abs(sum(t.pnl for t in losses if t.pnl is not None)) if losses else 0.0
        )
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )

        # Sharpe ratio from trade returns
        sharpe_ratio = 0.0
        if total_trades >= 2:
            trade_returns = [
                (t.exit_price / t.entry_price) - 1
                for t in closed_trades
                if t.entry_price > 0 and t.exit_price is not None
            ]

            if len(trade_returns) >= 2:
                mean_ret = sum(trade_returns) / len(trade_returns)
                variance = sum((r - mean_ret) ** 2 for r in trade_returns) / (
                    len(trade_returns) - 1
                )
                std_ret = math.sqrt(variance) if variance > 0 else 0.0
                if std_ret > 0:
                    sharpe_ratio = (mean_ret / std_ret) * math.sqrt(
                        len(trade_returns)
                    )

        pf_value = (
            round(profit_factor, 2)
            if profit_factor != float("inf")
            else profit_factor
        )

        return StrategyMetrics(
            total_return=round(total_return, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
            max_drawdown=round(max_drawdown, 2),
            win_rate=round(win_rate, 2),
            total_trades=total_trades,
            profit_factor=pf_value,
        )

    def _save_result(self, result: StrategyResult, config: BacktestConfig) -> None:
        """Save the strategy result as JSON to the results directory."""
        results_dir = self._config.resolve_strategy_results_dir()
        results_dir.mkdir(parents=True, exist_ok=True)

        safe_symbol = config.symbol.replace("/", "_")
        filename = (
            f"{result.strategy_id}_{safe_symbol}_{config.interval}_"
            f"{config.start_date}_{config.end_date}.json"
        )
        filepath = results_dir / filename

        filepath.write_text(result.model_dump_json(indent=2), encoding="utf-8")

        logger.debug("result_saved", path=str(filepath))
