# Step 2 Status: Root-Level .venv Setup — BLOCKED (Requires Human/CEO Action)

**From:** CTO
**To:** CEO
**Date:** 2026-05-07
**Priority:** P1 — Research team blocked
**Beads Issue:** cryplative-axc

## Summary

Step 2 is **blocked**. The platform-developer cannot execute this task because creating `.venv` at the project root is outside their `platform/` directory sandbox. This is a cross-domain infrastructure task.

## What Happened

1. I delegated the task to platform-developer twice
2. Platform-developer acknowledged the task, documented the steps in their expertise, but **could not execute** shell commands that create files outside `platform/`
3. No `.venv` was created, no `.gitignore` was modified, no commits were made

## What Needs to Happen (Human Execution Required)

The following commands need to be run **by a human or by the CEO agent** who has root project access:

```bash
# Step 1: Add .venv/ to root .gitignore
echo '.venv/' >> /Users/javi/projects/cryplative/.gitignore

# Step 2: Create root venv
python3 -m venv /Users/javi/projects/cryplative/.venv

# Step 3: Install cryplative as editable package
source /Users/javi/projects/cryplative/.venv/bin/activate
pip install -e /Users/javi/projects/cryplative/platform

# Step 4: Verify imports work
python -c "from cryplative.config import CryplativeConfig; print('OK')"
python -c "from cryplative.core.models import Candle, Signal, Trade; print('Models OK')"
python -c "from cryplative.market_fetcher.fetcher import MarketFetcher; print('Fetcher OK')"
python -c "from cryplative.strategies.indicators import SMA, EMA, RSI; print('Indicators OK')"
python -c "from cryplative.backtesting.engine import BacktestEngine; print('Engine OK')"

# Step 5: Commit
git add .gitignore
git commit -m "chore: add .venv to root gitignore for editable install venv"
```

All five verification commands should print their OK messages.

## After Human Execution

Once the above is done:
- Step 3 (updating /platform_docs) can proceed
- Research team can remove sys.path hacks from data/ scripts

## Recommendation for Future

Consider granting the platform-developer limited write access to the root `.gitignore` file, or designate a "project infra" agent with broader filesystem access for cross-cutting setup tasks like this.
