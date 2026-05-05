"""Tests for market data cache and fetcher."""

from __future__ import annotations

import json
from pathlib import Path

import ccxt
import pytest

from cryplative.core.models import Candle
from cryplative.market_fetcher.cache import (
    _cache_path,
    load_cache,
    save_cache,
    update_cache,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_cache_dir(tmp_path: Path) -> Path:
    """Temporary directory for cache files."""
    cache_dir = tmp_path / "market_cache"
    return cache_dir


def _make_candle(
    index: int = 0,
    symbol: str = "BTC/USDT",
    interval: str = "1h",
    base_time: int = 1704067200000,
) -> Candle:
    """Create a test candle with configurable open_time offset."""
    step = 3600000  # 1 hour in ms
    open_time = base_time + index * step
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        open=42000.0 + index * 10,
        high=42500.0 + index * 10,
        low=41800.0 + index * 10,
        close=42300.0 + index * 10,
        volume=1234.56 + index,
        close_time=open_time + 3599999,
        closed=True,
    )


def _sample_candles(n: int = 10, symbol: str = "BTC/USDT") -> list[Candle]:
    """Create n sample candles."""
    return [_make_candle(i, symbol=symbol) for i in range(n)]


# ---------------------------------------------------------------------------
# Cache path tests
# ---------------------------------------------------------------------------


class TestCachePath:
    def test_cache_path_format(self, tmp_cache_dir: Path) -> None:
        path = _cache_path(tmp_cache_dir, "BTC/USDT", "1h")
        assert path.name == "BTC_USDT_1h.json"
        assert path.parent == tmp_cache_dir

    def test_cache_path_different_symbol(self, tmp_cache_dir: Path) -> None:
        path = _cache_path(tmp_cache_dir, "ETH/USDT", "4h")
        assert path.name == "ETH_USDT_4h.json"


# ---------------------------------------------------------------------------
# Save / Load roundtrip
# ---------------------------------------------------------------------------


class TestCacheSaveLoad:
    def test_save_and_load(self, tmp_cache_dir: Path) -> None:
        candles = _sample_candles(5)
        save_cache(tmp_cache_dir, "BTC/USDT", "1h", candles)

        loaded = load_cache(tmp_cache_dir, "BTC/USDT", "1h")
        assert len(loaded) == 5
        assert loaded[0].symbol == "BTC/USDT"
        assert loaded[0].close == 42300.0

    def test_load_empty_when_missing(self, tmp_cache_dir: Path) -> None:
        loaded = load_cache(tmp_cache_dir, "BTC/USDT", "1h")
        assert loaded == []

    def test_save_creates_directory(self, tmp_cache_dir: Path) -> None:
        deep_dir = tmp_cache_dir / "nested" / "cache"
        candles = _sample_candles(2)
        save_cache(deep_dir, "BTC/USDT", "1h", candles)

        assert deep_dir.exists()
        loaded = load_cache(deep_dir, "BTC/USDT", "1h")
        assert len(loaded) == 2

    def test_file_is_valid_json(self, tmp_cache_dir: Path) -> None:
        candles = _sample_candles(3)
        save_cache(tmp_cache_dir, "BTC/USDT", "1h", candles)

        path = _cache_path(tmp_cache_dir, "BTC/USDT", "1h")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["symbol"] == "BTC/USDT"

    def test_overwrite_on_save(self, tmp_cache_dir: Path) -> None:
        candles1 = _sample_candles(3)
        save_cache(tmp_cache_dir, "BTC/USDT", "1h", candles1)

        candles2 = _sample_candles(5, symbol="BTC/USDT")
        save_cache(tmp_cache_dir, "BTC/USDT", "1h", candles2)

        loaded = load_cache(tmp_cache_dir, "BTC/USDT", "1h")
        assert len(loaded) == 5


# ---------------------------------------------------------------------------
# Update / merge / dedup
# ---------------------------------------------------------------------------


