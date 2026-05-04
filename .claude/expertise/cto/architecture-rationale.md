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

## Lessons Learned (To Be Updated)
- No lessons yet — project is in bootstrap phase.
