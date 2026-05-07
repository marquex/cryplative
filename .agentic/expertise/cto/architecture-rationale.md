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
- **Pre-implementation validation is essential** — SPEC-001 validation caught 4 critical issues (engine loop incompatibility, missing RunContext param, broken test imports, off-by-one candle counts) that would have caused failed tests and hours of rework. The 10-minute validation saved much more.
- **Validate specs against actual codebase** — the platform-developer read the real engine, tracker, models, and interfaces during validation. This catches interface mismatches that can't be found by reading the spec alone.
- **Provide concrete test vectors for math** — indicator functions need reference values (SMA, EMA, Bollinger Bands with exact inputs/outputs). Without them, implementers may write tests against their own bugs.
- **Off-by-one errors are the #1 risk in financial code** — warmup periods for indicators, minimum candles for crossover detection, and loop bounds all have subtle +1/-1 issues. Always double-check with concrete examples.

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

## Phase 2 Design Decisions (2026-05-05)

### Scope Refinement: Researcher-Ready Platform
User redirected Phase 2 from paper trading to researcher readiness. The goal is making the platform flexible and easy enough for an algo-researcher (human or AI) to test any type of strategy. Paper trading deferred to Phase 3.

Key components of Phase 2 (SPEC-001):
1. **Common Indicators Library** — reusable building blocks (SMA, EMA, RSI, MACD, Bollinger Bands) so researchers compose rather than reimplement
2. **Multi-Position Backtesting** — expand engine from single to multiple concurrent positions (backward compatible via max_positions config)
3. **Strategy Template System** — `cryplative new-strategy <name>` scaffolding command + auto-discovery of strategy files
4. **Diverse Strategies** — RSI, MACD, Bollinger Bands to validate the framework supports different strategy types (mean-reversion, trend-following, volatility)
5. **CLI Enhancements** — `compare` command, `strategies --verbose`, better error messages, params from file
6. **Robustness** — input validation, retry logic, edge case handling
7. **Researcher Documentation** — 5 docs: getting-started, writing-strategies, cli-reference, backtesting-guide, indicators

