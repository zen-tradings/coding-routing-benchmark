import io
import json

import pytest

from benchmark.adapters import ADAPTERS, BASELINE_KEYS
from benchmark.adapters import baselines
from benchmark.models import AVAILABLE_MODELS

LONG_PROMPT = "Refactor the order service. " * 10


@pytest.mark.parametrize("key, expected", [("always_low", "claude-haiku"), ("always_mid", "claude-sonnet"), ("always_high", "claude-opus")])
def test_constant_baselines_always_pick_their_model(key, expected):
    adapter = ADAPTERS[key]()
    for prompt in ("short", LONG_PROMPT, "Design a system"):
        result = adapter.route(prompt, AVAILABLE_MODELS)
        assert result.selected_model == expected and result.error is None


def test_length_heuristic_matches_readme_toy_router():
    adapter = ADAPTERS["length_heuristic"]()
    assert adapter.route("Explain the -r flag", AVAILABLE_MODELS).selected_tier == "LOW"
    assert adapter.route(LONG_PROMPT, AVAILABLE_MODELS).selected_tier == "MID"
    assert adapter.route("Review the ARCHITECTURE doc", AVAILABLE_MODELS).selected_tier == "HIGH"


def test_random_baseline_is_reproducible_for_a_seed():
    def sequence(seed):
        adapter = ADAPTERS["random"](options={"seed": seed})
        return [adapter.route("x", AVAILABLE_MODELS).selected_model for _ in range(50)]

    assert sequence(7) == sequence(7)
    assert sequence(7) != sequence(8)
    assert set(sequence(7)) == set(AVAILABLE_MODELS)
    assert ADAPTERS["random"](options={"seed": 7}).run_metadata()["seed"] == 7


def test_baselines_are_flagged_and_external_routers_are_not():
    assert all(ADAPTERS[key].is_baseline for key in BASELINE_KEYS)
    assert not any(ADAPTERS[key].is_baseline for key in ("auto", "model", "jev"))


def test_llm_low_is_skipped_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = ADAPTERS["llm_low"](options={"model": "claude-haiku-4-5"})
    assert "ANTHROPIC_API_KEY" in adapter.unavailable_reason()
    assert adapter.route("x", AVAILABLE_MODELS).error.startswith("configuration_error")


def test_llm_low_parses_reply_without_network(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "k")
    captured = {}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["headers"] = dict(request.header_items())
        return Response(json.dumps({"content": [{"type": "text", "text": "claude-sonnet"}]}).encode())

    monkeypatch.setattr(baselines.urllib.request, "urlopen", fake_urlopen)
    adapter = ADAPTERS["llm_low"](options={"model": "claude-haiku-4-5", "api_key_env": "TEST_KEY", "temperature": 0})
    assert adapter.unavailable_reason() is None
    result = adapter.route("Add pagination", AVAILABLE_MODELS)
    assert result.selected_model == "claude-sonnet" and result.error is None
    assert captured["body"]["model"] == "claude-haiku-4-5"
    assert captured["body"]["temperature"] == 0
    assert captured["headers"]["X-api-key"] == "k"


def test_parse_model_reply_rejects_ambiguous_answers():
    assert baselines.parse_model_reply("I would pick Opus.") == "opus"
    assert baselines.parse_model_reply("haiku or sonnet") == "haiku or sonnet"
