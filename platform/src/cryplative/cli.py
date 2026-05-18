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
        "total_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "total_trades",
        "profit_factor",
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
        False,
        "--verbose",
        help="Show default parameters for each strategy",
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
def pairs(
    quote: str = typer.Option(None, help="Filter by quote currency (e.g., USDT, USDC)"),
    active_only: bool = typer.Option(True, help="Exclude delisted/inactive pairs"),
) -> None:
    """List available trading pairs on the exchange.

    Displays a table of trading pairs with their base/quote currencies
    and trading constraints.

    Examples:
        cryplative pairs                     # All active pairs
        cryplative pairs --quote USDT        # Only USDT pairs
        cryplative pairs --quote USDC        # Only USDC pairs
        cryplative pairs --no-active-only    # Include delisted pairs
    """
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.market_fetcher.fetcher import MarketFetcher

    try:
        fetcher = MarketFetcher(config)
        pairs_list = fetcher.list_pairs(quote=quote, active_only=active_only)

        if not pairs_list:
            console.print("[yellow]No pairs found matching your criteria.[/yellow]")
            return

        # Build table
        table = Table(title="Available Trading Pairs")
        table.add_column("Symbol", style="cyan", no_wrap=True)
        table.add_column("Base", style="green")
        table.add_column("Quote", style="green")
        table.add_column("Min Order Size", justify="right", style="dim")

        for pair in pairs_list:
            min_size = pair["min_order_size"]
            if min_size is not None:
                min_size_str = f"{min_size:.8f}".rstrip("0").rstrip(".")
            else:
                min_size_str = "N/A"
            table.add_row(
                pair["symbol"],
                pair["base"],
                pair["quote"],
                min_size_str,
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(pairs_list)} pairs[/dim]")

    except Exception as e:
        console.print(f"[red]Error fetching pairs: {e}[/red]")
        raise typer.Exit(1) from None


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
    capital: Annotated[float, typer.Option("--capital", help="Initial capital")] = 10000.0,
    params: str = typer.Option(
        "{}",
        "--params",
        help="Strategy parameters as JSON string or path to JSON file",
    ),
    max_positions: int = typer.Option(
        1,
        "--max-positions",
        help="Maximum concurrent open positions",
    ),
    catalog_flag: bool = typer.Option(
        False, "--catalog", help="Save result to the strategy catalog after backtest"
    ),
    hypothesis: str | None = typer.Option(
        None, "--hypothesis", help="Hypothesis ID tag (e.g., H2)"
    ),
    experiment: str | None = typer.Option(
        None, "--experiment", help="Experiment batch ID (e.g., sweep_20260518)"
    ),
    data_split: str = typer.Option(
        "FULL", "--data-split", help="Data split: TRAIN, TEST, FULL, OUT_OF_SAMPLE"
    ),
    train_result: int | None = typer.Option(
        None, "--train-result", help="ID of the training result (for TEST splits)"
    ),
    verdict: str | None = typer.Option(
        None, "--verdict", help="Verdict tag: PASS, FAIL, or MARGINAL"
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
    pf_str = f"{metrics.profit_factor:.2f}" if metrics.profit_factor != float("inf") else "∞"
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
            pnl_pct = f"{trade.pnl_percentage:+.2f}%" if trade.pnl_percentage is not None else "-"

            pnl_color = (
                "green"
                if trade.pnl and trade.pnl > 0
                else ("red" if trade.pnl and trade.pnl < 0 else "dim")
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

    # Catalog integration
    if catalog_flag:
        from cryplative.catalog import ResultsCatalog

        cat = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
        try:
            saved_path = ResultsCatalog.build_results_path(
                strategy_id=strategy,
                symbol=symbol,
                interval=interval,
                start_date=start,
                end_date=end,
            )
            row_id = cat.insert_from_strategy_result(
                result=result,
                symbol=symbol,
                interval=interval,
                results_file=saved_path,
                hypothesis_id=hypothesis,
                experiment_id=experiment,
                data_split=data_split,
                train_result_id=train_result,
                verdict=verdict,
            )
            console.print(
                f"[green]Result cataloged as #{row_id} "
                f"({strategy}, {symbol}, {interval}, split={data_split})[/green]"
            )
        except Exception as e:
            console.print(f"[red]Catalog insert failed: {e}[/red]")
        finally:
            cat.close()


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


# ---------------------------------------------------------------------------
# Results catalog subcommands
# ---------------------------------------------------------------------------

results_app = typer.Typer(help="Query and manage the strategy results catalog.")
app.add_typer(results_app, name="results")


@results_app.command("list")
def results_list(
    strategy: str | None = typer.Option(None, "--strategy", help="Filter by strategy ID"),
    hypothesis: str | None = typer.Option(None, "--hypothesis", help="Filter by hypothesis ID"),
    experiment: str | None = typer.Option(None, "--experiment", help="Filter by experiment ID"),
    symbol: str | None = typer.Option(None, "--symbol", help="Filter by trading pair"),
    interval: str | None = typer.Option(None, "--interval", help="Filter by interval"),
    verdict: str | None = typer.Option(None, "--verdict", help="Filter by verdict"),
    data_split: str | None = typer.Option(None, "--data-split", help="Filter by data split"),
    min_sharpe: float | None = typer.Option(None, "--min-sharpe", help="Minimum Sharpe ratio"),
    min_return: float | None = typer.Option(None, "--min-return", help="Minimum return (%)"),
    limit: int = typer.Option(20, "--limit", help="Max results to show"),
) -> None:
    """List strategy results from the catalog."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        results = catalog.find(
            strategy_id=strategy,
            hypothesis_id=hypothesis,
            experiment_id=experiment,
            symbol=symbol,
            interval=interval,
            verdict=verdict,
            data_split=data_split,
            min_sharpe=min_sharpe,
            min_return_pct=min_return,
        )

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return

        total = len(results)
        display = results[:limit]

        table = Table(title="Strategy Results")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Strategy", style="cyan", no_wrap=True, max_width=22)
        table.add_column("Hyp", width=4)
        table.add_column("Symbol", width=12)
        table.add_column("TF", width=4)
        table.add_column("Split", width=6)
        table.add_column("Return", justify="right", width=8)
        table.add_column("Sharpe", justify="right", width=8)
        table.add_column("Verdict", width=8)

        for entry in display:
            ret_str = (
                f"{entry.total_return_pct:+.2f}%" if entry.total_return_pct is not None else "-"
            )
            ret_color = (
                "green"
                if entry.total_return_pct is not None and entry.total_return_pct >= 0
                else "red"
            )
            sharpe_str = f"{entry.sharpe_ratio:.2f}" if entry.sharpe_ratio is not None else "-"
            sharpe_display = (
                f"[bold]{sharpe_str}[/bold]"
                if entry.sharpe_ratio is not None and entry.sharpe_ratio > 1.0
                else sharpe_str
            )
            hyp = entry.hypothesis_id or "-"
            verdict_str = entry.verdict or "-"

            table.add_row(
                str(entry.id),
                entry.strategy_id,
                hyp,
                entry.symbol,
                entry.interval,
                entry.data_split,
                f"[{ret_color}]{ret_str}[/{ret_color}]",
                sharpe_display,
                verdict_str,
            )

        console.print(table)
        if total > limit:
            console.print(
                f"\n[dim]Showing {limit} of {total} results. Use --limit to show more.[/dim]"
            )
    finally:
        catalog.close()


@results_app.command("best")
def results_best(
    metric: str = typer.Option("sharpe_ratio", "--metric", help="Metric to rank by"),
    top: int = typer.Option(10, "--top", help="Number of top results"),
    strategy: str | None = typer.Option(None, "--strategy", help="Filter by strategy"),
    symbol: str | None = typer.Option(None, "--symbol", help="Filter by symbol"),
    hypothesis: str | None = typer.Option(None, "--hypothesis", help="Filter by hypothesis"),
    data_split: str | None = typer.Option(None, "--data-split", help="Filter by data split"),
) -> None:
    """Show top N results by a given metric."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        results = catalog.best(
            metric=metric,
            n=top,
            strategy_id=strategy,
            symbol=symbol,
            hypothesis_id=hypothesis,
            data_split=data_split,
        )

        split_info = f" (data_split={data_split})" if data_split else ""
        console.print(f"\n[bold]Top {top} by {metric}{split_info}:[/bold]")

        table = Table()
        table.add_column("ID", style="dim", width=4)
        table.add_column("Strategy", style="cyan", no_wrap=True, max_width=22)
        table.add_column("Symbol", width=12)
        table.add_column("Split", width=6)
        table.add_column("Return", justify="right", width=8)
        table.add_column("Metric", justify="right", width=8)

        for entry in results:
            ret_str = (
                f"{entry.total_return_pct:+.2f}%" if entry.total_return_pct is not None else "-"
            )
            metric_val = getattr(entry, metric, None)
            metric_str = f"{metric_val:.2f}" if metric_val is not None else "-"

            table.add_row(
                str(entry.id),
                entry.strategy_id,
                entry.symbol,
                entry.data_split,
                ret_str,
                metric_str,
            )

        console.print(table)
    finally:
        catalog.close()


@results_app.command("show")
def results_show(
    result_id: int = typer.Argument(help="Result ID to display"),
) -> None:
    """Display full details of a single result."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        entry = catalog.get(result_id)
        if entry is None:
            console.print(f"[red]Result #{result_id} not found.[/red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]Result #{entry.id}[/bold]")
        console.print("=" * 50)
        console.print(f"  Strategy:        {entry.strategy_id}")
        if entry.hypothesis_id:
            console.print(f"  Hypothesis:      {entry.hypothesis_id}")
        if entry.experiment_id:
            console.print(f"  Experiment:      {entry.experiment_id}")
        console.print(f"  Data Split:      {entry.data_split}")
        if entry.train_result_id:
            console.print(f"  Train Result:    #{entry.train_result_id}")
        console.print(f"  Symbol:          {entry.symbol}")
        console.print(f"  Interval:        {entry.interval}")
        console.print(f"  Period:          {entry.start_date} to {entry.end_date}")

        console.print("\n[bold]Metrics:[/bold]")
        ret_str = f"{entry.total_return_pct:+.2f}%" if entry.total_return_pct is not None else "-"
        console.print(f"  Return:          {ret_str}")
        sharpe_str = f"{entry.sharpe_ratio:.2f}" if entry.sharpe_ratio is not None else "-"
        console.print(f"  Sharpe:          {sharpe_str}")
        dd_str = f"{entry.max_drawdown_pct:.2f}%" if entry.max_drawdown_pct is not None else "-"
        console.print(f"  Max Drawdown:    {dd_str}")
        wr_str = f"{entry.win_rate_pct:.1f}%" if entry.win_rate_pct is not None else "-"
        console.print(f"  Win Rate:        {wr_str}")
        console.print(f"  Trades:          {entry.total_trades}")
        pf_str = f"{entry.profit_factor:.2f}" if entry.profit_factor is not None else "-"
        console.print(f"  Profit Factor:   {pf_str}")
        fees_str = (
            "Yes"
            if entry.fees_included is True
            else "No"
            if entry.fees_included is False
            else "Unknown"
        )
        console.print(f"  Fees Included:   {fees_str}")

        if entry.verdict:
            console.print(f"\n  Verdict:         {entry.verdict}")
        if entry.notes:
            console.print(f"  Notes:           {entry.notes}")
        console.print(f"  File:            {entry.results_file}")

        if entry.parameters:
            console.print("\n[bold]Parameters:[/bold]")
            for k, v in entry.parameters.items():
                console.print(f"  {k}: {v}")
    finally:
        catalog.close()


@results_app.command("compare")
def results_compare(
    hypothesis_ids: list[str] = typer.Argument(help="Hypothesis IDs to compare"),  # noqa: B008
    metric: str = typer.Option("sharpe_ratio", "--metric", help="Metric to compare"),
    data_split: str | None = typer.Option("TEST", "--data-split", help="Data split filter"),
) -> None:
    """Compare results across multiple hypotheses."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        comparison = catalog.compare_hypotheses(
            hypothesis_ids, metric=metric, data_split=data_split
        )

        split_info = f", data_split={data_split}" if data_split else ""
        hyps_str = " vs ".join(hypothesis_ids)
        console.print(f"\n[bold]Comparing {hyps_str} (metric={metric}{split_info}):[/bold]\n")

        summaries: dict[str, dict[str, float]] = {}

        for hyp_id, entries in comparison.items():
            console.print(f"[bold]── {hyp_id} ({len(entries)} results) ──[/bold]")
            if entries:
                best_metric_val = getattr(entries[0], metric, None)
                best_str = f"{best_metric_val:.2f}" if best_metric_val is not None else "-"
                console.print(
                    f"  Best {metric}:  {best_str} "
                    f"({entries[0].strategy_id}, {entries[0].symbol}, {entries[0].interval})"
                )
                returns = [e.total_return_pct for e in entries if e.total_return_pct is not None]
                avg_ret = sum(returns) / len(returns) if returns else 0.0
                console.print(f"  Avg Return:   {avg_ret:+.2f}%")

                metrics_vals = [
                    getattr(e, metric) for e in entries if getattr(e, metric) is not None
                ]
                avg_metric = sum(metrics_vals) / len(metrics_vals) if metrics_vals else 0.0
                console.print(f"  Avg {metric}: {avg_metric:.2f}")

                pass_count = sum(1 for e in entries if e.verdict == "PASS")
                total_count = len(entries)
                pass_rate = (pass_count / total_count * 100) if total_count > 0 else 0
                console.print(f"  Pass rate:    {pass_rate:.0f}% ({pass_count}/{total_count})")

                summaries[hyp_id] = {
                    "avg_return": avg_ret,
                    "avg_metric": avg_metric,
                    "pass_rate": pass_rate,
                }
            else:
                console.print("  No results found.")
                summaries[hyp_id] = {"avg_return": 0, "avg_metric": 0, "pass_rate": 0}

            console.print()

        # Summary comparison
        if len(summaries) >= 2:
            console.print("[bold]── Summary ──[/bold]")
            ids = list(summaries.keys())
            best_ret = max(ids, key=lambda h: summaries[h]["avg_return"])
            best_met = max(ids, key=lambda h: summaries[h]["avg_metric"])
            best_pass = max(ids, key=lambda h: summaries[h]["pass_rate"])

            console.print(
                f"  Better avg {metric}:    "
                f"{best_met} ({summaries[best_met]['avg_metric']:.2f} vs "
                f"{summaries[ids[1] if best_met == ids[0] else ids[0]]['avg_metric']:.2f})"
            )
            console.print(
                f"  Better avg Return:    "
                f"{best_ret} ({summaries[best_ret]['avg_return']:.2f}% vs "
                f"{summaries[ids[1] if best_ret == ids[0] else ids[0]]['avg_return']:.2f}%)"
            )
            console.print(
                f"  Better pass rate:     "
                f"{best_pass} ({summaries[best_pass]['pass_rate']:.0f}% vs "
                f"{summaries[ids[1] if best_pass == ids[0] else ids[0]]['pass_rate']:.0f}%)"
            )
    finally:
        catalog.close()