class TestCacheUpdate:
    def test_merge_new_with_existing(self, tmp_cache_dir: Path) -> None:
        existing = _sample_candles(5)
        save_cache(tmp_cache_dir, "BTC/USDT", "1h", existing)

        # New candles with some overlap (indices 3-8)
        new_candles = [_make_candle(i, symbol="BTC/USDT") for i in range(3, 9)]

        merged = update_cache(tmp_cache_dir, "BTC/USDT", "1h", new_candles)
        assert len(merged) == 9  # indices 0-8
        # Verify sorted
        times = [c.open_time for c in merged]
        assert times == sorted(times)

    def test_dedup_by_open_time(self, tmp_cache_dir: Path) -> None:
        existing = _sample_candles(5)
        save_cache(tmp_cache_dir, "BTC/USDT", "1h", existing)

        # New candle with same open_time but different close
        overlap = Candle(
            symbol="BTC/USDT",
            interval="1h",
            open_time=1704067200000,  # same as index 0
            open=99999.0,
            high=99999.0,
            low=99999.0,
            close=99999.0,
            volume=9999.0,
            close_time=1704070799999,
            closed=True,
        )
        merged = update_cache(tmp_cache_dir, "BTC/USDT", "1h", [overlap])
        assert len(merged) == 5  # deduped
        # The overlapping candle should be the new one
        first = next(c for c in merged if c.open_time == 1704067200000)
        assert first.close == 99999.0

    def test_update_empty_cache(self, tmp_cache_dir: Path) -> None:
        new_candles = _sample_candles(5)
        merged = update_cache(tmp_cache_dir, "BTC/USDT", "1h", new_candles)
        assert len(merged) == 5

    def test_separate_symbol_cache(self, tmp_cache_dir: Path) -> None:
        btc = _sample_candles(3, symbol="BTC/USDT")
        eth = _sample_candles(2, symbol="ETH/USDT")

        save_cache(tmp_cache_dir, "BTC/USDT", "1h", btc)
        save_cache(tmp_cache_dir, "ETH/USDT", "1h", eth)

        loaded_btc = load_cache(tmp_cache_dir, "BTC/USDT", "1h")
        loaded_eth = load_cache(tmp_cache_dir, "ETH/USDT", "1h")

        assert len(loaded_btc) == 3
        assert len(loaded_eth) == 2
        assert loaded_btc[0].symbol == "BTC/USDT"
        assert loaded_eth[0].symbol == "ETH/USDT"


# ---------------------------------------------------------------------------
# Fetcher tests (mocked ccxt)
# ---------------------------------------------------------------------------


class TestMarketFetcher:
    def test_ohlcv_to_candle_conversion(self) -> None:
        """Test that ccxt OHLCV arrays are correctly converted to Candle objects."""
        from cryplative.market_fetcher.fetcher import _ohlcv_to_candle

        ohlcv = [
            1704067200000,  # timestamp
            42000.0,  # open
            42500.0,  # high
            41800.0,  # low
            42300.0,  # close
            1234.56,  # volume
        ]
        candle = _ohlcv_to_candle("BTC/USDT", "1h", ohlcv)

        assert candle.symbol == "BTC/USDT"
        assert candle.interval == "1h"
        assert candle.open_time == 1704067200000
        assert candle.open == 42000.0
        assert candle.high == 42500.0
        assert candle.low == 41800.0
        assert candle.close == 42300.0
        assert candle.volume == 1234.56
        assert candle.closed is True

    def test_get_candles_uses_cache(self, tmp_path: Path) -> None:
        """Test that cached data is returned without API calls."""
        from unittest.mock import MagicMock

        from cryplative.config import CryplativeConfig
        from cryplative.market_fetcher.fetcher import MarketFetcher

        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        # Pre-populate cache
        candles = _sample_candles(10)
        save_cache(tmp_path / "cache", "BTC/USDT", "1h", candles)

        fetcher = MarketFetcher(config)
        mock_exchange = MagicMock()
        fetcher._exchange = mock_exchange

        result = fetcher.get_candles("BTC/USDT", "1h")

        assert len(result) == 10
        # Exchange should not have been called
        mock_exchange.fetch_ohlcv.assert_not_called()

    def test_get_candles_fetches_when_cache_empty(self, tmp_path: Path) -> None:
        """Test that data is fetched from exchange when cache is empty."""
        from unittest.mock import MagicMock

        from cryplative.config import CryplativeConfig
        from cryplative.market_fetcher.fetcher import MarketFetcher

        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))
        fetcher = MarketFetcher(config)

        # Mock the exchange
        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.return_value = [
            [1704067200000, 42000.0, 42500.0, 41800.0, 42300.0, 1234.56],
            [1704070800000, 42300.0, 42800.0, 42100.0, 42600.0, 1345.67],
            [1704074400000, 42600.0, 43100.0, 42400.0, 42900.0, 1456.78],
        ]
        mock_exchange.has = {"fetchOHLCV": True}
        mock_exchange.rateLimit = 50
        fetcher._exchange = mock_exchange

        result = fetcher.get_candles("BTC/USDT", "1h")

        assert len(result) == 3
        assert result[0].close == 42300.0
        mock_exchange.fetch_ohlcv.assert_called_once()

    def test_rate_limiting_enabled(self, tmp_path: Path) -> None:
        """Test that rate limiting is enabled on the exchange."""
        from cryplative.config import CryplativeConfig
        from cryplative.market_fetcher.fetcher import MarketFetcher

        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))
        fetcher = MarketFetcher(config)

        assert fetcher._exchange.enableRateLimit is True

    def test_get_candles_filters_by_time_range(self, tmp_path: Path) -> None:
        """Test that get_candles filters results by start_time and end_time."""
        from cryplative.config import CryplativeConfig
        from cryplative.market_fetcher.cache import save_cache
        from cryplative.market_fetcher.fetcher import MarketFetcher

        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))

        # Pre-populate with candles at different times
        candles = _sample_candles(10)
        save_cache(tmp_path / "cache", "BTC/USDT", "1h", candles)

        fetcher = MarketFetcher(config)

        # Request a subset
        start = candles[3].open_time
        end = candles[7].open_time
        result = fetcher.get_candles("BTC/USDT", "1h", start_time=start, end_time=end)

        assert len(result) == 5  # indices 3-7 inclusive
        assert result[0].open_time == start
        assert result[-1].open_time == end

    def test_market_data_error_on_exchange_failure(self, tmp_path: Path) -> None:
        """Test that exchange errors are wrapped in MarketDataError."""
        from unittest.mock import MagicMock

        from cryplative.config import CryplativeConfig
        from cryplative.core.exceptions import MarketDataError
        from cryplative.market_fetcher.fetcher import MarketFetcher

        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))
        fetcher = MarketFetcher(config)

        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.side_effect = Exception("API rate limited")
        mock_exchange.has = {"fetchOHLCV": True}
        mock_exchange.rateLimit = 50
        fetcher._exchange = mock_exchange

        with pytest.raises(MarketDataError, match="API rate limited"):
            fetcher.get_candles("BTC/USDT", "1h", start_time=1, end_time=2)


