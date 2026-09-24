"""Metrics for router decisions."""

from __future__ import annotations

import random
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


# ---------------------------------------------------------------------------
# Additional metrics. These never change the values returned by score_decisions.
# ---------------------------------------------------------------------------

ROW_METRICS = ("agreement", "under_route_rate", "over_route_rate", "mean_tier_distance", "mean_under_distance", "mean_over_distance")
COST_METRICS = ("cost_weighted_error", "mean_signed_cost_error")
CI_METRICS = ("agreement", "under_route_rate", "over_route_rate", "mean_tier_distance")


def tier_distance(selected_tier: str, reference_tier: str) -> int:
    """|chosen tier - reference tier| with LOW=0, MID=1, HIGH=2."""
    return abs(TIER_INDEX[selected_tier] - TIER_INDEX[reference_tier])


def relative_cost_error(selected_model: str, reference_model: str, prices: dict[str, float]) -> float:
    """Signed relative cost difference (chosen - reference) / reference, from configured per-model prices."""
    return (prices[selected_model] - prices[reference_model]) / prices[reference_model]


def row_values(row: dict, prices: dict[str, float] | None) -> dict[str, float]:
    delta = TIER_INDEX[row["selected_tier"]] - TIER_INDEX[row["expected_tier"]]
    values = {
        "agreement": float(bool(row.get("match", False))),
        "under_route_rate": float(delta < 0),
        "over_route_rate": float(delta > 0),
        "mean_tier_distance": float(abs(delta)),
        "mean_under_distance": float(-delta if delta < 0 else 0),
        "mean_over_distance": float(delta if delta > 0 else 0),
    }
    if prices is not None:
        signed = relative_cost_error(row["selected_model"], row["reference_model"], prices)
        values.update({
            "cost_weighted_error": abs(signed),
            "mean_signed_cost_error": signed,
            "_selected_cost": prices[row["selected_model"]],
            "_reference_cost": prices[row["reference_model"]],
        })
    return values


def score_extended(decisions: Iterable[dict], prices: dict[str, float] | None, target_shares: dict[str, float]) -> dict:
    """Severity, cost, and distribution-reweighted metrics over successful decisions.

    Under/over distances are averaged over *all* successful decisions, so
    mean_under_distance + mean_over_distance == mean_tier_distance.
    Reweighted values average each reference tier separately, then combine tiers with the
    target shares (renormalised over tiers present in the data).
    """
    successful = [row for row in decisions if row.get("selected_tier") in TIER_INDEX]
    values = [row_values(row, prices) for row in successful]
    names = ROW_METRICS + (COST_METRICS if prices is not None else ())
    result: dict = {name: (mean(v[name] for v in values) if values else None) for name in names}
    result["cost_ratio"] = cost_ratio(values) if prices is not None else None
    if prices is None:
        result.update({name: None for name in COST_METRICS})

    by_tier: dict[str, list[dict]] = defaultdict(list)
    for row, value in zip(successful, values):
        by_tier[row["expected_tier"]].append(value)
    present = [tier for tier in TIER_INDEX if by_tier.get(tier) and target_shares.get(tier, 0) > 0]
    total_share = sum(target_shares[tier] for tier in present)
    reweighted: dict = {}
    for name in names:
        reweighted[name] = (
            sum(target_shares[tier] * mean(v[name] for v in by_tier[tier]) for tier in present) / total_share if present else None
        )
    if prices is not None and present:
        selected = sum(target_shares[tier] * mean(v["_selected_cost"] for v in by_tier[tier]) for tier in present)
        reference = sum(target_shares[tier] * mean(v["_reference_cost"] for v in by_tier[tier]) for tier in present)
        reweighted["cost_ratio"] = selected / reference
    else:
        reweighted["cost_ratio"] = None
    if prices is None:
        reweighted.update({name: None for name in COST_METRICS})
    result["reweighted"] = reweighted
    result["reweighted_tiers_missing"] = [tier for tier in TIER_INDEX if target_shares.get(tier, 0) > 0 and tier not in present]
    return result


def cost_ratio(values: list[dict]) -> float | None:
    """Total cost of chosen models / total cost of reference models (1.0 = same spend)."""
    if not values:
        return None
    return sum(v["_selected_cost"] for v in values) / sum(v["_reference_cost"] for v in values)


def bootstrap_ci(decisions: Iterable[dict], iterations: int, seed: int, level: float = 0.95) -> dict[str, list[float] | None]:
    """Percentile bootstrap CIs, resampling prompts (all repeats of a prompt move together).

    Each resample recomputes the metric as successful-decision-weighted means, matching the point
    estimates. Using the same seed for every router gives identical prompt draws for routers that
    saw the same prompt set, so their intervals are paired.
    """
    rows = list(decisions)
    prompt_ids = sorted({row["prompt_id"] for row in rows})
    sums: dict[str, dict[str, float]] = {pid: {"n": 0.0, **{name: 0.0 for name in CI_METRICS}} for pid in prompt_ids}
    for row in rows:
        if row.get("selected_tier") not in TIER_INDEX:
            continue
        values = row_values(row, None)
        entry = sums[row["prompt_id"]]
        entry["n"] += 1
        for name in CI_METRICS:
            entry[name] += values[name]
    if not prompt_ids or not any(entry["n"] for entry in sums.values()):
        return {name: None for name in CI_METRICS}
    rng = random.Random(seed)
    samples: dict[str, list[float]] = {name: [] for name in CI_METRICS}
    per_prompt = [sums[pid] for pid in prompt_ids]
    for _ in range(iterations):
        draw = [per_prompt[rng.randrange(len(per_prompt))] for _ in per_prompt]
        n = sum(entry["n"] for entry in draw)
        if not n:
            continue
        for name in CI_METRICS:
            samples[name].append(sum(entry[name] for entry in draw) / n)
    tail = (1 - level) / 2 * 100
    return {name: [percentile(values, tail), percentile(values, 100 - tail)] if values else None for name, values in samples.items()}


def intervals_overlap(first: list[float] | None, second: list[float] | None) -> bool | None:
    if first is None or second is None:
        return None
    return first[0] <= second[1] and second[0] <= first[1]
