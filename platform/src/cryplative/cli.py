"""CLI entry point for Cryplative.

Provides commands for backtesting, data fetching, and strategy management.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from cryplative.config import CryplativeConfig, setup_logging

app = typer.Typer(
    name="cryplative",
    help="Cryplative - An agentic crypto trading platform",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------
# Shared validation
# ---------------------------------------------------------------------------

VALID_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}


def _validate_symbol(symbol: str) -> str:
    """Validate symbol format (e.g., BTC/USDT)."""
    if not re.match(r"^[A-Z]+/[A-Z]+$", symbol):
        console.print(
            f"[red]Invalid symbol format: '{symbol}'. Expected format: BASE/QUOTE "
            "(e.g., BTC/USDT).[/red]"
        )
        raise typer.Exit(1)
    return symbol


def _validate_interval(interval: str) -> str:
    """Validate candle interval."""
    if interval not in VALID_INTERVALS:
        console.print(
            f"[red]Invalid interval: '{interval}'. "
            f"Valid options: {', '.join(sorted(VALID_INTERVALS))}[/red]"
        )
        raise typer.Exit(1)
    return interval


def _validate_date(date_str: str, name: str = "date") -> str:
    """Validate ISO 8601 date format."""
    try:
        datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        console.print(
            f"[red]Invalid {name} format: '{date_str}'. "
            "Expected ISO 8601 (e.g., 2025-01-01 or 2025-01-01T00:00:00Z).[/red]"
        )
        raise typer.Exit(1) from None
    return date_str


# ---------------------------------------------------------------------------
# Comparison logic (testable pure functions)
# ---------------------------------------------------------------------------


def load_strategy_results(
    files: list[str],
) -> list[tuple[str, dict[str, Any]]]:
    """Load strategy results from JSON files.

    Returns a list of (filename, metrics_dict) tuples.
    Skips files that can't be loaded and returns them as errors.
    """
    results: list[tuple[str, dict[str, Any]]] = []
    for filepath in files:
        try:
            path = Path(filepath)
            data = json.loads(path.read_text(encoding="utf-8"))
            metrics = data.get("metrics", {})
            strategy_id = data.get("strategy_id", "unknown")
            results.append((strategy_id, metrics))
        except (json.JSONDecodeError, OSError, KeyError) as e:
            console.print(f"[yellow]Warning: Skipping {filepath}: {e}[/yellow]")
    return results


def build_comparison_data(
    results: list[tuple[str, dict[str, Any]]],
) -> tuple[list[str], list[str], list[list[str]]]:
    """Build comparison table data from loaded results.

    Returns (metrics, strategy_names, rows).
    """
    if not results:
        return [], [], []

    metrics = [
        "total_return", "sharpe_ratio", "max_drawdown",
        "win_rate", "total_trades", "profit_factor",
    ]
    strategy_names = [name for name, _ in results]
    rows: list[list[str]] = []

    for metric in metrics:
        row: list[str] = []
        for _, m in results:
            val = m.get(metric, 0)
            # Handle infinity values from JSON serialization
            if val == float("inf") or val == float("-inf") or val is None:
                val = 0
            if metric == "total_return":
                row.append(f"{val:+.2f}%")
            elif metric == "win_rate":
                row.append(f"{val:.1f}%")
            elif metric == "max_drawdown":
                row.append(f"{val:.2f}%")
            elif metric == "profit_factor":
                if val == float("inf"):
                    row.append("inf")
                else:
                    row.append(f"{val:.2f}")
            elif metric in ("sharpe_ratio",):
                row.append(f"{val:.2f}")
            else:
                row.append(str(val))
        rows.append(row)

    return metrics, strategy_names, rows


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def strategies(
    verbose: bool = typer.Option(
        False, "--verbose", help="Show default parameters for each strategy",
    ),
) -> None:
    """List all registered strategies."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.strategies import StrategyRegistry  # noqa: F811

    strategy_ids = StrategyRegistry.list_strategies()

    if not strategy_ids:
        console.print("[yellow]No strategies registered.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Registered Strategies")
    table.add_column("Strategy ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")

    if verbose:
        table.add_column("Default Parameters", style="dim")

    for sid in sorted(strategy_ids):
        try:
            cls = StrategyRegistry.get(sid)
            instance = cls.__new__(cls)
            name = instance.strategy_name

            if verbose:
                default_params = cls.default_parameters()
                if default_params:
                    params_str = ", ".join(f"{k}={v}" for k, v in default_params.items())
                    table.add_row(sid, name, params_str)
                else:
                    table.add_row(sid, name, "-")
            else:
                table.add_row(sid, name)
        except Exception:
            if verbose:
                table.add_row(sid, "[red]Error loading[/red]", "-")
            else:
                table.add_row(sid, "[red]Error loading[/red]")

    console.print(table)


