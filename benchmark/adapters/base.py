"""Common subprocess adapter for external Pi routers."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any

from benchmark.models import AVAILABLE_MODELS, RouteResult, normalize_model_name


class RouterAdapter(ABC):
    name: str
    command_env: str
    is_baseline = False

    def __init__(self, timeout_seconds: float | None = None, options: dict | None = None):
        self._configured_timeout_seconds = timeout_seconds
        self.options = dict(options or {})

    def unavailable_reason(self) -> str | None:
        """Return why this adapter should be skipped entirely, or None to run it."""
        return None

    def run_metadata(self) -> dict[str, Any]:
        """Settings recorded in metadata.json; `model` is the exact model id this router itself calls, if known."""
        return {"model": self.options.get("model")}

    def route(self, prompt: str, available_models: list[str], context: dict | None = None) -> RouteResult:
        started = time.perf_counter()
        command = os.environ.get(self.command_env)
        if not command:
            return RouteResult(None, None, elapsed_ms(started), error="configuration_error: set " + self.command_env)
        try:
            parsed = self._invoke(shlex.split(command), prompt, available_models, context)
            selected = parsed.get("selected_model", parsed.get("model", parsed.get("tier"))) if isinstance(parsed, dict) else parsed
            model, tier = normalize_model_name(selected)
            return RouteResult(model, tier, elapsed_ms(started), raw_output=parsed)
        except subprocess.TimeoutExpired:
            return RouteResult(None, None, elapsed_ms(started), error="timeout")
        except ValueError as exc:
            return RouteResult(None, None, elapsed_ms(started), error=f"invalid_model: {exc}")
        except json.JSONDecodeError as exc:
            return RouteResult(None, None, elapsed_ms(started), error=f"parse_error: {exc}")
        except OSError as exc:
            return RouteResult(None, None, elapsed_ms(started), error=f"router_error: {exc}")
        except Exception as exc:  # keep one broken router from aborting a run
            return RouteResult(None, None, elapsed_ms(started), error=f"router_error: {exc}")

    def _invoke(self, command: list[str], prompt: str, available_models: list[str], context: dict | None = None) -> Any:
        request = {"prompt": prompt, "available_models": available_models}
        if context is not None:
            request["context"] = context
        payload = json.dumps(request)
        completed = subprocess.run(command, input=payload, text=True, capture_output=True, timeout=self.timeout_seconds)
        if completed.returncode != 0:
            raise OSError(completed.stderr.strip() or f"command exited with {completed.returncode}")
        output = completed.stdout.strip()
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            if output:
                return output
            raise

    @property
    def timeout_seconds(self) -> float:
        if self._configured_timeout_seconds is not None:
            return self._configured_timeout_seconds
        try:
            return float(os.environ.get("PI_ROUTER_TIMEOUT_SECONDS", "10"))
        except ValueError:
            return 10.0


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
