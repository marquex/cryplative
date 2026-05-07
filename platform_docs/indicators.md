# Technical Indicators Reference

All indicators are in `cryplative.strategies.indicators` and are **pure functions** — they take data in and return computed values with no side effects.

All import examples work from any directory after `source .venv/bin/activate`.

## Common Interface

All functions accept `list[float]` (closing prices) and return `list[float | None]`:
- Same length as input
- `None` for indices where insufficient data exists (warmup period)
- Also accepts `numpy.ndarray` input

---

## compute_sma

Simple Moving Average — arithmetic mean of the last N values.

```python
from cryplative.strategies.indicators import compute_sma

sma = compute_sma(closes, period=20)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `closes` | `list[float]` | — | Closing prices |
| `period` | `int` | — | Lookback window size |

**Warmup:** First `period - 1` values are `None`.

**Example:**
```python
compute_sma([10.0, 20.0, 30.0, 40.0, 50.0], 3)
# Returns: [None, None, 20.0, 30.0, 40.0]
```

**Common usage:** Crossover strategies, trend identification, smoothing.

---

## compute_ema

Exponential Moving Average — gives more weight to recent prices.

```python
from cryplative.strategies.indicators import compute_ema

ema = compute_ema(closes, period=20)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `closes` | `list[float]` | — | Closing prices |
| `period` | `int` | — | Lookback period |

**Warmup:** First `period - 1` values are `None`. The first valid value (at index `period - 1`) is the SMA seed.

**Algorithm:** `EMA_t = price_t * multiplier + EMA_{t-1} * (1 - multiplier)` where `multiplier = 2 / (period + 1)`.

**Example:**
```python
compute_ema([10.0, 20.0, 30.0, 40.0, 50.0], 3)
# Returns: [None, None, 20.0, 30.0, 40.0]
```

**Common usage:** MACD calculation, trend following, smoothing.

---

## compute_rsi

Relative Strength Index — momentum oscillator measuring speed of price changes.

```python
from cryplative.strategies.indicators import compute_rsi

rsi = compute_rsi(closes, period=14)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `closes` | `list[float]` | — | Closing prices |
| `period` | `int` | `14` | RSI lookback period |

**Warmup:** First `period` values are `None`. First valid value is at index `period`.

**Range:** `[0, 100]`

- **> 70**: Overbought (price may be too high)
- **< 30**: Oversold (price may be too low)
- **= 100**: All changes positive (no losses)
- **= 0**: All changes negative (no gains)

**Algorithm:** Wilder's smoothing method.

**Example:**
```python
compute_rsi([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0], period=5)
# Returns: [None, None, None, None, None, 100.0]
```

**Common usage:** Mean-reversion strategies, overbought/oversold signals, divergence detection.

---

## compute_macd

Moving Average Convergence Divergence — trend-following momentum indicator.

```python
from cryplative.strategies.indicators import compute_macd

macd_line, signal_line, histogram = compute_macd(closes)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `closes` | `list[float]` | — | Closing prices |
| `fast_period` | `int` | `12` | Fast EMA period |
| `slow_period` | `int` | `26` | Slow EMA period |
| `signal_period` | `int` | `9` | Signal line EMA period |

**Returns:** `(macd_line, signal_line, histogram)` — three lists of same length as input.

**Warmup:** First valid values appear after `slow_period + signal_period - 2` indices.

**Components:**
- **MACD line** = EMA(fast) - EMA(slow)
- **Signal line** = EMA(MACD line, signal_period)
- **Histogram** = MACD line - Signal line

**Trading signals:**
- Histogram crosses from negative to positive → **BUY** (bullish)
- Histogram crosses from positive to negative → **SELL** (bearish)

**Common usage:** Trend-following strategies, momentum signals, divergence analysis.

---

## compute_bollinger_bands

Bollinger Bands — volatility envelope around a moving average.

```python
from cryplative.strategies.indicators import compute_bollinger_bands

upper, middle, lower = compute_bollinger_bands(closes)
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `closes` | `list[float]` | — | Closing prices |
| `period` | `int` | `20` | SMA period for middle band |
| `num_std` | `float` | `2.0` | Number of standard deviations |

**Returns:** `(upper_band, middle_band, lower_band)` — three lists of same length as input.

**Warmup:** First `period - 1` values are `None`.

**Components:**
- **Middle band** = SMA(period)
- **Upper band** = Middle + num_std * stdev(period)
- **Lower band** = Middle - num_std * stdev(period)

Uses sample standard deviation (ddof=1).

**Trading signals:**
- Price crosses below lower band → **BUY** (statistically cheap)
- Price crosses above upper band → **SELL** (statistically expensive)

**Example:**
```python
compute_bollinger_bands([10.0, 20.0, 30.0, 25.0, 35.0], 3, 2.0)
# upper:   [None, None, 40.0, 35.0, 40.0]
# middle:  [None, None, 20.0, 25.0, 30.0]
# lower:   [None, None,  0.0, 15.0, 20.0]
```

**Common usage:** Volatility-based strategies, mean reversion, breakout detection.
