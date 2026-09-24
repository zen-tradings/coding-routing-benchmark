"""Small TOML configuration loader for benchmark defaults."""

from __future__ import annotations

import tomllib
from pathlib import Path

from benchmark.models import AVAILABLE_MODELS


DEFAULT_WEIGHTING = {"low": 0.6, "mid": 0.3, "high": 0.1}
DEFAULT_BOOTSTRAP = {"iterations": 2000, "seed": 12345}

DEFAULT_CONFIG = {
    "benchmark": {"runs": 3, "timeout_seconds": 10},
    "models": {"low": "claude-haiku", "mid": "claude-sonnet", "high": "claude-opus"},
    "routers": {"auto": {"enabled": True}, "model": {"enabled": True}, "jev": {"enabled": True}},
}


def load_config(path: Path) -> dict:
    if path.exists():
        with path.open("rb") as handle:
            config = tomllib.load(handle)
    else:
        config = DEFAULT_CONFIG
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
    return {
        "benchmark": {"runs": runs, "timeout_seconds": timeout},
        "models": models,
        "routers": config.get("routers", {}),
        "model_ids": load_model_ids(config.get("model_ids", {})),
        "prices": load_prices(config.get("prices", {})),
        "weighting": load_weighting(config.get("weighting", {})),
        "bootstrap": load_bootstrap(config.get("bootstrap", {})),
    }


def load_model_ids(value: dict) -> dict[str, str | None]:
    unknown = set(value) - set(AVAILABLE_MODELS)
    if unknown:
        raise ValueError(f"model_ids has unknown models: {sorted(unknown)}")
    if any(not isinstance(model_id, str) or not model_id.strip() for model_id in value.values()):
        raise ValueError("model_ids values must be non-empty strings")
    return {model: value.get(model) for model in AVAILABLE_MODELS}


def load_prices(value: dict) -> dict[str, float] | None:
    """Return a blended USD-per-MTok price per canonical model, or None when prices are not configured.

    Blended price = input_per_mtok + output_per_mtok (an equal input/output token mix). Only ratios
    between models are used, so the blend matters only if the models' input:output ratios differ.
    """
    if not value:
        return None
    if set(value) != set(AVAILABLE_MODELS):
        raise ValueError("prices must define every canonical model: " + ", ".join(AVAILABLE_MODELS))
    blended = {}
    for model in AVAILABLE_MODELS:
        entry = value[model]
        parts = [entry.get("input_per_mtok"), entry.get("output_per_mtok")] if isinstance(entry, dict) else [None]
        if any(not isinstance(part, (int, float)) or isinstance(part, bool) or part < 0 for part in parts):
            raise ValueError(f"prices.{model} needs non-negative input_per_mtok and output_per_mtok")
        blended[model] = float(sum(parts))
        if blended[model] <= 0:
            raise ValueError(f"prices.{model} must be positive")
    return blended


def load_weighting(value: dict) -> dict[str, float]:
    shares = {key: value.get(key, DEFAULT_WEIGHTING[key]) for key in ("low", "mid", "high")}
    if any(not isinstance(share, (int, float)) or isinstance(share, bool) or share < 0 for share in shares.values()):
        raise ValueError("weighting shares must be non-negative numbers")
    if abs(sum(shares.values()) - 1.0) > 1e-6:
        raise ValueError("weighting shares low + mid + high must sum to 1")
    return {tier.upper(): float(share) for tier, share in shares.items()}


def load_bootstrap(value: dict) -> dict[str, int]:
    iterations = value.get("iterations", DEFAULT_BOOTSTRAP["iterations"])
    seed = value.get("seed", DEFAULT_BOOTSTRAP["seed"])
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1:
        raise ValueError("bootstrap.iterations must be a positive integer")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("bootstrap.seed must be an integer")
    return {"iterations": iterations, "seed": seed}
