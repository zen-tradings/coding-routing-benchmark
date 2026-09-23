"""Metrics for router decisions."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median
from typing import Iterable

from benchmark.models import TIER_INDEX


def score_decisions(decisions: Iterable[dict]) -> dict:
    rows = list(decisions)
    successful = [row for row in rows if row.get("selected_tier") in TIER_INDEX]
    under = [row for row in successful if row["tier_delta"] < 0]
    over = [row for row in successful if row["tier_delta"] > 0]
    latencies = [float(row["routing_ms"]) for row in rows if row.get("routing_ms") is not None]
    counts = Counter(row["selected_tier"] for row in successful)
    by_prompt = defaultdict(list)
    for row in successful:
        by_prompt[row["prompt_id"]].append(row["selected_tier"])
    stability_values = [max(Counter(selections).values()) / len(selections) for selections in by_prompt.values()]
    return {
        "total_decisions": len(rows),
        "successful_decisions": len(successful),
        "failure_count": len(rows) - len(successful),
        "failure_rate": (len(rows) - len(successful)) / len(rows) if rows else 0.0,
        "rubric_agreement": sum(row.get("match", False) for row in successful) / len(successful) if successful else None,
        "reference_model_agreement": sum(row.get("match", False) for row in successful) / len(successful) if successful else None,
        "under_route_rate": len(under) / len(successful) if successful else None,
        "over_route_rate": len(over) / len(successful) if successful else None,
        "under_route_severity": sum(-row["tier_delta"] for row in under),
        "over_route_severity": sum(row["tier_delta"] for row in over),
        "mean_routing_ms": mean(latencies) if latencies else None,
        "median_routing_ms": median(latencies) if latencies else None,
        "p95_routing_ms": percentile(latencies, 95) if latencies else None,
        "mean_stability": mean(stability_values) if stability_values else None,
        "tier_distribution": {tier: counts[tier] / len(successful) if successful else 0.0 for tier in TIER_INDEX},
        "unstable_prompts": sorted(prompt_id for prompt_id, selections in by_prompt.items() if len(set(selections)) > 1),
    }


def percentile(values: list[float], percentile_value: int) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile_value / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
