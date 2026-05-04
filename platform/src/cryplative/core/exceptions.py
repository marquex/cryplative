"""Custom exceptions for Cryplative."""


class CryplativeError(Exception):
    """Base exception for all Cryplative errors."""


class MarketDataError(CryplativeError):
    """Error fetching market data."""


class StrategyError(CryplativeError):
    """Error in strategy execution."""


class BacktestError(CryplativeError):
    """Error during backtesting."""


class ConfigurationError(CryplativeError):
    """Invalid configuration."""