### Design Decisions for SPEC-001
- **Indicators as pure functions** — no state, no classes, just data in → data out. Easy to test, compose, and understand.
- **numpy internally, list externally** — researchers pass simple lists, we use numpy for correctness/speed under the hood.
- **Multi-position via max_positions config** — backward compatible default of 1, opt-in to more. FIFO closing order.
- **Auto-discovery via pkgutil** — strategies register on import, `__init__.py` auto-imports all modules. No manual registration.
- **Template file prefixed with _** — `_template.py` is skipped by auto-discovery but serves as the scaffold source and living documentation.
- **Docs in platform/docs/** — Markdown, concise, code-heavy. Written for the algo-researcher persona, not developers.
- **Strategy.default_parameters()** — class method on Strategy ABC so CLI can show parameter info without instantiating.

### Key Risks for Phase 2
- **Indicator correctness** — technical indicators have subtle algorithmic differences (e.g., Wilder's vs simple RSI). Tests must validate against known values.
- **Backward compatibility** — multi-position refactor must not break existing single-position behavior. Regression tests are critical.
- **Documentation quality** — docs are only useful if they're accurate and complete. The platform-developer should verify all examples are runnable.

### Hiring Note
- **algo-researcher** is an external agent (not a CTO subordinate). They should be hired after Phase 2 is delivered and verified.
- Phase 2 docs are the onboarding material for this agent.

## Delegation Tracking (2026-05-05)

### Completed: SPEC-001 Phase 2
- **Task**: Implement Researcher-Ready Platform (12 steps)
- **Assignee**: platform-developer
- **Delegated**: 2026-05-05
- **Completed**: 2026-05-05
- **Status**: COMPLETE — 15 commits (1cbe49e through d8ce3ee)
- **Notes**: First delegation (b8lzhwahd) completed steps 1-11 but failed at step 12. Second delegation (btle28boz) finished step 12 and added polish fixes. Pending human verification of test suite and coverage.

### Lessons from Phase 2 Implementation
- **Large specs may need two delegations** — 12-step spec pushed the limits of a single background task. Having a progress tracking file (001-progress.md) enabled seamless resume.
- **platform-developer adds defensive fixes** — self-identified infinity edge case in comparison data formatting and fixed it without being asked.
- **Progress files are essential** — the 001-progress.md file created by the first delegation allowed the second delegation to pick up exactly where it left off. This is a pattern to formalize for all future specs.

## Cross-Agent Communication (2026-05-06)

### Answered Head-of-Research Platform Questions
- **Who**: head-of-research (external agent, not subordinate)
- **What**: 5 detailed questions about platform capabilities affecting research workflow design
- **Where**: `.agentic/specs/managers/cto-platform-answers.md`
- **Topics**: data pipeline capacity, paper trading timeline, backtesting limitations, strategy interface gotchas, data storage schema
- **Key insight**: The research team only had ~42 days of BTC/USDT hourly data — this was just example data from development, not a platform limitation. The MarketFetcher can pull years of data for any Binance pair. This misunderstanding could have led them to design a constrained workflow unnecessarily.

### Lessons from Cross-Agent Q&A
- **External agents need platform docs + direct answers** — the platform_docs/ directory is necessary but not sufficient. External agents have contextual questions (e.g., "how does this affect MY workflow?") that docs can't anticipate. Direct Q&A complements documentation.
- **Managers channel is effective for cross-org communication** — `.agentic/specs/managers/` provides a shared space for inter-agent documents that don't belong in any single agent's domain.
- **Backtesting limitations need proactive communication** — several gaps (no fees, no slippage, no multi-timeframe, SL/TP not auto-triggered) could mislead researchers into overestimating backtest accuracy. These should be prominent in docs, not buried.
- **Phase 3 scope clarification needed soon** — the research team asked about paper trading timeline. As the platform gets users, Phase 3 scope and timeline become a commitment. Should draft SPEC-002 soon.

### Answered Head-of-Research Follow-Up Questions (Round 2)
- **Who**: head-of-research (external agent, not subordinate)
- **What**: 7 follow-up questions after reviewing initial answers
- **Where**: `.agentic/specs/managers/cto-platform-answers-2.md`
- **Key decisions made**:
  1. **Phase 2.5 planned** — fee modeling is too important to wait for Phase 3. Adding `--fee-rate` to backtest CLI, ATR/ADX/Keltner to indicators library, and `--lookback-window` CLI flag. ETA 2-3 days.
  2. **Custom indicators confirmed OK** — strategies can write any helper functions locally. Python modules are not sandboxed. The `indicators.py` library is shared/optional, not mandatory.
  3. **Multi-TF workaround documented** — strategies CAN read cache files directly from disk in `initialize()`, but it's fragile (path-dependent, no time alignment). Recommended to defer H3 for Phase 3's clean multi-TF interface.
  4. **Programmatic API documented** — internal BacktestEngine API works for parameter sweeps. Not "officially public" but stable within a phase.

### Lessons from Round 2 Q&A
- **Research team needs drive platform priorities** — fee modeling wasn't on my near-term radar but the research team correctly identified it as the #1 gap. External user feedback is essential for prioritization.
- **Phase 2.5 is a pattern worth formalizing** — targeted enhancements between full phases based on user feedback. Small scope (3-4 items), fast turnaround (2-3 days), high impact.
- **"Can I do X?" questions need clear YES/NO + alternatives** — the research team was uncertain whether custom indicators were allowed. A clear "YES" with code examples unblocks immediately. Always provide the answer AND the path forward.
- **Assumption validation is valuable** — the research team listed 8 assumptions. Two were wrong (fees coming sooner than expected, programmatic API exists). Catching these early prevents workflow design based on incorrect premises.
- **Indicator library should be additive, not gatekeeping** — the official `indicators.py` is a shared convenience, not a requirement. Strategies can compute anything they want internally. This keeps the research team unblocked while the official library grows organically.
