"""Strategy registry for discovering and instantiating trading strategies."""

from __future__ import annotations

from cryplative.core.interfaces import Strategy


class StrategyRegistry:
    """Registry of available strategies.

    Strategies are registered via the ``@StrategyRegistry.register`` decorator.
    """

    _strategies: dict[str, type[Strategy]] = {}

    @classmethod
    def register(cls, strategy_class: type[Strategy]) -> type[Strategy]:
        """Decorator to register a strategy class."""
        # Access strategy_id as a class attribute; if it's a property,
        # instantiate a temporary object to get the value.
        instance = strategy_class.__new__(strategy_class)
        sid = instance.strategy_id
        cls._strategies[sid] = strategy_class
        return strategy_class

    @classmethod
    def get(cls, strategy_id: str) -> type[Strategy]:
        """Get a strategy class by ID. Raises KeyError if not found."""
        if strategy_id not in cls._strategies:
            available = list(cls._strategies.keys())
            raise KeyError(
                f"Strategy '{strategy_id}' not registered. Available: {available}"
            )
        return cls._strategies[strategy_id]

    @classmethod
    def list_strategies(cls) -> list[str]:
        """Return all registered strategy IDs."""
        return list(cls._strategies.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registered strategies. Useful for testing."""
        cls._strategies.clear()
