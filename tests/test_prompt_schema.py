from pathlib import Path

from benchmark.runner import load_prompts


def test_v1_has_expected_distribution_and_category_coverage():
    prompts = load_prompts(Path("prompts/dev_v1.jsonl"))
    assert len(prompts) == 30
    assert {prompt.expected_tier for prompt in prompts} == {"LOW", "MID", "HIGH"}
    assert all(sum(prompt.expected_tier == tier for prompt in prompts) == 10 for tier in ("LOW", "MID", "HIGH"))
    assert len({prompt.category for prompt in prompts}) == 10


def test_v2_sets_have_explicit_reference_models_and_balanced_difficulty():
    for name in ("dev_v2.jsonl", "quant_dev_v2.jsonl", "mle_dev_v2.jsonl"):
        prompts = load_prompts(Path("prompts") / name)
        assert len(prompts) == 30
        assert all(prompt.reference_model in {"claude-haiku", "claude-sonnet", "claude-opus"} for prompt in prompts)
        assert all(prompt.reference_rationale for prompt in prompts)
        assert all(sum(prompt.expected_tier == tier for prompt in prompts) == 10 for tier in ("LOW", "MID", "HIGH"))
