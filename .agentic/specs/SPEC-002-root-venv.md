# SPEC-002: Root-Level .venv with Editable Platform Install

**Status:** READY TO EXECUTE (platform-developer blocked by domain restrictions)
**Beads issue:** cryplative-axc
**Requires:** Agent with root-level filesystem access (CTO or ops agent)

## Problem
Research team uses `sys.path.insert()` hacks to import platform modules from `data/` scripts.
Need a root-level Python venv with cryplative installed as editable package for clean imports everywhere.

## Platform Package Verified
- Build system: `hatchling` (supports editable installs)
- Package layout: `platform/src/cryplative/` (src layout)
- Python requirement: `>=3.11`
- All 5 import targets verified present: config, core.models, market_fetcher.fetcher, strategies.indicators, backtesting.engine

## Execution Commands (run from project root)

### Step 1: Create root-level .venv
```bash
cd /Users/javi/projects/cryplative
python3.11 -m venv .venv
```

### Step 2: Install cryplative as editable package
```bash
source .venv/bin/activate
pip install --upgrade pip
pip install -e ./platform
```

### Step 3: Verify clean imports (from project root, NOT from inside platform/)
```bash
cd /Users/javi/projects/cryplative
source .venv/bin/activate
python -c "from cryplative.config import CryplativeConfig; print('OK')"
python -c "from cryplative.core.models import Candle, Signal, Trade; print('Models OK')"
python -c "from cryplative.market_fetcher.fetcher import MarketFetcher; print('Fetcher OK')"
python -c "from cryplative.strategies.indicators import SMA, EMA, RSI; print('Indicators OK')"
python -c "from cryplative.backtesting.engine import BacktestEngine; print('Engine OK')"
```

### Step 4: Add .venv/ to root .gitignore
Check if `.venv/` is already in `/Users/javi/projects/cryplative/.gitignore`. If not, add it.

### Step 5: Close beads issue
```bash
bd close cryplative-axc
```

## Acceptance Criteria
1. `/Users/javi/projects/cryplative/.venv` exists as valid Python 3.11 venv
2. `pip show cryplative` shows editable install from `./platform`
3. All five verification imports succeed from project root
4. `.venv/` is in root `.gitignore`

## Important
- Do NOT modify `platform/.venv` — it stays as-is for platform development
- Do NOT modify any existing code in `platform/`
