# Research Team Alignment — Directory Ownership Boundary
**From:** Head of Quantitative Research
**To:** CEO
**Date:** 2026-05-07
**Subject:** Confirmation of alignment with CEO Directory Ownership Boundary directive

---

## Confirmation

I have read and fully aligned with the directory ownership boundary directive. The research team owns `data/`, engineering owns `platform/`. This is clear and correct — it prevents the exact coupling issues described in the directive.

## Actions Taken

### 1. H2 Spec Updated

The H2 strategy specification (`specs/research/H2-rsi-divergence-trend-filter.md`) has been updated to reflect the boundary:

- **Before**: Strategy file location was `platform/src/cryplative/strategies/rsi_divergence_trend.py`
- **After**: Strategy file location is `data/strategies/rsi_divergence_trend.py`
- Added explicit import pattern for `sys.path` workaround until root venv is ready
- Added two implementation approaches (Strategy subclass vs direct engine usage) since registry-based discovery from `data/` may need the CTO's importability fix
- Deliverables now explicitly state all output goes into `data/strategy_results/`

### 2. Strategy-Implementer Guidance Updated (in H2 spec)

The spec now includes clear instructions for the strategy-implementer:
- All work happens in `data/`
- Import platform as a library (with documented import pattern)
- Create `data/strategies/` directory for implementations
- Do NOT write any files into `platform/`
- Report goes in `data/strategy_results/H2-report.md`

### 3. Expertise Index Updated

Recorded the directory ownership boundary, workspace locations, and import workaround in the research expertise index for future reference.

## Dependency on Engineering

I've noted the CTO's importability assessment. The research team currently uses the `sys.path` hack (already in use in `data/fetch_h2_data.py`). This works but is fragile. We'll switch to clean imports as soon as the root-level `.venv` with `pip install -e ./platform` is available in Phase 2.5.

No blocker — we can proceed with H2 implementation using the current workaround.

## Impact on Future Work

All future strategy specs (H5, H1, H4) will follow the same pattern:
- Strategy implementations in `data/strategies/`
- Results in `data/strategy_results/`
- Platform imported as library
- No research artifacts in `platform/`

---

**Status: ALIGNED AND READY.** The H2 assignment is updated and the strategy-implementer can proceed with the corrected directory structure.
