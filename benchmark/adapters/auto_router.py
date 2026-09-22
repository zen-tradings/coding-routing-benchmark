from .base import RouterAdapter


class AutoRouterAdapter(RouterAdapter):
    name = "pi-auto-router"
    command_env = "PI_AUTO_ROUTER_COMMAND"
