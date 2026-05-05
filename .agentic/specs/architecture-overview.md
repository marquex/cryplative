# Cryplative — Technical Architecture Overview
**Author**: CTO Agent
**Date**: 2026-05-04
**Status**: Draft — Initial Architecture

---

## 1. System Overview

Cryplative is a modular trading platform for researching, testing, and executing crypto trading strategies. The system is organized into distinct modules that communicate through well-defined interfaces.

```
┌─────────────────────────────────────────────────────────────────┐
│                        MONITORING LAYER                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  React SPA   │◄──►│  Bun.js API  │◄──►│  File System     │   │
│  │  (shadcn/ui) │    │  (REST)      │    │  (JSON storage)   │   │
│  └──────────────┘    └──────────────┘    └──────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│                        PLATFORM LAYER (Python)                   │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ MarketFetcher │───►│   Strategy   │───►│  Signal (Buy/    │   │
│  │ (Binance +    │    │   Engine     │    │  Sell + params)  │   │
│  │  cache)       │    │              │    │                  │   │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘   │
│                                                    │             │
│                           ┌────────────────────────┼─────────┐   │
│                           ▼                        ▼         ▼   │
│                  ┌──────────────┐  ┌────────────┐ ┌──────────┐  │
│                  │ Backtesting  │  │ Paper      │ │ Real     │  │
│                  │ Engine       │  │ Trading    │ │ Execution│  │
│                  └──────┬───────┘  └─────┬──────┘ └────┬─────┘  │
│                         │               │             │         │
│                         ▼               ▼             ▼         │
│                  ┌──────────────────────────────────────────┐   │
│                  │       Portfolio Management               │   │
│                  │  (tracking, performance, reporting)      │   │
│                  └──────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Routines / Scheduler                    │   │
│  │  (orchestrates all modules on configurable schedules)     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Platform** | Python 3.11+ | Ecosystem for data analysis, backtesting, trading |
| **API** | Bun.js | Fast, lightweight, native TS, file-system friendly |
| **Frontend** | Vite + React + shadcn/ui | Fast dev, rich components, industry standard |
| **Exchange** | Binance API (via `python-binance` or `ccxt`) | Largest volume, mature API |
| **Storage** | JSON files (initial), abstracted for DB migration later | Simple, versionable, no overhead |
| **Scheduling** | Python (APScheduler or similar) | Native integration with platform modules |

## 3. Module Specifications

Each module will have its own detailed specification in `.agentic/specs/`. The modules are:

1. **[SPEC-001] MarketFetcher** — Data ingestion and caching
2. **[SPEC-002] Strategy Interface** — Universal strategy protocol
3. **[SPEC-003] Backtesting Engine** — Historical strategy evaluation
4. **[SPEC-004] Paper Trading** — Simulated execution
5. **[SPEC-005] Real Execution** — Live trade execution on Binance
6. **[SPEC-006] Portfolio Management** — Performance tracking and reporting
7. **[SPEC-007] Routines / Scheduler** — Orchestrated scheduled execution
8. **[SPEC-008] Bun.js API** — REST API for monitoring and control
9. **[SPEC-009] React Webapp** — Dashboard for system visualization

## 4. Core Data Models

### 4.1 Candle (OHLCV)
```
Candle:
  symbol: str        # e.g., "BTCUSDT"
  interval: str      # e.g., "1h", "4h", "1d"
  open_time: int     # Unix timestamp (ms)
  open: float
  high: float
  low: float
  close: float
  volume: float
  close_time: int    # Unix timestamp (ms)
  closed: bool       # False if candle is still forming
```

### 4.2 Signal
```
Signal:
  strategy_id: str
  symbol: str
  timestamp: int
  direction: "BUY" | "SELL"
  order_type: "MARKET" | "LIMIT"
  price: float | None         # Required for LIMIT orders
  quantity: float
  stop_loss: float | None
  take_profit: float | None
  confidence: float           # 0.0 - 1.0, strategy's confidence level
  metadata: dict              # Strategy-specific additional info