@results_app.command("summary")
def results_summary() -> None:
    """Show catalog overview."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        s = catalog.summary()

        console.print(f"\n[bold]Strategy Results Catalog[/bold] — {config.data_dir}/catalog.db")
        console.print("=" * 50)
        console.print(f"  Total results:     {s.total_results}")
        console.print(f"  Strategies:        {', '.join(s.unique_strategies)}")
        console.print(f"  Hypotheses:        {', '.join(s.unique_hypotheses)}")
        console.print(f"  Symbols:           {', '.join(s.unique_symbols)}")

        if s.data_split_counts:
            console.print("\n  [bold]Data Splits:[/bold]")
            for split, count in sorted(s.data_split_counts.items()):
                console.print(f"    {split}:           {count}")

        if s.verdict_counts:
            console.print("\n  [bold]Verdicts:[/bold]")
            for verdict, count in sorted(
                s.verdict_counts.items(), key=lambda x: (x[0] is None, x[0] or "")
            ):
                label = verdict if verdict else "(none)"
                console.print(f"    {label}:     {count}")

        if s.best_by_metric:
            console.print("\n  [bold]Best by metric:[/bold]")
            for metric_name, entry in s.best_by_metric.items():
                val = getattr(entry, metric_name)
                val_str = f"{val:.2f}" if val is not None else "-"
                display_name = metric_name.replace("_pct", "").replace("_", " ").title()
                console.print(
                    f"    {display_name}:   {val_str}  "
                    f"({entry.strategy_id}, {entry.symbol}, {entry.interval})"
                )
    finally:
        catalog.close()


@results_app.command("rebuild")
def results_rebuild(
    results_dir: str | None = typer.Option(None, "--results-dir", help="Results directory path"),
) -> None:
    """Rebuild catalog by scanning strategy results directory."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        scan_dir = results_dir or str(config.resolve_strategy_results_dir())
        r = catalog.rebuild(results_dir=scan_dir)

        parts = [f"Indexed {r.indexed} new results"]
        if r.skipped_existing:
            parts.append(f"{r.skipped_existing} already indexed")
        if r.skipped_parse_error:
            error_names = [e.split(":")[0] for e in r.errors]
            parts.append(f"{r.skipped_parse_error} skipped: {', '.join(error_names)}")

        console.print(f"[green]{' ('.join(parts)}{')' if len(parts) > 1 else ''}[/green]")

        total = len(catalog.find())
        console.print(f"[dim]Total catalog entries: {total}[/dim]")
    finally:
        catalog.close()


