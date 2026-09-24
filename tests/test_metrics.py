import pytest

from benchmark.labels import cohens_kappa, labeler_agreement
from benchmark.models import prompt_from_dict
from benchmark.scoring import bootstrap_ci, intervals_overlap, relative_cost_error, score_extended, tier_distance

PRICES = {"claude-haiku": 6.0, "claude-sonnet": 12.0, "claude-opus": 30.0}
MODEL = {"LOW": "claude-haiku", "MID": "claude-sonnet", "HIGH": "claude-opus"}
EVEN = {"LOW": 1 / 3, "MID": 1 / 3, "HIGH": 1 / 3}


def row(prompt_id, expected, selected, router="r"):
    return {
        "router": router, "prompt_id": prompt_id, "expected_tier": expected, "reference_model": MODEL[expected],
        "selected_tier": selected, "selected_model": MODEL.get(selected), "match": expected == selected,
    }


def test_tier_distance_uses_low0_mid1_high2():
    assert tier_distance("LOW", "LOW") == 0
    assert tier_distance("LOW", "HIGH") == 2
    assert tier_distance("HIGH", "MID") == 1


def test_relative_cost_error_uses_configured_prices():
    assert relative_cost_error("claude-opus", "claude-haiku", PRICES) == 4.0
    assert relative_cost_error("claude-haiku", "claude-opus", PRICES) == pytest.approx(-0.8)
    assert relative_cost_error("claude-sonnet", "claude-sonnet", PRICES) == 0.0


def test_severity_and_cost_metrics():
    rows = [row("a", "LOW", "HIGH"), row("b", "HIGH", "LOW"), row("c", "MID", "MID"), {"prompt_id": "d", "expected_tier": "MID", "selected_tier": None}]
    metrics = score_extended(rows, PRICES, EVEN)
    assert metrics["mean_tier_distance"] == pytest.approx(4 / 3)
    assert metrics["mean_under_distance"] == pytest.approx(2 / 3)
    assert metrics["mean_over_distance"] == pytest.approx(2 / 3)
    assert metrics["cost_weighted_error"] == pytest.approx((4.0 + 0.8 + 0) / 3)
    assert metrics["mean_signed_cost_error"] == pytest.approx((4.0 - 0.8) / 3)
    assert metrics["cost_ratio"] == pytest.approx((30 + 6 + 12) / (6 + 30 + 12))


def test_cost_metrics_are_none_without_prices():
    metrics = score_extended([row("a", "LOW", "LOW")], None, EVEN)
    assert metrics["cost_weighted_error"] is None and metrics["reweighted"]["cost_weighted_error"] is None


def test_reweighting_averages_tiers_by_target_share():
    # LOW prompts: 3 of 4 correct; HIGH prompts: 0 of 1 correct. Unweighted 3/5.
    rows = [row("l1", "LOW", "LOW"), row("l2", "LOW", "LOW"), row("l3", "LOW", "LOW"), row("l4", "LOW", "MID"), row("h1", "HIGH", "MID")]
    metrics = score_extended(rows, PRICES, {"LOW": 0.6, "MID": 0.3, "HIGH": 0.1})
    assert metrics["agreement"] == pytest.approx(3 / 5)
    # MID is absent, so shares renormalise over LOW and HIGH: (0.6 * 0.75 + 0.1 * 0) / 0.7
    assert metrics["reweighted"]["agreement"] == pytest.approx(0.45 / 0.7)
    assert metrics["reweighted"]["under_route_rate"] == pytest.approx(0.1 / 0.7)
    assert metrics["reweighted"]["over_route_rate"] == pytest.approx(0.6 * 0.25 / 0.7)
    assert metrics["reweighted_tiers_missing"] == ["MID"]


def test_reweighting_with_matching_shares_equals_unweighted():
    rows = [row("l", "LOW", "LOW"), row("m", "MID", "HIGH"), row("h", "HIGH", "LOW")]
    metrics = score_extended(rows, PRICES, EVEN)
    for name in ("agreement", "under_route_rate", "over_route_rate", "mean_tier_distance", "cost_weighted_error"):
        assert metrics["reweighted"][name] == pytest.approx(metrics[name])


def test_bootstrap_ci_is_seeded_and_brackets_the_estimate():
    rows = [row(f"p{i}", "LOW", "LOW" if i % 3 else "MID") for i in range(30)]
    first = bootstrap_ci(rows, 500, seed=1)
    assert first == bootstrap_ci(rows, 500, seed=1)
    # With a coarse 30-prompt grid, CI endpoints can coincide across seeds; compare few-iteration draws instead.
    assert bootstrap_ci(rows, 5, seed=1) != bootstrap_ci(rows, 5, seed=2)
    low, high = first["agreement"]
    assert low <= 20 / 30 <= high and 0 <= low < high <= 1
    assert first["under_route_rate"] == [0.0, 0.0]


def test_bootstrap_resamples_prompts_not_decisions():
    # Two repeats per prompt that always agree: every resample keeps repeats together.
    rows = [row(f"p{i}", "LOW", "LOW" if i < 5 else "MID") for i in range(10) for _ in range(2)]
    ci = bootstrap_ci(rows, 200, seed=3)
    assert all(value * 10 == pytest.approx(round(value * 10)) for value in ci["agreement"])


def test_bootstrap_ci_is_none_without_successful_decisions():
    assert bootstrap_ci([{"prompt_id": "a", "selected_tier": None}], 10, 0)["agreement"] is None


def test_interval_overlap():
    assert intervals_overlap([0.1, 0.4], [0.3, 0.6]) is True
    assert intervals_overlap([0.1, 0.2], [0.3, 0.6]) is False
    assert intervals_overlap(None, [0.3, 0.6]) is None


def test_cohens_kappa_known_values():
    assert cohens_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    # Worked example: po = 0.7, pe = 0.5 * 0.6 + 0.5 * 0.4 = 0.5 -> kappa = 0.4
    first = ["y"] * 5 + ["n"] * 5
    second = ["y", "y", "y", "y", "n", "y", "y", "n", "n", "n"]
    assert cohens_kappa(first, second) == pytest.approx(0.4)
    assert cohens_kappa(["a", "a"], ["a", "a"]) is None


def test_labeler_agreement_scores_routers_on_consensus_prompts_only():
    prompts = [prompt_from_dict({"id": pid, "category": "c", "prompt": "p", "reference_model": model}) for pid, model in (("a", "haiku"), ("b", "sonnet"), ("c", "opus"))]
    labels_b = {"a": {"reference_model": "claude-haiku", "rationale": "r"}, "b": {"reference_model": "claude-opus", "rationale": "r"}}
    decisions = [row("a", "LOW", "LOW"), row("b", "MID", "MID"), row("c", "HIGH", "LOW")]
    result = labeler_agreement(prompts, labels_b, decisions, "x.labels_b.jsonl")
    assert result["prompts_compared"] == 2 and result["agreement"] == 0.5
    assert result["prompts_missing_labeler_b"] == ["c"]
    assert [item["prompt_id"] for item in result["disagreements"]] == ["b"]
    assert result["router_agreement_on_consensus"]["r"] == {"agreement": 1.0, "successful_decisions": 1}
