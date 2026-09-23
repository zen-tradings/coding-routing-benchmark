"""CLI runner for the Pi model router benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmark.adapters import ADAPTERS
from benchmark.config import load_config
from benchmark.models import AVAILABLE_MODELS, TIER_INDEX, Prompt, prompt_from_dict
from benchmark.reporting import write_summary


def load_prompts(path: Path) -> list[Prompt]:
    prompts = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            prompt = prompt_from_dict(value)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        if prompt.id in seen:
            raise ValueError(f"duplicate prompt id: {prompt.id}")
        seen.add(prompt.id)
        prompts.append(prompt)
    if not prompts:
        raise ValueError("prompt file contains no prompts")
    return prompts


def make_decision(router_name: str, prompt: Prompt, repeat: int, result, run_id: str) -> dict:
    selected_tier = result.selected_tier
    expected_index = TIER_INDEX[prompt.expected_tier]
    selected_index = TIER_INDEX[selected_tier] if selected_tier in TIER_INDEX else None
    return {
        "run_id": run_id,
        "router": router_name,
        "prompt_id": prompt.id,
        "category": prompt.category,
        "expected_tier": prompt.expected_tier,
        "reference_model": prompt.expected_model,
        "reference_rationale": prompt.reference_rationale,
        "selected_model": result.selected_model,
        "selected_tier": selected_tier,
        "routing_ms": result.routing_ms,
        "repeat": repeat,
        "match": result.selected_model == prompt.expected_model if result.selected_model else False,
        "tier_delta": selected_index - expected_index if selected_index is not None else None,
        "error": result.error,
    }


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", default="prompts/dev_v2.jsonl", type=Path)
    parser.add_argument("--runs", type=int)
    parser.add_argument("--output", type=Path, default=Path("results/run-001"))
    parser.add_argument("--router", choices=sorted(ADAPTERS), help="run only one router")
    parser.add_argument("--config", type=Path, default=Path("benchmark.toml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    runs = args.runs if args.runs is not None else config["benchmark"]["runs"]
    if runs < 1:
        parser.error("--runs must be at least 1")
    try:
        prompts = load_prompts(args.prompts)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    configured_routers = [key for key in ADAPTERS if config["routers"].get(key, {}).get("enabled", True)]
    router_keys = [args.router] if args.router else configured_routers
    if args.dry_run:
        print(f"validated {len(prompts)} prompts, {len(router_keys)} adapters, {len(AVAILABLE_MODELS)} available models")
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    decisions = []
    for router_key in router_keys:
        adapter = ADAPTERS[router_key](timeout_seconds=config["benchmark"]["timeout_seconds"])
        for prompt in prompts:
            for repeat in range(1, runs + 1):
                result = adapter.route(prompt.prompt, AVAILABLE_MODELS)
                decisions.append(make_decision(adapter.name, prompt, repeat, result, run_id))

    with (args.output / "results.jsonl").open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, sort_keys=True) + "\n")
    metadata = {
        "run_id": run_id,
        "timestamp": run_id,
        "git_commit": git_commit(),
        "prompt_set": args.prompts.name,
        "routers": router_keys,
        "router_names": [ADAPTERS[key]().name for key in router_keys],
        "repetitions": runs,
        "config_file": str(args.config),
        "timeout_seconds": config["benchmark"]["timeout_seconds"],
        "available_models": AVAILABLE_MODELS,
        "python_version": sys.version,
        "platform": platform.platform(),
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    write_summary(args.output, decisions)
    print(f"wrote {len(decisions)} decisions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