@results_app.command("tag")
def results_tag(
    result_id: int = typer.Argument(help="Result ID to tag"),
    hypothesis: str | None = typer.Option(None, "--hypothesis", help="Hypothesis ID"),
    experiment: str | None = typer.Option(None, "--experiment", help="Experiment ID"),
    verdict: str | None = typer.Option(None, "--verdict", help="Verdict: PASS, FAIL, MARGINAL"),
    notes: str | None = typer.Option(None, "--notes", help="Free-form notes"),
) -> None:
    """Tag a result with hypothesis, experiment, verdict, or notes."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        entry = catalog.get(result_id)
        if entry is None:
            console.print(f"[red]Result #{result_id} not found.[/red]")
            raise typer.Exit(1)

        success = catalog.tag(
            result_id,
            hypothesis_id=hypothesis,
            experiment_id=experiment,
            verdict=verdict,
            notes=notes,
        )

        if success:
            updates = []
            if hypothesis:
                updates.append(f"hypothesis={hypothesis}")
            if experiment:
                updates.append(f"experiment={experiment}")
            if verdict:
                updates.append(f"verdict={verdict}")
            if notes:
                updates.append(f"notes={notes}")
            update_str = ", ".join(updates)
            console.print(f"[green]Updated result #{result_id}: {update_str}[/green]")
        else:
            console.print(f"[red]Failed to update result #{result_id}.[/red]")
    finally:
        catalog.close()


@results_app.command("delete")
def results_delete(
    result_id: int = typer.Argument(help="Result ID to delete"),
) -> None:
    """Delete a result from the catalog (does NOT delete the JSON file)."""
    config = CryplativeConfig()
    setup_logging(config)

    from cryplative.catalog import ResultsCatalog

    catalog = ResultsCatalog(db_path=str(config.resolve_data_dir() / "catalog.db"))
    try:
        entry = catalog.get(result_id)
        if entry is None:
            console.print(f"[red]Result #{result_id} not found.[/red]")
            raise typer.Exit(1)

        deleted = catalog.delete(result_id)
        if deleted:
            console.print(
                f"[green]Deleted result #{result_id} "
                f"({entry.strategy_id}, {entry.symbol}, {entry.interval})[/green]"
            )
        else:
            console.print(f"[red]Failed to delete result #{result_id}.[/red]")
    finally:
        catalog.close()


if __name__ == "__main__":
    app()
