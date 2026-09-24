"""Existing metrics must keep the values produced before the v2 scoring additions.

The golden files were generated with the pre-change code (commit 903105b) and are not regenerated.
"""

import json
import sys
from pathlib import Path

import pytest

from benchmark import runner
from benchmark.config import load_config
from benchmark.reporting import build_summary

FIXTURES = Path(__file__).parent / "fixtures"
LATENCY = {"mean_routing_ms", "median_routing_ms", "p95_routing_ms"}


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def assert_contains(actual, expected, path="summary"):
    for key, value in expected.items():
        assert key in actual, f"{path}.{key} missing"
        if isinstance(value, dict):
            assert_contains(actual[key], value, f"{path}.{key}")
        else:
            assert actual[key] == value, f"{path}.{key}: {actual[key]!r} != {value!r}"


def test_summary_keeps_pre_v2_metric_values():
    golden = json.loads((FIXTURES / "golden_summary_pre_v2.json").read_text())
    config = load_config(Path("benchmark.toml"))
    summary = build_summary(
        load_jsonl(FIXTURES / "decisions.jsonl"),
        prices=config["prices"],
        target_shares=config["weighting"],
        bootstrap={"iterations": 50, "seed": 1},
        baselines={"r-b"},
    )
    assert_contains(summary, golden)


def run_fixture(tmp_path, monkeypatch, *extra):
    monkeypatch.setenv("PI_AUTO_ROUTER_COMMAND", f"{sys.executable} {FIXTURES / 'toy_router.py'}")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert runner.main(["--prompts", str(FIXTURES / "prompts.jsonl"), "--runs", "2", "--output", str(tmp_path), *extra]) == 0
    return (
        json.loads((tmp_path / "summary.json").read_text()),
        load_jsonl(tmp_path / "results.jsonl"),
        json.loads((tmp_path / "metadata.json").read_text()),
    )


def test_fixture_run_keeps_pre_v2_outputs(tmp_path, monkeypatch):
    golden = json.loads((FIXTURES / "golden_run_pre_v2.json").read_text())
    summary, results, _ = run_fixture(tmp_path, monkeypatch, "--router", "auto")
    assert_contains(summary, golden["summary"])
    assert len(results) == len(golden["results"])
    for actual, expected in zip(results, golden["results"]):
        assert_contains(actual, expected, "result")


def test_baselines_run_alongside_configured_routers(tmp_path, monkeypatch):
    summary, results, metadata = run_fixture(tmp_path, monkeypatch, "--router", "auto", "--baselines")
    routers = summary["routers"]
    assert {"pi-auto-router", "always_low", "always_mid", "always_high", "random", "length_heuristic"} == set(routers)
    assert routers["always_low"]["baseline"] and not routers["pi-auto-router"]["baseline"]
    assert metadata["skipped_routers"] == {"llm_low": "ANTHROPIC_API_KEY is not set"}
    assert metadata["router_settings"]["random"]["seed"] == 20260924
    assert metadata["model_ids"]["claude-haiku"] == "claude-haiku-4-5"
    assert metadata["git_commit"] and metadata["held_out"] is True  # fixtures live outside prompts/
    # length_heuristic is the README toy logic, like the fixture router (minus its FAIL case).
    toy = {r["prompt_id"]: r["selected_model"] for r in results if r["router"] == "pi-auto-router" and r["selected_model"]}
    heuristic = {r["prompt_id"]: r["selected_model"] for r in results if r["router"] == "length_heuristic"}
    assert all(heuristic[pid] == model for pid, model in toy.items())
    markdown = (tmp_path / "summary.md").read_text()
    assert "always_low *(baseline)*" in markdown and "assumption, not measured data" in markdown
    headings = [line for line in markdown.splitlines() if line.startswith("## ")]
    assert headings == ["## Category reference-model agreement", "## Significance", "## Unstable prompts"]


def test_default_router_selection_excludes_baselines():
    config = load_config(Path("benchmark.toml"))
    enabled = [key for key in runner.ADAPTERS if config["routers"].get(key, {}).get("enabled", key not in runner.BASELINE_KEYS)]
    assert enabled == ["auto", "model", "jev"]


