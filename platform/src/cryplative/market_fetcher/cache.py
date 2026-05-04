"""Local candle cache for market data.

Caches fetched candles to disk to avoid hammering the API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from cryplative.core.models import Candle

logger = structlog.get_logger()


def _cache_path(cache_dir: Path, symbol: str, interval: str) -> Path:
    """Return the cache file path for a symbol+interval combination.

    Symbol uses underscore format in filenames: BTC_USDT_1h.json
    """
    safe_symbol = symbol.replace("/", "_")
    filename = f"{safe_symbol}_{interval}.json"
    return cache_dir / filename


def _candles_to_dicts(candles: list[Candle]) -> list[dict[str, Any]]:
    """Convert a list of Candle objects to a list of dicts."""
    return [c.model_dump() for c in candles]


def _dicts_to_candles(data: list[dict[str, Any]]) -> list[Candle]:
    """Convert a list of dicts to a list of Candle objects."""
    return [Candle.model_validate(d) for d in data]


def load_cache(cache_dir: Path, symbol: str, interval: str) -> list[Candle]:
    """Load cached candles from disk.

    Returns an empty list if the cache file doesn't exist.
    """
    path = _cache_path(cache_dir, symbol, interval)
    if not path.exists():
        logger.debug("cache_miss", symbol=symbol, interval=interval, path=str(path))
        return []

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        candles = _dicts_to_candles(data)
        logger.debug(
            "cache_load",
            symbol=symbol,
            interval=interval,
            count=len(candles),
        )
        return candles
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("cache_load_error", symbol=symbol, interval=interval, error=str(e))
        return []


def save_cache(
    cache_dir: Path, symbol: str, interval: str, candles: list[Candle]
) -> None:
    """Write candles to disk. Overwrites entirely."""
    path = _cache_path(cache_dir, symbol, interval)
    cache_dir.mkdir(parents=True, exist_ok=True)

    data = _candles_to_dicts(candles)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    logger.debug(
        "cache_save",
        symbol=symbol,
        interval=interval,
        count=len(candles),
        path=str(path),
    )


def update_cache(
    cache_dir: Path, symbol: str, interval: str, new_candles: list[Candle]
) -> list[Candle]:
    """Merge new candles with existing cache.

    Deduplicates by open_time. Sorts by open_time. Saves and returns
    the merged list.
    """
    existing = load_cache(cache_dir, symbol, interval)

    # Build a dict keyed by open_time for deduplication
    merged: dict[int, Candle] = {c.open_time: c for c in existing}
    for c in new_candles:
        merged[c.open_time] = c

    # Sort by open_time ascending
    result = sorted(merged.values(), key=lambda c: c.open_time)

    save_cache(cache_dir, symbol, interval, result)

    logger.debug(
        "cache_update",
        symbol=symbol,
        interval=interval,
        existing_count=len(existing),
        new_count=len(new_candles),
        merged_count=len(result),
    )

    return result
