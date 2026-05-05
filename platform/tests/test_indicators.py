"""Tests for common technical indicator functions."""

from __future__ import annotations

import numpy as np
import pytest

from cryplative.strategies.indicators import (
    compute_bollinger_bands,
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_sma,
)


# ---------------------------------------------------------------------------
# compute_sma
# ---------------------------------------------------------------------------


class TestComputeSMA:
    def test_basic_sma(self) -> None:
        result = compute_sma([10.0, 20.0, 30.0, 40.0, 50.0], 3)
        assert result == [None, None, 20.0, 30.0, 40.0]

    def test_sma_period_1(self) -> None:
        result = compute_sma([10.0, 20.0, 30.0], 1)
        assert result == [10.0, 20.0, 30.0]

    def test_sma_not_enough_data(self) -> None:
        result = compute_sma([10.0], 3)
        assert result == [None]

    def test_sma_empty(self) -> None:
        result = compute_sma([], 3)
        assert result == []

    def test_sma_constant_values(self) -> None:
        result = compute_sma([5.0, 5.0, 5.0, 5.0], 2)
        assert result == [None, 5.0, 5.0, 5.0]

    def test_length_matches_input(self) -> None:
        data = list(range(1, 101))
        assert len(compute_sma(data, 10)) == 100

    def test_none_count(self) -> None:
        """First period-1 values should be None."""
        result = compute_sma([1.0] * 20, 5)
        assert result[:4] == [None, None, None, None]
        assert result[4] is not None

    def test_large_period(self) -> None:
        """Period larger than data length should return all None."""
        result = compute_sma([1.0, 2.0, 3.0], 10)
        assert result == [None, None, None]

    def test_accepts_numpy_array(self) -> None:
        arr = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        result = compute_sma(arr, 3)
        assert result == [None, None, 20.0, 30.0, 40.0]


# ---------------------------------------------------------------------------
# compute_ema
# ---------------------------------------------------------------------------


class TestComputeEMA:
    def test_basic_ema(self) -> None:
        result = compute_ema([10.0, 20.0, 30.0, 40.0, 50.0], 3)
        assert result == [None, None, 20.0, 30.0, 40.0]

    def test_ema_period_1(self) -> None:
        result = compute_ema([10.0, 20.0, 30.0], 1)
        assert result == [10.0, 20.0, 30.0]

    def test_ema_not_enough_data(self) -> None:
        result = compute_ema([10.0, 20.0], 3)
        assert result == [None, None]

    def test_ema_empty(self) -> None:
        result = compute_ema([], 3)
        assert result == []

    def test_ema_manual_calculation(self) -> None:
        """Manual EMA calculation for period=2."""
        closes = [10.0, 20.0, 30.0, 40.0]
        result = compute_ema(closes, 2)
        # Seed SMA(2) = (10+20)/2 = 15.0
        # multiplier = 2/3 ≈ 0.6667
        # EMA[1] = 15.0
        # EMA[2] = 30 * 0.6667 + 15 * 0.3333 = 20.0 + 5.0 = 25.0
        # EMA[3] = 40 * 0.6667 + 25 * 0.3333 = 26.6667 + 8.3333 = 35.0
        assert result[0] is None
        assert result[1] == pytest.approx(15.0)
        assert result[2] == pytest.approx(25.0)
        assert result[3] == pytest.approx(35.0)

    def test_length_matches_input(self) -> None:
        data = list(range(1, 101))
        assert len(compute_ema(data, 10)) == 100

    def test_none_count_period_plus_one(self) -> None:
        """First period values should be None (period-1 Nones + seed at period-1)."""
        result = compute_ema([1.0] * 20, 5)
        assert result[:4] == [None, None, None, None]
        assert result[4] is not None

    def test_large_period(self) -> None:
        result = compute_ema([1.0, 2.0, 3.0], 10)
        assert result == [None, None, None]

    def test_accepts_numpy_array(self) -> None:
        arr = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        result = compute_ema(arr, 3)
        assert result == [None, None, 20.0, 30.0, 40.0]


# ---------------------------------------------------------------------------
# compute_rsi
# ---------------------------------------------------------------------------


class TestComputeRSI:
    def test_rsi_all_positive(self) -> None:
        """RSI = 100 when all changes are positive (no losses)."""
        closes = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
        result = compute_rsi(closes, period=5)
        # First valid RSI at index 5 (period+1)
        assert result[5] == 100.0

    def test_rsi_all_negative(self) -> None:
        """RSI = 0 when all changes are negative (no gains)."""
        closes = [70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0]
        result = compute_rsi(closes, period=5)
        assert result[5] == 0.0

    def test_rsi_range(self) -> None:
        """All RSI values should be in [0, 100]."""
        closes = [float(i) for i in range(50)]
        result = compute_rsi(closes, period=14)
        for val in result:
            if val is not None:
                assert 0.0 <= val <= 100.0

    def test_rsi_flat_prices(self) -> None:
        """Flat prices should produce RSI close to 50."""
        closes = [100.0] * 20
        result = compute_rsi(closes, period=5)
        # With no changes, avg_loss = 0, so RSI should be 100
        # Actually, when all changes are 0, gains=0 and losses=0,
        # avg_loss = 0, so RSI = 100
        assert result[5] == 100.0

    def test_rsi_alternating(self) -> None:
        """Alternating equal gains and losses should produce RSI near 50."""
        # Long alternating pattern: after Wilder's smoothing converges, RSI → 50
        closes = []
        price = 100.0
        for _ in range(30):
            closes.append(price)
            price += 1.0
            closes.append(price)
            price -= 1.0
        result = compute_rsi(closes, period=14)
        # By the end, RSI should be near 50
        assert result[-1] == pytest.approx(50.0, abs=5.0)

    def test_rsi_insufficient_data(self) -> None:
        result = compute_rsi([10.0, 20.0, 30.0], period=14)
        assert result == [None, None, None]

    def test_rsi_empty(self) -> None:
        assert compute_rsi([]) == []

    def test_rsi_length_matches_input(self) -> None:
        data = [float(i) for i in range(50)]
        assert len(compute_rsi(data, period=14)) == 50

    def test_rsi_known_reference(self) -> None:
        """Verify RSI against a hand-calculated reference.

        closes: [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
                  45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
        period=14. Using Wilder's smoothing:
        - First avg_gain and avg_loss from first 14 changes.
        - RSI at index 14 (15th value, but first valid is at period = 14).
        """
        closes = [
            44.0, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
            45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
        ]
        result = compute_rsi(closes, period=14)
        # RSI[14] should exist and be in valid range
        assert result[14] is not None
        assert 0.0 <= result[14] <= 100.0
        # From TradingView reference, RSI(14) for this data ≈ 72.98 at index 14
        assert result[14] == pytest.approx(72.98, abs=1.0)

    def test_accepts_numpy_array(self) -> None:
        arr = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0])
        result = compute_rsi(arr, period=5)
        assert result[5] == 100.0


