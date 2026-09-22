# Coding Routing Benchmark

**Which AI model should handle this coding task?** This benchmark measures how well different *model routers* answer that question.

A model router is a piece of software that looks at a developer's request (a question, a bug, a design task) and picks a model for it — something cheap and fast for easy work, something powerful for hard work. A good router saves money and time without hurting quality. A bad router either wastes money by always picking the biggest model, or hurts quality by sending hard tasks to a weak one.

This repo gives every router the **same 30 realistic coding prompts**, the **same three model choices**, and records **which tier each router picked**, **how long it took to decide**, and **whether it picks the same thing every time**.

> **Scope of v1:** this benchmark measures *routing decisions only*. It does **not** run the chosen model or grade the code it would produce. See [Roadmap](#roadmap) for what comes next.

---

## How it works

```
                 30 developer prompts  (prompts/dev_v1.jsonl)
                 each labelled LOW / MID / HIGH by a difficulty rubric
                                  │
                                  ▼
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
   Router A                Router B                Router C
   "which model?"          "which model?"          "which model?"
          │                       │                       │
          ▼                       ▼                       ▼
   normalise answer → LOW / MID / HIGH, record latency, repeat 3×
                                  │
                                  ▼
        results.jsonl · summary.json · summary.md · metadata.json
```

Every router receives exactly the same choices:

| Tier | Canonical model | Intended for |
|---|---|---|
| `LOW` | `claude-haiku` | simple, local, low-risk tasks |
| `MID` | `claude-sonnet` | normal engineering tasks that need some reasoning |
| `HIGH` | `claude-opus` | complex, ambiguous, high-context or architecture-heavy tasks |

Whatever the router replies (`"haiku"`, `"claude-3-5-sonnet"`, `"HIGH"`, …) is normalised into one of these three tiers, so routers with different naming schemes can be compared directly.

---

## What is measured

| Metric | Question it answers |
|---|---|
| **Rubric agreement** | How often does the router pick the tier our rubric expected? |
| **Under-route rate** | How often does it send a hard task to a weaker model? (quality risk) |
| **Over-route rate** | How often does it send an easy task to a stronger model? (cost waste) |
| **Routing latency** | How many milliseconds does the decision itself add? (mean / median / p95) |
| **Stability** | Asked 3 times, does it give the same answer? |
| **Tier distribution** | Does it lean cheap, lean expensive, or spread out? |
| **Failure rate** | Timeouts, unparseable output, unknown model names — reported, never hidden |
| **Per-category breakdown** | All of the above split by task type (debugging, DevOps, security, …) |

We deliberately call the main metric **rubric agreement**, not "accuracy". The expected tiers are human labels from a written rubric, not proof of which model is actually needed. See [Interpreting results](#interpreting-results).

---

## Quick start

Requires **Python 3.11+**. No third-party dependencies for running; `pytest` for tests.

```bash
git clone https://github.com/zen-tradings/coding-routing-benchmark.git
cd coding-routing-benchmark

# 1. Validate the prompt set and configuration (makes no router calls)
python3 -m benchmark.runner --dry-run
# → validated 30 prompts, 3 adapters, 3 available models
```

### Try it with a toy router (no setup needed)

The benchmark talks to routers through a simple stdin/stdout protocol, so any script works. Save this as `toy_router.py`:

```python
#!/usr/bin/env python3
import json, sys

request = json.load(sys.stdin)          # {"prompt": "...", "available_models": [...]}
text = request["prompt"].lower()

if any(word in text for word in ("design", "architecture", "multi-region")):
    choice = "opus"
elif len(text) > 200:
    choice = "sonnet"
else:
    choice = "haiku"

print(json.dumps({"selected_model": choice}))
```

Then run it through one of the adapter slots:

```bash
export PI_AUTO_ROUTER_COMMAND='python3 toy_router.py'
python3 -m benchmark.runner --router auto --runs 1 --output results/toy
cat results/toy/summary.md
```

You'll get a table like:

| Router | Rubric agreement | Under-route | Over-route | Median route ms | Stability | Failures |
|---|---:|---:|---:|---:|---:|---:|
| pi-auto-router | 50.0% | 40.0% | 10.0% | 17.39 | 100.0% | 0/30 |

### Run the full comparison

```bash
export PI_AUTO_ROUTER_COMMAND='<command for router 1>'
export PI_MODEL_ROUTER_COMMAND='<command for router 2>'
export PI_JEV_ROUTER_COMMAND='<command for router 3>'

python3 -m benchmark.runner --prompts prompts/dev_v1.jsonl --runs 3 --output results/run-001
```

30 prompts × 3 routers × 3 repetitions = 270 routing decisions. Because the selected model is never executed, this finishes in seconds and costs nothing beyond what the routers themselves charge.

### CLI options

| Flag | Default | Meaning |
|---|---|---|
| `--prompts PATH` | `prompts/dev_v1.jsonl` | Prompt set to use |
| `--runs N` | `3` (from `benchmark.toml`) | Repetitions per prompt per router |
| `--router {auto,model,jev}` | all enabled | Run a single router |
| `--output DIR` | `results/run-001` | Where to write results |
| `--config PATH` | `benchmark.toml` | Config file |
| `--dry-run` | — | Validate prompts, config and adapters without calling routers |

---

## Plugging in your own router

Each router is wrapped by an **adapter** in `benchmark/adapters/`. The three built-in adapters (`auto`, `model`, `jev`) all use the same subprocess protocol and only differ in which environment variable holds their command:

| Adapter key | Reported name | Environment variable |
|---|---|---|
| `auto` | `pi-auto-router` | `PI_AUTO_ROUTER_COMMAND` |
| `model` | `pi-model-router` | `PI_MODEL_ROUTER_COMMAND` |
| `jev` | `pi-jev-model-router` | `PI_JEV_ROUTER_COMMAND` |

### The protocol

The command is run once per routing decision. It receives JSON on **stdin**:

```json
{"prompt": "…the developer's request…", "available_models": ["claude-haiku", "claude-sonnet", "claude-opus"]}
```

and must write its choice to **stdout** as either:

- a bare string: `sonnet`, `claude-opus`, `HIGH`, …
- or a JSON object with a `selected_model`, `model`, or `tier` key: `{"selected_model": "claude-3-5-sonnet"}`

Accepted aliases include `low/mid/high`, `haiku/sonnet/opus`, `claude-haiku/-sonnet/-opus`, and versioned names like `claude-3-5-sonnet`. Anything else is recorded as an `invalid_model` failure.

### Adding a fourth router

Create `benchmark/adapters/my_router.py`:

```python
from .base import RouterAdapter

class MyRouterAdapter(RouterAdapter):
    name = "my-router"
    command_env = "MY_ROUTER_COMMAND"
```

Register it in `benchmark/adapters/__init__.py` (`ADAPTERS` dict) and add a `[routers.my]` block to `benchmark.toml`. If your router isn't a CLI, override `route()` instead and return a `RouteResult` — the runner never contains router-specific logic.

### Error handling

A broken router never aborts the run. Each failure is recorded per decision with one of:

`timeout` · `invalid_model` · `parse_error` · `router_error` · `configuration_error` (env var not set)

Failures are excluded from agreement/distribution figures and reported separately. Errors are never silently mapped to a default tier.

---

## The prompt set

`prompts/dev_v1.jsonl` contains 30 prompts: **10 LOW, 10 MID, 10 HIGH**, spread across ten kinds of developer work so that *difficulty* and *task type* are independent axes:

| Category | Count | Category | Count |
|---|---:|---|---:|
| Q&A / knowledge | 4 | Refactoring | 2 |
| Core feature development | 5 | Code review | 3 |
| Debugging | 4 | Architecture / design | 3 |
| Tests | 3 | Security | 2 |
| DevOps / infrastructure | 3 | Documentation | 1 |

### How expected tiers are assigned

Each prompt is scored 0–2 on five dimensions; the total decides the tier:

| Dimension | 0 | 1 | 2 |
|---|---|---|---|
| Reasoning depth | direct | multi-step | deep / ambiguous |
| Scope | single function | module | multi-component / system |
| Context requirement | self-contained | several constraints | broad, interacting constraints |
| Risk of a wrong answer | low | moderate | high |
| Specialised knowledge | common | framework / domain | advanced systems |

```
total 0–3  → LOW    total 4–7  → MID    total 8–10 → HIGH
```

7 prompts sit near a tier boundary and are flagged `"boundary": true` so results can be reported with and without the contested cases.

### Prompt format

```json
{
  "id": "debug-003",
  "category": "debugging",
  "prompt": "An async FastAPI endpoint occasionally serves stale cached data after an update…",
  "rubric": {"reasoning_depth": 1, "scope": 1, "context_requirement": 1, "risk": 1, "specialized_knowledge": 1},
  "score": 5,
  "expected_tier": "MID",
  "boundary": false
}
```

`score` and `expected_tier` are validated against the rubric on load, so a mislabelled prompt fails fast.

### Rules for prompts

- Realistic, specific tasks — not "design a cache" but a real request with constraints.
- Never leak the answer: no "this is simple", no "use the strongest model", no model names.
- The set is **versioned benchmark data**. Once results are published, `dev_v1` is frozen; changes go into `dev_v2`.

---

## Output files

Each run writes to the `--output` directory:

| File | Contents |
|---|---|
| `results.jsonl` | One line per routing decision (router, prompt, expected vs. selected tier, `tier_delta`, latency, error) |
| `summary.json` | Aggregated metrics per router and per category, machine-readable |
| `summary.md` | The same as a Markdown report you can paste into an issue or PR |
| `metadata.json` | Timestamp, git commit, prompt set, routers, repetitions, timeout, model list, Python/platform — everything needed to reproduce |

`tier_delta = selected − expected`, with LOW=0, MID=1, HIGH=2:

```
-2  heavy under-route     -1  under-route     0  match     +1  over-route     +2  heavy over-route
```

---

## Interpreting results

- **There is no single "winner" metric.** A router with 90% agreement but 400 ms latency and a router with 75% agreement, zero over-routing and 5 ms latency are optimising for different things. The report is designed to expose trade-offs.
- **Agreement ≠ accuracy.** The rubric is a considered human opinion about what tier a task *probably* needs. Phase 2 (below) will test that empirically.
- **Look at under- vs over-routing separately.** Under-routing costs quality; over-routing costs money. Which matters more depends on your use case.
- **Tier distribution is a fingerprint, not a score.** "LOW 55% / MID 38% / HIGH 7%" tells you a router's personality, not whether it's right.

---

## Roadmap

| Phase | Goal | Status |
|---|---|---|
| **1 — Routing fingerprint** (this repo) | Same prompts, same choices → which tier, how fast, how stable | ✅ v1 |
| **2 — Empirical sufficiency** | Actually run Haiku, Sonnet and Opus on a subset; find the *cheapest model that passes*; compare routers against that instead of the rubric | planned |
| **3 — Cost / latency / quality frontier** | Add tokens, cost, TTFT, task success; evaluate routers on the real objective | planned |
| **4 — Repository-aware tasks** | Multi-file bug fixes, CI repair, refactors; possible SWE-bench-style integration | later |

Full design notes live in [`PLAN.md`](PLAN.md).

---

## Repository layout

```
benchmark.toml          runs, timeout, canonical models, enabled routers
benchmark/
  runner.py             CLI entry point
  models.py             Prompt / Rubric / RouteResult dataclasses, model-name normalisation
  scoring.py            agreement, under/over-routing, stability, latency, failures
  reporting.py          summary.json + summary.md
  adapters/
    base.py             subprocess protocol shared by all adapters
    auto_router.py, model_router.py, jev_router.py
prompts/
  dev_v1.jsonl          the 30-prompt benchmark set (frozen)
  README.md
results/                run outputs (git-ignored except .gitkeep)
tests/                  schema validation, scoring, normalisation
PLAN.md                 full design document and rationale
```

---

## Development

```bash
python3 -m pytest
```

Contributions welcome — particularly new router adapters, and reviews of the rubric labels in `prompts/dev_v1.jsonl` (open an issue rather than editing `dev_v1` directly; label changes go into `dev_v2`).
