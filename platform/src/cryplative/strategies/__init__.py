"""Trading strategies and registry.

Importing this module triggers registration of all strategies.
"""

# Import strategy modules to trigger registration
from cryplative.strategies import sma_crossover  # noqa: F401
from cryplative.strategies.registry import StrategyRegistry

__all__ = ["StrategyRegistry"]
