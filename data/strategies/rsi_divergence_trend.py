"""H2: RSI Divergence with Trend Filter — strategy implementation and backtest runner.

Spec: .agentic/specs/research/H2-rsi-divergence-trend-filter.md

Entry:  Bullish RSI divergence (price lower low + RSI higher low) during uptrend
        (close > SMA(200)) with RSI below oversold threshold.
Exit:   RSI overbought | stop-loss | take-profit | trend reversal | max holding period.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from cryplative.backtesting.engine import BacktestConfig, BacktestEngine
from cryplative.config import CryplativeConfig, setup_logging
from cryplative.core.interfaces import Strategy
from cryplative.core.models import (
    Candle,
    OrderType,
    Signal,
    SignalDirection,
    StrategyConfig,
)
from cryplative.market_fetcher.fetcher import MarketFetcher
from cryplative.strategies.indicators import compute_rsi, compute_sma
from cryplative.strategies.registry import StrategyRegistry


# ─── Constants ───────────────────────────────────────────────────────

FEE_PER_SIDE = 0.001       # 0.1% taker fee
ROUND_TRIP_FEE = 0.002     # 0.2% round-trip

# Module-level exit tracker.  The strategy appends to this list on each SELL
# signal.  The runner clears it before each backtest run and harvests it after.
_exit_log: list[dict] = []


# ─── Strategy ────────────────────────────────────────────────────────

@StrategyRegistry.register
class RSIDivergenceTrendFilter(Strategy):
    """H2: RSI Divergence with Trend Filter.

    Buys on bullish RSI divergence within an established uptrend.
    Self-tracks position state for entry/exit coordination.
    """

    @property
    def strategy_id(self) -> str:  # noqa: D102
        return "h2_rsi_divergence_trend"

    @property
    def strategy_name(self) -> str:  # noqa: D102
        return "RSI Divergence with Trend Filter (H2)"

    def initialize(self, config: StrategyConfig) -> None:
        super().initialize(config)
        p = config.parameters

        # Indicator parameters
        self._sma_period: int = p.get("sma_period", 200)
        self._rsi_period: int = p.get("rsi_period", 14)

        # Thresholds
        self._oversold_threshold: float = p.get("oversold_threshold", 40)
        self._overbought_exit: float = p.get("overbought_exit", 70)

        # Risk management
        self._stop_loss_pct: float = p.get("stop_loss_pct", 0.05)
        self._take_profit_pct: float = p.get("take_profit_pct", 0.10)

        # Pivot detection
        self._pivot_window: int = p.get("pivot_window", 5)
        self._min_pivot_spacing: int = p.get("min_pivot_spacing", 10)

        # Holding / sizing
        self._max_holding_candles: int = p.get("max_holding_candles", 50)
        self._assumed_capital: float = p.get("assumed_capital", 10000.0)
        self._risk_per_trade: float = p.get("risk_per_trade", 0.10)

        # Position state (self-tracked)
        self._has_position: bool = False
        self._entry_price: float = 0.0
        self._entry_qty: float = 0.0
        self._bars_held: int = 0

    # ── Pivot detection ──────────────────────────────────────────────

    def _find_pivot_lows(self, candles: list[Candle], count: int = 2) -> list[int]:
        """Return indices of the last *count* pivot lows (most recent first).

        A pivot low at index *i* means candles[i].low is the minimum low in a
        symmetric window of ``pivot_window`` candles on each side.

        Consecutive pivots must be separated by at least ``min_pivot_spacing``
        candles; closer candidates are skipped.
        """
        pw = self._pivot_window
        ms = self._min_pivot_spacing
        n = len(candles)

        pivots: list[int] = []

        # Scan backward.  Valid pivot indices are in [pw, n - pw - 1].
        for i in range(n - pw - 1, pw - 1, -1):
            center_low = candles[i].low

            # Check that center is the window minimum
            is_min = True
            for j in range(i - pw, i + pw + 1):
                if candles[j].low < center_low:
                    is_min = False
                    break
            if not is_min:
                continue

            # Enforce minimum spacing from the most-recently found pivot
            if pivots and (pivots[-1] - i) < ms:
                continue

            pivots.append(i)
            if len(pivots) == count:
                break

        return pivots

    # ── Divergence check ─────────────────────────────────────────────

    def _check_bullish_divergence(
        self,
        candles: list[Candle],
        rsi: list[float | None],
    ) -> bool:
        """True when the most recent pivot low has a *lower* price but
        *higher* RSI than the previous pivot low."""
        pivots = self._find_pivot_lows(candles, count=2)
        if len(pivots) < 2:
            return False

        i2, i1 = pivots  # i2 = most recent, i1 = older

        rsi2 = rsi[i2]
        rsi1 = rsi[i1]
        if rsi2 is None or rsi1 is None:
            return False

        price_lower_low = candles[i2].low < candles[i1].low
        rsi_higher_low = rsi2 > rsi1

        return price_lower_low and rsi_higher_low

    # ── Signal generation ────────────────────────────────────────────

    def generate_signal(self, candles: list[Candle]) -> Signal | None:
        """Analyze the candle window and optionally return a Signal."""
        n = len(candles)

        # Warmup: need enough candles for SMA + pivot detection
        warmup = self._sma_period + self._pivot_window + self._min_pivot_spacing
        if n < warmup:
            return None

        # Compute indicators on the full window
        closes = [c.close for c in candles]
        rsi = compute_rsi(closes, self._rsi_period)
        sma = compute_sma(closes, self._sma_period)

        cur_close = closes[-1]
        cur_rsi = rsi[-1]
        cur_sma = sma[-1]

        if cur_rsi is None or cur_sma is None:
            return None

        # ── EXIT CONDITIONS (position open) ──────────────────────────
        if self._has_position:
            self._bars_held += 1

            # 1. RSI overbought
            if cur_rsi > self._overbought_exit:
                return self._sell(candles, "rsi_overbought")

            # 2. Stop-loss
            if cur_close <= self._entry_price * (1.0 - self._stop_loss_pct):
                return self._sell(candles, "stop_loss")

            # 3. Take-profit
            if cur_close >= self._entry_price * (1.0 + self._take_profit_pct):
                return self._sell(candles, "take_profit")

            # 4. Trend reversal — close dropped below SMA
            if cur_close < cur_sma:
                return self._sell(candles, "trend_reversal")

            # 5. Maximum holding period
            if self._bars_held >= self._max_holding_candles:
                return self._sell(candles, "max_holding")

            return None

        # ── ENTRY CONDITIONS (no position) ───────────────────────────

        # Condition 1: Uptrend filter — price above SMA
        if cur_close <= cur_sma:
            return None

        # Condition 3: RSI below oversold threshold
        if cur_rsi >= self._oversold_threshold:
            return None

        # Condition 2: Bullish RSI divergence
        if not self._check_bullish_divergence(candles, rsi):
            return None

        # All entry conditions met
        return self._buy(candles)

    # ── Signal helpers ───────────────────────────────────────────────

    def _buy(self, candles: list[Candle]) -> Signal:
        """Create a BUY signal and track position state."""
        price = candles[-1].close
        qty = (self._assumed_capital * self._risk_per_trade) / price

        self._has_position = True
        self._entry_price = price
        self._entry_qty = qty
        self._bars_held = 0

        return Signal(
            strategy_id=self.strategy_id,
            symbol=candles[-1].symbol,
            timestamp=candles[-1].open_time,
            direction=SignalDirection.BUY,
            order_type=OrderType.MARKET,
            price=None,
            quantity=qty,
            stop_loss=price * (1.0 - self._stop_loss_pct),
            take_profit=price * (1.0 + self._take_profit_pct),
            confidence=0.7,
            metadata={"reason": "bullish_rsi_divergence"},
        )

    def _sell(self, candles: list[Candle], reason: str) -> Signal:
        """Create a SELL signal and clear position state."""
        qty = self._entry_qty
        price = candles[-1].close
        self._has_position = False

        # Record exit for post-processing
        _exit_log.append({
            "timestamp": candles[-1].open_time,
            "reason": reason,
            "entry_price": self._entry_price,
            "exit_price": price,
            "bars_held": self._bars_held,
        })

        return Signal(
            strategy_id=self.strategy_id,
            symbol=candles[-1].symbol,
            timestamp=candles[-1].open_time,
            direction=SignalDirection.SELL,
            order_type=OrderType.MARKET,
            price=None,
            quantity=qty,
            stop_loss=None,
            take_profit=None,
            confidence=0.7,
            metadata={"reason": reason},
        )


# ─── Fee-Adjusted Analysis ──────────────────────────────────────────


def _fee_adjust_trade(trade_data: dict) -> dict:
    """Add fee-adjusted PnL to a single trade dict."""
    entry_price = trade_data["entry_price"]
    exit_price = trade_data.get("exit_price")
    quantity = trade_data["quantity"]
    raw_pnl = trade_data.get("pnl") or 0.0

    if exit_price is None:
        return {**trade_data, "fee_adjusted_pnl": None}

    entry_fee = entry_price * quantity * FEE_PER_SIDE
    exit_fee = exit_price * quantity * FEE_PER_SIDE
    adj_pnl = raw_pnl - entry_fee - exit_fee

    return {**trade_data, "fee_adjusted_pnl": round(adj_pnl, 6)}


def _compute_metrics_from_pnls(
    trades: list[dict],
    initial_capital: float = 10000.0,
) -> dict:
    """Compute performance metrics from fee-adjusted trade data."""
    closed = [t for t in trades if t.get("exit_price") is not None]
    pnls = [t["fee_adjusted_pnl"] for t in closed if t.get("fee_adjusted_pnl") is not None]

    if not pnls:
        return {
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "total_trades": 0,
            "profit_factor": 0.0,
            "avg_trade_return_pct": 0.0,
        }

    total_pnl = sum(pnls)
    total_return = (total_pnl / initial_capital) * 100.0

    # Equity curve for max drawdown
    equity = initial_capital
    peak = equity
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = ((equity - peak) / peak) * 100.0 if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    # Win / loss
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = (len(wins) / len(pnls)) * 100.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe from per-trade returns (fee-adjusted)
    returns = []
    for t in closed:
        if t.get("exit_price") and t["entry_price"] > 0:
            raw_ret = (t["exit_price"] / t["entry_price"]) - 1.0
            returns.append(raw_ret - ROUND_TRIP_FEE)

    sharpe = 0.0
    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(var) if var > 0 else 0.0
        if std_r > 0:
            sharpe = (mean_r / std_r) * math.sqrt(len(returns))

    avg_ret = (total_pnl / len(pnls) / initial_capital) * 100.0

    pf_val = round(profit_factor, 4) if profit_factor != float("inf") else "inf"
    return {
        "total_return_pct": round(total_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "max_drawdown_pct": round(max_dd, 4),
        "win_rate_pct": round(win_rate, 2),
        "total_trades": len(pnls),
        "profit_factor": pf_val,
        "avg_trade_return_pct": round(avg_ret, 4),
    }


# ─── Backtest Configuration ─────────────────────────────────────────

# Adjusted defaults after initial diagnosis.
# Spec defaults (pivot_window=5, min_pivot_spacing=10, oversold_threshold=40)
# produced only 1 divergence across the full BTC 4h dataset — far too few for
# statistical validity.  The spec anticipated this ("Too few signals" failure
# mode) and suggested relaxing pivot_window.  After sweeping the spec's ranges
# we landed on pw=3, ms=5, threshold=50 which gives ~38 training-period signals.
SPEC_DEFAULT_PARAMS: dict = {
    "sma_period": 200,
    "rsi_period": 14,
    "oversold_threshold": 40,
    "overbought_exit": 70,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.10,
    "pivot_window": 5,
    "min_pivot_spacing": 10,
}

DEFAULT_PARAMS: dict = {
    "sma_period": 200,
    "rsi_period": 14,
    "oversold_threshold": 50,
    "overbought_exit": 70,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.10,
    "pivot_window": 3,
    "min_pivot_spacing": 5,
    "assumed_capital": 10000.0,
    "risk_per_trade": 0.10,
}

INTERVAL_OVERRIDES: dict[str, dict] = {
    "4h": {"max_holding_candles": 50},   # ~8.3 days
    "1d": {"max_holding_candles": 20},   # ~20 days
}

# (symbol, interval, start_date, end_date, label)
BACKTESTS: list[tuple[str, str, str, str, str]] = [
    # Primary deliverables (spec Section 12)
    ("BTC/USDT", "4h", "2024-01-01T00:00:00Z", "2025-08-31T23:59:59Z", "BTC_4h_train"),
    ("BTC/USDT", "4h", "2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z", "BTC_4h_test"),
    ("ETH/USDT", "4h", "2024-01-01T00:00:00Z", "2025-08-31T23:59:59Z", "ETH_4h_train"),
    ("ETH/USDT", "4h", "2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z", "ETH_4h_test"),
    ("BTC/USDT", "1d", "2024-01-01T00:00:00Z", "2025-08-31T23:59:59Z", "BTC_1d_train"),
    ("BTC/USDT", "1d", "2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z", "BTC_1d_test"),
    # Additional pairs for regime coverage (spec Section 9)
    ("SOL/USDT", "4h", "2024-01-01T00:00:00Z", "2025-08-31T23:59:59Z", "SOL_4h_train"),
    ("SOL/USDT", "4h", "2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z", "SOL_4h_test"),
    ("LINK/USDT", "4h", "2024-01-01T00:00:00Z", "2025-08-31T23:59:59Z", "LINK_4h_train"),
    ("LINK/USDT", "4h", "2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z", "LINK_4h_test"),
    ("ETH/USDT", "1d", "2024-01-01T00:00:00Z", "2025-08-31T23:59:59Z", "ETH_1d_train"),
    ("ETH/USDT", "1d", "2025-09-01T00:00:00Z", "2026-04-30T23:59:59Z", "ETH_1d_test"),
]


# ─── Runner ──────────────────────────────────────────────────────────


def run_all_backtests() -> dict:
    """Execute all configured backtests and return a results dict keyed by label."""
    config = CryplativeConfig()
    setup_logging(config)

    fetcher = MarketFetcher(config)
    engine = BacktestEngine(fetcher, config)

    all_results: dict = {}

    for symbol, interval, start, end, label in BACKTESTS:
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  {label}  |  {symbol} {interval}")
        print(f"  {start}  ->  {end}")
        print(sep)

        params = {**DEFAULT_PARAMS, **INTERVAL_OVERRIDES.get(interval, {})}

        bt_cfg = BacktestConfig(
            strategy_id="h2_rsi_divergence_trend",
            symbol=symbol,
            interval=interval,
            start_date=start,
            end_date=end,
            initial_capital=10000.0,
            parameters=params,
            lookback_window=300,
        )

        # Clear exit log before each run
        _exit_log.clear()

        try:
            result = engine.run(bt_cfg)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            all_results[label] = {"error": str(exc)}
            continue

        # Harvest exit log (strategy → module-level tracker)
        exit_reasons: dict[str, int] = {}
        exit_by_ts: dict[int, str] = {}
        for entry in _exit_log:
            r = entry["reason"]
            exit_reasons[r] = exit_reasons.get(r, 0) + 1
            exit_by_ts[entry["timestamp"]] = r

        # Serialize trades for analysis
        trades_data: list[dict] = []
        for t in result.trades:
            # Look up exit reason from tracker (match by closed_at timestamp)
            exit_reason = exit_by_ts.get(t.closed_at, "force_close" if t.closed_at else "open")
            td = {
                "trade_id": t.trade_id,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "pnl_percentage": t.pnl_percentage,
                "status": t.status,
                "opened_at": t.opened_at,
                "closed_at": t.closed_at,
                "direction": str(t.signal.direction),
                "entry_reason": t.signal.metadata.get("reason", "unknown"),
                "exit_reason": exit_reason,
            }
            td = _fee_adjust_trade(td)
            trades_data.append(td)

        # Raw metrics (from engine)
        raw = {
            "total_return_pct": result.metrics.total_return,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "max_drawdown_pct": result.metrics.max_drawdown,
            "win_rate_pct": result.metrics.win_rate,
            "total_trades": result.metrics.total_trades,
            "profit_factor": result.metrics.profit_factor,
        }

        # Fee-adjusted metrics
        closed = [t for t in trades_data if t.get("exit_price") is not None]
        fee_adj = _compute_metrics_from_pnls(closed, initial_capital=10000.0)

        all_results[label] = {
            "symbol": symbol,
            "interval": interval,
            "period": f"{start}  ->  {end}",
            "parameters": params,
            "raw_metrics": raw,
            "fee_adjusted_metrics": fee_adj,
            "total_signals": len(result.trades),
            "closed_trades": len(closed),
            "exit_reasons": exit_reasons,
            "trades": trades_data,
        }

        # Console summary
        print(f"\n  Raw Metrics:")
        print(f"    Return:     {raw['total_return_pct']:+.2f}%")
        print(f"    Sharpe:     {raw['sharpe_ratio']:.4f}")
        print(f"    Max DD:     {raw['max_drawdown_pct']:.2f}%")
        print(f"    Win Rate:   {raw['win_rate_pct']:.2f}%")
        print(f"    Trades:     {raw['total_trades']}")
        print(f"    Prof Factor:{raw['profit_factor']}")
        print(f"\n  Fee-Adjusted Metrics (0.2% round-trip):")
        print(f"    Return:     {fee_adj['total_return_pct']:+.2f}%")
        print(f"    Sharpe:     {fee_adj['sharpe_ratio']:.4f}")
        print(f"    Max DD:     {fee_adj['max_drawdown_pct']:.2f}%")
        print(f"    Win Rate:   {fee_adj['win_rate_pct']:.2f}%")
        print(f"    Trades:     {fee_adj['total_trades']}")
        print(f"    Prof Factor:{fee_adj['profit_factor']}")
        print(f"\n  Exit Reasons: {exit_reasons}")

    return all_results


# ─── Report ──────────────────────────────────────────────────────────


def _generate_report(results: dict) -> str:
    """Build the H2 markdown summary report."""
    lines: list[str] = []
    a = lines.append

    a("# H2: RSI Divergence with Trend Filter — Backtest Report")
    a("")
    a(f"**Generated**: {datetime.now(UTC).isoformat()}")
    a(f"**Strategy ID**: h2_rsi_divergence_trend")
    a("")

    # Parameter adjustment note
    a("## 0. Parameter Adjustment Note")
    a("")
    a("The spec defaults (`pivot_window=5, min_pivot_spacing=10, oversold_threshold=40`)")
    a("produced only **1 divergence signal** across the entire BTC/USDT 4h dataset.")
    a("This matches the spec's anticipated failure mode: *\"Too few signals: Divergence is rare.\"*")
    a("")
    a("After sweeping the spec's parameter ranges, the following adjusted defaults were")
    a("selected to produce sufficient trade counts for statistical validity:")
    a("")
    a("| Parameter | Spec Default | Adjusted | Rationale |")
    a("|-----------|-------------|----------|-----------|")
    a("| `pivot_window` | 5 | **3** | Smaller window detects more granular pivots |")
    a("| `min_pivot_spacing` | 10 | **5** | Allows closer pivots, more divergence candidates |")
    a("| `oversold_threshold` | 40 | **50** | RSI rarely drops below 40 in uptrends; 50 captures pullbacks |")
    a("")
    a("Result: ~38 potential divergences in BTC training period (vs 1 with spec defaults).")
    a("")

    # Parameters
    a("## 1. Strategy Parameters (Adjusted Defaults)")
    a("")
    a("| Parameter | Value |")
    a("|-----------|-------|")
    for k, v in DEFAULT_PARAMS.items():
        a(f"| `{k}` | `{v}` |")
    a("")
    a("| Interval Override | `max_holding_candles` |")
    a("|-------------------|----------------------|")
    for iv, ov in INTERVAL_OVERRIDES.items():
        a(f"| `{iv}` | `{ov['max_holding_candles']}` |")
    a("")

    # Summary table
    a("## 2. Results Summary")
    a("")
    a("| Config | Raw Ret | Fee-Adj Ret | Sharpe | Max DD | Win% | Trades | PF |")
    a("|--------|--------|------------|--------|--------|------|--------|----|")
    for label, r in results.items():
        if "error" in r:
            a(f"| {label} | ERROR | - | - | - | - | - | - |")
            continue
        raw = r["raw_metrics"]
        adj = r["fee_adjusted_metrics"]
        a(
            f"| {label} | {raw['total_return_pct']:+.2f}% "
            f"| {adj['total_return_pct']:+.2f}% "
            f"| {adj['sharpe_ratio']:.2f} "
            f"| {adj['max_drawdown_pct']:.2f}% "
            f"| {adj['win_rate_pct']:.1f} "
            f"| {adj['total_trades']} "
            f"| {adj['profit_factor']} |"
        )
    a("")

    # Per-config details
    for label, r in results.items():
        a(f"## {label}")
        a("")
        if "error" in r:
            a(f"**Error**: {r['error']}")
            a("")
            continue
        a(f"- **Pair**: {r['symbol']}")
        a(f"- **Interval**: {r['interval']}")
        a(f"- **Period**: {r['period']}")
        a(f"- **Total Signals**: {r['total_signals']}")
        a(f"- **Closed Trades**: {r['closed_trades']}")
        a("")

        a("### Raw Metrics")
        a("")
        for k, v in r["raw_metrics"].items():
            a(f"- **{k}**: {v}")
        a("")

        a("### Fee-Adjusted Metrics")
        a("")
        for k, v in r["fee_adjusted_metrics"].items():
            a(f"- **{k}**: {v}")
        a("")

        a("### Exit Distribution")
        a("")
        for reason, cnt in r["exit_reasons"].items():
            a(f"- **{reason}**: {cnt}")
        a("")

        # Trade table
        if r["trades"]:
            a("### Trade List")
            a("")
            a("| # | Entry Price | Exit Price | Qty | Raw PnL | Fee-Adj PnL | Exit Reason |")
            a("|---|------------|-----------|-----|---------|-------------|-------------|")
            for idx, t in enumerate(r["trades"], 1):
                if t.get("exit_price") is not None:
                    a(
                        f"| {idx} | {t['entry_price']:.2f} "
                        f"| {t['exit_price']:.2f} "
                        f"| {t['quantity']:.6f} "
                        f"| {t.get('pnl', 0):.2f} "
                        f"| {t.get('fee_adjusted_pnl', 0):.2f} "
                        f"| {t.get('exit_reason', 'unknown')} |"
                    )
            a("")

    # Implementation notes
    a("## Implementation Notes")
    a("")
    a("### Edge Cases Handled")
    a("- **Warmup period**: No signals generated until `sma_period + pivot_window + min_pivot_spacing` candles available in the sliding window")
    a("- **RSI None values**: Pivot lows with undefined RSI are skipped in divergence check")
    a("- **Pivot spacing**: Minimum distance between consecutive pivot lows enforced to reduce noise")
    a("- **Position tracking**: Self-managed via `_has_position` flag; one position at a time")
    a("- **Engine force-close**: Any positions still open at backtest end are force-closed at last candle price")
    a("")
    a("### Fee Adjustment")
    a(f"- Round-trip fee: **{ROUND_TRIP_FEE * 100:.1f}%** ({FEE_PER_SIDE * 100:.1f}% per side)")
    a("- Applied post-hoc to all closed trade PnLs")
    a("- Sharpe, drawdown, win rate, and profit factor recalculated from fee-adjusted equity curve")
    a("")
    a("### Known Limitations")
    a("- The engine processes one signal per candle — cannot exit and re-enter on the same bar")
    a("- Position sizing uses fixed 10% of assumed capital, not equity-curve-aware")
    a("- Pivot detection uses strict equality (`<=`) — ties where multiple candles share the same low are all detected")
    a("")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────


def main() -> None:
    print("H2: RSI Divergence with Trend Filter — Backtest Runner")
    print("=" * 60)

    # Run all backtests
    results = run_all_backtests()

    # Output directory
    results_dir = Path(__file__).resolve().parent.parent / "strategy_results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Save detailed JSON
    def _json_default(obj):
        if isinstance(obj, float) and math.isinf(obj):
            return "inf"
        raise TypeError(f"Not JSON serializable: {type(obj)}")

    detail_path = results_dir / "H2-detailed-results.json"
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=_json_default)
    print(f"\nDetailed results -> {detail_path}")

    # Save report
    report = _generate_report(results)
    report_path = results_dir / "H2-report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report           -> {report_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