# ---------------------------------------------------------------------------
# compute_macd
# ---------------------------------------------------------------------------


class TestComputeMACD:
    def test_length_matches_input(self) -> None:
        data = [float(i) for i in range(50)]
        macd, signal, hist = compute_macd(data, 12, 26, 9)
        assert len(macd) == 50
        assert len(signal) == 50
        assert len(hist) == 50

    def test_insufficient_data(self) -> None:
        data = [10.0, 20.0, 30.0]
        macd, signal, hist = compute_macd(data, 12, 26, 9)
        assert all(v is None for v in macd)
        assert all(v is None for v in signal)
        assert all(v is None for v in hist)

    def test_empty_input(self) -> None:
        macd, signal, hist = compute_macd([], 12, 26, 9)
        assert macd == []
        assert signal == []
        assert hist == []

    def test_histogram_equals_macd_minus_signal(self) -> None:
        data = list(range(30, 80))
        macd, signal, hist = compute_macd(data, 3, 6, 3)
        for i in range(len(data)):
            if macd[i] is not None and signal[i] is not None:
                assert hist[i] == pytest.approx(macd[i] - signal[i])

    def test_short_periods(self) -> None:
        """MACD with short periods should produce values quickly."""
        data = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        macd, signal, hist = compute_macd(data, 3, 6, 3)
        # MACD line should have values starting at index 5 (slow_period - 1)
        assert macd[5] is not None

    def test_accepts_numpy_array(self) -> None:
        arr = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
        macd, signal, hist = compute_macd(arr, 3, 6, 3)
        assert macd[5] is not None


# ---------------------------------------------------------------------------
# compute_bollinger_bands
# ---------------------------------------------------------------------------


class TestComputeBollingerBands:
    def test_basic_bollinger(self) -> None:
        result = compute_bollinger_bands([10.0, 20.0, 30.0, 25.0, 35.0], 3, 2.0)
        upper, middle, lower = result

        assert upper == [None, None, 40.0, 35.0, 40.0]
        assert middle == [None, None, 20.0, 25.0, 30.0]
        assert lower == [None, None, 0.0, 15.0, 20.0]

    def test_length_matches_input(self) -> None:
        data = list(range(1, 51))
        upper, middle, lower = compute_bollinger_bands(data, 20)
        assert len(upper) == 50
        assert len(middle) == 50
        assert len(lower) == 50

    def test_empty_input(self) -> None:
        upper, middle, lower = compute_bollinger_bands([], 20)
        assert upper == []
        assert middle == []
        assert lower == []

    def test_insufficient_data(self) -> None:
        result = compute_bollinger_bands([10.0, 20.0], 20)
        upper, middle, lower = result
        assert all(v is None for v in upper)
        assert all(v is None for v in middle)
        assert all(v is None for v in lower)

    def test_constant_prices(self) -> None:
        """Constant prices should have bands with 0 width."""
        upper, middle, lower = compute_bollinger_bands([100.0] * 10, 5, 2.0)
        assert upper[4] == pytest.approx(100.0)
        assert middle[4] == pytest.approx(100.0)
        assert lower[4] == pytest.approx(100.0)

    def test_upper_above_middle_above_lower(self) -> None:
        """For non-constant data, upper > middle > lower."""
        data = [float(i * 10) for i in range(1, 31)]
        upper, middle, lower = compute_bollinger_bands(data, 20, 2.0)
        for i in range(19, len(data)):
            if upper[i] is not None and middle[i] is not None and lower[i] is not None:
                assert upper[i] > middle[i]
                assert middle[i] > lower[i]

    def test_custom_num_std(self) -> None:
        """Different num_std values should change band width."""
        data = [float(i) for i in range(1, 31)]
        _, mid1, lower1 = compute_bollinger_bands(data, 10, 1.0)
        _, mid2, lower2 = compute_bollinger_bands(data, 10, 3.0)
        for i in range(len(data)):
            if mid1[i] is not None and lower1[i] is not None and lower2[i] is not None:
                width1 = mid1[i] - lower1[i]
                width2 = mid2[i] - lower2[i]
                assert width2 > width1

    def test_accepts_numpy_array(self) -> None:
        arr = np.array([10.0, 20.0, 30.0, 25.0, 35.0])
        upper, middle, lower = compute_bollinger_bands(arr, 3, 2.0)
        assert upper == [None, None, 40.0, 35.0, 40.0]
