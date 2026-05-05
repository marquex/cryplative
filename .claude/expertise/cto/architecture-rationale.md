# CTO Expertise — Architecture Rationale & Decisions
# Agent: cto
# Created: 2026-05-04

## Source Material
All architectural understanding is derived from `bootstrap.md` — the project's foundational vision document.

## Technology Stack Decisions

### Python for the Trading Platform
- **Why**: Rich ecosystem for data analysis (pandas, numpy), backtesting (backtrader, vectorbt), and trading (ccxt, python-binance)
- **Trade-off**: Slower runtime than compiled languages, but development speed and library availability matter more for strategy research
- **Decision**: Python is the right choice. We optimize for iteration speed — finding profitable strategies matters more than microsecond execution.

### Bun.js for the API
- **Why**: Fast startup, native TypeScript support, simple file-system access — aligns with the file-based storage model
- **Trade-off**: Smaller ecosystem than Node.js, but for a lightweight API serving JSON files it's more than sufficient
- **Decision**: Bun.js keeps the API layer thin and fast. The heavy lifting stays in Python.

### Vite + React + shadcn/ui for the Frontend
- **Why**: Fast dev experience (Vite), component-rich UI (shadcn/ui), industry standard (React)
- **Decision**: Good choice for a monitoring dashboard. Keep it simple — read-heavy, not write-heavy.

### Binance as Exchange
- **Why**: Largest crypto exchange by volume, mature API, good liquidity
- **Decision**: Start with Binance. Design the platform so the exchange adapter can be swapped later if needed.

### File-Based Storage
- **Why**: Simple, versionable, no database overhead for early stage
- **Trade-off**: Won't scale to high-frequency data or concurrent writes — but that's not our use case
- **Decision**: JSON files for now. The architecture should abstract storage behind interfaces so we can migrate to a database (SQLite, PostgreSQL) when the data volume justifies it.

## Module Architecture

### Inter-module Compatibility
The bootstrap doc emphasizes that all modules must work together. The key insight is:

1. **Strategies define a universal interface** — they receive market data, configuration, and state; they produce signals.
2. **Execution modes are interchangeable** — the same strategy + signals can be fed to backtesting, paper trading, or real execution.
3. **Portfolio management observes all modes** — it tracks performance regardless of execution context.

This means we need a clean **Strategy Protocol** that decouples:
- **Data ingestion** (MarketFetcher)
- **Signal generation** (Strategy)
- **Signal execution** (BacktestEngine / PaperTrader / RealTrader)
- **Performance tracking** (PortfolioManager)

### Order Support
Must support: market orders, limit orders, stop loss, take profit.
This affects the signal model — signals can't just be "buy/sell". They need to carry order type, price, stop loss, and take profit parameters.

### Routines / Scheduling
The system needs a scheduler that can run modules at configurable intervals.
Cron-like scheduling (e.g., "run backtesting daily at 00:00 UTC", "execute strategies every hour").

## Lessons Learned

### Delegation & Specification
- **Detailed specs with exact commit messages produce excellent results** — platform-developer followed SPEC-000 step-by-step without deviation. The 11-step ordered implementation table with explicit commit messages was the most valuable part of the spec.
- **Acceptance criteria tables are essential** — the Section 17 checklist gave an unambiguous definition of done. platform-developer even added an extra commit to ensure all criteria were met.
- **Platform-developer quality is high** — 93% test coverage (exceeded 80% target), ruff clean, mypy strict clean. This agent can be trusted with complex implementations.
- **Avoid double-delegation** — the first delegation (bw7diecr4) completed the full work but its notification arrived late, causing a redundant second delegation (bvv8qyf74). Always wait for task completion before re-delegating.

### Platform Architecture (Validated by Implementation)
- **Pydantic v2 models as single source of truth** works perfectly — models are used everywhere (cache, strategy signals, trade tracking, results). The round-trip serialization (model_dump / model_validate) is clean.
- **ABC-based interfaces enforce contracts well** — Strategy, DataProvider, ExecutionHandler abstractions held up. The SMA crossover strategy cleanly implements Strategy ABC.
- **Registry pattern for strategies** — `@StrategyRegistry.register` decorator is elegant and extensible. Adding new strategies will be trivial.
- **ccxt as exchange abstraction** — correct choice. Binance market data works without API keys. Rate limiting built-in.
- **File-based JSON caching** — adequate for Phase 1. Market cache deduplication by open_time works correctly. Will need to reconsider for high-frequency or multi-symbol scenarios.
- **typer + rich for CLI** — gives professional-looking output with minimal code. Good developer experience.

### What Needs Attention Next
- **Strategy state persistence** — currently strategies are stateless between runs. Phase 2 needs to address this for paper/live trading.
- **More strategies needed** — only SMA crossover exists. Need RSI, MACD, Bollinger Bands at minimum to validate the framework.
- **Backtesting engine is single-position** — can only hold one position at a time. Multi-position support needed for portfolio-level strategies.
- **No async yet** — everything is synchronous. ccxt supports async; we'll need it for real-time data feeds in Phase 3.
- **Error handling is basic** — custom exceptions exist but recovery/retry logic is minimal. Needs hardening for production.
