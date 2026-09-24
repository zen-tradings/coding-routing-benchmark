# Coding Routing Benchmark

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Which AI model should handle this coding task?** This benchmark measures how well different *model routers* answer that question.

A model router reads a developer's request and picks a model for it — cheap and fast for easy work, powerful for hard work. A bad router either wastes money (always picks the biggest model) or hurts quality (sends hard tasks to a weak one). This repo gives every router the **same prompt set** and **same three model choices**, then records **which model each router directly picked, how long it took, and how stable its answers are** — normalised into `LOW` / `MID` / `HIGH` tiers for analysis.

> **Scope of the current harness:** routing decisions only. It does not execute the selected model or judge task completion. The benchmark compares each router's model choice with a reference choice for the query. See the [benchmark review](BENCHMARK_REVIEW.md) for the prompt-set limitations and evaluation guidance.

## How it works

```
30 prompts, each with a reference Claude model and a written rationale
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
 Router A  Router B  Router C        every router sees the same choices:
   │          │          │           LOW → claude-haiku
   ▼          ▼          ▼           MID → claude-sonnet
 each router directly returns a    HIGH → claude-opus
 model name → normalised to
 LOW/MID/HIGH tier for scoring,
 latency recorded, repeated 3×
              │
              ▼
 results.jsonl · summary.json · summary.md · metadata.json
```

Routers answer with a **model name**, never a tier — whatever a router replies (`"haiku"`, `"claude-3-5-sonnet"`, `"HIGH"`, …) is mapped to one of the three canonical models, and that model maps to a tier for scoring. The tier labels exist only so routers with different naming schemes compare directly.

### What is measured