class TestRetryLogic:
    """Tests for network retry logic."""

    def test_retry_on_network_error(self, tmp_path: Path) -> None:
        """Network errors should be retried up to 3 times."""
        from unittest.mock import MagicMock, patch

        from cryplative.config import CryplativeConfig
        from cryplative.market_fetcher.fetcher import MarketFetcher

        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))
        fetcher = MarketFetcher(config)

        mock_exchange = MagicMock()
        # Fail twice, then succeed
        mock_exchange.fetch_ohlcv.side_effect = [
            ccxt.NetworkError("Connection refused"),
            ccxt.NetworkError("Timeout"),
            [
                [1704067200000, 42000.0, 42500.0, 41800.0, 42300.0, 1234.56],
            ],
        ]
        mock_exchange.has = {"fetchOHLCV": True}
        mock_exchange.rateLimit = 50
        fetcher._exchange = mock_exchange

        with patch("cryplative.market_fetcher.fetcher.time.sleep"):
            result = fetcher.get_candles("BTC/USDT", "1h")

        assert len(result) == 1
        assert mock_exchange.fetch_ohlcv.call_count == 3

    def test_no_retry_on_non_network_error(self, tmp_path: Path) -> None:
        """Non-network errors should NOT be retried."""
        from unittest.mock import MagicMock

        from cryplative.config import CryplativeConfig
        from cryplative.core.exceptions import MarketDataError
        from cryplative.market_fetcher.fetcher import MarketFetcher

        config = CryplativeConfig(market_cache_dir=str(tmp_path / "cache"))
        fetcher = MarketFetcher(config)

        mock_exchange = MagicMock()
        mock_exchange.fetch_ohlcv.side_effect = ccxt.BadSymbol("Invalid symbol")
        mock_exchange.has = {"fetchOHLCV": True}
        mock_exchange.rateLimit = 50
        fetcher._exchange = mock_exchange

        with pytest.raises(MarketDataError, match="Invalid symbol"):
            fetcher.get_candles("BTC/USDT", "1h", start_time=1, end_time=2)

        # Should only be called once (no retry)
        assert mock_exchange.fetch_ohlcv.call_count == 1
