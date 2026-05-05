"""Common technical indicator functions.

Pure functions for computing technical indicators. All functions accept
``list[float]`` (closing prices) and return ``list[float | None]`` where
``None`` means insufficient data at that index.

Uses numpy internally for correctness and performance.
"""

from __future__ import annotations

import numpy as np


def compute_sma(closes: list[float], period: int) -> list[float | None]:
    """Simple Moving Average.

    Returns a list of the same length as *closes*. Values are ``None``
    for indices where fewer than *period* data points are available.

    Algorithm: arithmetic mean of the last *period* values.
    """
    arr = np.asarray(closes, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return []
    result: list[float | None] = [None] * n
    if n < period:
        return result
    cumsum = np.cumsum(arr)
    # SMA at index i = (arr[i-period+1] + ... + arr[i]) / period
    # = (cumsum[i] - cumsum[i-period]) / period  for i >= period-1
    for i in range(period - 1, n):
        s = cumsum[i] - (cumsum[i - period] if i >= period else 0.0)
        result[i] = float(s / period)
    return result


def compute_ema(closes: list[float], period: int) -> list[float | None]:
    """Exponential Moving Average.

    Algorithm: ``EMA_t = price_t * multiplier + EMA_{t-1} * (1 - multiplier)``
    where ``multiplier = 2 / (period + 1)``.
    Seed with SMA of first *period* values.

    The first ``period - 1`` values are ``None``.  The seed value at index
    ``period - 1`` uses the SMA of the first *period* closes.
    """
    arr = np.asarray(closes, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return []
    result: list[float | None] = [None] * n
    if n < period:
        return result
    multiplier = 2.0 / (period + 1)
    seed = float(np.mean(arr[:period]))
    result[period - 1] = seed
    ema = seed
    for i in range(period, n):
        ema = arr[i] * multiplier + ema * (1.0 - multiplier)
        result[i] = float(ema)
    return result


def compute_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index (Wilder's smoothing).

    Returns values in range [0, 100].

    Algorithm:
    1. Calculate price changes.
    2. Separate into gains (positive changes) and losses (absolute negative changes).
    3. First avg_gain = mean(gains[:period]), first avg_loss = mean(losses[:period]).
    4. Subsequent: avg_gain = (prev_avg_gain * (period-1) + current_gain) / period.
    5. RS = avg_gain / avg_loss. RSI = 100 - (100 / (1 + RS)).
    """
    arr = np.asarray(closes, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return []
    result: list[float | None] = [None] * n
    if n < period + 1:
        return result

    changes = np.diff(arr)
    gains = np.where(changes > 0, changes, 0.0)
    losses = np.where(changes < 0, -changes, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, n - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        idx = i + 1
        if avg_loss == 0:
            result[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[idx] = 100.0 - (100.0 / (1.0 + rs))

    return result


def compute_macd(
    closes: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Moving Average Convergence Divergence.

    Returns ``(macd_line, signal_line, histogram)``.

    Algorithm:
    1. MACD line = EMA(fast) - EMA(slow).
    2. Signal line = EMA(MACD line, signal_period).
    3. Histogram = MACD line - Signal line.

    All three lists have the same length as *closes*.
    """
    fast_ema = compute_ema(closes, fast_period)
    slow_ema = compute_ema(closes, slow_period)

    n = len(closes)
    macd_line: list[float | None] = [None] * n
    for i in range(n):
        fv = fast_ema[i]
        sv = slow_ema[i]
        if fv is not None and sv is not None:
            macd_line[i] = fv - sv

    # Compute signal line from MACD values.
    # Extract only the non-None MACD values and compute EMA from those,
    # then map results back to original indices.
    valid_macd_indices: list[int] = []
    valid_macd_values: list[float] = []
    for i in range(n):
        mv = macd_line[i]
        if mv is not None:
            valid_macd_indices.append(i)
            valid_macd_values.append(mv)

    signal_ema = compute_ema(valid_macd_values, signal_period)

    signal_line: list[float | None] = [None] * n
    for j, val in enumerate(signal_ema):
        if val is not None and j < len(valid_macd_indices):
            signal_line[valid_macd_indices[j]] = val

    histogram: list[float | None] = [None] * n
    for i in range(n):
        mv = macd_line[i]
        sv = signal_line[i]
        if mv is not None and sv is not None:
            histogram[i] = mv - sv

    return macd_line, signal_line, histogram


def compute_bollinger_bands(
    closes: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger Bands.

    Returns ``(upper_band, middle_band, lower_band)``.

    Algorithm:
    1. Middle band = SMA(period).
    2. Upper band = Middle + num_std * stdev(period).
    3. Lower band = Middle - num_std * stdev(period).

    Uses sample standard deviation (ddof=1) for consistency with
    common Bollinger Band implementations.
    """
    middle = compute_sma(closes, period)
    n = len(closes)
    arr = np.asarray(closes, dtype=np.float64)
    upper_band: list[float | None] = [None] * n
    lower_band: list[float | None] = [None] * n

    for i in range(period - 1, n):
        window = arr[i - period + 1 : i + 1]
        std = float(np.std(window, ddof=1))
        m = middle[i]
        if m is not None:
            upper_band[i] = m + num_std * std
            lower_band[i] = m - num_std * std

    return upper_band, middle, lower_band