- **Reference-model agreement** — did the router pick the model specified by the benchmark's reference routing policy? This measures agreement with that policy, not universal routing correctness.
- **Under-routing** — hard task → weak model (quality risk)
- **Over-routing** — easy task → strong model (cost waste)
- **Decision latency** — mean / median / p95, of the routing call only
- **Stability** — same answer across repeats?
- **Per-category breakdown** and **failure rate** (timeouts, parse errors, unknown models — reported separately, never hidden)
- **Tier distance** — how far off a wrong pick is (LOW=0, MID=1, HIGH=2), overall and split into under- and over-routing
- **Cost-weighted error** — how much a wrong pick costs, relative to the reference model's price
- **Reweighted metrics** — the same numbers with reference tiers weighted to an *assumed* realistic workload
- **95% confidence intervals** and a note wherever two routers can't be told apart at this sample size
- **Labeler agreement** — when a second set of labels exists, how much two labelers agree (Cohen's kappa)

Built-in [baseline routers](#baseline-routers) run alongside the real routers, so every score has a floor to compare against.

## Quick start

Requires **Python 3.11+**, no third-party dependencies (`pytest` for tests).

```bash
git clone https://github.com/zen-tradings/coding-routing-benchmark.git
cd coding-routing-benchmark
python3 -m benchmark.runner --dry-run     # validate prompts & config, no router calls
```

### Try it with a toy router

The benchmark talks to routers via stdin/stdout, so any script works. Save this as `toy_router.py`:

```python
#!/usr/bin/env python3
import json, sys
text = json.load(sys.stdin)["prompt"].lower()   # {"prompt": ..., "available_models": [...]}
choice = "opus" if any(w in text for w in ("design", "architecture")) else \
         "sonnet" if len(text) > 200 else "haiku"
print(json.dumps({"selected_model": choice}))
```

```bash
export PI_AUTO_ROUTER_COMMAND='python3 toy_router.py'
python3 -m benchmark.runner --router auto --runs 1 --output results/toy
cat results/toy/summary.md
```

### Example output

The `summary.md` report is a table in this shape — run the commands above to fill it with your own numbers:

| Router | Agreement (95% CI) | Reweighted agreement | Mean tier distance | Cost-weighted error | Median route ms | Stability | Failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| pi-auto-router | …% (…–…) | …% | … | …% | … | …% | …/30 |
| always_mid *(baseline)* | …% (…–…) | …% | … | …% | … | …% | …/30 |

Below that come a routing-errors table (under/over rates with CIs, reweighted values, cost ratio), per-category agreement, significance notes, a labeler-agreement section when a second label file exists, and the prompts where a router gave inconsistent answers across repeats. `summary.json` has the same data. No official results are published yet.

### Run the full comparison

```bash
export PI_AUTO_ROUTER_COMMAND='<command for router 1>'
export PI_MODEL_ROUTER_COMMAND='<command for router 2>'
export PI_JEV_ROUTER_COMMAND='<command for router 3>'
python3 -m benchmark.runner --prompts prompts/dev_v2.jsonl --runs 3 --output results/run-001
```

30 prompts × 3 routers × 3 repetitions = 270 decisions. Since models are never executed, this costs nothing beyond what the routers themselves charge.

**CLI options:** `--prompts PATH` (default `$ROUTING_BENCHMARK_PROMPTS`, else `prompts/dev_v2.jsonl`) · `--runs N` · `--router NAME` (single router) · `--baselines` (also run every baseline) · `--output DIR` · `--config PATH` (default `benchmark.toml`) · `--dry-run`.

### Baseline routers

Baselines need no external command. They are registered in `benchmark.toml` with `enabled = false`, so a default run still uses only the configured routers. `--baselines` adds all of them to whatever else runs:

```bash
python3 -m benchmark.runner --baselines --runs 1 --output results/baselines
```

| Baseline | Picks |
|---|---|
| `always_low` / `always_mid` / `always_high` | the same model every time |
| `random` | a uniformly random model; seeded by `[routers.random] seed`, which is recorded in `metadata.json` |
| `length_heuristic` | the [toy router](#try-it-with-a-toy-router) logic: `design`/`architecture` → Opus, over 200 characters → Sonnet, otherwise Haiku |
| `llm_low` | the LOW-tier model (`model_ids.claude-haiku`) asked to route, one Messages API call per decision using only the standard library. Needs `ANTHROPIC_API_KEY`; without it the router is skipped with a message and listed as skipped in the summary. Each call is billed at Haiku rates. |

Baselines are marked *(baseline)* in every summary table and `"baseline": true` in `summary.json`. A candidate router that can't beat `always_mid` or `length_heuristic` on a set adds no information on that set.

## Plugging in your own router

The built-in adapters run the command in their environment variable once per decision. It receives on **stdin**:

```json
{"prompt": "…", "available_models": ["claude-haiku", "claude-sonnet", "claude-opus"]}
```

If a prompt has an optional [`context`](prompts/README.md#optional-structured-context) object, the payload also has a `"context"` key. Prompts without one send exactly the payload above, so existing routers keep working.

The router answers on **stdout** with either a bare string (`sonnet`, `HIGH`) or JSON (`{"selected_model": "claude-3-5-sonnet"}`).

| Adapter | Env var |
|---|---|
| `auto` | `PI_AUTO_ROUTER_COMMAND` |
| `model` | `PI_MODEL_ROUTER_COMMAND` |
| `jev` | `PI_JEV_ROUTER_COMMAND` |

If your router calls a model, set `model = "<exact model id>"` in its `[routers.<name>]` block so the id is recorded in `metadata.json`.

To add a router: subclass `RouterAdapter` in `benchmark/adapters/` (set `name` and `command_env`, or override `route()`), register it in the `ADAPTERS` dict, and add a `[routers.<name>]` block to `benchmark.toml`.

## The prompt set

`prompts/dev_v2.jsonl` is the default set: 30 realistic software-development work requests with explicit reference model and rationale, balanced 10 Haiku / 10 Sonnet / 10 Opus. V1 remains available as a legacy baseline and derives the reference tier from a rubric. The `reference_model` and `reference_rationale` fields are stored for scoring and analysis; only the prompt text is sent to the router.

Prompt files are **versioned benchmark data**: once results are published for a version, keep that file immutable and put revisions in the next version.

**Reference labels are tied to a model generation.** A label says which of the *current* Haiku, Sonnet, and Opus should handle a task. When those models are updated, the right choice for some prompts can change. Every run records the exact model id behind each candidate (`[model_ids]` in `benchmark.toml`), each router's configured model, the repo's git SHA, and whether the working tree was dirty. Compare results only across runs with the same model ids, and re-review labels in a new prompt-set version when the ids change.

**Second labels, held-out sets, and context.** A set can have an optional second-labeler file (`<set>.labels_b.jsonl`) for measuring label reliability. You can keep a private held-out set that is never committed, under `prompts/private/` or outside the repo; `metadata.json` then records `"held_out": true`. Future prompt versions can carry a structured `context` object. Formats and workflow are in the [prompt documentation](prompts/README.md).

### Domain-specific prompt sets

Quant development and machine-learning engineering are separate datasets so their routing patterns can be inspected independently:

```bash
python3 -m benchmark.runner --prompts prompts/quant_dev_v2.jsonl --output results/quant-dev-v2
python3 -m benchmark.runner --prompts prompts/mle_dev_v2.jsonl --output results/mle-dev-v2
```

Each v2 set has 30 prompts, balanced 10 / 10 / 10 across reference models, with detailed task context, constraints, and acceptance criteria. Quant prompts cover market data, research validity, signals, execution, portfolio risk, and controls. MLE prompts cover data quality, feature pipelines, training, evaluation, serving, and operations. They are original, task-shaped prompts informed by common engineering work; they are not verbatim items imported from public benchmarks. See [prompt documentation](prompts/README.md) and the [benchmark review](BENCHMARK_REVIEW.md) for provenance and interpretation limits.

## Interpreting results

There is no single "winner" metric. Under-routing costs quality, over-routing costs money — which matters more depends on you. A router's tier distribution (how often it picks LOW vs. MID vs. HIGH) is its *fingerprint*, not a score.

How to read the numbers:

- **Agreement (95% CI)** — the share of successful decisions that match the reference, with a bootstrap interval. Prompts are resampled with all their repeats together, 2000 iterations, seeded from `[bootstrap]`. With 30 prompts the intervals are wide; read agreement as a range, not a point.
- **Significance notes** — for each pair of routers, the report says whether their agreement intervals overlap. Overlap means the difference is not established at this sample size. It is a conservative check, not a formal test.
- **Mean tier distance** — 0 is perfect, 2 is always the opposite extreme. It separates a router that misses by one tier from one that sends Opus work to Haiku. *Under distance* and *over distance* split it by direction and add up to the total.
- **Cost-weighted error** — the mean of |chosen price − reference price| / reference price, using the `[prices]` block in `benchmark.toml` (input + output list price per million tokens; only ratios between models matter). It is asymmetric by construction: over-routing Haiku work to Opus costs +400%, while under-routing Opus work to Haiku can't go below −80%. **Cost ratio** (total chosen price / total reference price) shows net over- or under-spend.
- **Reweighted** — the v2 sets are balanced 10/10/10, but real traffic is mostly easy work. Reweighted values average each reference tier separately, then combine the tiers with the `[weighting]` shares (default LOW 0.6 / MID 0.3 / HIGH 0.1). **These shares are an assumption, not measured data.** Change them to match your own traffic. Under reweighting, `always_low` looks much better and `always_high` much worse than in the balanced numbers; that gap is the point.
- **Labeler agreement** — with a second label file, Cohen's kappa shows how much of the labelers' agreement is beyond chance. Router agreement on consensus-only prompts removes prompts whose labels are themselves disputed.

## Roadmap

1. **Routing fingerprint** (this repo) — same prompts, same choices → which model, how fast, how stable ✅
2. **Empirical sufficiency** — actually run all three models on a subset; find the *cheapest model that passes*; score routers against that
3. **Cost / latency / quality frontier** — add tokens, cost, task success
4. **Repository-aware tasks** — multi-file fixes, CI repair, refactors

## Known limitations and open work

**Benchmark validity**

1. **Sample size.** 30 prompts per set gives wide confidence intervals (about ±17 points on agreement), too wide to rank most routers. Around 100+ prompts per set would be needed to tell routers apart.
2. **Single labeler.** Reference labels come from one author. Second-labeler support exists, but no `<set>.labels_b.jsonl` file has been written yet.
3. **Agreement, not accuracy.** Reference choices are policy judgments. Empirical sufficiency (roadmap step 2) is needed before any score can be called routing accuracy.
4. **Boundary flags are unused.** v1 prompts carry `boundary: true`, but results are not yet reported with and without boundary prompts, and v2 has no boundary flags.
5. **Subprocess latency.** External routers start a new process per decision, so `routing_ms` includes interpreter start-up, not just routing time.

**Engineering**

6. **No re-scoring command.** Summaries can't be rebuilt from an existing `results.jsonl`, for example after adding second labels or changing prices; a full re-run is required.
7. **No CI.** Tests are not run automatically on push.
8. **Docs drift.** `BENCHMARK_REVIEW.md` is linked but missing, and the `doc/` site lags this README.
9. **Fixed model pool.** Configuration accepts exactly Haiku, Sonnet, and Opus; adding models or providers needs code changes.
10. **No retries in `llm_low`.** A rate limit or transient server error is recorded as a failed decision.

## Development

```bash
python3 -m pytest
```

## Contributing

Contributions welcome — especially:

- **New router adapters** — see [Plugging in your own router](#plugging-in-your-own-router)
- **Reference-label reviews** — keep published versions immutable and put reviewed changes in a new prompt-set version
- **Benchmark results** — include the run's `metadata.json` so results are reproducible

## License

[MIT](LICENSE)
