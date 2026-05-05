"""CLI entry point for Cryplative.

Provides commands for backtesting, data fetching, and strategy management.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

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


@app.command()
def strategies() -> None:
    """List all registered strategies."""
    config = CryplativeConfig()
    setup_logging(config)

    # Import strategies to trigger registration
    from cryplative.strategies import StrategyRegistry  # noqa: F811

    strategy_ids = StrategyRegistry.list_strategies()

    if not strategy_ids:
        console.print("[yellow]No strategies registered.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Registered Strategies")
    table.add_column("Strategy ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="green")
    table.add_column("Version", style="dim")

    for sid in sorted(strategy_ids):
        try:
            cls = StrategyRegistry.get(sid)
            instance = cls.__new__(cls)
            name = instance.strategy_name
            table.add_row(sid, name, "1.0.0")
        except Exception:
            table.add_row(sid, "[red]Error loading[/red]", "-")

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
    params: str = typer.Option(None, "--params", help="Strategy parameters as JSON string"),
) -> None:
    """Run a backtest with a strategy against historical data."""
    config = CryplativeConfig()
    setup_logging(config)

    # Import strategies to trigger registration

    from cryplative.backtesting.engine import BacktestConfig, BacktestEngine
    from cryplative.market_fetcher.fetcher import MarketFetcher

    # Parse parameters
    strategy_params: dict[str, object] = {}
    if params:
        try:
            strategy_params = json.loads(params)
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
        "# This is a template file only. Auto-discovery skips files starting with \"_\".",
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
