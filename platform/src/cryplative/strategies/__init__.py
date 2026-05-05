"""Trading strategies and registry.

Importing this module triggers auto-discovery of all strategy modules.
Modules whose names start with "_" (e.g., _template) are skipped.
"""

import importlib
import pkgutil
from pathlib import Path

from cryplative.strategies.registry import StrategyRegistry

# Auto-import all modules in this package to trigger @StrategyRegistry.register decorators.
# Skip _template (it's a template, not a real strategy).
for _module_info in pkgutil.iter_modules([str(Path(__file__).resolve().parent)]):
    if not _module_info.name.startswith("_"):
        importlib.import_module(f".{_module_info.name}", __package__)

__all__ = ["StrategyRegistry"]
