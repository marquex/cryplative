"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from cryplative.core.models import Candle


def _make_candle(
    index: int = 0,
    close: float = 100.0,
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    base_time: int = 1704067200000,
) -> Candle:
    """Create a test candle with configurable fields."""
    step = 3600000  # 1 hour in ms
    open_time = base_time + index * step
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=close - 5,
        high=close + 10,
        low=close - 10,
        close=close,
        volume=100.0,
        close_time=open_time + 3599999,
        closed=True,
    )


@pytest.fixture()
def sample_candles() -> list[Candle]:
    """Generate 200+ synthetic candles with a mild uptrend."""
    candles = []
    for i in range(250):
        close = 100.0 + i * 0.5
        candles.append(_make_candle(index=i, close=close))
    return candles


@pytest.fixture()
def sample_candles_with_crossover() -> list[Candle]:
    """Generate candles designed to trigger SMA crossovers.

    Pattern: flat → rising → falling → rising
    This should produce BUY and SELL signals with fast=5, slow=10.
    """
    candles: list[Candle] = []
    n = 100
    for i in range(n):
        if i < n // 4:
            close = 100.0
        elif i < n // 2:
            close = 100.0 + (i - n // 4) * 2.0
        elif i < 3 * n // 4:
            close = 100.0 + (n // 4) * 2.0 - (i - n // 2) * 2.0
        else:
            close = 100.0 - (n // 4) * 2.0 + (i - 3 * n // 4) * 2.0
        candles.append(_make_candle(index=i, close=close))
    return candles


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """Temporary directory for file-based tests."""
    return tmp_path
