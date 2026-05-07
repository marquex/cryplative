# Directory Ownership Boundary — CEO Directive
**From:** CEO
**To:** CTO, Head of Research
**Date:** 2026-05-07
**Priority:** High — affects how all research work is organized

## Decision

Javi has clarified an important architectural boundary between the engineering and research teams. This is now company policy.

## Boundary Rules

### Engineering Team owns `platform/`
- The platform is a **toolkit** — libraries, APIs, utilities for strategy implementation and backtesting
- **No strategies, research data, or research output** should live in `platform/`
- The platform must be **importable and usable** by code running in `data/`

### Research Team owns `data/`
- ALL research artifacts live in `data/`:
  - Strategy implementations
  - Downloaded market data
  - Calculated historical indicators
  - Backtesting results
  - Performance metrics
- The research team **imports and uses** platform tools (from `platform/`) as a library
- But all output, all files, all results stay in `data/`

## What This Means

**For CTO:**
- Ensure the platform can be imported and used by scripts running in `data/`
- If the current platform architecture doesn't support this cleanly (e.g., import paths, module structure), make it a priority to fix
- The platform is a tool for the research team — make sure it works as one

**For Head of Research:**
- When the strategy-implementer starts working on H2 or any strategy, all work happens in `data/`
- The implementer imports platform tools but writes everything to `data/`
- This is where strategies, backtest results, and performance metrics live

## Why This Matters

Clear ownership prevents:
- Strategies getting mixed into platform code
- Research coupling to platform internals
- Confusion about where to find artifacts

Each team owns its domain completely.
