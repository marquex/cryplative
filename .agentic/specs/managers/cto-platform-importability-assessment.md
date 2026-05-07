# Platform Importability Assessment — data/ Can Import platform/ Today
**From:** CTO
**To:** CEO
**Date:** 2026-05-07
**Priority:** High — answers CEO directive on directory ownership boundary

## Summary

**Can code in data/ import and use platform modules cleanly today? NO.** The current setup has a structural gap that needs fixing before the research team can work properly in `data/`.

## What I Found

### The Hack: sys.path.insert()

The research team's existing script `data/fetch_h2_data.py` uses this to import platform modules:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "platform", "src"))

from cryplative.config import CryplativeConfig, setup_logging
from cryplative.market_fetcher.fetcher import MarketFetcher
```

This is a **fragile workaround**, not a clean import. It breaks if:
- The script is moved or run from a different working directory
- The relative path calculation changes
- Multiple scripts each need their own path hack
- The package structure changes (e.g., `src` layout renaming)

### Root Cause

The platform is a proper installable Python package:
- `platform/pyproject.toml` defines `cryplative` as a hatchling-built package
- `platform/.venv/` contains a virtualenv with `cryplative` installed
- **But there is NO root-level Python environment** where `cryplative` is installed
- Scripts in `data/` have no venv and no package registry that includes `cryplative`

### What Needs to Change

The fix is straightforward. We need a **root-level Python environment** where `cryplative` is installed as an editable package. Two options:

#### Option A: Root-level venv with editable install (RECOMMENDED)
1. Create a `.venv` at the project root (`/Users/javi/projects/cryplative/`)
2. Install `cryplative` as editable: `pip install -e ./platform`
3. Research scripts in `data/` activate this root venv and import normally

Result for research team:
```python
# Clean — no sys.path hack needed
from cryplative.config import CryplativeConfig
from cryplative.market_fetcher.fetcher import MarketFetcher
from cryplative.strategies.base import Strategy
from cryplative.backtesting.engine import BacktestEngine
```

**Pros:** Simple, standard Python pattern. Platform venv stays for platform dev/test. Root venv is for all consumers. Research team just `source .venv/bin/activate` at project root.

**Cons:** Two venvs to maintain (root for usage, platform/ for development). Platform-developer must ensure `pip install -e` stays current.

#### Option B: Move venv to root, eliminate platform/.venv
1. Move `platform/.venv` to the project root
2. Platform-developer runs tests from root using `pytest` from root venv
3. Everything uses one environment

**Pros:** Single venv, no duplication.
**Cons:** Couples platform development with consumer usage. Platform-developer's test dependencies (pytest, ruff, mypy) leak into the research environment. Less isolation.

### Recommendation: Option A

Option A keeps clean separation of concerns:
- **`platform/.venv`** — platform-developer's environment for dev, test, lint
- **Root `.venv`** — shared environment for all consumers (data/, future API, etc.)

## Impact on data/ fetch_h2_data.py

Once the root venv is set up with editable install, the research team should remove the `sys.path` hack from `fetch_h2_data.py` and use clean imports. This is a research team action item, not an engineering one.

## Action Items

| Who | What | Priority |
|-----|------|----------|
| **Platform-developer** | Add root-level venv setup to platform spec: create `.venv` at project root, `pip install -e ./platform`, document in platform docs | Phase 2.5 (urgent) |
| **Research team** | Once root venv exists, remove `sys.path` hacks from `data/` scripts, use clean imports | After platform fix |
| **CTO** | Add this requirement to SPEC-002 (Phase 2.5) as a new step | Immediately |

## Public API Contract

For clarity, here are the modules that the research team in `data/` should be able to import (the "public API" of the platform toolkit):

| Import Path | Purpose |
|-------------|---------|
| `cryplative.config` | CryplativeConfig, setup_logging |
| `cryplative.core.models` | Candle, Signal, Trade, Position, BacktestResult |
| `cryplative.core.interfaces` | Strategy (ABC), DataProvider, ExecutionHandler |
| `cryplative.core.exceptions` | Custom exceptions |
| `cryplative.market_fetcher.fetcher` | MarketFetcher |
| `cryplative.market_fetcher.cache` | MarketCache |
| `cryplative.strategies.registry` | StrategyRegistry |
| `cryplative.strategies.indicators` | SMA, EMA, RSI, MACD, Bollinger Bands |
| `cryplative.strategies.base` | Strategy ABC, RunContext |
| `cryplative.backtesting.engine` | BacktestEngine |
| `cryplative.portfolio.tracker` | PortfolioTracker |

All of these should work with a simple `from cryplative.X import Y` once the root venv is in place.

## Verification Test

After the fix, this should work from any `.py` file in `data/`:

```bash
cd /Users/javi/projects/cryplative
source .venv/bin/activate
python -c "from cryplative.config import CryplativeConfig; print('OK')"
```

If this prints `OK`, the boundary is clean.
