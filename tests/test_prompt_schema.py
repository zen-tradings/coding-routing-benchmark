from pathlib import Path

from benchmark.runner import load_prompts


def test_v1_has_expected_distribution_and_category_coverage():
    prompts = load_prompts(Path("prompts/dev_v1.jsonl"))
    assert len(prompts) == 30
    assert {prompt.expected_tier for prompt in prompts} == {"LOW", "MID", "HIGH"}
    assert all(sum(prompt.expected_tier == tier for prompt in prompts) == 10 for tier in ("LOW", "MID", "HIGH"))
    assert len({prompt.category for prompt in prompts}) == 10
