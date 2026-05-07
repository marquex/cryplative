"""Market data fetcher using ccxt to pull candle data from exchanges."""

from __future__ import annotations

import time
from typing import Any

import ccxt
import structlog

from cryplative.config import CryplativeConfig
from cryplative.core.exceptions import MarketDataError
from cryplative.core.interfaces import DataProvider
from cryplative.core.models import Candle
from cryplative.market_fetcher.cache import load_cache, update_cache

logger = structlog.get_logger()

_MAX_RETRIES = 3
_RETRY_BACKOFFS = [1.0, 2.0, 4.0]


def _ohlcv_to_candle(symbol: str, interval: str, ohlcv: list[Any]) -> Candle:
    """Convert a ccxt OHLCV array to a Candle object.

    ccxt returns: [timestamp, open, high, low, close, volume]
    """
    close_time = ohlcv[0] + _interval_to_ms(interval) - 1
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time=int(ohlcv[0]),
        open=float(ohlcv[1]),
        high=float(ohlcv[2]),
        low=float(ohlcv[3]),
        close=float(ohlcv[4]),
        volume=float(ohlcv[5]),
        close_time=close_time,
        closed=True,
    )


def _interval_to_ms(interval: str) -> int:
    """Convert a ccxt interval string to milliseconds."""
    unit = interval[-1]
    value = int(interval[:-1])
    multipliers = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}
    return value * multipliers.get(unit, 3_600_000)


class MarketFetcher(DataProvider):
    """Fetches candle data from exchanges via ccxt, with local caching."""

    def __init__(self, config: CryplativeConfig | None = None) -> None:
        self._config = config or CryplativeConfig()
        self._exchange = self._create_exchange()
        self._cache_dir = self._config.resolve_market_cache_dir()

    def _create_exchange(self) -> ccxt.Exchange:
        """Create and configure the ccxt exchange instance."""
        exchange_class = getattr(ccxt, self._config.exchange_id, ccxt.binance)
        exchange_params: dict[str, Any] = {
            "enableRateLimit": True,
        }
        if self._config.binance_api_key:
            exchange_params["apiKey"] = self._config.binance_api_key
        if self._config.binance_api_secret:
            exchange_params["secret"] = self._config.binance_api_secret

        return exchange_class(exchange_params)

    def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> list[Candle]:
        """Fetch candle data, using cache where possible.

        Returns sorted by open_time ascending, filtered by start_time/end_time.
        """
        try:
            # Load cached data
            cached = load_cache(self._cache_dir, symbol, interval)

            # Determine what new data we need
            need_fetch = False
            fetch_since: int | None = None

            if start_time is not None:
                if cached:
                    latest_cached_time = max(c.open_time for c in cached)
                    if start_time > latest_cached_time:
                        # We need data after the cache
                        need_fetch = True
                        fetch_since = start_time
                    else:
                        need_fetch = False
                else:
                    need_fetch = True
                    fetch_since = start_time
            elif not cached:
                # No cache, no start_time: just fetch the limit
                need_fetch = True
                fetch_since = None
            else:
                # No start_time but have cache, and no end_time beyond cache
                if end_time is not None:
                    latest_cached_time = max(c.open_time for c in cached)
                    if end_time > latest_cached_time:
                        need_fetch = True
                        fetch_since = latest_cached_time + 1

            if need_fetch:
                logger.info(
                    "fetching_market_data",
                    symbol=symbol,
                    interval=interval,
                    since=fetch_since,
                )

                fetch_limit = limit or 1000
                all_new_candles: list[Candle] = []
                current_since = fetch_since

                while True:
                    ohlcv: list[list[Any]] | None = None
                    last_error: Exception | None = None

                    for attempt in range(_MAX_RETRIES):
                        try:
                            ohlcv = self._exchange.fetch_ohlcv(
                                symbol,
                                timeframe=interval,
                                since=current_since,
                                limit=fetch_limit,
                            )
                            last_error = None
                            break
                        except ccxt.NetworkError as e:
                            last_error = e
                            if attempt < _MAX_RETRIES - 1:
                                wait = _RETRY_BACKOFFS[attempt]
                                logger.warning(
                                    "network_error_retrying",
                                    symbol=symbol,
                                    interval=interval,
                                    attempt=attempt + 1,
                                    max_retries=_MAX_RETRIES,
                                    wait_seconds=wait,
                                )
                                time.sleep(wait)
                            continue
                        except Exception as e:
                            last_error = e
                            break

                    if last_error is not None:
                        raise MarketDataError(
                            f"Failed to fetch OHLCV data for {symbol} {interval}: "
                            f"{last_error}"
                        ) from last_error

                    if not ohlcv:
                        break

                    new_candles = [_ohlcv_to_candle(symbol, interval, row) for row in ohlcv]
                    all_new_candles.extend(new_candles)

                    if len(ohlcv) < fetch_limit:
                        break

                    # Move since forward to avoid duplicates
                    current_since = new_candles[-1].open_time + 1

                    # Safety: respect end_time
                    if end_time is not None and new_candles[-1].open_time >= end_time:
                        break

                if all_new_candles:
                    cached = update_cache(self._cache_dir, symbol, interval, all_new_candles)

            # Filter by time range
            result = cached
            if start_time is not None:
                result = [c for c in result if c.open_time >= start_time]
            if end_time is not None:
                result = [c for c in result if c.open_time <= end_time]
            if limit is not None:
                result = result[:limit]

            logger.debug(
                "get_candles_result",
                symbol=symbol,
                interval=interval,
                count=len(result),
            )

            return result

        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(
                f"Unexpected error fetching candles for {symbol} {interval}: {e}"
            ) from e

    def list_pairs(
        self,
        quote: str | None = None,
        active_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List available trading pairs from the exchange.

        Returns a list of dicts, each containing:
            - symbol: str          # e.g., "BTC/USDT"
            - base: str            # e.g., "BTC"
            - quote: str           # e.g., "USDT"
            - active: bool         # whether the market is active
            - price_precision: int # decimal places for price
            - min_order_size: float | None  # minimum order quantity

        Args:
            quote: Filter by quote currency (e.g., "USDT", "USDC").
                   Case-insensitive. None = no filter.
            active_only: If True (default), exclude delisted/inactive pairs.

        Raises:
            MarketDataError: If the exchange API call fails after retries.
        """
        try:
            # Load markets from exchange
            markets = self._exchange.load_markets()

            # Convert to list of dicts and filter
            result = []
            for market_id, market in markets.items():
                # Filter by active status
                if active_only and not market.get("active", True):
                    continue

                # Filter by quote currency (case-insensitive)
                if quote is not None:
                    market_quote = market.get("quote", "")
                    if market_quote.upper() != quote.upper():
                        continue

                # Extract relevant fields
                pair_info = {
                    "symbol": market.get("symbol", market_id),
                    "base": market.get("base", ""),
                    "quote": market.get("quote", ""),
                    "active": market.get("active", True),
                    "price_precision": market.get("precision", {}).get("price", 8),
                    "min_order_size": market.get("limits", {}).get("amount", {}).get("min"),
                }
                result.append(pair_info)

            # Sort alphabetically by symbol
            result.sort(key=lambda x: x["symbol"])

            logger.debug(
                "list_pairs_result",
                count=len(result),
                quote=quote,
                active_only=active_only,
            )

            return result

        except ccxt.NetworkError as e:
            raise MarketDataError(f"Network error loading markets: {e}") from e
        except Exception as e:
            raise MarketDataError(f"Error loading markets from exchange: {e}") from e
