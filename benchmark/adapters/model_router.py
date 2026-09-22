from .base import RouterAdapter


class ModelRouterAdapter(RouterAdapter):
    name = "pi-model-router"
    command_env = "PI_MODEL_ROUTER_COMMAND"
