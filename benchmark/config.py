"""Small TOML configuration loader for benchmark defaults."""

from __future__ import annotations

import tomllib
from pathlib import Path


DEFAULT_CONFIG = {
    "benchmark": {"runs": 3, "timeout_seconds": 10},
    "models": {"low": "claude-haiku", "mid": "claude-sonnet", "high": "claude-opus"},
    "routers": {"auto": {"enabled": True}, "model": {"enabled": True}, "jev": {"enabled": True}},
}


def load_config(path: Path) -> dict:
    if not path.exists():
        return DEFAULT_CONFIG
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    benchmark = config.get("benchmark", {})
    runs = benchmark.get("runs", 3)
    timeout = benchmark.get("timeout_seconds", 10)
    if not isinstance(runs, int) or runs < 1:
        raise ValueError("benchmark.runs must be a positive integer")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("benchmark.timeout_seconds must be positive")
    models = config.get("models", {})
    if {models.get(key) for key in ("low", "mid", "high")} != {"claude-haiku", "claude-sonnet", "claude-opus"}:
        raise ValueError("models must contain exactly the canonical Haiku, Sonnet, and Opus choices")
    return {"benchmark": {"runs": runs, "timeout_seconds": timeout}, "models": models, "routers": config.get("routers", {})}
