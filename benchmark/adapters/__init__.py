"""Router adapter implementations."""

from .auto_router import AutoRouterAdapter
from .jev_router import JevRouterAdapter
from .model_router import ModelRouterAdapter

ADAPTERS = {
    "auto": AutoRouterAdapter,
    "model": ModelRouterAdapter,
    "jev": JevRouterAdapter,
}

