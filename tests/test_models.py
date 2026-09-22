from benchmark.models import normalize_model_name, prompt_from_dict


def test_model_aliases_normalize_to_canonical_values():
    assert normalize_model_name("claude-3-5-sonnet") == ("claude-sonnet", "MID")
    assert normalize_model_name("HIGH") == ("claude-opus", "HIGH")


def test_prompt_score_and_tier_are_derived_from_dimensions():
    prompt = prompt_from_dict({
        "id": "x",
        "category": "debugging",
        "prompt": "Explain this bug.",
        "rubric": {"reasoning_depth": 1, "scope": 1, "context_requirement": 1, "risk": 1, "specialized_knowledge": 1},
        "score": 5,
        "expected_tier": "MID",
    })
    assert prompt.expected_tier == "MID"


def test_prompt_rejects_incorrect_declared_score():
    data = {"id": "x", "category": "qa", "prompt": "Explain.", "rubric": {"reasoning_depth": 0, "scope": 0, "context_requirement": 0, "risk": 0, "specialized_knowledge": 0}, "score": 2}
    try:
        prompt_from_dict(data)
    except ValueError as exc:
        assert "incorrect score" in str(exc)
    else:
        raise AssertionError("invalid score was accepted")