```

### 4.3 Trade
```
Trade:
  trade_id: str
  signal: Signal
  entry_price: float
  exit_price: float | None    # None if still open
  quantity: float
  pnl: float | None           # None if still open
  pnl_percentage: float | None
  status: "OPEN" | "CLOSED" | "CANCELLED"
  opened_at: int
  closed_at: int | None
  context: "BACKTEST" | "PAPER" | "REAL"
```

### 4.4 Strategy Config
```
StrategyConfig:
  strategy_id: str
  strategy_name: str
  version: str
  symbol: str
  interval: str
  parameters: dict            # Strategy-specific parameters
  state: dict                 # Persistent state across runs
```

### 4.5 Strategy Result (stored as JSON)
```
StrategyResult:
  strategy_id: str
  run_type: "BACKTEST" | "PAPER" | "REAL"
  start_date: str
  end_date: str
  parameters: dict
  trades: list[Trade]
  metrics:
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: float
  created_at: str
```

## 5. Directory Structure (Proposed)

```
cryplative/
├── platform/                  # Python trading platform
│   ├── core/                  # Shared interfaces and models
│   │   ├── models.py          # Data models (Candle, Signal, Trade, etc.)
│   │   └── interfaces.py      # Abstract base classes / protocols
│   ├── market_fetcher/        # MarketFetcher module
│   ├── strategies/            # Strategy implementations
│   │   ├── registry.py        # Strategy registry/discovery
│   │   └── <strategy_name>/   # Each strategy in its own directory
│   ├── backtesting/           # Backtesting engine
│   ├── paper_trading/         # Paper trading module
│   ├── execution/             # Real execution module
│   ├── portfolio/             # Portfolio management
│   ├── routines/              # Scheduler and routines
│   └── requirements.txt       # Python dependencies
├── api/                       # Bun.js REST API
│   ├── src/
│   │   ├── routes/
│   │   ├── services/
│   │   └── index.ts
│   └── package.json
├── webapp/                    # React + Vite + shadcn/ui
│   ├── src/
│   └── package.json
├── data/                      # File-based storage
│   ├── market_cache/          # Cached market data
│   ├── strategy_results/      # Backtest & trading results (JSON)
│   ├── portfolio/             # Portfolio state and reports
│   └── strategies/            # Strategy configs and state
├── .claude/                   # Agent system (existing)
├── bootstrap.md
└── CLAUDE.md
```

## 6. Key Design Decisions

1. **Strategy Protocol** — All strategies implement the same interface. This is the most critical abstraction in the system. It ensures any strategy can run in any execution mode.
2. **File-based storage initially** — Simple and effective for our scale. Storage is abstracted behind interfaces to allow migration to SQLite or PostgreSQL.
3. **Exchange adapter pattern** — Binance is the first exchange, but the MarketFetcher and Execution modules should abstract the exchange behind an interface.
4. **JSON results** — Every run (backtest, paper, real) produces a standardized JSON result file that can be compared, queried, and displayed.
5. **Separated execution modes** — Backtesting, paper trading, and real execution share the signal model but implement execution differently.

## 7. Development Phases (Proposed Roadmap)

### Phase 1: Foundation
- Core data models and interfaces
- MarketFetcher (Binance data ingestion + caching)
- First simple strategy (e.g., SMA Crossover)
- Backtesting engine

### Phase 2: Validation
- Paper trading module
- Portfolio management (basic tracking)
- Strategy registry and discovery
- More strategies implemented

### Phase 3: Live Operations
- Real execution module (Binance API)
- Routines / scheduler
- Risk management safeguards

### Phase 4: Monitoring & Control
- Bun.js API
- React webapp / dashboard
- Interactive strategy management

### Phase 5: Optimization
- Strategy parameter optimization
- Strategy combination / ensemble methods
- Performance analytics and reporting
- Advanced order types and risk management

---

*Detailed specifications for each module (SPEC-001 through SPEC-009) will be created as separate documents.*
