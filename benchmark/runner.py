"""CLI runner for the Pi model router benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmark.adapters import ADAPTERS, BASELINE_KEYS
from benchmark.config import load_config
from benchmark.labels import labeler_agreement, labels_b_path, load_labels_b
from benchmark.models import AVAILABLE_MODELS, TIER_INDEX, Prompt, prompt_from_dict
from benchmark.reporting import write_summary

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_ENV = "ROUTING_BENCHMARK_PROMPTS"
DEFAULT_PROMPTS = Path("prompts/dev_v2.jsonl")


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
        "tier_distance": abs(selected_index - expected_index) if selected_index is not None else None,
        "error": result.error,
    }


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=REPO_ROOT).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def git_dirty() -> bool | None:
    try:
        output = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True, cwd=REPO_ROOT).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return bool(output.strip())


def is_held_out(path: Path) -> bool:
    """A prompt file is held out when it lives outside the repo's prompts/ folder or under prompts/private/."""
    resolved = path.resolve()
    prompts_dir = REPO_ROOT / "prompts"
    return not resolved.is_relative_to(prompts_dir) or resolved.is_relative_to(prompts_dir / "private")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def router_options(key: str, config: dict) -> dict:
    options = {name: value for name, value in config["routers"].get(key, {}).items() if name != "enabled"}
    if key == "llm_low" and not options.get("model"):
        options["model"] = config["model_ids"].get(config["models"]["low"])
    return options


def route_prompt(adapter, prompt: Prompt):
    # Only pass context when the prompt has one, so adapters with the original route() signature keep working.
    if prompt.context is not None:
        return adapter.route(prompt.prompt, AVAILABLE_MODELS, context=prompt.context)
    return adapter.route(prompt.prompt, AVAILABLE_MODELS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", type=Path, help=f"prompt JSONL file (default: ${PROMPTS_ENV} or {DEFAULT_PROMPTS})")
    parser.add_argument("--runs", type=int)
    parser.add_argument("--output", type=Path, default=Path("results/run-001"))
    parser.add_argument("--router", choices=sorted(ADAPTERS), help="run only one router")
    parser.add_argument("--config", type=Path, default=Path("benchmark.toml"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--baselines", action="store_true", help="also run every built-in baseline router")
    args = parser.parse_args(argv)
    if args.prompts is None:
        args.prompts = Path(os.environ[PROMPTS_ENV]) if os.environ.get(PROMPTS_ENV) else DEFAULT_PROMPTS
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
    # Baselines are off unless enabled in config or requested with --baselines.
    configured_routers = [key for key in ADAPTERS if config["routers"].get(key, {}).get("enabled", key not in BASELINE_KEYS)]
    router_keys = [args.router] if args.router else configured_routers
    if args.baselines:
        router_keys += [key for key in BASELINE_KEYS if key not in router_keys]
    labels_path = labels_b_path(args.prompts)
    try:
        labels_b = load_labels_b(labels_path, prompts) if labels_path.exists() else None
        adapters = {key: ADAPTERS[key](timeout_seconds=config["benchmark"]["timeout_seconds"], options=router_options(key, config)) for key in router_keys}
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    held_out = is_held_out(args.prompts)
    if args.dry_run:
        print(f"validated {len(prompts)} prompts, {len(router_keys)} adapters, {len(AVAILABLE_MODELS)} available models")
        if labels_b is not None:
            print(f"validated {len(labels_b)} second-labeler records in {labels_path.name}")
        if held_out:
            print("prompt set is held out (outside prompts/ or under prompts/private/)")
        return 0

    skipped = {}
    for key, adapter in list(adapters.items()):
        reason = adapter.unavailable_reason()
        if reason:
            skipped[adapter.name] = reason
            print(f"skipping {adapter.name}: {reason}", file=sys.stderr)
            del adapters[key]

    args.output.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    decisions = []
    for adapter in adapters.values():
        for prompt in prompts:
            for repeat in range(1, runs + 1):
                result = route_prompt(adapter, prompt)
                decisions.append(make_decision(adapter.name, prompt, repeat, result, run_id))

    with (args.output / "results.jsonl").open("w", encoding="utf-8") as handle:
        for decision in decisions:
            handle.write(json.dumps(decision, sort_keys=True) + "\n")
    metadata = {
        "run_id": run_id,
        "timestamp": run_id,
        "git_commit": git_commit(),
        "prompt_set": args.prompts.name,
        "routers": list(adapters),
        "router_names": [adapter.name for adapter in adapters.values()],
        "repetitions": runs,
        "config_file": str(args.config),
        "timeout_seconds": config["benchmark"]["timeout_seconds"],
        "available_models": AVAILABLE_MODELS,
        "python_version": sys.version,
        "platform": platform.platform(),
        "git_dirty": git_dirty(),
        "model_ids": config["model_ids"],
        "router_settings": {adapter.name: adapter.run_metadata() for adapter in adapters.values()},
        "baseline_routers": [adapter.name for adapter in adapters.values() if adapter.is_baseline],
        "skipped_routers": skipped,
        "held_out": held_out,
        "prompt_sha256": file_sha256(args.prompts),
        "labels_b_file": labels_path.name if labels_b is not None else None,
        "weighting": {"target_shares": config["weighting"], "assumption": True},
        "bootstrap": config["bootstrap"],
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    labeler = labeler_agreement(prompts, labels_b, decisions, labels_path.name) if labels_b is not None else None
    write_summary(
        args.output,
        decisions,
        prices=config["prices"],
        target_shares=config["weighting"],
        bootstrap=config["bootstrap"],
        baselines={adapter.name for adapter in adapters.values() if adapter.is_baseline},
        labeler=labeler,
        skipped_routers=skipped,
    )
    print(f"wrote {len(decisions)} decisions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
