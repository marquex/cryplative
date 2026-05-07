"""Fetch all data needed for H2 strategy backtesting."""

from cryplative.config import CryplativeConfig, setup_logging
from cryplative.market_fetcher.fetcher import MarketFetcher


def main():
    config = CryplativeConfig()
    setup_logging(config)
    fetcher = MarketFetcher(config)

    pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT"]
    intervals = ["4h", "1d"]
    start_ts = 1704067200000  # 2024-01-01 00:00:00 UTC
    end_ts = 1746595200000    # 2026-05-07 00:00:00 UTC

    for symbol in pairs:
        for interval in intervals:
            print(f"Fetching {symbol} {interval}...")
            try:
                candles = fetcher.get_candles(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_ts,
                    end_time=end_ts,
                )
                print(f"  -> {len(candles)} candles cached")
            except Exception as e:
                print(f"  -> ERROR: {e}")

    print("\nAll fetches complete.")


if __name__ == "__main__":
    main()
