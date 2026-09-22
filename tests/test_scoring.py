from benchmark.scoring import score_decisions


def row(prompt_id, expected, selected, delta, match=True):
    return {"prompt_id": prompt_id, "expected_tier": expected, "selected_tier": selected, "tier_delta": delta, "match": match, "routing_ms": 10.0}


def test_scoring_separates_under_and_over_routing():
    metrics = score_decisions([
        row("a", "LOW", "LOW", 0),
        row("b", "HIGH", "MID", -1, False),
        row("c", "LOW", "HIGH", 2, False),
        {"prompt_id": "d", "selected_tier": None, "tier_delta": None, "match": False, "routing_ms": 20.0},
    ])
    assert metrics["rubric_agreement"] == 1 / 3
    assert metrics["under_route_rate"] == 1 / 3
    assert metrics["over_route_rate"] == 1 / 3
    assert metrics["failure_count"] == 1


def test_stability_detects_mixed_repeated_selections():
    rows = [row("a", "LOW", "LOW", 0), row("a", "LOW", "LOW", 0), row("a", "LOW", "MID", 1, False)]
    metrics = score_decisions(rows)
    assert metrics["mean_stability"] == 2 / 3
    assert metrics["unstable_prompts"] == ["a"]