@app.command()
def fetch(
    symbol: Annotated[str, typer.Option("--symbol", help="Trading pair (e.g., BTC/USDT)")],
    interval: Annotated[str, typer.Option("--interval", help="Candle interval (e.g., 1h, 4h, 1d)")],
    start: Annotated[str, typer.Option("--start", help="Start date (ISO 8601, e.g., 2025-01-01)")],
    end: Annotated[str, typer.Option("--end", help="End date (ISO 8601, e.g., 2025-06-01)")],
) -> None:
    """Fetch and cache market data from the exchange."""
    config = CryplativeConfig()
    setup_logging(config)

    _validate_symbol(symbol)
    _validate_interval(interval)
    _validate_date(start, "--start")
    _validate_date(end, "--end")

    from cryplative.market_fetcher.fetcher import MarketFetcher

    console.print(f"[bold]Fetching {symbol} {interval} data...[/bold]")

    fetcher = MarketFetcher(config)

    # Parse dates
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    candles = fetcher.get_candles(
        symbol=symbol,
        interval=interval,
        start_time=start_ms,
        end_time=end_ms,
    )

    if not candles:
        console.print(f"[yellow]No candles found for {symbol} {interval}[/yellow]")
        raise typer.Exit(1)

    table = Table(title="Fetched Data Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    first_date = datetime.fromtimestamp(candles[0].open_time / 1000, tz=UTC)
    last_date = datetime.fromtimestamp(candles[-1].open_time / 1000, tz=UTC)

    table.add_row("Symbol", symbol)
    table.add_row("Interval", interval)
    table.add_row("Candles", str(len(candles)))
    table.add_row("Start", first_date.strftime("%Y-%m-%d %H:%M UTC"))
    table.add_row("End", last_date.strftime("%Y-%m-%d %H:%M UTC"))
    table.add_row("First Close", f"{candles[0].close:.2f}")
    table.add_row("Last Close", f"{candles[-1].close:.2f}")

    console.print(table)
    console.print(f"[dim]Data cached to {config.resolve_market_cache_dir()}[/dim]")


@app.command()
def backtest(
    strategy: Annotated[str, typer.Option("--strategy", help="Strategy ID")],
    symbol: Annotated[str, typer.Option("--symbol", help="Trading pair (e.g., BTC/USDT)")],
    interval: Annotated[str, typer.Option("--interval", help="Candle interval (e.g., 1h, 4h, 1d)")],
    start: Annotated[str, typer.Option("--start", help="Start date (ISO 8601)")],
    end: Annotated[str, typer.Option("--end", help="End date (ISO 8601)")],
    capital: Annotated[
        float, typer.Option("--capital", help="Initial capital")
    ] = 10000.0,
    params: str = typer.Option(
        "{}", "--params",
        help="Strategy parameters as JSON string or path to JSON file",
    ),
    max_positions: int = typer.Option(
        1, "--max-positions", help="Maximum concurrent open positions",
    ),
) -> None:
    """Run a backtest with a strategy against historical data."""
    config = CryplativeConfig()
    setup_logging(config)

    # Validate inputs
    _validate_symbol(symbol)
    _validate_interval(interval)
    _validate_date(start, "--start")
    _validate_date(end, "--end")

    if capital <= 0:
        console.print("[red]Capital must be a positive number.[/red]")
        raise typer.Exit(1)

    from cryplative.strategies import StrategyRegistry  # noqa: F811

    if strategy not in StrategyRegistry.list_strategies():
        available = StrategyRegistry.list_strategies()
        console.print(
            f"[red]Strategy '{strategy}' not found.[/red] "
            f"Available strategies: {', '.join(sorted(available))}"
        )
        raise typer.Exit(1)

    from cryplative.backtesting.engine import BacktestConfig, BacktestEngine
    from cryplative.market_fetcher.fetcher import MarketFetcher

    # Parse parameters: JSON string or file path
    strategy_params: dict[str, object] = {}
    if params:
        params_source = params.strip()
        if params_source.endswith(".json"):
            try:
                params_path = Path(params_source)
                strategy_params = json.loads(params_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                console.print(f"[red]Error reading params file: {e}[/red]")
                raise typer.Exit(1) from None
        else:
            try:
                strategy_params = json.loads(params_source)
            except json.JSONDecodeError as e:
                console.print(f"[red]Invalid JSON in --params: {e}[/red]")
                raise typer.Exit(1) from None

    console.print(f"[bold]Running backtest: {strategy} on {symbol} {interval}...[/bold]")

    # Initialize components
    fetcher = MarketFetcher(config)
    engine = BacktestEngine(fetcher, config)

    backtest_config = BacktestConfig(
        strategy_id=strategy,
        symbol=symbol,
        interval=interval,
        start_date=start,
        end_date=end,
        initial_capital=capital,
        parameters=strategy_params,
        max_positions=max_positions,
    )

    try:
        result = engine.run(backtest_config)
    except Exception as e:
        console.print(f"[red]Backtest failed: {e}[/red]")
        raise typer.Exit(1) from None

    # Display results table
    metrics = result.metrics

    table = Table(title=f"Backtest Results — {strategy}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Strategy", strategy)
    table.add_row("Symbol", symbol)
    table.add_row("Interval", interval)
    table.add_row("Period", f"{start} → {end}")
    table.add_row("Initial Capital", f"${capital:,.2f}")
    table.add_row("Max Positions", str(max_positions))

    return_color = "green" if metrics.total_return >= 0 else "red"
    table.add_row(
        "Total Return",
        f"[{return_color}]{metrics.total_return:+.2f}%[/{return_color}]",
    )
    table.add_row("Sharpe Ratio", f"{metrics.sharpe_ratio:.2f}")
    table.add_row("Max Drawdown", f"{metrics.max_drawdown:.2f}%")
    table.add_row("Win Rate", f"{metrics.win_rate:.1f}%")
    table.add_row("Total Trades", str(metrics.total_trades))
    pf_str = (
        f"{metrics.profit_factor:.2f}"
        if metrics.profit_factor != float("inf")
        else "∞"
    )
    table.add_row("Profit Factor", pf_str)

    console.print(table)

    # Show trades table if any
    if result.trades:
        trades_table = Table(title="Trades")
        trades_table.add_column("#", style="dim", width=4)
        trades_table.add_column("Type", width=6)
        trades_table.add_column("Entry", justify="right")
        trades_table.add_column("Exit", justify="right")
        trades_table.add_column("PnL", justify="right")
        trades_table.add_column("PnL %", justify="right")

        for i, trade in enumerate(result.trades):
            direction = trade.signal.direction.value
            entry = f"{trade.entry_price:.2f}"
            exit_str = f"{trade.exit_price:.2f}" if trade.exit_price else "-"
            pnl_str = f"{trade.pnl:+.2f}" if trade.pnl is not None else "-"
            pnl_pct = (
                f"{trade.pnl_percentage:+.2f}%"
                if trade.pnl_percentage is not None
                else "-"
            )

            pnl_color = "green" if trade.pnl and trade.pnl > 0 else (
                "red" if trade.pnl and trade.pnl < 0 else "dim"
            )

            trades_table.add_row(
                str(i + 1),
                direction,
                entry,
                exit_str,
                f"[{pnl_color}]{pnl_str}[/{pnl_color}]",
                f"[{pnl_color}]{pnl_pct}[/{pnl_color}]",
            )

        console.print(trades_table)

    # Save location
    results_dir = config.resolve_strategy_results_dir()
    console.print(f"\n[dim]Full results saved to {results_dir}/[/dim]")


@app.command("compare")
def compare_cmd(
    files: list[str] = typer.Argument(help="Paths to strategy result JSON files"),  # noqa: B008
) -> None:
    """Compare backtest results from multiple result files."""
    config = CryplativeConfig()
    setup_logging(config)

    if not files:
        console.print("[red]No files specified.[/red]")
        raise typer.Exit(1)
    """Compare backtest results from multiple result files."""
    config = CryplativeConfig()
    setup_logging(config)

    results = load_strategy_results(files)

    if not results:
        console.print("[red]No valid result files found.[/red]")
        raise typer.Exit(1)

    metric_names, strategy_names, rows = build_comparison_data(results)

    table = Table(title="Strategy Comparison")

    # Header row
    table.add_column("Metric", style="cyan")
    for name in strategy_names:
        table.add_column(name, justify="right")

    # Closer-to-zero-is-better (max_drawdown is negative, less negative = better)
    closer_to_zero = {"max_drawdown"}

    for metric, row in zip(metric_names, rows, strict=True):
        if metric == "total_trades":
            # Neutral — no color coding
            table.add_row(metric.replace("_", " ").title(), *row)
            continue

        # Determine best and worst for color coding
        values = []
        for _, m in results:
            values.append(m.get(metric, 0))

        if metric in closer_to_zero:
            # Max drawdown: closer to 0 is better
            best_idx = values.index(max(values))
            worst_idx = values.index(min(values))
        else:
            best_idx = values.index(max(values))
            worst_idx = values.index(min(values))

        styled_row: list[str] = []
        for j, cell in enumerate(row):
            if j == best_idx:
                styled_row.append(f"[green]{cell}[/green]")
            elif j == worst_idx:
                styled_row.append(f"[red]{cell}[/red]")
            else:
                styled_row.append(cell)

        table.add_row(metric.replace("_", " ").title(), *styled_row)

    console.print(table)


def _snake_to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def _snake_to_title(name: str) -> str:
    """Convert snake_case to Title Case."""
    return " ".join(word.capitalize() for word in name.split("_"))


@app.command()
def new_strategy(name: str) -> None:
    """Scaffold a new strategy from the template.

    Creates a new strategy file with boilerplate code and
    registers it for immediate use.
    """
    # Validate name format
    if not re.match(r"^[a-z][a-z0-9_]*$", name):
        console.print(
            f"[red]Invalid strategy name '{name}'. "
            "Use lowercase letters, numbers, and underscores (must start with a letter).[/red]"
        )
        raise typer.Exit(1)

    strategies_dir = Path(__file__).resolve().parent / "strategies"
    target_file = strategies_dir / f"{name}.py"

    if target_file.exists():
        console.print(
            f"[red]Strategy file already exists: {target_file}[/red]\n"
            f"Choose a different name or delete the existing file."
        )
        raise typer.Exit(1)

    # Read template
    template_file = strategies_dir / "_template.py"
    if not template_file.exists():
        console.print("[red]Template file not found: _template.py[/red]")
        raise typer.Exit(1)

    template_content = template_file.read_text(encoding="utf-8")

    # Replace placeholders
    class_name = _snake_to_pascal(name)
    template_content = template_content.replace(
        "class TemplateStrategy(Strategy):", f"class {class_name}(Strategy):"
    )
    template_content = template_content.replace(
        'return "<PLACEHOLDER: unique_id>"',
        f'return "{name}"',
    )
    template_content = template_content.replace(
        'return "<PLACEHOLDER: Human-readable name>"',
        f'return "{_snake_to_title(name)}"',
    )
    template_content = template_content.replace(
        '"""<PLACEHOLDER: One-line description of your strategy>"""',
        f'"""{_snake_to_title(name)} strategy."""',
    )

    # Add the @StrategyRegistry.register decorator
    template_content = template_content.replace(
        "# NOTE: Do NOT add @StrategyRegistry.register here.",
        "@StrategyRegistry.register",
    )
    template_content = template_content.replace(
        '# This is a template file only. Auto-discovery skips files starting with "_".',
        "",
    )

    target_file.write_text(template_content, encoding="utf-8")

    console.print(f"[green]Created strategy: {name}[/green]")
    console.print(f"[dim]File: {target_file}[/dim]")
    console.print(
        "\nNext steps:\n"
        f"  1. Edit the file and implement generate_signal()\n"
        f"  2. Run: cryplative backtest --strategy {name} "
        "--symbol BTC/USDT --interval 1h --start 2025-01-01 --end 2025-06-01"
    )


if __name__ == "__main__":
    app()
