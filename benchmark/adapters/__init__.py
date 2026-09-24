"""Router adapter implementations."""

from .auto_router import AutoRouterAdapter
from .baselines import BASELINE_ADAPTERS
from .jev_router import JevRouterAdapter
from .model_router import ModelRouterAdapter

ADAPTERS = {
    "auto": AutoRouterAdapter,
    "model": ModelRouterAdapter,
    "jev": JevRouterAdapter,
    **BASELINE_ADAPTERS,
}

BASELINE_KEYS = tuple(BASELINE_ADAPTERS)
