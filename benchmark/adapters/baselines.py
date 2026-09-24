"""Built-in reference routers that need no external command.

Baselines give the router scores a floor: a router that cannot beat `always_mid` or
`length_heuristic` on a prompt set is not adding information on that set.
"""

from __future__ import annotations

import json
import os
import random
import re
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from benchmark.models import RouteResult, normalize_model_name

from .base import RouterAdapter, elapsed_ms


class BaselineAdapter(RouterAdapter):
    is_baseline = True
    command_env = ""

    def route(self, prompt: str, available_models: list[str], context: dict | None = None) -> RouteResult:
        started = time.perf_counter()
        try:
            selected = self.choose(prompt, available_models)
            model, tier = normalize_model_name(selected)
            return RouteResult(model, tier, elapsed_ms(started), raw_output=selected)
        except ValueError as exc:
            return RouteResult(None, None, elapsed_ms(started), error=f"invalid_model: {exc}")

    def choose(self, prompt: str, available_models: list[str]) -> str:
        raise NotImplementedError


class AlwaysLowAdapter(BaselineAdapter):
    name = "always_low"

    def choose(self, prompt: str, available_models: list[str]) -> str:
        return "claude-haiku"


class AlwaysMidAdapter(BaselineAdapter):
    name = "always_mid"

    def choose(self, prompt: str, available_models: list[str]) -> str:
        return "claude-sonnet"


class AlwaysHighAdapter(BaselineAdapter):
    name = "always_high"

    def choose(self, prompt: str, available_models: list[str]) -> str:
        return "claude-opus"


class RandomAdapter(BaselineAdapter):
    """Uniform choice from the available models. The sequence is reproducible for a given seed,
    prompt order, and repetition count."""

    name = "random"
    default_seed = 0

    def __init__(self, timeout_seconds: float | None = None, options: dict | None = None):
        super().__init__(timeout_seconds, options)
        self.seed = self.options.get("seed", self.default_seed)
        if not isinstance(self.seed, int) or isinstance(self.seed, bool):
            raise ValueError("routers.random.seed must be an integer")
        self._rng = random.Random(self.seed)

    def run_metadata(self) -> dict[str, Any]:
        return {"model": None, "seed": self.seed}

    def choose(self, prompt: str, available_models: list[str]) -> str:
        return self._rng.choice(available_models)


class LengthHeuristicAdapter(BaselineAdapter):
    """The toy router from the README: keywords pick HIGH, long prompts pick MID, the rest LOW."""

    name = "length_heuristic"

    def choose(self, prompt: str, available_models: list[str]) -> str:
        text = prompt.lower()
        if any(word in text for word in ("design", "architecture")):
            return "opus"
        return "sonnet" if len(text) > 200 else "haiku"


LLM_ROUTER_SYSTEM_PROMPT = (
    "You are a model router for software-development requests. Choose the least capable model that can "
    "complete the request well. claude-haiku: small, fast, for bounded and low-risk tasks. claude-sonnet: "
    "for typical engineering work that needs multi-step reasoning. claude-opus: for complex, ambiguous, "
    "high-risk, or system-wide work. Reply with exactly one model name from the list and nothing else."
)


class LlmLowAdapter(BaselineAdapter):
    """The LOW-tier model acting as a router through one Messages API call (standard library only)."""

    name = "llm_low"
    api_url = "https://api.anthropic.com/v1/messages"
    api_version = "2023-06-01"

    @property
    def api_key_env(self) -> str:
        return self.options.get("api_key_env", "ANTHROPIC_API_KEY")

    def unavailable_reason(self) -> str | None:
        if not os.environ.get(self.api_key_env):
            return f"{self.api_key_env} is not set"
        if not self.options.get("model"):
            return "no model id configured (set [model_ids] claude-haiku or routers.llm_low.model)"
        return None

    def run_metadata(self) -> dict[str, Any]:
        return {"model": self.options.get("model"), "api_key_env": self.api_key_env, "temperature": self.options.get("temperature")}

    def route(self, prompt: str, available_models: list[str], context: dict | None = None) -> RouteResult:
        started = time.perf_counter()
        reason = self.unavailable_reason()
        if reason:
            return RouteResult(None, None, elapsed_ms(started), error=f"configuration_error: {reason}")
        try:
            text = self._call(prompt, available_models)
        except (TimeoutError, socket.timeout):
            return RouteResult(None, None, elapsed_ms(started), error="timeout")
        except urllib.error.HTTPError as exc:
            return RouteResult(None, None, elapsed_ms(started), error=f"router_error: HTTP {exc.code}")
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                return RouteResult(None, None, elapsed_ms(started), error="timeout")
            return RouteResult(None, None, elapsed_ms(started), error=f"router_error: {exc.reason}")
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            return RouteResult(None, None, elapsed_ms(started), error=f"parse_error: {exc}")
        try:
            model, tier = normalize_model_name(parse_model_reply(text))
        except ValueError as exc:
            return RouteResult(None, None, elapsed_ms(started), raw_output=text, error=f"invalid_model: {exc}")
        return RouteResult(model, tier, elapsed_ms(started), raw_output=text)

    def _call(self, prompt: str, available_models: list[str]) -> str:
        body: dict[str, Any] = {
            "model": self.options["model"],
            "max_tokens": 32,
            "system": LLM_ROUTER_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"Available models: {', '.join(available_models)}\n\nRequest:\n{prompt}"}],
        }
        if self.options.get("temperature") is not None:
            body["temperature"] = self.options["temperature"]
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "x-api-key": os.environ[self.api_key_env],
                "anthropic-version": self.api_version,
                "content-type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return "".join(block["text"] for block in payload["content"] if block.get("type") == "text")


def parse_model_reply(text: str) -> str:
    """Pull one model family out of a free-text reply; ambiguous or empty replies are rejected."""
    families = set(re.findall(r"haiku|sonnet|opus", text.lower()))
    if len(families) == 1:
        return families.pop()
    return text.strip()


BASELINE_ADAPTERS = {
    "always_low": AlwaysLowAdapter,
    "always_mid": AlwaysMidAdapter,
    "always_high": AlwaysHighAdapter,
    "random": RandomAdapter,
    "length_heuristic": LengthHeuristicAdapter,
    "llm_low": LlmLowAdapter,
}
