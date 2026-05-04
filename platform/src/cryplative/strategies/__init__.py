"""Trading strategies and registry.

Importing this module triggers registration of all strategies.
"""

from cryplative.strategies.registry import StrategyRegistry

# Import strategy modules to trigger registration
from cryplative.strategies import sma_crossover  # noqa: F401

__all__ = ["StrategyRegistry"]
