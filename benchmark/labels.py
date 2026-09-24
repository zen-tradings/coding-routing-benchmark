"""Optional second-labeler reference file: prompts/<set>.labels_b.jsonl."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from benchmark.models import AVAILABLE_MODELS, Prompt, normalize_model_name


def labels_b_path(prompts_path: Path) -> Path:
    return prompts_path.with_name(prompts_path.stem + ".labels_b.jsonl")


def load_labels_b(path: Path, prompts: list[Prompt]) -> dict[str, dict]:
    """Load {id, reference_model, rationale} records keyed by prompt id; every id must exist in the prompt set."""
    known = {prompt.id for prompt in prompts}
    labels: dict[str, dict] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value, dict) or set(value) != {"id", "reference_model", "rationale"}:
                raise ValueError("record must have exactly the fields id, reference_model, rationale")
            if value["id"] not in known:
                raise ValueError(f"unknown prompt id {value['id']!r}")
            if value["id"] in labels:
                raise ValueError(f"duplicate id {value['id']!r}")
            if not isinstance(value["rationale"], str) or not value["rationale"].strip():
                raise ValueError("rationale must be a non-empty string")
            model, tier = normalize_model_name(value["reference_model"])
            if model not in AVAILABLE_MODELS:
                raise ValueError("reference_model is outside the available model pool")
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_number}: {exc}") from exc
        labels[value["id"]] = {"reference_model": model, "expected_tier": tier, "rationale": value["rationale"]}
    if not labels:
        raise ValueError(f"{path} contains no labels")
    return labels


def cohens_kappa(first: list[str], second: list[str]) -> float | None:
    """Cohen's kappa for two raters over the same items; None when chance agreement is 1 (undefined)."""
    if len(first) != len(second):
        raise ValueError("label lists must have the same length")
    if not first:
        return None
    n = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / n
    counts_a, counts_b = Counter(first), Counter(second)
    expected = sum(counts_a[label] * counts_b[label] for label in counts_a.keys() | counts_b.keys()) / (n * n)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def labeler_agreement(prompts: list[Prompt], labels_b: dict[str, dict], decisions: Iterable[dict], source: str) -> dict:
    """Compare labeler A (the prompt file) with labeler B and score routers on consensus prompts only."""
    compared = [prompt for prompt in prompts if prompt.id in labels_b]
    labels_a = [prompt.expected_model for prompt in compared]
    labels_second = [labels_b[prompt.id]["reference_model"] for prompt in compared]
    consensus = {prompt.id for prompt, a, b in zip(compared, labels_a, labels_second) if a == b}
    disagreements = [
        {"prompt_id": prompt.id, "labeler_a": a, "labeler_b": b, "rationale_b": labels_b[prompt.id]["rationale"]}
        for prompt, a, b in zip(compared, labels_a, labels_second)
        if a != b
    ]
    by_router: dict[str, list[dict]] = {}
    for row in decisions:
        if row["prompt_id"] in consensus and row.get("selected_model"):
            by_router.setdefault(row["router"], []).append(row)
    consensus_agreement = {
        router: {"agreement": sum(bool(row.get("match")) for row in rows) / len(rows), "successful_decisions": len(rows)}
        for router, rows in sorted(by_router.items())
    }
    return {
        "source": source,
        "prompts_compared": len(compared),
        "prompts_missing_labeler_b": sorted(prompt.id for prompt in prompts if prompt.id not in labels_b),
        "agreement": sum(a == b for a, b in zip(labels_a, labels_second)) / len(compared) if compared else None,
        "cohens_kappa": cohens_kappa(labels_a, labels_second),
        "consensus_prompts": len(consensus),
        "disagreements": disagreements,
        "router_agreement_on_consensus": consensus_agreement,
    }
