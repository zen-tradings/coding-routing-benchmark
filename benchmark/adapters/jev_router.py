from .base import RouterAdapter


class JevRouterAdapter(RouterAdapter):
    name = "pi-jev-model-router"
    command_env = "PI_JEV_ROUTER_COMMAND"