def test_labels_b_file_adds_labeler_section(tmp_path, monkeypatch):
    prompts = tmp_path / "set.jsonl"
    prompts.write_text((FIXTURES / "prompts.jsonl").read_text())
    (tmp_path / "set.labels_b.jsonl").write_text(
        '{"id": "fx-001", "reference_model": "claude-haiku", "rationale": "Lookup."}\n'
        '{"id": "fx-003", "reference_model": "claude-opus", "rationale": "Ordering subtleties."}\n'
    )
    monkeypatch.setenv("PI_AUTO_ROUTER_COMMAND", f"{sys.executable} {FIXTURES / 'toy_router.py'}")
    out = tmp_path / "out"
    assert runner.main(["--prompts", str(prompts), "--router", "auto", "--runs", "1", "--output", str(out)]) == 0
    labeler = json.loads((out / "summary.json").read_text())["labeler_agreement"]
    assert labeler["agreement"] == 0.5 and labeler["disagreements"][0]["prompt_id"] == "fx-003"
    assert "## Labeler agreement" in (out / "summary.md").read_text()


def test_prompts_path_can_come_from_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ROUTING_BENCHMARK_PROMPTS", str(FIXTURES / "prompts.jsonl"))
    assert runner.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "validated 6 prompts" in out and "held out" in out


def test_repo_prompt_sets_are_not_held_out():
    assert not runner.is_held_out(Path("prompts/dev_v2.jsonl"))
    assert runner.is_held_out(Path("prompts/private/secret.jsonl"))
    assert runner.is_held_out(Path("/tmp/elsewhere.jsonl"))


def test_context_is_sent_only_when_present(tmp_path, monkeypatch):
    from benchmark.adapters import ADAPTERS
    from benchmark.models import prompt_from_dict

    echo = tmp_path / "echo.py"
    echo.write_text("import json, sys\nprint(json.dumps({'selected_model': 'haiku', 'keys': sorted(json.load(sys.stdin))}))\n")
    monkeypatch.setenv("PI_AUTO_ROUTER_COMMAND", f"{sys.executable} {echo}")
    adapter = ADAPTERS["auto"]()
    plain = prompt_from_dict({"id": "a", "category": "c", "prompt": "p", "reference_model": "haiku"})
    rich = prompt_from_dict({"id": "b", "category": "c", "prompt": "p", "reference_model": "haiku", "context": {"files_touched": ["a.py"], "has_tests": True, "repo_size_loc": 1200}})
    assert runner.route_prompt(adapter, plain).raw_output["keys"] == ["available_models", "prompt"]
    assert runner.route_prompt(adapter, rich).raw_output["keys"] == ["available_models", "context", "prompt"]


def test_legacy_adapter_without_context_parameter_still_works():
    from benchmark.models import RouteResult, prompt_from_dict

    class Legacy:
        def route(self, prompt, available_models):
            return RouteResult("claude-haiku", "LOW", 1.0)

    plain = prompt_from_dict({"id": "a", "category": "c", "prompt": "p", "reference_model": "haiku"})
    assert runner.route_prompt(Legacy(), plain).selected_tier == "LOW"


@pytest.mark.parametrize("context", [{}, {"has_tests": "yes"}, {"repo_size_loc": -1}, {"files_touched": "a.py"}])
def test_invalid_context_is_rejected(context):
    from benchmark.models import prompt_from_dict

    with pytest.raises(ValueError):
        prompt_from_dict({"id": "a", "category": "c", "prompt": "p", "reference_model": "haiku", "context": context})


def test_weighting_must_sum_to_one(tmp_path):
    config = tmp_path / "bad.toml"
    config.write_text('[models]\nlow = "claude-haiku"\nmid = "claude-sonnet"\nhigh = "claude-opus"\n[weighting]\nlow = 0.5\nmid = 0.3\nhigh = 0.1\n')
    with pytest.raises(ValueError, match="sum to 1"):
        load_config(config)


def test_missing_config_uses_default_weighting(tmp_path):
    config = load_config(tmp_path / "absent.toml")
    assert config["weighting"] == {"LOW": 0.6, "MID": 0.3, "HIGH": 0.1}
    assert config["prices"] is None
